"""UAN submission and HR verification."""
import re
from datetime import datetime
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.utils.timeutil import utcnow
from app.core.constants import AuditAction, NotificationType, UanStatus
from app.models.employee import Employee
from app.models.uan import UanDetail
from app.models.user import User
from app.services import audit_service, notification_service

UAN_PATTERN = re.compile(r"^\d{12}$")


def get_or_create(db: Session, employee: Employee) -> UanDetail:
    record = db.query(UanDetail).filter(UanDetail.employee_id == employee.id).first()
    if record is None:
        record = UanDetail(employee_id=employee.id, status=UanStatus.NOT_SUBMITTED)
        db.add(record)
        db.flush()
    return record


def submit(db: Session, employee: Employee, uan_number: str, actor: User) -> UanDetail:
    number = (uan_number or "").strip().replace(" ", "")
    if not UAN_PATTERN.match(number):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="A UAN is exactly 12 digits.",
        )

    record = get_or_create(db, employee)
    if record.status == UanStatus.VERIFIED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Your UAN is already verified. Contact HR to change it.",
        )

    previous = record.uan_number
    record.uan_number = number
    record.status = UanStatus.SUBMITTED
    record.submitted_at = utcnow()
    record.hr_remarks = None
    record.verified_at = None
    record.verified_by_id = None
    db.flush()

    audit_service.record(
        db, AuditAction.UAN_SUBMITTED, user=actor, entity_type="uan_detail",
        entity_id=record.id,
        meta={"employee_id": employee.id, "previous": previous, "submitted": number},
    )
    return record


def review(
    db: Session, record: UanDetail, actor: User, verified: bool,
    remarks: Optional[str] = None,
) -> UanDetail:
    if record.status == UanStatus.NOT_SUBMITTED or not record.uan_number:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This employee hasn't submitted a UAN yet.",
        )
    if not verified and not (remarks or "").strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Add a remark explaining the rejection.",
        )

    record.status = UanStatus.VERIFIED if verified else UanStatus.REJECTED
    record.hr_remarks = (remarks or "").strip() or None
    record.verified_by_id = actor.id
    record.verified_at = utcnow()
    db.flush()

    audit_service.record(
        db,
        AuditAction.UAN_VERIFIED if verified else AuditAction.UAN_REJECTED,
        user=actor, entity_type="uan_detail", entity_id=record.id,
        meta={
            "employee_id": record.employee_id,
            "uan": record.uan_number,
            "remarks": record.hr_remarks,
        },
    )
    notification_service.create(
        db,
        user_id=record.employee.user_id,
        title="UAN verified" if verified else "UAN rejected",
        message=(
            "Your UAN has been verified by HR."
            if verified
            else f"Your UAN was rejected. {record.hr_remarks}"
        ),
        type_=NotificationType.UAN_VERIFIED if verified else NotificationType.UAN_REJECTED,
        related_entity="uan_detail", related_id=record.id,
        dedupe_key=f"uan:{record.id}:{record.status}:{record.verified_at.isoformat()}",
        actor=actor,
    )
    return record


def set_under_verification(db: Session, record: UanDetail, actor: User) -> UanDetail:
    record.status = UanStatus.UNDER_VERIFICATION
    db.flush()
    return record
