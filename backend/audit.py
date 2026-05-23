"""admin 写操作审计日志辅助函数。"""

import json
from sqlalchemy.orm import Session

from models.diagnosis import AdminAuditLog


def write_audit_log(
    db: Session,
    admin_user_id: int,
    action: str,
    target_type: str | None = None,
    target_id: str | int | None = None,
    details: dict | None = None,
) -> None:
    log = AdminAuditLog(
        admin_user_id=admin_user_id,
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        details_json=json.dumps(details, ensure_ascii=False, default=str) if details else None,
    )
    db.add(log)
    db.commit()
