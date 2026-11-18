from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.core.constants import UanStatus
from app.core.dependencies import (
    assert_can_access_employee, get_current_employee, get_current_user, require_hr,
)
from app.database.database import get_db
from app.models.employee import Employee
from app.models.uan import UanDetail
from app.models.user import User
from app.schemas.common import Page, paginate
from app.schemas.uan import UanOut, UanReviewRequest, UanSubmitRequest
from app.services import uan_service

router = APIRouter(prefix="/uan", tags=["UAN"])


def _out(record: UanDetail) -> UanOut:
    employee = record.employee
    return UanOut(
        id=record.id,
        employee_id=record.employee_id,
        employee_name=employee.full_name if employee else None,
        employee_code=employee.employee_code if employee else None,
        department=employee.department.name if employee and employee.department else None,
        uan_number=record.uan_number,
        status=record.status,
        submitted_at=record.submitted_at,
        hr_remarks=record.hr_remarks,
        verified_at=record.verified_at,
    )


@router.get("/me", response_model=UanOut)
def my_uan(db: Session = Depends(get_db), employee: Employee = Depends(get_current_employee)):
    return _out(uan_service.get_or_create(db, employee))


@router.post("", response_model=UanOut)
def submit_uan(
    payload: UanSubmitRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    employee: Employee = Depends(get_current_employee),
):
    record = uan_service.submit(db, employee, payload.uan_number, current_user)
    db.commit()
    return _out(record)


@router.get("", response_model=Page[UanOut])
def list_uan(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    status_filter: Optional[str] = Query(None, alias="status"),
    department_id: Optional[int] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr),
):
    from app.services import hierarchy_service
    query = (
        db.query(UanDetail)
        .options(joinedload(UanDetail.employee).joinedload(Employee.department))
        .join(Employee, UanDetail.employee_id == Employee.id)
    )
    query = hierarchy_service.restrict_managed(query, db, current_user, Employee.id)
    if status_filter and status_filter.lower() != "all":
        # A mistyped filter should say so rather than silently return nothing.
        if status_filter not in UanStatus.ALL:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"status must be one of {', '.join(UanStatus.ALL)}.",
            )
        query = query.filter(UanDetail.status == status_filter)
    if department_id:
        query = query.filter(Employee.department_id == department_id)
    if search:
        needle = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Employee.full_name.ilike(needle),
                Employee.employee_code.ilike(needle),
                Employee.unique_employee_id.ilike(needle),
                UanDetail.uan_number.ilike(needle),
            )
        )
    rows, meta = paginate(query.order_by(UanDetail.updated_at.desc()), page, page_size)
    return Page[UanOut](items=[_out(r) for r in rows], meta=meta)


@router.get("/employee/{employee_id}", response_model=UanOut)
def employee_uan(
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    employee = assert_can_access_employee(current_user, employee_id, db, level="sensitive")
    return _out(uan_service.get_or_create(db, employee))


def _load(db: Session, uan_id: int, user: Optional[User] = None) -> UanDetail:
    record = db.query(UanDetail).filter(UanDetail.id == uan_id).first()
    if record is None:
        raise HTTPException(status_code=404, detail="UAN record not found.")
    if user is not None:
        # Verifying a UAN is an HR action on someone in the reviewer's hierarchy.
        assert_can_access_employee(user, record.employee_id, db, level="manage")
    return record


@router.post("/{uan_id}/verify", response_model=UanOut)
def verify_uan(
    uan_id: int,
    payload: UanReviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr),
):
    record = uan_service.review(db, _load(db, uan_id, current_user), current_user, True, payload.remarks)
    db.commit()
    return _out(record)


@router.post("/{uan_id}/reject", response_model=UanOut)
def reject_uan(
    uan_id: int,
    payload: UanReviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr),
):
    record = uan_service.review(db, _load(db, uan_id, current_user), current_user, False, payload.remarks)
    db.commit()
    return _out(record)


@router.post("/{uan_id}/under-verification", response_model=UanOut)
def mark_under_verification(
    uan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr),
):
    record = uan_service.set_under_verification(db, _load(db, uan_id, current_user), current_user)
    db.commit()
    return _out(record)
