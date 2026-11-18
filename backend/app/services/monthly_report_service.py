"""Monthly employee report: attendance + leave + login/logout + daily reports +
working hours + salary, calculated from the stored records for one month.

Nothing here is typed in or hard-coded: every figure is derived from
work_sessions, leave_requests, daily_reports and salary_records. The same
builder feeds the on-screen report (HR and employee/intern), the PDF download
and the HR per-employee summary, so they always agree.
"""
import io
from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.core.constants import (
    AttendanceStatus, LeavePeriod, LeaveStatus, ReportStatus, ReportType, WorkPeriod,
)
from app.models.daily_report import DailyReport
from app.models.employee import Employee
from app.models.leave_request import LeaveRequest
from app.models.salary import MONTH_NAMES, SalaryRecord
from app.models.work_session import WorkSession
from app.services import attendance_service, leave_service, salary_service, settings_service
from app.utils.clock import local_now, to_local

SUBMITTED = (ReportStatus.SUBMITTED, ReportStatus.REVIEWED)


def parse_month(month: Optional[str]) -> (int, int):
    now = local_now()
    if not month:
        return now.year, now.month
    try:
        year, mon = (int(x) for x in str(month).split("-")[:2])
        date(year, mon, 1)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="month must look like YYYY-MM.")
    return year, mon


def period_label(year: int, month: int) -> str:
    return f"{MONTH_NAMES[month - 1]} {year}"


def available_months(db: Session, employee: Employee) -> List[dict]:
    """Every month from the employee's first record (or joining) up to this month."""
    now = local_now().date()
    starts = [employee.joining_date] if employee.joining_date else []
    first_session = (
        db.query(WorkSession.work_date)
        .filter(WorkSession.user_id == employee.user_id)
        .order_by(WorkSession.work_date)
        .first()
    )
    if first_session:
        starts.append(first_session[0])
    first_leave = (
        db.query(LeaveRequest.from_date)
        .filter(LeaveRequest.employee_id == employee.id)
        .order_by(LeaveRequest.from_date)
        .first()
    )
    if first_leave:
        starts.append(first_leave[0])
    first_salary = (
        db.query(SalaryRecord.period_year, SalaryRecord.period_month)
        .filter(SalaryRecord.employee_id == employee.id)
        .order_by(SalaryRecord.period_year, SalaryRecord.period_month)
        .first()
    )
    if first_salary:
        starts.append(date(first_salary[0], first_salary[1], 1))
    start = min(starts) if starts else now
    start = min(start, now)
    months = []
    y, m = now.year, now.month
    while (y, m) >= (start.year, start.month):
        months.append({
            "period": f"{y:04d}-{m:02d}",
            "label": period_label(y, m),
            "is_current": (y, m) == (now.year, now.month),
        })
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        if len(months) >= 60:
            break
    return months


def _fmt_local_time(value) -> Optional[str]:
    local = to_local(value)
    return local.strftime("%H:%M") if local else None


def _report_state(report: Optional[DailyReport], required: bool, day: date, today: date,
                  opens_passed: bool, is_eod: bool) -> str:
    if not required:
        return "Not Required"
    if report is not None and report.status in SUBMITTED:
        if is_eod and not report.attachments:
            return "No Attachment"
        return report.status
    if report is not None and report.status == ReportStatus.DRAFT:
        return "Draft"
    if day > today or (day == today and not opens_passed):
        return "Upcoming"
    if day == today:
        return "Pending"
    return "Missing"


def build(db: Session, employee: Employee, month: Optional[str] = None) -> dict:
    year, mon = parse_month(month)
    first = date(year, mon, 1)
    last = date(year, mon, monthrange(year, mon)[1])
    now = local_now()
    today = now.date()
    cutoff = min(last, today)

    sessions = (
        db.query(WorkSession)
        .filter(
            WorkSession.user_id == employee.user_id,
            WorkSession.work_date >= first,
            WorkSession.work_date <= last,
        )
        .order_by(WorkSession.login_at)
        .all()
    )
    leaves = (
        db.query(LeaveRequest)
        .options(joinedload(LeaveRequest.reviewed_by))
        .filter(
            LeaveRequest.employee_id == employee.id,
            LeaveRequest.from_date <= last,
            LeaveRequest.to_date >= first,
        )
        .order_by(LeaveRequest.from_date, LeaveRequest.id)
        .all()
    )
    reports = (
        db.query(DailyReport)
        .options(joinedload(DailyReport.attachments))
        .filter(
            DailyReport.employee_id == employee.id,
            DailyReport.report_date >= first,
            DailyReport.report_date <= last,
        )
        .all()
    )
    salary = (
        db.query(SalaryRecord)
        .options(joinedload(SalaryRecord.components))
        .filter(
            SalaryRecord.employee_id == employee.id,
            SalaryRecord.period_year == year,
            SalaryRecord.period_month == mon,
        )
        .first()
    )

    sessions_by_day: Dict[date, List[WorkSession]] = {}
    for s in sessions:
        sessions_by_day.setdefault(s.work_date, []).append(s)
    reports_by_key = {(r.report_date, r.report_type): r for r in reports}
    approved = [l for l in leaves if l.status == LeaveStatus.APPROVED]

    counts = {
        "full_day_attendance": 0, "first_half_attendance": 0, "second_half_attendance": 0,
        "full_day_leave": 0, "morning_half_leave": 0, "afternoon_half_leave": 0,
        "absent_days": 0,
    }
    unpaid_leave_days = Decimal("0")
    paid_leave_days = Decimal("0")
    expected_minutes = 0
    report_totals = {
        "noon_required": 0, "noon_submitted": 0, "noon_missing": 0,
        "eod_required": 0, "eod_submitted": 0, "eod_missing": 0,
    }
    days = []
    joined = employee.joining_date or first

    d = first
    while d <= last:
        working = attendance_service.is_working_day(d)
        day_leaves = [l for l in approved if l.from_date <= d <= l.to_date]
        leave_period = attendance_service.combine_periods(l.leave_period for l in day_leaves)
        day_sessions = sessions_by_day.get(d, [])
        first_s = day_sessions[0] if day_sessions else None
        logouts = [s.logout_at for s in day_sessions if s.logout_at]
        worked_minutes = sum(s.work_duration_minutes or 0 for s in day_sessions)
        extra_minutes = sum(s.extra_work_minutes or 0 for s in day_sessions)
        late_minutes = first_s.late_login_minutes if first_s else 0
        exp_in, exp_out = attendance_service._window(leave_period)
        # Without leave, the half-day working status recorded at login decides
        # the window; with approved leave, the (live) leave period decides it.
        if first_s is not None and not leave_period:
            exp_in, exp_out = attendance_service._window(None, first_s.work_period)
        in_scope = working and joined <= d <= cutoff

        # --- attendance classification
        if leave_period == LeavePeriod.FULL_DAY:
            attendance = AttendanceStatus.FULL_DAY_LEAVE
        elif day_sessions:
            if leave_period == LeavePeriod.MORNING_HALF:
                attendance = AttendanceStatus.SECOND_HALF
            elif leave_period == LeavePeriod.AFTERNOON_HALF:
                attendance = AttendanceStatus.FIRST_HALF
            elif first_s.work_period in (WorkPeriod.FIRST_HALF, WorkPeriod.SECOND_HALF):
                attendance = first_s.work_period
            else:
                attendance = AttendanceStatus.FULL_DAY
        elif not working:
            attendance = AttendanceStatus.WEEKLY_OFF
        elif d > today or d < joined:
            attendance = AttendanceStatus.UPCOMING if d > today else "Before Joining"
        elif d == today:
            attendance = "Not Logged In"
        else:
            attendance = AttendanceStatus.ABSENT
        leave_label = attendance_service.LEAVE_STATUS_LABEL.get(leave_period)

        if working and d <= cutoff:
            if leave_period == LeavePeriod.FULL_DAY:
                counts["full_day_leave"] += 1
            elif leave_period == LeavePeriod.MORNING_HALF:
                counts["morning_half_leave"] += 1
            elif leave_period == LeavePeriod.AFTERNOON_HALF:
                counts["afternoon_half_leave"] += 1
        if day_sessions:
            key = {
                AttendanceStatus.FULL_DAY: "full_day_attendance",
                AttendanceStatus.FIRST_HALF: "first_half_attendance",
                AttendanceStatus.SECOND_HALF: "second_half_attendance",
            }.get(attendance)
            if key:
                counts[key] += 1
        if attendance == AttendanceStatus.ABSENT and in_scope:
            counts["absent_days"] += 1

        # --- leave weight for payroll (working days only, whole month)
        if working:
            for l in day_leaves:
                weight = Decimal("0.5") if l.leave_period in LeavePeriod.HALVES else Decimal("1")
                if leave_period == LeavePeriod.FULL_DAY and len(day_leaves) > 1:
                    weight = Decimal("1") / len(day_leaves)
                if leave_service.is_paid(l):
                    paid_leave_days += weight
                else:
                    unpaid_leave_days += weight

        # --- expected working time (company expectation after approved leave)
        if in_scope and exp_in and exp_out and leave_period != LeavePeriod.FULL_DAY:
            span = (exp_out.hour * 60 + exp_out.minute) - (exp_in.hour * 60 + exp_in.minute)
            expected_minutes += max(0, span)

        # --- daily reports
        rules = attendance_service.report_rules(leave_period)
        noon_rep = reports_by_key.get((d, ReportType.NOON))
        eod_rep = reports_by_key.get((d, ReportType.EOD))
        noon_req = working and rules[ReportType.NOON]["required"]
        eod_req = working and rules[ReportType.EOD]["required"]
        noon_state = _report_state(noon_rep, noon_req, d, today,
                                   now.time() >= attendance_service.NOON_OPENS, False)
        eod_state = _report_state(eod_rep, eod_req, d, today,
                                  now.time() >= attendance_service.EOD_OPENS, True)
        # No attendance and nothing filed on a past day: reports weren't expected
        # (the day already shows as Absent), so they aren't flagged as missing.
        if not day_sessions and d < today and leave_period != LeavePeriod.FULL_DAY:
            if noon_state == "Missing":
                noon_state = "No Attendance"
            if eod_state == "Missing":
                eod_state = "No Attendance"
        if noon_rep is not None and not working:
            noon_state = noon_rep.status
        if eod_rep is not None and not working:
            eod_state = eod_rep.status
        # Reports count as missing on past days the employee actually worked.
        if day_sessions and d <= cutoff:
            if noon_req:
                report_totals["noon_required"] += 1
                if noon_state in SUBMITTED:
                    report_totals["noon_submitted"] += 1
                elif noon_state == "Missing" or (noon_state in ("Draft", "Pending") and d < today):
                    report_totals["noon_missing"] += 1
            if eod_req:
                report_totals["eod_required"] += 1
                if eod_state in SUBMITTED:
                    report_totals["eod_submitted"] += 1
                elif eod_state in ("Missing", "No Attachment") or (eod_state in ("Draft", "Pending") and d < today):
                    report_totals["eod_missing"] += 1

        days.append({
            "date": d,
            "weekday": d.strftime("%a"),
            "is_working_day": working,
            "attendance": attendance,
            "leave_status": leave_label,
            "leave_period": leave_period,
            "work_period": first_s.work_period if first_s else None,
            "expected_login": attendance_service.fmt_time(exp_in) if (working and exp_in) else None,
            "actual_login": _fmt_local_time(first_s.login_at) if first_s else None,
            "late_minutes": late_minutes or 0,
            "late_reason": first_s.late_login_reason if first_s else None,
            "expected_logout": attendance_service.fmt_time(exp_out) if (working and exp_out) else None,
            "actual_logout": _fmt_local_time(max(logouts)) if logouts else None,
            "still_logged_in": any(s.logout_at is None for s in day_sessions),
            "worked_minutes": worked_minutes,
            "extra_minutes": extra_minutes,
            "sessions": len(day_sessions),
            "noon_report": noon_state,
            "eod_report": eod_state,
            "noon_report_id": noon_rep.id if noon_rep else None,
            "eod_report_id": eod_rep.id if eod_rep else None,
        })
        d += timedelta(days=1)

    working_days = sum(1 for x in days if x["is_working_day"])
    working_days_elapsed = sum(1 for x in days if x["is_working_day"] and joined <= x["date"] <= cutoff)
    days_worked = len(sessions_by_day)
    total_minutes = sum(s.work_duration_minutes or 0 for s in sessions)
    extra_total = sum(s.extra_work_minutes or 0 for s in sessions)
    late_rows = [x for x in days if x["late_minutes"]]
    leave_days = Decimal(counts["full_day_leave"]) + Decimal("0.5") * (
        counts["morning_half_leave"] + counts["afternoon_half_leave"]
    )

    leave_rows = []
    for l in leaves:
        a, b = max(first, l.from_date), min(last, l.to_date)
        if l.leave_period in LeavePeriod.HALVES:
            in_month = 0.5
        else:
            in_month = float(sum(1 for i in range((b - a).days + 1)
                                 if attendance_service.is_working_day(a + timedelta(days=i))))
        leave_rows.append({
            "id": l.id,
            "leave_type": l.leave_type,
            "leave_type_label": leave_service.type_label(l.leave_type),
            "from_date": l.from_date,
            "to_date": l.to_date,
            "leave_period": l.leave_period,
            "leave_period_label": leave_service.period_label(l),
            "duration_days": leave_service.duration_days(l),
            "working_days_in_month": in_month,
            "status": l.status,
            "is_paid": leave_service.is_paid(l),
            "reason": l.reason,
            "hr_remarks": l.hr_remarks,
            "reviewed_at": l.reviewed_at,
            "reviewed_by": l.reviewed_by.email if l.reviewed_by else None,
        })

    salary_block = None
    breakdown = salary_service.payable_breakdown(salary, working_days, unpaid_leave_days)
    if salary is not None:
        salary_block = {
            "id": salary.id,
            "period_label": salary.period_label,
            "status": salary.status,
            "recorded_working_days": salary.working_days,
            "recorded_lop_days": salary.lop_days,
            "total_earnings": float(salary.total_earnings or 0),
            "total_deductions": float(salary.total_deductions or 0),
            "net_pay": float(salary.net_pay or 0),
            "credit_date": salary.credit_date,
            "earnings": [{"name": c.name, "amount": float(c.amount)} for c in salary.earnings],
            "deductions": [{"name": c.name, "amount": float(c.amount)} for c in salary.deductions],
            "intern_download_allowed": bool(salary.intern_download_allowed),
            **breakdown,
        }

    return {
        "employee": {
            "id": employee.id,
            "name": employee.full_name,
            "employee_code": employee.display_employee_id,
            "department": employee.department.name if employee.department else None,
            "designation": employee.designation,
            "is_intern": employee.is_intern,
            "joining_date": employee.joining_date,
        },
        "period": f"{year:04d}-{mon:02d}",
        "period_label": period_label(year, mon),
        "generated_at": now.replace(microsecond=0).isoformat(),
        "is_current_month": (year, mon) == (today.year, today.month),
        "office_hours": {
            "login": attendance_service.fmt_time(attendance_service.OFFICE_START),
            "logout": attendance_service.fmt_time(attendance_service.OFFICE_END),
            "noon_report": attendance_service.fmt_time(attendance_service.NOON_OPENS),
            "eod_report": attendance_service.fmt_time(attendance_service.EOD_OPENS),
        },
        "attendance": {
            "working_days": working_days,
            "working_days_elapsed": working_days_elapsed,
            "days_worked": days_worked,
            **counts,
            "leave_days": float(leave_days),
        },
        "login": {
            "expected_login": attendance_service.fmt_time(attendance_service.OFFICE_START),
            "late_login_count": len(late_rows),
            "late_login_minutes": sum(x["late_minutes"] for x in late_rows),
            "late_logins": [
                {"date": x["date"], "expected_login": x["expected_login"], "actual_login": x["actual_login"],
                 "late_minutes": x["late_minutes"], "late_reason": x["late_reason"]}
                for x in late_rows
            ],
        },
        "hours": {
            "expected_minutes": expected_minutes,
            "actual_minutes": total_minutes,
            "total_minutes": total_minutes,
            "extra_minutes": extra_total,
            "extra_days": sum(1 for x in days if x["extra_minutes"]),
        },
        "reports": {
            **report_totals,
            "submitted_total": report_totals["noon_submitted"] + report_totals["eod_submitted"],
            "missing_total": report_totals["noon_missing"] + report_totals["eod_missing"],
            "drafts": sum(1 for r in reports if r.status == ReportStatus.DRAFT),
            "reviewed": sum(1 for r in reports if r.status == ReportStatus.REVIEWED),
        },
        "leave": {
            "approved_days": float(leave_days),
            "paid_leave_days": float(paid_leave_days),
            "unpaid_leave_days": float(unpaid_leave_days),
            "pending_requests": sum(1 for l in leaves if l.status == LeaveStatus.PENDING),
            "items": leave_rows,
        },
        "salary": salary_block,
        "salary_rule": breakdown["rule"],
        "days": days,
        # ---- keys kept for the previous /attendance/me response shape ----
        "working_days": working_days,
        "days_worked": days_worked,
        "leave_days": float(leave_days),
        "unpaid_leave_days": float(unpaid_leave_days),
        "paid_days": breakdown["paid_days"],
        "half_days": counts["first_half_attendance"] + counts["second_half_attendance"],
        "late_login_count": len(late_rows),
        "late_login_minutes": sum(x["late_minutes"] for x in late_rows),
        "extra_work_minutes": extra_total,
        "total_work_minutes": total_minutes,
        "noon_reports": report_totals["noon_submitted"],
        "eod_reports": report_totals["eod_submitted"],
    }


def summary_row(db: Session, employee: Employee, month: Optional[str]) -> dict:
    data = build(db, employee, month)
    return {
        **data["employee"],
        "period": data["period"],
        "days_worked": data["attendance"]["days_worked"],
        "leave_days": data["attendance"]["leave_days"],
        "late_login_count": data["login"]["late_login_count"],
        "extra_work_minutes": data["hours"]["extra_minutes"],
        "total_work_minutes": data["hours"]["actual_minutes"],
        "noon_reports": data["reports"]["noon_submitted"],
        "eod_reports": data["reports"]["eod_submitted"],
        "missing_reports": data["reports"]["missing_total"],
    }


# ------------------------------------------------------------------------ PDF
def _hm(minutes) -> str:
    return attendance_service.minutes_label(minutes)


def _t12(value: Optional[str]) -> str:
    if not value:
        return "-"
    h, m = (int(x) for x in value.split(":"))
    return f"{(h % 12) or 12}:{m:02d} {'PM' if h >= 12 else 'AM'}"


def build_pdf(db: Session, data: dict, include_salary: bool = True) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )

    brand = colors.HexColor("#1f2a5a")
    soft = colors.HexColor("#eef1fb")
    line = colors.HexColor("#c9cfe0")

    company = settings_service.get(db, "company_name", settings.COMPANY_NAME)
    address = settings_service.get(db, "company_address", settings.COMPANY_ADDRESS)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=landscape(A4), rightMargin=10 * mm, leftMargin=10 * mm,
        topMargin=10 * mm, bottomMargin=10 * mm,
        title=f"Monthly Report - {data['employee']['name']} - {data['period_label']}",
    )
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Title"], alignment=TA_LEFT, fontSize=16,
                        textColor=brand, spaceAfter=2)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=11, textColor=brand,
                        spaceBefore=8, spaceAfter=4)
    small = ParagraphStyle("small", parent=styles["BodyText"], fontSize=7.5, leading=9)
    body = ParagraphStyle("body", parent=styles["BodyText"], fontSize=8.5, leading=11)

    def grid(rows, widths, header=True, font=7.5):
        t = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
        style = [
            ("GRID", (0, 0), (-1, -1), 0.3, line),
            ("FONTSIZE", (0, 0), (-1, -1), font),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ]
        if header:
            style += [("BACKGROUND", (0, 0), (-1, 0), brand),
                      ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                      ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")]
        t.setStyle(TableStyle(style))
        return t

    def kv_table(pairs, cols=4):
        rows, row = [], []
        for label, value in pairs:
            text = f"{value:g}" if isinstance(value, float) else str(value)
            row += [label, Paragraph(text, small)]
            if len(row) == cols * 2:
                rows.append(row)
                row = []
        if row:
            rows.append(row + [""] * (cols * 2 - len(row)))
        width = (doc.width) / (cols * 2)
        t = Table(rows, colWidths=[width * 1.15, width * 0.85] * cols)
        style = [("GRID", (0, 0), (-1, -1), 0.3, line), ("FONTSIZE", (0, 0), (-1, -1), 8)]
        for c in range(0, cols * 2, 2):
            style += [("BACKGROUND", (c, 0), (c, -1), soft), ("FONTNAME", (c, 0), (c, -1), "Helvetica-Bold")]
        t.setStyle(TableStyle(style))
        return t

    e, a, lg, hrs, rep, lv = (data["employee"], data["attendance"], data["login"], data["hours"],
                              data["reports"], data["leave"])
    story = [
        Paragraph(f"{company} &mdash; Monthly Employee Report", h1),
        Paragraph(address, small),
        Spacer(1, 4),
        kv_table([
            ("Employee", e["name"]), ("Employee ID", e["employee_code"]),
            ("Department", e["department"] or "-"), ("Designation", e["designation"] or "-"),
            ("Report Month", data["period_label"]), ("Generated", data["generated_at"].replace("T", " ")[:16] + " IST"),
            ("Office Hours", f"{_t12(data['office_hours']['login'])} - {_t12(data['office_hours']['logout'])}"),
            ("Type", "Intern" if e["is_intern"] else "Employee"),
        ]),
        Paragraph("Attendance", h2),
        kv_table([
            ("Working Days", a["working_days"]), ("Days Worked", a["days_worked"]),
            ("Full-Day Attendance", a["full_day_attendance"]), ("First-Half Attendance", a["first_half_attendance"]),
            ("Second-Half Attendance", a["second_half_attendance"]), ("Absent Days", a["absent_days"]),
            ("Full-Day Leave", a["full_day_leave"]), ("Morning Half Leave", a["morning_half_leave"]),
            ("Afternoon Half Leave", a["afternoon_half_leave"]), ("Total Leave Days", a["leave_days"]),
        ]),
        Paragraph("Login &amp; Working Hours", h2),
        kv_table([
            ("Expected Login", _t12(lg["expected_login"])), ("Late Logins", lg["late_login_count"]),
            ("Total Late Time", _hm(lg["late_login_minutes"])), ("Expected Hours", _hm(hrs["expected_minutes"])),
            ("Actual Hours", _hm(hrs["actual_minutes"])), ("Extra Hours", _hm(hrs["extra_minutes"])),
        ]),
        Paragraph("Daily Reports", h2),
        kv_table([
            ("Noon Required", rep["noon_required"]), ("Noon Submitted", rep["noon_submitted"]),
            ("Noon Missing", rep["noon_missing"]), ("EOD Required", rep["eod_required"]),
            ("EOD Submitted", rep["eod_submitted"]), ("EOD Missing", rep["eod_missing"]),
            ("Reviewed by HR", rep["reviewed"]), ("Drafts", rep["drafts"]),
        ]),
    ]

    story.append(Paragraph("Attendance Details", h2))
    rows = [["Date", "Day", "Attendance", "Leave", "Exp. Login", "Login", "Late", "Late Reason",
             "Exp. Logout", "Logout", "Worked", "Extra", "Noon", "EOD"]]
    for x in data["days"]:
        if not x["is_working_day"] and not x["sessions"]:
            continue
        rows.append([
            x["date"].strftime("%d %b"), x["weekday"], x["attendance"], x["leave_status"] or "-",
            _t12(x["expected_login"]), _t12(x["actual_login"]),
            _hm(x["late_minutes"]) if x["late_minutes"] else "-",
            Paragraph((x["late_reason"] or "-")[:120], small),
            _t12(x["expected_logout"]), _t12(x["actual_logout"]) if x["actual_logout"] else ("Active" if x["still_logged_in"] else "-"),
            _hm(x["worked_minutes"]) if x["worked_minutes"] else "-",
            _hm(x["extra_minutes"]) if x["extra_minutes"] else "-",
            x["noon_report"], x["eod_report"],
        ])
    w = doc.width
    story.append(grid(rows, [w * f for f in (.055, .035, .09, .1, .06, .055, .045, .16, .06, .055, .05, .045, .07, .07)]))

    story.append(Paragraph("Leave", h2))
    if lv["items"]:
        lrows = [["Type", "From", "To", "Period", "Duration", "Status", "Paid", "Reason", "HR Remarks"]]
        for l in lv["items"]:
            lrows.append([
                l["leave_type_label"], l["from_date"].strftime("%d %b %Y"), l["to_date"].strftime("%d %b %Y"),
                l["leave_period_label"], f"{l['duration_days']:g} day(s)", l["status"],
                "Paid" if l["is_paid"] else "Unpaid", Paragraph((l["reason"] or "-")[:160], small),
                Paragraph((l["hr_remarks"] or "-")[:120], small),
            ])
        story.append(grid(lrows, [w * f for f in (.1, .08, .08, .16, .07, .07, .05, .24, .15)]))
        story.append(Spacer(1, 3))
        story.append(Paragraph(
            f"Approved leave this month: {lv['approved_days']:g} day(s) &middot; paid {lv['paid_leave_days']:g} "
            f"&middot; unpaid {lv['unpaid_leave_days']:g} &middot; pending requests {lv['pending_requests']}", body))
    else:
        story.append(Paragraph("No leave requests in this month.", body))

    story.append(Paragraph("Salary", h2))
    s = data["salary"]
    if s is None:
        story.append(Paragraph("No salary record has been created for this month yet.", body))
    elif not include_salary:
        story.append(Paragraph(
            "Salary details for interns can be viewed in the portal. Downloading them needs HR "
            "permission for this month's payslip.", body))
    else:
        story.append(KeepTogether([
            kv_table([
                ("Salary Status", s["status"]), ("Gross Earnings", f"Rs. {s['total_earnings']:,.2f}"),
                ("Deductions", f"Rs. {s['total_deductions']:,.2f}"), ("Recorded Net Pay", f"Rs. {s['net_pay']:,.2f}"),
                ("Working Days (month)", s["working_days"]), ("Unpaid Leave Days", f"{s['unpaid_leave_days']:g}"),
                ("Paid Days", f"{s['paid_days']:g}"), ("Per-Day Rate", f"Rs. {s['per_day_rate']:,.2f}"),
                ("Unpaid Leave Deduction", f"Rs. {s['unpaid_leave_deduction']:,.2f}"),
                ("Payable (Gross)", f"Rs. {s['estimated_payable']:,.2f}"),
                ("Payable after Deductions", f"Rs. {s['estimated_net_payable']:,.2f}"),
                ("Payslip LOP Days", s["recorded_lop_days"]),
            ], cols=3),
            Spacer(1, 3),
            Paragraph(f"Rule: {data['salary_rule']}", small),
        ]))

    doc.build(story)
    return buf.getvalue()


def pdf_filename(data: dict) -> str:
    safe = "".join(ch for ch in data["employee"]["name"] if ch.isalnum() or ch in " -_").strip().replace(" ", "-")
    return f"Monthly-Report-{safe or 'Employee'}-{data['period']}.pdf"
