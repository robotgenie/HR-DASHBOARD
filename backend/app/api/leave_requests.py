from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload

from app.core.constants import ApprovalStage, LeaveStatus
from app.core.dependencies import (
    assert_can_access_employee, get_current_employee, get_current_user, require_hr,
    require_supervisor,
)
from app.database.database import get_db
from app.models.department import Department
from app.models.employee import Employee
from app.models.leave_request import LeaveRequest
from app.models.user import User
from app.schemas.common import Page, paginate
from app.schemas.leave import LEAVE_TYPES, LeaveRequestCreate, LeaveRequestOut, LeaveReviewRequest, LeaveSummary
from app.services import hierarchy_service, leave_service

router = APIRouter(prefix="/leave-requests", tags=["Leave Requests"])


def _query(db: Session):
    return db.query(LeaveRequest).options(
        joinedload(LeaveRequest.employee).joinedload(Employee.department),
        joinedload(LeaveRequest.employee).joinedload(Employee.internship_background),
    )


def _out(db: Session, row: LeaveRequest, user: User) -> LeaveRequestOut:
    data = leave_service.output(row)
    data["can_act"] = hierarchy_service.can_act_on_leave(db, user, row)
    return LeaveRequestOut(**data)


@router.get("/types", response_model=list[str])
def leave_types(current_user: User = Depends(get_current_user)):
    return LEAVE_TYPES


@router.get("/options")
def leave_options(current_user: User = Depends(get_current_user)):
    """Leave types (with display labels) and the half-day periods, for the request form."""
    from app.core.constants import LeavePeriod, LeaveType
    return {
        "types": [{"value": t, "label": LeaveType.LABELS.get(t, t)} for t in LeaveType.ALL],
        "periods": [
            {"value": p, "label": f"{p} ({leave_service.PERIOD_HOURS[p]})"} for p in LeavePeriod.ALL
        ],
        "half_day_type": LeaveType.HALF_DAY,
    }


@router.post("", response_model=LeaveRequestOut, status_code=status.HTTP_201_CREATED)
def create_leave_request(
    payload: LeaveRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    employee: Employee = Depends(get_current_employee),
):
    row = leave_service.create_request(
        db, employee, payload.leave_type, payload.from_date, payload.to_date,
        payload.reason, current_user, leave_period=payload.leave_period,
    )
    db.commit()
    row = _query(db).filter(LeaveRequest.id == row.id).first()
    return _out(db, row, current_user)


@router.get("/me", response_model=Page[LeaveRequestOut])
def my_leave_requests(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status"),
    db: Session = Depends(get_db),
    employee: Employee = Depends(get_current_employee),
):
    query = _query(db).filter(LeaveRequest.employee_id == employee.id)
    if status_filter and status_filter in LeaveStatus.ALL:
        query = query.filter(LeaveRequest.status == status_filter)
    query = query.order_by(LeaveRequest.created_at.desc(), LeaveRequest.id.desc())
    rows, meta = paginate(query, page, page_size)
    return Page[LeaveRequestOut](
        items=[LeaveRequestOut(**leave_service.output(r)) for r in rows], meta=meta
    )


@router.get("/summary/me", response_model=LeaveSummary)
def my_leave_summary(
    db: Session = Depends(get_db),
    employee: Employee = Depends(get_current_employee),
):
    counts = {
        s: db.query(LeaveRequest).filter(
            LeaveRequest.employee_id == employee.id, LeaveRequest.status == s
        ).count()
        for s in LeaveStatus.ALL
    }
    return LeaveSummary(
        pending=counts[LeaveStatus.PENDING],
        approved=counts[LeaveStatus.APPROVED],
        rejected=counts[LeaveStatus.REJECTED],
        total=sum(counts.values()),
    )


@router.get("", response_model=Page[LeaveRequestOut])
def hr_leave_requests(
    page: int = Query(1, ge=1),
    page_size: int = Query(15, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status"),
    department_id: Optional[int] = None,
    employee_id: Optional[int] = None,
    search: Optional[str] = None,
    stage: Optional[str] = None,
    awaiting_me: bool = False,
    reporting_hr_id: Optional[int] = None,
    reporting_manager_id: Optional[int] = None,
    leave_type: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_supervisor),
):
    """Leave of the people the viewer supervises (never the viewer's own:
    those are under "My leave" and go up the hierarchy)."""
    query = _query(db).join(Employee, LeaveRequest.employee_id == Employee.id)
    query = hierarchy_service.restrict(query, db, current_user, Employee.id, include_self=False)
    if status_filter and status_filter in LeaveStatus.ALL:
        query = query.filter(LeaveRequest.status == status_filter)
    if stage and stage in ApprovalStage.ALL:
        query = query.filter(LeaveRequest.approval_stage == stage)
    if awaiting_me:
        query = query.filter(hierarchy_service.leave_actionable_filter(db, current_user))
    if department_id:
        query = query.filter(Employee.department_id == department_id)
    if employee_id:
        query = query.filter(LeaveRequest.employee_id == employee_id)
    if reporting_hr_id:
        query = query.filter(Employee.reporting_hr_id == reporting_hr_id)
    if reporting_manager_id:
        query = query.filter(Employee.reporting_manager_id == reporting_manager_id)
    if leave_type:
        query = query.filter(LeaveRequest.leave_type == leave_type)
    if date_from:
        query = query.filter(LeaveRequest.to_date >= date_from)
    if date_to:
        query = query.filter(LeaveRequest.from_date <= date_to)
    if search:
        needle = f"%{search.strip()}%"
        query = query.filter(
            Employee.full_name.ilike(needle) | Employee.employee_code.ilike(needle)
        )
    query = query.order_by(LeaveRequest.created_at.desc(), LeaveRequest.id.desc())
    rows, meta = paginate(query, page, page_size)
    return Page[LeaveRequestOut](
        items=[_out(db, r, current_user) for r in rows], meta=meta
    )


@router.get("/summary", response_model=LeaveSummary)
def hr_leave_summary(
    db: Session = Depends(get_db), current_user: User = Depends(require_supervisor)
):
    def scoped():
        q = db.query(LeaveRequest).join(Employee, LeaveRequest.employee_id == Employee.id)
        return hierarchy_service.restrict(q, db, current_user, Employee.id, include_self=False)

    counts = {s: scoped().filter(LeaveRequest.status == s).count() for s in LeaveStatus.ALL}
    awaiting = scoped().filter(hierarchy_service.leave_actionable_filter(db, current_user)).count()
    return LeaveSummary(
        pending=counts[LeaveStatus.PENDING],
        approved=counts[LeaveStatus.APPROVED],
        rejected=counts[LeaveStatus.REJECTED],
        total=sum(counts.values()),
        awaiting_me=awaiting,
    )


@router.get("/{leave_id}", response_model=LeaveRequestOut)
def get_leave_request(
    leave_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = _query(db).filter(LeaveRequest.id == leave_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Leave request not found.")
    assert_can_access_employee(current_user, row.employee_id, db)
    return _out(db, row, current_user)


@router.patch("/{leave_id}", response_model=LeaveRequestOut)
def review_leave_request(
    leave_id: int,
    payload: LeaveReviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_supervisor),
):
    """Approve / reject according to the hierarchy (see leave_service.decide)."""
    row = _query(db).filter(LeaveRequest.id == leave_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Leave request not found.")
    assert_can_access_employee(current_user, row.employee_id, db)
    leave_service.decide(db, row, payload.status, payload.hr_remarks, current_user)
    db.commit()
    row = _query(db).filter(LeaveRequest.id == row.id).first()
    return _out(db, row, current_user)
