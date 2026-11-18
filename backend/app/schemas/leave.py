from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from app.core.constants import LeaveType, LeaveStatus
from app.schemas.common import ORMModel


class LeaveRequestCreate(BaseModel):
    leave_type: str = Field(..., min_length=1, max_length=40)
    from_date: date
    to_date: date
    leave_period: Optional[str] = Field(None, max_length=20)
    reason: str = Field(..., min_length=3, max_length=3000)

    @model_validator(mode="after")
    def validate_dates(self):
        if self.from_date > self.to_date:
            raise ValueError("From date cannot be after To date.")
        return self


class LeaveReviewRequest(BaseModel):
    status: str
    hr_remarks: Optional[str] = Field(None, max_length=3000)

    @model_validator(mode="after")
    def validate_status(self):
        if self.status not in (LeaveStatus.APPROVED, LeaveStatus.REJECTED):
            raise ValueError("Status must be Approved or Rejected.")
        if self.status == LeaveStatus.REJECTED and not (self.hr_remarks or "").strip():
            raise ValueError("Please provide a reason when rejecting a leave request.")
        return self


class LeaveRequestOut(ORMModel):
    id: int
    employee_id: int
    employee_name: Optional[str] = None
    employee_code: Optional[str] = None
    department: Optional[str] = None
    internship_background: Optional[str] = None
    leave_type: str
    leave_type_label: Optional[str] = None
    leave_period: str = "Full Day"
    leave_period_label: Optional[str] = None
    duration_days: float = 0
    is_paid: bool = True
    from_date: date
    to_date: date
    reason: str
    status: str
    hr_remarks: Optional[str] = None
    requested_at: datetime
    reviewed_at: Optional[datetime] = None
    reviewed_by_id: Optional[int] = None
    reviewed_by_name: Optional[str] = None
    approval_stage: Optional[str] = None
    manager_status: Optional[str] = None
    manager_remarks: Optional[str] = None
    manager_reviewed_at: Optional[datetime] = None
    manager_reviewed_by_name: Optional[str] = None
    person_type: Optional[str] = None
    reporting_manager: Optional[str] = None
    can_act: bool = False


class LeaveSummary(BaseModel):
    pending: int
    approved: int
    rejected: int
    total: int
    awaiting_me: int = 0


LEAVE_TYPES = list(LeaveType.ALL)
