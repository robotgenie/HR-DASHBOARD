"""Hourly work updates, linked to assigned tasks."""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.dependencies import ApiRuleError, get_current_employee, get_current_user, is_hr
from app.database.database import get_db
from app.models.employee import Employee
from app.models.hourly_update import HourlyUpdate, HourlyUpdateAttachment
from app.models.user import User
from app.services import file_service, hierarchy_service, hourly_service

router = APIRouter(prefix="/hourly-updates", tags=["Hourly Updates"])

# Same formats as daily-report proof-of-work attachments.
ATTACHMENT_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "pdf", "doc", "docx"}


class HourlyUpdateIn(BaseModel):
    slot_index: int = Field(..., ge=0, le=7)
    task_id: Optional[int] = None
    work_completed: str = Field(..., min_length=3, max_length=5000)
    description: Optional[str] = Field(None, max_length=5000)
    units_completed: int = Field(0, ge=0, le=100000)
    progress_percent: Optional[int] = Field(None, ge=0, le=100)
    task_status: str = "In Progress"
    remaining_work: Optional[str] = Field(None, max_length=5000)
    notes: Optional[str] = Field(None, max_length=3000)


@router.get("/today")
def my_hourly_today(db: Session = Depends(get_db), employee: Employee = Depends(get_current_employee),
                    current_user: User = Depends(get_current_user)):
    """Today's hourly periods, tasks and submitted updates (also raises the
    one-time 'update due' notification for each period that has ended)."""
    state = hourly_service.today_state(db, employee)
    db.commit()
    return state


@router.post("", status_code=status.HTTP_201_CREATED)
def submit_hourly_update(payload: HourlyUpdateIn, db: Session = Depends(get_db),
                         current_user: User = Depends(get_current_user),
                         employee: Employee = Depends(get_current_employee)):
    row = hourly_service.submit(db, current_user, employee, payload.model_dump())
    db.commit()
    return hourly_service.output(hourly_service.query(db).filter(HourlyUpdate.id == row.id).first())


def _load(db: Session, update_id: int, user: User) -> HourlyUpdate:
    row = hourly_service.query(db).filter(HourlyUpdate.id == update_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Hourly update not found.")
    if row.employee is None or not hierarchy_service.can_access_employee(db, user, row.employee):
        raise HTTPException(status_code=403, detail="You don't have access to this resource.")
    return row


@router.post("/{update_id}/attachments")
async def add_attachment(update_id: int, file: UploadFile = File(...), db: Session = Depends(get_db),
                         current_user: User = Depends(get_current_user)):
    row = _load(db, update_id, current_user)
    if row.employee.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the employee attaches work proof.")
    from app.utils.clock import local_today
    if row.update_date != local_today():
        raise ApiRuleError(409, "Attachments can only be added on the day of the update.", "UPDATE_CLOSED")
    if len(row.attachments) >= 5:
        raise HTTPException(status_code=409, detail="Up to 5 attachments per hourly update.")
    content, ext, mime, _ = await file_service.validate_and_read(
        file, allowed_extensions=ATTACHMENT_EXTENSIONS, max_size=10 * 1024 * 1024,
    )
    stored = file_service.build_stored_name(f"hourly_{row.id}", file.filename)
    file_service.save_bytes(file_service.REPORTS, stored, content)
    row.attachments.append(HourlyUpdateAttachment(
        hourly_update_id=row.id, stored_filename=stored,
        original_filename=file_service.sanitise_filename(file.filename),
        mime_type=mime, file_size=len(content), uploaded_by_id=current_user.id,
    ))
    db.commit()
    return hourly_service.output(_load(db, update_id, current_user))


@router.get("/attachments/{attachment_id}/download")
def download_attachment(attachment_id: int, db: Session = Depends(get_db),
                        current_user: User = Depends(get_current_user)):
    att = db.query(HourlyUpdateAttachment).filter(HourlyUpdateAttachment.id == attachment_id).first()
    if att is None:
        raise HTTPException(status_code=404, detail="Attachment not found.")
    _load(db, att.hourly_update_id, current_user)       # ownership check
    path = file_service.resolve_path(file_service.REPORTS, att.stored_filename)
    if not path.exists():
        raise HTTPException(status_code=404, detail="The stored file is missing.")
    return StreamingResponse(iter([path.read_bytes()]), media_type=att.mime_type,
                             headers={"Content-Disposition": f'inline; filename="{att.original_filename}"'})


@router.get("")
def list_updates(employee_id: Optional[int] = None, task_id: Optional[int] = None,
                 day: Optional[date] = Query(None, alias="date"),
                 date_from: Optional[date] = None, date_to: Optional[date] = None,
                 limit: int = Query(200, ge=1, le=500),
                 db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Hierarchy-scoped: Admin all, HR their hierarchy, Manager their team,
    everyone else their own updates."""
    query = hierarchy_service.restrict(hourly_service.query(db), db, current_user, HourlyUpdate.employee_id)
    if employee_id:
        query = query.filter(HourlyUpdate.employee_id == employee_id)
    if task_id:
        query = query.filter(HourlyUpdate.task_id == task_id)
    if day:
        query = query.filter(HourlyUpdate.update_date == day)
    if date_from:
        query = query.filter(HourlyUpdate.update_date >= date_from)
    if date_to:
        query = query.filter(HourlyUpdate.update_date <= date_to)
    rows = query.order_by(HourlyUpdate.update_date.desc(), HourlyUpdate.slot_index.desc()).limit(limit).all()
    return {"items": [hourly_service.output(u) for u in rows]}
