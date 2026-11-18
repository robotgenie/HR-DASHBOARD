"""
End-to-end verification of the four workflows added in this update, run live
against PostgreSQL with real seeded data (spec section 9).

  A. Employee ID flow      created -> profile completed -> photo -> id -> ID card
  B. Profile change flow    locked -> request -> HR approve/reject -> notify -> audit
  C. EOD flow               no attachment -> blocked -> attach -> submitted -> logout
  D. Intern salary slip     credited -> view ok, download blocked -> granted -> download
"""
import sys
import time
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database.database import SessionLocal
from app.main import app

client = TestClient(app)
results = []
TODAY = date.today().isoformat()
stamp = str(int(time.time()))[-6:]

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def record(name, passed, detail=""):
    results.append((name, passed, detail))
    print(f"  [{'PASS' if passed else 'FAIL'}] {name}" + (f"  -- {detail}" if detail else ""))


def login(email, password):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"{email}: {r.status_code} {r.text[:200]}"
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def audit_count(action):
    with SessionLocal() as db:
        return db.execute(
            text("select count(*) from audit_logs where action=:a"), {"a": action}
        ).scalar()


HR = login("hr@rocketgenie.com", "RocketHR@2026")

# ---------------------------------------------------------------- A
print("=" * 74)
print("A. EMPLOYEE ID + ELECTRONIC ID CARD FLOW")
print("=" * 74)

depts = client.get("/api/departments", headers=HR).json()
depts = depts["items"] if isinstance(depts, dict) else depts
intern_dept = next(d["id"] for d in depts if d["name"] == "Internship")
bgs = client.get("/api/internship-backgrounds", headers=HR).json()
bgs = bgs["items"] if isinstance(bgs, dict) else bgs
bg = next(b["id"] for b in bgs if "Cyber" in b["name"])

email = f"idflow{stamp}@rocketgenie.com"
created = client.post("/api/employees", json={
    "full_name": "ID Flow Candidate", "email": email,
    "department_id": intern_dept, "internship_background_id": bg,
    "designation": "Cyber Security Intern", "joining_date": "2026-09-01",
    "employment_status": "Active",
}, headers=HR)
record("Employee created", created.status_code in (200, 201), f"HTTP {created.status_code}")
NEW = created.json()["employee"]["id"]
PW = created.json()["initial_password"]

EMP = login(email, PW)
client.post("/api/auth/change-password",
            json={"current_password": PW, "new_password": "IdFlow@2026"}, headers=EMP)
EMP = login(email, "IdFlow@2026")

before = client.get("/api/employees/me", headers=EMP).json()
record("No employee ID before the profile is complete",
       before["unique_employee_id"] is None, str(before["unique_employee_id"]))
record("ID card not available yet", before["id_card_available"] is False)
record("Missing fields are reported to the employee",
       "Profile photograph" in before["profile_missing_fields"],
       ", ".join(before["profile_missing_fields"]))

card = client.get("/api/employees/me/id-card", headers=EMP).json()
record("Card endpoint explains what is missing", card["available"] is False,
       f"{len(card['missing_fields'])} missing")
pdf_early = client.get("/api/employees/me/id-card/pdf", headers=EMP)
record("Card PDF refused while incomplete", pdf_early.status_code == 409,
       f"HTTP {pdf_early.status_code}")

client.put("/api/employees/me", json={
    "phone": "+91 9876543000",
    "address": "21 Laxmi Nagar, New Delhi - 110092",
    "emergency_contact_name": "Family Contact",
    "emergency_contact_phone": "+91 9876543001",
    "emergency_contact_relation": "Parent",
}, headers=EMP)
client.put(f"/api/employees/{NEW}",
           json={"date_of_birth": "1999-02-14", "gender": "Male"}, headers=HR)

mid = client.get("/api/employees/me", headers=EMP).json()
record("Still no ID until the photograph is uploaded",
       mid["unique_employee_id"] is None,
       f"missing: {', '.join(mid['profile_missing_fields'])}")

photo = client.post("/api/employees/me/photo",
                    files={"file": ("me.png", PNG, "image/png")}, headers=EMP)
record("Photograph uploaded", photo.status_code == 200, f"HTTP {photo.status_code}")

after = client.get("/api/employees/me", headers=EMP).json()
record("Unique employee ID issued on completion",
       bool(after["unique_employee_id"]) and after["unique_employee_id"].startswith("RGEMP"),
       str(after["unique_employee_id"]))
record("Profile reported complete", after["profile_complete"] is True,
       f"{after['profile_completion']}%")
record("ID card now available", after["id_card_available"] is True)
record("Identity fields locked by completion", after["identity_locked"] is True,
       str(after["identity_locked_at"]))

EMP_ID = after["unique_employee_id"]

cardpdf = client.get("/api/employees/me/id-card/pdf", headers=EMP)
record("Employee can download the ID card PDF",
       cardpdf.status_code == 200 and cardpdf.content.startswith(b"%PDF"),
       f"{len(cardpdf.content)} bytes")
record("Card filename carries the employee ID", EMP_ID in cardpdf.headers["content-disposition"],
       cardpdf.headers["content-disposition"])

hr_card = client.get(f"/api/employees/{NEW}/id-card", headers=HR)
record("HR can view the employee's ID card", hr_card.status_code == 200
       and hr_card.json()["unique_employee_id"] == EMP_ID, f"HTTP {hr_card.status_code}")

# uniqueness across the whole table
with SessionLocal() as db:
    total, distinct = db.execute(text(
        "select count(unique_employee_id), count(distinct unique_employee_id) from employees"
    )).first()
record("All issued employee IDs are unique", total == distinct, f"{total} issued, {distinct} distinct")

reissue = client.post("/api/employees/me/issue-id", headers=EMP)
record("Re-issuing does not change the ID",
       reissue.status_code == 200 and reissue.json()["unique_employee_id"] == EMP_ID,
       reissue.json().get("unique_employee_id"))

record("ID generation audit-logged", audit_count("employee_id_generated") >= 1,
       f"{audit_count('employee_id_generated')} entries")
record("ID card generation audit-logged", audit_count("id_card_generated") >= 1,
       f"{audit_count('id_card_generated')} entries")

# ---------------------------------------------------------------- B
print()
print("=" * 74)
print("B. PROFILE CHANGE REQUEST FLOW")
print("=" * 74)

direct = client.put("/api/employees/me", json={"phone": "+91 9000011111"}, headers=EMP)
record("Locked field write refused by the backend", direct.status_code == 403,
       direct.json().get("detail", "")[:70])
record("Denied edit audit-logged", audit_count("profile_locked_edit_denied") >= 1,
       f"{audit_count('profile_locked_edit_denied')} entries")

still = client.get("/api/employees/me", headers=EMP).json()
record("Stored phone unchanged", still["phone"] == "+91 9876543000", still["phone"])

lock = client.get("/api/employees/me/profile-lock", headers=EMP).json()
record("Lock state lists the requestable fields",
       {f["field_name"] for f in lock["fields"]} >= {"full_name", "phone", "email"},
       ", ".join(f["field_name"] for f in lock["fields"]))

req = client.post("/api/profile-change-requests", json={
    "field_name": "phone", "new_value": "+91 9000011111",
    "reason": "New mobile number.",
}, headers=EMP)
record("Employee raises a change request", req.status_code == 201, f"HTTP {req.status_code}")
REQ = req.json()["id"]
record("Request captures old and new value",
       req.json()["old_value"] == "+91 9876543000" and req.json()["new_value"] == "+91 9000011111",
       f"{req.json()['old_value']} -> {req.json()['new_value']}")
record("Request starts Pending", req.json()["status"] == "Pending")

dupe = client.post("/api/profile-change-requests",
                   json={"field_name": "phone", "new_value": "+91 9000022222"}, headers=EMP)
record("Duplicate pending request refused", dupe.status_code == 409,
       dupe.json().get("detail", "")[:60])

emp_notifs = client.get("/api/notifications", headers=EMP).json()
record("Employee notified that the request was submitted",
       any(n["type"] == "Profile Change Requested" for n in emp_notifs["items"]),
       f"{emp_notifs['unread_count']} unread")

hr_queue = client.get("/api/profile-change-requests?status=Pending", headers=HR).json()
record("Request appears in HR's queue",
       any(r["id"] == REQ for r in hr_queue["items"]),
       f"{hr_queue['meta']['total']} pending")
hr_notifs = client.get("/api/notifications", headers=HR).json()
record("HR notified of the pending request",
       any(n["type"] == "Profile Change Requested" for n in hr_notifs["items"]))

self_approve = client.post(f"/api/profile-change-requests/{REQ}/approve",
                           json={}, headers=EMP)
record("Employee cannot approve their own request", self_approve.status_code == 403,
       f"HTTP {self_approve.status_code}")

approved = client.post(f"/api/profile-change-requests/{REQ}/approve",
                       json={"remarks": "Checked against the ID proof."}, headers=HR)
record("HR approves the request", approved.status_code == 200
       and approved.json()["status"] == "Approved", f"HTTP {approved.status_code}")

applied = client.get("/api/employees/me", headers=EMP).json()
record("Profile updated only after approval", applied["phone"] == "+91 9000011111",
       applied["phone"])
record("Approval audit-logged", audit_count("profile_change_approved") >= 1,
       f"{audit_count('profile_change_approved')} entries")
notifs = client.get("/api/notifications", headers=EMP).json()
record("Employee notified of the approval",
       any(n["type"] == "Profile Change Approved" for n in notifs["items"]))

again = client.post(f"/api/profile-change-requests/{REQ}/approve", json={}, headers=HR)
record("Approving twice refused", again.status_code == 409, f"HTTP {again.status_code}")

rej_req = client.post("/api/profile-change-requests", json={
    "field_name": "full_name", "new_value": "Totally Different Name",
}, headers=EMP)
REJ = rej_req.json()["id"]
no_reason = client.post(f"/api/profile-change-requests/{REJ}/reject", json={}, headers=HR)
record("Rejection without a reason refused", no_reason.status_code == 422,
       f"HTTP {no_reason.status_code}")
rejected = client.post(f"/api/profile-change-requests/{REJ}/reject",
                       json={"remarks": "Name must match the Aadhaar record."}, headers=HR)
record("HR rejects with remarks", rejected.status_code == 200
       and rejected.json()["status"] == "Rejected", f"HTTP {rejected.status_code}")
unchanged = client.get("/api/employees/me", headers=EMP).json()
record("Old value kept on rejection", unchanged["full_name"] == "ID Flow Candidate",
       unchanged["full_name"])
record("Rejection audit-logged", audit_count("profile_change_rejected") >= 1,
       f"{audit_count('profile_change_rejected')} entries")
notifs = client.get("/api/notifications", headers=EMP).json()
record("Employee notified of the rejection with remarks",
       any(n["type"] == "Profile Change Rejected" and "Aadhaar" in n["message"]
           for n in notifs["items"]))

# ---------------------------------------------------------------- C
print()
print("=" * 74)
print("C. EOD REPORT FLOW (ATTACHMENT MANDATORY)")
print("=" * 74)

body = {
    "report_date": TODAY,
    "tasks_completed": "Finished the lab exercise.",
    "tasks_in_progress": "Writing up the findings.",
    "tasks_pending": "Peer review.",
    "work_summary": "Lab work and documentation.",
    "submit": True,
}
blocked = client.post("/api/reports", json=body, headers=EMP)
record("Submit without an attachment is blocked", blocked.status_code == 422,
       f"HTTP {blocked.status_code}")
record("Exact validation message returned",
       blocked.json()["detail"] ==
       "Please upload at least one attachment before submitting your EOD report.",
       blocked.json()["detail"])
record("Blocked submission audit-logged",
       audit_count("daily_report_attachment_missing") >= 1,
       f"{audit_count('daily_report_attachment_missing')} entries")

today_report = client.get("/api/reports/me/today", headers=EMP).json()
record("Typed report kept as a Draft", today_report and today_report["status"] == "Draft",
       str(today_report and today_report["status"]))
REP = today_report["id"]

gate = client.get("/api/reports/logout-check", headers=EMP).json()
record("Logout blocked while the report is not valid", gate["logout_blocked"] is True,
       f"attachments={gate['attachment_count']}")
record("Gate reports the attachment requirement", gate["attachment_required"] is True)

att = client.post(f"/api/reports/{REP}/attachments",
                  files={"file": ("eod.png", PNG, "image/png")}, headers=EMP)
record("Attachment uploaded to the draft", att.status_code in (200, 201),
       f"HTTP {att.status_code}")

ok = client.post("/api/reports", json=body, headers=EMP)
record("Submit succeeds with an attachment", ok.status_code in (200, 201)
       and ok.json()["status"] == "Submitted", str(ok.json().get("status")))

gate2 = client.get("/api/reports/logout-check", headers=EMP).json()
record("Logout allowed after a valid submission", gate2["logout_blocked"] is False,
       f"attachments={gate2['attachment_count']}")

# ---------------------------------------------------------------- D
print()
print("=" * 74)
print("D. INTERN SALARY SLIP PERMISSION FLOW")
print("=" * 74)

sal = client.post("/api/salaries", json={
    "employee_id": NEW, "period_year": 2026, "period_month": 8, "working_days": 22,
    "components": [
        {"name": "Basic Salary", "component_type": "earning", "amount": 5565},
        {"name": "House Rent Allowance", "component_type": "earning", "amount": 2782},
        {"name": "Travelling Allowance", "component_type": "earning", "amount": 2225},
        {"name": "Special Allowance", "component_type": "earning", "amount": 557},
    ],
}, headers=HR)
record("HR creates the intern's salary", sal.status_code in (200, 201),
       f"net={sal.json().get('net_pay')}")
SAL = sal.json()["id"]
record("Record flagged as an intern's", sal.json()["is_intern"] is True)

client.post(f"/api/salaries/{SAL}/payslip/generate", headers=HR)
credited = client.post(f"/api/salaries/{SAL}/credit",
                       json={"credit_date": "2026-08-31"}, headers=HR)
record("Salary credited", credited.status_code == 200
       and credited.json()["salary"]["status"] == "Credited")

detail = client.get(f"/api/salaries/{SAL}", headers=EMP).json()
record("Intern may view the payslip", detail["employee_can_view_payslip"] is True)
record("Intern may NOT download it yet", detail["employee_can_download_payslip"] is False)
record("Block reason supplied to the UI",
       detail["download_block_reason"] == "Download permission has not been granted by HR.",
       detail["download_block_reason"])

view = client.get(f"/api/salaries/{SAL}/payslip", headers=EMP)
record("View endpoint works for the intern",
       view.status_code == 200 and view.content.startswith(b"%PDF"), f"HTTP {view.status_code}")

denied = client.get(f"/api/salaries/{SAL}/payslip/download", headers=EMP)
record("Download denied by the API, not just the button", denied.status_code == 403,
       denied.json().get("detail", ""))
record("Denied download audit-logged", audit_count("intern_payslip_download_denied") >= 1,
       f"{audit_count('intern_payslip_download_denied')} entries")

self_grant = client.post(f"/api/salaries/{SAL}/payslip-permission",
                         json={"allowed": True}, headers=EMP)
record("Intern cannot grant their own permission", self_grant.status_code == 403,
       f"HTTP {self_grant.status_code}")

grant = client.post(f"/api/salaries/{SAL}/payslip-permission",
                    json={"allowed": True}, headers=HR)
record("HR grants download permission", grant.status_code == 200
       and grant.json()["intern_download_allowed"] is True, grant.json().get("detail", ""))
record("Permission grant audit-logged",
       audit_count("intern_payslip_permission_granted") >= 1,
       f"{audit_count('intern_payslip_permission_granted')} entries")

notifs = client.get("/api/notifications", headers=EMP).json()
granted_note = [n for n in notifs["items"] if n["type"] == "Payslip Download Granted"]
record("Intern notified of the permission", bool(granted_note),
       granted_note[0]["message"] if granted_note else "")

allowed = client.get(f"/api/salaries/{SAL}/payslip/download", headers=EMP)
record("Intern downloads successfully after the grant",
       allowed.status_code == 200 and allowed.content.startswith(b"%PDF"),
       f"{len(allowed.content)} bytes")
record("Successful intern download audit-logged",
       audit_count("intern_payslip_downloaded") >= 1,
       f"{audit_count('intern_payslip_downloaded')} entries")

revoke = client.post(f"/api/salaries/{SAL}/payslip-permission",
                     json={"allowed": False}, headers=HR)
record("Permission can be withdrawn", revoke.status_code == 200
       and revoke.json()["intern_download_allowed"] is False)
record("Download blocked again after withdrawal",
       client.get(f"/api/salaries/{SAL}/payslip/download", headers=EMP).status_code == 403)

hr_dl = client.get(f"/api/salaries/{SAL}/payslip/download", headers=HR)
record("HR download never blocked", hr_dl.status_code == 200, f"HTTP {hr_dl.status_code}")

# regular employees are unaffected by the intern rule
reg = client.get("/api/employees?search=Priya&page_size=5", headers=HR).json()
reg_id = reg["items"][0]["id"]
reg_sal = client.get(f"/api/salaries?employee_id={reg_id}&page_size=50", headers=HR).json()
credited_reg = [s for s in reg_sal["items"] if s["status"] == "Credited"]
if credited_reg:
    s0 = credited_reg[0]
    record("Non-intern payslip needs no extra permission",
           s0["is_intern"] is False and s0["employee_can_download_payslip"] is True,
           f"intern={s0['is_intern']}")
    nope = client.post(f"/api/salaries/{s0['id']}/payslip-permission",
                       json={"allowed": True}, headers=HR)
    record("Permission endpoint rejects non-interns", nope.status_code == 422,
           nope.json().get("detail", "")[:50])

print()
print("=" * 74)
passed = sum(1 for _, p, _ in results if p)
print(f"RESULT: {passed}/{len(results)} checks passed")
for n, p, d in results:
    if not p:
        print(f"  FAILED: {n} ({d})")
print("=" * 74)
sys.exit(0 if passed == len(results) else 1)
