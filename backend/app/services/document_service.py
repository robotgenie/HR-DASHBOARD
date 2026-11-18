"""Employee document workflow: versioned uploads and HR review.

Two rules are enforced here rather than in the UI:
  * an employee can never delete or overwrite a submitted document;
  * a new upload always creates a new version row, never mutates an old one.
"""
from datetime import datetime
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.utils.timeutil import utcnow
from app.core.constants import (
    AuditAction, DocumentStatus, NotificationType, SettingKey,
)
from app.models.document_type import DocumentType
from app.models.document_version import DocumentVersion
from app.models.employee import Employee
from app.models.employee_document import EmployeeDocument
from app.models.user import User
from app.services import (
    audit_service, email_service, file_service, notification_service, settings_service,
)

# Employees may replace a file only while it is in one of these states.
UPLOADABLE_STATUSES = {
    DocumentStatus.MISSING,
    DocumentStatus.REJECTED,
    DocumentStatus.REUPLOAD_REQUESTED,
}


def active_document_types(db: Session) -> List[DocumentType]:
    return (
        db.query(DocumentType)
        .filter(DocumentType.is_active.is_(True))
        .order_by(DocumentType.sort_order, DocumentType.id)
        .all()
    )


def checklist(db: Session, employee: Employee) -> List[dict]:
    """Every active document type with the employee's current state for it."""
    by_type = {d.document_type_id: d for d in employee.documents}
    rows = []
    for doc_type in active_document_types(db):
        record = by_type.get(doc_type.id)
        current = record.current_version if record else None
        rows.append(
            {
                "document_type_id": doc_type.id,
                "document_type": doc_type.name,
                "code": doc_type.code,
                "is_required": doc_type.is_required,
                "allowed_extensions": sorted(doc_type.extension_set),
                "max_size_mb": doc_type.max_size_mb,
                "document_id": record.id if record else None,
                "status": record.status if record else DocumentStatus.MISSING,
                "hr_remarks": record.hr_remarks if record else None,
                "version_count": record.version_count if record else 0,
                "uploaded_at": current.created_at if current else None,
                "original_filename": current.original_filename if current else None,
                "reviewed_at": record.reviewed_at if record else None,
            }
        )
    return rows


def completion(db: Session, employee: Employee) -> dict:
    """Completion counts only the document types marked required."""
    rows = [r for r in checklist(db, employee) if r["is_required"]]
    total = len(rows)
    uploaded = sum(1 for r in rows if r["status"] != DocumentStatus.MISSING)
    verified = sum(1 for r in rows if r["status"] == DocumentStatus.VERIFIED)
    percent = round((uploaded / total) * 100, 1) if total else 0.0
    return {
        "total_required": total,
        "uploaded": uploaded,
        "verified": verified,
        "pending": sum(1 for r in rows if r["status"] == DocumentStatus.PENDING),
        "rejected": sum(1 for r in rows if r["status"] == DocumentStatus.REJECTED),
        "missing": total - uploaded,
        "percent": percent,
        "label": f"{uploaded} / {total} Documents",
    }


def upload_version(
    db: Session,
    employee: Employee,
    document_type: DocumentType,
    content: bytes,
    original_filename: str,
    mime_type: str,
    content_hash: str,
    actor: User,
) -> DocumentVersion:
    """Add a new immutable version. Previous files stay on disk and in the DB."""
    record = (
        db.query(EmployeeDocument)
        .filter(
            EmployeeDocument.employee_id == employee.id,
            EmployeeDocument.document_type_id == document_type.id,
        )
        .first()
    )

    if record is None:
        record = EmployeeDocument(
            employee_id=employee.id,
            document_type_id=document_type.id,
            status=DocumentStatus.PENDING,
        )
        db.add(record)
        db.flush()
    elif record.status not in UPLOADABLE_STATUSES:
        if record.status == DocumentStatus.VERIFIED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This document is already verified. Ask HR to request a re-upload "
                       "if it needs to change.",
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This document is awaiting HR review and can't be replaced yet.",
        )

    next_version = (record.versions[-1].version_no + 1) if record.versions else 1
    stored = file_service.build_stored_name(
        f"{employee.employee_code}_{document_type.code}_v{next_version}", original_filename
    )
    file_service.save_bytes(file_service.DOCUMENTS, stored, content)

    version = DocumentVersion(
        employee_document_id=record.id,
        version_no=next_version,
        stored_filename=stored,
        original_filename=file_service.sanitise_filename(original_filename),
        mime_type=mime_type,
        file_size=len(content),
        content_hash=content_hash,
        status=DocumentStatus.PENDING,
        uploaded_by_id=actor.id,
    )
    db.add(version)

    record.status = DocumentStatus.PENDING
    record.hr_remarks = None
    record.reviewed_at = None
    record.reviewed_by_id = None
    db.flush()

    audit_service.record(
        db, AuditAction.DOCUMENT_UPLOADED, user=actor, entity_type="employee_document",
        entity_id=record.id,
        meta={
            "employee_id": employee.id,
            "document_type": document_type.name,
            "version": next_version,
            "size": len(content),
        },
    )
    return version


def _notify_review(
    db: Session, record: EmployeeDocument, actor: User, outcome: str, remarks: Optional[str]
) -> None:
    if not settings_service.get_bool(db, SettingKey.NOTIFY_ON_DOCUMENT_REVIEW, True):
        return

    employee = record.employee
    doc_name = record.document_type.name
    version_no = record.current_version.version_no if record.current_version else 0

    if outcome == DocumentStatus.VERIFIED:
        notification_service.create(
            db, user_id=employee.user_id, title=f"{doc_name} verified",
            message=f"HR has verified your {doc_name}.",
            type_=NotificationType.DOCUMENT_VERIFIED, related_entity="employee_document",
            related_id=record.id, dedupe_key=f"document:{record.id}:v{version_no}:verified",
            actor=actor,
        )
        if settings_service.get_bool(db, SettingKey.EMAIL_ENABLED, True):
            email_service.send_document_verified_email(
                db, employee.user.email, employee.full_name, doc_name, record.id,
                version_no, actor=actor,
            )
        return

    reupload = outcome == DocumentStatus.REUPLOAD_REQUESTED
    type_ = NotificationType.REUPLOAD_REQUESTED if reupload else NotificationType.DOCUMENT_REJECTED
    title = f"{doc_name} needs a new upload" if reupload else f"{doc_name} was rejected"
    key = "reupload" if reupload else "rejected"

    notification_service.create(
        db, user_id=employee.user_id, title=title,
        message=f"{remarks or 'Please upload a corrected copy.'}",
        type_=type_, related_entity="employee_document", related_id=record.id,
        dedupe_key=f"document:{record.id}:v{version_no}:{key}", actor=actor,
    )
    if settings_service.get_bool(db, SettingKey.EMAIL_ENABLED, True):
        email_service.send_document_rejected_email(
            db, employee.user.email, employee.full_name, doc_name,
            remarks or "Please upload a corrected copy.", record.id, version_no,
            reupload=reupload, actor=actor,
        )


def review(
    db: Session, record: EmployeeDocument, actor: User, outcome: str,
    remarks: Optional[str] = None,
) -> EmployeeDocument:
    """HR verifies, rejects or requests a re-upload of the current version."""
    if outcome not in {
        DocumentStatus.VERIFIED, DocumentStatus.REJECTED, DocumentStatus.REUPLOAD_REQUESTED
    }:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Unknown review outcome."
        )
    if not record.versions:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Nothing has been uploaded for this document yet.",
        )
    if outcome != DocumentStatus.VERIFIED and not (remarks or "").strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Add a remark so the employee knows what to fix.",
        )

    record.status = outcome
    record.hr_remarks = (remarks or "").strip() or None
    record.reviewed_by_id = actor.id
    record.reviewed_at = utcnow()

    current = record.current_version
    current.status = outcome
    if outcome == DocumentStatus.VERIFIED and record.document_type.code == "PHOTO":
        source = file_service.resolve_path(file_service.DOCUMENTS, current.stored_filename)
        if source.exists():
            photo_stored = file_service.build_stored_name(
                f"photo_{record.employee.employee_code}", current.original_filename
            )
            file_service.save_bytes(file_service.PHOTOS, photo_stored, source.read_bytes())
            # Only an HR-approved photo becomes the official profile / ID-card photo.
            record.employee.photo_path = photo_stored
            db.flush()
            from app.services import employee_service
            employee_service.auto_approve_hr_id(db, record.employee, actor=actor)
    current.hr_remarks = record.hr_remarks
    current.reviewed_by_id = actor.id
    current.reviewed_at = record.reviewed_at
    db.flush()

    action = {
        DocumentStatus.VERIFIED: AuditAction.DOCUMENT_VERIFIED,
        DocumentStatus.REJECTED: AuditAction.DOCUMENT_REJECTED,
        DocumentStatus.REUPLOAD_REQUESTED: AuditAction.DOCUMENT_REUPLOAD_REQUESTED,
    }[outcome]
    audit_service.record(
        db, action, user=actor, entity_type="employee_document", entity_id=record.id,
        meta={
            "employee_id": record.employee_id,
            "document_type": record.document_type.name,
            "version": current.version_no,
            "remarks": record.hr_remarks,
        },
    )
    _notify_review(db, record, actor, outcome, record.hr_remarks)
    return record
