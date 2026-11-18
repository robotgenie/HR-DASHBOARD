"""Populate the database with realistic demo data.

Usage:
    python seed_data.py            # create reference data + demo records
    python seed_data.py --reset    # drop every table first, then seed

Demo passwords are development-only and are printed at the end.
"""
import argparse
import random
from io import BytesIO
import sys
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.utils.timeutil import utcnow
from app.core.constants import (
    DEFAULT_DEPARTMENTS, DEFAULT_DOCUMENT_TYPES, DEFAULT_INTERNSHIP_BACKGROUNDS,
    DocumentStatus, MeetingStatus, ReportStatus, RoleName, SalaryStatus, UanStatus,
)
from app.database.database import Base, SessionLocal, engine
from app.models.daily_report import DailyReport
from app.models.department import Department
from app.models.document_type import DocumentType
from app.models.document_version import DocumentVersion
from app.models.employee import Employee
from app.models.employee_document import EmployeeDocument
from app.models.internship_background import InternshipBackground
from app.models.meeting import Meeting
from app.models.report_attachment import ReportAttachment
from app.models.role import Role
from app.models.salary import SalaryRecord
from app.models.salary_component import SalaryComponent
from app.models.uan import UanDetail
from app.models.user import User
from app.services import employee_service, file_service, salary_service, settings_service

ADMIN_EMAIL = "admin@rocketgenie.com"
ADMIN_PASSWORD = "RocketAdmin@2026"
HR_PASSWORD = "RocketHR@2026"
EMPLOYEE_PASSWORD = "Rocket@2026"

random.seed(20260312)

# (name, email, department, designation, joining, gender, background)
PEOPLE = [
    ("Ananya Sharma", "hr@rocketgenie.com", "Senior HR", "Head of People", "2024-01-15", "Female", None),
    ("Rohit Verma", "rohit.verma@rocketgenie.com", "HR", "HR Executive", "2024-06-03", "Male", None),
    ("Priya Nair", "employee1@rocketgenie.com", "Digital Marketing", "Digital Marketing Executive", "2025-02-10", "Female", None),
    ("Karan Mehta", "employee2@rocketgenie.com", "Marketing", "Sales Associate", "2025-04-21", "Male", None),
    ("Sneha Iyer", "sneha.iyer@rocketgenie.com", "Teaching", "Senior Trainer", "2024-08-19", "Female", None),
    ("Aditya Rao", "aditya.rao@rocketgenie.com", "Teaching", "Trainer", "2025-07-14", "Male", None),
    ("Meera Joshi", "meera.joshi@rocketgenie.com", "Managers", "Operations Manager", "2023-11-06", "Female", None),
    ("Vikram Singh", "vikram.singh@rocketgenie.com", "Marketing", "Marketing Lead", "2024-03-25", "Male", None),
    ("Divya Menon", "divya.menon@rocketgenie.com", "Digital Marketing", "SEO Specialist", "2025-09-01", "Female", None),
    ("Arjun Kapoor", "arjun.kapoor@rocketgenie.com", "Managers", "Project Manager", "2024-05-13", "Male", None),
    ("Farhan Qureshi", "intern1@rocketgenie.com", "Internship", "Trainee", "2026-03-09", "Male", "Data Science"),
    ("Ishita Banerjee", "intern2@rocketgenie.com", "Internship", "Trainee", "2026-03-16", "Female", "Cyber Security"),
    ("Nikhil Pandey", "intern3@rocketgenie.com", "Internship", "Trainee", "2026-04-06", "Male", "Web Development"),
    ("Tanya Gupta", "intern4@rocketgenie.com", "Internship", "Trainee", "2026-04-20", "Female", "Data Analytics"),
    ("Rahul Desai", "rahul.desai@rocketgenie.com", "Teaching", "Curriculum Designer", "2025-01-08", "Male", None),
    ("Pooja Reddy", "pooja.reddy@rocketgenie.com", "Digital Marketing", "Content Strategist", "2025-11-17", "Female", None),
    ("Sameer Khan", "sameer.khan@rocketgenie.com", "Marketing", "Business Development", "2026-01-05", "Male", None),
]

MEETING_PLAN = [
    ("Marketing", "Daily Sales Day Plan", time(10, 15), time(10, 45),
     "Review yesterday's numbers and set today's call targets.",
     "https://meet.google.com/xkr-mqbn-ptd"),
    ("Digital Marketing", "Daily Work Discussion", time(10, 30), time(11, 0),
     "Campaign performance, creative reviews and blockers.",
     "https://meet.google.com/dwq-nyrs-vgk"),
    ("Teaching", "Daily Team Meeting", time(11, 0), time(11, 30),
     "Batch progress, learner escalations and schedule changes.",
     "https://meet.google.com/tbf-cmzx-jle"),
    ("Internship", "Intern Daily Meeting", time(11, 30), time(12, 0),
     "Task check-in, mentor Q&A and the day's deliverables.",
     "https://meet.google.com/inp-rkdv-qsw"),
]

SALARY_BANDS = {
    "Head of People": 95000, "Operations Manager": 78000, "Project Manager": 72000,
    "Marketing Lead": 62000, "Senior Trainer": 58000, "Curriculum Designer": 52000,
    "HR Executive": 38000, "Trainer": 42000, "SEO Specialist": 40000,
    "Digital Marketing Executive": 36000, "Content Strategist": 38000,
    "Sales Associate": 32000, "Business Development": 34000, "Trainee": 11129,
}

SAMPLE_PDF = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n"
    b"trailer<</Root 1 0 R>>\n%%EOF\n"
)


AVATAR_COLOURS = [
    (84, 127, 255), (110, 92, 255), (160, 85, 255), (14, 159, 110),
    (60, 99, 216), (180, 112, 10), (220, 43, 67), (30, 37, 80),
]


def _avatar_png(full_name: str) -> bytes:
    """A simple initials avatar so every seeded profile has a real photograph."""
    from PIL import Image, ImageDraw

    initials = "".join(part[0] for part in full_name.split()[:2]).upper() or "RG"
    colour = AVATAR_COLOURS[sum(map(ord, full_name)) % len(AVATAR_COLOURS)]
    size = 320
    image = Image.new("RGB", (size, size), colour)
    draw = ImageDraw.Draw(image)
    # A soft diagonal highlight keeps the avatars from looking like flat blocks.
    draw.polygon(
        [(0, size), (size, size * 0.45), (size, size), (0, size)],
        fill=tuple(min(255, c + 22) for c in colour),
    )
    try:
        from PIL import ImageFont

        font = ImageFont.load_default(size=132)
    except Exception:  # noqa: BLE001 - fall back to the bitmap default
        from PIL import ImageFont

        font = ImageFont.load_default()
    box = draw.textbbox((0, 0), initials, font=font)
    draw.text(
        ((size - (box[2] - box[0])) / 2 - box[0], (size - (box[3] - box[1])) / 2 - box[1]),
        initials, font=font, fill=(255, 255, 255),
    )
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def attach_photo(db: Session, employee: Employee) -> None:
    if employee.photo_path:
        return
    content = _avatar_png(employee.full_name)
    stored = file_service.build_stored_name(
        f"photo_{employee.employee_code}", "profile.png"
    )
    file_service.save_bytes(file_service.PHOTOS, stored, content)
    employee.photo_path = stored


def seed_payroll_details(db: Session) -> None:
    """Location, bank and PAN details the payslip prints."""
    banks = ['HDFC Bank', 'ICICI Bank', 'State Bank of India', 'Axis Bank', 'Kotak Mahindra Bank']
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    filled = 0
    for index, employee in enumerate(db.query(Employee).order_by(Employee.id).all()):
        if not employee.work_location:
            employee.work_location = "New Delhi"
        if not employee.bank_name:
            employee.bank_name = banks[index % len(banks)]
        if not employee.bank_account_no:
            employee.bank_account_no = f"50100{random.randint(10000000, 99999999)}"
        if not employee.pan_number:
            seq = "".join(letters[(index * 7 + i) % 26] for i in range(5))
            employee.pan_number = f"{seq}{1000 + index}{letters[index % 26]}"
        filled += 1
    db.commit()
    log(f"payroll details (location, bank, PAN) set for {filled} employees")


def seed_employee_ids(db: Session) -> None:
    """Issue RGEMP ids now that every seeded profile is complete."""
    issued = 0
    for employee in db.query(Employee).order_by(Employee.id).all():
        attach_photo(db, employee)
        db.flush()
        if employee_service.issue_employee_id(db, employee, actor=None):
            issued += 1
    db.commit()
    first = (
        db.query(Employee.unique_employee_id)
        .filter(Employee.unique_employee_id.isnot(None))
        .order_by(Employee.unique_employee_id)
        .first()
    )
    last = (
        db.query(Employee.unique_employee_id)
        .filter(Employee.unique_employee_id.isnot(None))
        .order_by(Employee.unique_employee_id.desc())
        .first()
    )
    span = f" ({first[0]}-{last[0]})" if first and last else ""
    log(f"{issued} unique employee ids + electronic ID cards issued{span}")


def log(message: str) -> None:
    print(f"  {message}")


def seed_reference(db: Session) -> None:
    for name, label, description in (
        (RoleName.ADMIN, "Admin", "Organisation administrator - monitors the whole organisation"),
        (RoleName.HR_ADMIN, "HR", "HR - manages the hierarchy assigned to them"),
        (RoleName.MANAGER, "Manager", "Supervises the employees and interns reporting to them"),
        (RoleName.EMPLOYEE, "Employee", "Access to their own records only"),
    ):
        if not db.query(Role).filter(Role.name == name).first():
            db.add(Role(name=name, label=label, description=description))

    for name, code in DEFAULT_DEPARTMENTS:
        department = db.query(Department).filter(Department.name == name).first()
        if department is None:
            db.add(Department(name=name, code=code, is_active=True))
        else:
            department.code = code
            department.is_active = True

    for name in DEFAULT_INTERNSHIP_BACKGROUNDS:
        if not db.query(InternshipBackground).filter(InternshipBackground.name == name).first():
            db.add(InternshipBackground(name=name, is_active=True))

    for index, (name, code, required, extensions) in enumerate(DEFAULT_DOCUMENT_TYPES):
        if not db.query(DocumentType).filter(DocumentType.code == code).first():
            db.add(
                DocumentType(
                    name=name, code=code, is_required=required,
                    allowed_extensions=extensions, sort_order=index, is_active=True,
                )
            )

    db.flush()
    settings_service.ensure_defaults(db)
    db.commit()
    log(f"Roles, {len(DEFAULT_DEPARTMENTS)} departments, "
        f"{len(DEFAULT_INTERNSHIP_BACKGROUNDS)} internship backgrounds, "
        f"{len(DEFAULT_DOCUMENT_TYPES)} document types")


def seed_people(db: Session) -> list:
    departments = {d.name: d for d in db.query(Department).all()}
    backgrounds = {b.name: b for b in db.query(InternshipBackground).all()}
    created = []

    for full_name, email, dept, designation, joining, gender, background in PEOPLE:
        if db.query(User).filter(User.email == email).first():
            continue

        is_hr_account = dept in ("HR", "Senior HR")
        payload = {
            "full_name": full_name,
            "email": email,
            "phone": f"+91 9{random.randint(100000000, 999999999)}",
            "date_of_birth": date(random.randint(1988, 2003), random.randint(1, 12), random.randint(1, 28)),
            "gender": gender,
            "department_id": departments[dept].id,
            "internship_background_id": backgrounds[background].id if background else None,
            "designation": designation,
            "joining_date": date.fromisoformat(joining),
            "employment_status": "Active",
            "address": f"{random.randint(1, 90)} Laxmi Nagar, New Delhi - 110092",
            "emergency_contact_name": "Family Contact",
            "emergency_contact_phone": f"+91 9{random.randint(100000000, 999999999)}",
            "emergency_contact_relation": random.choice(["Parent", "Sibling", "Spouse"]),
            "role": RoleName.HR_ADMIN if is_hr_account else RoleName.EMPLOYEE,
        }
        employee, _ = employee_service.create_employee(
            db, payload, actor=None,
            password=HR_PASSWORD if is_hr_account else EMPLOYEE_PASSWORD,
            send_email=False,
        )
        employee.user.must_change_password = False
        created.append(employee)

    db.commit()

    seed_hierarchy(db)

    log(f"{len(created)} employees (incl. 4 interns across 4 backgrounds)")
    return created


# Demo hierarchy:  Admin -> HR -> Manager -> Employees / Interns
HIERARCHY = {
    # manager email: (reporting HR email, [team emails])
    "meera.joshi@rocketgenie.com": ("hr@rocketgenie.com", [
        "employee1@rocketgenie.com", "divya.menon@rocketgenie.com", "pooja.reddy@rocketgenie.com",
        "intern1@rocketgenie.com", "intern2@rocketgenie.com",
    ]),
    "arjun.kapoor@rocketgenie.com": ("rohit.verma@rocketgenie.com", [
        "employee2@rocketgenie.com", "vikram.singh@rocketgenie.com", "sameer.khan@rocketgenie.com",
        "intern3@rocketgenie.com", "intern4@rocketgenie.com",
    ]),
}
# Employees who report straight to an HR (no manager in between).
HR_DIRECT = {
    "rohit.verma@rocketgenie.com": [
        "sneha.iyer@rocketgenie.com", "aditya.rao@rocketgenie.com", "rahul.desai@rocketgenie.com",
    ],
}


def _by_email(db: Session, email: str):
    user = db.query(User).filter(User.email == email).first()
    return user.employee if user is not None else None


def seed_hierarchy(db: Session) -> None:
    """Assign roles and reporting lines through the same service the app uses."""
    from app.services import hierarchy_service

    links = 0
    for manager_email, (hr_email, team) in HIERARCHY.items():
        manager, hr = _by_email(db, manager_email), _by_email(db, hr_email)
        if manager is None or hr is None:
            continue
        if manager.role_name != RoleName.MANAGER or manager.reporting_hr_id != hr.id:
            hierarchy_service.apply_assignment(
                db, None, manager, role=RoleName.MANAGER, reporting_hr_id=hr.id,
                reporting_manager_id=None, notify=False,
            )
            links += 1
        for email in team:
            member = _by_email(db, email)
            if member is not None and member.reporting_manager_id != manager.id:
                hierarchy_service.apply_assignment(
                    db, None, member, reporting_manager_id=manager.id, notify=False,
                )
                links += 1
    for hr_email, people in HR_DIRECT.items():
        hr = _by_email(db, hr_email)
        for email in people:
            member = _by_email(db, email)
            if hr is not None and member is not None and member.reporting_hr_id != hr.id:
                hierarchy_service.apply_assignment(
                    db, None, member, reporting_hr_id=hr.id, reporting_manager_id=None, notify=False,
                )
                links += 1
    db.commit()
    log(f"Hierarchy: 2 HR -> 2 managers -> teams ({links} reporting lines set)")


def seed_admin(db: Session) -> None:
    from app.api.admin import create_admin_account

    role = db.query(Role).filter(Role.name == RoleName.ADMIN).first()
    if role is not None and db.query(User).filter(User.role_id == role.id).first():
        return
    user, _ = create_admin_account(db, ADMIN_EMAIL, "Organisation Admin", password=ADMIN_PASSWORD,
                                   title="Administrator")
    user.must_change_password = False
    db.commit()
    log(f"Admin account {ADMIN_EMAIL}")


def seed_documents(db: Session) -> None:
    doc_types = db.query(DocumentType).order_by(DocumentType.sort_order).all()
    employees = db.query(Employee).all()
    hr_user = db.query(User).filter(User.email == "hr@rocketgenie.com").first()
    file_service.ensure_dirs()
    made = 0

    for employee in employees:
        # Vary completeness so the dashboard looks realistic.
        take = random.choice([len(doc_types), len(doc_types) - 1, len(doc_types) - 2, 4])
        for doc_type in doc_types[:take]:
            if db.query(EmployeeDocument).filter(
                EmployeeDocument.employee_id == employee.id,
                EmployeeDocument.document_type_id == doc_type.id,
            ).first():
                continue

            record = EmployeeDocument(
                employee_id=employee.id, document_type_id=doc_type.id,
                status=DocumentStatus.PENDING,
            )
            db.add(record)
            db.flush()

            outcome = random.choices(
                [DocumentStatus.VERIFIED, DocumentStatus.PENDING, DocumentStatus.REJECTED],
                weights=[6, 3, 1],
            )[0]

            filename = f"{doc_type.code.lower()}.pdf"
            stored = file_service.build_stored_name(
                f"{employee.employee_code}_{doc_type.code}_v1", filename
            )
            file_service.save_bytes(file_service.DOCUMENTS, stored, SAMPLE_PDF)

            db.add(
                DocumentVersion(
                    employee_document_id=record.id, version_no=1, stored_filename=stored,
                    original_filename=filename, mime_type="application/pdf",
                    file_size=len(SAMPLE_PDF), status=outcome,
                    uploaded_by_id=employee.user_id,
                    created_at=utcnow() - timedelta(days=random.randint(1, 60)),
                )
            )
            record.status = outcome
            if outcome == DocumentStatus.REJECTED:
                record.hr_remarks = "The scan is blurry. Please upload a clearer copy."
                record.reviewed_by_id = hr_user.id if hr_user else None
                record.reviewed_at = utcnow()
            elif outcome == DocumentStatus.VERIFIED:
                record.reviewed_by_id = hr_user.id if hr_user else None
                record.reviewed_at = utcnow()
            made += 1

    db.commit()
    log(f"{made} employee documents with version history")


def seed_uan(db: Session) -> None:
    for employee in db.query(Employee).all():
        record = db.query(UanDetail).filter(UanDetail.employee_id == employee.id).first()
        if record is None:
            record = UanDetail(employee_id=employee.id)
            db.add(record)
            db.flush()
        if record.status != UanStatus.NOT_SUBMITTED:
            continue

        choice = random.choices(
            [UanStatus.VERIFIED, UanStatus.SUBMITTED, UanStatus.NOT_SUBMITTED],
            weights=[5, 3, 2],
        )[0]
        if choice == UanStatus.NOT_SUBMITTED:
            continue
        record.uan_number = str(random.randint(100000000000, 999999999999))
        record.status = choice
        record.submitted_at = utcnow() - timedelta(days=random.randint(2, 90))
        if choice == UanStatus.VERIFIED:
            record.verified_at = utcnow() - timedelta(days=random.randint(0, 10))
    db.commit()
    log("UAN records across all statuses")


def _components(gross: int) -> list:
    """Basic + Incentive, matching the payslip structure. No HRA, no Special Allowance."""
    basic = round(gross * 0.625)
    incentive = gross - basic
    rows = [("earning", "Basic", basic), ("earning", "Incentive", incentive)]
    if gross > 12000:
        rows.append(("deduction", "PT", 200))
    return rows


def seed_salaries(db: Session) -> None:
    hr_user = db.query(User).filter(User.email == "hr@rocketgenie.com").first()
    today = date.today()
    periods = []
    for back in range(3, -1, -1):
        month = today.month - back
        year = today.year
        while month <= 0:
            month += 12
            year -= 1
        periods.append((year, month))

    made = 0
    for employee in db.query(Employee).all():
        gross = SALARY_BANDS.get(employee.designation, 30000)
        for index, (year, month) in enumerate(periods):
            if date(year, month, 28) < employee.joining_date:
                continue
            if db.query(SalaryRecord).filter(
                SalaryRecord.employee_id == employee.id,
                SalaryRecord.period_year == year,
                SalaryRecord.period_month == month,
            ).first():
                continue

            is_current = index == len(periods) - 1
            record = SalaryRecord(
                employee_id=employee.id, period_year=year, period_month=month,
                working_days=random.choice([26, 30, 31]),
                status=SalaryStatus.PENDING if is_current else SalaryStatus.CREDITED,
                created_by_id=hr_user.id if hr_user else None,
            )
            db.add(record)
            db.flush()

            for order, (ctype, name, amount) in enumerate(_components(gross)):
                record.components.append(
                    SalaryComponent(
                        component_type=ctype, name=name,
                        amount=Decimal(str(amount)), sort_order=order,
                    )
                )
            db.flush()
            salary_service.recalculate(record)

            if not is_current:
                record.credit_date = date(year, month, 28)
                record.credited_at = datetime.combine(record.credit_date, time(18, 0))
                record.credited_by_id = hr_user.id if hr_user else None
                # Historic rows are pre-credited; the notification/email fan-out is
                # exercised live from the UI on the current (Pending) period.
                record.credit_notified_at = record.credited_at
                record.credit_email_sent_at = record.credited_at
            made += 1

    db.commit()
    log(f"{made} salary records over {len(periods)} pay periods")


def seed_payslips(db: Session) -> None:
    from app.services import payslip_service

    count = 0
    credited = (
        db.query(SalaryRecord).filter(SalaryRecord.status == SalaryStatus.CREDITED).all()
    )
    for record in credited:
        if record.slip is None:
            payslip_service.generate_and_store(db, record, actor=None)
            count += 1
    db.commit()
    log(f"{count} payslip PDFs generated")


def seed_meetings(db: Session) -> None:
    departments = {d.name: d for d in db.query(Department).all()}
    hr_user = db.query(User).filter(User.email == "hr@rocketgenie.com").first()
    made = 0

    for offset in (0, 1, -1, -2):
        meeting_day = date.today() + timedelta(days=offset)
        for dept, title, start, end, agenda, url in MEETING_PLAN:
            if db.query(Meeting).filter(
                Meeting.department_id == departments[dept].id,
                Meeting.meeting_date == meeting_day,
                Meeting.start_time == start,
            ).first():
                continue
            db.add(
                Meeting(
                    title=title, department_id=departments[dept].id,
                    meeting_date=meeting_day, start_time=start, end_time=end,
                    agenda=agenda, google_meet_url=url,
                    status=MeetingStatus.COMPLETED if offset < 0 else MeetingStatus.SCHEDULED,
                    created_by_id=hr_user.id if hr_user else None,
                )
            )
            made += 1
    db.commit()
    log(f"{made} department meetings (4 departments x 4 days)")


def seed_intern_permissions(db: Session) -> None:
    """Grant download permission on the oldest intern payslip only.

    That leaves each intern with at least one downloadable payslip and at least
    one that is view-only, so the permission rule is visible in the demo.
    """
    granted = 0
    interns = [e for e in db.query(Employee).all() if e.is_intern]
    for intern in interns:
        credited = sorted(
            [
                r for r in intern.salary_records
                if r.status == SalaryStatus.CREDITED
            ],
            key=lambda r: (r.period_year, r.period_month),
        )
        if not credited:
            continue
        record = credited[0]
        if not record.intern_download_allowed:
            record.intern_download_allowed = True
            record.download_permission_at = datetime.now()
            granted += 1
    db.commit()
    log(f"{granted} intern payslip download permissions granted (rest view-only)")


def seed_reports(db: Session) -> None:
    made = 0
    employees = [
        e for e in db.query(Employee).all()
        if e.department.name not in ("HR", "Senior HR")
    ]
    for employee in employees:
        for back in range(0, 4):
            report_day = date.today() - timedelta(days=back)
            if report_day < employee.joining_date:
                continue
            if db.query(DailyReport).filter(
                DailyReport.employee_id == employee.id,
                DailyReport.report_date == report_day,
            ).first():
                continue
            if back == 0 and random.random() < 0.45:
                continue  # some people haven't filed today's report yet

            report = DailyReport(
                    employee_id=employee.id, report_date=report_day,
                    tasks_completed="Closed the assigned tickets and updated the tracker.",
                    tasks_in_progress="Drafting the weekly summary for the team review.",
                    tasks_pending="Waiting on design assets before the next handover.",
                    work_summary=(
                        f"Worked across {employee.department.name} deliverables, "
                        "attended the daily stand-up and cleared the open queue."
                    ),
                    challenges="None blocking." if random.random() > 0.3
                    else "Access to the shared drive was slow this morning.",
                    additional_comments=None,
                    status=ReportStatus.REVIEWED if back > 1 else ReportStatus.SUBMITTED,
                    submitted_at=datetime.combine(report_day, time(18, random.randint(0, 59))),
            )
            db.add(report)
            db.flush()

            # Submitted reports must carry evidence: an EOD report without an
            # attachment can no longer be submitted, so seeded ones get one too.
            content = _avatar_png(f"{employee.full_name} {report_day}")
            stored = file_service.build_stored_name(
                f"report_{employee.employee_code}", "eod-screenshot.png"
            )
            file_service.save_bytes(file_service.REPORTS, stored, content)
            db.add(
                ReportAttachment(
                    daily_report_id=report.id,
                    stored_filename=stored,
                    original_filename="eod-screenshot.png",
                    mime_type="image/png",
                    file_size=len(content),
                    uploaded_by_id=employee.user_id,
                )
            )
            made += 1
    db.commit()
    log(f"{made} daily work reports (each with an attachment)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the Rocket Genie HRMS database")
    parser.add_argument("--reset", action="store_true", help="Drop all tables first")
    args = parser.parse_args()

    if args.reset:
        print("Dropping all tables...")
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    db = SessionLocal()
    try:
        print("\nSeeding Rocket Genie HRMS")
        print("-" * 58)
        seed_reference(db)
        seed_admin(db)
        seed_people(db)
        seed_hierarchy(db)
        seed_employee_ids(db)
        seed_payroll_details(db)
        seed_documents(db)
        seed_uan(db)
        seed_salaries(db)
        seed_payslips(db)
        seed_meetings(db)
        seed_reports(db)
        seed_intern_permissions(db)
        print("-" * 58)
        print("\nDemo accounts (development only):\n")
        print(f"  Admin        {ADMIN_EMAIL}       {ADMIN_PASSWORD}  (no check-in)")
        print(f"  HR           hr@rocketgenie.com          {HR_PASSWORD}  (Ananya - Meera's team)")
        print(f"  HR           rohit.verma@rocketgenie.com {HR_PASSWORD}  (Rohit - Arjun's team + Teaching)")
        print(f"  Manager      meera.joshi@rocketgenie.com  {EMPLOYEE_PASSWORD}  (reports to Ananya)")
        print(f"  Manager      arjun.kapoor@rocketgenie.com {EMPLOYEE_PASSWORD}  (reports to Rohit)")
        print(f"  Employee     employee1@rocketgenie.com   {EMPLOYEE_PASSWORD}  (Digital Marketing)")
        print(f"  Employee     employee2@rocketgenie.com   {EMPLOYEE_PASSWORD}  (Marketing)")
        print(f"  Intern       intern1@rocketgenie.com     {EMPLOYEE_PASSWORD}  (Data Science)")
        print(f"  Intern       intern2@rocketgenie.com     {EMPLOYEE_PASSWORD}  (Cyber Security)")
        print("\nEvery other seeded employee uses the employee password above.\n")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
