"""Excel import (template -> preview -> confirm -> error report) and exports.

Import: Admin and HR (HR only inside their own hierarchy).
Export: Admin everything, HR their hierarchy, Manager their team (no salary),
employees / interns their own records. Every operation is audit-logged with
counts and filters only - never file contents.
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.constants import AuditAction
from app.core.dependencies import get_current_user, require_hr
from app.database.database import get_db
from app.models.user import User
from app.services import audit_service, excel_service

router = APIRouter(prefix="/excel", tags=["Excel import / export"])

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _xlsx(content: bytes, filename: str) -> StreamingResponse:
    return StreamingResponse(iter([content]), media_type=XLSX,
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/template")
def download_template(db: Session = Depends(get_db), current_user: User = Depends(require_hr)):
    content = excel_service.build_template(db, current_user)
    audit_service.record(db, AuditAction.EXCEL_TEMPLATE_DOWNLOADED, user=current_user,
                         entity_type="excel", entity_id=None, meta={}, commit=True)
    return _xlsx(content, "employee_import_template.xlsx")


@router.post("/import/preview")
async def import_preview(
    file: UploadFile = File(...),
    mode: str = Form("auto"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr),
):
    name = file.filename or "import.xlsx"
    if not name.lower().endswith(".xlsx"):
        raise HTTPException(status_code=422, detail="Upload an .xlsx file (Excel 2007 or later).")
    content = await file.read()
    batch = excel_service.preview(db, current_user, name, content, mode)
    db.commit()
    return excel_service.public_preview(batch)


@router.get("/import/{token}")
def import_status(token: str, db: Session = Depends(get_db), current_user: User = Depends(require_hr)):
    return excel_service.public_preview(excel_service.load_batch(db, current_user, token))


@router.get("/import/{token}/errors")
def import_error_report(token: str, db: Session = Depends(get_db), current_user: User = Depends(require_hr)):
    batch = excel_service.load_batch(db, current_user, token)
    return _xlsx(excel_service.error_report(batch), f"import_errors_{batch.id}.xlsx")


class ConfirmIn(BaseModel):
    confirm_hierarchy_changes: bool = False
    send_account_emails: bool = False


@router.post("/import/{token}/confirm")
def import_confirm(token: str, payload: ConfirmIn, db: Session = Depends(get_db),
                   current_user: User = Depends(require_hr)):
    batch = excel_service.load_batch(db, current_user, token)
    result = excel_service.confirm(db, current_user, batch, payload.confirm_hierarchy_changes,
                                   payload.send_account_emails)
    db.commit()
    return {**result, "preview": excel_service.public_preview(batch)}


@router.get("/export/types")
def export_types(current_user: User = Depends(get_current_user)):
    from app.services import hierarchy_service as H
    items = []
    for key, label in excel_service.EXPORT_TYPES.items():
        if not H.is_supervisor(current_user) and key in ("employees", "hierarchy", "documents"):
            continue
        if H.is_manager(current_user) and key in excel_service.SENSITIVE_EXPORTS:
            continue
        items.append({"value": key, "label": label})
    return {"items": items, "scope": (
        "organisation" if H.is_admin(current_user) else
        "hierarchy" if H.is_hr(current_user) else
        "team" if H.is_manager(current_user) else "own")}


@router.get("/export")
def export(
    export_type: str = Query(..., alias="type"),
    department_id: Optional[int] = None,
    reporting_hr_id: Optional[int] = None,
    reporting_manager_id: Optional[int] = None,
    person_type: Optional[str] = None,
    employment_status: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    month: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$"),
    report_type: Optional[str] = None,
    status: Optional[str] = None,
    leave_type: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    filters = {
        "department_id": department_id, "reporting_hr_id": reporting_hr_id,
        "reporting_manager_id": reporting_manager_id, "person_type": person_type,
        "employment_status": employment_status,
        "date_from": date_from, "date_to": date_to, "month": month, "report_type": report_type,
        "status": status, "leave_type": leave_type,
    }
    content, count, filename = excel_service.build_export(db, current_user, export_type, filters)
    audit_service.record(
        db, AuditAction.EXCEL_EXPORTED, user=current_user, entity_type="excel", entity_id=None,
        meta={"export_type": export_type, "records": count,
              "filters": {k: str(v) for k, v in filters.items() if v not in (None, "")}},
        commit=True,
    )
    return _xlsx(content, filename)
