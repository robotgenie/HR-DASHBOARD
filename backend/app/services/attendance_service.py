"""Attendance rules in one place: the expected office window for a day, how an
approved leave changes it, which daily reports are required, and the numbers
recorded at login and logout.

Everything that needs to know "is the Noon Report required today?" or "what time
was this person expected in?" calls into this module - the report API, the
logout gate, the login flow, the dashboards and the monthly report - so the
rules cannot drift apart. Approved leave is read live from the database, so an
approval takes effect on the very next request.

Office day (IST):   10:00 AM ---- 1:00 PM ---- 6:00 PM
Morning Half leave:  [ leave ]      [    works    ]   Noon: not required, EOD: required
Afternoon Half leave:[  works ]     [    leave    ]   Noon: required,     EOD: not required
Full Day leave:      [            leave           ]   Noon: not required, EOD: not required
"""
from datetime import date, datetime, time, timedelta
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.constants import (
    HOURLY_SLOTS, AttendanceStatus, AuditAction, LeavePeriod, LeaveStatus, OfficeHours, ReportType,
    RoleName, WorkPeriod,
)
from app.models.employee import Employee
from app.models.leave_request import LeaveRequest
from app.models.user import User
from app.models.work_session import WorkSession
from app.utils.clock import local_combine, local_now, to_local

OFFICE_START = time(*OfficeHours.START)
MIDDAY = time(*OfficeHours.MIDDAY)
OFFICE_END = time(*OfficeHours.END)
NOON_OPENS = time(*OfficeHours.NOON_REPORT_OPENS)
EOD_OPENS = time(*OfficeHours.EOD_REPORT_OPENS)

NOON_BLOCKED_MORNING = "Noon Report is not required because you are on approved Morning Half Leave."
EOD_BLOCKED_AFTERNOON = "EOD Report is not required because you are on approved Afternoon Half Leave."
FULL_DAY_BLOCKED = "You are on approved Full Day Leave. Daily reports are not required."

LEAVE_STATUS_LABEL = {
    LeavePeriod.FULL_DAY: AttendanceStatus.FULL_DAY_LEAVE,
    LeavePeriod.MORNING_HALF: AttendanceStatus.MORNING_HALF_LEAVE,
    LeavePeriod.AFTERNOON_HALF: AttendanceStatus.AFTERNOON_HALF_LEAVE,
}


def fmt_time(value: Optional[time]) -> Optional[str]:
    return value.strftime("%H:%M") if value else None


def fmt_12h(value: Optional[time]) -> Optional[str]:
    return value.strftime("%I:%M %p").lstrip("0") if value else None


def is_working_day(day: date) -> bool:
    """Existing company rule (also used by payroll): Monday-Saturday."""
    return day.weekday() < 6


# --------------------------------------------------------------------- leave
def approved_leaves_on(db: Session, employee_id: int, day: date) -> List[LeaveRequest]:
    return (
        db.query(LeaveRequest)
        .filter(
            LeaveRequest.employee_id == employee_id,
            LeaveRequest.status == LeaveStatus.APPROVED,
            LeaveRequest.from_date <= day,
            LeaveRequest.to_date >= day,
        )
        .order_by(LeaveRequest.id)
        .all()
    )


def combine_periods(periods) -> Optional[str]:
    """Merge the approved periods covering one date into a single period."""
    periods = set(p or LeavePeriod.FULL_DAY for p in periods)
    if not periods:
        return None
    if LeavePeriod.FULL_DAY in periods or periods >= set(LeavePeriod.HALVES):
        return LeavePeriod.FULL_DAY
    return next(iter(periods))


def leave_period_on(db: Session, employee_id: int, day: date) -> (Optional[str], List[LeaveRequest]):
    leaves = approved_leaves_on(db, employee_id, day)
    return combine_periods(l.leave_period for l in leaves), leaves


# ------------------------------------------------------------------ day plan
def _window(leave_period: Optional[str], work_period: Optional[str] = None):
    """Expected (login, logout) for a date, after leave, then half-day working status."""
    if leave_period == LeavePeriod.FULL_DAY:
        return None, None
    if leave_period == LeavePeriod.MORNING_HALF:
        return MIDDAY, OFFICE_END
    if leave_period == LeavePeriod.AFTERNOON_HALF:
        return OFFICE_START, MIDDAY
    if work_period == WorkPeriod.FIRST_HALF:
        return OFFICE_START, MIDDAY
    if work_period == WorkPeriod.SECOND_HALF:
        return MIDDAY, OFFICE_END
    return OFFICE_START, OFFICE_END


def report_rules(leave_period: Optional[str]) -> Dict[str, dict]:
    """Which reports are required for a leave period, and why not when they aren't."""
    noon = {"required": True, "blocked_reason": None, "attachment_required": False}
    eod = {"required": True, "blocked_reason": None, "attachment_required": True}
    if leave_period == LeavePeriod.FULL_DAY:
        noon = {"required": False, "blocked_reason": FULL_DAY_BLOCKED, "attachment_required": False}
        eod = {"required": False, "blocked_reason": FULL_DAY_BLOCKED, "attachment_required": False}
    elif leave_period == LeavePeriod.MORNING_HALF:
        noon = {"required": False, "blocked_reason": NOON_BLOCKED_MORNING, "attachment_required": False}
    elif leave_period == LeavePeriod.AFTERNOON_HALF:
        # The Noon Report is the closing report of the day: it needs the
        # proof-of-work attachment the EOD Report normally carries.
        noon = {"required": True, "blocked_reason": None, "attachment_required": True}
        eod = {"required": False, "blocked_reason": EOD_BLOCKED_AFTERNOON}
    return {ReportType.NOON: noon, ReportType.EOD: eod}


def day_plan(db: Session, employee: Optional[Employee], day: Optional[date] = None,
             now: Optional[datetime] = None) -> dict:
    """Everything the rest of the system needs to know about one employee-day."""
    now = now or local_now()
    day = day or now.date()
    leave_period, leaves = (None, [])
    if employee is not None:
        leave_period, leaves = leave_period_on(db, employee.id, day)
    exp_in, exp_out = _window(leave_period)
    rules = report_rules(leave_period)

    def window(opens: time, rule: dict) -> dict:
        opens_at = local_combine(day, opens)
        available = rule["required"] and (day < now.date() or now >= opens_at)
        if day > now.date():
            available = False
        return {
            "required": rule["required"],
            "blocked_reason": rule["blocked_reason"],
            "available_from": fmt_time(opens),
            "available": available,
            "status_label": "Required" if rule["required"] else "Not Required",
            "attachment_required": rule["required"] and rule.get("attachment_required", False),
        }

    return {
        "date": day,
        "is_working_day": is_working_day(day),
        "leave_period": leave_period,
        "leave_status": LEAVE_STATUS_LABEL.get(leave_period),
        "leaves": [
            {"id": l.id, "leave_type": l.leave_type, "leave_period": l.leave_period}
            for l in leaves
        ],
        "expected_login": fmt_time(exp_in),
        "expected_logout": fmt_time(exp_out),
        "noon": window(NOON_OPENS, rules[ReportType.NOON]),
        "eod": window(EOD_OPENS, rules[ReportType.EOD]),
    }


def report_rule_for(plan: dict, report_type: str) -> dict:
    return plan["noon"] if report_type == ReportType.NOON else plan["eod"]


# -------------------------------------------------------------------- login
def login_context(db: Session, user: User, requested_period: Optional[str],
                  now: Optional[datetime] = None) -> dict:
    """What the login flow must record, and what (if anything) it must still ask for.

    HR accounts are never subject to the late-login rule (the existing HR
    exception); they still check in and out like everyone else. Managers,
    employees and interns follow the late-login rule.
    """
    now = now or local_now()
    today = now.date()
    employee = user.employee
    is_hr = user.role_name == RoleName.HR_ADMIN
    leave_period = None
    if employee is not None:
        leave_period, _ = leave_period_on(db, employee.id, today)

    already_in_today = (
        db.query(WorkSession.id)
        .filter(WorkSession.user_id == user.id, WorkSession.work_date == today)
        .first()
        is not None
    )

    # Approved leave decides the working half; otherwise the employee chooses.
    if leave_period == LeavePeriod.MORNING_HALF:
        options = [WorkPeriod.SECOND_HALF]
    elif leave_period == LeavePeriod.AFTERNOON_HALF:
        options = [WorkPeriod.FIRST_HALF]
    elif leave_period == LeavePeriod.FULL_DAY:
        options = [WorkPeriod.FULL_DAY]
    elif now.time() >= MIDDAY:
        options = [WorkPeriod.SECOND_HALF]
    else:
        options = [WorkPeriod.FULL_DAY, WorkPeriod.FIRST_HALF]

    def late_for(period: str) -> int:
        if is_hr or already_in_today or leave_period == LeavePeriod.FULL_DAY:
            return 0
        exp_in, _ = _window(leave_period, period)
        if exp_in is None:
            return 0
        delta = (now - local_combine(today, exp_in)).total_seconds()
        return max(0, int(delta // 60))

    if is_hr:
        period = requested_period if requested_period in WorkPeriod.ALL else WorkPeriod.FULL_DAY
    elif leave_period is not None:
        period = options[0]                      # decided by the approved leave
    elif requested_period in options:
        period = requested_period
    elif requested_period in (None, "") and WorkPeriod.FULL_DAY in options:
        period = WorkPeriod.FULL_DAY             # normal morning login
    else:
        period = None                            # afternoon login: must confirm Second Half

    exp_in, exp_out = _window(leave_period, period or WorkPeriod.FULL_DAY)
    return {
        "is_hr": is_hr,
        "date": today,
        "actual_login": now.strftime("%H:%M"),
        "leave_period": leave_period,
        "work_period": period,
        "work_period_options": options,
        "late_by_period": {p: late_for(p) for p in options},
        "late_minutes": late_for(period) if period else 0,
        "expected_login": exp_in,
        "expected_logout": exp_out,
        "first_session_today": not already_in_today,
    }


def initial_status(ctx: dict) -> str:
    if ctx["leave_period"]:
        return LEAVE_STATUS_LABEL[ctx["leave_period"]]
    if ctx["late_minutes"]:
        return "Late Login"
    if ctx["work_period"] in (WorkPeriod.FIRST_HALF, WorkPeriod.SECOND_HALF):
        return ctx["work_period"]
    return "Present"


# ------------------------------------------------------------------- logout
def refresh_window(db: Session, session_row: WorkSession, employee: Optional[Employee]) -> None:
    """Re-apply the approved leave for the session's date.

    A leave approved after the employee logged in must still decide the
    expected logout (e.g. 1:00 PM for an Afternoon Half leave) - approval takes
    effect immediately, not from the next login.
    """
    if employee is None:
        return
    period, _ = leave_period_on(db, employee.id, session_row.work_date)
    if period == session_row.leave_period and session_row.expected_logout_time is not None:
        return
    session_row.leave_period = period
    exp_in, exp_out = _window(period, session_row.work_period)
    session_row.expected_logout_time = exp_out
    if session_row.expected_login_time is None:
        session_row.expected_login_time = exp_in
    if period:
        session_row.attendance_status = LEAVE_STATUS_LABEL[period]
        if period == LeavePeriod.MORNING_HALF:
            session_row.work_period = WorkPeriod.SECOND_HALF
        elif period == LeavePeriod.AFTERNOON_HALF:
            session_row.work_period = WorkPeriod.FIRST_HALF


def close_session(session_row: WorkSession, logout_utc_naive: datetime) -> WorkSession:
    """Record logout: duration, and extra/early time against the expected logout.

    Extra Working Hours = Actual Logout - Expected Logout (6:00 PM normally,
    1:00 PM on an approved Afternoon Half leave or a First Half working day).
    """
    session_row.logout_at = logout_utc_naive
    logout_local = to_local(logout_utc_naive)
    login_local = to_local(session_row.login_at)
    session_row.work_duration_minutes = max(
        0, int((logout_local - login_local).total_seconds() // 60)
    )
    expected_out = session_row.expected_logout_time
    if expected_out is None and session_row.leave_period != LeavePeriod.FULL_DAY:
        expected_out = OFFICE_END
    session_row.extra_work_minutes = 0
    session_row.early_logout_minutes = 0
    if expected_out is not None:
        expected_dt = local_combine(session_row.work_date, expected_out)
        diff = int((logout_local - expected_dt).total_seconds() // 60)
        if diff > 0:
            session_row.extra_work_minutes = diff
            session_row.attendance_status = "Extended Work"
        elif diff < 0 and not session_row.leave_period:
            session_row.early_logout_minutes = -diff
            if session_row.attendance_status in ("Present", "Late Login"):
                session_row.attendance_status = "Early Logout"
    return session_row


def minutes_label(value: Optional[int]) -> str:
    value = int(value or 0)
    hours, mins = divmod(value, 60)
    if hours and mins:
        return f"{hours}h {mins}m"
    if hours:
        return f"{hours}h"
    return f"{mins}m"


# -------------------------------------------------------------- check-in/out
# HR, Managers, employees and interns all check in. Only the Admin (not an
# employee, no employee record) does not.
CHECK_IN_ROLE_ERROR = "Check-In and Check-Out are for employee accounts. The Admin does not check in."


def today_session(db: Session, user_id: int, day: date) -> Optional[WorkSession]:
    """The attendance (check-in) record of a user for a date, newest first."""
    return (
        db.query(WorkSession)
        .filter(WorkSession.user_id == user_id, WorkSession.work_date == day)
        .order_by(WorkSession.login_at.desc())
        .first()
    )


def _validate_location(latitude, longitude, event: str):
    from app.core.dependencies import ApiRuleError
    try:
        lat = float(latitude)
        lng = float(longitude)
    except (TypeError, ValueError):
        raise ApiRuleError(
            422,
            f"Your location is required to {event}. Allow location access in the browser and try again.",
            "LOCATION_REQUIRED",
        )
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        raise ApiRuleError(422, "The location received is not valid. Please try again.", "LOCATION_REQUIRED")
    return round(lat, 6), round(lng, 6)


def check_in_blocker(db: Session, user: User, employee: Optional[Employee], now: datetime) -> Optional[dict]:
    """Why Check-In is not possible right now (None when it is)."""
    if user.role_name == RoleName.ADMIN or employee is None:
        return {"code": "CHECK_IN_NOT_ALLOWED", "message": CHECK_IN_ROLE_ERROR, "status": 403}
    existing = today_session(db, user.id, now.date())
    if existing is not None:
        if existing.logout_at is None:
            t = to_local(existing.login_at).strftime("%I:%M %p").lstrip("0")
            return {"code": "ALREADY_CHECKED_IN", "message": f"You are already checked in (since {t}).", "status": 409}
        return {"code": "ALREADY_CHECKED_OUT", "message": "You have already checked out for today.", "status": 409}
    period, _ = leave_period_on(db, employee.id, now.date())
    if period == LeavePeriod.FULL_DAY:
        return {"code": "ON_LEAVE", "message": "You are on approved Full Day Leave today. Check-In is not required.", "status": 409}
    if period == LeavePeriod.AFTERNOON_HALF and now.time() >= MIDDAY:
        return {"code": "ON_LEAVE", "message": "Your approved Afternoon Half Leave (1:00 PM - 6:00 PM) has started. Check-In is closed for today.", "status": 409}
    if now.time() >= OFFICE_END:
        return {"code": "DAY_OVER", "message": "Working hours (10:00 AM - 6:00 PM) are over for today. Check-In is closed.", "status": 409}
    return None


def check_in(db: Session, user: User, *, selfie_data: Optional[str], latitude, longitude,
             accuracy: Optional[float] = None, location_label: Optional[str] = None,
             late_login_reason: Optional[str] = None, work_period: Optional[str] = None,
             ip: Optional[str] = None, user_agent: Optional[str] = None) -> WorkSession:
    """Start the working day: late-login rule -> location -> live selfie -> session.

    Nothing is stored unless every required piece is present, so a Check-In is
    never half-recorded.
    """
    from app.core.dependencies import ApiRuleError
    from app.services import audit_service, file_service
    from app.utils.timeutil import utcnow

    now = local_now()
    employee = user.employee
    blocker = check_in_blocker(db, user, employee, now)
    if blocker:
        raise ApiRuleError(blocker["status"], blocker["message"], blocker["code"])

    work_period = (work_period or "").strip() or None
    if work_period and work_period not in WorkPeriod.ALL:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="Choose a valid work period.")
    ctx = login_context(db, user, work_period, now)
    reason = (late_login_reason or "").strip()
    context = public_context(ctx)
    if ctx["work_period"] is None:
        raise ApiRuleError(
            428, "It is past 1:00 PM, so today is recorded as Second Half. Please confirm your work period.",
            "WORK_PERIOD_REQUIRED", context,
        )
    if ctx["late_minutes"] > 0 and not reason:
        raise ApiRuleError(
            428,
            f"You are checking in {minutes_label(ctx['late_minutes'])} late "
            f"(expected {fmt_12h(ctx['expected_login'])}). Please provide a reason for your late login.",
            "LATE_LOGIN_REASON_REQUIRED", context,
        )
    lat, lng = _validate_location(latitude, longitude, "check in")
    if not selfie_data:
        raise ApiRuleError(428, "A live selfie is required to check in.", "SELFIE_REQUIRED", context)
    selfie_path = file_service.save_selfie_data_url(selfie_data, f"checkin_user_{user.id}")

    stamp = utcnow()
    user.last_login_at = user.last_login_at or stamp
    row = WorkSession(
        user_id=user.id, login_at=stamp, work_date=ctx["date"],
        work_period=ctx["work_period"] or WorkPeriod.FULL_DAY,
        expected_login_time=ctx["expected_login"], expected_logout_time=ctx["expected_logout"],
        leave_period=ctx["leave_period"], late_login_minutes=ctx["late_minutes"],
        late_login_reason=(reason or None) if ctx["late_minutes"] else None,
        attendance_status=initial_status(ctx), ip_address=ip, user_agent=user_agent,
        login_selfie_path=selfie_path,
        check_in_latitude=lat, check_in_longitude=lng,
        check_in_accuracy_m=float(accuracy) if accuracy is not None else None,
        check_in_location=(location_label or "").strip()[:255] or None,
    )
    db.add(row)
    db.flush()
    audit_service.record(
        db, AuditAction.CHECK_IN, user=user, entity_type="work_session", entity_id=row.id,
        ip_address=ip, user_agent=user_agent,
        meta={"late_minutes": ctx["late_minutes"], "latitude": lat, "longitude": lng,
              "leave_period": ctx["leave_period"], "work_period": row.work_period},
    )
    return row


def check_out(db: Session, user: User, *, selfie_data: Optional[str], latitude, longitude,
              accuracy: Optional[float] = None, location_label: Optional[str] = None,
              reason: Optional[str] = None, ip: Optional[str] = None,
              user_agent: Optional[str] = None) -> WorkSession:
    """End the working day: report/leave rules first, then location and live selfie."""
    from app.core.dependencies import ApiRuleError
    from app.services import audit_service, file_service, report_service
    from app.utils.timeutil import utcnow

    now = local_now()
    employee = user.employee
    if user.role_name == RoleName.ADMIN or employee is None:
        raise ApiRuleError(403, CHECK_IN_ROLE_ERROR, "CHECK_IN_NOT_ALLOWED")
    row = today_session(db, user.id, now.date())
    if row is None:
        raise ApiRuleError(409, "You haven't checked in today.", "NOT_CHECKED_IN")
    if row.logout_at is not None:
        raise ApiRuleError(409, "You have already checked out for today.", "ALREADY_CHECKED_OUT")

    gate = report_service.logout_requirements(db, employee)
    if gate["logout_blocked"]:
        audit_service.record(
            db, AuditAction.CHECK_OUT_BLOCKED, user=user, entity_type="work_session",
            entity_id=row.id, ip_address=ip, user_agent=user_agent,
            meta={"pending": gate["missing_reports"]}, commit=True,
        )
        raise ApiRuleError(409, gate["blocked_message"], "CHECKOUT_BLOCKED", gate)

    lat, lng = _validate_location(latitude, longitude, "check out")
    if not selfie_data:
        raise ApiRuleError(428, "A live selfie is required to check out.", "SELFIE_REQUIRED")
    selfie_path = file_service.save_selfie_data_url(selfie_data, f"checkout_user_{user.id}")

    stamp = utcnow()
    refresh_window(db, row, employee)
    close_session(row, stamp)
    row.logout_selfie_path = selfie_path
    row.check_out_latitude, row.check_out_longitude = lat, lng
    row.check_out_accuracy_m = float(accuracy) if accuracy is not None else None
    row.check_out_location = (location_label or "").strip()[:255] or None
    row.logout_reason = (reason or "").strip() or None
    db.flush()
    audit_service.record(
        db, AuditAction.CHECK_OUT, user=user, entity_type="work_session", entity_id=row.id,
        ip_address=ip, user_agent=user_agent,
        meta={"extra_minutes": row.extra_work_minutes, "latitude": lat, "longitude": lng},
    )
    return row


def public_context(ctx: dict) -> dict:
    return {
        "date": ctx["date"],
        "actual_login": ctx["actual_login"],
        "expected_login": fmt_time(ctx["expected_login"]),
        "late_minutes": ctx["late_minutes"],
        "leave_period": ctx["leave_period"],
        "work_period": ctx["work_period"],
        "work_period_options": ctx["work_period_options"],
        "late_by_period": ctx["late_by_period"],
    }


def session_out(row: Optional[WorkSession]) -> Optional[dict]:
    if row is None:
        return None
    cin, cout = to_local(row.login_at), to_local(row.logout_at)
    now = local_now()
    worked = row.work_duration_minutes if row.logout_at else max(0, int((now - cin).total_seconds() // 60))
    return {
        "id": row.id,
        "date": row.work_date,
        "check_in_at": cin.isoformat() if cin else None,
        "check_in_time": cin.strftime("%H:%M") if cin else None,
        "check_out_at": cout.isoformat() if cout else None,
        "check_out_time": cout.strftime("%H:%M") if cout else None,
        "checked_out": row.logout_at is not None,
        "work_period": row.work_period,
        "leave_period": row.leave_period,
        "expected_login": fmt_time(row.expected_login_time),
        "expected_logout": fmt_time(row.expected_logout_time),
        "late_minutes": row.late_login_minutes,
        "late_label": minutes_label(row.late_login_minutes) if row.late_login_minutes else None,
        "late_reason": row.late_login_reason,
        "worked_minutes": worked,
        "extra_minutes": row.extra_work_minutes,
        "attendance_status": row.attendance_status,
        "check_in_selfie": bool(row.login_selfie_path),
        "check_out_selfie": bool(row.logout_selfie_path),
        "check_in_location": _loc(row.check_in_latitude, row.check_in_longitude, row.check_in_accuracy_m, row.check_in_location),
        "check_out_location": _loc(row.check_out_latitude, row.check_out_longitude, row.check_out_accuracy_m, row.check_out_location),
    }


def _loc(lat, lng, acc, label) -> Optional[dict]:
    if lat is None or lng is None:
        return None
    lat, lng = float(lat), float(lng)
    return {
        "latitude": lat, "longitude": lng,
        "accuracy_m": round(acc) if acc is not None else None,
        "label": label or f"{lat:.5f}, {lng:.5f}",
        "map_url": f"https://www.google.com/maps?q={lat:.6f},{lng:.6f}",
    }


# ------------------------------------------------------------ hourly periods
def slot_label(h1: int, h2: int) -> str:
    def f(h):
        return f"{(h % 12) or 12}:00 {'PM' if h >= 12 else 'AM'}"
    return f"{f(h1)} - {f(h2)}"


def hourly_slots(db: Session, employee: Employee, session_row: Optional[WorkSession],
                 day: Optional[date] = None, now: Optional[datetime] = None) -> List[dict]:
    """Status of each 10-11 ... 5-6 period for one employee-day.

    Eligibility = approved leave (live) + working period (First/Second Half)
    + check-in/check-out times. Submitted, Open (current hour), Due (hour over,
    not yet submitted), Upcoming, Missed, Not Applicable.
    """
    from app.models.hourly_update import HourlyUpdate

    now = now or local_now()
    day = day or now.date()
    leave_period, _ = leave_period_on(db, employee.id, day)
    work_period = session_row.work_period if session_row is not None else None
    exp_in, exp_out = _window(leave_period, work_period)
    done = {
        u.slot_index: u for u in db.query(HourlyUpdate).filter(
            HourlyUpdate.employee_id == employee.id, HourlyUpdate.update_date == day
        )
    }
    cin = to_local(session_row.login_at) if session_row is not None else None
    cout = to_local(session_row.logout_at) if session_row is not None and session_row.logout_at else None
    leave_msg = {
        LeavePeriod.FULL_DAY: "Approved Full Day Leave",
        LeavePeriod.MORNING_HALF: "Approved Morning Half Leave (10:00 AM - 1:00 PM)",
        LeavePeriod.AFTERNOON_HALF: "Approved Afternoon Half Leave (1:00 PM - 6:00 PM)",
    }
    out = []
    for index, (h1, h2) in enumerate(HOURLY_SLOTS):
        start, end = local_combine(day, time(h1)), local_combine(day, time(h2))
        update = done.get(index)
        reason = None
        if update is not None:
            status = "Submitted"
        elif leave_period == LeavePeriod.FULL_DAY:
            status, reason = "Not Applicable", leave_msg[leave_period]
        elif exp_in is None or start < local_combine(day, exp_in) or end > local_combine(day, exp_out):
            status = "Not Applicable"
            reason = leave_msg.get(leave_period) or f"Outside your {work_period} working period"
        elif session_row is None:
            status = "Not Checked In" if day >= now.date() else "Missed"
        elif end <= cin:
            status, reason = "Not Applicable", "Before your check-in"
        elif cout is not None and start >= cout:
            status, reason = "Not Applicable", "After your check-out"
        elif now < start:
            status = "Upcoming"
        elif now < end - timedelta(minutes=5):
            status = "Open"
        elif cout is not None or day < now.date():
            status = "Missed"
        else:
            status = "Due"
        out.append({
            "slot_index": index,
            "start": f"{h1:02d}:00",
            "end": f"{h2:02d}:00",
            "label": slot_label(h1, h2),
            "status": status,
            "reason": reason,
            "can_submit": status in ("Open", "Due") and day == now.date(),
            "update_id": update.id if update is not None else None,
        })
    return out
