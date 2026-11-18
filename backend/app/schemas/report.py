from datetime import date, datetime
from datetime import date as _date
from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class ReportAttachmentOut(ORMModel):
    id: int
    original_filename: str
    mime_type: str
    file_size: int
    created_at: datetime


class DailyReportIn(BaseModel):
    report_type: str = "EOD"
    report_date: Optional[date] = None
    tasks_completed: Optional[str] = Field(None, max_length=5000)
    tasks_in_progress: Optional[str] = Field(None, max_length=5000)
    tasks_pending: Optional[str] = Field(None, max_length=5000)
    work_summary: Optional[str] = Field(None, max_length=5000)
    challenges: Optional[str] = Field(None, max_length=5000)
    additional_comments: Optional[str] = Field(None, max_length=5000)
    submit: bool = True


class DailyReportOut(BaseModel):
    id: int
    employee_id: int
    employee_name: Optional[str] = None
    person_type: Optional[str] = None
    reviewed_by_name: Optional[str] = None
    employee_code: Optional[str] = None
    department: Optional[str] = None
    report_date: date
    report_type: str = "EOD"
    tasks_completed: Optional[str] = None
    tasks_in_progress: Optional[str] = None
    tasks_pending: Optional[str] = None
    work_summary: Optional[str] = None
    challenges: Optional[str] = None
    additional_comments: Optional[str] = None
    status: str
    source: Optional[str] = "Manual"
    submitted_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None
    review_notes: Optional[str] = None
    attachments: List[ReportAttachmentOut] = []


class ReportReviewRequest(BaseModel):
    review_notes: Optional[str] = Field(None, max_length=2000)


class LogoutRequirements(BaseModel):
    date: Optional[_date] = None     # today's office (IST) date
    report_mandatory: bool
    report_submitted_today: bool
    report_status: str
    submitted_at: Optional[datetime] = None
    attachment_count: int = 0
    attachment_required: bool = True
    logout_blocked: bool
    noon_submitted: bool = False
    eod_submitted: bool = False
    noon_available: bool = False
    eod_available: bool = False
    missing_reports: List[str] = []
    blocked_message: Optional[str] = None
    pending_actions: List[str] = []
    noon_required: bool = True
    eod_required: bool = True
    noon_blocked_reason: Optional[str] = None
    eod_blocked_reason: Optional[str] = None
    noon_status: Optional[str] = None
    eod_status: Optional[str] = None
    leave_period: Optional[str] = None
    leave_status: Optional[str] = None
    expected_login: Optional[str] = None
    expected_logout: Optional[str] = None
    noon_attachment_required: bool = False
    noon_attachment_count: int = 0
    noon_source: Optional[str] = None
