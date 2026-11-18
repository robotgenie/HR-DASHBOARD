# HRMS Final Update Notes

## Employee ID approval
1. Employee/intern completes mandatory profile details and uploads photograph.
2. Employee/intern requests ID approval from My Profile.
3. Status becomes Pending; no final RGEMP### ID is issued.
4. HR/Admin reviews the request from **ID Approvals**.
5. HR/Admin approves or rejects with remarks.
6. Approval issues the immutable RGEMP### ID and makes the electronic ID card available.
7. The existing profile photograph is used on the ID card.
8. Existing issued IDs are backfilled as Approved by the migration.
9. Backend blocks ID-card view/download until approval.

## Two daily reports
- Exactly one **Noon** report and one **EOD** report per employee/date.
- Noon expected around 1:00 PM.
- EOD expected around 6:00 PM.
- Both store report type, report date, submission timestamp, work details and status.
- EOD requires at least one attachment; the existing EOD attachment requirement is preserved.
- HR Work Reports has a Noon/EOD filter.
- Employee/intern logout validation checks both reports when the daily-report setting is mandatory.

## Selfie
- Employee/intern login requires a fresh camera selfie.
- Employee/intern logout requires a fresh camera selfie after the report gate passes.
- Existing work-session selfie storage is preserved.

## Test database
Use a separate PostgreSQL database for testing, for example:

```env
DATABASE_URL=postgresql+psycopg2://rocket:YOUR_PASSWORD@localhost:5432/roboo_hr_selfie_test
```

Then:

```powershell
alembic upgrade head
python seed_data.py
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Current Alembic head:

```text
f2a3b4c5d6e7
```

## Verification performed
- Python compilation: passed.
- JavaScript syntax checks: passed for all frontend JS files.
- SQLAlchemy mapper configuration using SQLite: passed.
- SQLite metadata/schema creation: passed.
- Alembic head check: `f2a3b4c5d6e7`.
- Requested-update static checks: 8/8 passed.
- Comprehensive requested-feature static checks: 17/17 passed.

A real PostgreSQL/browser/camera run still needs to be performed on the target Windows machine because this environment cannot connect to the user's local PostgreSQL service or access a real camera.

---

# Update: attendance, half-day leave, report rules, monthly reports (Sep 2026)

## Run it

```powershell
cd backend
pip install -r requirements.txt
alembic upgrade head          # new head: b8c9d0e1f2a3 (adds columns only, existing rows kept)
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
# open http://127.0.0.1:8000/app/login.html
python -m pytest tests -q     # 243 tests (SQLite); RG_TEST_DB=postgres for PostgreSQL
```

## Business rules (all enforced in the backend; the UI only reflects them)
Office day (IST): 10:00 AM - 6:00 PM. Noon Report opens 1:00 PM, EOD Report opens 6:00 PM.

| Approved leave   | Works         | Noon report  | EOD report   | Logout allowed when |
|------------------|---------------|--------------|--------------|---------------------|
| none             | 10 AM - 6 PM  | required     | required     | both submitted (EOD with attachment) |
| Morning Half     | 1 PM - 6 PM   | blocked (403)| required     | EOD submitted |
| Afternoon Half   | 10 AM - 1 PM  | required     | blocked (403)| Noon submitted |
| Full Day         | -             | blocked (403)| blocked (403)| always |

* Late login: employees/interns logging in after the expected time (10:00 AM, or 1:00 PM on
  an approved Morning Half leave / Second Half day) must give a reason. Expected login,
  actual login, late minutes, reason, date and user are stored on work_sessions.
  HR/Admin accounts are never asked. Only the first login of the day is assessed.
* Extra working hours = actual logout - expected logout (6:00 PM, or 1:00 PM for an
  Afternoon Half leave / First Half day). Leave approved after login is re-applied at logout.
* Half-day working status (First/Second Half chosen at login) is separate from half-day
  leave (an approved leave request with leave_period Morning Half / Afternoon Half).
* Leave approval takes effect immediately - every rule reads approved leave live.
* Logout gate: POST /api/auth/logout returns 409 LOGOUT_BLOCKED with the pending actions.
* Photographs: uploads go to HR as a pending Photograph document; only an HR-verified
  photo becomes the profile / ID-card photo. HR/Admin IDs are approved automatically.
* Mandatory documents: Photograph, Aadhaar, PAN, CV. Optional: Highest Qualification,
  Experience Letter.
* Monthly report: HR -> Employees -> View -> Monthly Reports (View | Download);
  employees/interns: My Monthly Report. Salary uses the existing pro-rata rule
  (Gross x (Working days - Unpaid leave days) / Working days), now in
  salary_service.payable_breakdown. Interns' PDF includes salary figures only when HR has
  granted payslip download permission for that month.
* Notifications: read notifications can be deleted (single or "Delete read").

---

# Update 2: Check-In/Check-Out, tasks, hourly updates, dashboards (Oct 2026)

## Run it
```powershell
cd backend
pip install -r requirements.txt
alembic upgrade head          # new head: c9d0e1f2a3b4 (adds columns/tables only)
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
python -m pytest tests -q     # 248 tests
```
Camera and location need HTTPS or http://localhost / 127.0.0.1 in the browser.

## What changed
* Login is a normal email + password sign-in for every role (no selfie, no late prompt).
* Employees/interns use **Check-In / Check-Out** on the dashboard:
  Check-In -> late-login reason (if after the expected time) -> location -> live selfie
  (preview, retake, confirm) -> saved on work_sessions. Check-Out -> Noon/EOD rules
  (approved leave applied) -> location -> live selfie. Logout no longer checks anything.
* Tasks: HR/Admin assign from Work Monitor (one or many people, optional numeric target).
* Hourly Updates 10-11 ... 5-6, linked to a task, with attachments; popup + ~18 s chime
  when an hour is due (one per hour); nothing new after 6 PM. Eligibility uses the same
  approved-leave logic (Morning Half: before 1 PM blocked; Afternoon Half: from 1 PM
  blocked; Full Day: all blocked).
* An hourly update at/after 1 PM marks the existing Noon Report Submitted (source
  "Hourly Updates"). On an Afternoon Half leave the Noon Report is the closing report and
  requires a proof-of-work attachment.
* HR: Work Monitor (attendance with selfies/locations, tasks, hourly updates), "Today at
  work" on the dashboard, Check-In history + tasks on each employee profile.
* Employee creation: Employee type (Employee / Intern) drives the department.
* Fixes: brand buttons lost their colour on hover; timestamps displayed 5.5 h early.
