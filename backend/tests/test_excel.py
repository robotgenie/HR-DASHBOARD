"""Excel template, import (preview -> errors -> confirm), bulk update and
exports - all through the API, all hierarchy-aware."""
import io
import uuid

import pytest
from openpyxl import Workbook, load_workbook

from app.core.constants import RoleName
from app.database.database import SessionLocal
from app.models.audit_log import AuditLog
from app.models.employee import Employee
from app.models.excel_import_batch import ExcelImportBatch
from app.services import hierarchy_service
from tests.conftest import EMP_PASSWORD, _make_user

HEADERS = ["Employee ID", "Full Name", "Employee Type", "Department", "Designation", "Email",
           "Mobile Number", "Date of Birth", "Gender", "Address", "Joining Date", "Reporting HR",
           "Reporting Manager", "Manager Designation", "Employment Status", "Internship Background",
           "Internship Details"]


def _xlsx(rows, headers=HEADERS):
    wb = Workbook()
    ws = wb.active
    ws.title = "Employees"
    ws.append(headers)
    for r in rows:
        ws.append([r.get(h) for h in headers])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _h(client, email, password=EMP_PASSWORD):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _assign(pid, **kw):
    db = SessionLocal()
    try:
        e = db.query(Employee).filter(Employee.id == pid).first()
        hierarchy_service.apply_assignment(db, None, e, notify=False, **kw)
        db.commit()
    finally:
        db.close()


@pytest.fixture(scope="module")
def xorg(client):
    t = uuid.uuid4().hex[:5]
    hr_a = _make_user("HR", "HR Executive", f"xhra.{t}@xltest.com", f"XL HR A {t}", RoleName.HR_ADMIN, EMP_PASSWORD)
    hr_b = _make_user("HR", "HR Executive", f"xhrb.{t}@xltest.com", f"XL HR B {t}", RoleName.HR_ADMIN, EMP_PASSWORD)
    mgr_a = _make_user("Managers", "Project Manager", f"xmga.{t}@xltest.com", f"XL Mgr A {t}", RoleName.EMPLOYEE, EMP_PASSWORD)
    mgr_b = _make_user("Managers", "Ops Manager", f"xmgb.{t}@xltest.com", f"XL Mgr B {t}", RoleName.EMPLOYEE, EMP_PASSWORD)
    emp_a = _make_user("Marketing", "Exec", f"xema.{t}@xltest.com", f"XL Emp A {t}", RoleName.EMPLOYEE, EMP_PASSWORD)
    emp_b = _make_user("Marketing", "Exec", f"xemb.{t}@xltest.com", f"XL Emp B {t}", RoleName.EMPLOYEE, EMP_PASSWORD)
    _assign(mgr_a["id"], role=RoleName.MANAGER, reporting_hr_id=hr_a["id"])
    _assign(mgr_b["id"], role=RoleName.MANAGER, reporting_hr_id=hr_b["id"])
    _assign(emp_a["id"], reporting_manager_id=mgr_a["id"])
    _assign(emp_b["id"], reporting_manager_id=mgr_b["id"])
    db = SessionLocal()
    try:
        from app.api.admin import create_admin_account
        u, _ = create_admin_account(db, f"xadmin.{t}@xltest.com", "XL Admin", password="AdminPass@2026")
        u.must_change_password = False
        db.commit()
    finally:
        db.close()
    return {
        "t": t, "hr_a": hr_a, "hr_b": hr_b, "mgr_a": mgr_a, "mgr_b": mgr_b, "emp_a": emp_a, "emp_b": emp_b,
        "admin_h": _h(client, f"xadmin.{t}@xltest.com", "AdminPass@2026"),
        "hr_a_h": _h(client, hr_a["email"]), "hr_b_h": _h(client, hr_b["email"]),
        "mgr_a_h": _h(client, mgr_a["email"]), "emp_a_h": _h(client, emp_a["email"]),
    }


def _preview(client, h, content, mode="auto", name="people.xlsx"):
    return client.post("/api/excel/import/preview", data={"mode": mode},
                       files={"file": (name, content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                       headers=h)


def test_template_has_columns_and_dropdowns(client, xorg):
    r = client.get("/api/excel/template", headers=xorg["admin_h"])
    assert r.status_code == 200
    wb = load_workbook(io.BytesIO(r.content))
    assert {"Employees", "Reference", "Instructions"} <= set(wb.sheetnames)
    header = [c.value for c in wb["Employees"][1]]
    for h in ("Employee ID", "Full Name *", "Employee Type *", "Reporting HR", "Reporting Manager",
              "Manager Designation", "Employment Status", "Internship Details"):
        assert h in header
    assert wb["Employees"].data_validations.dataValidation          # dropdowns present
    ref = [c.value for c in wb["Reference"]["F"] if c.value]      # Reporting HR list
    assert any(xorg["hr_a"]["code"] in v for v in ref)
    assert client.get("/api/excel/template", headers=xorg["mgr_a_h"]).status_code == 403
    assert client.get("/api/excel/template", headers=xorg["emp_a_h"]).status_code == 403


def test_preview_validates_and_reports_errors(client, xorg):
    t = xorg["t"]
    rows = [
        {"Full Name": f"Good Manager {t}", "Employee Type": "Manager", "Department": "Managers",
         "Designation": "Team Lead", "Email": f"good.mgr.{t}@xltest.com", "Joining Date": "2026-09-01",
         "Reporting HR": xorg["hr_a"]["code"]},
        {"Full Name": f"Good Emp {t}", "Employee Type": "Employee", "Department": "Marketing",
         "Designation": "Executive", "Email": f"good.emp.{t}@xltest.com", "Joining Date": "01-09-2026",
         "Reporting Manager": f"good.mgr.{t}@xltest.com", "Mobile Number": "+91 9876543210"},
        {"Full Name": f"Good Intern {t}", "Employee Type": "Intern", "Department": "Internship",
         "Designation": "Trainee", "Email": f"good.int.{t}@xltest.com", "Joining Date": "2026-09-01",
         "Reporting Manager": xorg["mgr_a"]["code"], "Manager Designation": "Project Manager",
         "Internship Background": "Data Science", "Internship Details": "B.Tech, 6 months"},
        # duplicate email in file + already registered
        {"Full Name": "Dup One", "Employee Type": "Employee", "Department": "Marketing", "Designation": "Executive",
         "Email": xorg["emp_a"]["email"], "Joining Date": "2026-09-01"},
        # bad department, bad type, missing designation
        {"Full Name": "Bad Dept", "Employee Type": "Wizard", "Department": "Nowhere", "Email": f"bad.{t}@xltest.com",
         "Joining Date": "2026-09-01"},
        # hierarchy error: manager B belongs to HR B, row names HR A
        {"Full Name": "Wrong Line", "Employee Type": "Employee", "Department": "Marketing", "Designation": "Executive",
         "Email": f"wrong.{t}@xltest.com", "Joining Date": "2026-09-01",
         "Reporting HR": xorg["hr_a"]["code"], "Reporting Manager": xorg["mgr_b"]["code"]},
        # invalid manager / invalid HR references
        {"Full Name": "Ghost Ref", "Employee Type": "Employee", "Department": "Marketing", "Designation": "Executive",
         "Email": f"ghost.{t}@xltest.com", "Joining Date": "2026-09-01",
         "Reporting Manager": "RG-1999-9999", "Reporting HR": xorg["emp_b"]["code"]},
        # bad id format, bad email, intern without background, wrong manager designation
        {"Employee ID": "EMP-42", "Full Name": "Format Bad", "Employee Type": "Intern", "Department": "Internship",
         "Designation": "Trainee", "Email": "not-an-email", "Joining Date": "2026-13-45",
         "Reporting Manager": xorg["mgr_a"]["code"], "Manager Designation": "CEO"},
        # duplicate of row 3's email in the same file
        {"Full Name": "Same Mail", "Employee Type": "Employee", "Department": "Marketing", "Designation": "Executive",
         "Email": f"good.int.{t}@xltest.com", "Joining Date": "2026-09-01"},
    ]
    r = _preview(client, xorg["admin_h"], _xlsx(rows))
    assert r.status_code == 200, r.text
    p = r.json()
    c = p["counts"]
    assert c["total_rows"] == 9
    assert c["invalid_rows"] == 7 and c["valid_rows"] == 2
    assert c["invalid_departments"] >= 1 and c["invalid_reporting_managers"] >= 2
    assert c["hierarchy_errors"] >= 1 and c["missing_fields"] >= 1 and c["duplicate_rows"] >= 2
    msgs = " | ".join(e["message"] for row in p["rows"] for e in row["errors"])
    for needle in ("Department does not exist", "Employee Type must be", "Hierarchy error", "Reporting Manager not found",
                   "does not have the HR role", "Employee ID format", "Email address is not valid",
                   "Interns need an internship background", "designation is", "already registered",
                   "more than once", "Designation is required", "Joining Date is not a valid date"):
        assert needle in msgs, needle

    # Downloadable error report
    rep = client.get(f"/api/excel/import/{p['token']}/errors", headers=xorg["admin_h"])
    assert rep.status_code == 200
    ws = load_workbook(io.BytesIO(rep.content)).active
    head = [c.value for c in ws[1]]
    assert head == ["Row Number", "Employee ID", "Employee Name", "Field", "Invalid Value", "Error Message", "Suggested Correction"]
    assert ws.max_row > 8

    # Nothing was written by the preview
    db = SessionLocal()
    try:
        assert db.query(Employee).filter(Employee.full_name == f"Good Emp {t}").first() is None
        batch = db.query(ExcelImportBatch).filter(ExcelImportBatch.token == p["token"]).first()
        assert batch.status == "Previewed"
    finally:
        db.close()

    # Confirm imports only the valid rows, in hierarchy order, into the real tables
    r = client.post(f"/api/excel/import/{p['token']}/confirm", json={}, headers=xorg["admin_h"])
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["created"] == 2 and res["failed"] == 7 and len(res["credentials"]) == 2
    db = SessionLocal()
    try:
        mgr = db.query(Employee).filter(Employee.full_name == f"Good Manager {t}").first()
        emp = db.query(Employee).filter(Employee.full_name == f"Good Emp {t}").first()
        assert mgr.role_name == RoleName.MANAGER and mgr.reporting_hr_id == xorg["hr_a"]["id"]
        assert emp.reporting_manager_id == mgr.id and emp.reporting_hr_id == xorg["hr_a"]["id"]
        logs = db.query(AuditLog).filter(AuditLog.action.in_(["excel_import_previewed", "excel_import_confirmed"]),
                                         AuditLog.entity_id == batch.id).all()
        assert {l.action for l in logs} == {"excel_import_previewed", "excel_import_confirmed"}
        confirmed = next(l for l in logs if l.action == "excel_import_confirmed")
        assert confirmed.meta["created"] == 2 and confirmed.meta["failed"] == 7 and confirmed.meta["file_name"] == "people.xlsx"
        assert "records" not in (db.get(ExcelImportBatch, batch.id).payload or {})   # raw rows dropped
    finally:
        db.close()
    # The new people follow the hierarchy immediately
    assert client.get(f"/api/employees/{emp.id}", headers=xorg["hr_a_h"]).status_code == 200
    assert client.get(f"/api/employees/{emp.id}", headers=xorg["hr_b_h"]).status_code == 403
    # A preview can't be confirmed twice
    assert client.post(f"/api/excel/import/{p['token']}/confirm", json={}, headers=xorg["admin_h"]).status_code == 409


def test_missing_required_column_rejected(client, xorg):
    content = _xlsx([{"Full Name": "x"}], headers=["Full Name", "Department"])
    r = _preview(client, xorg["admin_h"], content)
    assert r.status_code == 422 and "Missing required column" in r.json()["detail"]
    r = _preview(client, xorg["admin_h"], b"not a workbook")
    assert r.status_code == 422
    r = _preview(client, xorg["admin_h"], b"x", name="people.csv")
    assert r.status_code == 422


def test_bulk_update_shows_diff_and_needs_hierarchy_confirmation(client, xorg):
    emp = xorg["emp_a"]
    rows = [{"Employee ID": emp["code"], "Designation": "Senior Executive", "Mobile Number": "9876501234"},
            {"Employee ID": xorg["emp_b"]["code"], "Reporting Manager": xorg["mgr_a"]["code"]}]
    p = _preview(client, xorg["admin_h"], _xlsx(rows), mode="update").json()
    first, second = p["rows"]
    assert first["action"] == "update" and not first["errors"]
    diff = {c["field"]: (c["old"], c["new"]) for c in first["changes"]}
    assert diff["Designation"] == ("Exec", "Senior Executive")
    assert second["hierarchy_change"] is True
    rm = next(c for c in second["changes"] if c["key"] == "reporting_manager")
    assert rm["old"].startswith("XL Mgr B") and rm["new"].startswith("XL Mgr A")
    r = client.post(f"/api/excel/import/{p['token']}/confirm", json={}, headers=xorg["admin_h"])
    assert r.status_code == 428
    r = client.post(f"/api/excel/import/{p['token']}/confirm", json={"confirm_hierarchy_changes": True}, headers=xorg["admin_h"])
    assert r.status_code == 200 and r.json()["updated"] == 2, r.text
    e = client.get(f"/api/employees/{xorg['emp_b']['id']}", headers=xorg["admin_h"]).json()
    assert e["reporting_manager_id"] == xorg["mgr_a"]["id"] and e["reporting_hr_id"] == xorg["hr_a"]["id"]
    assert client.get(f"/api/employees/{emp['id']}", headers=xorg["admin_h"]).json()["designation"] == "Senior Executive"
    # move back so other tests keep their setup
    _assign(xorg["emp_b"]["id"], reporting_manager_id=xorg["mgr_b"]["id"])


def test_create_mode_never_overwrites_existing_ids(client, xorg):
    rows = [{"Employee ID": xorg["emp_a"]["code"], "Full Name": "Overwrite", "Employee Type": "Employee",
             "Department": "Marketing", "Designation": "Exec", "Email": "ow@xltest.com", "Joining Date": "2026-09-01"}]
    p = _preview(client, xorg["admin_h"], _xlsx(rows), mode="create").json()
    assert p["counts"]["invalid_rows"] == 1
    assert "will not be overwritten" in p["rows"][0]["errors"][0]["message"]


def test_hr_import_is_limited_to_own_hierarchy(client, xorg):
    t = xorg["t"]
    rows = [
        {"Full Name": f"Mine {t}", "Employee Type": "Employee", "Department": "Marketing", "Designation": "Exec",
         "Email": f"mine.{t}@xltest.com", "Joining Date": "2026-09-01", "Reporting Manager": xorg["mgr_a"]["code"]},
        {"Full Name": f"Theirs {t}", "Employee Type": "Employee", "Department": "Marketing", "Designation": "Exec",
         "Email": f"theirs.{t}@xltest.com", "Joining Date": "2026-09-01", "Reporting Manager": xorg["mgr_b"]["code"]},
        {"Full Name": f"Other HR {t}", "Employee Type": "HR", "Department": "HR", "Designation": "HR",
         "Email": f"ohr.{t}@xltest.com", "Joining Date": "2026-09-01"},
        {"Employee ID": xorg["emp_b"]["code"], "Designation": "Hijack"},
    ]
    p = _preview(client, xorg["hr_a_h"], _xlsx(rows)).json()
    status = [r["status"] for r in p["rows"]]
    assert status == ["Valid", "Invalid", "Invalid", "Invalid"]
    # HR B can't open HR A's preview
    assert client.get(f"/api/excel/import/{p['token']}", headers=xorg["hr_b_h"]).status_code == 404
    r = client.post(f"/api/excel/import/{p['token']}/confirm", json={}, headers=xorg["hr_a_h"])
    assert r.json()["created"] == 1
    assert client.post("/api/excel/import/preview", files={"file": ("a.xlsx", _xlsx(rows), "application/octet-stream")},
                       headers=xorg["mgr_a_h"]).status_code == 403


def _export_names(client, h, **params):
    r = client.get("/api/excel/export", params=params, headers=h)
    assert r.status_code == 200, r.text
    ws = load_workbook(io.BytesIO(r.content)).active
    rows = list(ws.values)
    header = rows[0]
    col = header.index("Name") if "Name" in header else header.index("Full Name")
    return {row[col] for row in rows[1:]}, rows


def test_exports_respect_hierarchy(client, xorg):
    admin_names, _ = _export_names(client, xorg["admin_h"], type="employees")
    assert {xorg["emp_a"]["email"].split("@")[0]} and len(admin_names) > 5
    hr_names, _ = _export_names(client, xorg["hr_a_h"], type="employees")
    assert any(n.startswith("XL Emp A") for n in hr_names)
    assert not any(n.startswith("XL Emp B") or n.startswith("XL HR B") for n in hr_names)
    mgr_names, _ = _export_names(client, xorg["mgr_a_h"], type="employees")
    assert all(n.startswith("XL Mgr A") or n.startswith("XL Emp A") or n.startswith("Mine") or n.startswith("Good")
               for n in mgr_names)
    dept_names, rows = _export_names(client, xorg["admin_h"], type="employees", person_type="Manager")
    assert rows[0][3] == "Employee Type" and all(r[3] == "Manager" for r in rows[1:])
    assert client.get("/api/excel/export", params={"type": "salary"}, headers=xorg["mgr_a_h"]).status_code == 403
    assert client.get("/api/excel/export", params={"type": "employees"}, headers=xorg["emp_a_h"]).status_code == 403
    own, _ = _export_names(client, xorg["emp_a_h"], type="leave")
    assert own <= {n for n in own if n.startswith("XL Emp A")}
    for kind in ("attendance", "leave", "reports", "hourly", "tasks", "documents", "salary", "monthly", "hierarchy"):
        r = client.get("/api/excel/export", params={"type": kind, "month": "2026-09"}, headers=xorg["admin_h"])
        assert r.status_code == 200, (kind, r.text)
    types = {t["value"] for t in client.get("/api/excel/export/types", headers=xorg["mgr_a_h"]).json()["items"]}
    assert "salary" not in types and "employees" in types
    db = SessionLocal()
    try:
        assert db.query(AuditLog).filter(AuditLog.action == "excel_exported").count() >= 10
    finally:
        db.close()
