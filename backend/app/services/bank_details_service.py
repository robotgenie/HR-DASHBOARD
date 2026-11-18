"""Bank details: employee submission -> HR/Admin approval -> official details.

* The employee enters Bank Name, Account Number (twice), IFSC and PAN on the
  Documents page, reviews them and confirms. That creates a BankDetailRequest
  with status "Pending Approval".
* HR (for their hierarchy) or the Admin approves or rejects it. Who may
  review is decided by hierarchy_service (the same "manage" level as document
  verification: never your own, never a Manager).
* Approval copies the values to the employee record (bank_name,
  bank_account_no, ifsc_code, pan_number). Those approved values are the only
  ones salary slips print, so a pending or rejected submission never replaces
  previously approved details.
"""
import re
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.constants import AuditAction, BankDetailStatus, NotificationType, SalaryStatus
from app.models.bank_detail_request import BankDetailRequest
from app.models.employee import Employee
from app.models.salary import SalaryRecord
from app.models.user import User
from app.services import audit_service, hierarchy_service, notification_service
from app.utils.timeutil import utcnow

IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
ACCOUNT_RE = re.compile(r"^[0-9]{9,18}$")
BANK_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9&().,' \-]{1,119}$")


# ------------------------------------------------------------- formatting
def mask_account(value: Optional[str]) -> Optional[str]:
    """'XXXX XXXX 1234' - only the last four digits are shown."""
    if not value:
        return None
    digits = re.sub(r"\s", "", value)
    return "XXXX XXXX " + digits[-4:]


def mask_pan(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return value[:2] + "XXXXX" + value[-3:] if len(value) == 10 else "XXXXXXXXXX"


def clean(data: dict) -> dict:
    """Normalise and validate a submission. Raises 422 with a clear message."""
    bank = " ".join(str(data.get("bank_name") or "").split())
    account = re.sub(r"[\s-]", "", str(data.get("account_number") or ""))
    confirm = re.sub(r"[\s-]", "", str(data.get("confirm_account_number") or ""))
    ifsc = str(data.get("ifsc_code") or "").strip().upper()
    pan = str(data.get("pan_number") or "").strip().upper()

    missing = [label for label, value in (
        ("Bank Name", bank), ("Bank Account Number", account),
        ("Confirm Bank Account Number", confirm), ("IFSC Code", ifsc), ("PAN Card Number", pan),
    ) if not value]
    if missing:
        raise HTTPException(status_code=422, detail="Required: " + ", ".join(missing) + ".")
    if not BANK_NAME_RE.match(bank):
        raise HTTPException(status_code=422, detail="Enter a valid bank name (2-120 letters).")
    if not ACCOUNT_RE.match(account):
        raise HTTPException(status_code=422, detail="Bank Account Number must be 9 to 18 digits.")
    if account != confirm:
        raise HTTPException(status_code=422, detail="Bank Account Number and Confirm Bank Account Number do not match.")
    if not IFSC_RE.match(ifsc):
        raise HTTPException(
            status_code=422,
            detail="IFSC Code must be 11 characters: 4 letters, then 0, then 6 letters or digits (e.g. HDFC0001234).",
        )
    if not PAN_RE.match(pan):
        raise HTTPException(
            status_code=422,
            detail="PAN must be 10 characters: 5 letters, 4 digits, 1 letter (e.g. ABCDE1234F).",
        )
    return {"bank_name": bank, "account_number": account, "ifsc_code": ifsc, "pan_number": pan}


def approved_block(employee: Employee, full: bool = False) -> Optional[dict]:
    if not employee.bank_account_no and not employee.bank_name:
        return None
    return {
        "bank_name": employee.bank_name,
        "account_number_masked": mask_account(employee.bank_account_no),
        "account_number": employee.bank_account_no if full else None,
        "ifsc_code": employee.ifsc_code,
        "pan_number": employee.pan_number,
        "approved_at": employee.bank_details_approved_at,
    }


def request_out(row: BankDetailRequest, full: bool = False) -> dict:
    e = row.employee
    return {
        "id": row.id,
        "employee_id": row.employee_id,
        "employee_name": e.full_name if e else None,
        "employee_code": e.display_employee_id if e else None,
        "department": e.department.name if e and e.department else None,
        "person_type": hierarchy_service.person_type(e) if e else None,
        "bank_name": row.bank_name,
        "account_number_masked": mask_account(row.account_number),
        "account_number": row.account_number if full else None,
        "ifsc_code": row.ifsc_code,
        "pan_number": row.pan_number if full else mask_pan(row.pan_number),
        "status": row.status,
        "submitted_at": row.created_at,
        "confirmed_at": row.confirmed_at,
        "reviewed_at": row.reviewed_at,
        "reviewed_by_name": row.reviewed_by.display_name if row.reviewed_by else None,
        "review_remarks": row.review_remarks,
        "replaces_approved": bool(e and e.bank_account_no),
    }


def latest(db: Session, employee: Employee) -> Optional[BankDetailRequest]:
    return (
        db.query(BankDetailRequest)
        .filter(BankDetailRequest.employee_id == employee.id,
                BankDetailRequest.status != BankDetailStatus.SUPERSEDED)
        .order_by(BankDetailRequest.created_at.desc(), BankDetailRequest.id.desc())
        .first()
    )


def state(db: Session, employee: Employee) -> dict:
    """What the Documents page shows the employee about their own details."""
    last = latest(db, employee)
    approved = approved_block(employee, full=False)
    if last is not None and last.status == BankDetailStatus.PENDING:
        overall = BankDetailStatus.PENDING
    elif last is not None and last.status == BankDetailStatus.REJECTED:
        overall = BankDetailStatus.REJECTED
    elif approved is not None:
        overall = BankDetailStatus.APPROVED
    else:
        overall = "Not Submitted"
    return {
        "status": overall,
        "mandatory": True,
        "complete": approved is not None,
        "approved": approved,
        "latest_request": request_out(last) if last is not None else None,
        "can_submit": True,  # a new submission supersedes one still pending
    }


def is_complete(employee: Employee) -> bool:
    return bool(employee.bank_name and employee.bank_account_no and employee.pan_number)


# ---------------------------------------------------------------- submit
def submit(db: Session, employee: Employee, actor: User, data: dict, confirmed: bool) -> BankDetailRequest:
    if not confirmed:
        raise HTTPException(
            status_code=422,
            detail="Please confirm that the bank details entered are correct before submitting.",
        )
    values = clean(data)
    if (employee.bank_account_no == values["account_number"] and employee.bank_name == values["bank_name"]
            and (employee.ifsc_code or "") == values["ifsc_code"] and employee.pan_number == values["pan_number"]):
        raise HTTPException(status_code=409, detail="These bank details are already approved.")

    # A newer submission replaces one that is still waiting (it is kept as history).
    for old in db.query(BankDetailRequest).filter(
        BankDetailRequest.employee_id == employee.id,
        BankDetailRequest.status == BankDetailStatus.PENDING,
    ).all():
        old.status = BankDetailStatus.SUPERSEDED

    row = BankDetailRequest(
        employee_id=employee.id, status=BankDetailStatus.PENDING, confirmed_at=utcnow(),
        submitted_by_id=actor.id, **values,
    )
    db.add(row)
    db.flush()
    db.refresh(row)

    audit_service.record(
        db, AuditAction.BANK_DETAILS_SUBMITTED, user=actor, entity_type="bank_detail_request",
        entity_id=row.id,
        meta={"employee_id": employee.id, "account": mask_account(values["account_number"]),
              "replaces_approved": bool(employee.bank_account_no)},
    )
    notification_service.create(
        db, user_id=employee.user_id, title="Bank details submitted",
        message="Your bank details were sent for approval. Your salary slips keep using your "
                "approved details until the new ones are approved."
        if employee.bank_account_no else "Your bank details were sent to HR for approval.",
        type_=NotificationType.BANK_DETAILS_SUBMITTED, related_entity="bank_detail_request",
        related_id=row.id, dedupe_key=f"bank:{row.id}:submitted", actor=actor,
    )
    for reviewer in hierarchy_service.oversight_users(db, employee):
        if reviewer.id == employee.user_id:
            continue
        notification_service.create(
            db, user_id=reviewer.id, title="Bank details awaiting approval",
            message=f"{employee.full_name} ({employee.display_employee_id}) submitted bank details for approval.",
            type_=NotificationType.BANK_DETAILS_SUBMITTED, related_entity="bank_detail_request",
            related_id=row.id, dedupe_key=f"bank:{row.id}:review:{reviewer.id}", actor=actor,
        )
    return row


# ---------------------------------------------------------------- review
def load_for_review(db: Session, request_id: int, actor: User) -> BankDetailRequest:
    row = db.query(BankDetailRequest).filter(BankDetailRequest.id == request_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Bank details request not found.")
    hierarchy_service.assert_level(db, actor, row.employee, hierarchy_service.MANAGE, "bank_detail_request")
    return row


def _assert_pending(row: BankDetailRequest) -> None:
    if row.status != BankDetailStatus.PENDING:
        raise HTTPException(status_code=409, detail=f"This request is already {row.status.lower()}.")


def approve(db: Session, row: BankDetailRequest, actor: User, remarks: Optional[str] = None) -> BankDetailRequest:
    _assert_pending(row)
    employee = row.employee
    had_details = bool(employee.bank_account_no)
    employee.bank_name = row.bank_name
    employee.bank_account_no = row.account_number
    employee.ifsc_code = row.ifsc_code
    employee.pan_number = row.pan_number
    employee.bank_details_approved_at = utcnow()
    row.status = BankDetailStatus.APPROVED
    row.reviewed_at = utcnow()
    row.reviewed_by_id = actor.id
    row.review_remarks = (remarks or "").strip() or None
    db.flush()

    refreshed = refresh_payslips(db, employee, actor, include_credited=not had_details)
    audit_service.record(
        db, AuditAction.BANK_DETAILS_APPROVED, user=actor, entity_type="bank_detail_request",
        entity_id=row.id,
        meta={"employee_id": employee.id, "account": mask_account(row.account_number),
              "payslips_refreshed": refreshed},
    )
    notification_service.create(
        db, user_id=employee.user_id, title="Bank details approved",
        message=f"Your bank details ({row.bank_name}, {mask_account(row.account_number)}) were approved "
                "and will be used on your salary slips.",
        type_=NotificationType.BANK_DETAILS_APPROVED, related_entity="bank_detail_request",
        related_id=row.id, dedupe_key=f"bank:{row.id}:approved", actor=actor,
    )
    return row


def reject(db: Session, row: BankDetailRequest, actor: User, remarks: Optional[str]) -> BankDetailRequest:
    _assert_pending(row)
    remarks = (remarks or "").strip()
    if not remarks:
        raise HTTPException(status_code=422, detail="Please give a reason for rejecting the bank details.")
    row.status = BankDetailStatus.REJECTED
    row.reviewed_at = utcnow()
    row.reviewed_by_id = actor.id
    row.review_remarks = remarks
    db.flush()
    audit_service.record(
        db, AuditAction.BANK_DETAILS_REJECTED, user=actor, entity_type="bank_detail_request",
        entity_id=row.id, meta={"employee_id": row.employee_id, "remarks": remarks},
    )
    notification_service.create(
        db, user_id=row.employee.user_id, title="Bank details rejected",
        message=f"Your bank details were rejected: {remarks} Please correct them on the Documents page and submit again.",
        type_=NotificationType.BANK_DETAILS_REJECTED, related_entity="bank_detail_request",
        related_id=row.id, dedupe_key=f"bank:{row.id}:rejected", actor=actor,
    )
    return row


def refresh_payslips(db: Session, employee: Employee, actor: Optional[User], include_credited: bool) -> int:
    """Re-render generated payslip PDFs so they print the approved bank details.

    Salary slips not yet credited are always refreshed. Credited slips are only
    refreshed when the employee had no approved details before (their bank
    fields were blank); otherwise a credited slip keeps the account the salary
    was actually paid to. Uploaded payslip files are never touched.
    """
    from app.services import payslip_service

    count = 0
    records = db.query(SalaryRecord).filter(SalaryRecord.employee_id == employee.id).all()
    for record in records:
        slip = record.slip
        if slip is None or slip.source != "generated":
            continue
        if record.status == SalaryStatus.CREDITED and not include_credited:
            continue
        payslip_service.generate_and_store(db, record, actor=actor)
        count += 1
    return count
