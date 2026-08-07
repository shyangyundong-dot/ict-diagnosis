from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, func
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

class DiagnosisRecord(Base):
    __tablename__ = "diagnosis_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bpm_id = Column(String(100), nullable=False)
    project_type = Column(String(200), nullable=False)
    input_json = Column(Text, nullable=False)
    chat_snapshot_json = Column(Text, nullable=True)
    # 提交时的字段来源与人工核对快照；规则引擎不读取，只供溯源审计。
    field_review_json = Column(Text, nullable=True)
    # 六块引导式项目说明及提交时覆盖评估快照，只供交互溯源。
    guided_input_json = Column(Text, nullable=True)
    coverage_json = Column(Text, nullable=True)
    # 核算单元列表快照（#7）；NULL = 该记录创建于核算单元功能之前
    accounting_units_json = Column(Text, nullable=True)
    overall_risk = Column(String(20), nullable=False)
    result_json = Column(Text, nullable=False)
    rule_version = Column(String(20), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    # NULL = 上线前的存量数据（admin 唯一可见）；非 NULL = 真实创建人
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    # 创建时快照：员工调线条后此字段不变（设计意图，见 docs/auth-and-rbac-design.md §4.2）
    line_id = Column(Integer, ForeignKey("lines.id"), nullable=True, index=True)

class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(100), nullable=False, unique=True)
    messages_json = Column(Text, nullable=False, default="[]")
    extracted_fields_json = Column(Text, nullable=False, default="{}")
    # {schema_version, fields:{key:{source,status}}}；AI 预填必须人工确认后才能提交。
    field_review_json = Column(Text, nullable=False, default="{}")
    # 六块自然语言原文与覆盖/追问状态；规则引擎不直接读取。
    guided_input_json = Column(Text, nullable=False, default="{}")
    coverage_json = Column(Text, nullable=False, default="{}")
    # AI 切分草稿 + 用户确认后的核算单元列表（#7）
    accounting_units_json = Column(Text, nullable=False, default="[]")
    status = Column(String(20), nullable=False, default="collecting")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

class DissentRecord(Base):
    """人工复核与异议记录（规格 §7）"""
    __tablename__ = "dissent_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    diagnosis_id = Column(Integer, nullable=False, index=True)
    bpm_id = Column(String(100), nullable=False)
    reviewer_id = Column(String(100), nullable=True)  # 老字符串字段，保留兼容
    reviewer_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    review_result = Column(String(20), nullable=False)  # confirmed | partial | overridden
    risk_point_ids = Column(Text, nullable=True)         # JSON 数组
    manual_conclusion = Column(Text, nullable=True)
    override_reason = Column(Text, nullable=True)
    rule_version = Column(String(20), nullable=True)
    pmo_status = Column(String(20), nullable=False, default="pending")
    pmo_action = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class Line(Base):
    """组织架构单元（线条）。每个 user 挂一个 line；每个 line 至多一个 role=reviewer 的 user。"""
    __tablename__ = "lines"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, server_default=func.now())


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    display_name = Column(String(100), nullable=False)
    email = Column(String(255), nullable=True)
    role = Column(String(20), nullable=False)  # admin | reviewer | user
    line_id = Column(Integer, ForeignKey("lines.id"), nullable=True, index=True)
    is_active = Column(Boolean, nullable=False, default=True)
    must_change_password = Column(Boolean, nullable=False, default=True)
    last_login_at = Column(DateTime, nullable=True)
    last_failed_login_at = Column(DateTime, nullable=True)
    failed_login_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class AdminAuditLog(Base):
    """admin 的写操作审计。读操作不记。"""
    __tablename__ = "admin_audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    admin_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    action = Column(String(50), nullable=False, index=True)
    target_type = Column(String(50), nullable=True)
    target_id = Column(String(100), nullable=True)
    details_json = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), index=True)
