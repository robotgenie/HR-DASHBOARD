"""Intern payslip download requests.

An intern may always view a payslip. Downloading needs HR approval, and this is
the workflow for asking: the intern gives a reason, HR approves or rejects it.

Approval sets `SalaryRecord.intern_download_allowed` on that one salary record,
which is the same flag the download endpoint already checks -- there is no
second permission system, and approving one month never unlocks another.
"""
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.constants import (
    AuditAction, DownloadRequestStatus, NotificationType, RoleName,
)
from app.models.employee import Employee
from app.models.intern_payslip_request import InternPayslipDownloadRequest
from app.models.role import Role
from app.models.salary import SalaryRecord
from app.models.user import User
from app.services import audit_service, notification_service, salary_service
from app.utils.timeutil import utcnow

MIN_REASON_CHARS = 10


def pending_for(db: Session, salary_id: int, employee_id: int):
    return (
        db.query(InternPayslipDownloadRequest)
        .filter(
            InternPayslipDownloadRequest.salary_id == salary_id,
            InternPayslipDownloadRequest.employee_id == employee_id,
            InternPayslipDownloadRequest.status == DownloadRequestStatus.PENDING,
        )
        .first()
    )


def latest_for(db: Session, salary_id: int, employee_id: int):
    return (
        db.query(InternPayslipDownloadRequest)
        .filter(
            InternPayslipDownloadRequest.salary_id == salary_id,
            InternPayslipDownloadRequest.employee_id == employee_id,
        )
        .order_by(InternPayslipDownloadRequest.created_at.desc())
        .first()
    )


def _clean_reason(reason: Optional[str]) -> str:
    """Reject empty, whitespace-only and content-free reasons."""
    text = " ".join((reason or "").split())
    if not text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Enter the reason for requesting this payslip.",
        )
    if len(text) < MIN_REASON_CHARS or not any(ch.isalpha() for ch in text):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "Please give HR a little more detail about why you need this "
                "payslip (at least a short sentence)."
            ),
        )
    return text


def create_request(
    db: Session, record: SalaryRecord, employee: Employee, actor: User, reason: str
) -> InternPayslipDownloadRequest:
    # Intern status comes from the employee's own department record, never from
    # anything the client sends.
    if not employee.is_intern:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "Download requests apply to interns only. Your payslip can be "
                "downloaded directly once the salary is credited."
            ),
        )
    if record.employee_id != employee.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only request your own payslip.",
        )
    if record.intern_download_allowed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already have permission to download this payslip.",
        )

    reason = _clean_reason(reason)

    if pending_for(db, record.id, employee.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Your download request is already pending HR approval.",
        )

    request = InternPayslipDownloadRequest(
        employee_id=employee.id,
        salary_id=record.id,
        reason=reason,
        status=DownloadRequestStatus.PENDING,
        requested_at=utcnow(),
    )
    db.add(request)
    db.flush()

    audit_service.record(
        db, AuditAction.INTERN_PAYSLIP_DOWNLOAD_REQUESTED, user=actor,
        entity_type="intern_payslip_download_request", entity_id=request.id,
        meta={
            "employee_id": employee.id,
            "salary_id": record.id,
            "period": record.period_label,
            "reason": reason,
        },
    )

    notification_service.create(
        db, user_id=employee.user_id,
        title="Download request sent to HR",
        message=(
            f"Your request to download the {record.period_label} payslip has been "
            "sent to HR for approval."
        ),
        type_=NotificationType.PAYSLIP_DOWNLOAD_REQUESTED,
        related_entity="intern_payslip_download_request", related_id=request.id,
        dedupe_key=f"ipdr:{request.id}:submitted", actor=actor,
    )

    from app.services import hierarchy_service
    for hr_user in hierarchy_service.oversight_users(db, employee):
        notification_service.create(
            db, user_id=hr_user.id,
            title="Intern payslip download request",
            message=(
                f"Intern payslip download request received from {employee.full_name} "
                f"for {record.period_label}."
            ),
            type_=NotificationType.PAYSLIP_DOWNLOAD_REQUESTED,
            related_entity="intern_payslip_download_request", related_id=request.id,
            dedupe_key=f"ipdr:{request.id}:hr:{hr_user.id}", actor=actor,
        )
    return request


def _assert_pending(request: InternPayslipDownloadRequest) -> None:
    if request.status != DownloadRequestStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"This request was already {request.status.lower()}.",
        )


def approve(
    db: Session, request: InternPayslipDownloadRequest, actor: User,
    remarks: Optional[str] = None,
) -> InternPayslipDownloadRequest:
    _assert_pending(request)
    record = request.salary

    request.status = DownloadRequestStatus.APPROVED
    request.hr_remarks = (remarks or "").strip() or None
    request.reviewed_at = utcnow()
    request.hr_reviewer_id = actor.id

    # Grant on this salary record only. The existing permission flag stays the
    # single source of truth the download endpoint checks.
    salary_service.set_intern_download_permission(db, record, actor, True)
    db.flush()

    audit_service.record(
        db, AuditAction.INTERN_PAYSLIP_REQUEST_APPROVED, user=actor,
        entity_type="intern_payslip_download_request", entity_id=request.id,
        meta={
            "employee_id": request.employee_id,
            "salary_id": record.id,
            "period": record.period_label,
            "remarks": request.hr_remarks,
        },
    )
    return request


def reject(
    db: Session, request: InternPayslipDownloadRequest, actor: User,
    remarks: Optional[str] = None,
) -> InternPayslipDownloadRequest:
    _assert_pending(request)
    remarks = (remarks or "").strip()
    if not remarks:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Add a short reason so the intern knows why it was rejected.",
        )

    record = request.salary
    request.status = DownloadRequestStatus.REJECTED
    request.hr_remarks = remarks
    request.reviewed_at = utcnow()
    request.hr_reviewer_id = actor.id
    db.flush()

    audit_service.record(
        db, AuditAction.INTERN_PAYSLIP_REQUEST_REJECTED, user=actor,
        entity_type="intern_payslip_download_request", entity_id=request.id,
        meta={
            "employee_id": request.employee_id,
            "salary_id": record.id,
            "period": record.period_label,
            "remarks": remarks,
        },
    )
    notification_service.create(
        db, user_id=request.employee.user_id,
        title="Payslip download request rejected",
        message=(
            f"Your payslip download request for {record.period_label} was rejected. "
            f"HR remarks: {remarks}"
        ),
        type_=NotificationType.PAYSLIP_DOWNLOAD_REJECTED,
        related_entity="intern_payslip_download_request", related_id=request.id,
        dedupe_key=f"ipdr:{request.id}:rejected", actor=actor,
    )
    return request


def request_state(db: Session, record: SalaryRecord, employee: Employee) -> dict:
    """What the intern's payslip buttons should show for this salary record."""
    if employee is None or not employee.is_intern:
        return {"applies": False, "status": None, "can_request": False}
    latest = latest_for(db, record.id, employee.id)
    allowed = bool(record.intern_download_allowed)
    return {
        "applies": True,
        "status": latest.status if latest else None,
        "hr_remarks": latest.hr_remarks if latest else None,
        "reason": latest.reason if latest else None,
        "request_id": latest.id if latest else None,
        # A rejected request can be raised again; a pending one cannot.
        "can_request": (
            not allowed
            and (latest is None or latest.status == DownloadRequestStatus.REJECTED)
        ),
    }
