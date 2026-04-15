import asyncio
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import init_db
from routers.diagnosis import router
from session_cleanup import cleanup_stale_chat_sessions

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


@app.on_event("startup")
async def startup():
    init_db()
    try:
        cleanup_stale_chat_sessions()
    except Exception:
        pass
    asyncio.create_task(_periodic_chat_session_cleanup())

app.include_router(router)
