"""Profile change requests: the only route by which locked identity fields move.

An employee can fill in their identity details once. Completing the profile
locks them. After that the employee cannot write these fields through any API;
they raise a request, and HR approving it is what applies the new value.
"""
import re
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.constants import (
    LOCKED_FIELD_LABELS, LOCKED_IDENTITY_FIELDS, AuditAction, NotificationType,
    ProfileChangeStatus, RoleName,
)
from app.models.employee import Employee
from app.models.profile_change_request import ProfileChangeRequest
from app.models.role import Role
from app.models.user import User
from app.services import audit_service, notification_service
from app.utils.timeutil import utcnow

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^[0-9+\-\s()]{7,20}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
GENDERS = {"Male", "Female", "Other", "Prefer not to say"}


def current_value(employee: Employee, field: str) -> Optional[str]:
    if field == "email":
        return employee.user.email if employee.user else None
    value = getattr(employee, field, None)
    return None if value is None else str(value)


def _validate(db: Session, employee: Employee, field: str, new_value: str) -> str:
    new_value = (new_value or "").strip()
    if not new_value:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Enter the new value you are requesting.",
        )
    if field == "email":
        if not EMAIL_RE.match(new_value):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Enter a valid email address.",
            )
        clash = (
            db.query(User)
            .filter(User.email == new_value.lower(), User.id != employee.user_id)
            .first()
        )
        if clash:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Another account already uses that email address.",
            )
        new_value = new_value.lower()
    elif field == "phone":
        if not PHONE_RE.match(new_value):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Enter a valid phone number.",
            )
    elif field == "date_of_birth":
        if not DATE_RE.match(new_value):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Enter the date of birth as YYYY-MM-DD.",
            )
    elif field == "gender":
        if new_value not in GENDERS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Gender must be one of: {', '.join(sorted(GENDERS))}.",
            )
    elif field == "full_name":
        if len(new_value) < 2:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Enter the full name as it should appear.",
            )
    return new_value


def create_request(
    db: Session,
    employee: Employee,
    field: str,
    new_value: str,
    reason: Optional[str],
    actor: User,
) -> ProfileChangeRequest:
    if field not in LOCKED_IDENTITY_FIELDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "That field is not managed through change requests. Requestable "
                f"fields: {', '.join(LOCKED_FIELD_LABELS[f] for f in LOCKED_IDENTITY_FIELDS)}."
            ),
        )

    new_value = _validate(db, employee, field, new_value)
    old_value = current_value(employee, field)
    if old_value is not None and old_value.strip().lower() == new_value.strip().lower():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Your {LOCKED_FIELD_LABELS[field]} is already set to that value.",
        )

    pending = (
        db.query(ProfileChangeRequest)
        .filter(
            ProfileChangeRequest.employee_id == employee.id,
            ProfileChangeRequest.field_name == field,
            ProfileChangeRequest.status == ProfileChangeStatus.PENDING,
        )
        .first()
    )
    if pending:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"You already have a pending request for {LOCKED_FIELD_LABELS[field]}. "
                "HR will review it shortly."
            ),
        )

    request = ProfileChangeRequest(
        employee_id=employee.id,
        field_name=field,
        old_value=old_value,
        new_value=new_value,
        reason=(reason or "").strip() or None,
        status=ProfileChangeStatus.PENDING,
        requested_at=utcnow(),
    )
    db.add(request)
    db.flush()

    audit_service.record(
        db, AuditAction.PROFILE_CHANGE_REQUESTED, user=actor,
        entity_type="profile_change_request", entity_id=request.id,
        meta={
            "employee_id": employee.id,
            "field": field,
            "old_value": old_value,
            "new_value": new_value,
        },
    )

    label = LOCKED_FIELD_LABELS[field]
    notification_service.create(
        db, user_id=employee.user_id,
        title="Profile change request submitted",
        message=(
            f"Your request to change {label} to \"{new_value}\" has been sent to HR. "
            "You will be notified once it is reviewed."
        ),
        type_=NotificationType.PROFILE_CHANGE_REQUESTED,
        related_entity="profile_change_request", related_id=request.id,
        dedupe_key=f"pcr:{request.id}:submitted", actor=actor,
    )
    _notify_hr(db, employee, label, new_value, request, actor)
    return request


def _notify_hr(db, employee, label, new_value, request, actor) -> None:
    # Only the HR responsible for this person (hierarchy), or the Admin for HR.
    from app.services import hierarchy_service
    hr_users = hierarchy_service.oversight_users(db, employee)
    for hr_user in hr_users:
        notification_service.create(
            db, user_id=hr_user.id,
            title="Profile change request awaiting review",
            message=(
                f"{employee.full_name} ({employee.display_employee_id}) requested a "
                f"change to {label}: \"{new_value}\"."
            ),
            type_=NotificationType.PROFILE_CHANGE_REQUESTED,
            related_entity="profile_change_request", related_id=request.id,
            dedupe_key=f"pcr:{request.id}:hr:{hr_user.id}", actor=actor,
        )


def _assert_pending(request: ProfileChangeRequest) -> None:
    if request.status != ProfileChangeStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"This request was already {request.status.lower()}.",
        )


def approve(
    db: Session, request: ProfileChangeRequest, actor: User, remarks: Optional[str] = None
) -> ProfileChangeRequest:
    _assert_pending(request)
    employee = request.employee
    field = request.field_name

    # Re-validate at approval time: the world may have moved since the request.
    value = _validate(db, employee, field, request.new_value)

    if field == "email":
        employee.user.email = value
    elif field == "date_of_birth":
        from datetime import date as _date

        employee.date_of_birth = _date.fromisoformat(value)
    else:
        setattr(employee, field, value)

    request.status = ProfileChangeStatus.APPROVED
    request.hr_remarks = (remarks or "").strip() or None
    request.reviewed_at = utcnow()
    request.reviewed_by_id = actor.id
    db.flush()

    audit_service.record(
        db, AuditAction.PROFILE_CHANGE_APPROVED, user=actor,
        entity_type="profile_change_request", entity_id=request.id,
        meta={
            "employee_id": employee.id,
            "field": field,
            "old_value": request.old_value,
            "new_value": value,
            "remarks": request.hr_remarks,
        },
    )
    label = LOCKED_FIELD_LABELS.get(field, field)
    notification_service.create(
        db, user_id=employee.user_id,
        title=f"{label} change approved",
        message=(
            f"HR approved your request. Your {label} is now \"{value}\"."
            + (f" Remarks: {request.hr_remarks}" if request.hr_remarks else "")
        ),
        type_=NotificationType.PROFILE_CHANGE_APPROVED,
        related_entity="profile_change_request", related_id=request.id,
        dedupe_key=f"pcr:{request.id}:approved", actor=actor,
    )
    return request


def reject(
    db: Session, request: ProfileChangeRequest, actor: User, remarks: Optional[str] = None
) -> ProfileChangeRequest:
    _assert_pending(request)
    remarks = (remarks or "").strip()
    if not remarks:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Add a short reason so the employee knows why it was rejected.",
        )

    request.status = ProfileChangeStatus.REJECTED
    request.hr_remarks = remarks
    request.reviewed_at = utcnow()
    request.reviewed_by_id = actor.id
    db.flush()

    employee = request.employee
    audit_service.record(
        db, AuditAction.PROFILE_CHANGE_REJECTED, user=actor,
        entity_type="profile_change_request", entity_id=request.id,
        meta={
            "employee_id": employee.id,
            "field": request.field_name,
            "requested_value": request.new_value,
            "remarks": remarks,
        },
    )
    label = LOCKED_FIELD_LABELS.get(request.field_name, request.field_name)
    notification_service.create(
        db, user_id=employee.user_id,
        title=f"{label} change rejected",
        message=(
            f"HR did not approve your request to change {label}. "
            f"Reason: {remarks} Your current details are unchanged."
        ),
        type_=NotificationType.PROFILE_CHANGE_REJECTED,
        related_entity="profile_change_request", related_id=request.id,
        dedupe_key=f"pcr:{request.id}:rejected", actor=actor,
    )
    return request
