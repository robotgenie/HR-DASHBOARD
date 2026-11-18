from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from app.core.constants import LOCKED_IDENTITY_FIELDS, ProfileChangeStatus


class ProfileChangeRequestIn(BaseModel):
    field_name: str
    new_value: str = Field(min_length=1, max_length=255)
    reason: Optional[str] = Field(None, max_length=500)

    @field_validator("field_name")
    @classmethod
    def _field(cls, v: str) -> str:
        if v not in LOCKED_IDENTITY_FIELDS:
            raise ValueError(
                f"field_name must be one of: {', '.join(LOCKED_IDENTITY_FIELDS)}"
            )
        return v


class ProfileChangeReview(BaseModel):
    remarks: Optional[str] = Field(None, max_length=500)


class ProfileChangeRequestOut(BaseModel):
    id: int
    employee_id: int
    employee_name: Optional[str] = None
    employee_display_id: Optional[str] = None
    department: Optional[str] = None
    field_name: str
    field_label: str
    old_value: Optional[str] = None
    new_value: str
    reason: Optional[str] = None
    status: str
    hr_remarks: Optional[str] = None
    requested_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None
    reviewed_by: Optional[str] = None
    created_at: Optional[datetime] = None


class RequestableField(BaseModel):
    field_name: str
    label: str
    current_value: Optional[str] = None
    pending: bool = False


class ProfileLockState(BaseModel):
    identity_locked: bool
    identity_locked_at: Optional[datetime] = None
    fields: List[RequestableField] = []
    statuses: List[str] = list(ProfileChangeStatus.ALL)


class IdCardOut(BaseModel):
    available: bool
    id_card_status: str = "Pending"
    approval_remarks: Optional[str] = None
    missing_fields: List[str] = []
    unique_employee_id: Optional[str] = None
    issued_at: Optional[datetime] = None
    employee_id: int
    full_name: str
    employee_code: str
    department: Optional[str] = None
    internship_background: Optional[str] = None
    designation: str
    joining_date: Optional[date] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    photo_path: Optional[str] = None
    company_name: Optional[str] = None
    company_address: Optional[str] = None


class PayslipPermissionIn(BaseModel):
    allowed: bool
    remarks: Optional[str] = Field(None, max_length=300)


class PayslipPermissionResult(BaseModel):
    salary_id: int
    employee_id: int
    is_intern: bool
    intern_download_allowed: bool
    notification_created: bool = False
    detail: str


class DownloadRequestIn(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class DownloadRequestReview(BaseModel):
    remarks: Optional[str] = Field(None, max_length=500)


class DownloadRequestOut(BaseModel):
    id: int
    employee_id: int
    employee_name: Optional[str] = None
    employee_display_id: Optional[str] = None
    department: Optional[str] = None
    salary_id: int
    period_label: Optional[str] = None
    net_pay: Optional[str] = None
    has_payslip: bool = False
    reason: str
    status: str
    hr_remarks: Optional[str] = None
    hr_reviewer: Optional[str] = None
    requested_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
