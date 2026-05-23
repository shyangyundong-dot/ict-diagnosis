"""管理员后台接口：线条与账号 CRUD、重置密码。"""

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from audit import write_audit_log
from auth import get_current_user, hash_password, require_admin
from database import get_db
from models.diagnosis import AdminAuditLog, ChatSession, DiagnosisRecord, DissentRecord, Line, User

router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin)])


# ── Pydantic ──────────────────────────────────────────────────

class LineCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class LineUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    is_active: bool | None = None


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    display_name: str = Field(min_length=1, max_length=100)
    email: str | None = None
    role: str  # admin | reviewer | user
    line_id: int | None = None
    password: str = Field(min_length=8)


class UserUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    email: str | None = None
    role: str | None = None
    line_id: int | None = None
    is_active: bool | None = None


class PasswordReset(BaseModel):
    new_password: str = Field(min_length=8)


class LegacyClaim(BaseModel):
    diagnosis_ids: list[int] = Field(min_length=1)
    target_user_id: int


# ── 序列化 ────────────────────────────────────────────────────

def _serialize_line(db: Session, line: Line) -> dict:
    reviewer = (
        db.query(User)
        .filter(User.line_id == line.id, User.role == "reviewer", User.is_active == True)  # noqa: E712
        .first()
    )
    user_count = db.query(User).filter(User.line_id == line.id, User.is_active == True).count()  # noqa: E712
    return {
        "id": line.id,
        "name": line.name,
        "is_active": line.is_active,
        "created_at": line.created_at.strftime("%Y-%m-%d %H:%M") if line.created_at else "",
        "reviewer": {
            "id": reviewer.id,
            "username": reviewer.username,
            "display_name": reviewer.display_name,
        } if reviewer else None,
        "user_count": user_count,
    }


def _serialize_user(user: User, line_name: str | None) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "email": user.email,
        "role": user.role,
        "line_id": user.line_id,
        "line_name": line_name,
        "is_active": user.is_active,
        "must_change_password": user.must_change_password,
        "last_login_at": user.last_login_at.strftime("%Y-%m-%d %H:%M") if user.last_login_at else None,
        "last_failed_login_at": user.last_failed_login_at.strftime("%Y-%m-%d %H:%M") if user.last_failed_login_at else None,
        "failed_login_count": user.failed_login_count,
        "created_at": user.created_at.strftime("%Y-%m-%d %H:%M") if user.created_at else "",
    }


def _validate_role_line(role: str, line_id: int | None) -> None:
    if role not in ("admin", "reviewer", "user"):
        raise HTTPException(status_code=400, detail="role 必须是 admin / reviewer / user")
    if role == "admin" and line_id is not None:
        raise HTTPException(status_code=400, detail="admin 不挂线条")
    if role in ("reviewer", "user") and line_id is None:
        raise HTTPException(status_code=400, detail="reviewer / user 必须挂在某个线条上")


# ── 线条 ─────────────────────────────────────────────────────

@router.get("/lines")
def list_lines(
    include_inactive: bool = Query(default=True),
    db: Session = Depends(get_db),
):
    q = db.query(Line)
    if not include_inactive:
        q = q.filter(Line.is_active == True)  # noqa: E712
    lines = q.order_by(Line.created_at.asc()).all()
    return {"items": [_serialize_line(db, l) for l in lines]}


@router.post("/lines")
def create_line(
    body: LineCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_user),
):
    name = body.name.strip()
    if db.query(Line).filter(Line.name == name).first():
        raise HTTPException(status_code=400, detail="线条名已存在")
    line = Line(name=name, is_active=True)
    db.add(line)
    db.commit()
    db.refresh(line)
    write_audit_log(db, admin.id, "create_line", "line", line.id, {"name": line.name})
    return _serialize_line(db, line)


@router.patch("/lines/{line_id}")
def update_line(
    line_id: int,
    body: LineUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_user),
):
    line = db.query(Line).filter(Line.id == line_id).first()
    if not line:
        raise HTTPException(status_code=404, detail="线条不存在")

    changes: dict = {}
    if body.name is not None:
        new_name = body.name.strip()
        if new_name != line.name:
            if db.query(Line).filter(Line.name == new_name, Line.id != line.id).first():
                raise HTTPException(status_code=400, detail="线条名已存在")
            changes["name"] = {"from": line.name, "to": new_name}
            line.name = new_name
    if body.is_active is not None and body.is_active != line.is_active:
        changes["is_active"] = {"from": line.is_active, "to": body.is_active}
        line.is_active = body.is_active

    if changes:
        db.commit()
        write_audit_log(db, admin.id, "update_line", "line", line.id, changes)

    return _serialize_line(db, line)


# ── 用户 ─────────────────────────────────────────────────────

@router.get("/users")
def list_users(
    include_inactive: bool = Query(default=True),
    db: Session = Depends(get_db),
):
    q = db.query(User)
    if not include_inactive:
        q = q.filter(User.is_active == True)  # noqa: E712
    users = q.order_by(User.created_at.desc()).all()
    line_map = {l.id: l.name for l in db.query(Line).all()}
    return {"items": [_serialize_user(u, line_map.get(u.line_id)) for u in users]}


@router.get("/users/{user_id}")
def get_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="账号不存在")
    line_name = None
    if user.line_id:
        line = db.query(Line).filter(Line.id == user.line_id).first()
        line_name = line.name if line else None
    return _serialize_user(user, line_name)


def _check_reviewer_uniqueness(db: Session, line_id: int, exclude_user_id: int | None = None) -> None:
    q = db.query(User).filter(
        User.line_id == line_id,
        User.role == "reviewer",
        User.is_active == True,  # noqa: E712
    )
    if exclude_user_id is not None:
        q = q.filter(User.id != exclude_user_id)
    existing = q.first()
    if existing:
        line = db.query(Line).filter(Line.id == line_id).first()
        raise HTTPException(
            status_code=400,
            detail=f"线条「{line.name if line else line_id}」已有主管「{existing.display_name}」",
        )


@router.post("/users")
def create_user(
    body: UserCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_user),
):
    username = body.username.strip()
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=400, detail="用户名已存在")

    _validate_role_line(body.role, body.line_id)

    if body.line_id is not None:
        if not db.query(Line).filter(Line.id == body.line_id).first():
            raise HTTPException(status_code=400, detail="指定的线条不存在")
        if body.role == "reviewer":
            _check_reviewer_uniqueness(db, body.line_id)

    user = User(
        username=username,
        password_hash=hash_password(body.password),
        display_name=body.display_name.strip(),
        email=(body.email.strip() if body.email else None) or None,
        role=body.role,
        line_id=body.line_id,
        is_active=True,
        must_change_password=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    write_audit_log(db, admin.id, "create_user", "user", user.id, {
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role,
        "line_id": user.line_id,
    })

    line_name = None
    if user.line_id:
        line = db.query(Line).filter(Line.id == user.line_id).first()
        line_name = line.name if line else None
    return _serialize_user(user, line_name)


@router.patch("/users/{user_id}")
def update_user(
    user_id: int,
    body: UserUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_user),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="账号不存在")

    # 自杀式操作护栏
    if user.id == admin.id:
        if body.role is not None and body.role != user.role:
            raise HTTPException(status_code=400, detail="不能修改自己的角色")
        if body.is_active is False:
            raise HTTPException(status_code=400, detail="不能禁用自己的账号")

    # 校验最终态：先合成最终的 role / line_id
    final_role = body.role if body.role is not None else user.role
    # admin 强制清空 line_id
    if final_role == "admin":
        final_line_id = None
    else:
        final_line_id = body.line_id if body.line_id is not None else user.line_id
    _validate_role_line(final_role, final_line_id)

    if final_line_id is not None and final_line_id != user.line_id:
        if not db.query(Line).filter(Line.id == final_line_id).first():
            raise HTTPException(status_code=400, detail="指定的线条不存在")

    if final_role == "reviewer" and final_line_id is not None:
        _check_reviewer_uniqueness(db, final_line_id, exclude_user_id=user.id)

    changes: dict = {}
    if body.display_name is not None and body.display_name != user.display_name:
        changes["display_name"] = {"from": user.display_name, "to": body.display_name}
        user.display_name = body.display_name
    if body.email is not None:
        new_email = body.email.strip() or None
        if new_email != user.email:
            changes["email"] = {"from": user.email, "to": new_email}
            user.email = new_email
    if final_role != user.role:
        changes["role"] = {"from": user.role, "to": final_role}
        user.role = final_role
    if final_line_id != user.line_id:
        changes["line_id"] = {"from": user.line_id, "to": final_line_id}
        user.line_id = final_line_id
    if body.is_active is not None and body.is_active != user.is_active:
        changes["is_active"] = {"from": user.is_active, "to": body.is_active}
        user.is_active = body.is_active

    if changes:
        db.commit()
        write_audit_log(db, admin.id, "update_user", "user", user.id, changes)

    line_name = None
    if user.line_id:
        line = db.query(Line).filter(Line.id == user.line_id).first()
        line_name = line.name if line else None
    return _serialize_user(user, line_name)


@router.post("/users/{user_id}/reset-password")
def reset_password(
    user_id: int,
    body: PasswordReset,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_user),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="账号不存在")

    user.password_hash = hash_password(body.new_password)
    user.must_change_password = True
    user.failed_login_count = 0
    db.commit()
    # 不把新密码写进 details
    write_audit_log(db, admin.id, "reset_password", "user", user.id, {"username": user.username})
    return {"ok": True}


# ── 用户活动详情 ─────────────────────────────────────────────

@router.get("/users/{user_id}/activity")
def get_user_activity(user_id: int, db: Session = Depends(get_db)):
    """该账号的全部「处理记录」：创建的诊断 + 写过的复核 + 未完成对话。"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="账号不存在")

    diagnoses = (
        db.query(DiagnosisRecord)
        .filter(DiagnosisRecord.created_by == user_id)
        .order_by(DiagnosisRecord.created_at.desc())
        .all()
    )
    diagnoses_out = []
    for r in diagnoses:
        try:
            result = json.loads(r.result_json)
        except Exception:
            result = {}
        diagnoses_out.append({
            "diagnosis_id": r.id,
            "bpm_id": r.bpm_id,
            "project_type": r.project_type,
            "overall_risk": r.overall_risk,
            "overall_risk_label": result.get("overall_risk_label", ""),
            "rule_version": r.rule_version,
            "line_id": r.line_id,
            "created_at": r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else "",
        })

    reviews = (
        db.query(DissentRecord)
        .filter(DissentRecord.reviewer_user_id == user_id)
        .order_by(DissentRecord.created_at.desc())
        .all()
    )
    reviews_out = [{
        "dissent_id": r.id,
        "diagnosis_id": r.diagnosis_id,
        "bpm_id": r.bpm_id,
        "review_result": r.review_result,
        "manual_conclusion": r.manual_conclusion,
        "override_reason": r.override_reason,
        "pmo_status": r.pmo_status,
        "created_at": r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else "",
    } for r in reviews]

    sessions = (
        db.query(ChatSession)
        .filter(ChatSession.created_by == user_id)
        .order_by(ChatSession.updated_at.desc())
        .all()
    )
    sessions_out = [{
        "session_id": s.session_id,
        "status": s.status,
        "created_at": s.created_at.strftime("%Y-%m-%d %H:%M") if s.created_at else "",
        "updated_at": s.updated_at.strftime("%Y-%m-%d %H:%M") if s.updated_at else "",
    } for s in sessions]

    return {
        "user_id": user_id,
        "diagnoses": {"count": len(diagnoses_out), "items": diagnoses_out},
        "reviews": {"count": len(reviews_out), "items": reviews_out},
        "chat_sessions": {"count": len(sessions_out), "items": sessions_out},
    }


# ── 审计日志查询 ─────────────────────────────────────────────

@router.get("/audit")
def list_audit(
    admin_user_id: int | None = Query(default=None),
    action: str | None = Query(default=None),
    target_type: str | None = Query(default=None),
    start: str | None = Query(default=None, description="ISO 日期 YYYY-MM-DD"),
    end: str | None = Query(default=None, description="ISO 日期 YYYY-MM-DD"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    q = db.query(AdminAuditLog)
    if admin_user_id is not None:
        q = q.filter(AdminAuditLog.admin_user_id == admin_user_id)
    if action:
        q = q.filter(AdminAuditLog.action == action)
    if target_type:
        q = q.filter(AdminAuditLog.target_type == target_type)
    if start:
        try:
            q = q.filter(AdminAuditLog.created_at >= datetime.fromisoformat(start))
        except ValueError:
            raise HTTPException(status_code=400, detail="start 格式应为 YYYY-MM-DD")
    if end:
        try:
            # end 当天闭区间
            end_dt = datetime.fromisoformat(end)
            end_dt = end_dt.replace(hour=23, minute=59, second=59)
            q = q.filter(AdminAuditLog.created_at <= end_dt)
        except ValueError:
            raise HTTPException(status_code=400, detail="end 格式应为 YYYY-MM-DD")

    total = q.count()
    rows = q.order_by(AdminAuditLog.created_at.desc()).limit(limit).offset(offset).all()

    admin_ids = {r.admin_user_id for r in rows}
    admin_map = {
        u.id: u.display_name
        for u in db.query(User).filter(User.id.in_(admin_ids)).all()
    } if admin_ids else {}

    items = []
    for r in rows:
        try:
            details = json.loads(r.details_json) if r.details_json else None
        except Exception:
            details = {"raw": r.details_json}
        items.append({
            "id": r.id,
            "admin_user_id": r.admin_user_id,
            "admin_display_name": admin_map.get(r.admin_user_id, f"#{r.admin_user_id}"),
            "action": r.action,
            "target_type": r.target_type,
            "target_id": r.target_id,
            "details": details,
            "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else "",
        })
    return {"total": total, "limit": limit, "offset": offset, "items": items}


# ── 存量诊断批量认领 ────────────────────────────────────────

@router.get("/legacy")
def list_legacy(db: Session = Depends(get_db)):
    """列出所有 created_by IS NULL 的存量诊断（admin 唯一可见）。"""
    records = (
        db.query(DiagnosisRecord)
        .filter(DiagnosisRecord.created_by.is_(None))
        .order_by(DiagnosisRecord.created_at.desc())
        .all()
    )
    items = []
    for r in records:
        try:
            result = json.loads(r.result_json)
        except Exception:
            result = {}
        items.append({
            "diagnosis_id": r.id,
            "bpm_id": r.bpm_id,
            "project_type": r.project_type,
            "overall_risk": r.overall_risk,
            "overall_risk_label": result.get("overall_risk_label", ""),
            "rule_version": r.rule_version,
            "created_at": r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else "",
        })
    return {"count": len(items), "items": items}


@router.post("/legacy/claim")
def claim_legacy(
    body: LegacyClaim,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_user),
):
    """把若干条 created_by IS NULL 的存量诊断归到指定 user。
    同时把 diagnosis.line_id 设为该 user 当时的 line_id（admin 目标则保持 NULL）。
    只处理仍为 NULL 的，已被认领的跳过（用于防重）。"""
    target = db.query(User).filter(User.id == body.target_user_id).first()
    if not target:
        raise HTTPException(status_code=400, detail="目标账号不存在")
    if not target.is_active:
        raise HTTPException(status_code=400, detail="目标账号已禁用，不可作为认领目标")

    target_line = target.line_id  # admin 为 None

    records = (
        db.query(DiagnosisRecord)
        .filter(
            DiagnosisRecord.id.in_(body.diagnosis_ids),
            DiagnosisRecord.created_by.is_(None),
        )
        .all()
    )
    claimed_ids = []
    for r in records:
        r.created_by = target.id
        r.line_id = target_line
        claimed_ids.append(r.id)

    if claimed_ids:
        db.commit()
        write_audit_log(db, admin.id, "claim_legacy", "diagnosis", None, {
            "target_user_id": target.id,
            "target_username": target.username,
            "target_line_id": target_line,
            "claimed_count": len(claimed_ids),
            "claimed_ids": claimed_ids,
        })

    skipped = sorted(set(body.diagnosis_ids) - set(claimed_ids))
    return {
        "claimed_count": len(claimed_ids),
        "claimed_ids": claimed_ids,
        "skipped_ids": skipped,
        "skipped_reason": "不存在或非存量数据（已被归属）",
    }
