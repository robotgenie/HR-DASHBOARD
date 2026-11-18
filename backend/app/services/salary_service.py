"""Salary calculation and the credit workflow.

Totals are always recomputed on the server from the component rows; the client
never supplies a total. Marking a salary as credited is idempotent: repeating
it will not re-send an email or re-create a notification.
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Iterable, List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.utils.timeutil import utcnow
from app.core.constants import (
    AuditAction, ComponentType, NotificationType, SalaryStatus, SettingKey,
)
from app.models.employee import Employee
from app.models.salary import SalaryRecord
from app.models.salary_component import SalaryComponent
from app.models.user import User
from app.services import audit_service, email_service, notification_service, settings_service
from app.utils.amount_words import format_inr


def recalculate(record: SalaryRecord) -> SalaryRecord:
    """Net pay = sum(earnings) - sum(deductions). Single source of truth."""
    earnings = sum(
        (Decimal(str(c.amount)) for c in record.components
         if c.component_type == ComponentType.EARNING),
        Decimal("0"),
    )
    deductions = sum(
        (Decimal(str(c.amount)) for c in record.components
         if c.component_type == ComponentType.DEDUCTION),
        Decimal("0"),
    )
    record.total_earnings = earnings
    record.total_deductions = deductions
    record.net_pay = earnings - deductions
    return record


def replace_components(
    db: Session, record: SalaryRecord, components: Iterable
) -> SalaryRecord:
    """Swap the component set wholesale, then recompute totals."""
    for existing in list(record.components):
        db.delete(existing)
    record.components.clear()
    db.flush()

    for index, item in enumerate(components):
        data = item if isinstance(item, dict) else item.model_dump()
        ctype = data["component_type"]
        if ctype not in ComponentType.ALL:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Unknown component type '{ctype}'.",
            )
        amount = Decimal(str(data.get("amount") or 0))
        if amount < 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Component amounts can't be negative.",
            )
        record.components.append(
            SalaryComponent(
                component_type=ctype,
                name=data["name"].strip(),
                amount=amount,
                sort_order=data.get("sort_order", index),
            )
        )
    db.flush()
    recalculate(record)
    db.flush()
    return record


def get_or_404(db: Session, salary_id: int) -> SalaryRecord:
    record = db.query(SalaryRecord).filter(SalaryRecord.id == salary_id).first()
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Salary record not found."
        )
    return record


def component_tuples(record: SalaryRecord) -> Tuple[List, List]:
    earnings = [(c.name, Decimal(str(c.amount))) for c in record.earnings]
    deductions = [(c.name, Decimal(str(c.amount))) for c in record.deductions]
    return earnings, deductions


def mark_credited(
    db: Session,
    record: SalaryRecord,
    actor: User,
    credit_date: Optional[date] = None,
    attach_payslip: bool = True,
) -> dict:
    """Credit a salary and fan out notification + email + payslip + audit, once."""
    from app.services import payslip_service  # local import avoids a cycle

    employee: Employee = record.employee
    first_time = record.status != SalaryStatus.CREDITED

    record.status = SalaryStatus.CREDITED
    record.credit_date = credit_date or record.credit_date or date.today()
    if record.credited_at is None:
        record.credited_at = utcnow()
        record.credited_by_id = actor.id
    db.flush()

    if first_time:
        audit_service.record(
            db, AuditAction.SALARY_CREDITED, user=actor, entity_type="salary_record",
            entity_id=record.id,
            meta={
                "employee_id": employee.id,
                "period": record.period_label,
                "net_pay": str(record.net_pay),
            },
        )

    # 1. Make sure a payslip exists so the email/link has something to point at.
    slip = record.slip
    if slip is None and settings_service.get_bool(db, SettingKey.PAYSLIP_AUTO_GENERATE, True):
        slip = payslip_service.generate_and_store(db, record, actor=actor)

    result = {"notification_created": False, "email_sent": False, "payslip_ready": slip is not None}

    # 2. Notification (guarded by dedupe_key AND the timestamp column)
    if record.credit_notified_at is None and settings_service.get_bool(
        db, SettingKey.NOTIFY_ON_SALARY_CREDIT, True
    ):
        created = notification_service.create(
            db,
            user_id=employee.user_id,
            title=f"Salary credited for {record.period_label}",
            message=(
                f"Your salary for {record.period_label} has been credited. "
                f"Net pay {format_inr(record.net_pay)}. Your payslip is available now."
            ),
            type_=NotificationType.SALARY_CREDITED,
            related_entity="salary_record",
            related_id=record.id,
            dedupe_key=f"salary:{record.id}:credited",
            actor=actor,
        )
        if created:
            record.credit_notified_at = utcnow()
            result["notification_created"] = True
            if slip is not None:
                notification_service.create(
                    db,
                    user_id=employee.user_id,
                    title=f"Payslip available - {record.period_label}",
                    message="Your salary slip can now be viewed or downloaded.",
                    type_=NotificationType.SALARY_SLIP_AVAILABLE,
                    related_entity="salary_record",
                    related_id=record.id,
                    dedupe_key=f"salary:{record.id}:slip_available",
                    actor=actor,
                )
        db.flush()

    # 3. Email (its own dedupe key inside email_service)
    if record.credit_email_sent_at is None and settings_service.get_bool(
        db, SettingKey.EMAIL_ENABLED, True
    ):
        attachment = None
        if attach_payslip and slip is not None:
            content = payslip_service.read_slip_bytes(slip)
            if content:
                attachment = (
                    f"Payslip-{employee.employee_code}-{record.period_label.replace(' ', '-')}.pdf",
                    content,
                    "application/pdf",
                )
        log = email_service.send_salary_credited_email(
            db,
            to_email=employee.user.email,
            employee_name=employee.full_name,
            period_label=record.period_label,
            net_pay_display=format_inr(record.net_pay),
            salary_id=record.id,
            payslip=attachment,
            actor=actor,
        )
        if log is not None:
            record.credit_email_sent_at = utcnow()
            result["email_sent"] = True
        db.flush()

    result["payslip_ready"] = record.slip is not None
    return result


def can_download_payslip(record: SalaryRecord, is_hr_user: bool) -> Tuple[bool, str]:
    """Who may download this payslip, and why not when they may not.

    HR always may. A regular employee may once the salary is credited. An intern
    may only when HR has granted permission on this specific salary record --
    viewing stays open to them either way.
    """
    if is_hr_user:
        return True, ""
    if record.status != SalaryStatus.CREDITED:
        return False, "Your payslip becomes available once the salary is credited."
    if record.employee is not None and record.employee.is_intern:
        if not record.intern_download_allowed:
            return False, "Download permission has not been granted by HR."
    return True, ""


def set_intern_download_permission(
    db: Session, record: SalaryRecord, actor: User, allowed: bool
) -> dict:
    """Grant or withdraw an intern's payslip download permission."""
    employee = record.employee
    if employee is None or not employee.is_intern:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "This permission applies to interns only. Other employees can "
                "download their payslip as soon as the salary is credited."
            ),
        )

    already = record.intern_download_allowed is allowed
    record.intern_download_allowed = allowed
    record.download_permission_at = utcnow() if allowed else None
    record.download_permission_by_id = actor.id if allowed else None
    db.flush()

    audit_service.record(
        db,
        AuditAction.INTERN_PAYSLIP_PERMISSION_GRANTED
        if allowed
        else AuditAction.INTERN_PAYSLIP_PERMISSION_REVOKED,
        user=actor, entity_type="salary_record", entity_id=record.id,
        meta={
            "employee_id": employee.id,
            "period": record.period_label,
            "allowed": allowed,
        },
    )

    notified = False
    if allowed and not already and employee.user_id:
        created = notification_service.create(
            db, user_id=employee.user_id,
            title="Payslip download permission granted",
            message=(
                f"HR has granted permission to download your salary slip for "
                f"{record.period_label}."
            ),
            type_=NotificationType.PAYSLIP_DOWNLOAD_GRANTED,
            related_entity="salary_record", related_id=record.id,
            dedupe_key=f"salary:{record.id}:download_permission",
            actor=actor,
        )
        notified = created is not None

    detail = (
        f"Download permission granted for {record.period_label}."
        if allowed
        else f"Download permission withdrawn for {record.period_label}."
    )
    return {
        "salary_id": record.id,
        "employee_id": employee.id,
        "is_intern": True,
        "intern_download_allowed": allowed,
        "notification_created": notified,
        "detail": detail,
    }


PAYABLE_RULE = (
    "Payable = Gross earnings x (Working days - Unpaid leave days) / Working days; "
    "working days are Monday-Friday of the month; a half-day unpaid leave counts as 0.5."
)


def payable_breakdown(record: Optional[SalaryRecord], working_days: int, unpaid_days) -> dict:
    """The company's existing pro-rata rule, in one place.

    This is the formula the previous monthly summary used ("estimated payable
    after unpaid leave"); the monthly report, its PDF and the attendance API all
    call this function so they share one source of truth. The recorded payslip
    (net pay, LOP days) is shown alongside it and is never overwritten.
    """
    unpaid = Decimal(str(unpaid_days or 0))
    working = Decimal(working_days or 0)
    paid_days = max(Decimal("0"), working - unpaid)
    result = {
        "working_days": int(working_days or 0),
        "unpaid_leave_days": float(unpaid),
        "paid_days": float(paid_days),
        "per_day_rate": 0.0,
        "unpaid_leave_deduction": 0.0,
        "estimated_payable": None,
        "estimated_net_payable": None,
        "rule": PAYABLE_RULE,
    }
    if record is None or not working:
        return result
    gross = Decimal(str(record.total_earnings or 0))
    per_day = gross / working
    payable = (gross * paid_days / working).quantize(Decimal("0.01"))
    deductions = Decimal(str(record.total_deductions or 0))
    result.update({
        "per_day_rate": float(per_day.quantize(Decimal("0.01"))),
        "unpaid_leave_deduction": float((gross - payable).quantize(Decimal("0.01"))),
        "estimated_payable": float(payable),
        "estimated_net_payable": float(max(Decimal("0"), payable - deductions).quantize(Decimal("0.01"))),
    })
    return result
