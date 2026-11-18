"""Domain constants and status vocabularies shared across the application."""


class RoleName:
    """System roles.

    ADMIN    - organisation administrator. Not an employee: no employee record,
               no check-in/check-out. Monitors the whole organisation.
    HR_ADMIN - HR (stored name kept for backwards compatibility). An employee
               who also manages the hierarchy assigned to them.
    MANAGER  - an employee who supervises the employees/interns reporting to them.
    EMPLOYEE - employees and interns (interns = Internship department).
    """
    ADMIN = "ADMIN"
    HR_ADMIN = "HR_ADMIN"
    MANAGER = "MANAGER"
    EMPLOYEE = "EMPLOYEE"
    ALL = (ADMIN, HR_ADMIN, MANAGER, EMPLOYEE)
    # Roles that have an employee record and use the employee-side features.
    EMPLOYEE_SIDE = (HR_ADMIN, MANAGER, EMPLOYEE)
    LABELS = {
        ADMIN: "Admin",
        HR_ADMIN: "HR",
        MANAGER: "Manager",
        EMPLOYEE: "Employee",
    }
    # Higher number = higher in the hierarchy.
    LEVEL = {ADMIN: 4, HR_ADMIN: 3, MANAGER: 2, EMPLOYEE: 1}


class BankDetailStatus:
    """Lifecycle of one bank-details submission."""
    PENDING = "Pending Approval"
    APPROVED = "Approved"
    REJECTED = "Rejected"
    SUPERSEDED = "Superseded"     # replaced by a newer submission before review
    ALL = (PENDING, APPROVED, REJECTED, SUPERSEDED)


class ApprovalStage:
    """Who must act next on a pending leave request."""
    MANAGER = "Manager"
    HR = "HR"
    ADMIN = "Admin"
    CLOSED = "Closed"
    ALL = (MANAGER, HR, ADMIN, CLOSED)


class EmploymentStatus:
    ACTIVE = "Active"
    INACTIVE = "Inactive"
    ON_LEAVE = "On Leave"
    RESIGNED = "Resigned"
    TERMINATED = "Terminated"
    ALL = (ACTIVE, INACTIVE, ON_LEAVE, RESIGNED, TERMINATED)


class DocumentStatus:
    MISSING = "Missing"
    PENDING = "Pending"
    VERIFIED = "Verified"
    REJECTED = "Rejected"
    REUPLOAD_REQUESTED = "Re-upload Requested"
    ALL = (MISSING, PENDING, VERIFIED, REJECTED, REUPLOAD_REQUESTED)


class UanStatus:
    NOT_SUBMITTED = "Not Submitted"
    SUBMITTED = "Submitted"
    UNDER_VERIFICATION = "Under Verification"
    VERIFIED = "Verified"
    REJECTED = "Rejected"
    ALL = (NOT_SUBMITTED, SUBMITTED, UNDER_VERIFICATION, VERIFIED, REJECTED)


class SalaryStatus:
    PENDING = "Pending"
    PROCESSING = "Processing"
    CREDITED = "Credited"
    ALL = (PENDING, PROCESSING, CREDITED)


class ComponentType:
    EARNING = "earning"
    DEDUCTION = "deduction"
    ALL = (EARNING, DEDUCTION)


class MeetingStatus:
    SCHEDULED = "Scheduled"
    COMPLETED = "Completed"
    CANCELLED = "Cancelled"
    ALL = (SCHEDULED, COMPLETED, CANCELLED)


class ReportType:
    NOON = "Noon"
    EOD = "EOD"
    ALL = (NOON, EOD)


class ReportStatus:
    DRAFT = "Draft"
    SUBMITTED = "Submitted"
    REVIEWED = "Reviewed"
    ALL = (DRAFT, SUBMITTED, REVIEWED)


class WorkPeriod:
    FULL_DAY="Full Day"
    FIRST_HALF="First Half"
    SECOND_HALF="Second Half"
    HALF_DAY="Half Day"
    ALL=(FULL_DAY,FIRST_HALF,SECOND_HALF,HALF_DAY)

class DownloadRequestStatus:
    """Intern payslip download request lifecycle."""
    PENDING = "Pending"
    APPROVED = "Approved"
    REJECTED = "Rejected"
    ALL = (PENDING, APPROVED, REJECTED)


class ProfileChangeStatus:
    PENDING = "Pending"
    APPROVED = "Approved"
    REJECTED = "Rejected"
    ALL = (PENDING, APPROVED, REJECTED)


class LeaveStatus:
    PENDING = "Pending"
    APPROVED = "Approved"
    REJECTED = "Rejected"
    ALL = (PENDING, APPROVED, REJECTED)


class LeaveType:
    CASUAL = "Casual Leave"
    SICK = "Sick Leave"
    EARNED = "Earned Leave"
    UNPAID = "Unpaid Leave"
    OTHER = "Other"          # shown as "Other Leave"; stored value kept for existing rows
    HALF_DAY = "Half Day Leave"
    ALL = (CASUAL, SICK, EARNED, UNPAID, OTHER, HALF_DAY)
    # Leave that reduces payable days (loss of pay).
    UNPAID_TYPES = (UNPAID,)
    LABELS = {OTHER: "Other Leave"}


class LeavePeriod:
    """Which part of the office day an approved leave covers."""
    FULL_DAY = "Full Day"
    MORNING_HALF = "Morning Half"      # 10:00 AM - 1:00 PM
    AFTERNOON_HALF = "Afternoon Half"  # 1:00 PM - 6:00 PM
    ALL = (FULL_DAY, MORNING_HALF, AFTERNOON_HALF)
    HALVES = (MORNING_HALF, AFTERNOON_HALF)


class OfficeHours:
    """Company working day (IST). Every attendance/report rule reads these."""
    START = (10, 0)        # expected login
    MIDDAY = (13, 0)       # half-day boundary and Noon Report opening
    END = (18, 0)          # expected logout and EOD Report opening
    NOON_REPORT_OPENS = (13, 0)
    EOD_REPORT_OPENS = (18, 0)


class TaskStatus:
    PENDING = "Pending"
    IN_PROGRESS = "In Progress"
    COMPLETED = "Completed"
    CANCELLED = "Cancelled"
    ALL = (PENDING, IN_PROGRESS, COMPLETED, CANCELLED)
    OPEN = (PENDING, IN_PROGRESS)


# Hourly update periods inside the 10:00 AM - 6:00 PM working day.
HOURLY_SLOTS = [(h, h + 1) for h in range(10, 18)]


class AttendanceStatus:
    FULL_DAY = "Full Day"
    FIRST_HALF = "First Half"
    SECOND_HALF = "Second Half"
    FULL_DAY_LEAVE = "Full Day Leave"
    MORNING_HALF_LEAVE = "Morning Half Leave"
    AFTERNOON_HALF_LEAVE = "Afternoon Half Leave"
    ABSENT = "Absent"
    WEEKLY_OFF = "Weekly Off"
    UPCOMING = "Upcoming"


# Identity fields an employee may not edit once their profile is locked.
# Changing any of these needs an HR-approved profile change request.
LOCKED_IDENTITY_FIELDS = ("full_name", "phone", "email", "date_of_birth", "gender")

LOCKED_FIELD_LABELS = {
    "full_name": "Full Name",
    "phone": "Phone Number",
    "email": "Email ID",
    "date_of_birth": "Date of Birth",
    "gender": "Gender",
}

# Prefix and width of the unique employee id, e.g. RGEMP001
EMPLOYEE_ID_PREFIX = "RGEMP"
EMPLOYEE_ID_DIGITS = 3


class NotificationType:
    SALARY_CREDITED = "Salary Credited"
    SALARY_SLIP_AVAILABLE = "Salary Slip Available"
    DOCUMENT_VERIFIED = "Document Verified"
    DOCUMENT_REJECTED = "Document Rejected"
    REUPLOAD_REQUESTED = "Re-upload Requested"
    UAN_VERIFIED = "UAN Verified"
    UAN_REJECTED = "UAN Rejected"
    MEETING_REMINDER = "Meeting Reminder"
    DAILY_REPORT_REMINDER = "Daily Report Reminder"
    HR_ANNOUNCEMENT = "HR Announcement"
    ACCOUNT = "Account"
    EMPLOYEE_ID_ISSUED = "Employee ID Issued"
    PROFILE_CHANGE_REQUESTED = "Profile Change Requested"
    PROFILE_CHANGE_APPROVED = "Profile Change Approved"
    PROFILE_CHANGE_REJECTED = "Profile Change Rejected"
    LEAVE_REQUESTED = "Leave Request Submitted"
    LEAVE_APPROVED = "Leave Request Approved"
    LEAVE_REJECTED = "Leave Request Rejected"
    LATE_LOGIN = "Late Login"
    TASK_ASSIGNED = "Task Assigned"
    HOURLY_UPDATE_DUE = "Hourly Update Due"
    PAYSLIP_DOWNLOAD_GRANTED = "Payslip Download Granted"
    PAYSLIP_DOWNLOAD_REQUESTED = "Payslip Download Requested"
    PAYSLIP_DOWNLOAD_REJECTED = "Payslip Download Rejected"
    LEAVE_AWAITING_REVIEW = "Leave Awaiting Review"
    TASK_DIVIDED = "Task Divided"
    HIERARCHY_CHANGED = "Reporting Line Changed"
    BANK_DETAILS_SUBMITTED = "Bank Details Submitted"
    BANK_DETAILS_APPROVED = "Bank Details Approved"
    BANK_DETAILS_REJECTED = "Bank Details Rejected"
    SALARY_SLIP_GENERATED = "Salary Slip Generated"
    ALL = (
        SALARY_CREDITED, SALARY_SLIP_AVAILABLE, DOCUMENT_VERIFIED, DOCUMENT_REJECTED,
        REUPLOAD_REQUESTED, UAN_VERIFIED, UAN_REJECTED, MEETING_REMINDER,
        DAILY_REPORT_REMINDER, HR_ANNOUNCEMENT, ACCOUNT, EMPLOYEE_ID_ISSUED,
        PROFILE_CHANGE_REQUESTED, PROFILE_CHANGE_APPROVED, PROFILE_CHANGE_REJECTED,
        LEAVE_REQUESTED, LEAVE_APPROVED, LEAVE_REJECTED, LATE_LOGIN, TASK_ASSIGNED, HOURLY_UPDATE_DUE,
        PAYSLIP_DOWNLOAD_GRANTED, PAYSLIP_DOWNLOAD_REQUESTED, PAYSLIP_DOWNLOAD_REJECTED,
        LEAVE_AWAITING_REVIEW, TASK_DIVIDED, HIERARCHY_CHANGED,
        BANK_DETAILS_SUBMITTED, BANK_DETAILS_APPROVED, BANK_DETAILS_REJECTED, SALARY_SLIP_GENERATED,
    )


class EmailStatus:
    SENT = "sent"
    FAILED = "failed"
    LOGGED = "logged"  # SMTP not configured: written to the application log instead


class AuditAction:
    LOGIN = "login"
    LOGOUT = "logout"
    LIVE_SELFIE_LOGIN = "live_selfie_login"
    LIVE_SELFIE_LOGOUT = "live_selfie_logout"
    PASSWORD_RESET_REQUESTED = "password_reset_requested"
    PASSWORD_RESET_COMPLETED = "password_reset_completed"
    PASSWORD_CHANGED = "password_changed"
    EMPLOYEE_CREATED = "employee_created"
    EMPLOYEE_UPDATED = "employee_updated"
    EMPLOYEE_ACTIVATED = "employee_activated"
    EMPLOYEE_DEACTIVATED = "employee_deactivated"
    DEPARTMENT_CREATED = "department_created"
    DEPARTMENT_UPDATED = "department_updated"
    BACKGROUND_CREATED = "internship_background_created"
    BACKGROUND_UPDATED = "internship_background_updated"
    UAN_SUBMITTED = "uan_submitted"
    UAN_VERIFIED = "uan_verified"
    UAN_REJECTED = "uan_rejected"
    DOCUMENT_UPLOADED = "document_uploaded"
    DOCUMENT_VERIFIED = "document_verified"
    DOCUMENT_REJECTED = "document_rejected"
    DOCUMENT_REUPLOAD_REQUESTED = "document_reupload_requested"
    DOCUMENT_DELETE_DENIED = "document_delete_denied"
    DOCUMENT_DOWNLOADED = "document_downloaded"
    SALARY_CREATED = "salary_created"
    SALARY_UPDATED = "salary_updated"
    SALARY_CREDITED = "salary_credited"
    PAYSLIP_UPLOADED = "payslip_uploaded"
    PAYSLIP_GENERATED = "payslip_generated"
    NOTIFICATION_CREATED = "notification_created"
    EMAIL_SENT = "email_sent"
    MEETING_CREATED = "meeting_created"
    MEETING_UPDATED = "meeting_updated"
    MEETING_CANCELLED = "meeting_cancelled"
    REPORT_SUBMITTED = "daily_report_submitted"
    REPORT_REVIEWED = "daily_report_reviewed"
    SETTING_UPDATED = "setting_updated"
    EMPLOYEE_ID_GENERATED = "employee_id_generated"
    ID_CARD_GENERATED = "id_card_generated"
    PROFILE_CHANGE_REQUESTED = "profile_change_requested"
    PROFILE_CHANGE_APPROVED = "profile_change_approved"
    PROFILE_CHANGE_REJECTED = "profile_change_rejected"
    LEAVE_REQUESTED = "leave_requested"
    LEAVE_APPROVED = "leave_approved"
    LEAVE_REJECTED = "leave_rejected"
    PROFILE_LOCKED_EDIT_DENIED = "profile_locked_edit_denied"
    INTERN_PAYSLIP_PERMISSION_GRANTED = "intern_payslip_permission_granted"
    INTERN_PAYSLIP_PERMISSION_REVOKED = "intern_payslip_permission_revoked"
    INTERN_PAYSLIP_DOWNLOAD_DENIED = "intern_payslip_download_denied"
    INTERN_PAYSLIP_DOWNLOADED = "intern_payslip_downloaded"
    INTERN_PAYSLIP_DOWNLOAD_REQUESTED = "intern_payslip_download_requested"
    INTERN_PAYSLIP_REQUEST_APPROVED = "intern_payslip_request_approved"
    INTERN_PAYSLIP_REQUEST_REJECTED = "intern_payslip_request_rejected"
    REPORT_ATTACHMENT_MISSING = "daily_report_attachment_missing"
    REPORT_NOT_APPLICABLE = "daily_report_not_applicable"
    LOGOUT_BLOCKED = "logout_blocked"
    NOTIFICATION_DELETED = "notification_deleted"
    PHOTO_SUBMITTED = "profile_photo_submitted"
    EMPLOYEE_ID_AUTO_APPROVED = "employee_id_auto_approved"
    CHECK_IN = "attendance_check_in"
    CHECK_OUT = "attendance_check_out"
    CHECK_OUT_BLOCKED = "attendance_check_out_blocked"
    TASK_ASSIGNED = "task_assigned"
    TASK_UPDATED = "task_updated"
    HOURLY_UPDATE_SUBMITTED = "hourly_update_submitted"
    NOON_REPORT_FROM_HOURLY = "noon_report_satisfied_by_hourly_update"
    LEAVE_FORWARDED = "leave_forwarded_by_manager"
    TASK_DIVIDED = "task_divided"
    HIERARCHY_UPDATED = "hierarchy_updated"
    ROLE_CHANGED = "role_changed"
    ADMIN_CREATED = "admin_created"
    ADMIN_PROFILE_UPDATED = "admin_profile_updated"
    ACCESS_DENIED = "access_denied"
    EXCEL_TEMPLATE_DOWNLOADED = "excel_template_downloaded"
    EXCEL_IMPORT_PREVIEWED = "excel_import_previewed"
    EXCEL_IMPORT_CONFIRMED = "excel_import_confirmed"
    EXCEL_EXPORTED = "excel_exported"
    BANK_DETAILS_SUBMITTED = "bank_details_submitted"
    BANK_DETAILS_APPROVED = "bank_details_approved"
    BANK_DETAILS_REJECTED = "bank_details_rejected"
    BANK_DETAILS_VIEWED = "bank_details_viewed"
    SALARY_AUTO_GENERATED = "salary_auto_generated"
    SALARY_PAYSLIP_REFRESHED = "salary_payslip_refreshed"


# Settings keys stored in app_settings
class SettingKey:
    DAILY_REPORT_MANDATORY = "daily_report_mandatory"
    COMPANY_NAME = "company_name"
    COMPANY_ADDRESS = "company_address"
    COMPANY_UDYAM = "company_udyam"
    DEFAULT_WORK_LOCATION = "default_work_location"
    NOTIFY_ON_SALARY_CREDIT = "notify_on_salary_credit"
    NOTIFY_ON_DOCUMENT_REVIEW = "notify_on_document_review"
    EMAIL_ENABLED = "email_enabled"
    PAYSLIP_AUTO_GENERATE = "payslip_auto_generate"
    # When true, every HR can see (and claim) employees that have no reporting
    # HR yet. Admin can switch it off for strict HR-only hierarchies.
    HR_SEES_UNASSIGNED = "hr_sees_unassigned"
    # Create next month's salary record (salary slip) automatically from the
    # employee's latest one.
    SALARY_AUTO_GENERATE = "salary_auto_generate"


DEFAULT_DEPARTMENTS = [
    ("Teaching", "TEACH"),
    ("Marketing", "MKT"),
    ("Digital Marketing", "DMKT"),
    ("Managers", "MGR"),
    ("HR", "HR"),
    ("Internship", "INTERN"),
    ("Senior HR", "SRHR"),
    ("Finance", "FIN"),
]

INTERNSHIP_DEPARTMENT_NAME = "Internship"

DEFAULT_INTERNSHIP_BACKGROUNDS = [
    "Data Science", "Data Analytics", "Computer Science", "Cyber Security",
    "Artificial Intelligence", "Machine Learning", "Web Development",
    "Digital Marketing", "Human Resources", "Finance", "Other",
]

DEFAULT_DOCUMENT_TYPES = [
    ("Photograph", "PHOTO", True, "png,jpg,jpeg,webp"),
    ("Aadhaar Card", "AADHAAR", True, "pdf,png,jpg,jpeg"),
    ("PAN Card", "PAN", True, "pdf,png,jpg,jpeg"),
    ("Highest Qualification Certificate", "QUALIFICATION", False, "pdf,png,jpg,jpeg"),
    ("Experience Letter", "EXPERIENCE", False, "pdf,doc,docx"),
    ("CV / Resume", "CV", True, "pdf,doc,docx"),
    ("Other Supporting Document", "OTHER", False, "pdf,png,jpg,jpeg,doc,docx"),
]

# Payslip earnings are Basic + Incentive; HRA and Special Allowance are not part
# of the salary structure. "Other" stays so HR can add an ad-hoc line.
DEFAULT_EARNING_COMPONENTS = [
    "Basic", "Incentive", "Bonus", "Other",
]
DEFAULT_DEDUCTION_COMPONENTS = [
    "PT", "PF", "ESI", "Loan", "Other",
]
