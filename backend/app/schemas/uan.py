from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class UanSubmitRequest(BaseModel):
    uan_number: str = Field(min_length=12, max_length=12, pattern=r"^\d{12}$")


class UanReviewRequest(BaseModel):
    remarks: Optional[str] = Field(None, max_length=1000)


class UanOut(BaseModel):
    id: int
    employee_id: int
    employee_name: Optional[str] = None
    employee_code: Optional[str] = None
    department: Optional[str] = None
    uan_number: Optional[str] = None
    status: str
    submitted_at: Optional[datetime] = None
    hr_remarks: Optional[str] = None
    verified_at: Optional[datetime] = None
