from datetime import date, timedelta
from decimal import Decimal
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.api.serializers import (
    employee_list_item, latest_salary, meeting_out, profile_completion, salary_out,
)
from app.core.constants import DocumentStatus, LeaveStatus, ReportStatus, SalaryStatus, UanStatus
from app.core.dependencies import get_current_employee, get_current_user, require_hr
from app.database.database import get_db
from app.models.daily_report import DailyReport
from app.models.department import Department
from app.models.employee import Employee
from app.models.employee_document import EmployeeDocument
from app.models.meeting import Meeting
from app.models.notification import Notification
from app.models.salary import SalaryRecord
from app.models.uan import UanDetail
from app.models.user import User
from app.services import document_service, notification_service, report_service
from app.models.leave_request import LeaveRequest

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


def management_dashboard(db: Session, current_user: User) -> dict:
    """HR / Admin dashboard figures, limited to the viewer's hierarchy.

    Admin: the whole organisation. HR: their own hierarchy. Head-counts include
    the viewer; pending-action counts only include records the viewer can act
    on (never their own).
    """
    from app.services import hierarchy_service as H

    today = date.today()
    month_ago = today - timedelta(days=30)
    seen = H.visible_ids_select(db, current_user, include_self=True)
    acted = H.visible_ids_select(db, current_user, include_self=False)

    def in_scope(query, column, ids=seen):
        return query if ids is None else query.filter(column.in_(ids))

    total_employees = in_scope(db.query(func.count(Employee.id)), Employee.id).scalar() or 0
    active_employees = (
        in_scope(db.query(func.count(Employee.id)), Employee.id)
        .join(User, Employee.user_id == User.id)
        .filter(User.is_active.is_(True), Employee.employment_status == "Active")
        .scalar() or 0
    )
    new_employees = (
        in_scope(db.query(func.count(Employee.id)), Employee.id)
        .filter(Employee.joining_date >= month_ago)
        .scalar() or 0
    )

    doc_counts = dict(
        in_scope(db.query(EmployeeDocument.status, func.count(EmployeeDocument.id)),
                 EmployeeDocument.employee_id, acted)
        .group_by(EmployeeDocument.status)
        .all()
    )
    uan_pending = (
        in_scope(db.query(func.count(UanDetail.id)), UanDetail.employee_id, acted)
        .filter(UanDetail.status.in_([UanStatus.SUBMITTED, UanStatus.UNDER_VERIFICATION]))
        .scalar() or 0
    )
    reports_pending = (
        in_scope(db.query(func.count(DailyReport.id)), DailyReport.employee_id, acted)
        .filter(DailyReport.status == ReportStatus.SUBMITTED)
        .scalar() or 0
    )
    leave_pending = (
        db.query(func.count(LeaveRequest.id))
        .filter(H.leave_actionable_filter(db, current_user))
        .scalar() or 0
    )
    salary_counts = dict(
        in_scope(db.query(SalaryRecord.status, func.count(SalaryRecord.id)),
                 SalaryRecord.employee_id, acted)
        .group_by(SalaryRecord.status)
        .all()
    )
    payroll_total = (
        in_scope(db.query(func.coalesce(func.sum(SalaryRecord.net_pay), 0)), SalaryRecord.employee_id, acted)
        .filter(SalaryRecord.period_year == today.year, SalaryRecord.period_month == today.month)
        .scalar() or Decimal("0")
    )

    dept_join = Employee.department_id == Department.id
    if seen is not None:
        dept_join = (Employee.department_id == Department.id) & Employee.id.in_(seen)
    by_department = [
        {"department": name, "count": count}
        for name, count in db.query(Department.name, func.count(Employee.id))
        .outerjoin(Employee, dept_join)
        .group_by(Department.name)
        .order_by(func.count(Employee.id).desc())
        .all()
    ]

    recent = (
        in_scope(db.query(Employee), Employee.id)
        .options(joinedload(Employee.user), joinedload(Employee.department))
        .order_by(Employee.created_at.desc(), Employee.id.desc())
        .limit(6)
        .all()
    )
    meetings_today = (
        db.query(Meeting)
        .options(joinedload(Meeting.department))
        .filter(Meeting.meeting_date == today)
        .order_by(Meeting.start_time)
        .all()
    )

    from app.models.work_session import WorkSession
    from app.services import attendance_service
    from app.utils.clock import local_today, to_local
    today_local = local_today()
    late_today = (
        in_scope(
            db.query(WorkSession, Employee).join(Employee, Employee.user_id == WorkSession.user_id),
            Employee.id, acted,
        )
        .filter(WorkSession.work_date == today_local, WorkSession.late_login_minutes > 0)
        .order_by(WorkSession.login_at)
        .all()
    )
    late_logins_today = [
        {
            "employee_id": e.id, "employee_name": e.full_name,
            "employee_code": e.display_employee_id,
            "department": e.department.name if e.department else None,
            "date": s.work_date,
            "expected_login": attendance_service.fmt_time(s.expected_login_time) or "10:00",
            "actual_login": to_local(s.login_at).strftime("%H:%M"),
            "late_minutes": s.late_login_minutes,
            "late_label": attendance_service.minutes_label(s.late_login_minutes),
            "late_reason": s.late_login_reason,
        }
        for s, e in late_today
    ]

    report_status = []
    for st in ReportStatus.ALL:
        report_status.append({
            "status": st,
            "count": in_scope(db.query(func.count(DailyReport.id)), DailyReport.employee_id, acted)
            .filter(DailyReport.status == st).scalar() or 0,
        })

    return {
        "scope": "organisation" if seen is None else "hierarchy",
        "late_logins_today": late_logins_today,
        "kpis": {
            "late_logins_today": len(late_logins_today),
            "total_employees": total_employees,
            "active_employees": active_employees,
            "new_employees": new_employees,
            "documents_pending": doc_counts.get(DocumentStatus.PENDING, 0),
            "documents_verified": doc_counts.get(DocumentStatus.VERIFIED, 0),
            "documents_rejected": doc_counts.get(DocumentStatus.REJECTED, 0),
            "uan_pending": uan_pending,
            "reports_pending": reports_pending,
            "leave_pending": leave_pending,
            "salary_pending": salary_counts.get(SalaryStatus.PENDING, 0),
            "salary_processing": salary_counts.get(SalaryStatus.PROCESSING, 0),
            "salary_credited": salary_counts.get(SalaryStatus.CREDITED, 0),
            "monthly_payroll": float(payroll_total),
        },
        "charts": {
            "employees_by_department": by_department,
            "document_status": [
                {"status": s, "count": doc_counts.get(s, 0)}
                for s in (
                    DocumentStatus.PENDING, DocumentStatus.VERIFIED,
                    DocumentStatus.REJECTED, DocumentStatus.REUPLOAD_REQUESTED,
                )
            ],
            "salary_status": [
                {"status": s, "count": salary_counts.get(s, 0)} for s in SalaryStatus.ALL
            ],
            "report_status": report_status,
        },
        "pending_actions": [
            {"label": "documents awaiting verification",
             "count": doc_counts.get(DocumentStatus.PENDING, 0), "link": "documents.html"},
            {"label": "work reports to review", "count": reports_pending,
             "link": "work-reports.html"},
            {"label": "leave requests to review", "count": leave_pending,
             "link": "leave-requests.html"},
            {"label": "UANs awaiting verification", "count": uan_pending, "link": "uan.html"},
            {"label": "salaries not yet credited",
             "count": salary_counts.get(SalaryStatus.PENDING, 0), "link": "salary.html"},
        ],
        "recent_employees": [employee_list_item(db, e, with_docs=False) for e in recent],
        "todays_meetings": [meeting_out(m) for m in meetings_today],
    }


@router.get("/hr")
def hr_dashboard(db: Session = Depends(get_db), current_user: User = Depends(require_hr)):
    return management_dashboard(db, current_user)


@router.get("/employee")
def employee_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    employee: Employee = Depends(get_current_employee),
):
    today = date.today()
    completion = document_service.completion(db, employee)
    salary = latest_salary(employee)

    meetings_today = (
        db.query(Meeting)
        .options(joinedload(Meeting.department))
        .filter(
            Meeting.department_id == employee.department_id,
            Meeting.meeting_date == today,
        )
        .order_by(Meeting.start_time)
        .all()
    )
    notifications = (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(5)
        .all()
    )
    uan = employee.uan

    return {
        "employee": {
            "id": employee.id,
            "full_name": employee.full_name,
            "employee_code": employee.employee_code,
            "designation": employee.designation,
            "department": employee.department.name if employee.department else None,
            "internship_background": (
                employee.internship_background.name if employee.internship_background else None
            ),
            "photo_path": employee.photo_path,
        },
        "kpis": {
            "profile_completion": profile_completion(employee),
            "documents_uploaded": completion["uploaded"],
            "documents_total": completion["total_required"],
            "documents_percent": completion["percent"],
            "documents_label": completion["label"],
            "salary_period": salary.period_label if salary else None,
            "salary_status": salary.status if salary else "No salary records yet",
            "unread_notifications": notification_service.unread_count(db, current_user.id),
            "uan_status": uan.status if uan else UanStatus.NOT_SUBMITTED,
        },
        "document_progress": document_service.checklist(db, employee),
        "latest_salary": salary_out(salary) if salary else None,
        "todays_meetings": [meeting_out(m) for m in meetings_today],
        "recent_notifications": [
            {
                "id": n.id, "title": n.title, "message": n.message, "type": n.type,
                "is_read": n.is_read, "created_at": n.created_at,
            }
            for n in notifications
        ],
        "daily_report": report_service.logout_requirements(db, employee),
    }
