"""Bank details: shown inside the Documents page (no separate page).

Employee (any portal with an employee record):
    GET  /bank-details/me            status + approved details (masked) + latest submission
    POST /bank-details/me            submit for approval (requires confirmed = true)
HR (own hierarchy, never self) / Admin:
    GET  /bank-details               review queue (account numbers masked)
    GET  /bank-details/{id}          one submission, full values for an authorised reviewer
    POST /bank-details/{id}/approve
    POST /bank-details/{id}/reject   (reason required)
    GET  /bank-details/employee/{employee_id}   approved details of one employee
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.core.constants import AuditAction, BankDetailStatus
from app.core.dependencies import get_current_employee, get_current_user, require_hr
from app.database.database import get_db
from app.models.bank_detail_request import BankDetailRequest
from app.models.employee import Employee
from app.models.user import User
from app.schemas.common import paginate
from app.services import audit_service, bank_details_service as svc, hierarchy_service

router = APIRouter(prefix="/bank-details", tags=["Bank details"])


class BankDetailsSubmit(BaseModel):
    bank_name: str = Field("", max_length=120)
    account_number: str = Field("", max_length=40)
    confirm_account_number: str = Field("", max_length=40)
    ifsc_code: str = Field("", max_length=20)
    pan_number: str = Field("", max_length=20)
    confirmed: bool = False


class BankDetailsReview(BaseModel):
    remarks: Optional[str] = Field(None, max_length=1000)


# ------------------------------------------------------------------ employee
@router.get("/me")
def my_bank_details(db: Session = Depends(get_db), employee: Employee = Depends(get_current_employee)):
    return svc.state(db, employee)


@router.post("/me", status_code=201)
def submit_my_bank_details(
    payload: BankDetailsSubmit,
    db: Session = Depends(get_db),
    employee: Employee = Depends(get_current_employee),
    current_user: User = Depends(get_current_user),
):
    row = svc.submit(db, employee, current_user, payload.model_dump(), payload.confirmed)
    db.commit()
    db.refresh(row)
    return {"request": svc.request_out(row), "state": svc.state(db, employee)}


# ------------------------------------------------------------------ reviewers
@router.get("")
def list_bank_detail_requests(
    status: Optional[str] = Query(BankDetailStatus.PENDING),
    search: Optional[str] = None,
    department_id: Optional[int] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr),
):
    q = (
        db.query(BankDetailRequest)
        .join(Employee, Employee.id == BankDetailRequest.employee_id)
        .options(joinedload(BankDetailRequest.employee))
    )
    q = hierarchy_service.restrict_managed(q, db, current_user, BankDetailRequest.employee_id)
    if status and status != "all":
        if status not in BankDetailStatus.ALL:
            raise HTTPException(status_code=422, detail="Unknown status.")
        q = q.filter(BankDetailRequest.status == status)
    else:
        q = q.filter(BankDetailRequest.status != BankDetailStatus.SUPERSEDED)
    if department_id:
        q = q.filter(Employee.department_id == department_id)
    if search:
        like = f"%{search.strip()}%"
        q = q.filter(or_(Employee.full_name.ilike(like), Employee.employee_code.ilike(like), Employee.unique_employee_id.ilike(like),
                         BankDetailRequest.bank_name.ilike(like)))
    q = q.order_by(BankDetailRequest.created_at.desc(), BankDetailRequest.id.desc())
    items, meta = paginate(q, page, page_size)
    return {"items": [svc.request_out(r) for r in items], "meta": meta.model_dump()}


@router.get("/employee/{employee_id}")
def employee_bank_details(
    employee_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_hr),
):
    employee = hierarchy_service.assert_employee(db, current_user, employee_id, hierarchy_service.MANAGE,
                                                 "bank_details")
    data = svc.state(db, employee)
    data["approved"] = svc.approved_block(employee, full=True)
    audit_service.record(db, AuditAction.BANK_DETAILS_VIEWED, user=current_user, entity_type="employee",
                         entity_id=employee.id, meta={"what": "approved"})
    db.commit()
    return data


@router.get("/{request_id}")
def get_bank_detail_request(
    request_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    row = db.query(BankDetailRequest).filter(BankDetailRequest.id == request_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Bank details request not found.")
    own = hierarchy_service.own_employee(current_user)
    if own is not None and own.id == row.employee_id:
        return svc.request_out(row, full=False)
    hierarchy_service.assert_level(db, current_user, row.employee, hierarchy_service.MANAGE, "bank_detail_request")
    out = svc.request_out(row, full=True)
    out["approved"] = svc.approved_block(row.employee, full=True)
    audit_service.record(db, AuditAction.BANK_DETAILS_VIEWED, user=current_user,
                         entity_type="bank_detail_request", entity_id=row.id,
                         meta={"employee_id": row.employee_id})
    db.commit()
    return out


@router.post("/{request_id}/approve")
def approve_bank_details(
    request_id: int, payload: BankDetailsReview = BankDetailsReview(),
    db: Session = Depends(get_db), current_user: User = Depends(require_hr),
):
    row = svc.load_for_review(db, request_id, current_user)
    svc.approve(db, row, current_user, payload.remarks)
    db.commit()
    db.refresh(row)
    return svc.request_out(row)


@router.post("/{request_id}/reject")
def reject_bank_details(
    request_id: int, payload: BankDetailsReview,
    db: Session = Depends(get_db), current_user: User = Depends(require_hr),
):
    row = svc.load_for_review(db, request_id, current_user)
    svc.reject(db, row, current_user, payload.remarks)
    db.commit()
    db.refresh(row)
    return svc.request_out(row)
