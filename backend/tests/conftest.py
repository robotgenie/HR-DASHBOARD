"""Test fixtures: an isolated SQLite database and authenticated API clients."""
import os
import shutil
import tempfile
from datetime import date

import pytest

TEST_DIR = tempfile.mkdtemp(prefix="rg_test_")

# The suite runs on throwaway SQLite by default so it needs no services.
# Set RG_TEST_DB=postgres to run the identical suite against the PostgreSQL
# test database instead, proving parity on the engine used in production:
#   $env:RG_TEST_DB="postgres"; python -m pytest tests -q      (PowerShell)
#   RG_TEST_DB=postgres python -m pytest tests -q              (bash)
if os.getenv("RG_TEST_DB", "sqlite").lower() in {"postgres", "postgresql", "pg"}:
    _pg = os.getenv(
        "TEST_DATABASE_URL",
        "postgresql+psycopg2://rocket:rocket@localhost:5432/rocket_genie_hrms_test",
    )
    os.environ["DATABASE_URL"] = _pg
else:
    os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DIR}/test.db"

os.environ["UPLOAD_DIR"] = f"{TEST_DIR}/uploads"
os.environ["JWT_SECRET_KEY"] = "test-secret-key-not-for-production"
os.environ["SMTP_HOST"] = ""  # emails are logged, not sent
os.environ["SALARY_AUTOGEN_ENABLED"] = "false"  # tests trigger generation explicitly

from fastapi.testclient import TestClient  # noqa: E402
import base64 as _b64  # noqa: E402
import io as _io  # noqa: E402
from datetime import datetime as _dt, time as _time  # noqa: E402

from app.utils import clock  # noqa: E402

# Office-hour rules depend on the clock. The shared suite runs "today at
# 7:00 PM IST" so Noon and EOD reports are both open; scenario tests pin their
# own times with clock.set_fixed_now().
SUITE_NOW = _dt.combine(date.today(), _time(19, 0))
clock.set_fixed_now(SUITE_NOW)


def selfie_data_url() -> str:
    from PIL import Image
    buf = _io.BytesIO()
    Image.new("RGB", (8, 8), (120, 140, 160)).save(buf, format="PNG")
    return "data:image/png;base64," + _b64.b64encode(buf.getvalue()).decode()

from app.core.constants import (  # noqa: E402
    DEFAULT_DEPARTMENTS, DEFAULT_DOCUMENT_TYPES, DEFAULT_INTERNSHIP_BACKGROUNDS, RoleName,
)
from app.database.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models.department import Department  # noqa: E402
from app.models.document_type import DocumentType  # noqa: E402
from app.models.internship_background import InternshipBackground  # noqa: E402
from app.models.role import Role  # noqa: E402
from app.services import employee_service, file_service, settings_service  # noqa: E402

HR_PASSWORD = "TestHR@2026"
EMP_PASSWORD = "TestEmp@2026"

MINIMAL_PDF = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"
)
MINIMAL_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture(scope="session", autouse=True)
def _database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    file_service.ensure_dirs()

    db = SessionLocal()
    for name, label in ((RoleName.HR_ADMIN, "HR"), (RoleName.EMPLOYEE, "Employee"),
                        (RoleName.ADMIN, "Admin"), (RoleName.MANAGER, "Manager")):
        db.add(Role(name=name, label=label))
    for name, code in DEFAULT_DEPARTMENTS:
        db.add(Department(name=name, code=code))
    for name in DEFAULT_INTERNSHIP_BACKGROUNDS:
        db.add(InternshipBackground(name=name))
    for index, (name, code, required, extensions) in enumerate(DEFAULT_DOCUMENT_TYPES):
        db.add(
            DocumentType(
                name=name, code=code, is_required=required,
                allowed_extensions=extensions, sort_order=index,
            )
        )
    db.flush()
    settings_service.ensure_defaults(db)
    db.commit()
    db.close()

    yield
    shutil.rmtree(TEST_DIR, ignore_errors=True)


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client


def _make_user(department: str, designation: str, email: str, name: str,
               role: str, password: str, background: str = None):
    db = SessionLocal()
    try:
        dept = db.query(Department).filter(Department.name == department).first()
        bg = None
        if background:
            bg = (
                db.query(InternshipBackground)
                .filter(InternshipBackground.name == background)
                .first()
            )
        employee, _ = employee_service.create_employee(
            db,
            {
                "full_name": name, "email": email, "department_id": dept.id,
                "internship_background_id": bg.id if bg else None,
                "designation": designation, "joining_date": date(2026, 3, 9),
                "employment_status": "Active", "role": role,
            },
            actor=None, password=password, send_email=False,
        )
        employee.user.must_change_password = False
        db.commit()
        return {
            "id": employee.id, "user_id": employee.user_id, "email": email,
            "password": password, "code": employee.employee_code,
            "department_id": employee.department_id,
        }
    finally:
        db.close()


@pytest.fixture(scope="session")
def hr_user(_database):
    return _make_user("Senior HR", "Head of People", "hr@test.com", "HR Admin",
                      RoleName.HR_ADMIN, HR_PASSWORD)


@pytest.fixture(scope="session")
def employee_a(_database):
    return _make_user("Digital Marketing", "Trainee", "emp.a@test.com", "Employee A",
                      RoleName.EMPLOYEE, EMP_PASSWORD)


@pytest.fixture(scope="session")
def employee_b(_database):
    return _make_user("Marketing", "Sales Associate", "emp.b@test.com", "Employee B",
                      RoleName.EMPLOYEE, EMP_PASSWORD)


@pytest.fixture(scope="session")
def intern_ds(_database):
    return _make_user("Internship", "Trainee", "intern.ds@test.com", "Intern DS",
                      RoleName.EMPLOYEE, EMP_PASSWORD, background="Data Science")


@pytest.fixture(scope="session")
def intern_cy(_database):
    return _make_user("Internship", "Trainee", "intern.cy@test.com", "Intern Cyber",
                      RoleName.EMPLOYEE, EMP_PASSWORD, background="Cyber Security")


def login(client, email, password, reason="Traffic on the way", selfie=True):
    """Log in the way the browser does: answer each precondition the API asks for."""
    body = {"email": email, "password": password}
    for _ in range(4):
        response = client.post("/api/auth/login", json=body)
        if response.status_code != 428:
            return response
        payload = response.json()
        code, ctx = payload.get("code"), payload.get("context") or {}
        if code == "WORK_PERIOD_REQUIRED":
            body["work_period"] = ctx["work_period_options"][0]
        elif code == "LATE_LOGIN_REASON_REQUIRED":
            body["late_login_reason"] = reason
        elif code == "SELFIE_REQUIRED" and selfie:
            body["selfie_data"] = selfie_data_url()
        else:
            return response
    return response


def auth_headers(client, email, password):
    response = login(client, email, password)
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture(scope="session")
def hr_headers(client, hr_user):
    return auth_headers(client, hr_user["email"], hr_user["password"])


@pytest.fixture(scope="session")
def emp_a_headers(client, employee_a):
    return auth_headers(client, employee_a["email"], employee_a["password"])


@pytest.fixture(scope="session")
def emp_b_headers(client, employee_b):
    return auth_headers(client, employee_b["email"], employee_b["password"])


@pytest.fixture(scope="session")
def intern_ds_headers(client, intern_ds):
    return auth_headers(client, intern_ds["email"], intern_ds["password"])


@pytest.fixture(scope="session")
def intern_cy_headers(client, intern_cy):
    return auth_headers(client, intern_cy["email"], intern_cy["password"])


def hr_verify_photo(client, hr_headers, employee_id):
    """HR approves the employee's pending photograph (it then becomes the profile photo)."""
    docs = client.get(f"/api/documents/employee/{employee_id}", headers=hr_headers).json()
    photo = next(i for i in docs["items"] if i["code"] == "PHOTO")
    if photo["status"] == "Pending":
        r = client.post(f"/api/documents/{photo['document_id']}/verify", json={}, headers=hr_headers)
        assert r.status_code == 200, r.text


def request_and_approve_id(client, headers, employee_id, hr_headers):
    """Employee requests the ID; HR approves it (the current ID workflow)."""
    client.post("/api/employees/me/request-id-approval", headers=headers)
    client.post(f"/api/employees/{employee_id}/approve-id", headers=hr_headers)
