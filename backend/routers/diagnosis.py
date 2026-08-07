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
    MATERIAL_VERSION,
    get_realtime_warnings,
    assess_six_daowei,
)
from accounting_structure import (
    derive_final_units,
    invalidate_full_unit_checks,
    is_v2_structure,
    normalize_structure,
    prepare_structure_update,
    structure_from_units,
    validate_structure,
)
from ai_chat import (
    analyze_guided_intake,
    augment_project_types_from_units,
    chat_with_ai,
    help_with_field,
    segment_accounting_units,
    get_missing_fields,
    FIELD_DEFINITIONS,
    normalize_project_type_field,
    migrate_legacy_service_fields,
    merge_guided_source_units,
    strip_deprecated_input_fields,
    apply_derived_fields_for_diagnosis,
    build_fields_display,
)
from guided_intake import (
    MAX_FOLLOW_UP_ROUNDS,
    SECTION_DEFINITIONS,
    empty_coverage,
    empty_guided_input,
    evaluate_readiness,
    guided_input_as_message,
    has_minimum_starting_content,
    merge_coverage,
    normalize_coverage,
    normalize_guided_input,
)
from report_generator import generate_report_html, generate_pdf
from ai_report import enrich_diagnosis_with_ai

router = APIRouter(prefix="/api")

_SHARED_CHECK_FIELDS = {
    "control_roles", "service_delivery_mode", "contract_matches_bpm", "related_party",
    "customer_type", "scheme_reviewed", "procurement_method", "acceptance_content_same",
    "project_location", "has_telecom_capability", "capability_ratio", "logistics_control",
    "payment_terms", "ownership_transfer", "collective_procurement_ratio",
}

_FIELD_REVIEW_SOURCES = {"manual", "ai_bulk", "ai_field_help"}


def _empty_field_review() -> dict:
    return {"schema_version": 1, "fields": {}}


def _load_field_review(session: ChatSession) -> dict:
    try:
        raw = json.loads(session.field_review_json or "{}")
    except (TypeError, ValueError):
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    fields = raw.get("fields") if isinstance(raw.get("fields"), dict) else {}
    normalized = _empty_field_review()
    for key, entry in fields.items():
        if not isinstance(entry, dict) or key not in FIELD_DEFINITIONS:
            continue
        source = entry.get("source")
        status = entry.get("status")
        if source in _FIELD_REVIEW_SOURCES and status in {"pending", "confirmed"}:
            normalized["fields"][key] = {"source": source, "status": status}
    return normalized


def _save_field_review(session: ChatSession, review: dict) -> None:
    session.field_review_json = json.dumps(review, ensure_ascii=False)


def _set_field_review(review: dict, key: str, source: str, status: str) -> None:
    if key not in FIELD_DEFINITIONS or source not in _FIELD_REVIEW_SOURCES:
        return
    review.setdefault("fields", {})[key] = {"source": source, "status": status}


def _pending_ai_fields(review: dict) -> list[str]:
    return [
        key for key, entry in (review.get("fields") or {}).items()
        if entry.get("source") in {"ai_bulk", "ai_field_help"} and entry.get("status") == "pending"
    ]


def _is_blank_field_value(value) -> bool:
    return value is None or value == "" or value == []


def _field_review_payload(review: dict) -> dict:
    return {
        "field_review": review,
        "pending_ai_fields": _pending_ai_fields(review),
    }


def _assistant_summary(applied: list[str], conflicts: list[str], missing: list[str]) -> str:
    labels = [FIELD_DEFINITIONS[key]["label"] for key in applied if key in FIELD_DEFINITIONS]
    conflict_labels = [FIELD_DEFINITIONS[key]["label"] for key in conflicts if key in FIELD_DEFINITIONS]
    chunks = []
    if labels:
        chunks.append(f"已预填 {len(labels)} 项：{'、'.join(labels)}，请在表单中核对确认")
    if conflict_labels:
        chunks.append(f"{len(conflict_labels)} 项与已确认值不一致，未自动覆盖：{'、'.join(conflict_labels)}")
    if missing:
        chunks.append(f"仍缺 {len(missing)} 项必填信息")
    return "；".join(chunks) + "。以上仅为 AI 助填，不是规则诊断结论。" if chunks else "未识别到可安全预填的信息；请按表单中的项目事实填写。"


def _apply_ai_extracted_fields(current_fields: dict, review: dict, new_fields) -> tuple[list[str], list[str]]:
    """写入 AI 可安全预填的事实；已确认值永不覆盖。"""
    applied_fields: list[str] = []
    conflicting_fields: list[str] = []
    for key, value in (new_fields if isinstance(new_fields, dict) else {}).items():
        definition = FIELD_DEFINITIONS.get(key)
        if (
            not definition
            or key in {"control_roles", "major_integration", "service_capability_level"}
            or definition.get("manual_confirmation")
            or definition.get("deprecated")
            or value is None
        ):
            continue
        if key == "project_type" and isinstance(value, str):
            value = [value]
        existing = current_fields.get(key)
        existing_review = (review.get("fields") or {}).get(key, {})
        is_pending_ai = (
            existing_review.get("source") in {"ai_bulk", "ai_field_help"}
            and existing_review.get("status") == "pending"
        )
        if _is_blank_field_value(existing) or is_pending_ai:
            current_fields[key] = value
            _set_field_review(review, key, "ai_bulk", "pending")
            applied_fields.append(key)
        elif existing != value:
            conflicting_fields.append(key)
    return applied_fields, conflicting_fields


def _load_json_object(raw: str | None, fallback: dict) -> dict:
    try:
        value = json.loads(raw or "{}")
    except (TypeError, ValueError):
        value = {}
    return value if isinstance(value, dict) else fallback


def _load_guided_input(session: ChatSession) -> dict:
    return normalize_guided_input(_load_json_object(session.guided_input_json, empty_guided_input()))


def _load_coverage(session: ChatSession) -> dict:
    value = _load_json_object(session.coverage_json, empty_coverage())
    return normalize_coverage(value, round_no=value.get("round", 0))


def _guided_payload(session: ChatSession) -> dict:
    return {
        "guided_input": _load_guided_input(session),
        "guided_section_definitions": SECTION_DEFINITIONS,
        "coverage": _load_coverage(session),
        "max_follow_up_rounds": MAX_FOLLOW_UP_ROUNDS,
    }


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


def _six_daowei_for_session(session: ChatSession, fields: dict) -> dict:
    """给填报面板返回与诊断引擎同源的六到位建议。"""
    try:
        units = json.loads(session.accounting_units_json or "[]")
    except (TypeError, ValueError):
        units = []
    if is_v2_structure(units):
        return None
    has_hardware = fields.get("hardware_construction") is True or any(
        isinstance(u, dict) and u.get("declared_type") in {"设备", "施工"}
        for u in units
    )
    wants_full = fields.get("service_delivery_mode") in {"all_telecom", "mixed"} or (
        fields.get("has_telecom_capability") in {"yes", "partial"}
        and fields.get("capability_ratio") in {"medium", "high"}
    )
    return assess_six_daowei(fields, has_hardware=has_hardware, wants_full=wants_full)


def _load_accounting_payload(session: ChatSession):
    try:
        return json.loads(session.accounting_units_json or "[]")
    except (TypeError, ValueError):
        return []


def _invalidate_structure_if_shared_facts_changed(session: ChatSession, before: dict, after: dict) -> None:
    if not any(before.get(key) != after.get(key) for key in _SHARED_CHECK_FIELDS):
        return
    payload = _load_accounting_payload(session)
    if is_v2_structure(payload):
        session.accounting_units_json = json.dumps(
            invalidate_full_unit_checks(payload), ensure_ascii=False,
        )


# ── Pydantic 模型 ──────────────────────────────────────────────

class ChatMessage(BaseModel):
    session_id: str | None = None
    message: str
    fields: dict | None = None

class SessionFieldsBody(BaseModel):
    fields: dict = {}
    sources: dict[str, str] | None = None
    confirm_fields: list[str] | None = None


class FieldHelpBody(BaseModel):
    field_key: str
    question: str


class GuidedIntakeBody(BaseModel):
    sections: dict


class GuidedReplyBody(BaseModel):
    message: str

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

@router.post("/session")
async def create_session(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """创建空白填报会话，使用户可以先填写表单而不是先发起对话。"""
    session = ChatSession(
        session_id=str(uuid.uuid4()),
        messages_json="[]",
        extracted_fields_json="{}",
        field_review_json=json.dumps(_empty_field_review(), ensure_ascii=False),
        guided_input_json=json.dumps(empty_guided_input(), ensure_ascii=False),
        coverage_json=json.dumps(empty_coverage(), ensure_ascii=False),
        status="collecting",
        created_by=user.id,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    fields: dict = {}
    review = _load_field_review(session)
    return {
        "session_id": session.session_id,
        "extracted_fields": fields,
        "fields_display": [],
        "missing_fields": get_missing_fields(fields),
        "is_complete": False,
        "status": session.status,
        "realtime_warnings": [],
        "accounting_structure": None,
        **_field_review_payload(review),
        **_guided_payload(session),
    }

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
            field_review_json=json.dumps(_empty_field_review(), ensure_ascii=False),
            guided_input_json=json.dumps(empty_guided_input(), ensure_ascii=False),
            coverage_json=json.dumps(empty_coverage(), ensure_ascii=False),
            status="collecting",
            created_by=user.id,
        )
        db.add(session)
        db.commit()
        db.refresh(session)

    messages: list = json.loads(session.messages_json)
    current_fields: dict = json.loads(session.extracted_fields_json)
    review = _load_field_review(session)
    fields_before = dict(current_fields)

    if body.fields is not None:
        current_fields.update(body.fields)
        for key in body.fields:
            _set_field_review(review, key, "manual", "confirmed")

    messages.append({"role": "user", "content": body.message})

    pt_ctx = current_fields.get("project_type")
    if isinstance(pt_ctx, list):
        project_type_for_ai = json.dumps(pt_ctx, ensure_ascii=False) if pt_ctx else None
    else:
        project_type_for_ai = pt_ctx

    ai_result = await chat_with_ai(messages, current_fields, project_type_for_ai)

    applied_fields, conflicting_fields = _apply_ai_extracted_fields(
        current_fields, review, ai_result.get("extracted", {}),
    )
    normalize_project_type_field(current_fields)
    _invalidate_structure_if_shared_facts_changed(session, fields_before, current_fields)

    missing = get_missing_fields(current_fields)
    pending_ai_fields = _pending_ai_fields(review)
    is_complete = len(missing) == 0 and not pending_ai_fields

    reply = ai_result.get("reply") or ""
    if applied_fields or conflicting_fields:
        reply = _assistant_summary(applied_fields, conflicting_fields, missing)

    messages.append({"role": "assistant", "content": reply})

    session.messages_json = json.dumps(messages, ensure_ascii=False)
    session.extracted_fields_json = json.dumps(current_fields, ensure_ascii=False)
    _save_field_review(session, review)
    session.status = "confirmed" if is_complete else "collecting"
    db.commit()

    fields_display = build_fields_display(current_fields)

    return {
        "session_id": session_id,
        "reply": reply,
        "extracted_fields": current_fields,
        "fields_display": fields_display,
        "missing_fields": missing,
        "is_complete": is_complete,
        "status": session.status,
        # 填表阶段只做事实完整性校验；风险结论留给 /api/confirm 的规则引擎。
        "realtime_warnings": [],
        "six_daowei_check": _six_daowei_for_session(session, current_fields),
        "accounting_structure": (
            _load_accounting_payload(session) if is_v2_structure(_load_accounting_payload(session)) else None
        ),
        "ai_extracted_keys": applied_fields,
        "ai_conflicts": conflicting_fields,
        **_field_review_payload(review),
        **_guided_payload(session),
    }


def _guided_reply_text(coverage: dict, ai_error: str | None = None) -> str:
    if ai_error:
        return ai_error
    readiness = coverage.get("readiness")
    if readiness == "ready":
        return "六块项目说明已经形成完整项目骨架，可以进入信息确认。以上仅为事实整理，不是规则诊断结论。"
    if readiness == "blocked":
        topics = coverage.get("blocking_topics") or []
        suffix = f" 当前仍缺：{'；'.join(topics)}。" if topics else ""
        return f"三轮集中追问已经结束，当前资料仍不足，草稿已保存。{suffix}请取得相关材料后修改六块项目说明并重新评估。"
    questions = coverage.get("follow_up_questions") or []
    if questions:
        listed = "\n".join(f"{index}. {question}" for index, question in enumerate(questions, 1))
        return f"我已整理现有项目事实。请集中补充以下内容：\n{listed}\n可以一次回答整组问题，不清楚的项目请明确写“暂不清楚”。"
    topics = coverage.get("blocking_topics") or []
    if topics:
        return f"现有说明还不足以形成完整项目骨架，请补充：{'；'.join(topics)}。"
    return "已整理现有项目事实，请继续补充交付内容、职责边界和最终验收形态。"


async def _assess_guided_session(session: ChatSession, round_no: int, db: Session) -> dict:
    messages = json.loads(session.messages_json or "[]")
    current_fields = json.loads(session.extracted_fields_json or "{}")
    review = _load_field_review(session)
    fields_before = dict(current_fields)
    guided_input = _load_guided_input(session)
    previous_coverage = _load_coverage(session)
    previous_structure = _load_accounting_payload(session)
    previous_units = (
        previous_structure.get("source_units", []) if is_v2_structure(previous_structure) else []
    )

    analysis = await analyze_guided_intake(
        guided_input,
        messages,
        current_fields,
        known_coverage=previous_coverage,
        known_source_units=previous_units,
    )
    applied_fields, conflicting_fields = _apply_ai_extracted_fields(
        current_fields, review, analysis.get("extracted", {}),
    )
    normalize_project_type_field(current_fields)
    _invalidate_structure_if_shared_facts_changed(session, fields_before, current_fields)

    units = analysis.get("source_units") if isinstance(analysis.get("source_units"), list) else []
    if units:
        # 模型每轮都可能重新生成草稿；少返回的旧单元不能静默丢失。
        merged_units = merge_guided_source_units(previous_units, units)
        accounting_structure = structure_from_units(merged_units)
        if accounting_structure["source_units"]:
            accounting_structure["source_units_review_status"] = "pending"
        session.accounting_units_json = json.dumps(accounting_structure, ensure_ascii=False)
    elif is_v2_structure(previous_structure):
        accounting_structure = normalize_structure(previous_structure)
    else:
        accounting_structure = structure_from_units([])

    if augment_project_types_from_units(
        current_fields, accounting_structure.get("source_units", []),
    ):
        _set_field_review(review, "project_type", "ai_bulk", "pending")

    if analysis.get("error"):
        coverage = previous_coverage
        coverage["round"] = round_no
        for key, item in guided_input.get("sections", {}).items():
            if key not in coverage.get("sections", {}):
                continue
            if item.get("explicit_unknown"):
                coverage["sections"][key]["status"] = "unknown_confirmed"
                coverage["sections"][key]["summary"] = "用户已明确说明当前暂不清楚。"
            elif item.get("text"):
                coverage["sections"][key]["status"] = "partial"
                coverage["sections"][key]["summary"] = "原文已保存，待 AI 服务恢复后整理。"
        coverage["blocking_topics"] = list(dict.fromkeys([
            *(coverage.get("blocking_topics") or []),
            "AI 暂时无法完成覆盖评估",
        ]))
    else:
        coverage = merge_coverage(
            previous_coverage,
            analysis,
            round_no=round_no,
            latest_user_text=str((messages[-1] if messages else {}).get("content") or ""),
        )

    missing = get_missing_fields(current_fields)
    coverage = evaluate_readiness(
        coverage,
        simple_fact_gaps=missing,
        has_source_units=bool(accounting_structure.get("source_units")),
    )
    reply = _guided_reply_text(coverage, analysis.get("error"))
    messages.append({"role": "assistant", "content": reply})

    session.messages_json = json.dumps(messages, ensure_ascii=False)
    session.extracted_fields_json = json.dumps(current_fields, ensure_ascii=False)
    session.coverage_json = json.dumps(coverage, ensure_ascii=False)
    _save_field_review(session, review)
    session.status = "collecting"
    db.commit()

    return {
        "session_id": session.session_id,
        "reply": reply,
        "extracted_fields": current_fields,
        "fields_display": build_fields_display(current_fields),
        "missing_fields": missing,
        "is_complete": len(missing) == 0 and not _pending_ai_fields(review),
        "status": session.status,
        "realtime_warnings": [],
        "accounting_structure": accounting_structure,
        "ai_extracted_keys": applied_fields,
        "ai_conflicts": conflicting_fields,
        "ai_error": analysis.get("error"),
        "can_enter_confirmation": coverage.get("readiness") == "ready",
        "chat_messages": messages,
        **_field_review_payload(review),
        **_guided_payload(session),
    }


@router.post("/session/{session_id}/guided-intake")
async def submit_guided_intake(
    session_id: str,
    body: GuidedIntakeBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """保存六块项目说明并从第 0 轮重新评估覆盖度。"""
    session = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
    if not session or not can_resume_session(user, session):
        raise HTTPException(status_code=404, detail="会话不存在")

    guided_input = normalize_guided_input({"sections": body.sections})
    if not has_minimum_starting_content(guided_input):
        raise HTTPException(status_code=400, detail="请至少填写“项目基本情况”和“项目交付内容”后再提交")

    messages = json.loads(session.messages_json or "[]")
    messages.append({"role": "user", "content": guided_input_as_message(guided_input)})
    session.guided_input_json = json.dumps(guided_input, ensure_ascii=False)
    session.coverage_json = json.dumps(empty_coverage(), ensure_ascii=False)
    session.messages_json = json.dumps(messages, ensure_ascii=False)
    db.commit()
    return await _assess_guided_session(session, 0, db)


@router.post("/session/{session_id}/guided-reply")
async def reply_guided_intake(
    session_id: str,
    body: GuidedReplyBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """回答一轮集中追问；最多三轮，之后进入确认或资料不足终态。"""
    session = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
    if not session or not can_resume_session(user, session):
        raise HTTPException(status_code=404, detail="会话不存在")
    message = (body.message or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="请填写补充说明")

    coverage = _load_coverage(session)
    if coverage.get("readiness") == "ready":
        raise HTTPException(status_code=400, detail="项目说明已经可以进入信息确认")
    current_round = int(coverage.get("round") or 0)
    if current_round >= MAX_FOLLOW_UP_ROUNDS:
        raise HTTPException(status_code=400, detail="集中追问已结束，请修改六块项目说明后重新评估")

    messages = json.loads(session.messages_json or "[]")
    messages.append({"role": "user", "content": message})
    session.messages_json = json.dumps(messages, ensure_ascii=False)
    db.commit()
    return await _assess_guided_session(session, current_round + 1, db)


@router.post("/session/{session_id}/guided-supplement")
async def supplement_guided_intake(
    session_id: str,
    body: GuidedReplyBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """确认阶段主动补充项目事实；重新评估但不占用 AI 集中追问轮次。"""
    session = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
    if not session or not can_resume_session(user, session):
        raise HTTPException(status_code=404, detail="会话不存在")
    message = (body.message or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="请填写补充说明")
    coverage = _load_coverage(session)
    messages = json.loads(session.messages_json or "[]")
    messages.append({"role": "user", "content": f"【确认阶段主动补充】\n{message}"})
    session.messages_json = json.dumps(messages, ensure_ascii=False)
    db.commit()
    return await _assess_guided_session(session, int(coverage.get("round") or 0), db)


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
    review = _load_field_review(session)
    fields_before = dict(current_fields)
    current_fields.update(body.fields)
    for key in body.fields:
        source = ((body.sources or {}).get(key) or "manual").strip()
        if source not in _FIELD_REVIEW_SOURCES:
            raise HTTPException(status_code=400, detail="字段来源无效")
        _set_field_review(
            review,
            key,
            source,
            "pending" if source in {"ai_bulk", "ai_field_help"} else "confirmed",
        )
    for key in body.confirm_fields or []:
        entry = (review.get("fields") or {}).get(key)
        if entry and entry.get("source") in {"ai_bulk", "ai_field_help"}:
            entry["status"] = "confirmed"
    normalize_project_type_field(current_fields)
    _invalidate_structure_if_shared_facts_changed(session, fields_before, current_fields)

    missing = get_missing_fields(current_fields)
    is_complete = len(missing) == 0 and not _pending_ai_fields(review)

    session.extracted_fields_json = json.dumps(current_fields, ensure_ascii=False)
    _save_field_review(session, review)
    session.status = "confirmed" if is_complete else "collecting"
    db.commit()

    return {
        "session_id": session_id,
        "extracted_fields": current_fields,
        "fields_display": build_fields_display(current_fields),
        "missing_fields": missing,
        "is_complete": is_complete,
        "status": session.status,
        "realtime_warnings": [],
        "six_daowei_check": _six_daowei_for_session(session, current_fields),
        "accounting_structure": (
            _load_accounting_payload(session) if is_v2_structure(_load_accounting_payload(session)) else None
        ),
        **_field_review_payload(review),
        **_guided_payload(session),
    }


@router.post("/session/{session_id}/field-help")
async def get_field_help(
    session_id: str,
    body: FieldHelpBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """针对单个字段提供 AI 填写说明和建议；不运行规则、不直接改值。"""
    session = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
    if not session or not can_resume_session(user, session):
        raise HTTPException(status_code=404, detail="会话不存在")
    if body.field_key not in FIELD_DEFINITIONS:
        raise HTTPException(status_code=400, detail="字段不存在")
    fields = json.loads(session.extracted_fields_json or "{}")
    answer = await help_with_field(body.field_key, body.question, fields)
    return {"field_key": body.field_key, **answer}


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
    structure = structure_from_units(units)
    if structure["source_units"]:
        structure["source_units_review_status"] = "pending"
    session.accounting_units_json = json.dumps(structure, ensure_ascii=False)
    db.commit()
    return {
        "session_id": session_id,
        "accounting_structure": structure,
        "accounting_units": structure["source_units"],
        "final_units": derive_final_units(structure),
        "six_daowei_check": None,
    }


class UnitsSubmit(BaseModel):
    accounting_structure: dict | None = None
    accounting_units: list | None = None


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

    previous = _load_accounting_payload(session)
    incoming = body.accounting_structure
    if incoming is None:
        incoming = structure_from_units(body.accounting_units or [])
    structure = prepare_structure_update(previous, incoming)
    errors = validate_structure(structure, for_submit=False)
    if errors:
        raise HTTPException(status_code=400, detail="；".join(errors))
    session.accounting_units_json = json.dumps(structure, ensure_ascii=False)
    db.commit()
    return {
        "session_id": session_id,
        "accounting_structure": structure,
        "accounting_units": structure["source_units"],
        "final_units": derive_final_units(structure),
        "six_daowei_check": None,
    }


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

    stored_fields = json.loads(session.extracted_fields_json or "{}")
    review = _load_field_review(session)
    guided_input = _load_guided_input(session)
    if any(item.get("text") for item in guided_input.get("sections", {}).values()):
        coverage = _load_coverage(session)
        if coverage.get("readiness") != "ready":
            raise HTTPException(status_code=400, detail="六块项目说明尚未达到可确认状态，请先完成引导填报和集中追问")
    fields = dict(body.fields)
    # 与会话中已保存值不同的字段视为本次由用户手工修订；相同的 AI 待核对值不能借由重发
    # 整个 fields payload 绕过确认门禁。
    for key, value in fields.items():
        if stored_fields.get(key) != value:
            _set_field_review(review, key, "manual", "confirmed")
    normalize_project_type_field(fields)
    migrate_legacy_service_fields(fields)
    strip_deprecated_input_fields(fields)
    pending_ai_fields = _pending_ai_fields(review)
    if pending_ai_fields:
        labels = [FIELD_DEFINITIONS[key]["label"] for key in pending_ai_fields if key in FIELD_DEFINITIONS]
        raise HTTPException(status_code=400, detail=f"请先核对 AI 预填字段：{'、'.join(labels)}")
    session.extracted_fields_json = json.dumps(fields, ensure_ascii=False)
    _save_field_review(session, review)

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

    accounting_payload = _load_accounting_payload(session)
    accounting_structure = normalize_structure(accounting_payload)
    structure_errors = validate_structure(accounting_structure, for_submit=True)
    if structure_errors:
        raise HTTPException(status_code=400, detail="；".join(structure_errors))
    session.accounting_units_json = json.dumps(accounting_structure, ensure_ascii=False)
    result = run_diagnosis(pt_for_rules, fields_for_diagnosis, accounting_units=accounting_structure)

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
        field_review_json=session.field_review_json,
        guided_input_json=session.guided_input_json,
        coverage_json=session.coverage_json,
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
        "material_version": result.get("material_version", MATERIAL_VERSION),
        "created_at": record.created_at.strftime("%Y-%m-%d %H:%M") if record.created_at else "",
        # 与 /api/diagnose/{id} 保持 result 键一致（前端 confirm 后只用 diagnosis_id 跳 /report/:id
        # 让 ReportView 重新拉，故当前不依赖；补齐防未来其他客户端直接用 confirm 返回时再踩坑）
        "ai_enriched": result.get("ai_enriched", False),
        "segments": result.get("segments"),
        "is_mixed_project": result.get("is_mixed_project", False),
        "accounting_units": result.get("accounting_units", []),
        "accounting_structure": result.get("accounting_structure"),
        "suppressed_rules": result.get("suppressed_rules", []),
        "hard_to_service": result.get("hard_to_service", []),
        "unit_warning": result.get("unit_warning"),
        "control_roles_check": result.get("control_roles_check"),
        "six_daowei_check": result.get("six_daowei_check"),
        "six_daowei_checks": result.get("six_daowei_checks", []),
        "r08_checks": result.get("r08_checks", []),
        "listing_mode": result.get("listing_mode"),
        "advisory_only": result.get("advisory_only", False),
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
    try:
        field_review = json.loads(record.field_review_json or "{}")
    except Exception:
        field_review = {}
    try:
        accounting_snapshot = json.loads(record.accounting_units_json or "[]")
    except Exception:
        accounting_snapshot = []
    try:
        guided_input = normalize_guided_input(json.loads(record.guided_input_json or "{}"))
    except Exception:
        guided_input = empty_guided_input()
    try:
        coverage = normalize_coverage(json.loads(record.coverage_json or "{}"))
    except Exception:
        coverage = empty_coverage()

    return {
        "diagnosis_id": record.id,
        "bpm_id": record.bpm_id,
        "project_type": record.project_type,
        "rule_version": record.rule_version,
        "created_at": record.created_at.strftime("%Y-%m-%d %H:%M") if record.created_at else "",
        "confirmed_fields": confirmed_fields,
        "field_review": field_review,
        "guided_input": guided_input,
        "guided_section_definitions": SECTION_DEFINITIONS,
        "coverage": coverage,
        "fields_display": fields_display,
        "chat_messages": chat_messages,
        "has_chat_snapshot": bool(chat_messages),
        "accounting_structure": accounting_snapshot if is_v2_structure(accounting_snapshot) else None,
        "accounting_units": accounting_snapshot if isinstance(accounting_snapshot, list) else [],
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
        "material_version": result.get("material_version", "历史目录"),
        "created_at": record.created_at.strftime("%Y-%m-%d %H:%M") if record.created_at else "",
        "segments": result.get("segments"),
        "manual_check_rules": result.get("manual_check_rules", []),
        "ai_enriched": result.get("ai_enriched", False),
        "is_mixed_project": result.get("is_mixed_project", False),
        "accounting_units": result.get("accounting_units", []),
        "accounting_structure": result.get("accounting_structure"),
        "suppressed_rules": result.get("suppressed_rules", []),
        "hard_to_service": result.get("hard_to_service", []),
        # 以下四键之前漏传给 SPA 会导致 /report/:id 静默丢失「核算单元未切分黄条」(ADR 0002)、
        # 「六到位自查」板块 (ADR 0003) 与「列收模式判定」板块 (ADR 0004)——
        # HTML/PDF 直链报告不受影响（generate_report_html 直接读 result）
        "unit_warning": result.get("unit_warning"),
        "control_roles_check": result.get("control_roles_check"),
        "six_daowei_check": result.get("six_daowei_check"),
        "six_daowei_checks": result.get("six_daowei_checks", []),
        "r08_checks": result.get("r08_checks", []),
        "listing_mode": result.get("listing_mode"),
        "advisory_only": result.get("advisory_only", False),
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
    return {"status": "ok", "rule_version": RULE_VERSION, "material_version": MATERIAL_VERSION}
