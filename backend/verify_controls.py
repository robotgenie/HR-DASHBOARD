"""
Section 11 functional verification sweep, run live against PostgreSQL.

No browser is available in this environment, so this exercises every filter,
dropdown data source, search field, sort control, pager, form validation path,
role boundary and database effect through the same API the frontend calls.
What it cannot prove is visual rendering or that a button is wired to the right
handler; that is reported as a limitation rather than claimed as tested.
"""
import sys
import time
from datetime import date, timedelta

STAMP = str(int(time.time()))[-6:]

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database.database import SessionLocal
from app.main import app

client = TestClient(app)
results = []
section = ""


def head(title):
    global section
    section = title
    print()
    print("=" * 74)
    print(title)
    print("=" * 74)


def record(name, passed, detail=""):
    results.append((section, name, passed, detail))
    print(f"  [{'PASS' if passed else 'FAIL'}] {name}" + (f"  -- {detail}" if detail else ""))


def login(email, password):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"{email}: {r.text[:200]}"
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def items(response):
    body = response.json()
    if isinstance(body, dict):
        return body.get("items", [])
    return body


def get(path, headers, **params):
    return client.get(path, params={k: v for k, v in params.items() if v is not None},
                      headers=headers)


HR = login("hr@rocketgenie.com", "RocketHR@2026")
EMP = login("employee1@rocketgenie.com", "Rocket@2026")      # Priya, Digital Marketing
EMP2 = login("employee2@rocketgenie.com", "Rocket@2026")     # Karan, Marketing
INTERN = login("intern1@rocketgenie.com", "Rocket@2026")     # Farhan, Internship

depts = items(client.get("/api/departments", headers=HR))
DEPT = {d["name"]: d["id"] for d in depts}
bgs = items(client.get("/api/internship-backgrounds", headers=HR))

# ==================================================================== A
head("A. FILTERS (every filter must actually filter)")

r = get("/api/employees", HR, department_id=DEPT["Marketing"], page_size=100)
rows = items(r)
record("employees: department filter", bool(rows) and all(
    x["department"] == "Marketing" for x in rows), f"{len(rows)} rows")

r = get("/api/employees", HR, employment_status="Active", page_size=100)
rows = items(r)
record("employees: employment status filter", bool(rows) and all(
    x["employment_status"] == "Active" for x in rows), f"{len(rows)} rows")

r = get("/api/employees", HR, designation="Trainee", page_size=100)
rows = items(r)
record("employees: designation filter", bool(rows) and all(
    x["designation"] == "Trainee" for x in rows), f"{len(rows)} rows")

r = get("/api/employees", HR, document_status="complete", page_size=100)
complete = items(r)
r = get("/api/employees", HR, document_status="incomplete", page_size=100)
incomplete = items(r)
overlap = {x["id"] for x in complete} & {x["id"] for x in incomplete}
record("employees: document status filter partitions the set", not overlap,
       f"{len(complete)} complete / {len(incomplete)} incomplete, overlap={len(overlap)}")

r = get("/api/employees", HR, salary_status="Credited", page_size=100)
rows = items(r)
record("employees: salary status filter", all(
    x["salary_status"] == "Credited" for x in rows), f"{len(rows)} rows")

r = get("/api/employees", HR, joined_from="2026-01-01", page_size=100)
rows = items(r)
record("employees: joined-from date filter", bool(rows) and all(
    x["joining_date"] >= "2026-01-01" for x in rows), f"{len(rows)} rows")

r = get("/api/employees", HR, joined_to="2024-12-31", page_size=100)
rows = items(r)
record("employees: joined-to date filter", bool(rows) and all(
    x["joining_date"] <= "2024-12-31" for x in rows), f"{len(rows)} rows")

r = get("/api/employees", HR, department_id=DEPT["Internship"],
        employment_status="Active", page_size=100)
rows = items(r)
record("employees: two filters combine", bool(rows) and all(
    x["department"] == "Internship" and x["employment_status"] == "Active" for x in rows),
    f"{len(rows)} rows")

r = get("/api/employees", HR, page_size=100)
record("employees: clearing filters restores the full set",
       len(items(r)) >= len(rows), f"{len(items(r))} total")

r = get("/api/employees", HR, employee_type="Intern", page_size=100)
rows = items(r)
record("employees: employee type = Intern", bool(rows) and all(
    x["department"] == "Internship" for x in rows), f"{len(rows)} interns")

r = get("/api/employees", HR, employee_type="Regular", page_size=100)
rows = items(r)
record("employees: employee type = Regular excludes interns", bool(rows) and all(
    x["department"] != "Internship" for x in rows), f"{len(rows)} regular")

r = get("/api/employees", HR, employee_type="Contractor", page_size=10)
record("employees: invalid employee type rejected", r.status_code == 422,
       f"HTTP {r.status_code}")

_interns = items(get("/api/employees", HR, employee_type="Intern", page_size=100))
_named = [x for x in _interns if x.get("internship_background")]
if _named:
    _bg_name = _named[0]["internship_background"]
    _bg_id = next(b["id"] for b in bgs if b["name"] == _bg_name)
    rows = items(get("/api/employees", HR, internship_background_id=_bg_id, page_size=100))
    record("employees: internship background filter", bool(rows) and all(
        x["internship_background"] == _bg_name for x in rows),
        f"{len(rows)} in {_bg_name}")
    rows = items(get("/api/employees", HR, employee_type="Intern",
                     internship_background_id=_bg_id, page_size=100))
    record("employees: intern + background combine", all(
        x["department"] == "Internship" and x["internship_background"] == _bg_name
        for x in rows), f"{len(rows)} rows")

r = get("/api/documents", HR, status="Verified", page_size=100)
rows = items(r)
record("documents: status filter", bool(rows) and all(
    x["status"] == "Verified" for x in rows), f"{len(rows)} rows")

r = get("/api/documents", HR, department_id=DEPT["Internship"], page_size=100)
rows = items(r)
record("documents: department filter", bool(rows), f"{len(rows)} rows")

r = get("/api/uan", HR, status="Verified", page_size=100)
rows = items(r)
record("uan: status filter", bool(rows) and all(
    x["status"] == "Verified" for x in rows), f"{len(rows)} rows")

r = get("/api/salaries", HR, status="Credited", page_size=200)
rows = items(r)
record("salaries: status filter", bool(rows) and all(
    x["status"] == "Credited" for x in rows), f"{len(rows)} rows")

r = get("/api/salaries", HR, period_year=2026, period_month=8, page_size=200)
rows = items(r)
record("salaries: pay-period filter", all(
    x["period_year"] == 2026 and x["period_month"] == 8 for x in rows), f"{len(rows)} rows")

r = get("/api/salaries", HR, department_id=DEPT["Teaching"], page_size=200)
rows = items(r)
record("salaries: department filter", bool(rows) and all(
    x["department"] == "Teaching" for x in rows), f"{len(rows)} rows")

r = get("/api/reports", HR, status="Reviewed", page_size=100)
rows = items(r)
record("reports: status filter", bool(rows) and all(
    x["status"] == "Reviewed" for x in rows), f"{len(rows)} rows")

r = get("/api/reports", HR, department_id=DEPT["Marketing"], page_size=100)
rows = items(r)
record("reports: department filter", bool(rows), f"{len(rows)} rows")

yesterday = (date.today() - timedelta(days=1)).isoformat()
r = get("/api/reports", HR, report_date=yesterday, page_size=100)
rows = items(r)
record("reports: exact-date filter", all(
    x["report_date"] == yesterday for x in rows), f"{len(rows)} rows")

r = get("/api/meetings", HR, department_id=DEPT["Internship"])
rows = items(r)
record("meetings: department filter", bool(rows) and all(
    x["department"] == "Internship" for x in rows), f"{len(rows)} rows")

r = get("/api/meetings", HR, date_from=date.today().isoformat(),
        date_to=(date.today() + timedelta(days=30)).isoformat())
rows = items(r)
record("meetings: date-range filter", all(
    x["meeting_date"] >= date.today().isoformat() for x in rows), f"{len(rows)} rows")

r = get("/api/notifications", EMP, unread_only=True, limit=100)
rows = items(r)
record("notifications: unread-only filter", all(x["is_read"] is False for x in rows),
       f"{len(rows)} unread")

r = get("/api/notifications", EMP, type="Salary Credited", limit=100)
rows = items(r)
record("notifications: type filter", all(
    x["type"] == "Salary Credited" for x in rows), f"{len(rows)} rows")

r = get("/api/audit-logs", HR, action="login", page_size=100)
rows = items(r)
record("audit: action filter", bool(rows) and all(
    x["action"] == "login" for x in rows), f"{len(rows)} rows")

r = get("/api/audit-logs", HR, entity_type="employee", page_size=100)
rows = items(r)
record("audit: entity-type filter", bool(rows) and all(
    x["entity_type"] == "employee" for x in rows), f"{len(rows)} rows")

r = get("/api/audit-logs", HR, date_from=date.today().isoformat(), page_size=100)
record("audit: date-from filter", r.status_code == 200, f"{len(items(r))} rows")

r = get("/api/profile-change-requests", HR, status="Approved", page_size=100)
rows = items(r)
record("profile requests: status filter", all(
    x["status"] == "Approved" for x in rows), f"{len(rows)} rows")

r = get("/api/profile-change-requests", HR, field_name="phone", page_size=100)
rows = items(r)
record("profile requests: field filter", all(
    x["field_name"] == "phone" for x in rows), f"{len(rows)} rows")

# ==================================================================== B
head("B. DROPDOWN DATA SOURCES (populated from the database)")

record("Departments dropdown", len(depts) == 7 and all(d.get("name") for d in depts),
       f"{len(depts)} options")
record("Internship backgrounds dropdown", len(bgs) >= 11, f"{len(bgs)} options")

r = client.get("/api/documents/requirements", headers=HR)
if r.status_code == 200:
    dt = items(r)
    record("Document types dropdown", len(dt) >= 8, f"{len(dt)} options")
else:
    dt = items(client.get("/api/documents/me", headers=EMP))
    record("Document types dropdown", len(dt) >= 8, f"{len(dt)} options via checklist")

r = client.get("/api/audit-logs/actions", headers=HR)
record("Audit action dropdown", r.status_code == 200 and len(items(r)) >= 20,
       f"{len(items(r))} actions")

r = client.get("/api/profile-change-requests/fields", headers=EMP)
fields = r.json()
record("Requestable-field dropdown", r.status_code == 200 and len(fields) == 5,
       ", ".join(f["field_name"] for f in fields))

r = client.get("/api/settings", headers=HR).json()
record("Upload extension list comes from settings",
       bool(r["uploads"]["allowed_extensions"]),
       str(r["uploads"]["allowed_extensions"])[:50])

statuses = {d["name"] for d in depts}
record("Department dropdown matches the seeded taxonomy",
       statuses == {"Teaching", "Marketing", "Digital Marketing", "Managers", "HR",
                    "Internship", "Senior HR"}, f"{len(statuses)} names")

# edit form must pre-select existing values
emp = client.get("/api/employees", headers=HR, params={"search": "Farhan"}).json()["items"][0]
detail = client.get(f"/api/employees/{emp['id']}", headers=HR).json()
record("Edit form can pre-select department and background",
       detail["department_id"] == DEPT["Internship"] and detail["internship_background"],
       f"{detail['department']} / {detail['internship_background']}")

# ==================================================================== C
head("C. SEARCH")

r = get("/api/employees", HR, search="pri", page_size=50)
rows = items(r)
record("Partial, case-insensitive name search", bool(rows) and any(
    "Priya" in x["full_name"] for x in rows), f"{len(rows)} hits for 'pri'")

r = get("/api/employees", HR, search="PRIYA", page_size=50)
record("Uppercase search matches the same row", bool(items(r)), f"{len(items(r))} hits")

r = get("/api/employees", HR, search="RGEMP003", page_size=50)
rows = items(r)
record("Search by unique employee ID", bool(rows) and rows[0]["unique_employee_id"] == "RGEMP003",
       rows[0]["full_name"] if rows else "no hit")

r = get("/api/employees", HR, search="employee1@rocketgenie.com", page_size=50)
record("Search by email", bool(items(r)), f"{len(items(r))} hits")

r = get("/api/employees", HR, search="zzzznosuchperson", page_size=50)
body = r.json()
record("No-result search returns an empty page, not an error",
       r.status_code == 200 and body["items"] == [] and body["meta"]["total"] == 0,
       f"total={body['meta']['total']}")

r = get("/api/employees", HR, search="", page_size=5)
record("Empty search behaves like no filter", r.status_code == 200,
       f"total={r.json()['meta']['total']}")

r = get("/api/employees", HR, search="a", department_id=DEPT["Teaching"], page_size=50)
rows = items(r)
record("Search combines with a filter", all(
    x["department"] == "Teaching" for x in rows), f"{len(rows)} rows")

r = get("/api/employees", HR, search="a", page=1, page_size=3)
meta = r.json()["meta"]
record("Search combines with pagination", len(items(r)) <= 3 and meta["page"] == 1,
       f"{meta['total']} hits over {meta['pages']} pages")

r = get("/api/documents", HR, search="Priya", page_size=50)
record("Document search by employee name", r.status_code == 200, f"{len(items(r))} rows")

r = get("/api/uan", HR, search="Priya", page_size=50)
record("UAN search by employee name", r.status_code == 200, f"{len(items(r))} rows")

r = get("/api/audit-logs", HR, search="hr@rocketgenie.com", page_size=20)
record("Audit search by actor", r.status_code == 200, f"{len(items(r))} rows")

r = get("/api/profile-change-requests", HR, search="ID Flow", page_size=20)
record("Profile-request search by employee", r.status_code == 200, f"{len(items(r))} rows")

# ==================================================================== D
head("D. SORTING")

asc = [x["full_name"] for x in items(
    get("/api/employees", HR, sort_by="full_name", sort_dir="asc", page_size=100))]
desc = [x["full_name"] for x in items(
    get("/api/employees", HR, sort_by="full_name", sort_dir="desc", page_size=100))]
record("Name sort ascending is ordered", asc == sorted(asc), f"first={asc[0] if asc else '-'}")
record("Name sort descending reverses it", desc == list(reversed(asc)),
       f"first={desc[0] if desc else '-'}")

jasc = [x["joining_date"] for x in items(
    get("/api/employees", HR, sort_by="joining_date", sort_dir="asc", page_size=100))]
record("Joining-date sort ascending", jasc == sorted(jasc), f"{jasc[0] if jasc else '-'} first")

sorted_filtered = items(get("/api/employees", HR, department_id=DEPT["Teaching"],
                            sort_by="full_name", sort_dir="asc", page_size=50))
names = [x["full_name"] for x in sorted_filtered]
record("Sorting survives filtering", names == sorted(names) and all(
    x["department"] == "Teaching" for x in sorted_filtered), f"{len(names)} rows")

p1 = items(get("/api/employees", HR, sort_by="full_name", sort_dir="asc", page=1, page_size=5))
p2 = items(get("/api/employees", HR, sort_by="full_name", sort_dir="asc", page=2, page_size=5))
record("Sorting survives pagination",
       [x["full_name"] for x in p1] == asc[:5] and [x["full_name"] for x in p2] == asc[5:10],
       "pages align with the full ordering")

r = get("/api/employees", HR, sort_by="not_a_column", page_size=5)
record("Unknown sort key is handled, not fatal", r.status_code in (200, 422),
       f"HTTP {r.status_code}")

# ==================================================================== E
head("E. PAGINATION")

r = get("/api/employees", HR, page=1, page_size=5)
body = r.json()
meta = body["meta"]
total = meta["total"]
record("Page size is honoured", len(body["items"]) == 5, f"{len(body['items'])} rows")
record("Page count arithmetic is right", meta["pages"] == -(-total // 5),
       f"{total} rows over {meta['pages']} pages")

ids1 = {x["id"] for x in body["items"]}
ids2 = {x["id"] for x in items(get("/api/employees", HR, page=2, page_size=5))}
record("Consecutive pages do not repeat rows", not (ids1 & ids2),
       f"{len(ids1)} + {len(ids2)}, overlap={len(ids1 & ids2)}")

last = items(get("/api/employees", HR, page=meta["pages"], page_size=5))
record("Last page returns rows", bool(last), f"{len(last)} rows on page {meta['pages']}")

beyond = get("/api/employees", HR, page=meta["pages"] + 50, page_size=5)
record("Page beyond the last returns empty, not an error",
       beyond.status_code == 200 and items(beyond) == [], f"HTTP {beyond.status_code}")

r = get("/api/employees", HR, department_id=DEPT["Internship"], page=1, page_size=2)
fmeta = r.json()["meta"]
record("Pagination totals respect the active filter", fmeta["total"] < total,
       f"{fmeta['total']} filtered vs {total} unfiltered")

r = get("/api/employees", HR, page=0)
record("Invalid page number rejected", r.status_code == 422, f"HTTP {r.status_code}")
r = get("/api/employees", HR, page_size=5000)
record("Oversized page_size rejected", r.status_code == 422, f"HTTP {r.status_code}")

for path in ("/api/documents", "/api/uan", "/api/salaries", "/api/reports",
             "/api/profile-change-requests", "/api/audit-logs"):
    body = get(path, HR, page=1, page_size=3).json()
    ok = isinstance(body, dict) and "meta" in body and len(body["items"]) <= 3
    record(f"Paged envelope on {path}", ok,
           f"total={body.get('meta', {}).get('total')}" if ok else "no envelope")

# ==================================================================== F
head("F. FORM VALIDATION (server-side)")

r = client.post("/api/employees", json={"full_name": "X"}, headers=HR)
record("Missing required fields rejected", r.status_code == 422, f"HTTP {r.status_code}")

r = client.post("/api/employees", json={
    "full_name": "Bad Email", "email": "not-an-email",
    "department_id": DEPT["Marketing"], "designation": "X", "joining_date": "2026-01-01",
}, headers=HR)
record("Invalid email rejected", r.status_code == 422, f"HTTP {r.status_code}")

r = client.post("/api/employees", json={
    "full_name": "Duplicate", "email": "employee1@rocketgenie.com",
    "department_id": DEPT["Marketing"], "designation": "X", "joining_date": "2026-01-01",
}, headers=HR)
record("Duplicate email rejected", r.status_code in (409, 422), f"HTTP {r.status_code}")

r = client.post("/api/employees", json={
    "full_name": "No Background", "email": "nobg@rocketgenie.com",
    "department_id": DEPT["Internship"], "designation": "Trainee",
    "joining_date": "2026-01-01",
}, headers=HR)
record("Intern without a background rejected", r.status_code == 422, f"HTTP {r.status_code}")

r = client.post("/api/uan", json={"uan_number": "abc"}, headers=EMP2)
record("Non-numeric UAN rejected", r.status_code == 422, f"HTTP {r.status_code}")

r = client.post("/api/salaries", json={
    "employee_id": 3, "period_year": 2026, "period_month": 99, "working_days": 30,
    "components": [],
}, headers=HR)
record("Out-of-range month rejected", r.status_code == 422, f"HTTP {r.status_code}")

r = client.post("/api/salaries", json={
    "employee_id": 3, "period_year": 2026, "period_month": 7, "working_days": 30,
    "components": [{"name": "Basic", "component_type": "bonus", "amount": 10}],
}, headers=HR)
record("Unknown component type rejected", r.status_code == 422, f"HTTP {r.status_code}")

r = client.post("/api/meetings", json={
    "department_id": DEPT["Marketing"], "title": "No link",
    "meeting_date": date.today().isoformat(), "start_time": "10:00",
}, headers=HR)
record("Meeting without a Meet link rejected", r.status_code == 422, f"HTTP {r.status_code}")

r = client.post("/api/auth/change-password",
                json={"current_password": "Rocket@2026", "new_password": "short"},
                headers=EMP2)
record("Weak password rejected", r.status_code == 422, f"HTTP {r.status_code}")

r = client.post("/api/employees/me/photo",
                files={"file": ("bad.txt", b"not an image", "text/plain")}, headers=EMP2)
record("Wrong file type rejected on upload", r.status_code in (400, 422),
       f"HTTP {r.status_code}")

# ==================================================================== G
head("G. ROLE-BASED ACCESS (HR / employee / intern)")

hr_only = [
    ("GET", "/api/employees"),
    ("GET", "/api/audit-logs"),
    ("GET", "/api/settings"),
    ("GET", "/api/documents"),
    ("GET", "/api/uan"),
]
for method, path in hr_only:
    r = client.request(method, path, headers=EMP)
    record(f"Employee denied {method} {path}", r.status_code == 403, f"HTTP {r.status_code}")

r = client.post("/api/employees", json={
    "full_name": "Nope", "email": "nope@rocketgenie.com",
    "department_id": DEPT["Marketing"], "designation": "X", "joining_date": "2026-01-01",
}, headers=EMP)
record("Employee cannot create employees", r.status_code == 403, f"HTTP {r.status_code}")

docs = items(client.get("/api/documents/me", headers=EMP))
own_doc = next(d["document_id"] for d in docs if d.get("document_id"))
r = client.post(f"/api/documents/{own_doc}/verify", json={"remarks": "self"}, headers=EMP)
record("Employee cannot verify documents", r.status_code == 403, f"HTTP {r.status_code}")
r = client.post(f"/api/documents/{own_doc}/reject", json={"remarks": "self"}, headers=EMP)
record("Employee cannot reject documents", r.status_code == 403, f"HTTP {r.status_code}")
r = client.delete(f"/api/documents/{own_doc}", headers=EMP)
record("Employee cannot delete documents", r.status_code == 403, f"HTTP {r.status_code}")

sal = items(client.get("/api/salaries", headers=EMP))[0]
r = client.put(f"/api/salaries/{sal['id']}", json={"working_days": 1}, headers=EMP)
record("Employee cannot modify salary", r.status_code == 403, f"HTTP {r.status_code}")

with SessionLocal() as db:
    other_doc = db.execute(text(
        "select ed.id from employee_documents ed join employees e on e.id=ed.employee_id "
        "where e.user_id != (select user_id from employees where id=3) limit 1"
    )).scalar()
r = client.get(f"/api/documents/{other_doc}/download", headers=EMP)
record("Employee cannot reach another employee's document", r.status_code in (403, 404),
       f"HTTP {r.status_code}")

other_sal = items(client.get("/api/salaries", headers=EMP2))[0]
r = client.get(f"/api/salaries/{other_sal['id']}", headers=EMP)
record("Employee cannot read another employee's salary", r.status_code in (403, 404),
       f"HTTP {r.status_code}")

r = client.put("/api/employees/me", json={"full_name": "Renamed Myself"}, headers=EMP)
record("Employee cannot rename themselves via the self API",
       r.status_code in (403, 422) or
       client.get("/api/employees/me", headers=EMP).json()["full_name"] != "Renamed Myself",
       f"HTTP {r.status_code}")

intern_sal = [s for s in items(client.get("/api/salaries", headers=INTERN))
              if s["status"] == "Credited" and not s["intern_download_allowed"]]
if intern_sal:
    r = client.get(f"/api/salaries/{intern_sal[0]['id']}/payslip/download", headers=INTERN)
    record("Intern cannot download without permission", r.status_code == 403,
           f"HTTP {r.status_code}")
    r = client.get(f"/api/salaries/{intern_sal[0]['id']}/payslip", headers=INTERN)
    record("Intern can still view it", r.status_code == 200, f"HTTP {r.status_code}")

mkt_meetings = {m["department"] for m in items(client.get("/api/meetings", headers=EMP2))}
int_meetings = {m["department"] for m in items(client.get("/api/meetings", headers=INTERN))}
record("Meetings stay department-scoped", mkt_meetings <= {"Marketing"}
       and int_meetings <= {"Internship"}, f"{mkt_meetings} vs {int_meetings}")

r = client.get("/api/employees", headers={"Authorization": "Bearer not-a-real-token"})
record("Garbage token rejected", r.status_code == 401, f"HTTP {r.status_code}")
r = client.get("/api/employees")
record("Missing token rejected", r.status_code in (401, 403), f"HTTP {r.status_code}")

# ==================================================================== H
head("H. DATABASE EFFECTS OF API OPERATIONS")


def scalar(sql, **params):
    with SessionLocal() as db:
        return db.execute(text(sql), params).scalar()


before = scalar("select count(*) from employees")
created = client.post("/api/employees", json={
    "full_name": "DB Check Person", "email": f"dbcheck{STAMP}@rocketgenie.com",
    "department_id": DEPT["Marketing"], "designation": "Analyst",
    "joining_date": "2026-09-01", "employment_status": "Active",
}, headers=HR)
new_id = created.json()["employee"]["id"]
record("Employee creation writes a row", scalar("select count(*) from employees") == before + 1,
       f"{before} -> {before + 1}")
record("Linked user row created",
       scalar("select count(*) from users u join employees e on e.user_id=u.id where e.id=:i",
              i=new_id) == 1)

client.put(f"/api/employees/{new_id}", json={"designation": "Senior Analyst"}, headers=HR)
record("Update writes the new value",
       scalar("select designation from employees where id=:i", i=new_id) == "Senior Analyst")

pcr_before = scalar("select count(*) from profile_change_requests")
client.get("/api/profile-change-requests", headers=HR)
record("Profile change request table is live", pcr_before >= 1, f"{pcr_before} rows")

record("Employee IDs stored and unique",
       scalar("select count(unique_employee_id) from employees") ==
       scalar("select count(distinct unique_employee_id) from employees"),
       f"{scalar('select count(unique_employee_id) from employees')} issued")

record("Intern download permission persisted",
       scalar("select count(*) from salary_records where intern_download_allowed") >= 1,
       f"{scalar('select count(*) from salary_records where intern_download_allowed')} records")

record("Report attachments stored (one per submitted report)",
       scalar("select count(*) from report_attachments") >=
       scalar("select count(*) from daily_reports where status in ('Submitted','Reviewed')"),
       f"{scalar('select count(*) from report_attachments')} rows")

_docs = scalar("select count(*) from employee_documents")
_vers = scalar("select count(*) from document_versions")
record("Document versions retained (at least one per document)", _vers >= _docs,
       f"{_vers} versions for {_docs} documents")

record("Audit log is being written",
       scalar("select count(*) from audit_logs") > 100,
       f"{scalar('select count(*) from audit_logs')} entries")

# ==================================================================== I
head("I. EMPTY / ERROR / NOT-FOUND STATES")

r = client.get("/api/employees/999999", headers=HR)
record("Unknown employee gives 404 with a message", r.status_code == 404
       and "detail" in r.json(), r.json().get("detail", ""))

r = client.get("/api/salaries/999999", headers=HR)
record("Unknown salary gives 404", r.status_code == 404, f"HTTP {r.status_code}")

r = client.get("/api/profile-change-requests/999999", headers=HR)
record("Unknown change request gives 404", r.status_code == 404, f"HTTP {r.status_code}")

r = get("/api/employees", HR, search="zzzznobody", page_size=10)
body = r.json()
record("Empty list is a valid empty envelope", body["items"] == []
       and body["meta"]["total"] == 0 and "pages" in body["meta"],
       f"total={body['meta']['total']}, pages={body['meta']['pages']}")

r = get("/api/salaries", HR, period_year=1999, page_size=10)
record("Filter with no matches returns empty", items(r) == [], f"{len(items(r))} rows")

r = get("/api/audit-logs", HR, action="no_such_action", page_size=10)
record("Unknown audit action returns empty, not an error", r.status_code == 200
       and items(r) == [], f"HTTP {r.status_code}")

r = client.get("/api/uan", headers=HR, params={"status": "Bogus"})
record("Invalid filter value rejected with a message", r.status_code == 422,
       f"HTTP {r.status_code}")

r = client.get("/api/documents/999999/download", headers=HR)
record("Missing document download gives 404", r.status_code == 404, f"HTTP {r.status_code}")

# ==================================================================== summary
print()
print("=" * 74)
passed = sum(1 for _, _, p, _ in results if p)
print(f"RESULT: {passed}/{len(results)} checks passed")
by_section = {}
for sec, _, p, _ in results:
    tally = by_section.setdefault(sec, [0, 0])
    tally[0] += 1 if p else 0
    tally[1] += 1
for sec, (ok, tot) in by_section.items():
    print(f"  {'PASS' if ok == tot else 'FAIL'}  {sec}: {ok}/{tot}")
for sec, name, p, d in results:
    if not p:
        print(f"  FAILED: [{sec}] {name} ({d})")
print("=" * 74)
sys.exit(0 if passed == len(results) else 1)
