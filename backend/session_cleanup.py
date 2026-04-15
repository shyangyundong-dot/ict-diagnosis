"""未完成对话会话的过期清理，避免 SQLite 中堆积大量废弃 ChatSession。"""

import os
from datetime import datetime, timedelta

from sqlalchemy import delete, func

from database import SessionLocal
from models.diagnosis import ChatSession

# 仅删除 status=collecting 且超过该小时数未更新的会话（可用环境变量覆盖）
STALE_HOURS = int(os.getenv("CHAT_SESSION_STALE_HOURS", "24"))


def cleanup_stale_chat_sessions() -> int:
    """
    删除「收集中」且长期未更新的会话。返回删除行数。
    updated_at 为空时回退到 created_at（兼容旧数据）。
    """
    db = SessionLocal()
    try:
        cutoff = datetime.utcnow() - timedelta(hours=STALE_HOURS)
        last_activity = func.coalesce(ChatSession.updated_at, ChatSession.created_at)
        result = db.execute(
            delete(ChatSession).where(
                ChatSession.status == "collecting",
                last_activity < cutoff,
            )
        )
        db.commit()
        return int(result.rowcount or 0)
    finally:
        db.close()
