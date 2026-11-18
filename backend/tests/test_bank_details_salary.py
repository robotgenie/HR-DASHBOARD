"""Bank details (Documents page) + automatic monthly salary slips.

Covers the 13 acceptance tests of the "Bank details + salary slip automation"
update, calling the API directly as each role:

    Admin
     |- HR A ----- Manager A ---- Employee A1, Employee A2 (direct to HR A)
     |- HR B ----- Employee B1
"""
import io
import uuid
from datetime import date

import pdfplumber
import pytest

from app.core.constants import RoleName
from app.database.database import SessionLocal
from app.models.employee import Employee
from app.models.salary import SalaryRecord
from app.services import bank_details_service, hierarchy_service, salary_autogen_service
from tests.conftest import EMP_PASSWORD, _make_user

GOOD = {
    "bank_name": "HDFC Bank",
    "account_number": "50100123456789",
    "confirm_account_number": "50100123456789",
    "ifsc_code": "HDFC0001234",
    "pan_number": "ABCDE1234F",
    "confirmed": True,
}

TODAY = date.today()
CUR = (TODAY.year, TODAY.month)
PREV = (TODAY.year - 1, 12) if TODAY.month == 1 else (TODAY.year, TODAY.month - 1)
PREV2 = (PREV[0] - 1, 12) if PREV[1] == 1 else (PREV[0], PREV[1] - 1)


def _assign(person, **kw):
    db = SessionLocal()
    try:
        e = db.query(Employee).filter(Employee.id == person["id"]).first()
        hierarchy_service.apply_assignment(db, None, e, notify=False, **kw)
        db.commit()
    finally:
        db.close()


def _set_joining(person, day):
    db = SessionLocal()
    try:
        db.query(Employee).filter(Employee.id == person["id"]).update({"joining_date": day})
        db.commit()
    finally:
        db.close()


def _h(client, email, password=EMP_PASSWORD):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}, r.json()


def _employee(pid):
    db = SessionLocal()
    try:
        e = db.query(Employee).filter(Employee.id == pid).first()
        db.expunge(e)
        return e
    finally:
        db.close()


def _pdf_text(client, headers, salary_id):
    r = client.get(f"/api/salaries/{salary_id}/payslip", headers=headers)
    assert r.status_code == 200, r.text
    with pdfplumber.open(io.BytesIO(r.content)) as pdf:
        return "\n".join(p.extract_text() or "" for p in pdf.pages), len(pdf.pages)


@pytest.fixture(scope="module")
def org(client):
    tag = uuid.uuid4().hex[:5]
    mk = lambda dept, title, who, role=RoleName.EMPLOYEE: _make_user(  # noqa: E731
        dept, title, f"{who}.{tag}@banktest.com", f"{who.replace('_', ' ').title()} {tag}", role, EMP_PASSWORD)
    o = {
        "hr_a": mk("HR", "HR Executive", "hr_a", RoleName.HR_ADMIN),
        "hr_b": mk("Senior HR", "HR Lead", "hr_b", RoleName.HR_ADMIN),
        "mgr_a": mk("Managers", "Project Manager", "mgr_a"),
        "emp_a1": mk("Digital Marketing", "SEO Specialist", "emp_a1"),
        "emp_a2": mk("Teaching", "Trainer", "emp_a2"),
        "emp_b1": mk("Marketing", "Sales Associate", "emp_b1"),
    }
    _assign(o["mgr_a"], role=RoleName.MANAGER, reporting_hr_id=o["hr_a"]["id"])
    _assign(o["emp_a1"], reporting_manager_id=o["mgr_a"]["id"])
    _assign(o["emp_a2"], reporting_hr_id=o["hr_a"]["id"])
    _assign(o["emp_b1"], reporting_hr_id=o["hr_b"]["id"])
    for k in ("emp_a1", "emp_a2", "emp_b1"):
        _set_joining(o[k], date(PREV2[0], PREV2[1], 1))

    db = SessionLocal()
    try:
        from app.api.admin import create_admin_account
        user, _ = create_admin_account(db, f"admin.{tag}@banktest.com", "Org Admin", password="AdminPass@2026")
        user.must_change_password = False
        db.commit()
    finally:
        db.close()
    o["admin"] = {"email": f"admin.{tag}@banktest.com", "password": "AdminPass@2026"}
    for k, v in o.items():
        v["h"], v["login"] = _h(client, v["email"], v.get("password", EMP_PASSWORD))
    return o


def _salary(client, hr_h, employee_id, period, basic="30000.00", tds="1000.00"):
    r = client.post("/api/salaries", headers=hr_h, json={
        "employee_id": employee_id, "period_year": period[0], "period_month": period[1],
        "working_days": 22, "components": [
            {"component_type": "earning", "name": "Basic", "amount": basic},
            {"component_type": "earning", "name": "HRA", "amount": "5000.00"},
            {"component_type": "deduction", "name": "TDS", "amount": tds},
        ]})
    assert r.status_code == 201, r.text
    return r.json()


# ---------------------------------------------------------------- TEST 1
def test_01_employee_creation_does_not_ask_for_bank_details(client, hr_headers):
    deps = {d["name"]: d["id"] for d in client.get("/api/departments", headers=hr_headers).json()}
    tag = uuid.uuid4().hex[:6]
    r = client.post("/api/employees", headers=hr_headers, json={
        "full_name": "No Bank Yet", "email": f"nobank{tag}@banktest.com", "designation": "Associate",
        "joining_date": "2026-09-01", "employee_type": "Employee", "department_id": deps["Marketing"],
        "send_account_email": False})
    assert r.status_code == 201, r.text
    e = _employee(r.json()["employee"]["id"])
    assert e.bank_name is None and e.bank_account_no is None and e.pan_number is None and e.ifsc_code is None
    assert bank_details_service.is_complete(e) is False


# ---------------------------------------------------------------- TEST 2
def test_02_bank_details_section_for_the_employee(client, org):
    r = client.get("/api/bank-details/me", headers=org["emp_a1"]["h"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "Not Submitted" and body["mandatory"] is True and body["complete"] is False
    # Sign-in sends an employee without approved bank details to the Documents page.
    assert org["emp_a1"]["login"]["onboarding_required"] is True
    # The Admin has no employee record and therefore no bank details section.
    assert client.get("/api/bank-details/me", headers=org["admin"]["h"]).status_code == 404


# ---------------------------------------------------------------- TEST 3
@pytest.mark.parametrize("change, message", [
    ({"bank_name": ""}, "Bank Name"),
    ({"account_number": "", "confirm_account_number": ""}, "Bank Account Number"),
    ({"confirm_account_number": ""}, "Confirm Bank Account Number"),
    ({"ifsc_code": ""}, "IFSC Code"),
    ({"pan_number": ""}, "PAN Card Number"),
    ({"confirm_account_number": "50100123456780"}, "do not match"),
    ({"account_number": "12AB", "confirm_account_number": "12AB"}, "9 to 18 digits"),
    ({"ifsc_code": "HDFC1001234"}, "IFSC"),
    ({"ifsc_code": "HDF0001234"}, "IFSC"),
    ({"pan_number": "ABCD1234F"}, "PAN"),
    ({"pan_number": "ABCDE12345"}, "PAN"),
])
def test_03_backend_validation(client, org, change, message):
    r = client.post("/api/bank-details/me", headers=org["emp_a2"]["h"], json=dict(GOOD, **change))
    assert r.status_code == 422, r.text
    assert message in r.json()["detail"]
    assert client.get("/api/bank-details/me", headers=org["emp_a2"]["h"]).json()["latest_request"] is None


# ---------------------------------------------------------------- TEST 4
def test_04_confirmation_is_required(client, org):
    r = client.post("/api/bank-details/me", headers=org["emp_a2"]["h"], json=dict(GOOD, confirmed=False))
    assert r.status_code == 422 and "confirm" in r.json()["detail"].lower()
    assert bank_details_service.mask_account("50100123456789") == "XXXX XXXX 6789"


# ---------------------------------------------------------------- TEST 5
def test_05_submission_is_pending_approval(client, org):
    r = client.post("/api/bank-details/me", headers=org["emp_a1"]["h"], json=GOOD)
    assert r.status_code == 201, r.text
    assert r.json()["request"]["status"] == "Pending Approval"
    assert r.json()["request"]["account_number_masked"] == "XXXX XXXX 6789"
    assert r.json()["request"]["account_number"] is None
    me = client.get("/api/bank-details/me", headers=org["emp_a1"]["h"]).json()
    assert me["status"] == "Pending Approval" and me["approved"] is None
    # Not official yet: the employee record (what payslips print) is unchanged.
    assert _employee(org["emp_a1"]["id"]).bank_account_no is None
    # HR A sees it in the queue (masked); HR B does not.
    queue = client.get("/api/bank-details", headers=org["hr_a"]["h"]).json()["items"]
    row = next(i for i in queue if i["employee_id"] == org["emp_a1"]["id"])
    assert row["account_number"] is None and row["account_number_masked"] == "XXXX XXXX 6789"
    assert row["pan_number"] != GOOD["pan_number"]
    other = client.get("/api/bank-details", headers=org["hr_b"]["h"]).json()["items"]
    assert all(i["employee_id"] != org["emp_a1"]["id"] for i in other)
    org["req_a1"] = row["id"]


# ---------------------------------------------------------------- TEST 6 + 7
def test_06_07_approval_makes_details_official_and_fills_the_payslip(client, org):
    hr_a = org["hr_a"]["h"]
    # A generated payslip that exists before approval prints "-" for bank fields.
    sal = _salary(client, hr_a, org["emp_a1"]["id"], PREV2)
    assert client.post(f"/api/salaries/{sal['id']}/payslip/generate", headers=hr_a).status_code == 200
    before, pages_before = _pdf_text(client, hr_a, sal["id"])
    assert GOOD["account_number"] not in before

    # Unauthorised reviewers are refused by the backend.
    for who in ("hr_b", "mgr_a", "emp_a2", "emp_a1"):
        r = client.post(f"/api/bank-details/{org['req_a1']}/approve", headers=org[who]["h"], json={})
        assert r.status_code == 403, (who, r.text)

    full = client.get(f"/api/bank-details/{org['req_a1']}", headers=hr_a).json()
    assert full["account_number"] == GOOD["account_number"]          # reviewer sees the full value
    r = client.post(f"/api/bank-details/{org['req_a1']}/approve", headers=hr_a, json={})
    assert r.status_code == 200 and r.json()["status"] == "Approved"
    again = client.post(f"/api/bank-details/{org['req_a1']}/approve", headers=hr_a, json={})
    assert again.status_code == 409

    e = _employee(org["emp_a1"]["id"])
    assert (e.bank_name, e.bank_account_no, e.ifsc_code, e.pan_number) == (
        "HDFC Bank", "50100123456789", "HDFC0001234", "ABCDE1234F")
    me = client.get("/api/bank-details/me", headers=org["emp_a1"]["h"]).json()
    assert me["status"] == "Approved" and me["complete"] is True
    assert me["approved"]["account_number_masked"] == "XXXX XXXX 6789" and me["approved"]["account_number"] is None

    # TEST 7: existing Bank Name / Account / PAN fields filled, nothing new added.
    after, pages_after = _pdf_text(client, hr_a, sal["id"])
    assert "HDFC Bank" in after and "50100123456789" in after and "ABCDE1234F" in after
    assert "IFSC" not in after and "HDFC0001234" not in after
    assert "Branch" not in after and "Account Holder" not in after
    assert pages_after == pages_before
    for label in ("Bank Name", "Bank Account No.", "PAN No."):
        assert label in before and label in after
    # Every line label of the slip is unchanged: only the values were filled in.
    strip = lambda t: [ln.split(":")[0].split()[0] for ln in t.splitlines() if ln.strip()]  # noqa: E731
    assert len(strip(before)) == len(strip(after))


# ---------------------------------------------------------------- TEST 8
def test_08_reject_shows_reason_and_allows_resubmission(client, org):
    emp_h, hr_a = org["emp_a1"]["h"], org["hr_a"]["h"]
    changed = dict(GOOD, bank_name="State Bank of India", account_number="123456789012",
                   confirm_account_number="123456789012", ifsc_code="SBIN0005678")
    r = client.post("/api/bank-details/me", headers=emp_h, json=changed)
    assert r.status_code == 201
    rid = r.json()["request"]["id"]
    # Pending new details never replace the approved ones.
    assert _employee(org["emp_a1"]["id"]).bank_account_no == "50100123456789"

    assert client.post(f"/api/bank-details/{rid}/reject", headers=hr_a, json={}).status_code == 422
    r = client.post(f"/api/bank-details/{rid}/reject", headers=hr_a, json={"remarks": "Passbook name mismatch."})
    assert r.status_code == 200 and r.json()["status"] == "Rejected"
    me = client.get("/api/bank-details/me", headers=emp_h).json()
    assert me["status"] == "Rejected"
    assert me["latest_request"]["review_remarks"] == "Passbook name mismatch."
    assert me["approved"]["account_number_masked"] == "XXXX XXXX 6789"      # still the approved one
    assert _employee(org["emp_a1"]["id"]).bank_account_no == "50100123456789"

    r = client.post("/api/bank-details/me", headers=emp_h, json=dict(changed, bank_name="SBI"))
    assert r.status_code == 201 and r.json()["state"]["status"] == "Pending Approval"
    rid2 = r.json()["request"]["id"]
    assert client.post(f"/api/bank-details/{rid2}/approve", headers=hr_a, json={}).status_code == 200
    e = _employee(org["emp_a1"]["id"])
    assert (e.bank_name, e.bank_account_no, e.ifsc_code) == ("SBI", "123456789012", "SBIN0005678")


# ---------------------------------------------------------------- TEST 9
def test_09_next_month_is_generated_automatically(client, org):
    hr_a, hr_b = org["hr_a"]["h"], org["hr_b"]["h"]
    src = _salary(client, hr_a, org["emp_a2"]["id"], PREV, basic="40000.00", tds="2000.00")

    # HR B's run stays inside HR B's hierarchy.
    client.post("/api/salaries/auto-generate", headers=hr_b, json={})
    assert not client.get("/api/salaries", headers=hr_a, params={
        "employee_id": org["emp_a2"]["id"], "period_year": CUR[0], "period_month": CUR[1]}).json()["items"]

    # The unattended job (what the API's background loop runs) needs no dashboard.
    summary = salary_autogen_service.run_scheduled()
    assert summary is not None and summary["created"] >= 1
    rows = client.get("/api/salaries", headers=hr_a, params={
        "employee_id": org["emp_a2"]["id"], "period_year": CUR[0], "period_month": CUR[1]}).json()["items"]
    assert len(rows) == 1
    gen = rows[0]
    assert gen["auto_generated"] is True and gen["status"] == "Pending"
    assert gen["employee_id"] == org["emp_a2"]["id"]
    assert gen["net_pay"] == src["net_pay"]
    assert [(c["name"], c["amount"]) for c in gen["earnings"]] == [(c["name"], c["amount"]) for c in src["earnings"]]
    assert [(c["name"], c["amount"]) for c in gen["deductions"]] == [(c["name"], c["amount"]) for c in src["deductions"]]
    assert gen["working_days"] == salary_autogen_service.working_days_in(*CUR)
    # The same structure: the slip renders with the existing generator.
    assert client.post(f"/api/salaries/{gen['id']}/payslip/generate", headers=hr_a).status_code == 200
    org["gen_id"] = gen["id"]

    # Employees without any previous salary are left for HR, future months never created.
    assert not client.get("/api/salaries", headers=hr_b, params={"employee_id": org["emp_b1"]["id"]}).json()["items"]
    nxt = (CUR[0] + 1, 1) if CUR[1] == 12 else (CUR[0], CUR[1] + 1)
    db = SessionLocal()
    try:
        assert db.query(SalaryRecord).filter_by(period_year=nxt[0], period_month=nxt[1]).count() == 0
    finally:
        db.close()
    future = client.post("/api/salaries/auto-generate", headers=hr_a, json={"month": f"{nxt[0]}-{nxt[1]:02d}"})
    assert future.status_code == 422


def test_09b_catch_up_and_setting_switch(client, org):
    hr_a, admin = org["hr_a"]["h"], org["admin"]["h"]
    # Employee A1 has PREV2 only: a manual run fills PREV and CUR.
    r = client.post("/api/salaries/auto-generate", headers=admin, json={})
    assert r.status_code == 200, r.text
    items = client.get("/api/salaries", headers=hr_a, params={"employee_id": org["emp_a1"]["id"]}).json()["items"]
    periods = {(i["period_year"], i["period_month"]) for i in items}
    assert {PREV2, PREV, CUR} <= periods
    # Switched off in Settings -> the unattended job does nothing.
    assert client.put("/api/settings", headers=admin, json={"values": {"salary_auto_generate": False}}).status_code == 200
    try:
        assert salary_autogen_service.run_scheduled() is None
    finally:
        client.put("/api/settings", headers=admin, json={"values": {"salary_auto_generate": True}})


# ---------------------------------------------------------------- TEST 10
def test_10_no_duplicate_slip_for_the_same_month(client, org):
    hr_a = org["hr_a"]["h"]
    before = client.get("/api/salaries", headers=hr_a, params={"employee_id": org["emp_a2"]["id"]}).json()["meta"]["total"]
    r = client.post("/api/salaries/auto-generate", headers=hr_a, json={})
    assert r.status_code == 200 and r.json()["created"] == 0
    assert salary_autogen_service.run_scheduled()["created"] == 0
    dup = client.post("/api/salaries", headers=hr_a, json={
        "employee_id": org["emp_a2"]["id"], "period_year": CUR[0], "period_month": CUR[1],
        "working_days": 22, "components": []})
    assert dup.status_code == 409
    assert dup.json()["code"] == "SALARY_EXISTS" and dup.json()["context"]["salary_id"] == org["gen_id"]
    after = client.get("/api/salaries", headers=hr_a, params={"employee_id": org["emp_a2"]["id"]}).json()["meta"]["total"]
    assert before == after


# ---------------------------------------------------------------- TEST 11
def test_11_payment_only_editing_of_the_generated_slip(client, org):
    hr_a, sid = org["hr_a"]["h"], org["gen_id"]
    for fixed in ({"employee_id": org["emp_b1"]["id"]}, {"period_month": PREV[1]}, {"period_year": 2030}):
        r = client.put(f"/api/salaries/{sid}", headers=hr_a, json=fixed)
        assert r.status_code == 422, (fixed, r.text)
    r = client.put(f"/api/salaries/{sid}", headers=hr_a, json={"components": [
        {"component_type": "earning", "name": "Basic", "amount": "41234.00"},
        {"component_type": "earning", "name": "HRA", "amount": "5000.00"},
        {"component_type": "deduction", "name": "TDS", "amount": "2000.00"},
    ]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == sid and body["net_pay"] == "44234.00" and body["auto_generated"] is True
    assert body["employee_id"] == org["emp_a2"]["id"] and (body["period_year"], body["period_month"]) == CUR
    text, _ = _pdf_text(client, hr_a, sid)          # the existing slip now shows the edited payment
    assert "41,234" in text or "41234" in text
    # Credit it: same record, no second slip.
    assert client.post(f"/api/salaries/{sid}/credit", headers=hr_a, json={}).status_code == 200
    rows = client.get("/api/salaries", headers=hr_a, params={
        "employee_id": org["emp_a2"]["id"], "period_year": CUR[0], "period_month": CUR[1]}).json()["items"]
    assert len(rows) == 1 and rows[0]["status"] == "Credited"


# ---------------------------------------------------------------- TEST 12
def test_12_existing_edit_still_works_on_manual_slips(client, org):
    hr_b = org["hr_b"]["h"]
    sal = _salary(client, hr_b, org["emp_b1"]["id"], PREV)
    r = client.put(f"/api/salaries/{sal['id']}", headers=hr_b, json={
        "working_days": 20, "remarks": "Adjusted", "status": "Pending",
        "components": [{"component_type": "earning", "name": "Basic", "amount": "31000.00"}]})
    assert r.status_code == 200, r.text
    assert r.json()["working_days"] == 20 and r.json()["net_pay"] == "31000.00"
    assert r.json()["auto_generated"] is False


# ---------------------------------------------------------------- TEST 13
def test_13_privacy_and_authorization(client, org):
    rid = org["req_a1"]
    # Another employee cannot read someone else's submission.
    assert client.get(f"/api/bank-details/{rid}", headers=org["emp_b1"]["h"]).status_code == 403
    # The owner sees their own submission, masked.
    own = client.get(f"/api/bank-details/{rid}", headers=org["emp_a1"]["h"])
    assert own.status_code == 200 and own.json()["account_number"] is None
    # Employees and Managers have no review queue; a Manager can't read a team member's details.
    for who in ("emp_a1", "mgr_a"):
        assert client.get("/api/bank-details", headers=org[who]["h"]).status_code == 403
        assert client.get(f"/api/bank-details/{rid}", headers=org[who]["h"] if who == "mgr_a" else org["emp_b1"]["h"]).status_code == 403
    # HR outside the hierarchy cannot read or act.
    assert client.get(f"/api/bank-details/{rid}", headers=org["hr_b"]["h"]).status_code == 403
    assert client.get(f"/api/bank-details/employee/{org['emp_a1']['id']}", headers=org["hr_b"]["h"]).status_code == 403
    full = client.get(f"/api/bank-details/employee/{org['emp_a1']['id']}", headers=org["hr_a"]["h"])
    assert full.status_code == 200 and full.json()["approved"]["account_number"] == "123456789012"

    # HR's own bank details are approved by the Admin, never by the HR themselves.
    r = client.post("/api/bank-details/me", headers=org["hr_a"]["h"], json=GOOD)
    assert r.status_code == 201
    hr_rid = r.json()["request"]["id"]
    assert all(i["id"] != hr_rid for i in client.get("/api/bank-details", headers=org["hr_a"]["h"]).json()["items"])
    assert client.post(f"/api/bank-details/{hr_rid}/approve", headers=org["hr_a"]["h"], json={}).status_code == 403
    admin_q = client.get("/api/bank-details", headers=org["admin"]["h"]).json()["items"]
    assert any(i["id"] == hr_rid for i in admin_q)
    assert client.post(f"/api/bank-details/{hr_rid}/approve", headers=org["admin"]["h"], json={}).status_code == 200

    # Salary records stay private as before: a Manager never sees team salary.
    assert client.get(f"/api/salaries/{org['gen_id']}", headers=org["mgr_a"]["h"]).status_code == 403
