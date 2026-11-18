"""Append-only audit trail helper."""
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.user import User


def record(
    db: Session,
    action: str,
    user: Optional[User] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    meta: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    commit: bool = False,
) -> AuditLog:
    entry = AuditLog(
        user_id=user.id if user else None,
        actor_email=user.email if user else None,
        role_name=user.role_name if user else None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        meta=meta or {},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(entry)
    db.flush()
    if commit:
        db.commit()
    return entry
