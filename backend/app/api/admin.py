"""Admin console API: organisation monitoring with HR as the primary focus,
Admin profile and Admin accounts.

The Admin is not an employee: there is no employee record, no check-in, no
attendance. Everything here is read from the same tables and services the rest
of the HRMS uses; nothing is duplicated or cached.
"""
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.api.dashboard import management_dashboard
from app.api.serializers import employee_detail, employee_list_item, report_out, salary_out
from app.core.constants import (
    ApprovalStage, AuditAction, DocumentStatus, LeaveStatus, ReportStatus, RoleName, TaskStatus,
)
from app.core.dependencies import require_admin
from app.core.security import generate_initial_password, hash_password
from app.database.database import get_db
from app.models.daily_report import DailyReport
from app.models.department import Department
from app.models.employee import Employee
from app.models.employee_document import EmployeeDocument
from app.models.hourly_update import HourlyUpdate
from app.models.leave_request import LeaveRequest
from app.models.role import Role
from app.models.salary import SalaryRecord
from app.models.user import User
from app.models.work_task import WorkTask
from app.services import (
    attendance_service, audit_service, auth_service, document_service, hierarchy_service as H,
    hourly_service, leave_service, monthly_report_service, task_service,
)
from app.utils.clock import local_now, local_today

router = APIRouter(prefix="/admin", tags=["Admin"])


# ----------------------------------------------------------------- helpers
def _today_status(db: Session, employee: Employee, day: date) -> dict:
    session = attendance_service.today_session(db, employee.user_id, day)
    plan = attendance_service.day_plan(db, employee, day, local_now())
    if session is None:
        state = plan["leave_status"] or ("Not Checked In" if plan["is_working_day"] else "Weekly Off")
    else:
        state = "Checked Out" if session.logout_at else "Checked In"
    return {
        "state": state,
        "session": attendance_service.session_out(session),
        "leave_status": plan["leave_status"],
    }


def _counts_for_hr(db: Session, hr: Employee) -> dict:
    ids = [hr.id] + [
        e.id for e in db.query(Employee.id).filter(Employee.reporting_hr_id == hr.id).all()
    ]
    managers = (
        db.query(func.count(Employee.id)).join(User, Employee.user_id == User.id)
        .join(Role, User.role_id == Role.id)
        .filter(Employee.reporting_hr_id == hr.id, Role.name == RoleName.MANAGER).scalar() or 0
    )
    team = len(ids) - 1 - managers
    return {
        "managers": managers,
        "employees": team,
        "pending_leave_in_team": db.query(func.count(LeaveRequest.id)).filter(
            LeaveRequest.employee_id.in_(ids[1:] or [0]), LeaveRequest.status == LeaveStatus.PENDING
        ).scalar() or 0,
        "reports_to_review": db.query(func.count(DailyReport.id)).filter(
            DailyReport.employee_id.in_(ids[1:] or [0]), DailyReport.status == ReportStatus.SUBMITTED
        ).scalar() or 0,
        "own_open_tasks": db.query(func.count(WorkTask.id)).filter(
            WorkTask.employee_id == hr.id, WorkTask.status.in_(TaskStatus.OPEN)
        ).scalar() or 0,
        "own_pending_leave": db.query(func.count(LeaveRequest.id)).filter(
            LeaveRequest.employee_id == hr.id, LeaveRequest.status == LeaveStatus.PENDING
        ).scalar() or 0,
    }


def _people_of_role(db: Session, role: str):
    return (
        db.query(Employee).join(User, Employee.user_id == User.id).join(Role, User.role_id == Role.id)
        .options(joinedload(Employee.department), joinedload(Employee.user))
        .filter(Role.name == role).order_by(Employee.full_name)
    )


# --------------------------------------------------------------- dashboard
@router.get("/dashboard")
def admin_dashboard(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    """Organisation overview. HR monitoring comes first."""
    base = management_dashboard(db, current_user)
    day = local_today()

    hr_rows = []
    for hr in _people_of_role(db, RoleName.HR_ADMIN).all():
        hr_rows.append({
            **employee_list_item(db, hr, with_docs=False),
            "today": _today_status(db, hr, day),
            "counts": _counts_for_hr(db, hr),
        })

    by_type = {"HR": 0, "Manager": 0, "Employee": 0, "Intern": 0}
    active_by_type = dict(by_type)
    for e in db.query(Employee).options(joinedload(Employee.user), joinedload(Employee.department)).all():
        t = H.person_type(e)
        by_type[t] = by_type.get(t, 0) + 1
        if e.user and e.user.is_active:
            active_by_type[t] = active_by_type.get(t, 0) + 1

    checked_in = 0
    from app.models.work_session import WorkSession
    checked_in = db.query(func.count(func.distinct(WorkSession.user_id))).filter(
        WorkSession.work_date == day).scalar() or 0

    stage_counts = dict(
        db.query(LeaveRequest.approval_stage, func.count(LeaveRequest.id))
        .filter(LeaveRequest.status == LeaveStatus.PENDING)
        .group_by(LeaveRequest.approval_stage).all()
    )
    unassigned = (
        db.query(func.count(Employee.id)).join(User, Employee.user_id == User.id)
        .join(Role, User.role_id == Role.id)
        .filter(Employee.reporting_hr_id.is_(None), Role.name.in_((RoleName.MANAGER, RoleName.EMPLOYEE)))
        .scalar() or 0
    )
    base.update({
        "hr_monitoring": hr_rows,
        "people_by_type": by_type,
        "active_by_type": active_by_type,
        "checked_in_today": checked_in,
        "leave_by_stage": {s: stage_counts.get(s, 0) for s in (ApprovalStage.MANAGER, ApprovalStage.HR, ApprovalStage.ADMIN)},
        "unassigned_people": unassigned,
        "hr_leave_awaiting_admin": stage_counts.get(ApprovalStage.ADMIN, 0),
    })
    return base


# ----------------------------------------------------------- HR monitoring
@router.get("/hr")
def list_hr(department_id: Optional[int] = None, db: Session = Depends(get_db),
            current_user: User = Depends(require_admin)):
    query = _people_of_role(db, RoleName.HR_ADMIN)
    if department_id:
        query = query.filter(Employee.department_id == department_id)
    day = local_today()
    return {"items": [
        {**employee_list_item(db, hr), "today": _today_status(db, hr, day), "counts": _counts_for_hr(db, hr)}
        for hr in query.all()
    ]}


@router.get("/people/{employee_id}/overview")
def person_overview(employee_id: int, month: Optional[str] = None,
                    db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    """Everything about one person on one screen (built for HR monitoring:
    profile -> attendance -> reports -> hourly -> tasks -> leave -> documents
    -> salary -> managers -> teams). Works for any employee-side person."""
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found.")
    day = local_today()
    month_data = monthly_report_service.build(db, employee, month)
    since = day - timedelta(days=30)

    reports = (
        db.query(DailyReport).options(joinedload(DailyReport.attachments), joinedload(DailyReport.employee))
        .filter(DailyReport.employee_id == employee.id, DailyReport.report_date >= since)
        .order_by(DailyReport.report_date.desc(), DailyReport.id.desc()).limit(60).all()
    )
    hourly = (
        hourly_service.query(db).filter(HourlyUpdate.employee_id == employee.id,
                                        HourlyUpdate.update_date >= day - timedelta(days=7))
        .order_by(HourlyUpdate.update_date.desc(), HourlyUpdate.slot_index.desc()).limit(80).all()
    )
    tasks = (
        task_service.query(db).filter(WorkTask.employee_id == employee.id)
        .order_by(WorkTask.task_date.desc(), WorkTask.id.desc()).limit(50).all()
    )
    leaves = (
        db.query(LeaveRequest).filter(LeaveRequest.employee_id == employee.id)
        .order_by(LeaveRequest.created_at.desc()).limit(30).all()
    )
    salaries = (
        db.query(SalaryRecord).filter(SalaryRecord.employee_id == employee.id)
        .order_by(SalaryRecord.period_year.desc(), SalaryRecord.period_month.desc()).limit(12).all()
    )

    managers = []
    if H.employee_role(employee) == RoleName.HR_ADMIN:
        for mgr in H.get_direct_reports(db, employee):
            managers.append({
                **employee_list_item(db, mgr, with_docs=False),
                "today": _today_status(db, mgr, day),
                "team": [
                    {**employee_list_item(db, m, with_docs=False), "today": _today_status(db, m, day)}
                    for m in H.get_team(db, mgr)
                ],
            })
        direct = [
            {**employee_list_item(db, e, with_docs=False), "today": _today_status(db, e, day)}
            for e in db.query(Employee).filter(
                Employee.reporting_hr_id == employee.id, Employee.reporting_manager_id.is_(None)
            ).all() if H.employee_role(e) == RoleName.EMPLOYEE
        ]
    elif H.employee_role(employee) == RoleName.MANAGER:
        direct = [
            {**employee_list_item(db, m, with_docs=False), "today": _today_status(db, m, day)}
            for m in H.get_team(db, employee)
        ]
    else:
        direct = []

    return {
        "profile": employee_detail(db, employee),
        "type": H.person_type(employee),
        "chain": H.reporting_chain(employee),
        "today": _today_status(db, employee, day),
        "attendance": month_data,
        "reports": [report_out(r) for r in reports],
        "hourly_updates": [hourly_service.output(u) for u in hourly],
        "tasks": [task_service.output(t) for t in tasks],
        "leave": [leave_service.output(l) for l in leaves],
        "documents": {
            "completion": document_service.completion(db, employee),
            "items": document_service.checklist(db, employee),
        },
        "salary": [salary_out(s) for s in salaries],
        "managers": managers,
        "direct_team": direct,
    }


@router.get("/people")
def list_people(
    person_type: Optional[str] = Query(None, description="HR | Manager | Employee | Intern"),
    department_id: Optional[int] = None, reporting_hr_id: Optional[int] = None,
    reporting_manager_id: Optional[int] = None, search: Optional[str] = None,
    db: Session = Depends(get_db), current_user: User = Depends(require_admin),
):
    """Organisation directory with today's attendance state, for the Admin
    monitoring pages (HR / Manager / Employee / Intern monitoring)."""
    query = db.query(Employee).options(joinedload(Employee.department), joinedload(Employee.user))
    if department_id:
        query = query.filter(Employee.department_id == department_id)
    if reporting_hr_id:
        query = query.filter(Employee.reporting_hr_id == reporting_hr_id)
    if reporting_manager_id:
        query = query.filter(Employee.reporting_manager_id == reporting_manager_id)
    if search:
        needle = f"%{search.strip()}%"
        query = query.filter(Employee.full_name.ilike(needle) | Employee.employee_code.ilike(needle)
                             | Employee.unique_employee_id.ilike(needle))
    rows = query.order_by(Employee.full_name).all()
    if person_type:
        rows = [e for e in rows if H.person_type(e) == person_type]
    day = local_today()
    items = []
    for e in rows:
        item = employee_list_item(db, e)
        item["today"] = _today_status(db, e, day)
        item["team_size"] = len(H.get_direct_reports(db, e))
        items.append(item)
    return {"items": items, "total": len(items)}


# --------------------------------------------------------------- profile
class AdminProfileIn(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=160)
    phone: Optional[str] = Field(None, max_length=20)
    title: Optional[str] = Field(None, max_length=120)


def _admin_out(user: User) -> dict:
    return {
        "id": user.id, "email": user.email, "full_name": user.full_name or user.email,
        "phone": user.phone, "title": user.title or "Administrator", "role": user.role_name,
        "role_label": "Admin", "is_active": user.is_active, "last_login_at": user.last_login_at,
        "created_at": user.created_at,
    }


@router.get("/profile")
def admin_profile(current_user: User = Depends(require_admin)):
    return _admin_out(current_user)


@router.put("/profile")
def update_admin_profile(payload: AdminProfileIn, db: Session = Depends(get_db),
                         current_user: User = Depends(require_admin)):
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(current_user, field, (value or "").strip() or None)
    audit_service.record(db, AuditAction.ADMIN_PROFILE_UPDATED, user=current_user,
                         entity_type="user", entity_id=current_user.id, meta={"fields": list(changes)})
    db.commit()
    db.refresh(current_user)
    return _admin_out(current_user)


# ---------------------------------------------------------- admin accounts
class AdminCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(..., min_length=2, max_length=160)
    phone: Optional[str] = Field(None, max_length=20)
    title: Optional[str] = Field(None, max_length=120)


@router.get("/admins")
def list_admins(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    rows = H.active_users_with_role(db, RoleName.ADMIN)
    return {"items": [_admin_out(u) for u in rows]}


@router.post("/admins", status_code=status.HTTP_201_CREATED)
def create_admin(payload: AdminCreate, db: Session = Depends(get_db),
                 current_user: User = Depends(require_admin)):
    user, raw = create_admin_account(db, payload.email, payload.full_name, actor=current_user,
                                     phone=payload.phone, title=payload.title)
    db.commit()
    return {"admin": _admin_out(user), "initial_password": raw}


def create_admin_account(db: Session, email: str, full_name: str, actor: Optional[User] = None,
                         password: Optional[str] = None, phone: Optional[str] = None,
                         title: Optional[str] = None):
    """Shared by the API, seed_data.py and create_admin.py."""
    email = email.strip().lower()
    if db.query(User).filter(func.lower(User.email) == email).first():
        raise HTTPException(status_code=409, detail="That email address is already registered.")
    role = db.query(Role).filter(Role.name == RoleName.ADMIN).first()
    if role is None:
        role = Role(name=RoleName.ADMIN, label="Admin", description="Organisation administrator")
        db.add(role)
        db.flush()
    raw = password or generate_initial_password()
    user = User(email=email, hashed_password=hash_password(raw), role_id=role.id, is_active=True,
                must_change_password=password is None, full_name=full_name.strip(),
                phone=phone, title=title or "Administrator")
    db.add(user)
    db.flush()
    audit_service.record(db, AuditAction.ADMIN_CREATED, user=actor, entity_type="user",
                         entity_id=user.id, meta={"email": email})
    return user, raw


@router.get("/departments/overview")
def departments_overview(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    """Per department: head-count by type, HRs and managers in it, today's check-ins."""
    day = local_today()
    from app.models.work_session import WorkSession
    checked = {r[0] for r in db.query(WorkSession.user_id).filter(WorkSession.work_date == day).all()}
    out = []
    people = db.query(Employee).options(joinedload(Employee.user), joinedload(Employee.department)).all()
    for dept in db.query(Department).order_by(Department.name).all():
        members = [e for e in people if e.department_id == dept.id]
        counts = {"HR": 0, "Manager": 0, "Employee": 0, "Intern": 0}
        for e in members:
            counts[H.person_type(e)] += 1
        out.append({
            "id": dept.id, "name": dept.name, "code": dept.code, "is_active": dept.is_active,
            "total": len(members), "counts": counts,
            "checked_in_today": sum(1 for e in members if e.user_id in checked),
            "documents_pending": db.query(func.count(EmployeeDocument.id)).filter(
                EmployeeDocument.employee_id.in_([e.id for e in members] or [0]),
                EmployeeDocument.status == DocumentStatus.PENDING).scalar() or 0,
        })
    return {"items": out}
