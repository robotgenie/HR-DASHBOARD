"""Attendance, working-hours, late logins and monthly reporting.

All figures come from app.services.monthly_report_service, which derives them
from the stored sessions, leave, daily reports and salary records.
"""
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload

from app.core.dependencies import (
    assert_can_access_employee, get_current_employee, get_current_user, is_hr, require_hr,
    require_supervisor,
)
from app.database.database import get_db
from app.models.employee import Employee
from app.models.user import User
from app.models.work_session import WorkSession
from app.services import attendance_service, hierarchy_service, monthly_report_service
from app.utils.clock import local_today, to_local

router = APIRouter(prefix="/attendance", tags=["Attendance"])


def _for_viewer(db: Session, current_user: User, employee: Employee, data: dict) -> dict:
    """Monthly reports keep their salary block only for viewers allowed to see
    salary (self, HR, Admin). A Manager sees attendance/report figures only."""
    if not hierarchy_service.can_view_sensitive(db, current_user, employee):
        data = dict(data)
        data["salary"] = None
    return data


def _scoped_employees(db: Session, current_user: User, include_self: bool = False,
                      department_id: Optional[int] = None, reporting_hr_id: Optional[int] = None,
                      reporting_manager_id: Optional[int] = None, person_type: Optional[str] = None,
                      active_only: bool = False):
    query = db.query(Employee).join(User, Employee.user_id == User.id).options(
        joinedload(Employee.department), joinedload(Employee.user))
    query = hierarchy_service.restrict(query, db, current_user, Employee.id, include_self=include_self)
    if active_only:
        query = query.filter(User.is_active.is_(True))
    if department_id:
        query = query.filter(Employee.department_id == department_id)
    if reporting_hr_id:
        query = query.filter(Employee.reporting_hr_id == reporting_hr_id)
    if reporting_manager_id:
        query = query.filter(Employee.reporting_manager_id == reporting_manager_id)
    rows = query.order_by(Employee.full_name).all()
    if person_type:
        rows = [e for e in rows if hierarchy_service.person_type(e) == person_type]
    return rows


def _target(db: Session, current_user: User, employee_id: Optional[int]) -> Employee:
    """Admin anyone, HR their hierarchy, Manager their team, others only themselves."""
    if employee_id:
        return assert_can_access_employee(current_user, employee_id, db)
    employee = db.query(Employee).filter(Employee.user_id == current_user.id).first()
    if employee is None:
        raise HTTPException(status_code=404, detail="No employee profile on this account.")
    return employee


@router.get("/me")
def my_attendance(month: Optional[str] = Query(None), db: Session = Depends(get_db),
                  employee: Employee = Depends(get_current_employee)):
    return monthly_report_service.build(db, employee, month)


@router.get("/today")
def my_day_plan(db: Session = Depends(get_db), employee: Employee = Depends(get_current_employee)):
    """Today's expected window and which reports apply after approved leave."""
    return attendance_service.day_plan(db, employee)


@router.get("/employee/{employee_id}")
def employee_attendance(employee_id: int, month: Optional[str] = Query(None),
                        db: Session = Depends(get_db),
                        current_user: User = Depends(get_current_user)):
    employee = assert_can_access_employee(current_user, employee_id, db)
    return _for_viewer(db, current_user, employee, monthly_report_service.build(db, employee, month))


@router.get("/months")
def report_months(employee_id: Optional[int] = Query(None), db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    """Months for which a monthly report can be viewed, newest first."""
    employee = _target(db, current_user, employee_id)
    return {"employee_id": employee.id, "items": monthly_report_service.available_months(db, employee)}


@router.get("/monthly-report")
def monthly_report(month: Optional[str] = Query(None), employee_id: Optional[int] = Query(None),
                   db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    employee = _target(db, current_user, employee_id)
    return _for_viewer(db, current_user, employee, monthly_report_service.build(db, employee, month))


@router.get("/hr/monthly-summary")
def hr_monthly_summary(month: Optional[str] = Query(None),
                       department_id: Optional[int] = Query(None),
                       reporting_hr_id: Optional[int] = Query(None),
                       reporting_manager_id: Optional[int] = Query(None),
                       person_type: Optional[str] = Query(None),
                       db: Session = Depends(get_db),
                       current_user: User = Depends(require_supervisor)):
    """Monthly summary for everyone the viewer may monitor (hierarchy-scoped)."""
    employees = _scoped_employees(
        db, current_user, include_self=True, department_id=department_id,
        reporting_hr_id=reporting_hr_id, reporting_manager_id=reporting_manager_id,
        person_type=person_type,
    )
    year, mon = monthly_report_service.parse_month(month)
    period = f"{year:04d}-{mon:02d}"
    return {"period": period, "items": [
        monthly_report_service.summary_row(db, e, period) for e in employees
    ]}


@router.get("/hr/late-logins")
def hr_late_logins(
    date_from: Optional[date] = Query(None), date_to: Optional[date] = Query(None),
    employee_id: Optional[int] = Query(None), limit: int = Query(100, ge=1, le=500),
    department_id: Optional[int] = Query(None),
    db: Session = Depends(get_db), current_user: User = Depends(require_supervisor),
):
    """Late logins with expected/actual time, duration and the stated reason."""
    date_to = date_to or local_today()
    date_from = date_from or (date_to - timedelta(days=30))
    query = (
        db.query(WorkSession, Employee)
        .join(Employee, Employee.user_id == WorkSession.user_id)
        .options(joinedload(Employee.department))
        .filter(
            WorkSession.late_login_minutes > 0,
            WorkSession.work_date >= date_from,
            WorkSession.work_date <= date_to,
        )
    )
    query = hierarchy_service.restrict(query, db, current_user, Employee.id, include_self=False)
    if employee_id:
        query = query.filter(Employee.id == employee_id)
    if department_id:
        query = query.filter(Employee.department_id == department_id)
    rows = query.order_by(WorkSession.login_at.desc()).limit(limit).all()
    items = []
    for session, employee in rows:
        actual = to_local(session.login_at)
        items.append({
            "session_id": session.id,
            "employee_id": employee.id,
            "employee_name": employee.full_name,
            "employee_code": employee.display_employee_id,
            "department": employee.department.name if employee.department else None,
            "is_intern": employee.is_intern,
            "date": session.work_date,
            "expected_login": attendance_service.fmt_time(session.expected_login_time) or "10:00",
            "actual_login": actual.strftime("%H:%M") if actual else None,
            "late_minutes": session.late_login_minutes,
            "late_label": attendance_service.minutes_label(session.late_login_minutes),
            "late_reason": session.late_login_reason,
            "work_period": session.work_period,
        })
    return {"date_from": date_from, "date_to": date_to, "items": items}


@router.get("/monthly-pdf")
def monthly_pdf(month: Optional[str] = Query(None),
                employee_id: Optional[int] = Query(None),
                db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)):
    employee = _target(db, current_user, employee_id)
    data = monthly_report_service.build(db, employee, month)
    # Interns keep their existing restriction: salary figures leave the portal
    # (download) only when HR has granted download permission for that month.
    include_salary = hierarchy_service.can_view_sensitive(db, current_user, employee)
    is_own = employee.user_id == current_user.id
    if include_salary and is_own and employee.is_intern and data["salary"] is not None:
        include_salary = bool(data["salary"]["intern_download_allowed"])
    content = monthly_report_service.build_pdf(db, data, include_salary=include_salary)
    return StreamingResponse(
        iter([content]), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{monthly_report_service.pdf_filename(data)}"'},
    )


# --------------------------------------------------------------------------
# Check-In / Check-Out (live selfie + location). Login no longer records
# attendance; these endpoints do, using the same work_sessions records.
# --------------------------------------------------------------------------
from fastapi import Request  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from app.core.dependencies import client_ip, user_agent  # noqa: E402
from app.services import file_service, report_service  # noqa: E402
from app.utils.clock import local_now  # noqa: E402


class AttendanceEventIn(BaseModel):
    selfie_data: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    accuracy: Optional[float] = Field(None, ge=0)
    location_label: Optional[str] = Field(None, max_length=255)
    late_login_reason: Optional[str] = Field(None, max_length=500)
    work_period: Optional[str] = Field(None, max_length=20)
    reason: Optional[str] = Field(None, max_length=500)


@router.get("/status")
def attendance_status(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Everything the dashboard's attendance card needs for today."""
    now = local_now()
    employee = current_user.employee
    # The Admin is not an employee: no check-in/check-out. HR and Managers are.
    if hierarchy_service.is_admin(current_user) or employee is None:
        return {"applicable": False, "reason": attendance_service.CHECK_IN_ROLE_ERROR}
    row = attendance_service.today_session(db, current_user.id, now.date())
    blocker = attendance_service.check_in_blocker(db, current_user, employee, now)
    context = None
    if blocker is None:
        context = attendance_service.public_context(
            attendance_service.login_context(db, current_user, None, now)
        )
    return {
        "applicable": True,
        "date": now.date(),
        "now": now.strftime("%H:%M"),
        "office_hours": {"start": "10:00", "end": "18:00"},
        "state": "checked_out" if row is not None and row.logout_at else ("checked_in" if row is not None else "not_checked_in"),
        "session": attendance_service.session_out(row),
        "can_check_in": blocker is None,
        "check_in_blocker": blocker,
        "check_in_context": context,
        "plan": attendance_service.day_plan(db, employee, now.date(), now),
        "reports": report_service.logout_requirements(db, employee),
    }


@router.post("/check-in")
def check_in(payload: AttendanceEventIn, request: Request, db: Session = Depends(get_db),
             current_user: User = Depends(get_current_user)):
    row = attendance_service.check_in(
        db, current_user, selfie_data=payload.selfie_data, latitude=payload.latitude,
        longitude=payload.longitude, accuracy=payload.accuracy, location_label=payload.location_label,
        late_login_reason=payload.late_login_reason, work_period=payload.work_period,
        ip=client_ip(request), user_agent=user_agent(request),
    )
    db.commit()
    return {"detail": "Checked in.", "session": attendance_service.session_out(row)}


@router.post("/check-out")
def check_out(payload: AttendanceEventIn, request: Request, db: Session = Depends(get_db),
              current_user: User = Depends(get_current_user)):
    row = attendance_service.check_out(
        db, current_user, selfie_data=payload.selfie_data, latitude=payload.latitude,
        longitude=payload.longitude, accuracy=payload.accuracy, location_label=payload.location_label,
        reason=payload.reason, ip=client_ip(request), user_agent=user_agent(request),
    )
    db.commit()
    return {"detail": "Checked out.", "session": attendance_service.session_out(row)}


def _session_for(db: Session, session_id: int, current_user: User) -> WorkSession:
    row = db.query(WorkSession).filter(WorkSession.id == session_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Attendance record not found.")
    if row.user_id != current_user.id:
        owner = db.query(Employee).filter(Employee.user_id == row.user_id).first()
        if owner is None and not hierarchy_service.is_admin(current_user):
            raise HTTPException(status_code=403, detail="You don't have access to this resource.")
        if owner is not None:
            hierarchy_service.assert_level(db, current_user, owner, hierarchy_service.VIEW, "work_session")
    return row


@router.get("/sessions/{session_id}/selfie/{kind}")
def session_selfie(session_id: int, kind: str, db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    """Check-In / Check-Out selfie: HR/Admin, or the employee who took it."""
    row = _session_for(db, session_id, current_user)
    stored = {"check-in": row.login_selfie_path, "check-out": row.logout_selfie_path}.get(kind)
    if kind not in ("check-in", "check-out"):
        raise HTTPException(status_code=404, detail="Unknown selfie.")
    if not stored:
        raise HTTPException(status_code=404, detail="No selfie was recorded for this event.")
    path = file_service.resolve_path(file_service.SELFIES, stored)
    if not path.exists():
        raise HTTPException(status_code=404, detail="The selfie file is missing.")
    return FileResponse(path, media_type="image/jpeg")


@router.get("/sessions")
def attendance_sessions(
    day: Optional[date] = Query(None, alias="date"), employee_id: Optional[int] = Query(None),
    date_from: Optional[date] = Query(None), date_to: Optional[date] = Query(None),
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Check-In/Check-Out records. Employees see only their own."""
    query = db.query(WorkSession, Employee).join(Employee, Employee.user_id == WorkSession.user_id)
    query = hierarchy_service.restrict(query, db, current_user, Employee.id)
    if employee_id:
        query = query.filter(Employee.id == employee_id)
    if day:
        query = query.filter(WorkSession.work_date == day)
    if date_from:
        query = query.filter(WorkSession.work_date >= date_from)
    if date_to:
        query = query.filter(WorkSession.work_date <= date_to)
    rows = query.order_by(WorkSession.work_date.desc(), WorkSession.login_at.desc()).limit(500).all()
    return {"items": [
        {**attendance_service.session_out(s), "employee_id": e.id, "employee_name": e.full_name,
         "employee_code": e.display_employee_id, "department": e.department.name if e.department else None}
        for s, e in rows
    ]}


@router.get("/hr/today")
def hr_work_today(day: Optional[date] = Query(None, alias="date"),
                  department_id: Optional[int] = Query(None),
                  reporting_hr_id: Optional[int] = Query(None),
                  reporting_manager_id: Optional[int] = Query(None),
                  person_type: Optional[str] = Query(None),
                  db: Session = Depends(get_db),
                  current_user: User = Depends(require_supervisor)):
    """Work monitor: one row per person the viewer supervises, for a date.

    Admin: everyone (HR, managers, employees, interns). HR: their hierarchy.
    Manager: their team. The viewer's own row is not part of the monitor.
    """
    from app.services import task_service

    now = local_now()
    day = day or now.date()
    employees = _scoped_employees(
        db, current_user, include_self=False, department_id=department_id,
        reporting_hr_id=reporting_hr_id, reporting_manager_id=reporting_manager_id,
        person_type=person_type, active_only=True,
    )
    rows = []
    totals = {"employees": 0, "checked_in": 0, "checked_out": 0, "late": 0, "on_leave": 0,
              "hourly_submitted": 0, "hourly_due": 0, "open_tasks": 0}
    for e in employees:
        session = attendance_service.today_session(db, e.user_id, day)
        slots = attendance_service.hourly_slots(db, e, session, day, now)
        plan = attendance_service.day_plan(db, e, day, now)
        tasks = task_service.active_for(db, e.id, day)
        from app.models.daily_report import DailyReport
        reps = {r.report_type: r for r in db.query(DailyReport).filter(
            DailyReport.employee_id == e.id, DailyReport.report_date == day)}

        def rstate(kind, rule):
            if not rule["required"]:
                return "Not Required"
            r = reps.get(kind)
            return r.status if r else "Pending"
        submitted = sum(1 for s in slots if s["status"] == "Submitted")
        due = sum(1 for s in slots if s["status"] in ("Due", "Missed"))
        totals["employees"] += 1
        totals["checked_in"] += 1 if session is not None else 0
        totals["checked_out"] += 1 if session is not None and session.logout_at else 0
        totals["late"] += 1 if session is not None and session.late_login_minutes else 0
        totals["on_leave"] += 1 if plan["leave_period"] else 0
        totals["hourly_submitted"] += submitted
        totals["hourly_due"] += due
        totals["open_tasks"] += sum(1 for t in tasks if t.status in ("Pending", "In Progress"))
        rows.append({
            "employee_id": e.id, "employee_name": e.full_name, "employee_code": e.display_employee_id,
            "department": e.department.name if e.department else None, "is_intern": e.is_intern,
            "person_type": hierarchy_service.person_type(e),
            "reporting_manager": e.reporting_manager.full_name if e.reporting_manager else None,
            "reporting_hr": (hierarchy_service.get_reporting_hr(e).full_name
                             if hierarchy_service.get_reporting_hr(e) else None),
            "session": attendance_service.session_out(session),
            "leave_status": plan["leave_status"], "leave_period": plan["leave_period"],
            "noon_report": rstate("Noon", plan["noon"]), "eod_report": rstate("EOD", plan["eod"]),
            "hourly_submitted": submitted, "hourly_missing": due,
            "hourly_applicable": sum(1 for s in slots if s["status"] != "Not Applicable"),
            "tasks": [task_service.output(t) for t in tasks],
        })
    return {"date": day, "totals": totals, "items": rows}
