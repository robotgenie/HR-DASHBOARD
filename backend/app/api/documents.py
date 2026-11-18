from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.core.constants import AuditAction, DocumentStatus
from app.core.dependencies import (
    assert_can_access_employee, get_current_employee, get_current_user, is_hr, require_hr,
)
from app.database.database import get_db
from app.models.document_type import DocumentType
from app.models.document_version import DocumentVersion
from app.models.employee import Employee
from app.models.employee_document import EmployeeDocument
from app.models.user import User
from app.schemas.common import Page, paginate
from app.schemas.document import (
    ChecklistItem, DocumentCompletion, DocumentReviewRequest, DocumentRow,
    DocumentTypeOut, DocumentTypeUpdate, DocumentVersionOut, EmployeeDocumentsResponse,
)
from app.services import (
    audit_service, document_service, employee_service, file_service, hierarchy_service,
)

router = APIRouter(prefix="/documents", tags=["Documents"])


# ---------------------------------------------------------------- document types
@router.get("/types", response_model=List[DocumentTypeOut])
def list_document_types(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    return (
        db.query(DocumentType)
        .order_by(DocumentType.sort_order, DocumentType.id)
        .all()
    )


@router.put("/types/{type_id}", response_model=DocumentTypeOut)
def update_document_type(
    type_id: int,
    payload: DocumentTypeUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr),
):
    doc_type = db.query(DocumentType).filter(DocumentType.id == type_id).first()
    if doc_type is None:
        raise HTTPException(status_code=404, detail="Document type not found.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(doc_type, field, value)
    db.flush()
    audit_service.record(
        db, AuditAction.SETTING_UPDATED, user=current_user, entity_type="document_type",
        entity_id=doc_type.id, meta={"name": doc_type.name},
    )
    db.commit()
    db.refresh(doc_type)
    return doc_type


# ---------------------------------------------------------------- employee views
@router.get("/me", response_model=EmployeeDocumentsResponse)
def my_documents(
    db: Session = Depends(get_db), employee: Employee = Depends(get_current_employee)
):
    return EmployeeDocumentsResponse(
        employee_id=employee.id,
        employee_name=employee.full_name,
        completion=DocumentCompletion(**document_service.completion(db, employee)),
        items=[ChecklistItem(**row) for row in document_service.checklist(db, employee)],
    )


@router.get("/employee/{employee_id}", response_model=EmployeeDocumentsResponse)
def employee_documents(
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    employee = assert_can_access_employee(current_user, employee_id, db)
    return EmployeeDocumentsResponse(
        employee_id=employee.id,
        employee_name=employee.full_name,
        completion=DocumentCompletion(**document_service.completion(db, employee)),
        items=[ChecklistItem(**row) for row in document_service.checklist(db, employee)],
    )


@router.post("/upload", response_model=ChecklistItem, status_code=status.HTTP_201_CREATED)
async def upload_document(
    document_type_id: int = Form(...),
    employee_id: Optional[int] = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Employees upload for themselves; HR may upload on an employee's behalf."""
    own = current_user.employee
    if employee_id is not None and is_hr(current_user) and (own is None or own.id != employee_id):
        employee = assert_can_access_employee(current_user, employee_id, db, level="manage")
    else:
        employee = db.query(Employee).filter(Employee.user_id == current_user.id).first()
        if employee is None:
            raise HTTPException(status_code=404, detail="No employee profile on this account.")

    doc_type = db.query(DocumentType).filter(DocumentType.id == document_type_id).first()
    if doc_type is None or not doc_type.is_active:
        raise HTTPException(status_code=404, detail="Document type not found.")

    content, ext, mime, digest = await file_service.validate_and_read(
        file,
        allowed_extensions=doc_type.extension_set,
        max_size=doc_type.max_size_mb * 1024 * 1024,
    )
    document_service.upload_version(
        db, employee, doc_type, content, file.filename, mime, digest, current_user
    )
    # A Photograph document is also the canonical profile/ID-card photo.
    # Re-check profile completion so uploading the photo can issue the same
    # RGEMP ID and electronic ID card as the dedicated profile-photo flow.
    employee_service.issue_employee_id(db, employee, actor=current_user)
    db.commit()

    row = next(
        r for r in document_service.checklist(db, employee)
        if r["document_type_id"] == doc_type.id
    )
    return ChecklistItem(**row)


# ---------------------------------------------------------------- HR queue
@router.get("", response_model=Page[DocumentRow])
def document_queue(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    status_filter: Optional[str] = Query(None, alias="status"),
    department_id: Optional[int] = None,
    employee_id: Optional[int] = None,
    search: Optional[str] = None,
    reporting_hr_id: Optional[int] = None,
    reporting_manager_id: Optional[int] = None,
    document_type_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr),
):
    """Verification queue: Admin everyone (incl. HR), HR their hierarchy
    (never their own documents - the Admin verifies those)."""
    query = (
        db.query(EmployeeDocument)
        .join(Employee, EmployeeDocument.employee_id == Employee.id)
        .options(
            joinedload(EmployeeDocument.employee).joinedload(Employee.department),
            joinedload(EmployeeDocument.document_type),
            joinedload(EmployeeDocument.versions),
        )
    )
    query = hierarchy_service.restrict_managed(query, db, current_user, Employee.id)
    if status_filter and status_filter.lower() != "all":
        query = query.filter(EmployeeDocument.status == status_filter)
    if employee_id:
        query = query.filter(EmployeeDocument.employee_id == employee_id)
    if reporting_hr_id:
        query = query.filter(Employee.reporting_hr_id == reporting_hr_id)
    if reporting_manager_id:
        query = query.filter(Employee.reporting_manager_id == reporting_manager_id)
    if document_type_id:
        query = query.filter(EmployeeDocument.document_type_id == document_type_id)
    if department_id:
        query = query.filter(Employee.department_id == department_id)
    if search:
        needle = f"%{search.strip()}%"
        query = query.filter(
            or_(Employee.full_name.ilike(needle), Employee.employee_code.ilike(needle))
        )

    query = query.order_by(EmployeeDocument.updated_at.desc())
    records, meta = paginate(query, page, page_size)

    rows = []
    for record in records:
        current = record.current_version
        rows.append(
            DocumentRow(
                document_id=record.id,
                employee_id=record.employee_id,
                employee_name=record.employee.full_name,
                employee_code=record.employee.employee_code,
                department=record.employee.department.name if record.employee.department else None,
                document_type=record.document_type.name,
                status=record.status,
                hr_remarks=record.hr_remarks,
                version_count=record.version_count,
                uploaded_at=current.created_at if current else None,
                original_filename=current.original_filename if current else None,
                reviewed_at=record.reviewed_at,
            )
        )
    return Page[DocumentRow](items=rows, meta=meta)


def _load_document(db: Session, document_id: int, user: User, level: str = "sensitive") -> EmployeeDocument:
    record = (
        db.query(EmployeeDocument)
        .options(
            joinedload(EmployeeDocument.employee),
            joinedload(EmployeeDocument.document_type),
            joinedload(EmployeeDocument.versions),
        )
        .filter(EmployeeDocument.id == document_id)
        .first()
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    # Hierarchy check: employee B can never reach employee A's document by ID,
    # a Manager sees team document *status* only (checklist), never the files.
    assert_can_access_employee(user, record.employee_id, db, level=level)
    return record


@router.get("/{document_id}/versions", response_model=List[DocumentVersionOut])
def document_versions(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    record = _load_document(db, document_id, current_user)
    return record.versions


@router.get("/{document_id}/download")
def download_document(
    document_id: int,
    version: Optional[int] = None,
    inline: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Authenticated, ownership-checked streaming. Files are never public."""
    record = _load_document(db, document_id, current_user)
    if not record.versions:
        raise HTTPException(status_code=404, detail="Nothing uploaded yet.")

    target: DocumentVersion = record.current_version
    if version is not None:
        target = next((v for v in record.versions if v.version_no == version), None)
        if target is None:
            raise HTTPException(status_code=404, detail="That version doesn't exist.")

    path = file_service.resolve_path(file_service.DOCUMENTS, target.stored_filename)
    if not path.exists():
        raise HTTPException(status_code=404, detail="The stored file is missing.")

    audit_service.record(
        db, AuditAction.DOCUMENT_DOWNLOADED, user=current_user,
        entity_type="employee_document", entity_id=record.id,
        meta={"version": target.version_no}, commit=True,
    )

    disposition = "inline" if inline else "attachment"
    return StreamingResponse(
        iter([path.read_bytes()]),
        media_type=target.mime_type,
        headers={
            "Content-Disposition": f'{disposition}; filename="{target.original_filename}"'
        },
    )


@router.post("/{document_id}/verify", response_model=DocumentRow)
def verify_document(
    document_id: int,
    payload: DocumentReviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr),
):
    record = _load_document(db, document_id, current_user, level="manage")
    document_service.review(db, record, current_user, DocumentStatus.VERIFIED, payload.remarks)
    db.commit()
    return _row(record)


@router.post("/{document_id}/reject", response_model=DocumentRow)
def reject_document(
    document_id: int,
    payload: DocumentReviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr),
):
    record = _load_document(db, document_id, current_user, level="manage")
    document_service.review(db, record, current_user, DocumentStatus.REJECTED, payload.remarks)
    db.commit()
    return _row(record)


@router.post("/{document_id}/request-reupload", response_model=DocumentRow)
def request_reupload(
    document_id: int,
    payload: DocumentReviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr),
):
    record = _load_document(db, document_id, current_user, level="manage")
    document_service.review(
        db, record, current_user, DocumentStatus.REUPLOAD_REQUESTED, payload.remarks
    )
    db.commit()
    return _row(record)


@router.delete("/{document_id}", status_code=status.HTTP_403_FORBIDDEN)
def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Submitted documents are permanent.

    The route exists purely to answer 403 and leave an audit trail. Nothing is
    ever removed here -- not by an employee, and not by HR. Document history is
    part of the compliance record.
    """
    record = _load_document(db, document_id, current_user, level="view")
    audit_service.record(
        db, AuditAction.DOCUMENT_DELETE_DENIED, user=current_user,
        entity_type="employee_document", entity_id=record.id,
        meta={
            "employee_id": record.employee_id,
            "document_type": record.document_type.name,
            "attempted_by_role": current_user.role_name,
        },
        commit=True,
    )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Submitted documents can't be deleted. Ask HR to request a re-upload "
               "if this document needs to change.",
    )


def _row(record: EmployeeDocument) -> DocumentRow:
    current = record.current_version
    return DocumentRow(
        document_id=record.id,
        employee_id=record.employee_id,
        employee_name=record.employee.full_name,
        employee_code=record.employee.employee_code,
        department=record.employee.department.name if record.employee.department else None,
        document_type=record.document_type.name,
        status=record.status,
        hr_remarks=record.hr_remarks,
        version_count=record.version_count,
        uploaded_at=current.created_at if current else None,
        original_filename=current.original_filename if current else None,
        reviewed_at=record.reviewed_at,
    )
