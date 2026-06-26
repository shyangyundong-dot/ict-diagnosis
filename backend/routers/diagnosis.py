import json
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db
from models.diagnosis import DiagnosisRecord, ChatSession, DissentRecord, Line, User
from rules.engine import (
    run_diagnosis,
    RULE_VERSION,
    get_realtime_warnings,
    enforce_hardware_no_listing,
)
from ai_chat import (
    chat_with_ai,
    segment_accounting_units,
    get_missing_fields,
    FIELD_DEFINITIONS,
    normalize_project_type_field,
    migrate_legacy_service_fields,
    strip_deprecated_input_fields,
    apply_derived_fields_for_diagnosis,
    build_fields_display,
)
from report_generator import generate_report_html, generate_pdf
from ai_report import enrich_diagnosis_with_ai

router = APIRouter(prefix="/api")


# ── 权限辅助 ──────────────────────────────────────────────────
# 数据隔离规则（设计文档 §3）：
#   user      → 仅自己创建的
#   reviewer  → 自己创建的 + 本线条内所有员工创建的
#   admin     → 全部（含 created_by IS NULL 的存量数据）
# 拒绝访问统一返回 404，避免泄漏「这条记录存在但你看不到」。

def filter_diagnoses_for_user(q, user: User):
    """给 DiagnosisRecord 查询追加按角色与线条的过滤。"""
    if user.role == "admin":
        return q
    if user.role == "reviewer" and user.line_id is not None:
        return q.filter(
            or_(
                DiagnosisRecord.created_by == user.id,
                DiagnosisRecord.line_id == user.line_id,
            )
        )
    # user 或 reviewer 但无 line_id → 只看自己
    return q.filter(DiagnosisRecord.created_by == user.id)


def can_access_diagnosis(user: User, record: DiagnosisRecord) -> bool:
    if user.role == "admin":
        return True
    if record.created_by == user.id:
        return True
    if (
        user.role == "reviewer"
        and user.line_id is not None
        and record.line_id == user.line_id
    ):
        return True
    return False


def can_review_diagnosis(user: User, record: DiagnosisRecord) -> bool:
    """写复核：仅 admin 与 reviewer（且必须在该诊断所在的线条）。"""
    if user.role == "admin":
        return True
    if (
        user.role == "reviewer"
        and user.line_id is not None
        and record.line_id == user.line_id
    ):
        return True
    return False


def can_resume_session(user: User, session: ChatSession) -> bool:
    """ChatSession 只允许创建者继续编辑。admin 也不能续别人的对话（避免误篡）。"""
    return session.created_by is not None and session.created_by == user.id


# ── Pydantic 模型 ──────────────────────────────────────────────

class ChatMessage(BaseModel):
    session_id: str | None = None
    message: str
    fields: dict | None = None

class SessionFieldsBody(BaseModel):
    fields: dict

class ConfirmSubmit(BaseModel):
    session_id: str
    fields: dict


class ReviewSubmit(BaseModel):
    """人工复核与异议提交（规格 §7）"""
    review_result: str                       # confirmed | partial | overridden
    risk_point_ids: list[str] | None = None  # 被推翻的 rule_id 列表
    manual_conclusion: str | None = None
    override_reason: str | None = None


# ── 对话接口 ───────────────────────────────────────────────────

@router.post("/chat")
async def chat(
    body: ChatMessage,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """对话式收集项目信息"""

    session_id = body.session_id or str(uuid.uuid4())
    session = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()

    if session and not can_resume_session(user, session):
        raise HTTPException(status_code=404, detail="会话不存在")

    if not session:
        session = ChatSession(
            session_id=session_id,
            messages_json="[]",
            extracted_fields_json="{}",
            status="collecting",
            created_by=user.id,
        )
        db.add(session)
        db.commit()
        db.refresh(session)

    messages: list = json.loads(session.messages_json)
    current_fields: dict = json.loads(session.extracted_fields_json)

    if body.fields is not None:
        current_fields.update(body.fields)

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

    # 对新提取的字段做即时预警
    realtime_warnings = []
    for k, v in new_fields.items():
        if v is not None:
            w = get_realtime_warnings(k, v)
            if w:
                realtime_warnings.append(w)

    return {
        "session_id": session_id,
        "reply": ai_result["reply"],
        "extracted_fields": current_fields,
        "fields_display": fields_display,
        "missing_fields": missing,
        "is_complete": is_complete,
        "status": session.status,
        "realtime_warnings": realtime_warnings,
        # AI 来源标注：本轮新提取的字段键列表，前端用于标黄
        "ai_extracted_keys": list(new_fields.keys()),
    }


@router.patch("/session/{session_id}/fields")
async def patch_session_fields(
    session_id: str,
    body: SessionFieldsBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """仅更新结构化字段（右侧手工修改），不触发对话。"""
    session = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
    if not session or not can_resume_session(user, session):
        raise HTTPException(status_code=404, detail="会话不存在")

    current_fields: dict = json.loads(session.extracted_fields_json)
    current_fields.update(body.fields)
    normalize_project_type_field(current_fields)

    missing = get_missing_fields(current_fields)
    is_complete = len(missing) == 0

    session.extracted_fields_json = json.dumps(current_fields, ensure_ascii=False)
    session.status = "confirmed" if is_complete else "collecting"
    db.commit()

    # 对手动修改的字段做即时预警
    realtime_warnings = []
    for k, v in body.fields.items():
        w = get_realtime_warnings(k, v)
        if w:
            realtime_warnings.append(w)

    return {
        "session_id": session_id,
        "extracted_fields": current_fields,
        "fields_display": build_fields_display(current_fields),
        "missing_fields": missing,
        "is_complete": is_complete,
        "status": session.status,
        "realtime_warnings": realtime_warnings,
    }


@router.post("/session/{session_id}/units")
async def segment_session_units(
    session_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """让 AI 把当前对话切分成核算单元草稿，存入会话并返回（#7，见 docs/adr/0002）。"""
    session = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
    if not session or not can_resume_session(user, session):
        raise HTTPException(status_code=404, detail="会话不存在")

    messages: list = json.loads(session.messages_json)
    units = await segment_accounting_units(messages)
    # 铁律不列收（#8）：AI 草稿可能给硬件单元漏标 listed，数据层强制归一
    enforce_hardware_no_listing(units)
    session.accounting_units_json = json.dumps(units, ensure_ascii=False)
    db.commit()
    return {"session_id": session_id, "accounting_units": units}


class UnitsSubmit(BaseModel):
    accounting_units: list


@router.patch("/session/{session_id}/units")
async def save_session_units(
    session_id: str,
    body: UnitsSubmit,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """保存用户确认/微调后的核算单元（AI 切分是草稿，人确认定稿）。"""
    session = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
    if not session or not can_resume_session(user, session):
        raise HTTPException(status_code=404, detail="会话不存在")

    units = enforce_hardware_no_listing(body.accounting_units)  # 铁律不列收（#8）数据层归一
    session.accounting_units_json = json.dumps(units, ensure_ascii=False)
    db.commit()
    return {"session_id": session_id, "accounting_units": units}


@router.get("/field-definitions")
async def field_definitions(user: User = Depends(get_current_user)):
    """供前端渲染下拉/多选。"""
    return FIELD_DEFINITIONS


@router.post("/confirm")
async def confirm_and_diagnose(
    body: ConfirmSubmit,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """用户确认字段后提交诊断"""

    session = db.query(ChatSession).filter(ChatSession.session_id == body.session_id).first()
    if not session or not can_resume_session(user, session):
        raise HTTPException(status_code=404, detail="会话不存在")

    fields = dict(body.fields)
    normalize_project_type_field(fields)
    migrate_legacy_service_fields(fields)
    strip_deprecated_input_fields(fields)
    session.extracted_fields_json = json.dumps(fields, ensure_ascii=False)

    fields_for_diagnosis = dict(fields)
    apply_derived_fields_for_diagnosis(fields_for_diagnosis)

    bpm_id = fields_for_diagnosis.get("bpm_id") or "未填写"
    if isinstance(bpm_id, str) and bpm_id.strip():
        bpm_id = bpm_id.strip().upper()
    else:
        bpm_id = "未填写"

    pt = fields_for_diagnosis.get("project_type")
    if isinstance(pt, list) and pt:
        pt_for_rules = pt
        project_type_db = ",".join(pt)
    elif isinstance(pt, str) and pt.strip():
        pt_for_rules = [pt.strip()]
        project_type_db = pt.strip()
    else:
        raise HTTPException(status_code=400, detail="project_type 为必填项，请先确认项目类型")

    try:
        accounting_units = json.loads(session.accounting_units_json or "[]")
    except Exception:
        accounting_units = []
    # 铁律不列收（#8）兜底：存量会话可能残留归一前的硬件单元，诊断与落库快照都用归一后数据
    enforce_hardware_no_listing(accounting_units)
    session.accounting_units_json = json.dumps(accounting_units, ensure_ascii=False)
    result = run_diagnosis(pt_for_rules, fields_for_diagnosis, accounting_units=accounting_units)

    chat_history = None
    if session:
        try:
            chat_history = json.loads(session.messages_json)
        except Exception:
            chat_history = None

    try:
        result = await enrich_diagnosis_with_ai(result, fields_for_diagnosis, chat_history)
    except Exception as e:
        result["ai_enriched"] = False
        result["ai_error"] = str(e)

    record = DiagnosisRecord(
        bpm_id=bpm_id,
        project_type=project_type_db,
        input_json=json.dumps(fields_for_diagnosis, ensure_ascii=False),
        chat_snapshot_json=session.messages_json,
        accounting_units_json=session.accounting_units_json,
        overall_risk=result["overall_risk"],
        result_json=json.dumps(result, ensure_ascii=False),
        rule_version=RULE_VERSION,
        created_by=user.id,
        line_id=user.line_id,  # 创建时快照
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
        "manual_check_rules": result.get("manual_check_rules", []),
        "audit_checklist": result["audit_checklist"],
        "rule_version": result["rule_version"],
        "created_at": record.created_at.strftime("%Y-%m-%d %H:%M") if record.created_at else "",
        # 与 /api/diagnose/{id} 保持 result 键一致（前端 confirm 后只用 diagnosis_id 跳 /report/:id
        # 让 ReportView 重新拉，故当前不依赖；补齐防未来其他客户端直接用 confirm 返回时再踩坑）
        "ai_enriched": result.get("ai_enriched", False),
        "segments": result.get("segments"),
        "is_mixed_project": result.get("is_mixed_project", False),
        "accounting_units": result.get("accounting_units", []),
        "suppressed_rules": result.get("suppressed_rules", []),
        "hard_to_service": result.get("hard_to_service", []),
        "unit_warning": result.get("unit_warning"),
        "control_roles_check": result.get("control_roles_check"),
        "listing_mode": result.get("listing_mode"),
    }


# ── 人工复核与异议接口（规格 §7）─────────────────────────────

@router.post("/diagnose/{diagnosis_id}/review")
async def submit_review(
    diagnosis_id: int,
    body: ReviewSubmit,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """审核人员提交人工复核结论（一致 / 部分采纳 / 推翻）。
    仅 admin 与 reviewer（且诊断属于该 reviewer 的线条）可写。"""
    record = db.query(DiagnosisRecord).filter(DiagnosisRecord.id == diagnosis_id).first()
    if not record or not can_access_diagnosis(user, record):
        raise HTTPException(status_code=404, detail="诊断记录不存在")
    if not can_review_diagnosis(user, record):
        raise HTTPException(status_code=403, detail="仅主管或管理员可提交复核")

    if body.review_result not in ("confirmed", "partial", "overridden"):
        raise HTTPException(status_code=400, detail="review_result 须为 confirmed / partial / overridden")

    dissent = DissentRecord(
        diagnosis_id=diagnosis_id,
        bpm_id=record.bpm_id,
        reviewer_id=user.display_name,    # 老字符串字段，写入展示名兼容旧报告渲染
        reviewer_user_id=user.id,         # 新外键字段，是 commit 3 起的权威来源
        review_result=body.review_result,
        risk_point_ids=json.dumps(body.risk_point_ids or [], ensure_ascii=False),
        manual_conclusion=body.manual_conclusion,
        override_reason=body.override_reason,
        rule_version=record.rule_version,
        pmo_status="pending",
    )
    db.add(dissent)
    db.commit()
    db.refresh(dissent)

    return {
        "dissent_id": dissent.id,
        "diagnosis_id": diagnosis_id,
        "review_result": dissent.review_result,
        "created_at": dissent.created_at.strftime("%Y-%m-%d %H:%M") if dissent.created_at else "",
    }


@router.get("/diagnose/{diagnosis_id}/reviews")
async def list_reviews(
    diagnosis_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """查询某条诊断记录的所有复核记录"""
    record = db.query(DiagnosisRecord).filter(DiagnosisRecord.id == diagnosis_id).first()
    if not record or not can_access_diagnosis(user, record):
        raise HTTPException(status_code=404, detail="诊断记录不存在")

    records = (
        db.query(DissentRecord)
        .filter(DissentRecord.diagnosis_id == diagnosis_id)
        .order_by(DissentRecord.created_at.desc())
        .all()
    )
    items = []
    for r in records:
        items.append({
            "dissent_id": r.id,
            "reviewer_id": r.reviewer_id,
            "review_result": r.review_result,
            "risk_point_ids": json.loads(r.risk_point_ids or "[]"),
            "manual_conclusion": r.manual_conclusion,
            "override_reason": r.override_reason,
            "pmo_status": r.pmo_status,
            "created_at": r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else "",
        })
    return {"diagnosis_id": diagnosis_id, "count": len(items), "items": items}


# ── 列表接口 ───────────────────────────────────────────────────

def _serialize_diagnosis_summary(rec: DiagnosisRecord, creator: User | None) -> dict:
    try:
        result = json.loads(rec.result_json)
    except Exception:
        result = {}
    if creator:
        creator_display = creator.display_name
    elif rec.created_by is None:
        creator_display = "[存量数据]"
    else:
        creator_display = f"[已删除#{rec.created_by}]"
    return {
        "diagnosis_id": rec.id,
        "bpm_id": rec.bpm_id,
        "project_type": rec.project_type,
        "overall_risk": rec.overall_risk,
        "overall_risk_label": result.get("overall_risk_label", ""),
        "rule_version": rec.rule_version,
        "created_at": rec.created_at.strftime("%Y-%m-%d %H:%M") if rec.created_at else "",
        "created_by": rec.created_by,
        "creator_display_name": creator_display,
        "line_id": rec.line_id,
    }


@router.get("/diagnoses")
async def list_diagnoses(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """合并列表：按角色自动过滤（user 看自己，reviewer 看本线条，admin 看全部）。"""
    base = filter_diagnoses_for_user(db.query(DiagnosisRecord), user)
    total = base.count()
    records = (
        base.order_by(DiagnosisRecord.created_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )
    creator_ids = {r.created_by for r in records if r.created_by}
    creators = (
        {u.id: u for u in db.query(User).filter(User.id.in_(creator_ids)).all()}
        if creator_ids else {}
    )
    items = [_serialize_diagnosis_summary(r, creators.get(r.created_by)) for r in records]
    return {"total": total, "limit": limit, "offset": offset, "items": items}


@router.get("/diagnose/by-bpm")
async def list_diagnoses_by_bpm(
    bpm_id: str = Query(..., description="BPM 商机编码"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    key = (bpm_id or "").strip().upper()
    if not key:
        raise HTTPException(status_code=400, detail="请提供 BPM 商机编码")

    base = filter_diagnoses_for_user(db.query(DiagnosisRecord), user)
    records = (
        base.filter(DiagnosisRecord.bpm_id == key)
        .order_by(DiagnosisRecord.created_at.desc())
        .all()
    )
    creator_ids = {r.created_by for r in records if r.created_by}
    creators = (
        {u.id: u for u in db.query(User).filter(User.id.in_(creator_ids)).all()}
        if creator_ids else {}
    )
    items = [_serialize_diagnosis_summary(r, creators.get(r.created_by)) for r in records]
    return {"bpm_id": key, "count": len(items), "items": items}


@router.get("/diagnose/{diagnosis_id}/traceability")
async def get_diagnosis_traceability(
    diagnosis_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """填报溯源：返回提交时的确认字段与对话快照。"""
    record = db.query(DiagnosisRecord).filter(DiagnosisRecord.id == diagnosis_id).first()
    if not record or not can_access_diagnosis(user, record):
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
async def get_diagnosis(
    diagnosis_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """按ID读取历史诊断报告"""
    record = db.query(DiagnosisRecord).filter(DiagnosisRecord.id == diagnosis_id).first()
    if not record or not can_access_diagnosis(user, record):
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
        "segments": result.get("segments"),
        "manual_check_rules": result.get("manual_check_rules", []),
        "ai_enriched": result.get("ai_enriched", False),
        "is_mixed_project": result.get("is_mixed_project", False),
        "accounting_units": result.get("accounting_units", []),
        "suppressed_rules": result.get("suppressed_rules", []),
        "hard_to_service": result.get("hard_to_service", []),
        # 以下三键之前漏传给 SPA，导致 /report/:id 静默丢失「核算单元未切分黄条」(ADR 0002)、
        # 「控制权角色自查」板块 (ADR 0003) 与「列收模式判定」板块 (ADR 0004)——
        # HTML/PDF 直链报告不受影响（generate_report_html 直接读 result）
        "unit_warning": result.get("unit_warning"),
        "control_roles_check": result.get("control_roles_check"),
        "listing_mode": result.get("listing_mode"),
    }


@router.get("/report/{diagnosis_id}/html", response_class=HTMLResponse)
async def get_report_html(
    diagnosis_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取HTML格式报告"""
    record = db.query(DiagnosisRecord).filter(DiagnosisRecord.id == diagnosis_id).first()
    if not record or not can_access_diagnosis(user, record):
        raise HTTPException(status_code=404, detail="报告不存在")
    result = json.loads(record.result_json)
    created_at = record.created_at.strftime("%Y-%m-%d %H:%M") if record.created_at else ""
    html = generate_report_html(record.id, record.bpm_id, result, created_at)
    return HTMLResponse(content=html)


@router.get("/report/{diagnosis_id}/pdf")
async def get_report_pdf(
    diagnosis_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取PDF格式报告"""
    record = db.query(DiagnosisRecord).filter(DiagnosisRecord.id == diagnosis_id).first()
    if not record or not can_access_diagnosis(user, record):
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
        return Response(
            content=html.encode("utf-8"),
            media_type="text/html",
            headers={"Content-Disposition": f"attachment; filename=report_{diagnosis_id}.html"},
        )


@router.get("/health")
async def health():
    return {"status": "ok", "rule_version": RULE_VERSION}
