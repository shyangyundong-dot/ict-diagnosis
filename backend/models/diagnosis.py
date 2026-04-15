from sqlalchemy import Column, Integer, String, Text, DateTime, func
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

class DiagnosisRecord(Base):
    __tablename__ = "diagnosis_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bpm_id = Column(String(100), nullable=False)
    project_type = Column(String(200), nullable=False)
    input_json = Column(Text, nullable=False)
    overall_risk = Column(String(20), nullable=False)
    result_json = Column(Text, nullable=False)
    rule_version = Column(String(20), nullable=False)
    created_at = Column(DateTime, server_default=func.now())

class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(100), nullable=False, unique=True)
    messages_json = Column(Text, nullable=False, default="[]")
    extracted_fields_json = Column(Text, nullable=False, default="{}")
    status = Column(String(20), nullable=False, default="collecting")  # collecting | confirmed | submitted
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
