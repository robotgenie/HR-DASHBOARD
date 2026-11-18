from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.api.serializers import employee_detail, employee_list_item, redact_for_viewer
from app.core.constants import (
    INTERNSHIP_DEPARTMENT_NAME, LOCKED_FIELD_LABELS, LOCKED_IDENTITY_FIELDS,
    AuditAction, EmploymentStatus, ProfileChangeStatus, SalaryStatus,
)
from app.core.constants import RoleName
from app.core.dependencies import (
    assert_can_access_employee, get_current_employee, get_current_user, is_hr, require_hr,
    require_supervisor,
)
from app.models.role import Role
from app.database.database import get_db
from app.models.department import Department
from app.models.employee import Employee
from app.models.user import User
from app.schemas.common import Message, Page, PageMeta
from app.models.profile_change_request import ProfileChangeRequest
from app.schemas.employee import (
    EmployeeCreate, EmployeeCreated, EmployeeDetail, EmployeeListItem,
    EmployeeSelfUpdate, EmployeeUpdate,
)
from app.schemas.profile_change import IdCardOut, ProfileLockState, RequestableField
from app.services import (
    audit_service, document_service, employee_service, file_service, hierarchy_service,
    idcard_service, profile_change_service,
)

router = APIRouter(prefix="/employees", tags=["Employees"])

SORTABLE = {
    "full_name": Employee.full_name,
    "employee_code": Employee.employee_code,
    "unique_employee_id": Employee.unique_employee_id,
    "joining_date": Employee.joining_date,
    "designation": Employee.designation,
    "employment_status": Employee.employment_status,
}


def _base_query(db: Session):
    return db.query(Employee).options(
        joinedload(Employee.user),
        joinedload(Employee.department),
        joinedload(Employee.internship_background),
        joinedload(Employee.uan),
    )


@router.get("", response_model=Page[EmployeeListItem])
def list_employees(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_supervisor),
    search: Optional[str] = None,
    department_id: Optional[int] = None,
    internship_background_id: Optional[int] = None,
    employee_type: Optional[str] = Query(None, description="Intern | Regular"),
    role: Optional[str] = Query(None, description="HR_ADMIN | MANAGER | EMPLOYEE"),
    person_type: Optional[str] = Query(None, description="HR | Manager | Employee | Intern"),
    reporting_hr_id: Optional[int] = None,
    reporting_manager_id: Optional[int] = None,
    include_self: bool = True,
    designation: Optional[str] = None,
    employment_status: Optional[str] = None,
    joined_from: Optional[date] = None,
    joined_to: Optional[date] = None,
    document_status: Optional[str] = Query(None, description="complete | incomplete"),
    salary_status: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    sort_by: str = Query("full_name"),
    sort_dir: str = Query("asc", pattern="^(asc|desc)$"),
):
    query = _base_query(db).join(User, Employee.user_id == User.id)
    # Hierarchy: Admin everyone, HR their hierarchy, Manager their team.
    query = hierarchy_service.restrict(query, db, current_user, Employee.id, include_self=include_self)

    if role or person_type:
        query = query.join(Role, User.role_id == Role.id)
        wanted_role = role
        if person_type:
            wanted_role = {
                "HR": RoleName.HR_ADMIN, "Manager": RoleName.MANAGER,
                "Employee": RoleName.EMPLOYEE, "Intern": RoleName.EMPLOYEE,
            }.get(person_type)
            if wanted_role is None:
                raise HTTPException(status_code=422, detail="person_type must be HR, Manager, Employee or Intern.")
            if person_type in ("Employee", "Intern"):
                employee_type = "Intern" if person_type == "Intern" else "Regular"
        if wanted_role not in RoleName.EMPLOYEE_SIDE:
            raise HTTPException(status_code=422, detail="Unknown role.")
        query = query.filter(Role.name == wanted_role)
    if reporting_hr_id:
        query = query.filter(Employee.reporting_hr_id == reporting_hr_id)
    if reporting_manager_id:
        query = query.filter(Employee.reporting_manager_id == reporting_manager_id)

    if internship_background_id is not None:
        query = query.filter(Employee.internship_background_id == internship_background_id)

    if employee_type:
        if employee_type not in ("Intern", "Regular"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="employee_type must be Intern or Regular.",
            )
        # Whether someone is an intern is decided by their department record,
        # never by a value the client sends alongside it.
        intern_dept = (
            db.query(Department.id)
            .filter(Department.name == INTERNSHIP_DEPARTMENT_NAME)
            .scalar_subquery()
        )
        if employee_type == "Intern":
            query = query.filter(Employee.department_id == intern_dept)
        else:
            query = query.filter(Employee.department_id != intern_dept)

    if search:
        needle = f"%{search.strip().lower()}%"
        query = query.filter(
            or_(
                func.lower(Employee.full_name).like(needle),
                func.lower(Employee.employee_code).like(needle),
                func.lower(Employee.unique_employee_id).like(needle),
                func.lower(User.email).like(needle),
            )
        )
    if department_id:
        query = query.filter(Employee.department_id == department_id)
    if designation:
        query = query.filter(func.lower(Employee.designation) == designation.lower())
    if employment_status:
        query = query.filter(Employee.employment_status == employment_status)
    if joined_from:
        query = query.filter(Employee.joining_date >= joined_from)
    if joined_to:
        query = query.filter(Employee.joining_date <= joined_to)

    column = SORTABLE.get(sort_by, Employee.full_name)
    query = query.order_by(column.desc() if sort_dir == "desc" else column.asc())

    rows = query.all()
    items = [redact_for_viewer(db, current_user, e, employee_list_item(db, e)) for e in rows]

    # Derived filters run after serialisation: they depend on computed values.
    if document_status == "complete":
        items = [i for i in items if (i["document_completion"] or 0) >= 100]
    elif document_status == "incomplete":
        items = [i for i in items if (i["document_completion"] or 0) < 100]
    if salary_status:
        items = [i for i in items if i["salary_status"] == salary_status]

    total = len(items)
    start = (page - 1) * page_size
    return Page[EmployeeListItem](
        items=items[start: start + page_size],
        meta=PageMeta(
            page=page, page_size=page_size, total=total,
            pages=(total + page_size - 1) // page_size if page_size else 0,
        ),
    )


@router.post("", response_model=EmployeeCreated, status_code=status.HTTP_201_CREATED)
def create_employee(
    payload: EmployeeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr),
):
    data = payload.model_dump()
    data["reporting_hr_id"], data["reporting_manager_id"] = employee_service.normalise_reporting(
        db, data.get("reporting_hr_id"), data.get("reporting_manager_id")
    )
    role_name = data.get("role") or RoleName.EMPLOYEE
    # HR create people inside their own hierarchy by default.
    if hierarchy_service.is_hr(current_user) and role_name != RoleName.HR_ADMIN and not data["reporting_hr_id"] \
            and not data["reporting_manager_id"]:
        data["reporting_hr_id"] = current_user.employee.id if current_user.employee else None
    hierarchy_service.authorize_assignment(
        db, current_user, None, role=role_name,
        reporting_hr_id=data["reporting_hr_id"], reporting_manager_id=data["reporting_manager_id"],
    )
    employee, raw_password = employee_service.create_employee(
        db, data, actor=current_user, send_email=payload.send_account_email
    )
    db.commit()
    db.refresh(employee)
    return EmployeeCreated(
        employee=EmployeeDetail(**employee_detail(db, employee)),
        initial_password=raw_password,
        account_email_sent=payload.send_account_email,
    )


@router.get("/me", response_model=EmployeeDetail)
def my_profile(
    db: Session = Depends(get_db), employee: Employee = Depends(get_current_employee)
):
    # Existing HR/Admin accounts with a complete profile get their ID without a request.
    if employee_service.auto_approve_hr_id(db, employee):
        db.commit()
        db.refresh(employee)
    return EmployeeDetail(**employee_detail(db, employee))


@router.put("/me", response_model=EmployeeDetail)
def update_my_profile(
    payload: EmployeeSelfUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    employee: Employee = Depends(get_current_employee),
):
    """Contact fields only, and locked identity fields not at all.

    Department, designation, salary and status stay HR-controlled. Once the
    profile is complete the identity fields lock: an employee changing one has
    to raise a profile change request, and this endpoint rejects the write even
    if the UI is bypassed.
    """
    changes = payload.model_dump(exclude_unset=True)

    if employee.identity_locked:
        blocked = [
            field for field in changes
            if field in LOCKED_IDENTITY_FIELDS
            and str(changes[field] or "") != str(getattr(employee, field, "") or "")
        ]
        if blocked:
            labels = ", ".join(LOCKED_FIELD_LABELS.get(f, f) for f in blocked)
            audit_service.record(
                db, AuditAction.PROFILE_LOCKED_EDIT_DENIED, user=current_user,
                entity_type="employee", entity_id=employee.id,
                meta={"fields": blocked, "via": "PUT /employees/me"},
                commit=True,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"{labels} can only be changed with HR approval. Raise a "
                    "profile change request from your profile page."
                ),
            )

    for field, value in changes.items():
        setattr(employee, field, value)
    db.flush()
    issued = employee_service.auto_approve_hr_id(db, employee, actor=current_user)
    audit_service.record(
        db, AuditAction.EMPLOYEE_UPDATED, user=current_user, entity_type="employee",
        entity_id=employee.id,
        meta={
            "self_service": True,
            "fields": list(changes),
            "employee_id_issued": issued,
        },
    )
    db.commit()
    db.refresh(employee)
    return EmployeeDetail(**employee_detail(db, employee))


@router.post("/me/photo", response_model=EmployeeDetail)
async def upload_my_photo(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    employee: Employee = Depends(get_current_employee),
):
    """Submit a new photograph for HR approval.

    The upload is stored as a new version of the employee's Photograph document
    with status Pending. It becomes the official profile / ID-card photo only
    when HR verifies it (see document_service.review); until then the previous
    approved photo (if any) stays in use.
    """
    from app.models.document_type import DocumentType

    doc_type = (
        db.query(DocumentType)
        .filter(DocumentType.code == "PHOTO", DocumentType.is_active.is_(True))
        .first()
    )
    if doc_type is None:
        raise HTTPException(status_code=409, detail="The Photograph document type is not configured.")
    content, ext, mime, digest = await file_service.validate_and_read(
        file, allowed_extensions=doc_type.extension_set or {"png", "jpg", "jpeg", "webp"},
        max_size=min(doc_type.max_size_mb, 4) * 1024 * 1024,
    )
    document_service.upload_version(
        db, employee, doc_type, content, file.filename, mime, digest, current_user
    )
    audit_service.record(
        db, AuditAction.PHOTO_SUBMITTED, user=current_user, entity_type="employee",
        entity_id=employee.id, meta={"status": "Pending HR approval"},
    )
    db.commit()
    db.refresh(employee)
    return EmployeeDetail(**employee_detail(db, employee))


@router.get("/id-approval-requests", response_model=Page[EmployeeDetail])
def id_approval_requests(
    status_filter: Optional[str] = Query("Pending", alias="status"),
    search: Optional[str] = None,
    department_id: Optional[int] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr),
):
    query = hierarchy_service.restrict_managed(_base_query(db), db, current_user, Employee.id)
    if status_filter and status_filter.lower() != "all":
        value = status_filter.title()
        if value not in ("Pending", "Approved", "Rejected"):
            raise HTTPException(status_code=422, detail="status must be Pending, Approved or Rejected.")
        query = query.filter(Employee.id_card_status == value)
    if search:
        needle = f"%{search.strip().lower()}%"
        query = query.filter(
            or_(
                func.lower(Employee.full_name).like(needle),
                func.lower(Employee.employee_code).like(needle),
                func.lower(Employee.unique_employee_id).like(needle),
                func.lower(User.email).like(needle),
            )
        ).join(User, Employee.user_id == User.id)
    if department_id:
        query = query.filter(Employee.department_id == department_id)
    query = query.order_by(Employee.id_card_requested_at.desc().nullslast(), Employee.id.desc())
    rows = query.all()
    items = [EmployeeDetail(**employee_detail(db, e)) for e in rows]
    total = len(items)
    start = (page - 1) * page_size
    return Page[EmployeeDetail](
        items=items[start:start + page_size],
        meta=PageMeta(page=page, page_size=page_size, total=total, pages=(total + page_size - 1) // page_size if page_size else 0),
    )


@router.get("/{employee_id}", response_model=EmployeeDetail)
def get_employee(
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    employee = assert_can_access_employee(current_user, employee_id, db)
    return EmployeeDetail(**redact_for_viewer(db, current_user, employee, employee_detail(db, employee)))


@router.put("/{employee_id}", response_model=EmployeeDetail)
def update_employee(
    employee_id: int,
    payload: EmployeeUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr),
):
    employee = assert_can_access_employee(current_user, employee_id, db, level="manage")

    changes = payload.model_dump(exclude_unset=True)
    hierarchy_changes = {}
    if any(k in changes for k in ("role", "reporting_hr_id", "reporting_manager_id")):
        new_role = changes.pop("role", None)
        hr_id = changes.pop("reporting_hr_id", hierarchy_service.UNSET)
        mgr_id = changes.pop("reporting_manager_id", hierarchy_service.UNSET)
        if hr_id is hierarchy_service.UNSET and mgr_id not in (hierarchy_service.UNSET, None):
            legacy_hr, legacy_mgr = employee_service.normalise_reporting(db, None, mgr_id)
            if legacy_hr is not None:
                hr_id, mgr_id = legacy_hr, None
        # Unchanged values sent back by the edit form are not a change request.
        if new_role == employee.role_name:
            new_role = None
        if hr_id is not hierarchy_service.UNSET and hr_id == employee.reporting_hr_id:
            hr_id = hierarchy_service.UNSET
        if mgr_id is not hierarchy_service.UNSET and mgr_id == employee.reporting_manager_id:
            mgr_id = hierarchy_service.UNSET
        if new_role is not None or hr_id is not hierarchy_service.UNSET or mgr_id is not hierarchy_service.UNSET:
            hierarchy_service.authorize_assignment(
                db, current_user, employee, role=new_role,
                reporting_hr_id=hr_id, reporting_manager_id=mgr_id,
            )
            hierarchy_changes = hierarchy_service.apply_assignment(
                db, current_user, employee,
                role=new_role if new_role is not None else hierarchy_service.UNSET,
                reporting_hr_id=hr_id, reporting_manager_id=mgr_id,
            )

    if "department_id" in changes or "internship_background_id" in changes:
        department_id = changes.get("department_id", employee.department_id)
        background_id = changes.get(
            "internship_background_id", employee.internship_background_id
        )
        department, background = employee_service.validate_department_background(
            db, department_id, background_id
        )
        changes["department_id"] = department.id
        changes["internship_background_id"] = background.id if background else None

    if "employment_status" in changes and changes["employment_status"] not in EmploymentStatus.ALL:
        raise HTTPException(status_code=422, detail="Unknown employment status.")

    if "work_location" in changes:
        changes["work_location"] = (changes["work_location"] or "").strip() or None
    location_changed = "work_location" in changes and changes["work_location"] != employee.work_location

    for field, value in changes.items():
        setattr(employee, field, value)
    db.flush()
    employee_service.auto_approve_hr_id(db, employee, actor=current_user)
    if location_changed:
        # Salary slips not yet credited show the new location; credited ones keep theirs.
        from app.services import bank_details_service
        bank_details_service.refresh_payslips(db, employee, current_user, include_credited=False)

    audit_service.record(
        db, AuditAction.EMPLOYEE_UPDATED, user=current_user, entity_type="employee",
        entity_id=employee.id, meta={"fields": list(changes) + list(hierarchy_changes)},
    )
    db.commit()
    db.refresh(employee)
    return EmployeeDetail(**employee_detail(db, employee))


@router.post("/{employee_id}/activate", response_model=EmployeeDetail)
def activate_employee(
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr),
):
    employee = assert_can_access_employee(current_user, employee_id, db, level="manage")
    employee_service.set_active(db, employee, True, current_user)
    db.commit()
    db.refresh(employee)
    return EmployeeDetail(**employee_detail(db, employee))


@router.post("/{employee_id}/deactivate", response_model=EmployeeDetail)
def deactivate_employee(
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr),
):
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found.")
    if employee.user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You can't deactivate your own account.",
        )
    assert_can_access_employee(current_user, employee_id, db, level="manage")
    employee_service.set_active(db, employee, False, current_user)
    db.commit()
    db.refresh(employee)
    return EmployeeDetail(**employee_detail(db, employee))


@router.get("/{employee_id}/photo")
def get_employee_photo(
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Photos are served through this authenticated route, never from a static dir."""
    from fastapi.responses import FileResponse

    employee = assert_can_access_employee(current_user, employee_id, db)
    if not employee.photo_path:
        raise HTTPException(status_code=404, detail="No photo uploaded.")
    path = file_service.resolve_path(file_service.PHOTOS, employee.photo_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Photo file is missing.")
    return FileResponse(path)


# --------------------------------------------------------------------------
# Electronic employee ID card
# --------------------------------------------------------------------------

def _load_for_card(db: Session, employee_id: Optional[int], current_user: User) -> Employee:
    """HR may open anyone's card; an employee only their own."""
    if employee_id is None:
        employee = (
            _base_query(db).filter(Employee.user_id == current_user.id).first()
        )
        if employee is None:
            raise HTTPException(status_code=404, detail="No employee profile found.")
        return employee
    return assert_can_access_employee(current_user, employee_id, db)


@router.get("/me/id-card", response_model=IdCardOut)
def my_id_card(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    """Card data for the employee's own electronic ID card."""
    employee = _load_for_card(db, None, current_user)
    return IdCardOut(**idcard_service.card_data(db, employee))


@router.get("/me/id-card/pdf")
def my_id_card_pdf(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    employee = _load_for_card(db, None, current_user)
    content = idcard_service.build_pdf(db, employee, actor=current_user)
    return StreamingResponse(
        iter([content]),
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{idcard_service.filename(employee)}"'
            )
        },
    )


@router.get("/me/profile-lock", response_model=ProfileLockState)
def my_profile_lock(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    """Which identity fields are locked, their values, and what is pending."""
    employee = _load_for_card(db, None, current_user)
    pending = {
        row.field_name
        for row in db.query(ProfileChangeRequest).filter(
            ProfileChangeRequest.employee_id == employee.id,
            ProfileChangeRequest.status == ProfileChangeStatus.PENDING,
        )
    }
    return ProfileLockState(
        identity_locked=employee.identity_locked,
        identity_locked_at=employee.identity_locked_at,
        fields=[
            RequestableField(
                field_name=field,
                label=LOCKED_FIELD_LABELS[field],
                current_value=profile_change_service.current_value(employee, field),
                pending=field in pending,
            )
            for field in LOCKED_IDENTITY_FIELDS
        ],
    )


@router.post("/me/request-id-approval", response_model=EmployeeDetail)
def request_my_employee_id_approval(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    employee = _load_for_card(db, None, current_user)
    employee_service.request_employee_id_approval(db, employee, actor=current_user)
    db.commit()
    db.refresh(employee)
    return EmployeeDetail(**employee_detail(db, employee))


@router.get("/{employee_id}/id-card", response_model=IdCardOut)
def employee_id_card(
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    employee = _load_for_card(db, employee_id, current_user)
    return IdCardOut(**idcard_service.card_data(db, employee))


@router.get("/{employee_id}/id-card/pdf")
def employee_id_card_pdf(
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    employee = _load_for_card(db, employee_id, current_user)
    content = idcard_service.build_pdf(db, employee, actor=current_user)
    return StreamingResponse(
        iter([content]),
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{idcard_service.filename(employee)}"'
            )
        },
    )


@router.post("/{employee_id}/approve-id", response_model=EmployeeDetail)
def approve_employee_id(
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr),
):
    employee = assert_can_access_employee(current_user, employee_id, db, level="manage")
    employee_service.approve_employee_id(db, employee, current_user)
    db.commit()
    db.refresh(employee)
    return EmployeeDetail(**employee_detail(db, employee))


@router.post("/{employee_id}/reject-id", response_model=EmployeeDetail)
def reject_employee_id(
    employee_id: int,
    remarks: str = Query(..., min_length=1, max_length=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr),
):
    employee = assert_can_access_employee(current_user, employee_id, db, level="manage")
    employee_service.reject_employee_id(db, employee, current_user, remarks)
    db.commit()
    db.refresh(employee)
    return EmployeeDetail(**employee_detail(db, employee))
