from sqlalchemy import select
from datetime import date, datetime, time
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.dependencies import require_hr
from app.database.database import get_db
from app.models.audit_log import AuditLog
from app.models.email_log import EmailLog
from app.models.user import User
from app.schemas.common import Page, PageMeta
from app.schemas.notification import AuditLogOut, EmailLogOut

router = APIRouter(prefix="/audit-logs", tags=["Audit"])


@router.get("", response_model=Page[AuditLogOut])
def list_audit_logs(
    action: Optional[str] = None,
    entity_type: Optional[str] = None,
    user_id: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr),
):
    """Read-only. Admin: every entry. HR: entries made by people in their
    hierarchy (and their own). There is no create, update or delete route."""
    from app.services import hierarchy_service
    query = db.query(AuditLog)
    users = hierarchy_service.visible_user_ids_select(db, current_user)
    if users is not None:
        query = query.filter(AuditLog.user_id.in_(users))
    if action:
        query = query.filter(AuditLog.action == action)
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    if user_id:
        query = query.filter(AuditLog.user_id == user_id)
    if date_from:
        query = query.filter(AuditLog.created_at >= datetime.combine(date_from, time.min))
    if date_to:
        query = query.filter(AuditLog.created_at <= datetime.combine(date_to, time.max))
    if search:
        query = query.filter(AuditLog.actor_email.ilike(f"%{search.strip()}%"))

    total = query.count()
    rows = (
        query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return Page[AuditLogOut](
        items=[AuditLogOut.model_validate(r) for r in rows],
        meta=PageMeta(
            page=page, page_size=page_size, total=total,
            pages=(total + page_size - 1) // page_size,
        ),
    )


@router.get("/actions", response_model=List[str])
def distinct_actions(
    db: Session = Depends(get_db), current_user: User = Depends(require_hr)
):
    return [row[0] for row in db.query(AuditLog.action).distinct().order_by(AuditLog.action)]


@router.get("/emails", response_model=List[EmailLogOut])
def list_email_logs(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr),
):
    from app.services import hierarchy_service
    from app.models.employee import Employee
    query = db.query(EmailLog)
    ids = hierarchy_service.visible_ids_select(db, current_user)
    if ids is not None:
        emails = select(User.email).join(Employee, Employee.user_id == User.id).where(Employee.id.in_(ids))
        query = query.filter(EmailLog.to_email.in_(emails))
    rows = query.order_by(EmailLog.created_at.desc()).limit(limit).all()
    return [EmailLogOut.model_validate(r) for r in rows]
