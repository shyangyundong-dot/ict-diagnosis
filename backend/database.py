import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from models.diagnosis import Base

load_dotenv()

DB_PATH = os.getenv("DATABASE_PATH", "../data/diagnosis.db")
os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _add_column_if_missing(conn, table: str, column: str, ddl: str) -> bool:
    """给已存在的表补列；返回 True 表示本次新加。"""
    r = conn.execute(text(f"PRAGMA table_info({table})"))
    cols = [row[1] for row in r.fetchall()]
    if not cols:
        return False  # 表不存在，由 create_all 负责
    if column in cols:
        return False
    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {ddl}"))
    return True


def _migrate_sqlite():
    """已有库文件缺列时补齐（SQLite 不支持 CREATE TABLE IF NOT EXISTS 多列 ALTER）。"""
    with engine.begin() as conn:
        # 既有列补齐
        _add_column_if_missing(conn, "diagnosis_records", "chat_snapshot_json", "chat_snapshot_json TEXT")

        # 账号 & 权限模块新增列
        _add_column_if_missing(conn, "diagnosis_records", "created_by", "created_by INTEGER")
        _add_column_if_missing(conn, "diagnosis_records", "line_id", "line_id INTEGER")
        chat_session_created_by_just_added = _add_column_if_missing(
            conn, "chat_sessions", "created_by", "created_by INTEGER"
        )
        _add_column_if_missing(conn, "dissent_records", "reviewer_user_id", "reviewer_user_id INTEGER")

        # 核算单元模块（#7）
        _add_column_if_missing(conn, "chat_sessions", "accounting_units_json", "accounting_units_json TEXT DEFAULT '[]'")
        _add_column_if_missing(conn, "diagnosis_records", "accounting_units_json", "accounting_units_json TEXT")

        # 一次性清理：created_by 列刚加上时，把所有 status='collecting' 的存量会话删掉
        # 它们没有归属人，新认证体系下无法被任何用户接续完成（设计文档 §11.1 决策 A）
        if chat_session_created_by_just_added:
            conn.execute(
                text("DELETE FROM chat_sessions WHERE created_by IS NULL AND status = 'collecting'")
            )


def init_db():
    Base.metadata.create_all(bind=engine)
    _migrate_sqlite()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
