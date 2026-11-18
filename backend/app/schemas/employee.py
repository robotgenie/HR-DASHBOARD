from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.constants import EmploymentStatus
from app.schemas.common import ORMModel


class DepartmentBase(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    code: str = Field(min_length=1, max_length=20)
    description: Optional[str] = None
    is_active: bool = True


class DepartmentCreate(DepartmentBase):
    pass


class DepartmentUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=120)
    code: Optional[str] = Field(None, min_length=1, max_length=20)
    description: Optional[str] = None
    is_active: Optional[bool] = None


class DepartmentOut(ORMModel, DepartmentBase):
    id: int
    employee_count: Optional[int] = None


class BackgroundBase(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: Optional[str] = None
    is_active: bool = True


class BackgroundCreate(BackgroundBase):
    pass


class BackgroundUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=120)
    description: Optional[str] = None
    is_active: Optional[bool] = None


class BackgroundOut(ORMModel, BackgroundBase):
    id: int


class EmployeeBase(BaseModel):
    full_name: str = Field(min_length=2, max_length=160)
    phone: Optional[str] = Field(None, max_length=20)
    date_of_birth: Optional[date] = None
    gender: Optional[str] = Field(None, max_length=20)
    department_id: int
    internship_background_id: Optional[int] = None
    designation: str = Field(min_length=2, max_length=120)
    joining_date: date
    reporting_manager_id: Optional[int] = None
    reporting_hr_id: Optional[int] = None
    internship_details: Optional[str] = Field(None, max_length=2000)
    employment_status: str = EmploymentStatus.ACTIVE
    work_location: Optional[str] = Field(None, max_length=120)
    address: Optional[str] = None
    emergency_contact_name: Optional[str] = Field(None, max_length=160)
    emergency_contact_phone: Optional[str] = Field(None, max_length=20)
    emergency_contact_relation: Optional[str] = Field(None, max_length=60)

    @field_validator("employment_status")
    @classmethod
    def _status(cls, v: str) -> str:
        if v not in EmploymentStatus.ALL:
            raise ValueError(f"Status must be one of {', '.join(EmploymentStatus.ALL)}")
        return v


class EmployeeCreate(EmployeeBase):
    email: EmailStr
    employee_code: Optional[str] = None
    # "Employee" or "Intern". Interns belong to the Internship department and
    # need an internship background; the department stays the source of truth.
    employee_type: Optional[str] = None
    role: Optional[str] = None
    send_account_email: bool = True


class EmployeeUpdate(BaseModel):
    """HR-editable fields. Employees get the narrower EmployeeSelfUpdate."""
    full_name: Optional[str] = Field(None, min_length=2, max_length=160)
    phone: Optional[str] = None
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    department_id: Optional[int] = None
    internship_background_id: Optional[int] = None
    designation: Optional[str] = None
    joining_date: Optional[date] = None
    reporting_manager_id: Optional[int] = None
    reporting_hr_id: Optional[int] = None
    role: Optional[str] = None
    internship_details: Optional[str] = Field(None, max_length=2000)
    employment_status: Optional[str] = None
    work_location: Optional[str] = Field(None, max_length=120)
    address: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    emergency_contact_relation: Optional[str] = None


class EmployeeSelfUpdate(BaseModel):
    """The only fields an employee may change on their own profile."""
    phone: Optional[str] = Field(None, max_length=20)
    address: Optional[str] = None
    emergency_contact_name: Optional[str] = Field(None, max_length=160)
    emergency_contact_phone: Optional[str] = Field(None, max_length=20)
    emergency_contact_relation: Optional[str] = Field(None, max_length=60)


class EmployeeListItem(BaseModel):
    id: int
    employee_code: str
    unique_employee_id: Optional[str] = None
    display_employee_id: Optional[str] = None
    full_name: str
    email: str
    department: Optional[str] = None
    department_id: Optional[int] = None
    internship_background: Optional[str] = None
    designation: str
    joining_date: date
    employment_status: str
    is_active: bool
    role: Optional[str] = None
    role_label: Optional[str] = None
    reporting_manager: Optional[str] = None
    reporting_manager_id: Optional[int] = None
    reporting_hr: Optional[str] = None
    reporting_hr_id: Optional[int] = None
    photo_path: Optional[str] = None
    document_completion: Optional[float] = None
    document_label: Optional[str] = None
    salary_status: Optional[str] = None


class EmployeeDetail(EmployeeListItem):
    phone: Optional[str] = None
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    address: Optional[str] = None
    work_location: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    emergency_contact_relation: Optional[str] = None
    reporting_chain: List[dict] = []
    internship_details: Optional[str] = None
    is_intern: bool = False
    uan_number: Optional[str] = None
    uan_status: Optional[str] = None
    uan_submitted_at: Optional[datetime] = None
    uan_remarks: Optional[str] = None
    profile_completion: Optional[float] = None
    profile_complete: bool = False
    profile_missing_fields: List[str] = []
    identity_locked: bool = False
    identity_locked_at: Optional[datetime] = None
    locked_fields: List[str] = []
    employee_id_issued_at: Optional[datetime] = None
    id_card_available: bool = False
    id_card_status: str = "Pending"
    id_card_requested_at: Optional[datetime] = None
    id_card_approved_at: Optional[datetime] = None
    id_card_rejected_at: Optional[datetime] = None
    id_card_approval_remarks: Optional[str] = None
    photo_status: Optional[str] = None
    pending_change_requests: int = 0
    created_at: Optional[datetime] = None


class EmployeeCreated(BaseModel):
    employee: EmployeeDetail
    initial_password: Optional[str] = None
    account_email_sent: bool = False
