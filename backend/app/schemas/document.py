from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class DocumentTypeOut(ORMModel):
    id: int
    name: str
    code: str
    is_required: bool
    is_active: bool
    sort_order: int
    allowed_extensions: str
    max_size_mb: int


class DocumentTypeUpdate(BaseModel):
    name: Optional[str] = None
    is_required: Optional[bool] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None
    allowed_extensions: Optional[str] = None
    max_size_mb: Optional[int] = Field(None, ge=1, le=50)


class DocumentVersionOut(ORMModel):
    id: int
    version_no: int
    original_filename: str
    mime_type: str
    file_size: int
    status: str
    hr_remarks: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime


class ChecklistItem(BaseModel):
    document_type_id: int
    document_type: str
    code: str
    is_required: bool
    allowed_extensions: List[str]
    max_size_mb: int
    document_id: Optional[int] = None
    status: str
    hr_remarks: Optional[str] = None
    version_count: int = 0
    uploaded_at: Optional[datetime] = None
    original_filename: Optional[str] = None
    reviewed_at: Optional[datetime] = None


class DocumentCompletion(BaseModel):
    total_required: int
    uploaded: int
    verified: int
    pending: int
    rejected: int
    missing: int
    percent: float
    label: str


class EmployeeDocumentsResponse(BaseModel):
    employee_id: int
    employee_name: str
    completion: DocumentCompletion
    items: List[ChecklistItem]


class DocumentReviewRequest(BaseModel):
    remarks: Optional[str] = Field(None, max_length=1000)


class DocumentRow(BaseModel):
    """A row on the HR documents queue."""
    document_id: int
    employee_id: int
    employee_name: str
    employee_code: str
    department: Optional[str] = None
    document_type: str
    status: str
    hr_remarks: Optional[str] = None
    version_count: int
    uploaded_at: Optional[datetime] = None
    original_filename: Optional[str] = None
    reviewed_at: Optional[datetime] = None
