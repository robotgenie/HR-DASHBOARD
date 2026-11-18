"""Employee creation and lookup helpers."""
from datetime import date
from typing import Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.constants import (
    AuditAction, EMPLOYEE_ID_DIGITS, EMPLOYEE_ID_PREFIX, INTERNSHIP_DEPARTMENT_NAME,
    NotificationType, RoleName, SettingKey,
)
from app.core.security import generate_initial_password, hash_password
from app.models.department import Department
from app.models.employee import Employee
from app.models.internship_background import InternshipBackground
from app.models.role import Role
from app.models.uan import UanDetail
from app.models.user import User
from app.services import audit_service, email_service, notification_service, settings_service
from app.utils.timeutil import utcnow

# Fields that must all be filled before an employee id and ID card are issued.
# The photograph is mandatory: the ID card cannot be produced without it.
REQUIRED_PROFILE_FIELDS = (
    "full_name", "phone", "date_of_birth", "gender", "address",
    "emergency_contact_name", "emergency_contact_phone",
    "emergency_contact_relation", "designation", "photo_path",
)

PROFILE_FIELD_LABELS = {
    "full_name": "Full name",
    "phone": "Phone number",
    "date_of_birth": "Date of birth",
    "gender": "Gender",
    "address": "Address",
    "emergency_contact_name": "Emergency contact name",
    "emergency_contact_phone": "Emergency contact phone",
    "emergency_contact_relation": "Emergency contact relation",
    "designation": "Designation",
    "photo_path": "Profile photograph",
}


def missing_profile_fields(employee: Employee) -> list:
    """Human-readable list of what still blocks ID card generation."""
    return [
        PROFILE_FIELD_LABELS[f]
        for f in REQUIRED_PROFILE_FIELDS
        if not getattr(employee, f, None)
    ]


def profile_is_complete(employee: Employee) -> bool:
    return not missing_profile_fields(employee)


def next_unique_employee_id(db: Session) -> str:
    """Next id in the RGEMP001 sequence, derived from the highest issued one."""
    last = (
        db.query(Employee.unique_employee_id)
        .filter(Employee.unique_employee_id.like(f"{EMPLOYEE_ID_PREFIX}%"))
        .order_by(func.length(Employee.unique_employee_id).desc(),
                  Employee.unique_employee_id.desc())
        .first()
    )
    sequence = 1
    if last and last[0]:
        try:
            sequence = int(last[0][len(EMPLOYEE_ID_PREFIX):]) + 1
        except ValueError:
            sequence = db.query(func.count(Employee.id)).scalar() + 1
    return f"{EMPLOYEE_ID_PREFIX}{sequence:0{EMPLOYEE_ID_DIGITS}d}"


def issue_employee_id(db: Session, employee: Employee, actor: Optional[User] = None) -> bool:
    """Issue the unique employee id once the profile is complete.

    Returns True only when an id was issued by this call. Already-issued ids are
    never regenerated or overwritten, so this is safe to call on every profile
    save. Issuing also locks the identity fields.
    """
    if employee.unique_employee_id:
        return False
    if not profile_is_complete(employee):
        return False
    if getattr(employee, "id_card_status", "Pending") != "Approved":
        return False

    for _ in range(5):  # retry past a concurrent issue of the same number
        candidate = next_unique_employee_id(db)
        employee.unique_employee_id = candidate
        try:
            db.flush()
            break
        except IntegrityError:
            db.rollback()
            db.add(employee)
    else:
        return False

    now = utcnow()
    employee.employee_id_issued_at = now
    employee.id_card_issued_at = now
    if employee.identity_locked_at is None:
        employee.identity_locked_at = now
    db.flush()

    audit_service.record(
        db, AuditAction.EMPLOYEE_ID_GENERATED, user=actor, entity_type="employee",
        entity_id=employee.id,
        meta={"unique_employee_id": employee.unique_employee_id},
    )
    audit_service.record(
        db, AuditAction.ID_CARD_GENERATED, user=actor, entity_type="employee",
        entity_id=employee.id,
        meta={"unique_employee_id": employee.unique_employee_id},
    )
    if employee.user_id:
        notification_service.create(
            db,
            user_id=employee.user_id,
            title="Your Employee ID has been issued",
            message=(
                f"Your unique Employee ID is {employee.unique_employee_id}. "
                "Your electronic ID card is now available on your profile. "
                "Name, phone, email, date of birth and gender are now locked - "
                "raise a profile change request if any of them need correcting."
            ),
            type_=NotificationType.EMPLOYEE_ID_ISSUED,
            related_entity="employee",
            related_id=employee.id,
            dedupe_key=f"employee:{employee.id}:id_issued",
            actor=actor,
        )
    return True


def is_hr_account(employee: Employee) -> bool:
    return bool(employee.user and employee.user.role_name == RoleName.HR_ADMIN)


def auto_approve_hr_id(db: Session, employee: Employee, actor: Optional[User] = None) -> bool:
    """HR/Admin IDs never wait in the approval queue.

    Once an HR account's profile is complete (including an HR-approved
    photograph) the ID is approved and issued automatically. Employee and intern
    accounts are untouched: they still go Request ID -> HR approval.
    Returns True when this call approved/issued the ID.
    """
    if not is_hr_account(employee):
        return False
    if employee.unique_employee_id and employee.id_card_status == "Approved":
        return False
    if missing_profile_fields(employee):
        return False
    now = utcnow()
    employee.id_card_status = "Approved"
    employee.id_card_requested_at = employee.id_card_requested_at or now
    employee.id_card_approved_at = employee.id_card_approved_at or now
    employee.id_card_rejected_at = None
    employee.id_card_approval_remarks = None
    employee.id_card_approved_by_id = employee.user_id
    db.flush()
    issue_employee_id(db, employee, actor=actor or employee.user)
    employee.id_card_issued_at = employee.id_card_issued_at or employee.employee_id_issued_at or now
    db.flush()
    audit_service.record(
        db, AuditAction.EMPLOYEE_ID_AUTO_APPROVED, user=actor or employee.user,
        entity_type="employee", entity_id=employee.id,
        meta={"unique_employee_id": employee.unique_employee_id, "reason": "HR/Admin account"},
    )
    return True


def request_employee_id_approval(db: Session, employee: Employee, actor: Optional[User] = None) -> Employee:
    """Create an ID-card approval request; never issue the final ID here.

    HR/Admin accounts are the exception: their ID is approved automatically.
    """
    if employee.unique_employee_id:
        employee.id_card_status = "Approved"
        return employee
    missing = missing_profile_fields(employee)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Complete your profile first. Still needed: " + ", ".join(missing) + ".",
        )
    if is_hr_account(employee):
        auto_approve_hr_id(db, employee, actor=actor)
        return employee
    employee.id_card_status = "Pending"
    employee.id_card_requested_at = utcnow()
    employee.id_card_rejected_at = None
    employee.id_card_approval_remarks = None
    db.flush()
    audit_service.record(
        db, AuditAction.ID_CARD_GENERATED, user=actor, entity_type="employee",
        entity_id=employee.id, meta={"action": "approval_requested"},
    )
    return employee


def approve_employee_id(db: Session, employee: Employee, approver: User) -> Employee:
    """Approve an ID request and issue the final immutable employee ID."""
    if employee.unique_employee_id:
        employee.id_card_status = "Approved"
        employee.id_card_approved_by_id = approver.id
        employee.id_card_approved_at = employee.id_card_approved_at or utcnow()
        employee.id_card_issued_at = employee.id_card_issued_at or employee.id_card_approved_at
        return employee
    missing = missing_profile_fields(employee)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Profile is incomplete. Still needed: " + ", ".join(missing) + ".",
        )
    if employee.id_card_status not in ("Pending", "Rejected"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="ID approval is not pending.")
    employee.id_card_status = "Approved"
    employee.id_card_approved_at = utcnow()
    employee.id_card_rejected_at = None
    employee.id_card_approved_by_id = approver.id
    issue_employee_id(db, employee, actor=approver)
    employee.identity_locked_at = employee.identity_locked_at or utcnow()
    employee.id_card_issued_at = employee.employee_id_issued_at or utcnow()
    notification_service.create(
        db, user_id=employee.user_id,
        title="Employee ID approved",
        message=f"Your Employee ID {employee.unique_employee_id} has been approved. Your ID card is now available.",
        type_=NotificationType.EMPLOYEE_ID_ISSUED, related_entity="employee",
        related_id=employee.id, dedupe_key=f"employee:{employee.id}:id_approved:{employee.unique_employee_id}",
        actor=approver,
    )
    db.flush()
    return employee


def reject_employee_id(db: Session, employee: Employee, approver: User, remarks: str) -> Employee:
    if employee.unique_employee_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An issued Employee ID cannot be rejected.")
    if employee.id_card_status != "Pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="ID approval is not pending.")
    employee.id_card_status = "Rejected"
    employee.id_card_rejected_at = utcnow()
    employee.id_card_approval_remarks = (remarks or "").strip() or None
    employee.id_card_approved_by_id = approver.id
    db.flush()
    return employee


def next_employee_code(db: Session) -> str:
    year = date.today().year
    prefix = f"RG-{year}-"
    last = (
        db.query(Employee.employee_code)
        .filter(Employee.employee_code.like(f"{prefix}%"))
        .order_by(Employee.employee_code.desc())
        .first()
    )
    sequence = 1
    if last and last[0]:
        try:
            sequence = int(last[0].rsplit("-", 1)[1]) + 1
        except (IndexError, ValueError):
            sequence = db.query(func.count(Employee.id)).scalar() + 1
    return f"{prefix}{sequence:04d}"


def validate_department_background(
    db: Session, department_id: int, internship_background_id: Optional[int]
) -> Tuple[Department, Optional[InternshipBackground]]:
    department = db.query(Department).filter(Department.id == department_id).first()
    if department is None or not department.is_active:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Pick an active department.",
        )

    background = None
    if department.name == INTERNSHIP_DEPARTMENT_NAME:
        if internship_background_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Interns need an internship background.",
            )
        background = (
            db.query(InternshipBackground)
            .filter(InternshipBackground.id == internship_background_id)
            .first()
        )
        if background is None or not background.is_active:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Pick an active internship background.",
            )
    return department, background


def create_employee(
    db: Session,
    payload,
    actor: Optional[User] = None,
    password: Optional[str] = None,
    send_email: bool = True,
) -> Tuple[Employee, str]:
    """Create the user account and the employee record together."""
    data = payload if isinstance(payload, dict) else payload.model_dump()
    email = data["email"].strip().lower()

    if db.query(User).filter(func.lower(User.email) == email).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That email address is already registered.",
        )

    department, background = validate_department_background(
        db, data["department_id"], data.get("internship_background_id")
    )
    employee_type = (data.get("employee_type") or "").strip()
    if employee_type:
        if employee_type not in ("Employee", "Intern"):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                detail="Employee type must be Employee or Intern.")
        is_intern_dept = department.name == INTERNSHIP_DEPARTMENT_NAME
        if employee_type == "Intern" and not is_intern_dept:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                detail="Interns belong to the Internship department.")
        if employee_type == "Employee" and is_intern_dept:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                detail="Choose employee type Intern for the Internship department.")

    role_name = data.get("role") or RoleName.EMPLOYEE
    if role_name not in RoleName.EMPLOYEE_SIDE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Employee accounts can be HR, Manager or Employee. Admins are created separately.",
        )
    role = db.query(Role).filter(Role.name == role_name).first()
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Unknown role."
        )

    raw_password = password or generate_initial_password()
    user = User(
        email=email,
        hashed_password=hash_password(raw_password),
        role_id=role.id,
        is_active=True,
        must_change_password=True,
    )
    db.add(user)
    db.flush()

    code = data.get("employee_code") or next_employee_code(db)
    if db.query(Employee).filter(Employee.employee_code == code).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="That employee ID is already in use."
        )

    employee = Employee(
        user_id=user.id,
        employee_code=code,
        full_name=data["full_name"].strip(),
        phone=data.get("phone"),
        date_of_birth=data.get("date_of_birth"),
        gender=data.get("gender"),
        department_id=department.id,
        internship_background_id=background.id if background else None,
        designation=data["designation"].strip(),
        joining_date=data["joining_date"],
        employment_status=data.get("employment_status") or "Active",
        internship_details=(data.get("internship_details") or None),
        address=data.get("address"),
        work_location=(data.get("work_location") or "").strip() or None,
        emergency_contact_name=data.get("emergency_contact_name"),
        emergency_contact_phone=data.get("emergency_contact_phone"),
        emergency_contact_relation=data.get("emergency_contact_relation"),
    )
    db.add(employee)
    db.flush()

    db.add(UanDetail(employee_id=employee.id))
    db.flush()

    reporting_hr_id, reporting_manager_id = normalise_reporting(
        db, data.get("reporting_hr_id"), data.get("reporting_manager_id")
    )
    if reporting_hr_id is not None or reporting_manager_id is not None:
        from app.services import hierarchy_service
        db.refresh(employee)
        hierarchy_service.apply_assignment(
            db, actor, employee, reporting_hr_id=reporting_hr_id,
            reporting_manager_id=reporting_manager_id, notify=False,
        )

    audit_service.record(
        db, AuditAction.EMPLOYEE_CREATED, user=actor, entity_type="employee",
        entity_id=employee.id,
        meta={"employee_code": code, "email": email, "department": department.name},
    )

    notification_service.create(
        db, user_id=user.id, title="Welcome to Rocket Genie",
        message="Your HR portal account is ready. Complete your profile and upload your documents.",
        type_=NotificationType.ACCOUNT, related_entity="user", related_id=user.id,
        dedupe_key=f"user:{user.id}:welcome", actor=actor,
    )

    if send_email and settings_service.get_bool(db, SettingKey.EMAIL_ENABLED, True):
        email_service.send_employee_account_email(
            db, email, employee.full_name, code, raw_password, user.id, actor=actor
        )

    return employee, raw_password


def normalise_reporting(db: Session, reporting_hr_id, reporting_manager_id):
    """Backwards compatibility for the original form, where "Reporting manager"
    listed HR staff: an HR picked there becomes the Reporting HR."""
    if reporting_manager_id and not reporting_hr_id:
        target = db.query(Employee).filter(Employee.id == reporting_manager_id).first()
        if target is not None and target.user is not None and target.user.role_name == RoleName.HR_ADMIN:
            return target.id, None
    return reporting_hr_id, reporting_manager_id


def set_active(db: Session, employee: Employee, active: bool, actor: User) -> Employee:
    employee.user.is_active = active
    employee.employment_status = "Active" if active else "Inactive"
    db.flush()
    audit_service.record(
        db,
        AuditAction.EMPLOYEE_ACTIVATED if active else AuditAction.EMPLOYEE_DEACTIVATED,
        user=actor, entity_type="employee", entity_id=employee.id,
        meta={"employee_code": employee.employee_code},
    )
    return employee
