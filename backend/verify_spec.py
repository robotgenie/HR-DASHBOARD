"""
Live end-to-end verification of the four remaining spec requirements, run against
the real PostgreSQL database with real seeded data.

  A. Dynamic payslip re-test at Rs 25,500 (totals + amount-in-words must change)
  B. Salary credit idempotency (a second credit must not re-notify / re-email)
  C. Department-scoped meeting visibility (Marketing vs Internship)
  D. Document security (employee self-delete denied, cross-employee denied, HR allowed)
"""
import sys

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database.database import SessionLocal
from app.main import app

client = TestClient(app)
results = []


def record(name, passed, detail=""):
    results.append((name, passed, detail))
    print(f"  [{'PASS' if passed else 'FAIL'}] {name}" + (f"  -- {detail}" if detail else ""))


def login(email, password):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text[:200]}"
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def counts(salary_id, employee_id):
    """Notification + email-log counts tied to a salary credit."""
    with SessionLocal() as db:
        notif = db.execute(
            text("select count(*) from notifications where dedupe_key like :k"),
            {"k": f"salary:{salary_id}:%"},
        ).scalar()
        emails = db.execute(
            text("select count(*) from email_logs where dedupe_key like :k"),
            {"k": f"salary:{salary_id}:%"},
        ).scalar()
    return notif, emails


HR = login("hr@rocketgenie.com", "RocketHR@2026")

# ---------------------------------------------------------------- A
print("=" * 74)
print("A. DYNAMIC PAYSLIP RE-TEST @ Rs 25,500")
print("=" * 74)

# Resolve (or create) the reference employee by name rather than by a fixed id:
# reseeding the database reassigns numeric ids.
_found = client.get("/api/employees?search=Test Employee&page_size=5", headers=HR).json()
_match = [e for e in _found["items"] if e["full_name"] == "Test Employee"]
if _match:
    TEST_EMP = _match[0]["id"]
else:
    _depts = client.get("/api/departments", headers=HR).json()
    _depts = _depts["items"] if isinstance(_depts, dict) else _depts
    _dm = next(d["id"] for d in _depts if d["name"] == "Digital Marketing")
    _created = client.post("/api/employees", json={
        "full_name": "Test Employee",
        "email": "test.employee@rocketgenie.com",
        "department_id": _dm,
        "designation": "Trainee",
        "joining_date": "2026-03-09",
        "employment_status": "Active",
    }, headers=HR)
    assert _created.status_code in (200, 201), _created.text
    TEST_EMP = _created.json()["employee"]["id"]
print(f"  reference employee id: {TEST_EMP}")

MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]

existing = client.get(f"/api/salaries?employee_id={TEST_EMP}&page_size=200", headers=HR).json()
taken = {(x["period_year"], x["period_month"]) for x in existing["items"]}
period = next((y, m) for y in (2026, 2027) for m in range(1, 13) if (y, m) not in taken)
PY, PM = period
print(f"  using a fresh, never-credited period: {MONTHS[PM - 1]} {PY}")

payload = {
    "employee_id": TEST_EMP,
    "period_month": PM,
    "period_year": PY,
    "working_days": 30,
    "components": [
        {"name": "Basic Salary", "component_type": "earning", "amount": 12750},
        {"name": "House Rent Allowance", "component_type": "earning", "amount": 6375},
        {"name": "Travelling Allowance", "component_type": "earning", "amount": 5100},
        {"name": "Special Allowance", "component_type": "earning", "amount": 1275},
        {"name": "Provident Fund", "component_type": "deduction", "amount": 0},
        {"name": "ESI", "component_type": "deduction", "amount": 0},
    ],
}
r = client.post("/api/salaries", json=payload, headers=HR)
if r.status_code not in (200, 201):
    print(f"  !! create failed HTTP {r.status_code}: {r.text[:300]}")
    sys.exit(1)
sal = r.json()

sid = sal["id"]
print(f"  Salary #{sid}  {sal['period_label']}  working_days={sal['working_days']}")
print(f"  earnings={sal['total_earnings']}  deductions={sal['total_deductions']}  net={sal['net_pay']}")
print(f"  words: {sal['amount_in_words']}")

record("Total earnings recalculated to 25500", float(sal["total_earnings"]) == 25500.0, str(sal["total_earnings"]))
record("Net pay recalculated to 25500", float(sal["net_pay"]) == 25500.0, str(sal["net_pay"]))
record(
    "Amount in words regenerated dynamically",
    sal["amount_in_words"].strip().lower() == "twenty five thousand five hundred only",
    sal["amount_in_words"],
)
record("Period label follows month/year", sal["period_label"] == f"{MONTHS[PM - 1]} {PY}", sal["period_label"])

# employee identity must be unchanged
det = client.get(f"/api/employees/{TEST_EMP}", headers=HR).json()
emp = det.get("employee", det)
record("Employee details unchanged",
       emp["full_name"] == "Test Employee" and emp.get("department") == "Digital Marketing",
       f"{emp['employee_code']} / {emp['full_name']} / {emp.get('department')}")

g = client.post(f"/api/salaries/{sid}/payslip/generate", headers=HR)
record("Payslip PDF generated for new amount", g.status_code == 200, f"HTTP {g.status_code}")
d = client.get(f"/api/salaries/{sid}/payslip/download", headers=HR)
record("Payslip PDF downloadable", d.status_code == 200 and d.headers["content-type"] == "application/pdf",
       f"HTTP {d.status_code}, {len(d.content)} bytes")
if d.status_code == 200:
    open("/tmp/payslip_25500.pdf", "wb").write(d.content)

# ---------------------------------------------------------------- B
print()
print("=" * 74)
print("B. SALARY CREDIT IDEMPOTENCY")
print("=" * 74)

before = counts(sid, TEST_EMP)
print(f"  before credit: notifications={before[0]} salary emails={before[1]}")

c1 = client.post(f"/api/salaries/{sid}/credit", json={"credit_date": f"{PY}-{PM:02d}-28", "attach_payslip": True}, headers=HR)
after1 = counts(sid, TEST_EMP)
print(f"  credit #1 -> HTTP {c1.status_code}; notifications={after1[0]} emails={after1[1]}")
record("First credit succeeds", c1.status_code == 200, f"HTTP {c1.status_code}")
j1 = c1.json() if c1.status_code == 200 else {}
record("First credit sets status Credited", j1.get("salary", {}).get("status") == "Credited",
       str(j1.get("salary", {}).get("status")))
record("First credit reports notification_created=True", j1.get("notification_created") is True,
       str(j1.get("notification_created")))
record("First credit reports email_sent=True", j1.get("email_sent") is True, str(j1.get("email_sent")))
record("First credit raised notification(s)", after1[0] > before[0], f"{before[0]} -> {after1[0]}")
record("First credit logged the salary email", after1[1] == before[1] + 1, f"{before[1]} -> {after1[1]}")

c2 = client.post(f"/api/salaries/{sid}/credit", json={"credit_date": f"{PY}-{PM:02d}-28", "attach_payslip": True}, headers=HR)
after2 = counts(sid, TEST_EMP)
print(f"  credit #2 -> HTTP {c2.status_code}; notifications={after2[0]} emails={after2[1]}")
j2 = c2.json() if c2.status_code == 200 else {}
record("Duplicate credit produced NO extra notification", after2[0] == after1[0], f"{after1[0]} -> {after2[0]}")
record("Duplicate credit produced NO extra email", after2[1] == after1[1], f"{after1[1]} -> {after2[1]}")
record("Duplicate credit reports notification_created=False", j2.get("notification_created") is False,
       str(j2.get("notification_created")))
record("Duplicate credit reports email_sent=False", j2.get("email_sent") is False, str(j2.get("email_sent")))
record("Duplicate credit explains itself to HR", "already credited" in (j2.get("detail") or "").lower(),
       j2.get("detail", ""))
record("Status remains Credited after duplicate", j2.get("salary", {}).get("status") == "Credited",
       str(j2.get("salary", {}).get("status")))

# ---------------------------------------------------------------- C
print()
print("=" * 74)
print("C. DEPARTMENT-SCOPED MEETING VISIBILITY")
print("=" * 74)

MKT = login("employee2@rocketgenie.com", "Rocket@2026")      # Karan Mehta, Marketing
INT = login("intern1@rocketgenie.com", "Rocket@2026")        # Farhan Qureshi, Internship


def dept_set(headers):
    r = client.get("/api/meetings?range=all", headers=headers)
    if r.status_code != 200:
        r = client.get("/api/meetings", headers=headers)
    items = r.json()
    items = items["items"] if isinstance(items, dict) else items
    return {m.get("department") for m in items}, items


mkt_depts, mkt_items = dept_set(MKT)
int_depts, int_items = dept_set(INT)
print(f"  Marketing employee sees departments: {mkt_depts or '{}'} ({len(mkt_items)} meetings)")
print(f"  Internship employee sees departments: {int_depts or '{}'} ({len(int_items)} meetings)")

record("Marketing employee sees only Marketing meetings", mkt_depts <= {"Marketing"}, str(mkt_depts))
record("Internship employee sees only Internship meetings", int_depts <= {"Internship"}, str(int_depts))
record("No cross-department leakage", not (mkt_depts & int_depts) or not mkt_depts or not int_depts,
       "disjoint" if not (mkt_depts & int_depts) else "OVERLAP")

# direct-object access: Marketing employee fetching an Internship meeting by id
with SessionLocal() as db:
    int_meeting = db.execute(
        text("select m.id from meetings m join departments d on d.id=m.department_id where d.name='Internship' limit 1")
    ).scalar()
if int_meeting:
    r = client.get(f"/api/meetings/{int_meeting}", headers=MKT)
    record("No single-meeting read surface exists at all", r.status_code in (403, 404, 405),
           f"HTTP {r.status_code} (405 = no GET-by-id route)")
    r = client.put(f"/api/meetings/{int_meeting}",
                   json={"title": "hijacked", "meeting_date": "2026-09-20", "start_time": "10:00",
                         "google_meet_url": "https://meet.google.com/aaa-bbbb-ccc"}, headers=MKT)
    record("Employee cannot edit another dept's meeting", r.status_code == 403, f"HTTP {r.status_code}")
    r = client.post(f"/api/meetings/{int_meeting}/cancel", headers=MKT)
    record("Employee cannot cancel another dept's meeting", r.status_code == 403, f"HTTP {r.status_code}")

# employees must not be able to create meetings
r = client.post(
    "/api/meetings",
    json={"department_id": 5, "title": "x", "meeting_date": "2026-09-20", "start_time": "10:00",
          "meet_link": "https://meet.google.com/abc-defg-hij"},
    headers=MKT,
)
record("Employee cannot create meetings", r.status_code == 403, f"HTTP {r.status_code}")

# ---------------------------------------------------------------- D
print()
print("=" * 74)
print("D. DOCUMENT SECURITY")
print("=" * 74)

mine = client.get("/api/documents/me", headers=MKT).json()
own = [d for d in mine["items"] if d.get("document_id")]
own_id = own[0]["document_id"]
print(f"  Marketing employee owns document #{own_id} ({own[0].get('document_type')})")

with SessionLocal() as db:
    other_id = db.execute(
        text("select id from employee_documents where employee_id != 4 order by id limit 1")
    ).scalar()
print(f"  Another employee's document: #{other_id}")

r = client.delete(f"/api/documents/{own_id}", headers=MKT)
record("Employee CANNOT delete own submitted document", r.status_code == 403, f"HTTP {r.status_code}")

with SessionLocal() as db:
    still = db.execute(
        text("select count(*) from employee_documents where id=:i"), {"i": own_id}
    ).scalar()
record("Document still present after denied delete", still == 1, f"rows={still}")

r = client.get(f"/api/documents/{other_id}", headers=MKT)
record("No raw document-metadata read surface", r.status_code in (403, 404, 405),
       f"HTTP {r.status_code} (405 = no GET-by-id route)")
r = client.get(f"/api/documents/{other_id}/versions", headers=MKT)
record("Cross-employee version history denied", r.status_code in (403, 404), f"HTTP {r.status_code}")

r = client.get(f"/api/documents/{other_id}/download", headers=MKT)
record("Cross-employee document download denied", r.status_code in (403, 404), f"HTTP {r.status_code}")

r = client.get(f"/api/documents/{own_id}/download", headers=MKT)
record("Own document download allowed", r.status_code == 200, f"HTTP {r.status_code}, {len(r.content)} bytes")

r = client.get(f"/api/documents/{other_id}/download", headers=HR)
record("HR can download any document", r.status_code == 200, f"HTTP {r.status_code}, {len(r.content)} bytes")

r = client.delete(f"/api/documents/{other_id}", headers=HR)
record("Documents are permanent even for HR (403 by design)", r.status_code == 403, f"HTTP {r.status_code}")
with SessionLocal() as db:
    denied = db.execute(
        text("select count(*) from audit_logs where action='document_delete_denied'")
    ).scalar()
record("Denied deletions are audit-logged", denied >= 2, f"{denied} DOCUMENT_DELETE_DENIED entries")

r = client.get("/api/documents/me/download", headers=MKT)
r = client.get("/api/documents/../../etc/passwd", headers=MKT)
record("Path-traversal style document id rejected", r.status_code in (403, 404, 422), f"HTTP {r.status_code}")

r = client.post("/api/documents/{}/verify".format(own_id), json={"remarks": "x"}, headers=MKT)
record("Employee cannot verify own document", r.status_code == 403, f"HTTP {r.status_code}")

r = client.get("/api/audit-logs", headers=MKT)
record("Employee cannot read audit log", r.status_code == 403, f"HTTP {r.status_code}")

# ---------------------------------------------------------------- summary
print()
print("=" * 74)
passed = sum(1 for _, p, _ in results if p)
print(f"RESULT: {passed}/{len(results)} checks passed")
for n, p, d in results:
    if not p:
        print(f"  FAILED: {n} ({d})")
print("=" * 74)
sys.exit(0 if passed == len(results) else 1)
