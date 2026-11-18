from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload

from app.api.serializers import meeting_out
from app.core.constants import AuditAction, MeetingStatus
from app.core.dependencies import get_current_user, is_hr, require_hr
from app.database.database import get_db
from app.models.department import Department
from app.models.employee import Employee
from app.models.meeting import Meeting
from app.models.user import User
from app.schemas.meeting import MeetingCreate, MeetingOut, MeetingUpdate
from app.services import audit_service, meeting_service

router = APIRouter(prefix="/meetings", tags=["Meetings"])


def _visible_meetings(
    db: Session,
    current_user: User,
    department_id: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    status_filter: Optional[str] = None,
    today_only: bool = False,
) -> List[MeetingOut]:
    """HR sees everything. An employee only sees their own department's meetings."""
    query = db.query(Meeting).options(joinedload(Meeting.department))

    if is_hr(current_user):
        if department_id:
            query = query.filter(Meeting.department_id == department_id)
    else:
        employee = db.query(Employee).filter(Employee.user_id == current_user.id).first()
        if employee is None:
            raise HTTPException(status_code=404, detail="No employee profile on this account.")
        # Department scoping is applied server-side and cannot be overridden by a query param.
        query = query.filter(Meeting.department_id == employee.department_id)

    if today_only:
        query = query.filter(Meeting.meeting_date == date.today())
    if date_from:
        query = query.filter(Meeting.meeting_date >= date_from)
    if date_to:
        query = query.filter(Meeting.meeting_date <= date_to)
    if status_filter and status_filter.lower() != "all":
        query = query.filter(Meeting.status == status_filter)

    rows = query.order_by(Meeting.meeting_date.desc(), Meeting.start_time.asc()).all()
    return [MeetingOut(**meeting_out(m)) for m in rows]


@router.get("", response_model=List[MeetingOut])
def list_meetings(
    department_id: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    today_only: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _visible_meetings(
        db, current_user, department_id, date_from, date_to, status_filter, today_only
    )


@router.get("/today", response_model=List[MeetingOut])
def todays_meetings(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    return _visible_meetings(db, current_user, today_only=True)


@router.post("", response_model=MeetingOut, status_code=status.HTTP_201_CREATED)
def create_meeting(
    payload: MeetingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr),
):
    department = db.query(Department).filter(Department.id == payload.department_id).first()
    if department is None:
        raise HTTPException(status_code=404, detail="Department not found.")

    data = payload.model_dump()
    data["google_meet_url"] = meeting_service.validate_meet_url(data.get("google_meet_url"))
    if data.get("end_time") and data["end_time"] <= data["start_time"]:
        raise HTTPException(status_code=422, detail="The end time must be after the start time.")

    meeting = Meeting(**data, created_by_id=current_user.id)
    db.add(meeting)
    db.flush()
    audit_service.record(
        db, AuditAction.MEETING_CREATED, user=current_user, entity_type="meeting",
        entity_id=meeting.id,
        meta={"department": department.name, "date": str(meeting.meeting_date)},
    )
    db.commit()
    db.refresh(meeting)
    return MeetingOut(**meeting_out(meeting))


@router.put("/{meeting_id}", response_model=MeetingOut)
def update_meeting(
    meeting_id: int,
    payload: MeetingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr),
):
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting not found.")

    changes = payload.model_dump(exclude_unset=True)
    if "google_meet_url" in changes:
        changes["google_meet_url"] = meeting_service.validate_meet_url(changes["google_meet_url"])
    if "status" in changes and changes["status"] not in MeetingStatus.ALL:
        raise HTTPException(status_code=422, detail="Unknown meeting status.")

    for field, value in changes.items():
        setattr(meeting, field, value)
    db.flush()
    audit_service.record(
        db, AuditAction.MEETING_UPDATED, user=current_user, entity_type="meeting",
        entity_id=meeting.id, meta={"fields": list(changes)},
    )
    db.commit()
    db.refresh(meeting)
    return MeetingOut(**meeting_out(meeting))


@router.post("/{meeting_id}/cancel", response_model=MeetingOut)
def cancel_meeting(
    meeting_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr),
):
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting not found.")
    meeting.status = MeetingStatus.CANCELLED
    db.flush()
    audit_service.record(
        db, AuditAction.MEETING_CANCELLED, user=current_user, entity_type="meeting",
        entity_id=meeting.id, meta={"title": meeting.title},
    )
    db.commit()
    db.refresh(meeting)
    return MeetingOut(**meeting_out(meeting))
