"""Intern payslip download requests: the intern asks, HR decides."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.core.constants import DownloadRequestStatus
from app.core.dependencies import get_current_user, is_hr, require_hr
from app.database.database import get_db
from app.models.employee import Employee
from app.models.intern_payslip_request import InternPayslipDownloadRequest
from app.models.salary import SalaryRecord
from app.models.user import User
from app.schemas.common import Page, PageMeta
from app.schemas.profile_change import DownloadRequestOut, DownloadRequestReview
from app.services import intern_payslip_request_service as request_service

router = APIRouter(
    prefix="/payslip-download-requests", tags=["Intern Payslip Download Requests"]
)


def serialize(request: InternPayslipDownloadRequest) -> dict:
    employee = request.employee
    salary = request.salary
    return {
        "id": request.id,
        "employee_id": request.employee_id,
        "employee_name": employee.full_name if employee else None,
        "employee_display_id": employee.display_employee_id if employee else None,
        "department": (
            employee.department.name if employee and employee.department else None
        ),
        "salary_id": request.salary_id,
        "period_label": salary.period_label if salary else None,
        "net_pay": str(salary.net_pay) if salary else None,
        "has_payslip": bool(salary and salary.slip),
        "reason": request.reason,
        "status": request.status,
        "hr_remarks": request.hr_remarks,
        "hr_reviewer": (
            request.hr_reviewer.email if request.hr_reviewer is not None else None
        ),
        "requested_at": request.requested_at,
        "reviewed_at": request.reviewed_at,
        "created_at": request.created_at,
    }


def _base(db: Session):
    return db.query(InternPayslipDownloadRequest).options(
        joinedload(InternPayslipDownloadRequest.employee).joinedload(Employee.department),
        joinedload(InternPayslipDownloadRequest.salary).joinedload(SalaryRecord.slip),
        joinedload(InternPayslipDownloadRequest.hr_reviewer),
    )


@router.get("", response_model=Page[DownloadRequestOut])
def list_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    status_filter: Optional[str] = Query(None, alias="status"),
    employee_id: Optional[int] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
):
    """HR/Admin see their hierarchy's requests; an intern sees only their own."""
    from app.services import hierarchy_service
    query = _base(db)

    if is_hr(current_user):
        query = hierarchy_service.restrict_managed(
            query, db, current_user, InternPayslipDownloadRequest.employee_id
        )
        if employee_id is not None:
            query = query.filter(InternPayslipDownloadRequest.employee_id == employee_id)
    else:
        own = db.query(Employee).filter(Employee.user_id == current_user.id).first()
        if own is None:
            raise HTTPException(status_code=404, detail="No employee profile found.")
        query = query.filter(InternPayslipDownloadRequest.employee_id == own.id)

    if status_filter:
        if status_filter not in DownloadRequestStatus.ALL:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"status must be one of {', '.join(DownloadRequestStatus.ALL)}.",
            )
        query = query.filter(InternPayslipDownloadRequest.status == status_filter)

    if search:
        like = f"%{search.strip()}%"
        query = query.join(
            Employee, Employee.id == InternPayslipDownloadRequest.employee_id
        ).filter(
            or_(
                Employee.full_name.ilike(like),
                Employee.employee_code.ilike(like),
                Employee.unique_employee_id.ilike(like),
                InternPayslipDownloadRequest.reason.ilike(like),
            )
        )

    total = query.count()
    rows = (
        query.order_by(InternPayslipDownloadRequest.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return Page[DownloadRequestOut](
        items=[DownloadRequestOut(**serialize(r)) for r in rows],
        meta=PageMeta(
            page=page, page_size=page_size, total=total,
            pages=max(1, (total + page_size - 1) // page_size),
        ),
    )


def _load(db: Session, request_id: int, user: Optional[User] = None) -> InternPayslipDownloadRequest:
    request = _base(db).filter(InternPayslipDownloadRequest.id == request_id).first()
    if request is None:
        raise HTTPException(status_code=404, detail="Download request not found.")
    if user is not None:
        from app.core.dependencies import assert_can_access_employee
        assert_can_access_employee(user, request.employee_id, db, level="manage")
    return request


@router.get("/{request_id}", response_model=DownloadRequestOut)
def get_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    request = _load(db, request_id)
    from app.services import hierarchy_service
    own = current_user.employee
    if not (own is not None and request.employee_id == own.id) and not (
            is_hr(current_user) and hierarchy_service.can_manage_employee(db, current_user, request.employee)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only view your own download requests.",
        )
    return DownloadRequestOut(**serialize(request))


@router.post("/{request_id}/approve", response_model=DownloadRequestOut)
def approve_request(
    request_id: int,
    payload: DownloadRequestReview,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr),
):
    request = request_service.approve(db, _load(db, request_id, current_user), current_user,
                                      payload.remarks)
    db.commit()
    db.refresh(request)
    return DownloadRequestOut(**serialize(request))


@router.post("/{request_id}/reject", response_model=DownloadRequestOut)
def reject_request(
    request_id: int,
    payload: DownloadRequestReview,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr),
):
    request = request_service.reject(db, _load(db, request_id, current_user), current_user,
                                     payload.remarks)
    db.commit()
    db.refresh(request)
    return DownloadRequestOut(**serialize(request))
