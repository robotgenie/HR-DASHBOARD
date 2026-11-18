from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from app.api.serializers import salary_out
from app.core.constants import AuditAction, SalaryStatus
from app.core.dependencies import (
    ApiRuleError, assert_can_access_employee, get_current_employee, get_current_user, is_hr, require_hr,
)
from app.database.database import get_db
from app.models.employee import Employee
from app.models.salary import SalaryRecord
from app.models.user import User
from app.schemas.common import Page, paginate
from app.schemas.profile_change import (
    DownloadRequestIn, DownloadRequestOut, PayslipPermissionIn, PayslipPermissionResult,
)
from app.schemas.salary import (
    SalaryCreate, SalaryCreditRequest, SalaryCreditResult, SalaryOut, SalaryUpdate,
)
from app.services import (
    audit_service, file_service, hierarchy_service, intern_payslip_request_service,
    payslip_service, salary_autogen_service, salary_service,
)
from app.utils.clock import local_today

router = APIRouter(prefix="/salaries", tags=["Salary"])


def _query(db: Session):
    return db.query(SalaryRecord).options(
        joinedload(SalaryRecord.employee).joinedload(Employee.department),
        joinedload(SalaryRecord.components),
        joinedload(SalaryRecord.slip),
    )


def _load(db: Session, salary_id: int, user: User, level: str = "sensitive") -> SalaryRecord:
    record = _query(db).filter(SalaryRecord.id == salary_id).first()
    if record is None:
        raise HTTPException(status_code=404, detail="Salary record not found.")
    # Salary is sensitive: self, HR (hierarchy) and Admin only - never a
    # Manager. Changing a record needs "manage" (HR's own salary: Admin).
    assert_can_access_employee(user, record.employee_id, db, level=level)
    return record


def _manages(db: Session, user: User, record: SalaryRecord) -> bool:
    return hierarchy_service.can_manage_employee(db, user, record.employee)


@router.get("", response_model=Page[SalaryOut])
def list_salaries(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    employee_id: Optional[int] = None,
    period_year: Optional[int] = None,
    period_month: Optional[int] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    department_id: Optional[int] = None,
    reporting_hr_id: Optional[int] = None,
    reporting_manager_id: Optional[int] = None,
    mine: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = _query(db)

    if mine or not is_hr(current_user):
        employee = db.query(Employee).filter(Employee.user_id == current_user.id).first()
        if employee is None:
            raise HTTPException(status_code=404, detail="No employee profile on this account.")
        query = query.filter(SalaryRecord.employee_id == employee.id)
    else:
        # Payroll view: Admin everyone, HR their hierarchy (own salary is the Admin's).
        query = query.join(Employee, SalaryRecord.employee_id == Employee.id)
        query = hierarchy_service.restrict_managed(query, db, current_user, Employee.id)
        if employee_id:
            query = query.filter(SalaryRecord.employee_id == employee_id)
        if reporting_hr_id:
            query = query.filter(Employee.reporting_hr_id == reporting_hr_id)
        if reporting_manager_id:
            query = query.filter(Employee.reporting_manager_id == reporting_manager_id)

    if period_year:
        query = query.filter(SalaryRecord.period_year == period_year)
    if period_month:
        query = query.filter(SalaryRecord.period_month == period_month)
    if status_filter and status_filter.lower() != "all":
        query = query.filter(SalaryRecord.status == status_filter)
    if department_id and is_hr(current_user) and not mine:
        query = query.filter(Employee.department_id == department_id)

    query = query.order_by(
        SalaryRecord.period_year.desc(), SalaryRecord.period_month.desc()
    )
    rows, meta = paginate(query, page, page_size)
    return Page[SalaryOut](items=[SalaryOut(**salary_out(r)) for r in rows], meta=meta)


@router.get("/me", response_model=List[SalaryOut])
def my_salaries(
    db: Session = Depends(get_db), employee: Employee = Depends(get_current_employee)
):
    rows = (
        _query(db)
        .filter(SalaryRecord.employee_id == employee.id)
        .order_by(SalaryRecord.period_year.desc(), SalaryRecord.period_month.desc())
        .all()
    )
    return [SalaryOut(**salary_out(r)) for r in rows]


@router.post("", response_model=SalaryOut, status_code=status.HTTP_201_CREATED)
def create_salary(
    payload: SalaryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr),
):
    employee = assert_can_access_employee(current_user, payload.employee_id, db, level="manage")

    duplicate = (
        db.query(SalaryRecord)
        .filter(
            SalaryRecord.employee_id == employee.id,
            SalaryRecord.period_year == payload.period_year,
            SalaryRecord.period_month == payload.period_month,
        )
        .first()
    )
    if duplicate:
        # One slip per employee + month + year: point the UI at the existing
        # slip so it is opened for editing instead of creating another one.
        raise ApiRuleError(
            status.HTTP_409_CONFLICT,
            "A salary record already exists for that employee and pay period.",
            "SALARY_EXISTS",
            {"salary_id": duplicate.id, "period_label": duplicate.period_label},
        )

    record = SalaryRecord(
        employee_id=employee.id,
        period_year=payload.period_year,
        period_month=payload.period_month,
        working_days=payload.working_days,
        status=SalaryStatus.PENDING,
        credit_date=payload.credit_date,
        remarks=payload.remarks,
        created_by_id=current_user.id,
    )
    db.add(record)
    db.flush()
    salary_service.replace_components(db, record, payload.components)

    audit_service.record(
        db, AuditAction.SALARY_CREATED, user=current_user, entity_type="salary_record",
        entity_id=record.id,
        meta={
            "employee_id": employee.id,
            "period": record.period_label,
            "net_pay": str(record.net_pay),
        },
    )

    # Crediting on create still goes through the single idempotent path.
    if payload.status == SalaryStatus.CREDITED:
        salary_service.mark_credited(db, record, current_user, payload.credit_date)
    else:
        record.status = payload.status

    db.commit()
    db.refresh(record)
    return SalaryOut(**salary_out(record))


class AutoGenerateRequest(BaseModel):
    month: Optional[str] = None  # "YYYY-MM"; default the current month


@router.post("/auto-generate")
def auto_generate_salaries(
    payload: AutoGenerateRequest = AutoGenerateRequest(),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr),
):
    """Run the monthly generation now (the background job does the same on its own).

    HR only generates for the people they manage; the Admin for everyone.
    Existing months are never duplicated and future months are never created.
    """
    up_to = None
    if payload.month:
        try:
            year, month = (int(x) for x in payload.month.split("-"))
            if not 1 <= month <= 12:
                raise ValueError
        except ValueError:
            raise HTTPException(status_code=422, detail="month must look like 2026-11.")
        today = local_today()
        if (year, month) > (today.year, today.month):
            raise HTTPException(status_code=422, detail="Salary slips are not generated for future months.")
        up_to = (year, month)
    scope = hierarchy_service.visible_employee_ids(db, current_user, include_self=False)
    summary = salary_autogen_service.run(db, actor=current_user, up_to=up_to, employee_ids=scope)
    db.commit()
    return summary


@router.get("/{salary_id}", response_model=SalaryOut)
def get_salary(
    salary_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return SalaryOut(**salary_out(_load(db, salary_id, current_user)))


@router.put("/{salary_id}", response_model=SalaryOut)
def update_salary(
    salary_id: int,
    payload: SalaryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr),
):
    record = _load(db, salary_id, current_user, level="manage")
    changes = payload.model_dump(exclude_unset=True)
    components = changes.pop("components", None)
    new_status = changes.pop("status", None)

    for field, value in changes.items():
        setattr(record, field, value)
    if components is not None:
        salary_service.replace_components(db, record, components)

    audit_service.record(
        db, AuditAction.SALARY_UPDATED, user=current_user, entity_type="salary_record",
        entity_id=record.id, meta={"fields": list(changes), "components_replaced": components is not None},
    )

    # Keep a generated payslip PDF in step with the edited amounts (an
    # uploaded payslip file is HR's own document and is left alone).
    if (components is not None or "working_days" in changes) and record.slip is not None \
            and record.slip.source == "generated":
        db.flush()
        db.refresh(record)
        payslip_service.generate_and_store(db, record, actor=current_user)

    if new_status == SalaryStatus.CREDITED:
        # Re-saving an already-credited record will not re-notify or re-email.
        salary_service.mark_credited(db, record, current_user, record.credit_date)
    elif new_status:
        record.status = new_status

    db.commit()
    db.refresh(record)
    return SalaryOut(**salary_out(record))


@router.post("/{salary_id}/credit", response_model=SalaryCreditResult)
def credit_salary(
    salary_id: int,
    payload: SalaryCreditRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr),
):
    record = _load(db, salary_id, current_user, level="manage")
    outcome = salary_service.mark_credited(
        db, record, current_user, payload.credit_date, payload.attach_payslip
    )
    db.commit()
    db.refresh(record)

    if outcome["notification_created"]:
        detail = "Salary credited. The employee has been notified."
    else:
        detail = "Salary was already credited; no duplicate notification or email was sent."

    return SalaryCreditResult(
        salary=SalaryOut(**salary_out(record)),
        notification_created=outcome["notification_created"],
        email_sent=outcome["email_sent"],
        payslip_ready=outcome["payslip_ready"],
        detail=detail,
    )


@router.post("/{salary_id}/payslip/generate", response_model=SalaryOut)
def generate_payslip(
    salary_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr),
):
    record = _load(db, salary_id, current_user, level="manage")
    payslip_service.generate_and_store(db, record, actor=current_user)
    db.commit()
    db.refresh(record)
    return SalaryOut(**salary_out(record))


@router.post("/{salary_id}/payslip/upload", response_model=SalaryOut)
async def upload_payslip(
    salary_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr),
):
    record = _load(db, salary_id, current_user, level="manage")
    content, ext, mime, _ = await file_service.validate_and_read(
        file, allowed_extensions={"pdf"}, max_size=5 * 1024 * 1024
    )
    payslip_service.store_uploaded(db, record, content, file.filename, mime, current_user)
    db.commit()
    db.refresh(record)
    return SalaryOut(**salary_out(record))


def _stream_payslip(record: SalaryRecord, inline: bool):
    slip = record.slip
    if slip is None:
        raise HTTPException(
            status_code=404, detail="No payslip has been generated for this pay period yet."
        )
    path = file_service.resolve_path(file_service.PAYSLIPS, slip.stored_filename)
    if not path.exists():
        raise HTTPException(status_code=404, detail="The payslip file is missing.")
    disposition = "inline" if inline else "attachment"
    return StreamingResponse(
        iter([path.read_bytes()]),
        media_type=slip.mime_type or "application/pdf",
        headers={
            "Content-Disposition": f'{disposition}; filename="{slip.original_filename}"'
        },
    )


@router.get("/{salary_id}/payslip")
def view_payslip(
    salary_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    record = _load(db, salary_id, current_user)
    if not _manages(db, current_user, record) and record.status != SalaryStatus.CREDITED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your payslip becomes available once the salary is credited.",
        )
    return _stream_payslip(record, inline=True)


@router.get("/{salary_id}/payslip/download")
def download_payslip(
    salary_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Downloading is gated. Interns need HR permission on this salary record.

    The check runs here, not in the browser: disabling the button is a courtesy,
    this is the rule.
    """
    record = _load(db, salary_id, current_user)
    hr_user = _manages(db, current_user, record)
    allowed, reason = salary_service.can_download_payslip(record, hr_user)
    if not allowed:
        if record.employee is not None and record.employee.is_intern:
            audit_service.record(
                db, AuditAction.INTERN_PAYSLIP_DOWNLOAD_DENIED, user=current_user,
                entity_type="salary_record", entity_id=record.id,
                meta={"employee_id": record.employee_id, "period": record.period_label},
                commit=True,
            )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=reason)

    if not hr_user and record.employee is not None and record.employee.is_intern:
        audit_service.record(
            db, AuditAction.INTERN_PAYSLIP_DOWNLOADED, user=current_user,
            entity_type="salary_record", entity_id=record.id,
            meta={"employee_id": record.employee_id, "period": record.period_label},
            commit=True,
        )
    return _stream_payslip(record, inline=False)


@router.post("/{salary_id}/download-request", response_model=DownloadRequestOut,
             status_code=status.HTTP_201_CREATED)
def request_payslip_download(
    salary_id: int,
    payload: DownloadRequestIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    employee: Employee = Depends(get_current_employee),
):
    """An intern asks HR for permission to download this one payslip."""
    record = _load(db, salary_id, current_user)
    request = intern_payslip_request_service.create_request(
        db, record, employee, current_user, payload.reason
    )
    db.commit()
    db.refresh(request)
    from app.api.intern_payslip_requests import serialize

    return DownloadRequestOut(**serialize(request))


@router.post("/{salary_id}/payslip-permission", response_model=PayslipPermissionResult)
def set_payslip_permission(
    salary_id: int,
    payload: PayslipPermissionIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr),
):
    """Grant or withdraw an intern's permission to download this payslip."""
    record = _load(db, salary_id, current_user, level="manage")
    result = salary_service.set_intern_download_permission(
        db, record, current_user, payload.allowed
    )
    db.commit()
    return PayslipPermissionResult(**result)
