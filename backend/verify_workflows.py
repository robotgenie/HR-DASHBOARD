"""
Full workflow walkthroughs against the live PostgreSQL database.

  HR journey:       login -> dashboard -> hire -> review document -> verify UAN
                    -> run payroll -> generate payslip -> credit -> schedule
                    meeting -> read work report -> audit trail -> settings
  Employee journey: first login -> forced password change -> dashboard ->
                    upload document -> re-upload after rejection -> submit UAN
                    -> see own meeting -> file daily report -> logout gate
                    -> notifications
"""
import sys
import time
from datetime import date

TODAY = date.today().isoformat()

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
results = []
step = 0


def record(name, passed, detail=""):
    global step
    step += 1
    results.append((name, passed, detail))
    print(f"  {step:>2}. [{'PASS' if passed else 'FAIL'}] {name}" + (f"  -- {detail}" if detail else ""))


def auth(email, password):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    return r


def hdr(token):
    return {"Authorization": f"Bearer {token}"}


PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)

stamp = str(int(time.time()))[-6:]

print("=" * 74)
print("HR WORKFLOW")
print("=" * 74)

r = auth("hr@rocketgenie.com", "RocketHR@2026")
record("HR logs in", r.status_code == 200, f"home={r.json().get('home')}")
HR = hdr(r.json()["access_token"])
record("HR is routed to the HR dashboard", r.json()["home"] == "/hr/dashboard.html")

d = client.get("/api/dashboard/hr", headers=HR)
k = d.json()["kpis"]
record("HR dashboard returns KPIs + charts", d.status_code == 200 and len(k) >= 9,
       f"{len(k)} KPIs, {len(d.json()['charts'])} charts, {k['total_employees']} employees")

depts = client.get("/api/departments", headers=HR).json()
bgs = client.get("/api/internship-backgrounds", headers=HR).json()
depts = depts["items"] if isinstance(depts, dict) else depts
bgs = bgs["items"] if isinstance(bgs, dict) else bgs
record("Departments and internship backgrounds come from the database",
       len(depts) >= 7 and len(bgs) >= 3, f"{len(depts)} departments, {len(bgs)} backgrounds")

intern_dept = next(x["id"] for x in depts if x["name"] == "Internship")
cyber_bg = next(x["id"] for x in bgs if "Cyber" in x["name"])

new_emp = {
    "full_name": "Walkthrough Candidate",
    "email": f"walkthrough{stamp}@rocketgenie.com",
    "phone": "9876500000",
    "department_id": intern_dept,
    "internship_background_id": cyber_bg,
    "designation": "Cyber Security Intern",
    "joining_date": "2026-09-01",
    "employment_status": "Active",
}
r = client.post("/api/employees", json=new_emp, headers=HR)
record("HR hires an employee", r.status_code in (200, 201), f"HTTP {r.status_code}")
created = r.json()
NEW_ID = created["employee"]["id"]
INIT_PW = created["initial_password"]
record("Initial credentials are returned to HR once", bool(INIT_PW), f"code={created['employee']['employee_code']}")
record("Account email dispatched (console fallback when SMTP is unset)",
       "account_email_sent" in created, str(created["account_email_sent"]))
record("Internship hire stores its background", created["employee"].get("internship_background") is not None,
       str(created["employee"].get("internship_background")))

lst = client.get(f"/api/employees?search=Walkthrough&page_size=5", headers=HR).json()
record("New hire appears in the searchable directory",
       any(x["id"] == NEW_ID for x in lst["items"]), f"{lst['meta']['total']} match")

print()
print("=" * 74)
print("EMPLOYEE WORKFLOW")
print("=" * 74)

r = auth(new_emp["email"], INIT_PW)
record("New employee logs in with issued credentials", r.status_code == 200, f"HTTP {r.status_code}")
record("Employee is forced to change the temporary password", r.json()["must_change_password"] is True)
EMP = hdr(r.json()["access_token"])

NEW_PW = "Walkthrough@2026"
r = client.post("/api/auth/change-password",
                json={"current_password": INIT_PW, "new_password": NEW_PW}, headers=EMP)
record("Employee changes password", r.status_code == 200, f"HTTP {r.status_code}")
r = auth(new_emp["email"], NEW_PW)
record("Re-login with new password clears the change flag", r.json()["must_change_password"] is False)
EMP = hdr(r.json()["access_token"])
record("Old password no longer works", auth(new_emp["email"], INIT_PW).status_code == 401)

d = client.get("/api/dashboard/employee", headers=EMP).json()
record("Employee dashboard is personalised", d["employee"]["full_name"] == "Walkthrough Candidate",
       f"profile {d['kpis']['profile_completion']}%, docs {d['kpis']['documents_label']}")

docs = client.get("/api/documents/me", headers=EMP).json()
photo_type = next(x["document_type_id"] for x in docs["items"] if x["code"] == "PHOTO")
record("Employee sees the full document checklist",
       len(docs["items"]) >= 7 and docs["completion"]["uploaded"] == 0,
       f"{len(docs['items'])} types, {docs['completion']['percent']}% complete")

r = client.post("/api/documents/upload",
                data={"document_type_id": str(photo_type)},
                files={"file": ("photo.png", PNG, "image/png")}, headers=EMP)
record("Employee uploads a document", r.status_code in (200, 201), f"HTTP {r.status_code}")
DOC_ID = r.json()["document_id"]

docs = client.get("/api/documents/me", headers=EMP).json()
photo = next(x for x in docs["items"] if x["code"] == "PHOTO")
record("Uploaded document shows as Pending and lifts completion",
       photo["status"] == "Pending" and docs["completion"]["uploaded"] == 1,
       f"{photo['status']}, {docs['completion']['percent']}%")

r = client.delete(f"/api/documents/{DOC_ID}", headers=EMP)
record("Employee still cannot delete what they submitted", r.status_code == 403, f"HTTP {r.status_code}")

r = client.post(f"/api/documents/{DOC_ID}/reject", json={"remarks": "Photo is too dark, please re-upload."},
                headers=HR)
record("HR rejects the document with remarks", r.status_code == 200, f"HTTP {r.status_code}")

r = client.post("/api/documents/upload",
                data={"document_type_id": str(photo_type)},
                files={"file": ("photo-v2.png", PNG, "image/png")}, headers=EMP)
record("Employee re-uploads a corrected copy", r.status_code in (200, 201), f"HTTP {r.status_code}")

v = client.get(f"/api/documents/{DOC_ID}/versions", headers=EMP).json()
versions = v["items"] if isinstance(v, dict) else v
record("Both versions are retained (nothing overwritten)", len(versions) == 2,
       f"v{versions[0]['version_no']} + v{versions[1]['version_no']}")

r = client.post(f"/api/documents/{DOC_ID}/verify", json={"remarks": "Clear copy, approved."}, headers=HR)
record("HR verifies the new version", r.status_code == 200, f"HTTP {r.status_code}")

r = client.post("/api/uan", json={"uan_number": "100200300400"}, headers=EMP)
record("Employee submits a 12-digit UAN", r.status_code in (200, 201), f"HTTP {r.status_code}")
UAN_ID = r.json()["id"]
r = client.post("/api/uan", json={"uan_number": "12345"}, headers=EMP)
record("Malformed UAN rejected by the server", r.status_code == 422, f"HTTP {r.status_code}")
r = client.post(f"/api/uan/{UAN_ID}/verify", json={"remarks": "Matches EPFO records."}, headers=HR)
record("HR verifies the UAN", r.status_code == 200, f"status={r.json().get('status')}")

r = client.post("/api/meetings", json={
    "department_id": intern_dept,
    "title": "Intern Daily Standup",
    "meeting_date": TODAY,
    "start_time": "09:30",
    "end_time": "09:50",
    "agenda": "Blockers and today's learning goals.",
    "google_meet_url": "https://meet.google.com/wlk-thru-001",
}, headers=HR)
record("HR schedules a department meeting with a real Meet link",
       r.status_code in (200, 201), f"HTTP {r.status_code}")
MEET_ID = r.json()["id"]

today = client.get("/api/meetings/today", headers=EMP).json()
today = today["items"] if isinstance(today, dict) else today
record("Employee sees today's meeting with its join link",
       any(m["id"] == MEET_ID and m["google_meet_url"] for m in today), f"{len(today)} today")

# An EOD report now needs evidence: save a draft, attach, then submit.
draft = client.post("/api/reports", json={
    "report_date": TODAY,
    "tasks_completed": "Completed the onboarding security module.",
    "work_summary": "First day: environment setup and orientation.",
    "submit": False,
}, headers=EMP)
record("Draft saves without an attachment", draft.status_code in (200, 201),
       f"status={draft.json().get('status')}")
REP_ID = draft.json()["id"]

blocked = client.post("/api/reports", json={
    "report_date": TODAY,
    "tasks_completed": "Completed the onboarding security module.",
    "work_summary": "First day: environment setup and orientation.",
    "submit": True,
}, headers=EMP)
record("Submit blocked without an attachment", blocked.status_code == 422,
       blocked.json().get("detail", ""))

att = client.post(f"/api/reports/{REP_ID}/attachments",
                  files={"file": ("screenshot.png", PNG, "image/png")}, headers=EMP)
record("Report accepts a screenshot attachment", att.status_code in (200, 201),
       f"HTTP {att.status_code}")

r = client.post("/api/reports", json={
    "report_date": TODAY,
    "tasks_completed": "Completed the onboarding security module.",
    "tasks_in_progress": "Setting up the lab VM.",
    "tasks_pending": "Read the incident response playbook.",
    "work_summary": "First day: environment setup and orientation.",
    "challenges": "VPN client needed a manual proxy setting.",
    "additional_comments": "Mentor assigned.",
    "submit": True,
}, headers=EMP)
record("Submit succeeds once an attachment exists", r.status_code in (200, 201),
       f"status={r.json().get('status')}")

lc = client.get("/api/reports/logout-check", headers=EMP).json()
record("Logout gate reports today's submission", lc.get("report_submitted_today") is True,
       f"mandatory={lc.get('report_mandatory')} blocked={lc.get('logout_blocked')}")

rr = client.get(
    f"/api/reports?employee_id={NEW_ID}&page_size=25", headers=HR
).json()
record("HR can read the submitted report", any(x["id"] == REP_ID for x in rr["items"]),
       f"{rr['meta']['total']} for this employee")
r = client.post(f"/api/reports/{REP_ID}/review", json={"review_notes": "Good first day."}, headers=HR)
record("HR marks the report reviewed", r.status_code == 200 and r.json()["status"] == "Reviewed",
       str(r.json().get("status")))

print()
print("=" * 74)
print("PAYROLL + NOTIFICATIONS")
print("=" * 74)

r = client.post("/api/salaries", json={
    "employee_id": NEW_ID, "period_month": 9, "period_year": 2026, "working_days": 22,
    "components": [
        {"name": "Basic Salary", "component_type": "earning", "amount": 9000},
        {"name": "House Rent Allowance", "component_type": "earning", "amount": 4500},
        {"name": "Travelling Allowance", "component_type": "earning", "amount": 1500},
        {"name": "Provident Fund", "component_type": "deduction", "amount": 780},
    ],
}, headers=HR)
sal = r.json()
record("HR runs payroll with flexible components", r.status_code in (200, 201),
       f"earnings={sal.get('total_earnings')} deductions={sal.get('total_deductions')} net={sal.get('net_pay')}")
record("Server computes the net pay itself", float(sal["net_pay"]) == 14220.0, str(sal["net_pay"]))
record("Amount in words generated in Indian format",
       sal["amount_in_words"].strip().lower() == "fourteen thousand two hundred twenty only",
       sal["amount_in_words"])
SAL_ID = sal["id"]

record("Payslip PDF generated",
       client.post(f"/api/salaries/{SAL_ID}/payslip/generate", headers=HR).status_code == 200)
before = client.get("/api/notifications", headers=EMP).json()["unread_count"]
r = client.post(f"/api/salaries/{SAL_ID}/credit", json={"credit_date": "2026-09-30"}, headers=HR)
record("Salary credited", r.status_code == 200 and r.json()["salary"]["status"] == "Credited",
       r.json().get("detail", ""))

n = client.get("/api/notifications", headers=EMP).json()
record("Employee is notified of the credit", n["unread_count"] > before,
       f"unread {before} -> {n['unread_count']}: {n['items'][0]['title']}")

v = client.get(f"/api/salaries/{SAL_ID}/payslip", headers=EMP)
record("Intern can always VIEW their payslip",
       v.status_code == 200 and v.content.startswith(b"%PDF"), f"HTTP {v.status_code}")

blocked_dl = client.get(f"/api/salaries/{SAL_ID}/payslip/download", headers=EMP)
record("Intern download blocked without HR permission", blocked_dl.status_code == 403,
       blocked_dl.json().get("detail", ""))

perm = client.post(f"/api/salaries/{SAL_ID}/payslip-permission",
                   json={"allowed": True}, headers=HR)
record("HR grants the intern download permission",
       perm.status_code == 200 and perm.json()["intern_download_allowed"] is True,
       perm.json().get("detail", ""))
record("Intern is notified of the permission", perm.json()["notification_created"] is True,
       str(perm.json().get("notification_created")))

p = client.get(f"/api/salaries/{SAL_ID}/payslip/download", headers=EMP)
record("Intern can download once permission is granted",
       p.status_code == 200 and p.headers["content-type"] == "application/pdf",
       f"{len(p.content)} bytes")

other = client.get("/api/salaries/1/payslip/download", headers=EMP)
record("Employee cannot download someone else's payslip", other.status_code in (403, 404),
       f"HTTP {other.status_code}")

a = client.get("/api/audit-logs?page_size=5", headers=HR).json()
record("Audit trail records the workflow", a["meta"]["total"] > 0,
       f"{a['meta']['total']} entries, latest={a['items'][0]['action']}")

s = client.get("/api/settings", headers=HR).json()
record("HR settings expose rules but never SMTP credentials",
       "daily_report_mandatory" in s["values"] and "smtp_password" not in str(s),
       f"smtp_configured={s['email']['smtp_configured']}")

r = client.get("/api/settings", headers=EMP)
record("Employee cannot read HR settings", r.status_code == 403, f"HTTP {r.status_code}")

r = client.post("/api/auth/logout", headers=EMP)
record("Employee logs out (session recorded)", r.status_code == 200, f"HTTP {r.status_code}")

print()
print("=" * 74)
passed = sum(1 for _, p, _ in results if p)
print(f"RESULT: {passed}/{len(results)} workflow steps passed")
for n_, p_, d_ in results:
    if not p_:
        print(f"  FAILED: {n_} ({d_})")
print("=" * 74)
sys.exit(0 if passed == len(results) else 1)
