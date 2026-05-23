"""管理员后台接口：线条与账号 CRUD、重置密码。"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from audit import write_audit_log
from auth import get_current_user, hash_password, require_admin
from database import get_db
from models.diagnosis import Line, User

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
