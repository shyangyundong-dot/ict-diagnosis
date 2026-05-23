import asyncio
import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from auth import hash_password
from database import SessionLocal, init_db
from models.diagnosis import User
from routers.auth import router as auth_router
from routers.diagnosis import router
from session_cleanup import cleanup_stale_chat_sessions

logger = logging.getLogger("uvicorn.error")

app = FastAPI(title="ICT项目合规诊断工具", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 后台定期清理未完成会话（默认每 6 小时一次）
CLEANUP_INTERVAL_SEC = int(os.getenv("CHAT_SESSION_CLEANUP_INTERVAL_SEC", str(6 * 3600)))


async def _periodic_chat_session_cleanup():
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL_SEC)
        try:
            cleanup_stale_chat_sessions()
        except Exception:
            pass


def _bootstrap_initial_admin():
    """user 表为空时，根据环境变量创建首个 admin。幂等。"""
    username = os.getenv("INITIAL_ADMIN_USERNAME")
    password = os.getenv("INITIAL_ADMIN_PASSWORD")
    db = SessionLocal()
    try:
        if db.query(User).count() > 0:
            return
        if not username or not password:
            logger.warning(
                "user 表为空，但 INITIAL_ADMIN_USERNAME / INITIAL_ADMIN_PASSWORD 未配置；"
                "请在 .env 中设置后重启，否则无法登录。"
            )
            return
        admin = User(
            username=username,
            password_hash=hash_password(password),
            display_name=username,
            role="admin",
            line_id=None,
            is_active=True,
            must_change_password=True,  # 首次登录强制改密
        )
        db.add(admin)
        db.commit()
        logger.info("已根据 .env 创建首个 admin 账号：%s（首次登录需改密）", username)
    finally:
        db.close()


@app.on_event("startup")
async def startup():
    init_db()
    _bootstrap_initial_admin()
    try:
        cleanup_stale_chat_sessions()
    except Exception:
        pass
    asyncio.create_task(_periodic_chat_session_cleanup())

app.include_router(auth_router)
app.include_router(router)
