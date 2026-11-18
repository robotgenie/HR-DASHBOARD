"""Daily work reports."""
from datetime import date, datetime
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.utils.timeutil import utcnow
from app.core.constants import AuditAction, ReportStatus, ReportType, SettingKey
from app.models.daily_report import DailyReport
from app.models.employee import Employee
from app.models.user import User
from app.services import attendance_service, audit_service, settings_service
from app.utils.clock import local_now


def assert_report_applicable(db: Session, employee: Employee, report_type: str,
                             on: date, actor: Optional[User] = None) -> dict:
    """Reject a Noon/EOD action that approved leave makes not applicable.

    Enforced on the server for create, draft, submit and attachment upload, so
    hiding a button in the browser is never the only protection.
    """
    plan = attendance_service.day_plan(db, employee, on)
    rule = attendance_service.report_rule_for(plan, report_type)
    if not rule["required"]:
        if actor is not None:
            audit_service.record(
                db, AuditAction.REPORT_NOT_APPLICABLE, user=actor,
                entity_type="employee", entity_id=employee.id,
                meta={"report_type": report_type, "report_date": on.isoformat(),
                      "leave_period": plan["leave_period"]},
                commit=True,
            )
        from app.core.dependencies import ApiRuleError
        raise ApiRuleError(
            403, rule["blocked_reason"], "REPORT_NOT_APPLICABLE",
            {"report_type": report_type, "report_date": on, "leave_period": plan["leave_period"]},
        )
    return plan


def get_for_date(db: Session, employee: Employee, on: date, report_type: str = ReportType.EOD) -> Optional[DailyReport]:
    return (
        db.query(DailyReport)
        .filter(
            DailyReport.employee_id == employee.id,
            DailyReport.report_date == on,
            DailyReport.report_type == report_type,
        )
        .first()
    )


ATTACHMENT_REQUIRED_MESSAGE = (
    "Please upload at least one attachment before submitting your EOD report."
)


NOON_ATTACHMENT_MESSAGE = (
    "Please upload at least one attachment before submitting your Noon Report. "
    "On an approved Afternoon Half leave the Noon Report is your closing report."
)


def attachment_count(report: Optional[DailyReport]) -> int:
    return len(report.attachments) if report is not None else 0


def upsert(
    db: Session, employee: Employee, payload, actor: User, submit: bool = True
) -> DailyReport:
    data = payload if isinstance(payload, dict) else payload.model_dump()
    now = local_now()
    report_date = data.get("report_date") or now.date()
    report_type = str(data.get("report_type") or ReportType.EOD).strip()
    report_type = "EOD" if report_type.upper() == "EOD" else report_type.title()
    if report_type not in ReportType.ALL:
        raise HTTPException(status_code=422, detail="report_type must be Noon or EOD.")
    if report_date > now.date():
        raise HTTPException(status_code=422, detail="Reports can't be filed for a future date.")

    # Approved leave decides which reports exist for the day (drafts included).
    plan = assert_report_applicable(db, employee, report_type, report_date, actor)
    needs_attachment = attendance_service.report_rule_for(plan, report_type).get("attachment_required", False)

    report = get_for_date(db, employee, report_date, report_type)
    if report is None:
        report = DailyReport(employee_id=employee.id, report_date=report_date, report_type=report_type)
        db.add(report)
    elif report.status == ReportStatus.REVIEWED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="HR has already reviewed this report, so it can't be edited.",
        )

    for field in (
        "tasks_completed", "tasks_in_progress", "tasks_pending",
        "work_summary", "challenges", "additional_comments",
    ):
        if field in data:
            report.__setattr__(field, data[field])

    if submit:
        if report_date == now.date():
            if report_type == ReportType.NOON and now.time() < attendance_service.NOON_OPENS:
                raise HTTPException(status_code=422, detail="Noon Report can be submitted only at or after 1:00 PM.")
            if report_type == ReportType.EOD and now.time() < attendance_service.EOD_OPENS:
                raise HTTPException(status_code=422, detail="EOD Report can be submitted only at or after 6:00 PM.")
        if not (report.work_summary or "").strip() and not (report.tasks_completed or "").strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Add what you completed today, or a work summary, before submitting.",
            )
        # EOD reports require proof of work; so does the Noon Report when it is
        # the closing report of the day (approved Afternoon Half leave).
        # Whatever was typed is kept as a draft so nothing the employee wrote is lost.
        if needs_attachment and not attachment_count(report):
            report.status = ReportStatus.DRAFT
            db.flush()
            audit_service.record(
                db, AuditAction.REPORT_ATTACHMENT_MISSING, user=actor,
                entity_type="daily_report", entity_id=report.id,
                meta={
                    "employee_id": employee.id,
                    "report_date": report_date.isoformat(),
                    "kept_as": ReportStatus.DRAFT,
                },
                commit=True,
            )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=ATTACHMENT_REQUIRED_MESSAGE if report_type == ReportType.EOD else NOON_ATTACHMENT_MESSAGE,
            )
        report.status = ReportStatus.SUBMITTED
        report.submitted_at = utcnow()
    else:
        report.status = ReportStatus.DRAFT

    db.flush()

    if submit:
        audit_service.record(
            db, AuditAction.REPORT_SUBMITTED, user=actor, entity_type="daily_report",
            entity_id=report.id,
            meta={"employee_id": employee.id, "report_date": report_date.isoformat()},
        )
    return report


def _is_done(report: Optional[DailyReport], needs_attachment: bool) -> bool:
    if report is None or report.status not in (ReportStatus.SUBMITTED, ReportStatus.REVIEWED):
        return False
    return attachment_count(report) >= 1 if needs_attachment else True


def logout_requirements(db: Session, employee: Employee) -> dict:
    """Which of today's reports apply (after approved leave) and whether they're done.

    FULL DAY LEAVE       -> no reports required, logout allowed
    MORNING HALF LEAVE   -> Noon not required, EOD required
    AFTERNOON HALF LEAVE -> Noon required, EOD not required
    no leave             -> Noon and EOD required
    """
    mandatory = settings_service.get_bool(db, SettingKey.DAILY_REPORT_MANDATORY, True)
    now = local_now()
    today = now.date()
    plan = attendance_service.day_plan(db, employee, today, now)
    noon = get_for_date(db, employee, today, ReportType.NOON)
    eod = get_for_date(db, employee, today, ReportType.EOD)
    noon_needs_file = plan["noon"]["attachment_required"]
    noon_submitted = _is_done(noon, needs_attachment=noon_needs_file)
    eod_submitted = _is_done(eod, needs_attachment=True)
    noon_required = plan["noon"]["required"]
    eod_required = plan["eod"]["required"]

    missing = []
    if noon_required and not noon_submitted:
        missing.append("Noon Report")
    if eod_required and not eod_submitted:
        missing.append("EOD Report")
    valid = not missing
    blocked = mandatory and not valid

    pending_actions = []
    if noon_required and not noon_submitted:
        pending_actions.append(
            "Submit your Noon Report" + (" with a proof-of-work attachment" if noon_needs_file else "")
            + ("" if plan["noon"]["available"]
                                          else f" (opens at {attendance_service.NOON_OPENS.strftime('%I:%M %p').lstrip('0')})")
        )
    if eod_required and not eod_submitted:
        if eod is not None and eod.status in (ReportStatus.SUBMITTED, ReportStatus.REVIEWED):
            pending_actions.append("Attach proof of work to your EOD Report")
        else:
            pending_actions.append(
                "Submit your EOD Report with a proof-of-work attachment"
                + ("" if plan["eod"]["available"]
                   else f" (opens at {attendance_service.EOD_OPENS.strftime('%I:%M %p').lstrip('0')})")
            )

    if plan["leave_period"] == "Full Day":
        status_text = "Full Day Leave - no reports required"
    elif valid:
        status_text = "Submitted" if (noon_required or eod_required) else "Not required"
    else:
        status_text = ", ".join(missing) + " pending"

    submitted_at = None
    for rep, ok in ((eod, eod_submitted), (noon, noon_submitted)):
        if ok and rep is not None:
            submitted_at = rep.submitted_at
            break

    return {
        "date": today,
        "report_mandatory": mandatory,
        "report_submitted_today": valid,
        "report_status": status_text,
        "submitted_at": submitted_at,
        "attachment_count": attachment_count(eod),
        "attachment_required": eod_required,
        "noon_attachment_required": noon_needs_file,
        "noon_attachment_count": attachment_count(noon),
        "noon_source": noon.source if noon else None,
        "logout_blocked": blocked,
        "blocked_message": (
            "You can't check out yet. Pending: " + "; ".join(pending_actions) + "."
            if blocked else None
        ),
        "pending_actions": pending_actions,
        "noon_submitted": noon_submitted,
        "eod_submitted": eod_submitted,
        "noon_required": noon_required,
        "eod_required": eod_required,
        "noon_available": plan["noon"]["available"],
        "eod_available": plan["eod"]["available"],
        "noon_blocked_reason": plan["noon"]["blocked_reason"],
        "eod_blocked_reason": plan["eod"]["blocked_reason"],
        "noon_status": noon.status if noon else None,
        "eod_status": eod.status if eod else None,
        "leave_period": plan["leave_period"],
        "leave_status": plan["leave_status"],
        "expected_login": plan["expected_login"],
        "expected_logout": plan["expected_logout"],
        "missing_reports": missing,
    }



def satisfy_noon_from_hourly(db: Session, employee: Employee, actor: User, now=None) -> Optional[DailyReport]:
    """An hourly update submitted at/after 1:00 PM satisfies today's Noon Report.

    Only when the Noon Report applies today and needs no attachment (on an
    Afternoon Half leave it is the closing report and must be filed with proof).
    The Noon Report row is the existing one - status Submitted, source "Hourly
    Updates" - built from the day's hourly updates so nothing is typed twice.
    A report the employee already submitted is never overwritten.
    """
    from app.models.hourly_update import HourlyUpdate

    now = now or local_now()
    today = now.date()
    if now.time() < attendance_service.NOON_OPENS:
        return None
    plan = attendance_service.day_plan(db, employee, today, now)
    rule = plan["noon"]
    if not rule["required"] or rule["attachment_required"]:
        return None
    report = get_for_date(db, employee, today, ReportType.NOON)
    if report is not None and report.status in (ReportStatus.SUBMITTED, ReportStatus.REVIEWED):
        return None
    updates = (
        db.query(HourlyUpdate)
        .filter(HourlyUpdate.employee_id == employee.id, HourlyUpdate.update_date == today)
        .order_by(HourlyUpdate.slot_index)
        .all()
    )
    if not updates:
        return None

    def line(u):
        task = u.task.title if u.task else "General work"
        return f"{attendance_service.slot_label(u.slot_start.hour, u.slot_end.hour)} [{task}]: {u.work_completed}"

    summary = "\n".join(line(u) for u in updates)
    remaining = "\n".join(f"[{u.task.title if u.task else 'General'}] {u.remaining_work}" for u in updates if u.remaining_work)
    if report is None:
        report = DailyReport(employee_id=employee.id, report_date=today, report_type=ReportType.NOON)
        db.add(report)
    report.work_summary = report.work_summary or summary
    report.tasks_completed = report.tasks_completed or summary
    report.tasks_pending = report.tasks_pending or (remaining or None)
    report.additional_comments = report.additional_comments or "Submitted automatically from hourly work updates."
    report.status = ReportStatus.SUBMITTED
    report.submitted_at = utcnow()
    report.source = "Hourly Updates"
    db.flush()
    audit_service.record(
        db, AuditAction.NOON_REPORT_FROM_HOURLY, user=actor, entity_type="daily_report",
        entity_id=report.id, meta={"employee_id": employee.id, "hourly_updates": len(updates)},
    )
    return report
