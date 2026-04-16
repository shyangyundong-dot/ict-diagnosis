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

def _migrate_sqlite_add_chat_snapshot():
    """已有库文件缺少 chat_snapshot_json 列时补齐（SQLite）。"""
    with engine.begin() as conn:
        r = conn.execute(text("PRAGMA table_info(diagnosis_records)"))
        cols = [row[1] for row in r.fetchall()]
        if cols and "chat_snapshot_json" not in cols:
            conn.execute(
                text("ALTER TABLE diagnosis_records ADD COLUMN chat_snapshot_json TEXT")
            )


def init_db():
    Base.metadata.create_all(bind=engine)
    _migrate_sqlite_add_chat_snapshot()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
