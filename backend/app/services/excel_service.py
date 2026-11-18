"""Excel import / export, wired into the live database and hierarchy.

The database stays the single source of truth. A workbook is only a way in or
out:

    upload -> parse -> validate every row (columns, ids, emails, departments,
    types, dates, reporting HR / manager, hierarchy) -> preview (stored as an
    ExcelImportBatch: normalised rows + errors + diffs, never the file) ->
    confirm -> valid rows are re-validated against the current database and
    applied through the same services as manual creation / editing.

Exports read the same tables through hierarchy_service, so an HR exports only
their hierarchy, a Manager only their team, an employee only themselves.
"""
import io
import re
import secrets
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.core.constants import (
    INTERNSHIP_DEPARTMENT_NAME, AuditAction, EmploymentStatus, RoleName,
)
from app.models.department import Department
from app.models.employee import Employee
from app.models.excel_import_batch import ExcelImportBatch
from app.models.internship_background import InternshipBackground
from app.models.role import Role
from app.models.user import User
from app.services import audit_service, hierarchy_service as H
from app.utils.timeutil import utcnow

MAX_ROWS = 2000
MAX_FILE_BYTES = 5 * 1024 * 1024
EMPLOYEE_ID_RE = re.compile(r"^RG-\d{4}-\d{4}$")
UNIQUE_ID_RE = re.compile(r"^RGEMP\d{3,}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^\+?[0-9][0-9 \-]{8,18}[0-9]$")
GENDERS = ["Female", "Male", "Other", "Prefer not to say"]
PERSON_TYPES = ["Employee", "Intern", "Manager", "HR"]
TYPE_TO_ROLE = {"Employee": RoleName.EMPLOYEE, "Intern": RoleName.EMPLOYEE,
                "Manager": RoleName.MANAGER, "HR": RoleName.HR_ADMIN}

# (header, key, required for new rows, help text)
COLUMNS: List[Tuple[str, str, bool, str]] = [
    ("Employee ID", "employee_code", False, "Leave blank for new people (generated as RG-YYYY-NNNN). Required to update an existing person."),
    ("Full Name", "full_name", True, "2-160 characters."),
    ("Employee Type", "person_type", True, "Employee, Intern, Manager or HR."),
    ("Department", "department", True, "An existing active department (name or code)."),
    ("Designation", "designation", True, "Job title, 2-120 characters."),
    ("Email", "email", True, "Login email. Must be unique."),
    ("Mobile Number", "phone", False, "10-15 digits, optional + prefix."),
    ("Date of Birth", "date_of_birth", False, "YYYY-MM-DD or DD-MM-YYYY."),
    ("Gender", "gender", False, "Female, Male, Other or Prefer not to say."),
    ("Address", "address", False, ""),
    ("Work Location", "work_location", False, "Office / city printed as Location on salary slips (blank = company default)."),
    ("Joining Date", "joining_date", True, "YYYY-MM-DD or DD-MM-YYYY."),
    ("Reporting HR", "reporting_hr", False, "Employee ID, email or exact name of an HR. Blank for HR rows."),
    ("Reporting Manager", "reporting_manager", False, "Employee ID, email or exact name of a Manager (employees/interns only)."),
    ("Manager Designation", "manager_designation", False, "Optional check: must match the reporting manager's designation."),
    ("Employment Status", "employment_status", False, "Active (default), Inactive, On Leave, Resigned, Terminated."),
    ("Internship Background", "internship_background", False, "Required for interns: an existing internship background."),
    ("Internship Details", "internship_details", False, "Free text: college, programme, duration..."),
    ("Emergency Contact Name", "emergency_contact_name", False, ""),
    ("Emergency Contact Phone", "emergency_contact_phone", False, ""),
    ("Emergency Contact Relation", "emergency_contact_relation", False, ""),
]
HEADER_TO_KEY = {h.lower(): k for h, k, _, _ in COLUMNS}
KEY_TO_HEADER = {k: h for h, k, _, _ in COLUMNS}
REQUIRED_KEYS = [k for _, k, req, _ in COLUMNS if req]
# Fields a bulk update may change (blank cell = leave unchanged).
UPDATABLE = [
    "full_name", "person_type", "department", "designation", "phone", "date_of_birth", "gender",
    "address", "work_location", "joining_date", "employment_status", "internship_background", "internship_details",
    "emergency_contact_name", "emergency_contact_phone", "emergency_contact_relation",
    "reporting_hr", "reporting_manager",
]
HIERARCHY_FIELDS = ("person_type", "reporting_hr", "reporting_manager")

HEAD_FILL = PatternFill("solid", fgColor="1F2A5A")
HEAD_FONT = Font(bold=True, color="FFFFFF")


# ================================================================ helpers
def _cell(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = str(value).strip()
    return text or None


def _parse_date(text: Optional[str]) -> Optional[date]:
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d", "%d.%m.%Y", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(text[:20].strip(), fmt).date()
        except ValueError:
            continue
    raise ValueError(text)


def _style_header(ws, widths: Optional[Dict[int, int]] = None) -> None:
    for cell in ws[1]:
        cell.fill = HEAD_FILL
        cell.font = HEAD_FONT
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    ws.freeze_panes = "A2"
    for idx, col in enumerate(ws.columns, start=1):
        width = (widths or {}).get(idx)
        if width is None:
            longest = max((len(str(c.value)) for c in col if c.value is not None), default=10)
            width = min(max(12, longest + 2), 48)
        ws.column_dimensions[get_column_letter(idx)].width = width


def workbook_bytes(wb: Workbook) -> bytes:
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class Directory:
    """Lookups the validator needs, loaded once per preview/confirm."""

    def __init__(self, db: Session):
        self.db = db
        self.departments = {}
        for d in db.query(Department).all():
            self.departments[d.name.lower()] = d
            self.departments[d.code.lower()] = d
        self.backgrounds = {b.name.lower(): b for b in db.query(InternshipBackground).all()}
        self.people: List[Employee] = (
            db.query(Employee).options(joinedload(Employee.user).joinedload(User.role),
                                       joinedload(Employee.department)).all()
        )
        self.by_code = {e.employee_code.lower(): e for e in self.people}
        self.by_unique = {e.unique_employee_id.lower(): e for e in self.people if e.unique_employee_id}
        self.by_email = {e.user.email.lower(): e for e in self.people if e.user}
        self.user_emails = {u[0].lower() for u in db.query(User.email).all()}
        names: Dict[str, List[Employee]] = {}
        for e in self.people:
            names.setdefault(e.full_name.strip().lower(), []).append(e)
        self.by_name = names

    def find(self, ref: Optional[str]) -> Tuple[Optional[Employee], Optional[str]]:
        """Resolve 'RG-2026-0001', 'RGEMP001', an email, a name, or 'ID | Name'."""
        if not ref:
            return None, None
        key = ref.split("|")[0].strip().lower()
        for table in (self.by_code, self.by_unique, self.by_email):
            if key in table:
                return table[key], None
        matches = self.by_name.get(ref.strip().lower()) or self.by_name.get(key) or []
        if len(matches) == 1:
            return matches[0], None
        if len(matches) > 1:
            return None, f"More than one person is called '{ref}'. Use their Employee ID."
        return None, None


# ================================================================ template
def build_template(db: Session, user: User) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Employees"
    ws.append([h for h, _, _, _ in COLUMNS])
    _style_header(ws, {i + 1: 22 for i in range(len(COLUMNS))})
    for idx, (_, key, required, _) in enumerate(COLUMNS, start=1):
        if required:
            ws.cell(row=1, column=idx).value = f"{KEY_TO_HEADER[key]} *"

    ref = wb.create_sheet("Reference")
    depts = [d for d in db.query(Department).filter(Department.is_active.is_(True)).order_by(Department.name)]
    bgs = [b for b in db.query(InternshipBackground).filter(InternshipBackground.is_active.is_(True)).order_by(InternshipBackground.name)]
    hrs = H.candidates(db, user, RoleName.HR_ADMIN)
    mgrs = H.candidates(db, user, RoleName.MANAGER)
    designations = sorted({e.designation for e in db.query(Employee.designation).distinct()} - {None})
    lists = {
        "Employee Type": PERSON_TYPES if H.is_admin(user) else ["Employee", "Intern", "Manager"],
        "Department": [d.name for d in depts],
        "Gender": GENDERS,
        "Employment Status": list(EmploymentStatus.ALL),
        "Internship Background": [b.name for b in bgs],
        "Reporting HR": [f"{e.employee_code} | {e.full_name}" for e in hrs],
        "Reporting Manager": [f"{e.employee_code} | {e.full_name}" for e in mgrs],
        "Designation (existing)": designations,
    }
    ranges = {}
    for col, (title, values) in enumerate(lists.items(), start=1):
        ref.cell(row=1, column=col, value=title)
        for r, v in enumerate(values, start=2):
            ref.cell(row=r, column=col, value=v)
        letter = get_column_letter(col)
        ranges[title] = f"Reference!${letter}$2:${letter}${max(2, len(values) + 1)}"
    _style_header(ref, {i: 34 for i in range(1, len(lists) + 1)})

    def add_dv(header: str, list_name: str, strict: bool = True):
        col = [h for h, _, _, _ in COLUMNS].index(header) + 1
        letter = get_column_letter(col)
        dv = DataValidation(type="list", formula1=ranges[list_name], allow_blank=True)
        dv.errorStyle = "stop" if strict else "information"
        dv.error = f"Pick a value from the {list_name} list on the Reference sheet."
        dv.showErrorMessage = True
        ws.add_data_validation(dv)
        dv.add(f"{letter}2:{letter}{MAX_ROWS + 1}")

    add_dv("Employee Type", "Employee Type")
    add_dv("Department", "Department")
    add_dv("Gender", "Gender")
    add_dv("Employment Status", "Employment Status")
    add_dv("Internship Background", "Internship Background")
    add_dv("Reporting HR", "Reporting HR", strict=False)
    add_dv("Reporting Manager", "Reporting Manager", strict=False)
    add_dv("Designation", "Designation (existing)", strict=False)

    guide = wb.create_sheet("Instructions")
    guide.append(["Column", "Required for new people", "How to fill it"])
    for header, key, required, help_text in COLUMNS:
        guide.append([header, "Yes" if required else "No", help_text])
    guide.append([])
    guide.append(["Hierarchy", "", "ADMIN -> HR -> MANAGER -> EMPLOYEE / INTERN. HR rows have no Reporting HR/Manager. "
                                    "Manager rows need a Reporting HR. Employee/Intern rows report to a Manager "
                                    "(their HR is taken from the manager) or directly to an HR."])
    guide.append(["Updating", "", "Rows whose Employee ID already exists are shown as updates. Blank cells keep the "
                                   "current value. Hierarchy changes need an extra confirmation in the preview."])
    guide.append(["References", "", "Reporting HR / Manager accept the Employee ID, the email or the exact name. "
                                     "People added earlier in the same file can be referenced too."])
    _style_header(guide, {1: 28, 2: 22, 3: 110})
    return workbook_bytes(wb)


# ================================================================ parsing
def parse_workbook(content: bytes) -> List[dict]:
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="The Excel file is larger than 5 MB.")
    try:
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception:
        raise HTTPException(status_code=422, detail="That file is not a readable .xlsx workbook.")
    ws = wb["Employees"] if "Employees" in wb.sheetnames else wb.worksheets[0]
    rows = ws.iter_rows(values_only=True)
    try:
        header = next(rows)
    except StopIteration:
        raise HTTPException(status_code=422, detail="The workbook is empty.")
    keys = []
    for value in header:
        text = (_cell(value) or "").replace("*", "").strip().lower()
        keys.append(HEADER_TO_KEY.get(text))
    present = {k for k in keys if k}
    missing = [KEY_TO_HEADER[k] for k in REQUIRED_KEYS if k not in present]
    if missing:
        raise HTTPException(
            status_code=422,
            detail="Missing required column(s): " + ", ".join(missing) + ". Download the template to see the expected columns.",
        )
    out = []
    for number, values in enumerate(rows, start=2):
        record = {k: _cell(v) for k, v in zip(keys, values) if k}
        if not any(record.values()):
            continue
        record["_row"] = number
        out.append(record)
        if len(out) > MAX_ROWS:
            raise HTTPException(status_code=422, detail=f"Up to {MAX_ROWS} rows per import.")
    if not out:
        raise HTTPException(status_code=422, detail="No data rows were found under the header row.")
    return out


# ============================================================== validation
def _err(errors, field, value, message, suggestion=""):
    errors.append({"field": KEY_TO_HEADER.get(field, field), "key": field, "value": value,
                   "message": message, "suggestion": suggestion})


def validate_rows(db: Session, actor: User, records: List[dict], mode: str = "auto") -> List[dict]:
    """Validate parsed rows. Returns one result per row with errors/changes."""
    d = Directory(db)
    results: List[dict] = []
    code_count: Dict[str, int] = {}
    email_count: Dict[str, int] = {}
    for r in records:
        if r.get("employee_code"):
            code_count[r["employee_code"].lower()] = code_count.get(r["employee_code"].lower(), 0) + 1
        if r.get("email"):
            email_count[r["email"].lower()] = email_count.get(r["email"].lower(), 0) + 1

    # People introduced by this file, so later rows may reference them.
    file_people: Dict[str, dict] = {}

    me = actor.employee
    for r in records:
        errors: List[dict] = []
        existing = None
        code = r.get("employee_code")
        if code:
            existing = d.by_code.get(code.lower()) or d.by_unique.get(code.lower())
            if existing is None and not EMPLOYEE_ID_RE.match(code):
                _err(errors, "employee_code", code, "Employee ID format is not valid.",
                     "Use RG-YYYY-NNNN (e.g. RG-2026-0042) or leave it blank to generate one.")
            if code_count.get(code.lower(), 0) > 1:
                _err(errors, "employee_code", code, "This Employee ID appears more than once in the file.",
                     "Keep one row per person.")
        action = "update" if existing is not None else "create"
        if mode == "create" and existing is not None:
            _err(errors, "employee_code", code, "This Employee ID already exists; it will not be overwritten.",
                 "Use update mode, or remove the Employee ID to create a new person.")
            action = "create"
        if mode == "update" and existing is None:
            _err(errors, "employee_code", code, "No existing person has this Employee ID.",
                 "Updates need the Employee ID of an existing person.")
            action = "update"

        if action == "create":
            for key in REQUIRED_KEYS:
                if not r.get(key):
                    _err(errors, key, None, f"{KEY_TO_HEADER[key]} is required.", "Fill this cell.")

        # Permission on the target row.
        if existing is not None and not H.can_manage_employee(db, actor, existing):
            _err(errors, "employee_code", code, "This person is outside your hierarchy.",
                 "Only people you manage can be updated.")

        # -- simple fields
        full_name = r.get("full_name")
        if full_name and not (2 <= len(full_name) <= 160):
            _err(errors, "full_name", full_name, "Full Name must be 2-160 characters.")
        if r.get("work_location") and len(str(r.get("work_location")).strip()) > 120:
            _err(errors, "work_location", r.get("work_location"), "Work Location must be at most 120 characters.")
        email = (r.get("email") or "").lower() or None
        if email:
            if not EMAIL_RE.match(email):
                _err(errors, "email", r.get("email"), "Email address is not valid.", "Use name@company.com.")
            if email_count.get(email, 0) > 1:
                _err(errors, "email", r.get("email"), "This email appears more than once in the file.")
            owner = d.by_email.get(email)
            if action == "create" and (email in d.user_emails):
                _err(errors, "email", r.get("email"), "This email is already registered.",
                     "Use another email, or the person's Employee ID to update them.")
            if action == "update" and existing is not None and email != existing.user.email.lower():
                if owner is not None or email in d.user_emails:
                    _err(errors, "email", r.get("email"), "This email belongs to another account.")
                else:
                    _err(errors, "email", r.get("email"), "Email (login) cannot be changed by import.",
                         f"Keep {existing.user.email} or leave the cell blank.")
        ptype = r.get("person_type")
        if ptype:
            match = next((t for t in PERSON_TYPES if t.lower() == ptype.lower()), None)
            if match is None:
                _err(errors, "person_type", ptype, "Employee Type must be Employee, Intern, Manager or HR.")
            ptype = match
        dept = None
        if r.get("department"):
            dept = d.departments.get(r["department"].lower())
            if dept is None or not dept.is_active:
                _err(errors, "department", r["department"], "Department does not exist or is inactive.",
                     "Pick a department from the Reference sheet.")
                dept = None
        designation = r.get("designation")
        if designation and not (2 <= len(designation) <= 120):
            _err(errors, "designation", designation, "Designation must be 2-120 characters.")
        if designation and not re.match(r"^[A-Za-z0-9&()/,.'\- ]+$", designation):
            _err(errors, "designation", designation, "Designation has unsupported characters.",
                 "Use letters, numbers and & ( ) / , . ' -")
        if r.get("phone") and not PHONE_RE.match(r["phone"]):
            _err(errors, "phone", r["phone"], "Mobile Number is not valid.", "Use 10-15 digits, e.g. +91 9876543210.")
        dob = joined = None
        try:
            dob = _parse_date(r.get("date_of_birth"))
            if dob and dob >= date.today():
                _err(errors, "date_of_birth", r.get("date_of_birth"), "Date of Birth must be in the past.")
        except ValueError:
            _err(errors, "date_of_birth", r.get("date_of_birth"), "Date of Birth is not a valid date.", "Use YYYY-MM-DD.")
        try:
            joined = _parse_date(r.get("joining_date"))
            if joined and joined > date.today() + timedelta(days=366):
                _err(errors, "joining_date", r.get("joining_date"), "Joining Date is more than a year away.")
        except ValueError:
            _err(errors, "joining_date", r.get("joining_date"), "Joining Date is not a valid date.", "Use YYYY-MM-DD.")
        if r.get("gender"):
            g = next((x for x in GENDERS if x.lower() == r["gender"].lower()), None)
            if g is None:
                _err(errors, "gender", r["gender"], "Gender must be Female, Male, Other or Prefer not to say.")
            r["gender"] = g or r["gender"]
        status = r.get("employment_status")
        if status:
            st = next((x for x in EmploymentStatus.ALL if x.lower() == status.lower()), None)
            if st is None:
                _err(errors, "employment_status", status, "Unknown Employment Status.",
                     ", ".join(EmploymentStatus.ALL))
            r["employment_status"] = st or status

        # -- type / department / background coherence
        eff_type = ptype or (H.person_type(existing) if existing is not None else None)
        eff_dept = dept or (existing.department if existing is not None else None)
        is_intern_dept = bool(eff_dept and eff_dept.name == INTERNSHIP_DEPARTMENT_NAME)
        if eff_type == "Intern" and eff_dept is not None and not is_intern_dept:
            _err(errors, "department", r.get("department"), "Interns belong to the Internship department.")
        if eff_type in ("Employee", "Manager", "HR") and is_intern_dept:
            _err(errors, "person_type", ptype, f"The Internship department is for interns, not {eff_type}.",
                 "Set Employee Type to Intern or choose another department.")
        background = None
        if r.get("internship_background"):
            background = d.backgrounds.get(r["internship_background"].lower())
            if background is None or not background.is_active:
                _err(errors, "internship_background", r["internship_background"], "Unknown internship background.",
                     "Pick one from the Reference sheet.")
        if eff_type == "Intern" and background is None and not (existing is not None and existing.internship_background_id):
            if not any(e["key"] == "internship_background" for e in errors):
                _err(errors, "internship_background", None, "Interns need an internship background.")

        # -- permissions on the type
        if eff_type == "HR" and not H.is_admin(actor) and (ptype == "HR"):
            _err(errors, "person_type", ptype, "Only the Admin can create or assign HR accounts.")

        # -- hierarchy references (DB or earlier rows in this file)
        role = TYPE_TO_ROLE.get(eff_type) if eff_type else None
        hr_ref, mgr_ref = r.get("reporting_hr"), r.get("reporting_manager")
        hr_obj = mgr_obj = None
        hr_file = mgr_file = None
        if hr_ref:
            hr_obj, amb = d.find(hr_ref)
            if hr_obj is None:
                hr_file = file_people.get(hr_ref.split("|")[0].strip().lower())
                if hr_file is None:
                    _err(errors, "reporting_hr", hr_ref, amb or "Reporting HR not found.",
                         "Use the Employee ID or email of an existing HR (see the Reference sheet).")
                elif hr_file["type"] != "HR":
                    _err(errors, "reporting_hr", hr_ref, f"{hr_file['name']} is not an HR in this file.")
                    hr_file = None
            elif H.employee_role(hr_obj) != RoleName.HR_ADMIN:
                _err(errors, "reporting_hr", hr_ref, f"{hr_obj.full_name} does not have the HR role.")
                hr_obj = None
            elif not hr_obj.user.is_active:
                _err(errors, "reporting_hr", hr_ref, f"{hr_obj.full_name}'s account is inactive.")
        if mgr_ref:
            mgr_obj, amb = d.find(mgr_ref)
            if mgr_obj is None:
                mgr_file = file_people.get(mgr_ref.split("|")[0].strip().lower())
                if mgr_file is None:
                    _err(errors, "reporting_manager", mgr_ref, amb or "Reporting Manager not found.",
                         "Use the Employee ID or email of an existing Manager (see the Reference sheet).")
                elif mgr_file["type"] != "Manager":
                    _err(errors, "reporting_manager", mgr_ref, f"{mgr_file['name']} is not a Manager in this file.")
                    mgr_file = None
            elif H.employee_role(mgr_obj) != RoleName.MANAGER:
                _err(errors, "reporting_manager", mgr_ref, f"{mgr_obj.full_name} does not have the Manager role.")
                mgr_obj = None
            elif not mgr_obj.user.is_active:
                _err(errors, "reporting_manager", mgr_ref, f"{mgr_obj.full_name}'s account is inactive.")

        if existing is not None and ((hr_obj is not None and hr_obj.id == existing.id)
                                     or (mgr_obj is not None and mgr_obj.id == existing.id)):
            _err(errors, "reporting_manager", mgr_ref or hr_ref, "A person cannot report to themselves.")

        if role == RoleName.HR_ADMIN and (hr_ref or mgr_ref):
            _err(errors, "reporting_hr", hr_ref or mgr_ref, "HR reports to the Admin only.",
                 "Leave Reporting HR and Reporting Manager blank for HR rows.")
        if role == RoleName.MANAGER and mgr_ref:
            _err(errors, "reporting_manager", mgr_ref, "A Manager reports to an HR, not to another manager.",
                 "Put the HR in Reporting HR and leave Reporting Manager blank.")
        if role == RoleName.MANAGER and not hr_ref and action == "create" and H.is_admin(actor):
            _err(errors, "reporting_hr", None, "Every Manager needs a Reporting HR.", "Fill Reporting HR.")
        # Manager <-> HR consistency
        mgr_hr_id = mgr_obj.reporting_hr_id if mgr_obj is not None else None
        mgr_hr_key = mgr_file["hr_key"] if mgr_file is not None else None
        if (mgr_obj is not None or mgr_file is not None) and (hr_obj is not None or hr_file is not None):
            consistent = True
            if mgr_obj is not None and hr_obj is not None:
                consistent = mgr_hr_id == hr_obj.id
            elif mgr_file is not None and hr_obj is not None:
                consistent = mgr_hr_key in (hr_obj.employee_code.lower(), (hr_obj.user.email or "").lower())
            elif mgr_obj is not None and hr_file is not None:
                consistent = False
            elif mgr_file is not None and hr_file is not None:
                consistent = mgr_hr_key == hr_file["key"] or mgr_hr_key == hr_file.get("email")
            if not consistent:
                mname = mgr_obj.full_name if mgr_obj is not None else mgr_file["name"]
                hname = hr_obj.full_name if hr_obj is not None else hr_file["name"]
                _err(errors, "reporting_hr", hr_ref,
                     f"Hierarchy error: Manager {mname} is not assigned to HR {hname}.",
                     "Use the manager's own HR, or move the manager first.")
        if r.get("manager_designation") and mgr_obj is not None:
            if r["manager_designation"].strip().lower() != (mgr_obj.designation or "").strip().lower():
                _err(errors, "manager_designation", r["manager_designation"],
                     f"{mgr_obj.full_name}'s designation is '{mgr_obj.designation}'.",
                     "Correct the Manager Designation or leave it blank.")

        # HR importer: everything lands under themselves.
        if H.is_hr(actor) and me is not None:
            if hr_obj is not None and hr_obj.id != me.id:
                _err(errors, "reporting_hr", hr_ref, "You can only place people under yourself.",
                     f"Use your own Employee ID ({me.employee_code}) or leave it blank.")
            if mgr_obj is not None and not H.can_manage_employee(db, actor, mgr_obj):
                _err(errors, "reporting_manager", mgr_ref, "That manager is outside your hierarchy.")

        # Role change sanity for existing people.
        if existing is not None and role and role != H.employee_role(existing):
            old = H.employee_role(existing)
            if old == RoleName.MANAGER and any(p.reporting_manager_id == existing.id for p in d.people):
                _err(errors, "person_type", ptype, f"{existing.full_name} still has team members.",
                     "Reassign the team before changing the type.")
            if old == RoleName.HR_ADMIN and any(p.reporting_hr_id == existing.id for p in d.people):
                _err(errors, "person_type", ptype, f"{existing.full_name} still has managers/employees assigned.",
                     "Reassign them first.")

        # -- diff for updates
        changes = []
        if existing is not None and action == "update":
            current = _current_values(existing)
            for key in UPDATABLE:
                new = r.get(key)
                if new in (None, ""):
                    continue
                if key == "person_type":
                    new = ptype or new
                if key == "department" and dept is not None:
                    new = dept.name
                if key in ("date_of_birth", "joining_date"):
                    new = (dob if key == "date_of_birth" else joined)
                    new = new.isoformat() if new else None
                if key == "internship_background" and background is not None:
                    new = background.name
                if key == "reporting_hr" and hr_obj is not None:
                    new = hr_obj.full_name
                if key == "reporting_manager" and mgr_obj is not None:
                    new = mgr_obj.full_name
                old = current.get(key)
                if str(old or "").strip().lower() != str(new or "").strip().lower():
                    changes.append({"field": KEY_TO_HEADER[key], "key": key, "old": old, "new": new,
                                    "hierarchy": key in HIERARCHY_FIELDS})

        norm = {
            "row": r["_row"], "action": action, "existing_id": existing.id if existing is not None else None,
            "employee_code": code, "full_name": full_name, "email": email, "person_type": eff_type,
            "role": role, "department_id": dept.id if dept is not None else None,
            "designation": designation, "phone": r.get("phone"),
            "date_of_birth": dob.isoformat() if dob else None,
            "joining_date": joined.isoformat() if joined else None, "gender": r.get("gender"),
            "address": r.get("address"), "work_location": (r.get("work_location") or "").strip() or None,
            "employment_status": r.get("employment_status"),
            "internship_background_id": background.id if background is not None else None,
            "internship_details": r.get("internship_details"),
            "emergency_contact_name": r.get("emergency_contact_name"),
            "emergency_contact_phone": r.get("emergency_contact_phone"),
            "emergency_contact_relation": r.get("emergency_contact_relation"),
            "reporting_hr_id": hr_obj.id if hr_obj is not None else None,
            "reporting_manager_id": mgr_obj.id if mgr_obj is not None else None,
            "reporting_hr_ref": hr_ref if hr_file is not None else None,
            "reporting_manager_ref": mgr_ref if mgr_file is not None else None,
            "has_reporting_hr": bool(hr_ref), "has_reporting_manager": bool(mgr_ref),
        }
        status_label = "Invalid" if errors else ("No change" if action == "update" and not changes else "Valid")
        results.append({
            "row": r["_row"], "action": action, "status": status_label,
            "employee_code": code or (existing.employee_code if existing is not None else None),
            "full_name": full_name or (existing.full_name if existing is not None else None),
            "email": r.get("email"), "person_type": eff_type,
            "department": dept.name if dept is not None else r.get("department"),
            "reporting_hr": r.get("reporting_hr"), "reporting_manager": r.get("reporting_manager"),
            "errors": errors, "changes": changes,
            "hierarchy_change": any(c["hierarchy"] for c in changes),
            "normalised": norm,
        })
        if not errors and action == "create":
            entry = {"type": eff_type, "name": full_name,
                     "key": (code or email or "").lower(), "email": email,
                     "hr_key": (hr_ref.split("|")[0].strip().lower() if hr_ref else None)}
            if hr_obj is not None:
                entry["hr_key"] = hr_obj.employee_code.lower()
            for k in {code.lower() if code else None, email, (full_name or "").lower()} - {None, ""}:
                file_people[k] = entry
    return results


def _current_values(e: Employee) -> dict:
    hr = H.get_reporting_hr(e)
    return {
        "full_name": e.full_name, "person_type": H.person_type(e),
        "department": e.department.name if e.department else None, "designation": e.designation,
        "phone": e.phone, "date_of_birth": e.date_of_birth.isoformat() if e.date_of_birth else None,
        "gender": e.gender, "address": e.address, "work_location": e.work_location,
        "joining_date": e.joining_date.isoformat() if e.joining_date else None,
        "employment_status": e.employment_status,
        "internship_background": e.internship_background.name if e.internship_background else None,
        "internship_details": e.internship_details,
        "emergency_contact_name": e.emergency_contact_name,
        "emergency_contact_phone": e.emergency_contact_phone,
        "emergency_contact_relation": e.emergency_contact_relation,
        "reporting_hr": hr.full_name if hr is not None and hr.id != e.id else None,
        "reporting_manager": e.reporting_manager.full_name if e.reporting_manager else None,
    }


def summarise(results: List[dict]) -> dict:
    def has(r, key):
        return any(e["key"] == key for e in r["errors"])
    invalid = [r for r in results if r["errors"]]
    return {
        "total_rows": len(results),
        "valid_rows": len(results) - len(invalid),
        "invalid_rows": len(invalid),
        "create_rows": sum(1 for r in results if not r["errors"] and r["action"] == "create"),
        "update_rows": sum(1 for r in results if not r["errors"] and r["action"] == "update" and r["changes"]),
        "unchanged_rows": sum(1 for r in results if not r["errors"] and r["action"] == "update" and not r["changes"]),
        "duplicate_rows": sum(1 for r in results if any("more than once" in e["message"] or "already" in e["message"] for e in r["errors"])),
        "missing_fields": sum(1 for r in results for e in r["errors"] if e["message"].endswith("is required.")),
        "invalid_departments": sum(1 for r in results if has(r, "department")),
        "invalid_designations": sum(1 for r in results if has(r, "designation")),
        "invalid_reporting_managers": sum(1 for r in results if has(r, "reporting_manager") or has(r, "manager_designation")),
        "invalid_reporting_hrs": sum(1 for r in results if has(r, "reporting_hr") and not any("Hierarchy error" in e["message"] for e in r["errors"])),
        "hierarchy_errors": sum(1 for r in results if any(
            "Hierarchy error" in e["message"] or "reports to" in e["message"]
            or "report to themselves" in e["message"] or "outside your hierarchy" in e["message"]
            or "under yourself" in e["message"] or "still has" in e["message"]
            for e in r["errors"])),
        "hierarchy_changes": sum(1 for r in results if not r["errors"] and r["hierarchy_change"]),
    }


# ============================================================ preview/confirm
def preview(db: Session, actor: User, file_name: str, content: bytes, mode: str = "auto") -> ExcelImportBatch:
    if mode not in ("auto", "create", "update"):
        raise HTTPException(status_code=422, detail="mode must be auto, create or update.")
    records = parse_workbook(content)
    results = validate_rows(db, actor, records, mode)
    counts = summarise(results)
    batch = ExcelImportBatch(
        token=secrets.token_urlsafe(24), created_by_id=actor.id, file_name=(file_name or "import.xlsx")[:255],
        mode=mode, status="Previewed", total_rows=counts["total_rows"], valid_rows=counts["valid_rows"],
        invalid_rows=counts["invalid_rows"], payload={"records": records, "results": results, "counts": counts},
    )
    db.add(batch)
    db.flush()
    audit_service.record(
        db, AuditAction.EXCEL_IMPORT_PREVIEWED, user=actor, entity_type="excel_import_batch",
        entity_id=batch.id,
        meta={"file_name": batch.file_name, "mode": mode, **{k: counts[k] for k in (
            "total_rows", "valid_rows", "invalid_rows", "create_rows", "update_rows")}},
    )
    return batch


def load_batch(db: Session, actor: User, token: str) -> ExcelImportBatch:
    batch = db.query(ExcelImportBatch).filter(ExcelImportBatch.token == token).first()
    if batch is None or (batch.created_by_id != actor.id and not H.is_admin(actor)):
        raise HTTPException(status_code=404, detail="Import preview not found.")
    return batch


def public_preview(batch: ExcelImportBatch) -> dict:
    payload = batch.payload or {}
    results = payload.get("results", [])
    return {
        "token": batch.token, "file_name": batch.file_name, "mode": batch.mode, "status": batch.status,
        "created_at": batch.created_at, "confirmed_at": batch.confirmed_at,
        "counts": payload.get("counts") or {
            "total_rows": batch.total_rows, "valid_rows": batch.valid_rows, "invalid_rows": batch.invalid_rows},
        "result_counts": {"created": batch.created_count, "updated": batch.updated_count, "failed": batch.failed_count},
        "rows": [{k: v for k, v in r.items() if k != "normalised"} for r in results],
    }


def error_report(batch: ExcelImportBatch) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Import errors"
    ws.append(["Row Number", "Employee ID", "Employee Name", "Field", "Invalid Value", "Error Message", "Suggested Correction"])
    for r in (batch.payload or {}).get("results", []):
        for e in r["errors"]:
            ws.append([r["row"], r.get("employee_code") or "", r.get("full_name") or "", e["field"],
                       "" if e["value"] is None else str(e["value"]), e["message"], e.get("suggestion") or ""])
    for e in (batch.payload or {}).get("apply_errors", []):
        ws.append([e["row"], e.get("employee_code") or "", e.get("full_name") or "", e.get("field") or "",
                   "", e["message"], "Fix the row and import it again."])
    _style_header(ws, {1: 12, 2: 16, 3: 26, 4: 22, 5: 28, 6: 60, 7: 60})
    return workbook_bytes(wb)


def confirm(db: Session, actor: User, batch: ExcelImportBatch, confirm_hierarchy_changes: bool,
            send_account_emails: bool = False) -> dict:
    from app.services import employee_service

    if batch.status != "Previewed":
        raise HTTPException(status_code=409, detail="This import has already been processed.")
    payload = batch.payload or {}
    # Re-validate against the database as it is now (someone may have changed it).
    results = validate_rows(db, actor, payload.get("records", []), batch.mode)
    if any(not r["errors"] and r["hierarchy_change"] for r in results) and not confirm_hierarchy_changes:
        raise HTTPException(
            status_code=428,
            detail="This import changes reporting lines (Reporting HR / Manager / Type). Review them and confirm hierarchy changes.",
        )

    order = {"HR": 0, "Manager": 1, "Employee": 2, "Intern": 2, None: 3}
    todo = sorted([r for r in results if not r["errors"]], key=lambda r: (order.get(r["person_type"], 3), r["row"]))
    created, updated, apply_errors, credentials = [], [], [], []
    ref_map: Dict[str, int] = {}

    for r in todo:
        n = r["normalised"]
        try:
            with db.begin_nested():
                hr_id = n["reporting_hr_id"]
                mgr_id = n["reporting_manager_id"]
                if hr_id is None and n.get("reporting_hr_ref"):
                    hr_id = ref_map.get(n["reporting_hr_ref"].split("|")[0].strip().lower())
                if mgr_id is None and n.get("reporting_manager_ref"):
                    mgr_id = ref_map.get(n["reporting_manager_ref"].split("|")[0].strip().lower())
                if n["action"] == "create":
                    if H.is_hr(actor) and n["role"] != RoleName.HR_ADMIN and hr_id is None and mgr_id is None:
                        hr_id = actor.employee.id
                    data = {
                        "full_name": n["full_name"], "email": n["email"], "department_id": n["department_id"],
                        "internship_background_id": n["internship_background_id"], "designation": n["designation"],
                        "joining_date": date.fromisoformat(n["joining_date"]),
                        "date_of_birth": date.fromisoformat(n["date_of_birth"]) if n["date_of_birth"] else None,
                        "phone": n["phone"], "gender": n["gender"], "address": n["address"],
                        "work_location": n.get("work_location"),
                        "employment_status": n["employment_status"] or EmploymentStatus.ACTIVE,
                        "internship_details": n["internship_details"],
                        "emergency_contact_name": n["emergency_contact_name"],
                        "emergency_contact_phone": n["emergency_contact_phone"],
                        "emergency_contact_relation": n["emergency_contact_relation"],
                        "employee_code": n["employee_code"], "role": n["role"],
                        "employee_type": "Intern" if n["person_type"] == "Intern" else "Employee",
                        "reporting_hr_id": hr_id, "reporting_manager_id": mgr_id,
                    }
                    employee, raw = employee_service.create_employee(
                        db, data, actor=actor, send_email=send_account_emails)
                    created.append(employee.id)
                    credentials.append({"row": r["row"], "employee_code": employee.employee_code,
                                        "full_name": employee.full_name, "email": employee.user.email,
                                        "initial_password": raw})
                    for key in {employee.employee_code.lower(), employee.user.email.lower(),
                                employee.full_name.lower(), (n["employee_code"] or "").lower()} - {""}:
                        ref_map[key] = employee.id
                elif r["changes"]:
                    employee = db.query(Employee).filter(Employee.id == n["existing_id"]).first()
                    keys = {c["key"] for c in r["changes"]}
                    simple = {
                        "full_name": "full_name", "designation": "designation", "phone": "phone",
                        "gender": "gender", "address": "address", "work_location": "work_location",
                        "employment_status": "employment_status",
                        "internship_details": "internship_details",
                        "emergency_contact_name": "emergency_contact_name",
                        "emergency_contact_phone": "emergency_contact_phone",
                        "emergency_contact_relation": "emergency_contact_relation",
                    }
                    for key, attr in simple.items():
                        if key in keys:
                            setattr(employee, attr, n[key])
                    if "date_of_birth" in keys:
                        employee.date_of_birth = date.fromisoformat(n["date_of_birth"])
                    if "joining_date" in keys:
                        employee.joining_date = date.fromisoformat(n["joining_date"])
                    if "department" in keys or "internship_background" in keys:
                        dept_id = n["department_id"] or employee.department_id
                        bg_id = n["internship_background_id"] or employee.internship_background_id
                        dept, bg = employee_service.validate_department_background(db, dept_id, bg_id)
                        employee.department_id = dept.id
                        employee.internship_background_id = bg.id if bg else None
                    db.flush()
                    if keys & set(HIERARCHY_FIELDS):
                        H.apply_assignment(
                            db, actor, employee,
                            role=n["role"] if "person_type" in keys else H.UNSET,
                            reporting_hr_id=hr_id if "reporting_hr" in keys else H.UNSET,
                            reporting_manager_id=mgr_id if "reporting_manager" in keys else H.UNSET,
                        )
                    audit_service.record(
                        db, AuditAction.EMPLOYEE_UPDATED, user=actor, entity_type="employee",
                        entity_id=employee.id, meta={"fields": sorted(keys), "via": "excel_import"},
                    )
                    updated.append(employee.id)
                    if "work_location" in keys:
                        from app.services import bank_details_service
                        bank_details_service.refresh_payslips(db, employee, actor, include_credited=False)
        except HTTPException as exc:
            apply_errors.append({"row": r["row"], "employee_code": r.get("employee_code"),
                                 "full_name": r.get("full_name"), "message": str(exc.detail)})
        except Exception as exc:  # pragma: no cover - reported, never swallowed silently
            apply_errors.append({"row": r["row"], "employee_code": r.get("employee_code"),
                                 "full_name": r.get("full_name"), "message": f"Could not be saved: {exc}"})

    invalid = [r for r in results if r["errors"]]
    batch.status = "Confirmed"
    batch.confirmed_at = utcnow()
    batch.created_count = len(created)
    batch.updated_count = len(updated)
    batch.failed_count = len(invalid) + len(apply_errors)
    batch.valid_rows = len(results) - len(invalid)
    batch.invalid_rows = len(invalid)
    # Keep what the error report needs; drop the raw rows (personal data).
    batch.payload = {
        "results": [{k: v for k, v in r.items() if k != "normalised"} for r in results],
        "counts": summarise(results), "apply_errors": apply_errors,
    }
    db.flush()
    audit_service.record(
        db, AuditAction.EXCEL_IMPORT_CONFIRMED, user=actor, entity_type="excel_import_batch",
        entity_id=batch.id,
        meta={"file_name": batch.file_name, "rows": len(results), "successful": len(created) + len(updated),
              "failed": batch.failed_count, "created": len(created), "updated": len(updated)},
    )
    return {
        "created": len(created), "updated": len(updated), "failed": batch.failed_count,
        "unchanged": sum(1 for r in results if not r["errors"] and r["action"] == "update" and not r["changes"]),
        "apply_errors": apply_errors, "credentials": credentials, "token": batch.token,
    }


# ================================================================== export
EXPORT_TYPES = {
    "employees": "People (HR, managers, employees, interns)",
    "hierarchy": "HR-wise / manager-wise teams",
    "attendance": "Attendance (check-in / check-out)",
    "leave": "Leave requests",
    "reports": "Work reports (Noon / EOD)",
    "hourly": "Hourly updates",
    "tasks": "Tasks",
    "documents": "Documents and status",
    "salary": "Salary records",
    "monthly": "Monthly reports",
}
SENSITIVE_EXPORTS = {"salary"}


def _people_query(db: Session, user: User, f: dict):
    q = db.query(Employee).options(joinedload(Employee.department), joinedload(Employee.user).joinedload(User.role),
                                   joinedload(Employee.internship_background))
    if f.get("self_only"):
        return q.filter(Employee.user_id == user.id)
    q = H.restrict(q, db, user, Employee.id)
    if f.get("department_id"):
        q = q.filter(Employee.department_id == f["department_id"])
    if f.get("reporting_hr_id"):
        q = q.filter((Employee.reporting_hr_id == f["reporting_hr_id"]) | (Employee.id == f["reporting_hr_id"]))
    if f.get("reporting_manager_id"):
        q = q.filter((Employee.reporting_manager_id == f["reporting_manager_id"]) | (Employee.id == f["reporting_manager_id"]))
    if f.get("employment_status"):
        q = q.filter(Employee.employment_status == f["employment_status"])
    return q


def _people(db: Session, user: User, f: dict) -> List[Employee]:
    rows = _people_query(db, user, f).order_by(Employee.full_name).all()
    if f.get("person_type"):
        rows = [e for e in rows if H.person_type(e) == f["person_type"]]
    return rows


def _dates(f: dict) -> Tuple[Optional[date], Optional[date]]:
    d_from, d_to = f.get("date_from"), f.get("date_to")
    if f.get("month"):
        y, m = (int(x) for x in f["month"].split("-"))
        d_from = date(y, m, 1)
        d_to = (date(y + (m == 12), (m % 12) + 1, 1) - timedelta(days=1))
    return d_from, d_to


def build_export(db: Session, user: User, export_type: str, f: dict) -> Tuple[bytes, int, str]:
    """Return (xlsx bytes, number of records, file name)."""
    from app.api.serializers import employee_list_item
    from app.models.daily_report import DailyReport
    from app.models.employee_document import EmployeeDocument
    from app.models.hourly_update import HourlyUpdate
    from app.models.leave_request import LeaveRequest
    from app.models.salary import SalaryRecord
    from app.models.work_session import WorkSession
    from app.models.work_task import WorkTask
    from app.services import attendance_service, leave_service, monthly_report_service, task_service
    from app.utils.clock import to_local

    if export_type not in EXPORT_TYPES:
        raise HTTPException(status_code=422, detail="Unknown export type.")
    if not H.is_supervisor(user):
        f = dict(f, self_only=True)
        if export_type in ("employees", "hierarchy", "documents"):
            raise HTTPException(status_code=403, detail="This export is for HR, Managers and the Admin.")
    if export_type in SENSITIVE_EXPORTS and H.is_manager(user) and not f.get("self_only"):
        raise HTTPException(status_code=403, detail="Managers can't export salary information.")

    people = _people(db, user, f)
    ids = [e.id for e in people]
    id_set = set(ids)
    by_id = {e.id: e for e in people}
    d_from, d_to = _dates(f)
    wb = Workbook()
    ws = wb.active
    ws.title = re.sub(r"[\\/*?:\[\]]", "-", EXPORT_TYPES[export_type])[:31]
    rows: List[list] = []

    def who(e: Employee) -> list:
        hr = H.get_reporting_hr(e)
        return [e.display_employee_id, e.full_name, H.person_type(e),
                e.department.name if e.department else "",
                e.reporting_manager.full_name if e.reporting_manager else "",
                hr.full_name if hr is not None and hr.id != e.id else ""]

    WHO = ["Employee ID", "Name", "Type", "Department", "Reporting Manager", "Reporting HR"]

    if export_type == "employees":
        header = ["Employee ID", "Unique ID", "Full Name", "Employee Type", "Department", "Designation", "Email",
                  "Mobile Number", "Date of Birth", "Gender", "Address", "Work Location", "Joining Date", "Reporting HR",
                  "Reporting Manager", "Manager Designation", "Employment Status", "Account Active",
                  "Internship Background", "Internship Details", "Documents %"]
        for e in people:
            item = employee_list_item(db, e)
            hr = H.get_reporting_hr(e)
            rows.append([e.employee_code, e.unique_employee_id or "", e.full_name, H.person_type(e),
                         e.department.name if e.department else "", e.designation, e.user.email if e.user else "",
                         e.phone or "", e.date_of_birth, e.gender or "", e.address or "", e.work_location or "", e.joining_date,
                         hr.full_name if hr is not None and hr.id != e.id else "",
                         e.reporting_manager.full_name if e.reporting_manager else "",
                         e.reporting_manager.designation if e.reporting_manager else "",
                         e.employment_status, "Yes" if e.user and e.user.is_active else "No",
                         e.internship_background.name if e.internship_background else "",
                         e.internship_details or "", item.get("document_completion")])
    elif export_type == "hierarchy":
        header = ["HR", "HR Employee ID", "Manager", "Manager Employee ID", "Member", "Member Employee ID",
                  "Member Type", "Department", "Designation", "Status"]
        for hr_node in H.hierarchy_tree(db, user):
            if f.get("reporting_hr_id") and hr_node["id"] != f["reporting_hr_id"]:
                continue
            for m in hr_node.get("managers", []):
                if f.get("reporting_manager_id") and m["id"] != f["reporting_manager_id"]:
                    continue
                if not m.get("team"):
                    rows.append([hr_node["full_name"], hr_node.get("employee_code") or "", m["full_name"],
                                 m["employee_code"], "", "", "", m["department"], m["designation"], ""])
                for t in m.get("team", []):
                    if f.get("department_id") and t["department_id"] != f["department_id"]:
                        continue
                    rows.append([hr_node["full_name"], hr_node.get("employee_code") or "", m["full_name"],
                                 m["employee_code"], t["full_name"], t["employee_code"], t["type"],
                                 t["department"], t["designation"], "Active" if t["is_active"] else "Inactive"])
            if not f.get("reporting_manager_id"):
                for t in hr_node.get("direct", []):
                    rows.append([hr_node["full_name"], hr_node.get("employee_code") or "", "(reports to HR)", "",
                                 t["full_name"], t["employee_code"], t["type"], t["department"], t["designation"],
                                 "Active" if t["is_active"] else "Inactive"])
    elif export_type == "attendance":
        header = WHO + ["Date", "Check-in", "Check-out", "Work Period", "Late (min)", "Late Reason",
                        "Worked (min)", "Extra (min)", "Status", "Check-in Location", "Check-out Location"]
        q = db.query(WorkSession, Employee).join(Employee, Employee.user_id == WorkSession.user_id)
        q = q.filter(Employee.id.in_(ids or [0]))
        if d_from:
            q = q.filter(WorkSession.work_date >= d_from)
        if d_to:
            q = q.filter(WorkSession.work_date <= d_to)
        for s, e in q.order_by(WorkSession.work_date.desc(), Employee.full_name).all():
            out = attendance_service.session_out(s)
            rows.append(who(e) + [s.work_date, out["check_in_time"] or "", out["check_out_time"] or "",
                                  s.work_period or "", s.late_login_minutes or 0, s.late_login_reason or "",
                                  out["worked_minutes"], s.extra_work_minutes or 0, s.attendance_status or "",
                                  (out["check_in_location"] or {}).get("label", ""),
                                  (out["check_out_location"] or {}).get("label", "")])
    elif export_type == "leave":
        header = WHO + ["Leave Type", "From", "To", "Period", "Days", "Paid", "Status", "Stage",
                        "Manager Decision", "Manager Remarks", "Final Remarks", "Requested", "Reason"]
        q = db.query(LeaveRequest).filter(LeaveRequest.employee_id.in_(ids or [0]))
        if f.get("status"):
            q = q.filter(LeaveRequest.status == f["status"])
        if f.get("leave_type"):
            q = q.filter(LeaveRequest.leave_type == f["leave_type"])
        if d_from:
            q = q.filter(LeaveRequest.to_date >= d_from)
        if d_to:
            q = q.filter(LeaveRequest.from_date <= d_to)
        for l in q.order_by(LeaveRequest.from_date.desc()).all():
            o = leave_service.output(l)
            rows.append(who(by_id[l.employee_id]) + [o["leave_type_label"], l.from_date, l.to_date, l.leave_period,
                        o["duration_days"], "Yes" if o["is_paid"] else "No", l.status, l.approval_stage,
                        l.manager_status or "", l.manager_remarks or "", l.hr_remarks or "",
                        l.requested_at, l.reason])
    elif export_type == "reports":
        header = WHO + ["Date", "Report Type", "Status", "Work Summary", "Tasks Completed", "In Progress",
                        "Pending", "Challenges", "Attachments", "Submitted", "Reviewed", "Review Notes"]
        q = db.query(DailyReport).options(joinedload(DailyReport.attachments)).filter(DailyReport.employee_id.in_(ids or [0]))
        rtype = (f.get("report_type") or "").lower()
        if rtype in ("noon", "eod"):
            q = q.filter(DailyReport.report_type == ("Noon" if rtype == "noon" else "EOD"))
        if f.get("status"):
            q = q.filter(DailyReport.status == f["status"])
        if d_from:
            q = q.filter(DailyReport.report_date >= d_from)
        if d_to:
            q = q.filter(DailyReport.report_date <= d_to)
        for rep in q.order_by(DailyReport.report_date.desc()).all():
            rows.append(who(by_id[rep.employee_id]) + [
                rep.report_date, rep.report_type, rep.status, rep.work_summary or "",
                rep.tasks_completed or "", rep.tasks_in_progress or "", rep.tasks_pending or "",
                rep.challenges or "", len(rep.attachments), rep.submitted_at, rep.reviewed_at,
                rep.review_notes or ""])
    elif export_type == "hourly":
        header = WHO + ["Date", "Hour", "Task", "Work Completed", "Units", "Progress %", "Task Status",
                        "Remaining Work", "Notes", "Submitted"]
        q = db.query(HourlyUpdate).filter(HourlyUpdate.employee_id.in_(ids or [0]))
        if d_from:
            q = q.filter(HourlyUpdate.update_date >= d_from)
        if d_to:
            q = q.filter(HourlyUpdate.update_date <= d_to)
        for u in q.order_by(HourlyUpdate.update_date.desc(), HourlyUpdate.slot_index).all():
            h1, h2 = 10 + u.slot_index, 11 + u.slot_index
            rows.append(who(by_id[u.employee_id]) + [
                u.update_date, attendance_service.slot_label(h1, h2), u.task.title if u.task else "",
                u.work_completed, u.units_completed, u.progress_percent, u.task_status,
                u.remaining_work or "", u.notes or "", u.submitted_at])
    elif export_type == "tasks":
        header = WHO + ["Task", "Description", "Task Date", "Due Date", "Target", "Unit", "Completed",
                        "Progress %", "Status", "Assigned By", "Parent Task", "Completed At"]
        q = task_service.query(db).filter(WorkTask.employee_id.in_(ids or [0]))
        if f.get("status"):
            q = q.filter(WorkTask.status == f["status"])
        if d_from:
            q = q.filter(WorkTask.task_date >= d_from)
        if d_to:
            q = q.filter(WorkTask.task_date <= d_to)
        for t in q.order_by(WorkTask.task_date.desc()).all():
            o = task_service.output(t)
            rows.append(who(by_id[t.employee_id]) + [t.title, t.description or "", t.task_date, t.due_date,
                        t.target, t.unit or "", t.completed, o["progress_percent"], t.status,
                        o["assigned_by"] or "", o["parent_task_title"] or "", t.completed_at])
    elif export_type == "documents":
        header = WHO + ["Document", "Mandatory", "Status", "Versions", "Last Upload", "Reviewed", "HR Remarks"]
        q = db.query(EmployeeDocument).options(joinedload(EmployeeDocument.document_type),
                                               joinedload(EmployeeDocument.versions)).filter(
            EmployeeDocument.employee_id.in_(ids or [0]))
        if f.get("status"):
            q = q.filter(EmployeeDocument.status == f["status"])
        for doc in q.all():
            cur = doc.current_version
            rows.append(who(by_id[doc.employee_id]) + [
                doc.document_type.name, "Yes" if doc.document_type.is_required else "No", doc.status,
                doc.version_count, cur.created_at if cur else None, doc.reviewed_at, doc.hr_remarks or ""])
    elif export_type == "salary":
        header = WHO + ["Period", "Working Days", "LOP Days", "Total Earnings", "Total Deductions", "Net Pay",
                        "Status", "Credit Date", "Payslip"]
        allowed = [e.id for e in people if H.can_view_sensitive(db, user, e)]
        q = db.query(SalaryRecord).filter(SalaryRecord.employee_id.in_(allowed or [0]))
        if f.get("status"):
            q = q.filter(SalaryRecord.status == f["status"])
        if f.get("month"):
            y, m = (int(x) for x in f["month"].split("-"))
            q = q.filter(SalaryRecord.period_year == y, SalaryRecord.period_month == m)
        for s in q.order_by(SalaryRecord.period_year.desc(), SalaryRecord.period_month.desc()).all():
            rows.append(who(by_id[s.employee_id]) + [
                s.period_label, s.working_days, s.lop_days, float(s.total_earnings or 0),
                float(s.total_deductions or 0), float(s.net_pay or 0), s.status,
                s.credit_date, "Yes" if s.slip else "No"])
    elif export_type == "monthly":
        period = f.get("month") or date.today().strftime("%Y-%m")
        header = WHO + ["Month", "Working Days", "Days Worked", "Leave Days", "Late Logins", "Total Hours",
                        "Extra Hours", "Noon Reports", "EOD Reports", "Missing Reports", "Net Payable"]
        for e in people:
            data = monthly_report_service.build(db, e, period)
            sal = data.get("salary") if H.can_view_sensitive(db, user, e) else None
            payable = ""
            if sal:
                payable = sal.get("estimated_net_payable")
                if payable is None:
                    payable = sal.get("net_pay", "")
            rows.append(who(e) + [
                data["period"], data["attendance"].get("working_days"), data["attendance"]["days_worked"],
                data["attendance"]["leave_days"], data["login"]["late_login_count"],
                round((data["hours"]["actual_minutes"] or 0) / 60, 2),
                round((data["hours"]["extra_minutes"] or 0) / 60, 2),
                data["reports"]["noon_submitted"], data["reports"]["eod_submitted"],
                data["reports"]["missing_total"], payable])

    ws.append(header)
    for row in rows:
        ws.append([_xl(v) for v in row])
    _style_header(ws)
    meta = wb.create_sheet("Export info")
    meta.append(["Exported by", user.display_name])
    meta.append(["Exported at", datetime.now().strftime("%Y-%m-%d %H:%M")])
    meta.append(["Export", EXPORT_TYPES[export_type]])
    meta.append(["Scope", "Organisation" if H.is_admin(user) else ("Own records" if f.get("self_only") else "Your hierarchy")])
    for k, v in sorted(f.items()):
        if v not in (None, "", False):
            meta.append([f"Filter: {k}", str(v)])
    meta.append(["Records", len(rows)])
    _style_header(meta, {1: 26, 2: 60})
    name = f"{export_type}_{date.today().isoformat()}.xlsx"
    return workbook_bytes(wb), len(rows), name


def _xl(v):
    if isinstance(v, datetime):
        return v.replace(tzinfo=None)
    return v
