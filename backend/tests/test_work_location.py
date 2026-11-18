"""Work location on salary slips.

The payslip "Location" field prints the employee's own work location, or the
company default from Settings when they have none. HR sets it on the employee
form (create / edit) or through Excel import; changing it re-renders generated
payslips that are not yet credited.
"""
import io
import uuid

import pdfplumber
import pytest
from openpyxl import Workbook, load_workbook

from app.database.database import SessionLocal
from app.models.employee import Employee


def _location(client, headers, salary_id):
    r = client.get(f"/api/salaries/{salary_id}/payslip", headers=headers)
    assert r.status_code == 200, r.text
    with pdfplumber.open(io.BytesIO(r.content)) as pdf:
        text = pdf.pages[0].extract_text()
    line = next(l for l in text.splitlines() if "Location" in l)
    return line.split("Location", 1)[1].split(":", 1)[1].split("PAN")[0].strip()


def _new_employee(client, hr_headers, **extra):
    deps = {d["name"]: d["id"] for d in client.get("/api/departments", headers=hr_headers).json()}
    tag = uuid.uuid4().hex[:6]
    body = {"full_name": f"Loc Person {tag}", "email": f"loc{tag}@loctest.com", "designation": "Associate",
            "joining_date": "2026-09-01", "employee_type": "Employee", "department_id": deps["Marketing"],
            "send_account_email": False}
    body.update(extra)
    r = client.post("/api/employees", headers=hr_headers, json=body)
    assert r.status_code == 201, r.text
    return r.json()["employee"]


def _slip(client, hr_headers, employee_id, month, credit=False):
    r = client.post("/api/salaries", headers=hr_headers, json={
        "employee_id": employee_id, "period_year": 2026, "period_month": month, "working_days": 22,
        "components": [{"component_type": "earning", "name": "Basic", "amount": "20000.00"}]})
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    if credit:
        assert client.post(f"/api/salaries/{sid}/credit", headers=hr_headers, json={}).status_code == 200
    else:
        assert client.post(f"/api/salaries/{sid}/payslip/generate", headers=hr_headers).status_code == 200
    return sid


@pytest.fixture()
def default_location(client, hr_headers):
    before = client.get("/api/settings", headers=hr_headers).json()["values"].get("default_work_location", "")
    yield
    client.put("/api/settings", headers=hr_headers, json={"values": {"default_work_location": before}})


def test_location_set_on_create_is_printed(client, hr_headers):
    e = _new_employee(client, hr_headers, work_location="  Bengaluru ")
    detail = client.get(f"/api/employees/{e['id']}", headers=hr_headers).json()
    assert detail["work_location"] == "Bengaluru"
    sid = _slip(client, hr_headers, e["id"], 1)
    assert _location(client, hr_headers, sid) == "Bengaluru"


def test_blank_location_uses_company_default(client, hr_headers, default_location):
    e = _new_employee(client, hr_headers)
    assert client.get(f"/api/employees/{e['id']}", headers=hr_headers).json()["work_location"] is None
    client.put("/api/settings", headers=hr_headers, json={"values": {"default_work_location": ""}})
    sid = _slip(client, hr_headers, e["id"], 2)
    assert _location(client, hr_headers, sid) == "-"
    # Setting the default re-renders the not-yet-credited slip.
    r = client.put("/api/settings", headers=hr_headers, json={"values": {"default_work_location": " Pune "}})
    assert r.status_code == 200 and r.json()["values"]["default_work_location"] == "Pune"
    assert _location(client, hr_headers, sid) == "Pune"


def test_editing_location_refreshes_pending_slips_only(client, hr_headers, default_location):
    client.put("/api/settings", headers=hr_headers, json={"values": {"default_work_location": "Pune"}})
    e = _new_employee(client, hr_headers)
    credited = _slip(client, hr_headers, e["id"], 3, credit=True)
    pending = _slip(client, hr_headers, e["id"], 4)
    assert _location(client, hr_headers, credited) == "Pune"
    r = client.put(f"/api/employees/{e['id']}", headers=hr_headers, json={"work_location": "Mumbai"})
    assert r.status_code == 200 and r.json()["work_location"] == "Mumbai"
    assert _location(client, hr_headers, pending) == "Mumbai"
    assert _location(client, hr_headers, credited) == "Pune"       # a paid slip keeps what it said
    # Clearing it falls back to the default again.
    r = client.put(f"/api/employees/{e['id']}", headers=hr_headers, json={"work_location": "  "})
    assert r.json()["work_location"] is None
    assert _location(client, hr_headers, pending) == "Pune"


def test_location_is_limited_to_120_characters(client, hr_headers):
    deps = {d["name"]: d["id"] for d in client.get("/api/departments", headers=hr_headers).json()}
    r = client.post("/api/employees", headers=hr_headers, json={
        "full_name": "Too Long", "email": f"long{uuid.uuid4().hex[:6]}@loctest.com", "designation": "Associate",
        "joining_date": "2026-09-01", "employee_type": "Employee", "department_id": deps["Marketing"],
        "send_account_email": False, "work_location": "x" * 121})
    assert r.status_code == 422


def test_excel_template_import_and_export_carry_work_location(client, hr_headers):
    t = client.get("/api/excel/template", headers=hr_headers)
    headers = [c.value for c in load_workbook(io.BytesIO(t.content))["Employees"][1]]
    assert "Work Location" in headers and headers.index("Work Location") == headers.index("Address") + 1

    tag = uuid.uuid4().hex[:6]
    wb = Workbook()
    ws = wb.active
    ws.title = "Employees"
    cols = ["Full Name", "Employee Type", "Department", "Designation", "Email", "Joining Date", "Work Location"]
    ws.append(cols)
    ws.append([f"Xl Loc {tag}", "Employee", "Marketing", "Executive", f"xlloc{tag}@loctest.com", "2026-09-01", "Chennai"])
    buf = io.BytesIO(); wb.save(buf)
    p = client.post("/api/excel/import/preview", data={"mode": "create"}, headers=hr_headers,
                    files={"file": ("p.xlsx", buf.getvalue(), "application/octet-stream")})
    assert p.status_code == 200, p.text
    assert p.json()["counts"]["valid_rows"] == 1, p.json()
    c = client.post(f"/api/excel/import/{p.json()['token']}/confirm", json={}, headers=hr_headers)
    assert c.status_code == 200, c.text
    db = SessionLocal()
    try:
        e = db.query(Employee).filter(Employee.full_name == f"Xl Loc {tag}").first()
        assert e is not None and e.work_location == "Chennai"
    finally:
        db.close()

    x = client.get("/api/excel/export", params={"type": "employees"}, headers=hr_headers)
    assert x.status_code == 200, x.text
    ws = load_workbook(io.BytesIO(x.content)).active
    rows = list(ws.iter_rows(values_only=True))
    head = next(r for r in rows if r and "Work Location" in r)
    i_loc, i_name = head.index("Work Location"), head.index("Full Name")
    assert any(r[i_name] == f"Xl Loc {tag}" and r[i_loc] == "Chennai" for r in rows if r)
