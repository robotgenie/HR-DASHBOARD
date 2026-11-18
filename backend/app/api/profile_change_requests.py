"""Profile change requests: employees raise them, HR approves or rejects them."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.api.serializers import profile_change_out
from app.core.constants import (
    LOCKED_FIELD_LABELS, LOCKED_IDENTITY_FIELDS, ProfileChangeStatus,
)
from app.core.dependencies import get_current_employee, get_current_user, is_hr, require_hr
from app.database.database import get_db
from app.models.employee import Employee
from app.models.profile_change_request import ProfileChangeRequest
from app.models.user import User
from app.schemas.common import Page, PageMeta
from app.schemas.profile_change import (
    ProfileChangeRequestIn, ProfileChangeRequestOut, ProfileChangeReview,
)
from app.services import profile_change_service

router = APIRouter(prefix="/profile-change-requests", tags=["Profile Change Requests"])


def _base(db: Session):
    return db.query(ProfileChangeRequest).options(
        joinedload(ProfileChangeRequest.employee).joinedload(Employee.department),
        joinedload(ProfileChangeRequest.employee).joinedload(Employee.user),
        joinedload(ProfileChangeRequest.reviewed_by),
    )


@router.get("/fields", response_model=List[dict])
def requestable_fields():
    """The fields a change request may target."""
    return [
        {"field_name": field, "label": LOCKED_FIELD_LABELS[field]}
        for field in LOCKED_IDENTITY_FIELDS
    ]


@router.get("", response_model=Page[ProfileChangeRequestOut])
def list_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    status_filter: Optional[str] = Query(None, alias="status"),
    employee_id: Optional[int] = Query(None),
    field_name: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
):
    """HR/Admin see the requests of their hierarchy; everyone else their own."""
    from app.services import hierarchy_service
    query = _base(db)

    if is_hr(current_user):
        query = hierarchy_service.restrict_managed(
            query, db, current_user, ProfileChangeRequest.employee_id
        )
        if employee_id is not None:
            query = query.filter(ProfileChangeRequest.employee_id == employee_id)
    else:
        own = db.query(Employee).filter(Employee.user_id == current_user.id).first()
        if own is None:
            raise HTTPException(status_code=404, detail="No employee profile found.")
        query = query.filter(ProfileChangeRequest.employee_id == own.id)

    if status_filter:
        if status_filter not in ProfileChangeStatus.ALL:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"status must be one of {', '.join(ProfileChangeStatus.ALL)}.",
            )
        query = query.filter(ProfileChangeRequest.status == status_filter)

    if field_name:
        query = query.filter(ProfileChangeRequest.field_name == field_name)

    if search:
        like = f"%{search.strip()}%"
        query = query.join(Employee, Employee.id == ProfileChangeRequest.employee_id).filter(
            or_(
                Employee.full_name.ilike(like),
                Employee.employee_code.ilike(like),
                Employee.unique_employee_id.ilike(like),
                ProfileChangeRequest.new_value.ilike(like),
            )
        )

    total = query.count()
    rows = (
        query.order_by(ProfileChangeRequest.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return Page[ProfileChangeRequestOut](
        items=[ProfileChangeRequestOut(**profile_change_out(r)) for r in rows],
        meta=PageMeta(
            page=page, page_size=page_size, total=total,
            pages=max(1, (total + page_size - 1) // page_size),
        ),
    )


@router.post("", response_model=ProfileChangeRequestOut, status_code=status.HTTP_201_CREATED)
def create_request(
    payload: ProfileChangeRequestIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    employee: Employee = Depends(get_current_employee),
):
    """Employees only: HR edits identity fields directly instead."""
    request = profile_change_service.create_request(
        db, employee, payload.field_name, payload.new_value, payload.reason, current_user
    )
    db.commit()
    db.refresh(request)
    return ProfileChangeRequestOut(**profile_change_out(request))


def _load(db: Session, request_id: int, user: Optional[User] = None,
          level: str = "manage") -> ProfileChangeRequest:
    request = _base(db).filter(ProfileChangeRequest.id == request_id).first()
    if request is None:
        raise HTTPException(status_code=404, detail="Change request not found.")
    if user is not None:
        from app.core.dependencies import assert_can_access_employee
        assert_can_access_employee(user, request.employee_id, db, level=level)
    return request


@router.get("/{request_id}", response_model=ProfileChangeRequestOut)
def get_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    request = _load(db, request_id)
    own = current_user.employee
    is_own = own is not None and request.employee_id == own.id
    from app.services import hierarchy_service
    if not is_own and not (is_hr(current_user) and hierarchy_service.can_manage_employee(
            db, current_user, request.employee)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only view your own change requests.",
        )
    return ProfileChangeRequestOut(**profile_change_out(request))


@router.post("/{request_id}/approve", response_model=ProfileChangeRequestOut)
def approve_request(
    request_id: int,
    payload: ProfileChangeReview,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr),
):
    request = profile_change_service.approve(
        db, _load(db, request_id, current_user), current_user, payload.remarks
    )
    db.commit()
    db.refresh(request)
    return ProfileChangeRequestOut(**profile_change_out(request))


@router.post("/{request_id}/reject", response_model=ProfileChangeRequestOut)
def reject_request(
    request_id: int,
    payload: ProfileChangeReview,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr),
):
    request = profile_change_service.reject(
        db, _load(db, request_id, current_user), current_user, payload.remarks
    )
    db.commit()
    db.refresh(request)
    return ProfileChangeRequestOut(**profile_change_out(request))
