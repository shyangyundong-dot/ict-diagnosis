import json
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models.diagnosis import DiagnosisRecord, ChatSession
from rules.engine import run_diagnosis, RULE_VERSION
from ai_chat import (
    chat_with_ai,
    get_missing_fields,
    FIELD_DEFINITIONS,
    normalize_project_type_field,
    build_fields_display,
)
from report_generator import generate_report_html, generate_pdf
from ai_report import enrich_diagnosis_with_ai

router = APIRouter(prefix="/api")


# ── Pydantic 模型 ──────────────────────────────────────────────

class ChatMessage(BaseModel):
    session_id: str | None = None
    message: str
    fields: dict | None = None  # 前端当前编辑态，先发后合并再调模型


class SessionFieldsBody(BaseModel):
    fields: dict

class ConfirmSubmit(BaseModel):
    session_id: str
    fields: dict           # 用户在前端确认/修改后的最终字段

class DiagnoseDirectly(BaseModel):
    bpm_id: str
    project_type: str
    fields: dict


# ── 对话接口 ───────────────────────────────────────────────────

@router.post("/chat")
async def chat(body: ChatMessage, db: Session = Depends(get_db)):
    """对话式收集项目信息"""

    # 获取或创建会话
    session_id = body.session_id or str(uuid.uuid4())
    session = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()

    if not session:
        session = ChatSession(
            session_id=session_id,
            messages_json="[]",
            extracted_fields_json="{}",
            status="collecting",
        )
        db.add(session)
        db.commit()
        db.refresh(session)

    messages: list = json.loads(session.messages_json)
    current_fields: dict = json.loads(session.extracted_fields_json)

    if body.fields is not None:
        current_fields.update(body.fields)

    # 添加用户消息
    messages.append({"role": "user", "content": body.message})

    pt_ctx = current_fields.get("project_type")
    if isinstance(pt_ctx, list):
        project_type_for_ai = json.dumps(pt_ctx, ensure_ascii=False) if pt_ctx else None
    else:
        project_type_for_ai = pt_ctx

    ai_result = await chat_with_ai(messages, current_fields, project_type_for_ai)

    new_fields = ai_result.get("extracted", {})
    current_fields.update({k: v for k, v in new_fields.items() if v is not None})
    normalize_project_type_field(current_fields)

    missing = get_missing_fields(current_fields)
    is_complete = len(missing) == 0

    messages.append({"role": "assistant", "content": ai_result["reply"]})

    session.messages_json = json.dumps(messages, ensure_ascii=False)
    session.extracted_fields_json = json.dumps(current_fields, ensure_ascii=False)
    session.status = "confirmed" if is_complete else "collecting"
    db.commit()

    fields_display = build_fields_display(current_fields)

    return {
        "session_id": session_id,
        "reply": ai_result["reply"],
        "extracted_fields": current_fields,
        "fields_display": fields_display,
        "missing_fields": missing,
        "is_complete": is_complete,
        "status": session.status,
    }


@router.patch("/session/{session_id}/fields")
async def patch_session_fields(session_id: str, body: SessionFieldsBody, db: Session = Depends(get_db)):
    """仅更新结构化字段（右侧手工修改），不触发对话。"""
    session = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    current_fields: dict = json.loads(session.extracted_fields_json)
    current_fields.update(body.fields)
    normalize_project_type_field(current_fields)

    missing = get_missing_fields(current_fields)
    is_complete = len(missing) == 0

    session.extracted_fields_json = json.dumps(current_fields, ensure_ascii=False)
    session.status = "confirmed" if is_complete else "collecting"
    db.commit()

    return {
        "session_id": session_id,
        "extracted_fields": current_fields,
        "fields_display": build_fields_display(current_fields),
        "missing_fields": missing,
        "is_complete": is_complete,
        "status": session.status,
    }


@router.get("/field-definitions")
async def field_definitions():
    """供前端渲染下拉/多选。"""
    return FIELD_DEFINITIONS


@router.post("/confirm")
async def confirm_and_diagnose(body: ConfirmSubmit, db: Session = Depends(get_db)):
    """用户确认字段后提交诊断"""

    session = db.query(ChatSession).filter(ChatSession.session_id == body.session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    fields = dict(body.fields)
    normalize_project_type_field(fields)
    session.extracted_fields_json = json.dumps(fields, ensure_ascii=False)

    bpm_id = fields.get("bpm_id") or "未填写"
    if isinstance(bpm_id, str) and not bpm_id.strip():
        bpm_id = "未填写"

    pt = fields.get("project_type")
    if isinstance(pt, list) and pt:
        pt_for_rules = pt
        project_type_db = ",".join(pt)
    elif isinstance(pt, str) and pt.strip():
        pt_for_rules = [pt.strip()]
        project_type_db = pt.strip()
    else:
        pt_for_rules = ["system_integration"]
        project_type_db = "system_integration"

    result = run_diagnosis(pt_for_rules, fields)

    # 获取对话历史用于AI个性化分析
    chat_history = None
    if session:
        try:
            chat_history = json.loads(session.messages_json)
        except Exception:
            chat_history = None

    # B方案：用AI针对具体项目生成个性化分析（含A方案的板块分节）
    try:
        result = await enrich_diagnosis_with_ai(result, fields, chat_history)
    except Exception as e:
        # AI丰富化失败不影响主流程，降级为原始规则输出
        result["ai_enriched"] = False
        result["ai_error"] = str(e)

    # 保存诊断记录（对话快照仅用于溯源，不进入报告）
    record = DiagnosisRecord(
        bpm_id=bpm_id,
        project_type=project_type_db,
        input_json=json.dumps(fields, ensure_ascii=False),
        chat_snapshot_json=session.messages_json,
        overall_risk=result["overall_risk"],
        result_json=json.dumps(result, ensure_ascii=False),
        rule_version=RULE_VERSION,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return {
        "diagnosis_id": record.id,
        "bpm_id": bpm_id,
        "overall_risk": result["overall_risk"],
        "overall_risk_label": result["overall_risk_label"],
        "triggered_rules": result["triggered_rules"],
        "tips": result["tips"],
        "audit_checklist": result["audit_checklist"],
        "rule_version": result["rule_version"],
        "created_at": record.created_at.strftime("%Y-%m-%d %H:%M") if record.created_at else "",
    }


@router.get("/diagnose/by-bpm")
async def list_diagnoses_by_bpm(
    bpm_id: str = Query(..., description="BPM 商机编码（与填报时一致，精确匹配）"),
    db: Session = Depends(get_db),
):
    """按 BPM 商机编码查询历史诊断记录（同一编码可有多条，按时间倒序）。"""
    key = (bpm_id or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="请提供 BPM 商机编码")

    records = (
        db.query(DiagnosisRecord)
        .filter(DiagnosisRecord.bpm_id == key)
        .order_by(DiagnosisRecord.created_at.desc())
        .all()
    )

    items = []
    for rec in records:
        result = json.loads(rec.result_json)
        items.append(
            {
                "diagnosis_id": rec.id,
                "bpm_id": rec.bpm_id,
                "project_type": rec.project_type,
                "overall_risk": rec.overall_risk,
                "overall_risk_label": result.get("overall_risk_label", ""),
                "rule_version": rec.rule_version,
                "created_at": rec.created_at.strftime("%Y-%m-%d %H:%M") if rec.created_at else "",
            }
        )

    return {"bpm_id": key, "count": len(items), "items": items}


@router.get("/diagnose/{diagnosis_id}/traceability")
async def get_diagnosis_traceability(diagnosis_id: int, db: Session = Depends(get_db)):
    """填报溯源：返回提交时的确认字段与对话快照（不用于报告正文）。"""
    record = db.query(DiagnosisRecord).filter(DiagnosisRecord.id == diagnosis_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="诊断记录不存在")

    try:
        confirmed_fields = json.loads(record.input_json)
    except Exception:
        confirmed_fields = {}

    chat_messages: list = []
    raw = record.chat_snapshot_json
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                chat_messages = parsed
        except Exception:
            chat_messages = []

    fields_display = build_fields_display(confirmed_fields) if confirmed_fields else []

    return {
        "diagnosis_id": record.id,
        "bpm_id": record.bpm_id,
        "project_type": record.project_type,
        "rule_version": record.rule_version,
        "created_at": record.created_at.strftime("%Y-%m-%d %H:%M") if record.created_at else "",
        "confirmed_fields": confirmed_fields,
        "fields_display": fields_display,
        "chat_messages": chat_messages,
        "has_chat_snapshot": bool(chat_messages),
    }


@router.get("/diagnose/{diagnosis_id}")
async def get_diagnosis(diagnosis_id: int, db: Session = Depends(get_db)):
    """按ID读取历史诊断报告"""
    record = db.query(DiagnosisRecord).filter(DiagnosisRecord.id == diagnosis_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="报告不存在")

    result = json.loads(record.result_json)
    return {
        "diagnosis_id": record.id,
        "bpm_id": record.bpm_id,
        "overall_risk": record.overall_risk,
        "overall_risk_label": result.get("overall_risk_label", ""),
        "triggered_rules": result.get("triggered_rules", []),
        "tips": result.get("tips", []),
        "audit_checklist": result.get("audit_checklist", []),
        "rule_version": record.rule_version,
        "created_at": record.created_at.strftime("%Y-%m-%d %H:%M") if record.created_at else "",
        # 以下字段存于 result_json，供前端 /report/:id 与下载 HTML 一致（分板块、AI 标识）
        "segments": result.get("segments"),
        "ai_enriched": result.get("ai_enriched", False),
        "is_mixed_project": result.get("is_mixed_project", False),
    }


@router.get("/report/{diagnosis_id}/html", response_class=HTMLResponse)
async def get_report_html(diagnosis_id: int, db: Session = Depends(get_db)):
    """获取HTML格式报告"""
    record = db.query(DiagnosisRecord).filter(DiagnosisRecord.id == diagnosis_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="报告不存在")
    result = json.loads(record.result_json)
    created_at = record.created_at.strftime("%Y-%m-%d %H:%M") if record.created_at else ""
    html = generate_report_html(record.id, record.bpm_id, result, created_at)
    return HTMLResponse(content=html)


@router.get("/report/{diagnosis_id}/pdf")
async def get_report_pdf(diagnosis_id: int, db: Session = Depends(get_db)):
    """获取PDF格式报告"""
    record = db.query(DiagnosisRecord).filter(DiagnosisRecord.id == diagnosis_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="报告不存在")
    result = json.loads(record.result_json)
    created_at = record.created_at.strftime("%Y-%m-%d %H:%M") if record.created_at else ""
    html = generate_report_html(record.id, record.bpm_id, result, created_at)
    pdf_bytes = await generate_pdf(html)
    if pdf_bytes:
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=report_{diagnosis_id}.pdf"},
        )
    else:
        # 降级为HTML下载
        return Response(
            content=html.encode("utf-8"),
            media_type="text/html",
            headers={"Content-Disposition": f"attachment; filename=report_{diagnosis_id}.html"},
        )


@router.get("/health")
async def health():
    return {"status": "ok", "rule_version": RULE_VERSION}
