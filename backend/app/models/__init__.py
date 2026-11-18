"""Import every model so SQLAlchemy's registry (and Alembic autogenerate) sees them."""
from app.models.app_setting import AppSetting
from app.models.bank_detail_request import BankDetailRequest
from app.models.audit_log import AuditLog
from app.models.daily_report import DailyReport
from app.models.department import Department
from app.models.document_type import DocumentType
from app.models.document_version import DocumentVersion
from app.models.email_log import EmailLog
from app.models.employee import Employee
from app.models.employee_document import EmployeeDocument
from app.models.excel_import_batch import ExcelImportBatch
from app.models.internship_background import InternshipBackground
from app.models.leave_request import LeaveRequest
from app.models.meeting import Meeting
from app.models.notification import Notification
from app.models.intern_payslip_request import InternPayslipDownloadRequest
from app.models.password_reset import PasswordResetToken
from app.models.profile_change_request import ProfileChangeRequest
from app.models.report_attachment import ReportAttachment
from app.models.role import Role
from app.models.salary import SalaryRecord
from app.models.salary_component import SalaryComponent
from app.models.salary_slip import SalarySlip
from app.models.uan import UanDetail
from app.models.user import User
from app.models.work_session import WorkSession
from app.models.work_task import WorkTask
from app.models.hourly_update import HourlyUpdate, HourlyUpdateAttachment

__all__ = [
    "AppSetting", "AuditLog", "BankDetailRequest", "DailyReport", "Department", "DocumentType",
    "DocumentVersion", "EmailLog", "Employee", "EmployeeDocument",
    "ExcelImportBatch", "InternshipBackground", "LeaveRequest", "Meeting", "Notification", "PasswordResetToken",
    "InternPayslipDownloadRequest", "ProfileChangeRequest", "ReportAttachment", "Role", "SalaryRecord", "SalaryComponent", "SalarySlip",
    "UanDetail", "User", "WorkSession", "WorkTask", "HourlyUpdate", "HourlyUpdateAttachment",
]
