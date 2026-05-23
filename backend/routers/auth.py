"""认证相关接口：登录、改密、当前用户信息。"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth import get_current_user, hash_password, issue_token, verify_password
from database import get_db
from models.diagnosis import User

router = APIRouter(prefix="/api")


# ── Pydantic 模型 ─────────────────────────────────────────────

class LoginBody(BaseModel):
    username: str
    password: str


class ChangePasswordBody(BaseModel):
    old_password: str
    new_password: str = Field(min_length=8, description="新密码至少 8 位")


def _serialize_user(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "email": user.email,
        "role": user.role,
        "line_id": user.line_id,
        "must_change_password": user.must_change_password,
    }


# ── 接口 ─────────────────────────────────────────────────────

@router.post("/auth/login")
def login(body: LoginBody, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == body.username).first()
    now = datetime.now(timezone.utc)

    # 用户名不存在或密码不对走同一分支，避免泄漏「用户名是否存在」
    if not user or not verify_password(body.password, user.password_hash):
        if user:
            user.last_failed_login_at = now
            user.failed_login_count = (user.failed_login_count or 0) + 1
            db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号已被禁用")

    user.last_login_at = now
    user.failed_login_count = 0
    db.commit()

    return {
        "token": issue_token(user),
        "user": _serialize_user(user),
    }


@router.post("/auth/change-password")
def change_password(
    body: ChangePasswordBody,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(body.old_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="原密码错误")
    if body.old_password == body.new_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="新密码不能与原密码相同")

    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    db.commit()
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return _serialize_user(user)
