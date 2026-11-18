from datetime import date
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.core.constants import (
    ApprovalStage, AuditAction, LeavePeriod, LeaveStatus, LeaveType, NotificationType,
)
from app.models.employee import Employee
from app.models.leave_request import LeaveRequest
from app.models.user import User
from app.services import audit_service, hierarchy_service, notification_service
from app.utils.timeutil import utcnow


PERIOD_HOURS = {
    LeavePeriod.MORNING_HALF: "10:00 AM - 1:00 PM",
    LeavePeriod.AFTERNOON_HALF: "1:00 PM - 6:00 PM",
    LeavePeriod.FULL_DAY: "10:00 AM - 6:00 PM",
}


def _validate_type(leave_type: str) -> str:
    if leave_type == "Other Leave":
        leave_type = LeaveType.OTHER
    if leave_type not in LeaveType.ALL:
        raise HTTPException(status_code=422, detail="Pick a valid leave type.")
    return leave_type


def validate_period(leave_type: str, leave_period: Optional[str], from_date: date, to_date: date) -> str:
    """Half-day leave covers exactly one date and one half of the office day."""
    period = (leave_period or "").strip() or None
    if leave_type == LeaveType.HALF_DAY:
        if period not in LeavePeriod.HALVES:
            raise HTTPException(
                status_code=422,
                detail="Choose Morning Half (10:00 AM - 1:00 PM) or Afternoon Half (1:00 PM - 6:00 PM) for a half-day leave.",
            )
    period = period or LeavePeriod.FULL_DAY
    if period not in LeavePeriod.ALL:
        raise HTTPException(status_code=422, detail="Pick a valid leave period.")
    if period in LeavePeriod.HALVES and from_date != to_date:
        raise HTTPException(status_code=422, detail="A half-day leave must start and end on the same date.")
    return period


def duration_days(row: LeaveRequest) -> float:
    """Calendar days covered; a half-day period counts as 0.5."""
    if row.leave_period in LeavePeriod.HALVES:
        return 0.5
    return float((row.to_date - row.from_date).days + 1)


def is_paid(row: LeaveRequest) -> bool:
    return row.leave_type not in LeaveType.UNPAID_TYPES


def type_label(value: str) -> str:
    return LeaveType.LABELS.get(value, value)


def period_label(row: LeaveRequest) -> str:
    return f"{row.leave_period} ({PERIOD_HOURS.get(row.leave_period, '')})"


def _conflicts(a_period: str, b_period: str, a_from: date, a_to: date, b_from: date, b_to: date) -> bool:
    """Two leaves conflict unless they are opposite halves of the same single date."""
    if not (a_from <= b_to and a_to >= b_from):
        return False
    if (
        a_period in LeavePeriod.HALVES and b_period in LeavePeriod.HALVES
        and a_period != b_period and a_from == a_to == b_from == b_to
    ):
        return False
    return True


def _overlap_query(db: Session, employee_id: int, from_date: date, to_date: date):
    return (
        db.query(LeaveRequest)
        .filter(
            LeaveRequest.employee_id == employee_id,
            LeaveRequest.status.in_([LeaveStatus.PENDING, LeaveStatus.APPROVED]),
            LeaveRequest.from_date <= to_date,
            LeaveRequest.to_date >= from_date,
        )
    )


def create_request(
    db: Session, employee: Employee, leave_type: str, from_date: date,
    to_date: date, reason: str, actor: User, leave_period: Optional[str] = None,
) -> LeaveRequest:
    leave_type = _validate_type(leave_type)
    reason = (reason or "").strip()
    if not reason:
        raise HTTPException(status_code=422, detail="Please explain why you need leave.")
    if from_date > to_date:
        raise HTTPException(status_code=422, detail="From date cannot be after To date.")
    if employee.employment_status in ("Inactive", "Terminated", "Resigned"):
        raise HTTPException(status_code=409, detail="Leave cannot be requested for an inactive account.")

    period = validate_period(leave_type, leave_period, from_date, to_date)

    overlap = next(
        (
            o for o in _overlap_query(db, employee.id, from_date, to_date).all()
            if _conflicts(period, o.leave_period, from_date, to_date, o.from_date, o.to_date)
        ),
        None,
    )
    if overlap:
        raise HTTPException(
            status_code=409,
            detail=(
                f"You already have a {overlap.status.lower()} leave request covering "
                f"{overlap.from_date.strftime('%d %b %Y')} to {overlap.to_date.strftime('%d %b %Y')}."
            ),
        )

    stage = hierarchy_service.initial_leave_stage(employee)
    row = LeaveRequest(
        employee_id=employee.id,
        leave_type=leave_type,
        from_date=from_date,
        to_date=to_date,
        leave_period=period,
        reason=reason,
        status=LeaveStatus.PENDING,
        approval_stage=stage,
        requested_at=utcnow(),
    )
    db.add(row)
    db.flush()

    audit_service.record(
        db, AuditAction.LEAVE_REQUESTED, user=actor,
        entity_type="leave_request", entity_id=row.id,
        meta={"employee_id": employee.id, "leave_type": leave_type, "leave_period": period,
              "from_date": str(from_date), "to_date": str(to_date)},
    )
    notification_service.create(
        db, user_id=actor.id,
        title="Leave request submitted",
        message=(
            f"Your {type_label(leave_type).lower()} request for {from_date.strftime('%d %b %Y')}"
            + (f" to {to_date.strftime('%d %b %Y')}" if to_date != from_date else "")
            + f" ({period}) is pending {STAGE_WAITING[stage]} review."
        ),
        type_=NotificationType.LEAVE_REQUESTED,
        related_entity="leave_request", related_id=row.id,
        dedupe_key=f"leave:{row.id}:requested", actor=actor,
    )
    _notify_reviewers(db, row, employee, stage, actor)
    return row


STAGE_WAITING = {
    ApprovalStage.MANAGER: "your reporting manager's",
    ApprovalStage.HR: "HR",
    ApprovalStage.ADMIN: "Admin",
    ApprovalStage.CLOSED: "",
}


def _notify_reviewers(db: Session, row: LeaveRequest, employee: Employee, stage: str, actor: User) -> None:
    """Tell whoever acts next (manager, HR or admin) that a request is waiting."""
    for reviewer in hierarchy_service.stage_reviewers(db, employee, stage):
        if reviewer.id == employee.user_id:
            continue
        notification_service.create(
            db, user_id=reviewer.id,
            title="Leave request awaiting your review",
            message=(
                f"{employee.full_name} requested {type_label(row.leave_type).lower()} "
                f"({row.leave_period}) for {row.from_date.strftime('%d %b %Y')}"
                + (f" to {row.to_date.strftime('%d %b %Y')}" if row.to_date != row.from_date else "")
                + "."
            ),
            type_=NotificationType.LEAVE_AWAITING_REVIEW,
            related_entity="leave_request", related_id=row.id,
            dedupe_key=f"leave:{row.id}:{stage.lower()}:{reviewer.id}", actor=actor,
        )


def decide(db: Session, row: LeaveRequest, status_value: str, remarks: Optional[str], actor: User) -> LeaveRequest:
    """Hierarchy-aware decision on a pending request.

    * Reporting Manager at the Manager stage: Approve forwards the request to
      HR (still Pending); Reject closes it.
    * HR (their hierarchy) at the Manager or HR stage, and the Admin at any
      stage: the final decision, through review_request (all existing rules).
    """
    if row.status != LeaveStatus.PENDING:
        raise HTTPException(status_code=409, detail="This leave request has already been reviewed.")
    if not hierarchy_service.can_act_on_leave(db, actor, row):
        raise HTTPException(status_code=403, detail="This leave request is not waiting on you.")
    if hierarchy_service.is_manager(actor):
        return _manager_decision(db, row, status_value, remarks, actor)
    return review_request(db, row, status_value, remarks, actor)


def _manager_decision(db: Session, row: LeaveRequest, status_value: str, remarks: Optional[str], actor: User) -> LeaveRequest:
    if status_value not in (LeaveStatus.APPROVED, LeaveStatus.REJECTED):
        raise HTTPException(status_code=422, detail="Status must be Approved or Rejected.")
    remarks = (remarks or "").strip() or None
    if status_value == LeaveStatus.REJECTED:
        if not remarks:
            raise HTTPException(status_code=422, detail="Please provide a rejection reason.")
        row.manager_status = LeaveStatus.REJECTED
        row.manager_remarks = remarks
        row.manager_reviewed_at = utcnow()
        row.manager_reviewed_by_id = actor.id
        row.approval_stage = ApprovalStage.CLOSED
        return review_request(db, row, LeaveStatus.REJECTED, remarks, actor)

    row.manager_status = LeaveStatus.APPROVED
    row.manager_remarks = remarks
    row.manager_reviewed_at = utcnow()
    row.manager_reviewed_by_id = actor.id
    row.approval_stage = ApprovalStage.HR
    db.flush()
    employee = row.employee
    audit_service.record(
        db, AuditAction.LEAVE_FORWARDED, user=actor, entity_type="leave_request", entity_id=row.id,
        meta={"employee_id": employee.id, "remarks": remarks, "next_stage": ApprovalStage.HR},
    )
    notification_service.create(
        db, user_id=employee.user_id,
        title="Leave request approved by your manager",
        message=(
            f"Your {type_label(row.leave_type).lower()} request for "
            f"{row.from_date.strftime('%d %b %Y')} was approved by your reporting manager "
            "and is now with HR for the final decision."
        ),
        type_=NotificationType.LEAVE_REQUESTED, related_entity="leave_request", related_id=row.id,
        dedupe_key=f"leave:{row.id}:manager-approved", actor=actor,
    )
    _notify_reviewers(db, row, employee, ApprovalStage.HR, actor)
    return row


def review_request(
    db: Session, row: LeaveRequest, status_value: str,
    remarks: Optional[str], actor: User,
) -> LeaveRequest:
    if row.status != LeaveStatus.PENDING:
        raise HTTPException(status_code=409, detail="This leave request has already been reviewed.")
    if status_value not in (LeaveStatus.APPROVED, LeaveStatus.REJECTED):
        raise HTTPException(status_code=422, detail="Status must be Approved or Rejected.")
    remarks = (remarks or "").strip() or None
    if status_value == LeaveStatus.REJECTED and not remarks:
        raise HTTPException(status_code=422, detail="Please provide a rejection reason.")

    if status_value == LeaveStatus.APPROVED:
        overlap = next(
            (
                o for o in db.query(LeaveRequest).filter(
                    LeaveRequest.id != row.id,
                    LeaveRequest.employee_id == row.employee_id,
                    LeaveRequest.status == LeaveStatus.APPROVED,
                    LeaveRequest.from_date <= row.to_date,
                    LeaveRequest.to_date >= row.from_date,
                ).all()
                if _conflicts(row.leave_period, o.leave_period, row.from_date, row.to_date,
                              o.from_date, o.to_date)
            ),
            None,
        )
        if overlap:
            raise HTTPException(status_code=409, detail="This request overlaps an already approved leave.")

    row.status = status_value
    row.approval_stage = ApprovalStage.CLOSED
    row.hr_remarks = remarks
    row.reviewed_at = utcnow()
    row.reviewed_by_id = actor.id
    db.flush()

    employee = row.employee
    action = AuditAction.LEAVE_APPROVED if status_value == LeaveStatus.APPROVED else AuditAction.LEAVE_REJECTED
    audit_service.record(
        db, action, user=actor, entity_type="leave_request", entity_id=row.id,
        meta={"employee_id": employee.id, "status": status_value, "remarks": remarks},
    )
    notification_service.create(
        db, user_id=employee.user_id,
        title=f"Leave request {status_value.lower()}",
        message=(
            f"Your {type_label(row.leave_type).lower()} ({row.leave_period}) from "
            f"{row.from_date.strftime('%d %b %Y')} to "
            f"{row.to_date.strftime('%d %b %Y')} was {status_value.lower()}."
            + (f" {_report_note(row.leave_period)}" if status_value == LeaveStatus.APPROVED else "")
            + (f" HR remarks: {remarks}" if remarks else "")
        ),
        type_=NotificationType.LEAVE_APPROVED if status_value == LeaveStatus.APPROVED else NotificationType.LEAVE_REJECTED,
        related_entity="leave_request", related_id=row.id,
        dedupe_key=f"leave:{row.id}:{status_value.lower()}", actor=actor,
    )
    return row


def _report_note(period: str) -> str:
    return {
        LeavePeriod.FULL_DAY: "Noon and EOD reports are not required on these dates.",
        LeavePeriod.MORNING_HALF: "Noon Report: not required. EOD Report: required.",
        LeavePeriod.AFTERNOON_HALF: "Noon Report: required. EOD Report: not required.",
    }.get(period, "")


def output(row: LeaveRequest) -> dict:
    employee = row.employee
    return {
        "id": row.id,
        "employee_id": row.employee_id,
        "employee_name": employee.full_name if employee else None,
        "employee_code": employee.unique_employee_id or employee.employee_code if employee else None,
        "department": employee.department.name if employee and employee.department else None,
        "internship_background": (
            employee.internship_background.name
            if employee and employee.internship_background else None
        ),
        "leave_type": row.leave_type,
        "leave_type_label": type_label(row.leave_type),
        "leave_period": row.leave_period,
        "leave_period_label": period_label(row),
        "duration_days": duration_days(row),
        "is_paid": is_paid(row),
        "from_date": row.from_date,
        "to_date": row.to_date,
        "reason": row.reason,
        "status": row.status,
        "hr_remarks": row.hr_remarks,
        "requested_at": row.requested_at,
        "reviewed_at": row.reviewed_at,
        "reviewed_by_id": row.reviewed_by_id,
        "reviewed_by_name": row.reviewed_by.display_name if row.reviewed_by else None,
        "approval_stage": row.approval_stage,
        "manager_status": row.manager_status,
        "manager_remarks": row.manager_remarks,
        "manager_reviewed_at": row.manager_reviewed_at,
        "manager_reviewed_by_name": (
            row.manager_reviewed_by.display_name if row.manager_reviewed_by else None
        ),
        "person_type": hierarchy_service.person_type(employee) if employee else None,
        "reporting_manager": (
            employee.reporting_manager.full_name if employee and employee.reporting_manager else None
        ),
    }
