from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.database.database import get_db
from app.models.notification import Notification
from app.models.user import User
from app.schemas.common import Message
from app.schemas.notification import NotificationList, NotificationOut
from app.services import notification_service

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("", response_model=NotificationList)
def list_notifications(
    unread_only: bool = False,
    type_filter: Optional[str] = Query(None, alias="type"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Scoped to the signed-in user; there is no way to read anyone else's."""
    query = db.query(Notification).filter(Notification.user_id == current_user.id)
    if unread_only:
        query = query.filter(Notification.is_read.is_(False))
    if type_filter:
        query = query.filter(Notification.type == type_filter)

    total = query.count()
    items = query.order_by(Notification.created_at.desc()).limit(limit).all()
    return NotificationList(
        items=[NotificationOut.model_validate(n) for n in items],
        unread_count=notification_service.unread_count(db, current_user.id),
        total=total,
    )


@router.get("/unread-count")
def unread_count(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    return {"unread_count": notification_service.unread_count(db, current_user.id)}


@router.post("/{notification_id}/read", response_model=NotificationOut)
def mark_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    notification = (
        db.query(Notification)
        .filter(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
        )
        .first()
    )
    if notification is None:
        raise HTTPException(status_code=404, detail="Notification not found.")
    notification_service.mark_read(db, notification)
    db.commit()
    return NotificationOut.model_validate(notification)


@router.post("/read-all", response_model=Message)
def mark_all_read(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    count = notification_service.mark_all_read(db, current_user.id)
    db.commit()
    return Message(detail=f"{count} notifications marked as read.")


@router.delete("/read", response_model=Message)
def delete_all_read(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    """Clear every already-read notification of the signed-in user."""
    count = notification_service.delete_read(db, current_user)
    db.commit()
    return Message(detail=f"{count} read notifications deleted.")


@router.delete("/{notification_id}", response_model=Message)
def delete_notification(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete one of your own notifications. Only read notifications can be deleted."""
    notification = (
        db.query(Notification)
        .filter(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
        )
        .first()
    )
    if notification is None:
        raise HTTPException(status_code=404, detail="Notification not found.")
    if not notification.is_read:
        raise HTTPException(
            status_code=409, detail="Mark this notification as read before deleting it."
        )
    notification_service.delete(db, notification, current_user)
    db.commit()
    return Message(detail="Notification deleted.")
