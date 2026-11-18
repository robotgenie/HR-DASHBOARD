"""Router registry."""
from fastapi import APIRouter

from app.api import (
    audit_logs, auth, dashboard, departments, documents, employees,
    intern_payslip_requests, internship_backgrounds, meetings, notifications,
    profile_change_requests, reports, salaries, settings, uan, leave_requests, attendance,
    tasks, hourly_updates, hierarchy, admin, excel, bank_details,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(dashboard.router)
api_router.include_router(employees.router)
api_router.include_router(profile_change_requests.router)
api_router.include_router(departments.router)
api_router.include_router(internship_backgrounds.router)
api_router.include_router(documents.router)
api_router.include_router(uan.router)
api_router.include_router(salaries.router)
api_router.include_router(intern_payslip_requests.router)
api_router.include_router(notifications.router)
api_router.include_router(meetings.router)
api_router.include_router(reports.router)
api_router.include_router(leave_requests.router)
api_router.include_router(audit_logs.router)
api_router.include_router(settings.router)

api_router.include_router(attendance.router)
api_router.include_router(tasks.router)
api_router.include_router(hourly_updates.router)
api_router.include_router(hierarchy.router)
api_router.include_router(admin.router)
api_router.include_router(excel.router)
api_router.include_router(bank_details.router)
