from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)
    selfie_data: Optional[str] = None
    late_login_reason: Optional[str] = Field(None, max_length=500)
    work_period: Optional[str] = Field(None, max_length=20)


class LogoutRequest(BaseModel):
    selfie_data: Optional[str] = None
    logout_reason: Optional[str] = Field(None, max_length=500)


class UserSummary(BaseModel):
    id: int
    email: str
    role: str
    employee_id: Optional[int] = None
    employee_code: Optional[str] = None
    full_name: str
    designation: Optional[str] = None
    department: Optional[str] = None
    department_id: Optional[int] = None
    photo_path: Optional[str] = None
    role_label: Optional[str] = None
    # Which portal the account uses: admin | hr | manager | employee | intern
    portal: Optional[str] = None
    has_employee_record: bool = True
    reporting_manager: Optional[str] = None
    reporting_hr: Optional[str] = None


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    must_change_password: bool
    user: UserSummary
    home: str
    onboarding_required: bool = False
    onboarding_message: Optional[str] = None


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)
