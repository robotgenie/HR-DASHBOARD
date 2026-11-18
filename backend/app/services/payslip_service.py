"""Payslip generation, storage and retrieval."""
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.utils.timeutil import utcnow
from app.core.constants import AuditAction
from app.models.salary import SalaryRecord
from app.models.salary_slip import SalarySlip
from app.models.user import User
from app.pdf.payslip_generator import build_payslip_pdf
from app.utils.amount_words import amount_to_words
from app.services import audit_service, file_service


MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def payslip_period_label(record: SalaryRecord) -> str:
    """'March, 2026' - the comma form the payslip title uses."""
    month = MONTH_NAMES[record.period_month - 1] if 1 <= record.period_month <= 12 else ""
    return f"{month}, {record.period_year}".strip(", ")


def work_location_for(employee) -> Optional[str]:
    """The employee's own work location, else the company default from Settings."""
    if employee.work_location and employee.work_location.strip():
        return employee.work_location.strip()
    from sqlalchemy.orm import object_session
    from app.core.constants import SettingKey
    from app.services import settings_service
    db = object_session(employee)
    if db is None:
        return None
    value = settings_service.get(db, SettingKey.DEFAULT_WORK_LOCATION, "")
    return (str(value).strip() or None) if value else None


def build_bytes(record: SalaryRecord) -> bytes:
    """Render the PDF for a salary record straight from the database values."""
    from app.services.salary_service import component_tuples

    employee = record.employee
    earnings, deductions = component_tuples(record)

    return build_payslip_pdf(
        employee_name=employee.full_name,
        employee_code=employee.display_employee_id,
        designation=employee.designation,
        department=employee.department.name if employee.department else "-",
        pay_period=payslip_period_label(record),
        working_days=record.working_days,
        lop_days=record.lop_days,
        location=work_location_for(employee),
        bank_name=employee.bank_name,
        bank_account_no=employee.bank_account_no,
        pan_number=employee.pan_number,
        earnings=earnings,
        deductions=deductions,
        total_earnings=record.total_earnings,
        total_deductions=record.total_deductions,
        net_pay=record.net_pay,
        amount_in_words=amount_to_words(record.net_pay),
    )


def generate_and_store(
    db: Session, record: SalaryRecord, actor: Optional[User] = None
) -> SalarySlip:
    """Generate the payslip PDF and attach it to the salary record."""
    content = build_bytes(record)
    employee = record.employee
    original = (
        f"Payslip-{employee.employee_code}-"
        f"{record.period_label.replace(' ', '-')}.pdf"
    )
    stored = file_service.build_stored_name(f"payslip_{employee.employee_code}", original)
    file_service.save_bytes(file_service.PAYSLIPS, stored, content)

    slip = record.slip
    if slip is None:
        slip = SalarySlip(salary_record_id=record.id)
        # Assign through the relationship so record.slip is populated immediately.
        record.slip = slip
        db.add(slip)
    else:
        # Replace the file but keep one slip row per salary record.
        try:
            file_service.delete_file(file_service.PAYSLIPS, slip.stored_filename)
        except Exception:  # noqa: BLE001
            pass

    slip.stored_filename = stored
    slip.original_filename = original
    slip.mime_type = "application/pdf"
    slip.file_size = len(content)
    slip.source = "generated"
    slip.uploaded_by_id = actor.id if actor else None
    slip.created_at = utcnow()
    db.flush()

    audit_service.record(
        db, AuditAction.PAYSLIP_GENERATED, user=actor, entity_type="salary_slip",
        entity_id=slip.id, meta={"salary_id": record.id, "period": record.period_label},
    )
    return slip


def store_uploaded(
    db: Session, record: SalaryRecord, content: bytes, original_filename: str,
    mime_type: str, actor: User,
) -> SalarySlip:
    """HR can upload their own payslip file instead of using the generated one."""
    stored = file_service.build_stored_name(
        f"payslip_{record.employee.employee_code}", original_filename
    )
    file_service.save_bytes(file_service.PAYSLIPS, stored, content)

    slip = record.slip
    if slip is None:
        slip = SalarySlip(salary_record_id=record.id)
        record.slip = slip
        db.add(slip)

    slip.stored_filename = stored
    slip.original_filename = original_filename
    slip.mime_type = mime_type
    slip.file_size = len(content)
    slip.source = "uploaded"
    slip.uploaded_by_id = actor.id
    db.flush()

    audit_service.record(
        db, AuditAction.PAYSLIP_UPLOADED, user=actor, entity_type="salary_slip",
        entity_id=slip.id, meta={"salary_id": record.id, "filename": original_filename},
    )
    return slip


def read_slip_bytes(slip: SalarySlip) -> Optional[bytes]:
    path = file_service.resolve_path(file_service.PAYSLIPS, slip.stored_filename)
    return path.read_bytes() if path.exists() else None
