"""Automatic monthly salary slips.

Every month each applicable employee gets the next salary record created for
them automatically, copied from their most recent month:

* same employee, same earning/deduction lines and amounts (HR/Admin then edit
  only the payment amounts on that existing record before crediting it);
* working days = the Monday-Friday days of the new month (the existing payroll rule);
* status Pending, ``auto_generated = True``, ``generated_from_id`` = the source month.

Applicable employees: employment status Active or On Leave, an active login,
joined on or before the end of the month, and an earlier salary record no
more than SALARY_AUTOGEN_MAX_BACKFILL_MONTHS months back (the very first
salary, or one after a long pause, is still created by HR, as before).

Never creates a duplicate: the database already enforces one record per
employee + month + year (``uq_salary_employee_period``); each insert runs in a
savepoint and an existing month is simply skipped. Never creates future months:
generation stops at the current month.

Triggers (all call ``run``):
* the background loop started by the API process (app.main lifespan);
* ``python generate_monthly_salaries.py`` for an OS scheduler (cron / Task Scheduler);
* ``POST /api/salaries/auto-generate`` for HR/Admin ("Generate now").
"""
import asyncio
import logging
from calendar import monthrange
from collections import defaultdict
from datetime import date
from typing import Dict, Iterable, List, Optional, Tuple

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import (
    AuditAction, EmploymentStatus, NotificationType, SalaryStatus, SettingKey,
)
from app.models.employee import Employee
from app.models.salary import MONTH_NAMES, SalaryRecord
from app.models.salary_component import SalaryComponent
from app.models.user import User
from app.services import audit_service, hierarchy_service, notification_service, settings_service
from app.services.attendance_service import is_working_day
from app.utils.clock import local_today

logger = logging.getLogger("rocketgenie.salary_autogen")

ELIGIBLE_STATUSES = (EmploymentStatus.ACTIVE, EmploymentStatus.ON_LEAVE)


def _index(year: int, month: int) -> int:
    return year * 12 + (month - 1)


def _period(index: int) -> Tuple[int, int]:
    return index // 12, index % 12 + 1


def working_days_in(year: int, month: int) -> int:
    return sum(1 for d in range(1, monthrange(year, month)[1] + 1) if is_working_day(date(year, month, d)))


def label(year: int, month: int) -> str:
    return f"{MONTH_NAMES[month - 1]} {year}"


def is_enabled(db: Session) -> bool:
    return settings_service.get_bool(db, SettingKey.SALARY_AUTO_GENERATE, True)


def _copy(db: Session, source: SalaryRecord, year: int, month: int, actor: Optional[User]) -> Optional[SalaryRecord]:
    """Insert one month copied from ``source``; None if that month already exists."""
    record = SalaryRecord(
        employee_id=source.employee_id,
        period_year=year,
        period_month=month,
        working_days=working_days_in(year, month),
        lop_days=0,
        status=SalaryStatus.PENDING,
        remarks=f"Generated automatically from {source.period_label}. Update the payment amounts before crediting.",
        auto_generated=True,
        generated_from_id=source.id,
        created_by_id=actor.id if actor else None,
    )
    for i, c in enumerate(source.components):
        record.components.append(SalaryComponent(
            component_type=c.component_type, name=c.name, amount=c.amount,
            sort_order=c.sort_order if c.sort_order is not None else i,
        ))
    record.total_earnings = source.total_earnings
    record.total_deductions = source.total_deductions
    record.net_pay = source.net_pay

    savepoint = db.begin_nested()
    try:
        db.add(record)
        db.flush()
    except IntegrityError:
        savepoint.rollback()
        return None
    savepoint.commit()
    from app.services import salary_service
    salary_service.recalculate(record)
    db.flush()
    return record


def run(
    db: Session,
    actor: Optional[User] = None,
    up_to: Optional[Tuple[int, int]] = None,
    employee_ids: Optional[Iterable[int]] = None,
) -> Dict:
    """Create every missing month up to ``up_to`` (default: the current month).

    ``employee_ids`` limits the run (used to keep an HR inside their hierarchy).
    Returns a summary; the caller commits.
    """
    today = local_today()
    target_year, target_month = up_to or (today.year, today.month)
    target = _index(target_year, target_month)
    month_end = date(target_year, target_month, monthrange(target_year, target_month)[1])
    max_backfill = max(1, int(settings.SALARY_AUTOGEN_MAX_BACKFILL_MONTHS or 1))

    q = (
        db.query(Employee)
        .join(User, User.id == Employee.user_id)
        .filter(Employee.employment_status.in_(ELIGIBLE_STATUSES), User.is_active.is_(True),
                Employee.joining_date <= month_end)
    )
    if employee_ids is not None:
        ids = list(employee_ids)
        if not ids:
            return {"period": label(target_year, target_month), "created": 0, "skipped_existing": 0,
                    "skipped_no_previous": 0, "skipped_stale": 0, "records": []}
        q = q.filter(Employee.id.in_(ids))
    employees = q.all()

    created: List[SalaryRecord] = []
    skipped_existing = 0
    skipped_no_previous = 0
    skipped_stale = 0
    for employee in employees:
        latest = (
            db.query(SalaryRecord)
            .filter(SalaryRecord.employee_id == employee.id,
                    (SalaryRecord.period_year * 12 + SalaryRecord.period_month - 1) <= target)
            .order_by(SalaryRecord.period_year.desc(), SalaryRecord.period_month.desc())
            .first()
        )
        if latest is None:
            skipped_no_previous += 1
            continue
        last = _index(latest.period_year, latest.period_month)
        if last >= target:
            skipped_existing += 1
            continue
        if target - last > max_backfill:
            # Salary not run for a long time (e.g. paused): leave it to HR
            # rather than filling a long series of past months.
            skipped_stale += 1
            continue
        joined = _index(employee.joining_date.year, employee.joining_date.month)
        source = latest
        for idx in range(max(last + 1, joined), target + 1):
            year, month = _period(idx)
            record = _copy(db, source, year, month, actor)
            if record is None:
                skipped_existing += 1
                source = (db.query(SalaryRecord)
                          .filter_by(employee_id=employee.id, period_year=year, period_month=month).first()
                          or source)
                continue
            created.append(record)
            source = record
            audit_service.record(
                db, AuditAction.SALARY_AUTO_GENERATED, user=actor, entity_type="salary_record",
                entity_id=record.id,
                meta={"employee_id": employee.id, "period": record.period_label,
                      "from_salary_id": record.generated_from_id, "net_pay": str(record.net_pay),
                      "trigger": "manual" if actor else "scheduler"},
            )

    _notify_reviewers(db, created, actor)
    db.flush()
    summary = {
        "period": label(target_year, target_month),
        "created": len(created),
        "skipped_existing": skipped_existing,
        "skipped_no_previous": skipped_no_previous,
        "skipped_stale": skipped_stale,
        "records": [{"id": r.id, "employee_id": r.employee_id, "period_label": r.period_label} for r in created],
    }
    if created:
        logger.info("Salary auto-generation: %s record(s) created (up to %s)", len(created), summary["period"])
    return summary


def _notify_reviewers(db: Session, created: List[SalaryRecord], actor: Optional[User]) -> None:
    """One summary per HR/Admin responsible, so they can review the amounts."""
    by_reviewer: Dict[int, List[SalaryRecord]] = defaultdict(list)
    for record in created:
        for reviewer in hierarchy_service.oversight_users(db, record.employee):
            if actor is not None and reviewer.id == actor.id:
                continue
            by_reviewer[reviewer.id].append(record)
    for reviewer_id, records in by_reviewer.items():
        periods = sorted({r.period_label for r in records})
        notification_service.create(
            db, user_id=reviewer_id,
            title="Salary slips generated",
            message=(f"{len(records)} salary slip(s) for {', '.join(periods)} were created automatically "
                     "from the previous month. Review the payment amounts before crediting."),
            type_=NotificationType.SALARY_SLIP_GENERATED, related_entity="salary_record",
            related_id=records[0].id,
            dedupe_key=f"salary-autogen:{reviewer_id}:{min(r.id for r in records)}",
            actor=actor,
        )


# ------------------------------------------------------------- scheduler
def run_scheduled() -> Optional[Dict]:
    """One unattended pass with its own session (scheduler / CLI)."""
    from app.database.database import SessionLocal

    db = SessionLocal()
    try:
        if not is_enabled(db):
            return None
        summary = run(db)
        db.commit()
        return summary
    except Exception:  # never let the loop die
        db.rollback()
        logger.exception("Salary auto-generation failed")
        return None
    finally:
        db.close()


async def scheduler_loop(interval_minutes: int) -> None:
    """Runs at start-up and then every ``interval_minutes``.

    Idempotent, so several API workers (or the CLI on cron as well) can run it
    side by side: the unique constraint means each month is created once.
    """
    interval = max(1, int(interval_minutes)) * 60
    while True:
        await asyncio.to_thread(run_scheduled)
        await asyncio.sleep(interval)
