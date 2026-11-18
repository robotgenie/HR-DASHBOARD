"""In-app notification creation with dedupe protection."""
from datetime import datetime
from typing import List, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.utils.timeutil import utcnow
from app.core.constants import AuditAction
from app.models.notification import Notification
from app.models.user import User
from app.services import audit_service


def create(
    db: Session,
    user_id: int,
    title: str,
    message: str,
    type_: str,
    related_entity: Optional[str] = None,
    related_id: Optional[int] = None,
    dedupe_key: Optional[str] = None,
    actor: Optional[User] = None,
) -> Optional[Notification]:
    """Create a notification. Returns None when dedupe_key was already used."""
    if dedupe_key:
        existing = (
            db.query(Notification).filter(Notification.dedupe_key == dedupe_key).first()
        )
        if existing:
            return None

    notification = Notification(
        user_id=user_id,
        title=title,
        message=message,
        type=type_,
        related_entity=related_entity,
        related_id=related_id,
        dedupe_key=dedupe_key,
    )
    db.add(notification)
    try:
        db.flush()
    except IntegrityError:
        # Lost a race on the unique dedupe_key: another request already created it.
        db.rollback()
        return None

    audit_service.record(
        db,
        AuditAction.NOTIFICATION_CREATED,
        user=actor,
        entity_type="notification",
        entity_id=notification.id,
        meta={"type": type_, "recipient_user_id": user_id},
    )
    return notification


def broadcast(
    db: Session, user_ids: List[int], title: str, message: str, type_: str,
    related_entity: Optional[str] = None, related_id: Optional[int] = None,
    actor: Optional[User] = None,
) -> int:
    created = 0
    for uid in user_ids:
        if create(db, uid, title, message, type_, related_entity, related_id, actor=actor):
            created += 1
    return created


def unread_count(db: Session, user_id: int) -> int:
    return (
        db.query(Notification)
        .filter(Notification.user_id == user_id, Notification.is_read.is_(False))
        .count()
    )


def mark_read(db: Session, notification: Notification) -> Notification:
    if not notification.is_read:
        notification.is_read = True
        notification.read_at = utcnow()
        db.flush()
    return notification


def mark_all_read(db: Session, user_id: int) -> int:
    updated = (
        db.query(Notification)
        .filter(Notification.user_id == user_id, Notification.is_read.is_(False))
        .update({"is_read": True, "read_at": utcnow()}, synchronize_session=False)
    )
    db.flush()
    return updated


def delete(db: Session, notification: Notification, actor: User) -> None:
    """Remove a read notification. Its dedupe_key goes with it, which is fine:
    the events that use dedupe keys (salary credit, ID issue...) are guarded by
    their own timestamps as well, so deleting never causes a re-send."""
    audit_service.record(
        db, AuditAction.NOTIFICATION_DELETED, user=actor, entity_type="notification",
        entity_id=notification.id, meta={"type": notification.type},
    )
    db.delete(notification)
    db.flush()


def delete_read(db: Session, actor: User) -> int:
    rows = (
        db.query(Notification)
        .filter(Notification.user_id == actor.id, Notification.is_read.is_(True))
        .all()
    )
    for row in rows:
        db.delete(row)
    if rows:
        audit_service.record(
            db, AuditAction.NOTIFICATION_DELETED, user=actor, entity_type="notification",
            entity_id=None, meta={"bulk_read_deleted": len(rows)},
        )
    db.flush()
    return len(rows)
