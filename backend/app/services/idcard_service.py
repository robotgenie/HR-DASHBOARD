"""Electronic ID card: card data for the UI and the printable PDF."""
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import AuditAction, RoleName
from app.models.employee import Employee
from app.models.user import User
from app.pdf.idcard_generator import build_id_card_pdf
from app.services import audit_service, employee_service, file_service, settings_service


def availability(db: Session, employee: Employee) -> dict:
    """Whether the card can be issued, and what is still missing if not."""
    missing = employee_service.missing_profile_fields(employee)
    return {
        "available": bool(employee.unique_employee_id) and not missing and getattr(employee, "id_card_status", "Approved") == "Approved",
        "id_card_status": getattr(employee, "id_card_status", "Approved" if employee.unique_employee_id else "Pending"),
        "approval_remarks": getattr(employee, "id_card_approval_remarks", None),
        "missing_fields": missing,
        "unique_employee_id": employee.unique_employee_id,
        "issued_at": employee.id_card_issued_at,
    }


def _photo_path(employee: Employee) -> Optional[Path]:
    if not employee.photo_path:
        return None
    try:
        return file_service.resolve_path(file_service.PHOTOS, employee.photo_path)
    except Exception:  # noqa: BLE001 - a bad stored name must not break the card
        return None


def card_data(db: Session, employee: Employee) -> dict:
    """Everything the UI needs to render the card, plus its availability."""
    state = availability(db, employee)
    company_name = settings_service.get(db, "company_name", settings.COMPANY_NAME)
    company_address = settings_service.get(
        db, "company_address", settings.COMPANY_ADDRESS
    )
    return {
        **state,
        "employee_id": employee.id,
        "full_name": employee.full_name,
        "employee_code": employee.employee_code,
        "department": employee.department.name if employee.department else None,
        "internship_background": (
            employee.internship_background.name if employee.internship_background else None
        ),
        "designation": employee.designation,
        "joining_date": employee.joining_date,
        "email": employee.user.email if employee.user else None,
        "phone": employee.phone,
        "photo_path": employee.photo_path,
        "company_name": company_name,
        "company_address": company_address,
    }


def assert_available(db: Session, employee: Employee) -> None:
    state = availability(db, employee)
    if state["available"]:
        return
    if state["missing_fields"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "The ID card is generated once the profile is complete. Still "
                f"needed: {', '.join(state['missing_fields'])}."
            ),
        )
    if state.get("id_card_status") == "Pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Your ID card is awaiting HR/Admin approval.")
    if state.get("id_card_status") == "Rejected":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=state.get("approval_remarks") or "Your ID card request was rejected. Please contact HR.")
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No Employee ID has been issued for this profile yet.")


def build_pdf(db: Session, employee: Employee, actor: Optional[User] = None) -> bytes:
    assert_available(db, employee)
    data = card_data(db, employee)
    content = build_id_card_pdf(
        full_name=employee.full_name,
        unique_employee_id=employee.unique_employee_id,
        department=data["department"] or "-",
        designation=employee.designation,
        date_of_joining=(
            employee.joining_date.strftime("%d %b %Y") if employee.joining_date else "-"
        ),
        email=data["email"] or "",
        phone=employee.phone or "",
        photo_path=_photo_path(employee),
        company_name=data["company_name"],
        company_address=data["company_address"],
        card_title="HR IDENTITY CARD" if employee.user and employee.user.role_name == RoleName.HR_ADMIN else "EMPLOYEE IDENTITY CARD",
    )
    audit_service.record(
        db, AuditAction.ID_CARD_GENERATED, user=actor, entity_type="employee",
        entity_id=employee.id,
        meta={"unique_employee_id": employee.unique_employee_id, "format": "pdf"},
        commit=True,
    )
    return content


def filename(employee: Employee) -> str:
    safe = "".join(ch for ch in employee.full_name if ch.isalnum() or ch in " -_").strip()
    safe = safe.replace(" ", "-") or "Employee"
    return f"ID-Card-{employee.unique_employee_id}-{safe}.pdf"
