# Rocket Genie HRMS — Admin, Manager & Hierarchy release

FastAPI + SQLAlchemy + PostgreSQL + Alembic backend, HTML / CSS / vanilla JavaScript
frontend (no frameworks, no Node build). This release extends the existing HRMS with:

* a separate **Admin** role and **Admin console** (the Admin is not an employee — no check-in);
* a **Manager** role and **Manager portal**;
* the reporting hierarchy **ADMIN → HR → MANAGER → EMPLOYEE / INTERN**, stored in the
  database and enforced by one central authorization engine in **every** module;
* HR self-service (HR checks in, submits reports, requests leave like any employee);
* **Excel** import (template → preview → error report → confirm), bulk update and exports.

Everything that existed before (selfie check-in/out, late-login rules, half-day leave,
Noon/EOD/hourly reports, tasks, documents, salary/payslips, UAN, ID cards, profile change
requests, intern payslip requests, meetings, notifications, monthly reports, audit logs)
is preserved.

---

## 1. Installation

Requirements: Python 3.11+, PostgreSQL 13+ (16 tested).

```powershell
cd backend
python -m venv venv
venv\Scripts\activate            # Linux/macOS: source venv/bin/activate
pip install -r requirements.txt  # adds openpyxl 3.1.5 for Excel
```

> The `backend/venv` folder in the original ZIP was created on Windows without
> `openpyxl`. Re-run `pip install -r requirements.txt` in it (or create a fresh venv).

## 2. Environment variables (`backend/.env`)

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | `postgresql+psycopg2://USER:PASSWORD@HOST:5432/DBNAME` (URL-encode `@` as `%40`) |
| `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES` | Login tokens |
| `SMTP_*` | Optional. Without SMTP, emails are written to the log and the email log |
| `UPLOAD_DIR`, `MAX_FILE_SIZE`, `ALLOWED_EXTENSIONS` | Document / selfie / payslip storage |
| `COMPANY_*` | Printed on payslips |
| `FRONTEND_BASE_URL`, `CORS_ORIGINS` | Where the frontend is served |
| `SEED_HR_PASSWORD`, `SEED_EMPLOYEE_PASSWORD` | Demo seed passwords |

No new variables are required by this release.

## 3. Database setup & migrations

```powershell
createdb hrms                    # or create it in pgAdmin
cd backend
alembic upgrade head             # new head: d1e2f3a4b5c6
```

Migration `d1e2f3a4b5c6_admin_manager_hierarchy` is **additive** — no table or column is
dropped and existing rows are kept. It adds the ADMIN and MANAGER roles, the hierarchy
columns, the leave approval stage, task division and the Excel batch table, and then
normalises existing reporting lines (see `VERIFICATION_REPORT.md` → Database changes).
`alembic downgrade -1` reverses it.

Demo data (development only):

```powershell
python seed_data.py              # idempotent; --reset drops everything first
```

## 4. Running

```powershell
cd backend
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The frontend is served by FastAPI: open **http://127.0.0.1:8000/app/login.html**.
(Any static host also works; set `FRONTEND_BASE_URL`/`CORS_ORIGINS`, and the frontend
reads the API base from `localStorage.rg_api_base` when it is not served under `/app/`.)

API docs: http://127.0.0.1:8000/docs

## 5. Accounts and roles

One login page for everyone; the API returns the portal each account uses:

| Role (DB `roles.name`) | Portal | Is an employee? | Check-in |
|---|---|---|---|
| `ADMIN` | `/admin/` Admin console | No (no employee record) | No |
| `HR_ADMIN` (HR) | `/hr/` HR dashboard + "My work" pages | Yes | Yes (no late-login rule — existing HR exception) |
| `MANAGER` | `/manager/` personal dashboard + team pages | Yes | Yes |
| `EMPLOYEE` | `/employee/` | Yes | Yes |
| `EMPLOYEE` in the Internship department | `/intern/` | Yes | Yes |

Demo accounts after `seed_data.py`:

| Role | Email | Password |
|---|---|---|
| Admin | admin@rocketgenie.com | RocketAdmin@2026 |
| HR (Ananya — Meera's branch) | hr@rocketgenie.com | RocketHR@2026 |
| HR (Rohit — Arjun's branch + Teaching) | rohit.verma@rocketgenie.com | RocketHR@2026 |
| Manager (reports to Ananya) | meera.joshi@rocketgenie.com | Rocket@2026 |
| Manager (reports to Rohit) | arjun.kapoor@rocketgenie.com | Rocket@2026 |
| Employee / Intern | employee1@…, intern1@… | Rocket@2026 |

### Creating an Admin
```powershell
python create_admin.py --email admin@company.com --name "Org Admin"            # prints a temporary password
python create_admin.py --email admin@company.com --name "Org Admin" --password "S3cure!Pass"
```
An existing Admin can also add Admins from **Admin Profile → Admin accounts**.

### Creating HR, Managers, Employees, Interns
* **Admin → People Directory → Add person**: choose *Role* (HR / Manager / Employee),
  *Reporting HR* and *Reporting manager*. Interns = Employee role in the Internship department.
* **HR → Employees → Add employee**: Manager or Employee/Intern, placed under the HR
  (Reporting HR defaults to the HR; the reporting-manager list shows only the HR's managers).
* **Excel**: Admin / HR → *Excel Import / Export* → download the template, fill it, upload,
  review the preview, confirm.
* API: `POST /api/employees` with `role`, `reporting_hr_id`, `reporting_manager_id`.

### Reporting hierarchy
* HR → reports to the Admin (no Reporting HR / Manager).
* Manager → must have a Reporting HR; never reports to another manager.
* Employee / Intern → reports to a Manager (their Reporting HR is the manager's HR,
  kept in sync automatically) or directly to an HR.
* Change it in **Admin → Organization & Hierarchy** (anyone), **HR → My Hierarchy**
  (own branch), the employee edit form, Excel bulk update, or
  `PUT /api/hierarchy/employees/{id}`. Moving a manager to another HR moves the team too.
  A manager with team members (or an HR with people) can't be demoted until reassigned.
* **Unassigned people**: managers/employees with no Reporting HR (e.g. legacy data when
  more than one HR exists) are visible to every HR while *Settings → HR can see unassigned
  people* is on (default, Admin-only switch). Turn it off for strict HR-only hierarchies.
  HR accounts are never in that pool — one HR never sees another HR.

## 6. Permissions (enforced by the backend — `app/services/hierarchy_service.py`)

| Level | Who | Used for |
|---|---|---|
| view | self, Manager → team, HR → hierarchy, Admin → all | profile, attendance, reports, hourly, tasks, leave, monthly report, document status |
| sensitive | self, HR → hierarchy, Admin → all (never a Manager) | salary, payslips, UAN, document files |
| supervise | Manager → team, HR → hierarchy, Admin → all (never self) | review reports, first-level leave, assign/divide tasks |
| manage | HR → hierarchy (never self), Admin → all | verify documents, salary, UAN, ID approval, final leave, edit records |

Flows:
* **Leave**: Employee/Intern → Manager (approve = forward) → HR (final) ; Manager → HR ;
  HR → Admin. HR may decide at the manager stage; the Admin may decide at any stage.
* **Work reports**: reviewed by Manager (team), HR (hierarchy) or Admin; HR's own → Admin.
* **Tasks**: Admin → HR/Manager/Employee/Intern; HR → Manager/Employee/Intern; Manager →
  team. A task assigned to you can be **divided** among the people below you.
* **Documents**: HR verifies their hierarchy; the Admin verifies HR's own documents;
  Managers see document *status* only.
* **Salary**: HR/Admin manage; HR's own salary is managed by the Admin; Managers never see
  team salary; everyone sees their own (intern download permission rules unchanged).
* **Notifications** stay personal (a user only reads their own). Requests are routed up the
  hierarchy: leave → manager / HR / Admin; profile-change and intern payslip requests → the
  person's HR (Admin for HR accounts).
* Every refusal is a **403** and is written to the audit log (`access_denied`).

## 7. Excel

* Template: `GET /api/excel/template` — sheets *Employees*, *Reference* (dropdown lists of
  your departments, backgrounds, HRs, managers, statuses) and *Instructions*.
* Preview: `POST /api/excel/import/preview` (multipart `file`, `mode` = auto | create | update).
  Nothing is written. Validates columns, IDs (`RG-YYYY-NNNN`), emails, departments,
  designations, type, dates, gender, status, background, Reporting HR/Manager, manager
  designation, the HR↔manager relationship, duplicates and the importer's own authority.
* Error report: `GET /api/excel/import/{token}/errors` (.xlsx: Row, Employee ID, Name,
  Field, Invalid value, Error, Suggested correction).
* Confirm: `POST /api/excel/import/{token}/confirm` — re-validates against the current
  database, applies valid rows only (HR → managers → employees order, one savepoint per
  row), returns temporary passwords once. Reporting-line changes require
  `confirm_hierarchy_changes: true`.
* Export: `GET /api/excel/export?type=employees|hierarchy|attendance|leave|reports|hourly|tasks|documents|salary|monthly`
  with filters `department_id, reporting_hr_id, reporting_manager_id, person_type,
  employment_status, date_from, date_to, month, report_type, status, leave_type`.
  Admin = organisation, HR = hierarchy, Manager = team (no salary), employee = own.
* The workbook itself is never stored; audit entries hold counts and filters only.

## 8. Testing

```powershell
cd backend
python -m pytest tests -q                          # SQLite (no services needed)
$env:RG_TEST_DB="postgres"; python -m pytest tests -q   # PostgreSQL test DB (TEST_DATABASE_URL)
```

Tests: the original 248 (one updated: HR now checks in) + 28 hierarchy / API-security
tests (`tests/test_hierarchy.py`) + 7 Excel tests (`tests/test_excel.py`) + 23 bank-details /
salary-automation tests (`tests/test_bank_details_salary.py`) + 5 work-location tests
(`tests/test_work_location.py`). 311 in total.
See `VERIFICATION_REPORT.md` for the full results, including browser end-to-end checks.

## 9. Project map (new pieces)

```
backend/app/services/hierarchy_service.py   central hierarchy + authorization engine
backend/app/services/excel_service.py       Excel template / validation / import / export
backend/app/api/hierarchy.py                /api/hierarchy/*  (tree, team, candidates, reassign)
backend/app/api/admin.py                    /api/admin/*      (dashboard, HR monitoring, people, profile, admins)
backend/app/api/excel.py                    /api/excel/*
backend/app/models/excel_import_batch.py
backend/migrations/versions/d1e2f3a4b5c6_admin_manager_hierarchy.py
backend/create_admin.py
frontend/admin/*.html                       Admin console
frontend/manager/*.html                     Manager portal
frontend/hr/{hierarchy,tasks,excel,monthly-reports,person,my-*}.html
frontend/js/{admin-dashboard,people,person,org,departments,tasks,excel,monthly-summary,manager-dashboard,admin-profile}.js
frontend/css/hierarchy.css
```

## 10. Bank details and automatic monthly salary slips

**Bank details** live inside the existing **Documents** page (no separate page or menu item).
They are not asked for when HR creates an employee.

1. The employee opens Documents → **Bank Details** (marked MANDATORY) and enters Bank Name,
   Bank Account Number, Confirm Bank Account Number, IFSC Code and PAN Card Number.
   The browser and the API both validate them (account 9–18 digits and matching, IFSC
   `AAAA0XXXXXX`, PAN `AAAAA9999A`, nothing blank).
2. **Review details** shows a summary with the account masked (`XXXX XXXX 1234`). The employee
   ticks *"I confirm that the bank details entered above are correct."* and clicks
   **Submit for Approval** → status **Pending Approval**.
3. HR (for people in their hierarchy) or the Admin (for everyone, and for HR's own details)
   opens Documents → **Bank details** tab → Review → **Approve** or **Reject** (a reason is
   required). Managers and employees cannot review; the API refuses it.
4. **Rejected**: the employee sees the reason, corrects the details and submits again.
5. **Approved**: the details become official. Until then, previously approved details stay in use.

Salary slips print the approved Bank Name, Bank Account No. and PAN No. in the fields that
already existed on the slip (no new columns; IFSC is stored but not printed). On approval,
generated slips that are not yet credited are re-rendered with the new details; a credited
slip is only refreshed when the employee had no approved details before.

**Monthly salary slips** are created automatically: for every Active / On Leave employee with
an active login and a previous salary record, the current month's record is created by
copying the previous month (same earnings/deductions, Monday–Friday working days, status
Pending, marked *Auto*). Months missing since the last salary are filled in when the last
salary is at most `SALARY_AUTOGEN_MAX_BACKFILL_MONTHS` (default 3) months old. Future months
are never created, and one employee + month + year can only ever have one record.

* Runs inside the API process at start-up and every `SALARY_AUTOGEN_INTERVAL_MINUTES`
  (default 60). Disable with `SALARY_AUTOGEN_ENABLED=false`, or switch off
  *Create monthly salary slips automatically* in Settings.
* For an OS scheduler instead/as well: `python generate_monthly_salaries.py`
  (cron example: `15 1 1 * * cd /path/backend && venv/bin/python generate_monthly_salaries.py`).
* Payroll page → **Generate this month** runs it on demand (HR: own hierarchy; Admin: everyone).

HR/Admin then **Edit** the generated slip and change only the payment details (amounts, days,
status, credit date, remarks). The employee and the pay period can't be changed (the API
returns 422). Creating a record for a month that already exists opens the existing one
for editing instead.

APIs: `GET/POST /api/bank-details/me`, `GET /api/bank-details`, `GET /api/bank-details/{id}`,
`POST /api/bank-details/{id}/approve`, `POST /api/bank-details/{id}/reject`,
`GET /api/bank-details/employee/{employee_id}`, `POST /api/salaries/auto-generate`.
Migration: `e2f3a4b5c6d7` (run `alembic upgrade head`; additive, no data removed).

**Location on salary slips** is the employee's **Work location** (employee form, Excel column
"Work Location"), or Settings → *Default work location* when they have none. Migration
`f3a4b5c6d7e8` sets that default from the location most existing employees already have.

---
---

# Original system documentation (kept from the previous release)

> Everything below is the README that shipped before this release, unchanged.
> Where it says the system has two roles (HR / Admin and Employee), read the
> sections above: there are now four roles (Admin, HR, Manager, Employee/Intern)
> and the HR role is scoped to its own hierarchy.

## New HR Records Database

The project includes `backend/create_robo_gini_hr_records.sql` for creating
the PostgreSQL database named **Robo Gini HR Records**. Run the script from
`psql`, then copy `backend/.env.example` to `backend/.env` and set the real
database credentials. Run `alembic upgrade head` before starting the API.

# Rocket Genie — HR & Employee Management System

A complete, working HR platform for **Rocket Genie**
(Hno. 35, Office no. 301, 3rd Floor, Metro Pillar no. 35, Near Sai Baba Mandir,
Laxmi Nagar, New Delhi – 110092).

Two roles — **HR / Admin** and **Employee** — with employee onboarding, document
verification with version history, UAN handling, payroll with real PDF payslips,
department-scoped daily meetings, daily work reports, notifications, email
delivery, and a full audit trail.

Every rule is enforced **on the server**. Hiding a button in the UI is never the
security mechanism.

---

## 1. Stack

| Layer | Technology |
| --- | --- |
| API | Python 3.12, FastAPI, Pydantic v2 |
| ORM / DB | SQLAlchemy 2, PostgreSQL 16 |
| Migrations | Alembic |
| Auth | JWT (python-jose), bcrypt password hashing |
| Email | Python `smtplib` (Mailtrap-friendly, console fallback) |
| PDF | ReportLab (payslip generation) |
| Frontend | HTML + CSS + **vanilla JavaScript** only |
| Charts | Chart.js via CDN (dashboards only) |

No React, Vue, Angular, Next.js, TypeScript, Vite, Node.js or Express is used
anywhere in the product. Node is not required to run or build anything.

**Size:** 95 Python modules, 17 JS modules, 13 stylesheets, 26 HTML pages,
92 API endpoints, 24 database tables.

---

## 2. Folder structure

```
rocket-genie-hrms/
├── README.md
├── backend/
│   ├── app/
│   │   ├── main.py                  FastAPI app, CORS, error handlers, static mount
│   │   ├── core/                    config, security, constants, dependencies (RBAC)
│   │   ├── database/                engine, session, declarative Base
│   │   ├── models/                  22 SQLAlchemy models
│   │   ├── schemas/                 Pydantic request/response models
│   │   ├── api/                     routers: auth, employees, departments,
│   │   │                            internship_backgrounds, documents, uan,
│   │   │                            salaries, notifications, meetings, reports,
│   │   │                            audit_logs, dashboard, settings
│   │   ├── services/                business logic (13 services)
│   │   ├── pdf/payslip_generator.py payslip layout
│   │   └── utils/                   amount-in-words, time helper
│   ├── migrations/                  Alembic environment + versions
│   ├── tests/                       223 pytest tests
│   ├── uploads/                     private file storage (not web-served)
│   ├── seed_data.py                 demo data loader
│   ├── verify_spec.py               live security/idempotency verification
│   ├── verify_workflows.py          live end-to-end workflow walkthrough
│   ├── verify_update.py             ID card / profile change / EOD / intern flows
│   ├── verify_controls.py           filters, search, sorting, paging, RBAC sweep
│   ├── verify_frontend.py           static-asset smoke test
│   ├── alembic.ini
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    ├── login.html, forgot-password.html, reset-password.html, change-password.html
    ├── hr/         13 pages (dashboard, employees, employee-details, documents,
    │               profile-requests, payslip-requests,
    │               uan, salary, meetings, work-reports, notifications,
    │               audit-logs, settings)
    ├── employee/   9 pages (dashboard, profile, documents, uan, salary-slips,
    │               meetings, daily-reports, notifications, settings)
    ├── css/        12 stylesheets, all tokens in global.css
    ├── js/         15 modules; api.js is the only place that talks HTTP
    └── assets/logo/
```

---

## 3. Prerequisites

- Python 3.11 or newer
- PostgreSQL 14 or newer

---

## 4. Setup — Windows (PowerShell)

All commands are run from the repository root unless stated otherwise.

### 4.1 Create the databases

Open **SQL Shell (psql)** or use `psql` from PowerShell:

```powershell
psql -U postgres
```

```sql
CREATE USER rocket WITH PASSWORD 'rocket';
ALTER USER rocket CREATEDB;
CREATE DATABASE rocket_genie_hrms OWNER rocket;
CREATE DATABASE rocket_genie_hrms_test OWNER rocket;
\q
```

### 4.2 Virtual environment and dependencies

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If PowerShell blocks the activation script:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

### 4.3 Environment file

```powershell
Copy-Item .env.example .env
notepad .env
```

At minimum set `DATABASE_URL` and a strong `JWT_SECRET_KEY`. To generate one:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

### 4.4 Create the schema

```powershell
alembic upgrade head
```

### 4.5 Load demo data

```powershell
python seed_data.py
```

### 4.6 Run the application

```powershell
uvicorn app.main:app --reload --port 8000
```

Then open **http://localhost:8000/** — it redirects to the login page. The
frontend is served by the same process at `/app`, so there is no separate
frontend server, build step or bundler.

- Interactive API docs: http://localhost:8000/docs
- OpenAPI schema: http://localhost:8000/openapi.json

---

## 5. Setup — macOS / Linux

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then edit DATABASE_URL and JWT_SECRET_KEY
alembic upgrade head
python seed_data.py
uvicorn app.main:app --reload --port 8000
```

---

## 6. Demo credentials

| Role | Email | Password |
| --- | --- | --- |
| HR / Admin | `hr@rocketgenie.com` | `RocketHR@2026` |
| HR Executive | `rohit.verma@rocketgenie.com` | `RocketHR@2026` |
| Employee (Digital Marketing) | `employee1@rocketgenie.com` | `Rocket@2026` |
| Employee (Marketing) | `employee2@rocketgenie.com` | `Rocket@2026` |
| Intern (Data Science) | `intern1@rocketgenie.com` | `Rocket@2026` |
| Intern (Cyber Security) | `intern2@rocketgenie.com` | `Rocket@2026` |

Seeded volume: 17 employees across 7 departments (all with employee ids
`RGEMP001`-`RGEMP017`, photographs and ID cards), 111 documents with version
history, UAN records in every status, 68 salary records over 4 pay periods,
51 generated payslip PDFs, 16 department meetings, 49 daily work reports each
with an attachment, and 4 intern payslip download permissions granted (the rest
left view-only so the permission rule is visible).

Log in as `employee1@` and `employee2@` side by side to see that meetings for one
department are genuinely invisible to the other.

---

## 7. Environment variables

Full list with comments lives in `backend/.env.example`. The ones that matter most:

| Variable | Purpose |
| --- | --- |
| `COMPANY_UDYAM` | Udyam registration number printed on the payslip |
| `DATABASE_URL` | PostgreSQL connection string |
| `TEST_DATABASE_URL` | Used when running the suite against PostgreSQL |
| `JWT_SECRET_KEY` | **Change this.** Signs access tokens |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Token lifetime (default 480) |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USERNAME` / `SMTP_PASSWORD` | Mail transport |
| `SMTP_FROM_EMAIL` / `SMTP_FROM_NAME` | Sender identity |
| `UPLOAD_DIR` | Private file root (default `uploads`) |
| `MAX_FILE_SIZE` / `ALLOWED_EXTENSIONS` | Upload limits |
| `COMPANY_NAME` / `COMPANY_ADDRESS` / `COMPANY_LOGO_PATH` | Payslip header |
| `FRONTEND_BASE_URL` | Used to build links inside emails |
| `SEED_HR_PASSWORD` / `SEED_EMPLOYEE_PASSWORD` | Seed script passwords |

No secret is hardcoded anywhere in the source.

### Email setup

Leave `SMTP_HOST` blank during development: every message is written to the
console in full (subject, recipient, body) and recorded in the `email_logs`
table, so nothing is lost and no mail escapes.

For a real inbox, [Mailtrap](https://mailtrap.io) works without any code change:

```
SMTP_HOST=sandbox.smtp.mailtrap.io
SMTP_PORT=2525
SMTP_USERNAME=<your mailtrap username>
SMTP_PASSWORD=<your mailtrap password>
```

Employees can never see SMTP settings — the settings endpoint returns only
whether email is configured, never the credentials.

---

## 8. Alembic commands

```powershell
alembic upgrade head            # apply all migrations (2 revisions)
alembic downgrade -1            # roll back one revision
alembic current                 # show the applied revision
alembic history --verbose       # list revisions
alembic revision --autogenerate -m "describe the change"
```

`f5e3b245eda5_initial_schema.py` creates the first 22 tables with primary keys,
foreign keys, unique constraints, indexes and timestamps.
`9c41ab7de552_payslip_fields.py` adds the payroll fields the payslip prints
(work location, bank name, bank account number, PAN) and the per-period
loss-of-pay day count. `b7d31f04ae19_intern_payslip_download_requests.py` adds
the intern download request table.
`286d92b51b39_employee_id_card_profile_change_.py` adds the
`profile_change_requests` table, the employee-id and lock columns on
`employees`, and the intern download-permission columns on `salary_records`. It
also backfills an employee id for every existing employee whose profile is
already complete, so upgrading a live installation does not leave them without
an id or ID card.

---

## 9. Testing

```powershell
cd backend
python -m pytest tests -q                    # 223 tests on throwaway SQLite
$env:RG_TEST_DB="postgres"; python -m pytest tests -q   # same suite on PostgreSQL
```

The suite covers authentication and token expiry, RBAC and resource ownership,
document upload/versioning/review, **rejection of document deletion**, UAN
validation, salary totals and amount-in-words, payslip generation, credit
idempotency, and department-scoped meeting visibility.

Three live verification scripts run against real seeded data:

```powershell
python verify_frontend.py     # every page and asset is served (26 + 60)
python verify_spec.py         # 38 security / idempotency / payslip checks
python verify_workflows.py    # 51-step HR and employee journeys end to end
python verify_update.py       # 70 checks across the four newer workflows
python verify_controls.py     # 117 checks: filters, search, sort, paging, RBAC
```

`verify_workflows.py` hires a new employee, so it adds a row each run.

---

## 10. How key rules are enforced

**Documents can never be deleted.** `DELETE /api/documents/{id}` is wired to
return `403` for *everyone* — employee and HR alike — and writes a
`document_delete_denied` entry to the audit log. Submitted documents are part of
the compliance record. Re-uploads create a new version; the previous version is
kept and remains viewable.

**Files are never publicly reachable.** Uploads live outside the static mount and
are streamed only through authenticated endpoints that re-check ownership on
every request. Filenames are regenerated server-side, extensions and MIME types
are validated against the document type, size is capped, and path traversal is
impossible because the stored name is never taken from the client.

**Salary crediting is idempotent.** Notification and email rows carry a unique
`dedupe_key` (`salary:{id}:credited`). Crediting twice returns `200` with
`notification_created: false`, `email_sent: false` and an explanatory message —
the employee is never notified or emailed twice.

**Meetings are department-scoped.** The list query filters by the caller's own
department, there is no read-by-id endpoint to bypass it, and create/edit/cancel
all require HR.

**Logging out never fabricates a work report.** The logout gate asks the server
whether a report is required and whether one exists today. If reports are
mandatory and none is filed, logout is blocked with a link to file one. Choosing
"Submit report & log out" submits a real report the employee wrote. Logging out
by itself never marks anything submitted.

**Amounts in words are computed in Python** using the Indian numbering system
(lakh/crore), from the server-side total — not from anything the client sends.

---

## 11. Employee IDs, ID cards and locked identity fields

**Unique employee ID.** Every employee is issued a sequential id (`RGEMP001`,
`RGEMP002`, ...) automatically, the moment their profile becomes complete. It is
assigned server-side, unique-constrained in the database, and never reissued or
editable — sending `unique_employee_id` to either update endpoint is ignored.
Until it is issued, the UI falls back to the internal joining code
(`RG-2026-0003`).

**The profile must be complete first, photograph included.** All ten mandatory
fields are required: name, phone, date of birth, gender, address, all three
emergency-contact fields, designation and the profile photograph. The API
reports exactly what is still missing, and the ID card PDF is refused with a
409 until the list is empty.

**Electronic ID card.** Issued alongside the id. Employees view it on their
profile and can print it or download a CR80 badge-sized PDF (logo, photo, name,
employee id, department, designation, date of joining, company name and
address). HR can view and download any employee's card.

**Identity fields lock on completion.** Name, phone, email, date of birth and
gender become read-only to the employee at that point. `PUT /api/employees/me`
returns 403 and writes a `profile_locked_edit_denied` audit entry if one is
attempted, so bypassing the disabled control in the browser achieves nothing.
Address and emergency contact stay self-editable.

**Change requests are the only route.** The employee raises a request naming the
field and new value; HR approves or rejects it from **Profile Requests**.
Approval is what writes the field — the value is re-validated at that moment.
Rejection requires a reason, leaves the old value untouched, and the employee is
notified either way. Only one pending request per field is allowed.

## 12. EOD reports require an attachment

A daily work report cannot be submitted without at least one attachment
(screenshot, image, PDF or DOC). The API rejects an empty submission with
exactly *"Please upload at least one attachment before submitting your EOD
report."* and keeps what the employee typed as a **Draft**, so nothing is lost;
the blocked attempt is audit-logged. Saving a draft needs no attachment.

Logging out is gated on a report that is both submitted *and* carries an
attachment, and the logout prompt says which of the two is outstanding.
Logging out still never marks a report as submitted.

## 13. Intern payslip download permission and requests

Regular employees can view and download their payslip as soon as the salary is
credited. **Interns can always view it, but can only download it once HR
approves that specific payslip** — approval never carries across pay periods.

`SalaryRecord.intern_download_allowed` is the single source of truth the
download endpoint checks. There is no second permission system: approving a
request sets that flag on that one record.

**The request workflow.** An intern clicking *Request Download* opens a dialog
asking why they need the payslip. The reason is mandatory — empty, whitespace-
only and content-free reasons are all rejected by the server, not just the
browser. The request lands in HR's **Payslip Requests** queue with the intern's
name, employee ID, pay period and reason. HR approves (optionally with remarks)
or rejects (a reason is required, and the intern is told what it was).

Intern button states mirror the server's own answer:

| Situation | Buttons |
| --- | --- |
| Before requesting | View Payslip · Request Download |
| Request pending | View Payslip · Request Pending (disabled) |
| Approved | View Payslip · Download Payslip |
| Rejected | View Payslip · Request Again, with HR's remarks |

Only one pending request per payslip is allowed; a rejected one can be raised
again. `GET /api/salaries/{id}/payslip/download` returns 403 with *"Download
permission has not been granted by HR."* if called directly, whatever the UI
shows. Whether someone is an intern is read from their employee record, never
from a value the client sends. Requests, approvals, rejections, denied attempts
and successful intern downloads are all audit-logged, and every transition
notifies through the existing notification system.

## 14. Payslips

`POST /api/salaries/{id}/payslip/generate` builds a PDF with ReportLab matching
the supplied company format: logo, company name and address, a two-column
employee information grid, blue-header Earnings / Deductions tables with
alternating row shading, totals, net pay, the figure and its amount in words,
an employer signature rule, and a system-generated footer.

`GET /api/salaries/{id}/payslip/download` streams it. HR may download any
payslip; an employee may download only their own. The in-app HTML preview mirrors
the PDF so what is seen on screen is what prints.

HR can also upload an externally prepared PDF instead of generating one.

---

## 15. API surface

92 endpoints grouped as:

```
/api/auth               login, logout, forgot/reset/change password, me
/api/employees          CRUD, search/filter/sort/paginate, self-profile, photo,
                        id-card (+pdf), profile-lock, issue-id
/api/departments        list + HR CRUD
/api/internship-backgrounds
                        list + HR CRUD
/api/documents          checklist, upload, versions, download, verify/reject/
                        re-upload request, requirements, DELETE -> 403
/api/profile-change-requests
                        raise, list/filter/search, approve, reject, fields
/api/payslip-download-requests
                        list/filter/search, read, approve, reject (HR)
/api/uan                submit/update, HR verify/reject, history
/api/salaries           CRUD, components, payslip generate/upload/download, credit,
                        payslip-permission (intern download grant),
                        download-request (intern asks HR, with a reason)
/api/notifications      list, unread count, mark read, mark all read
/api/meetings           list, today, HR create/edit/cancel
/api/reports            list, today, create/submit, attachments, review,
                        logout-check
/api/audit-logs         activity, email log, action list (HR only)
/api/dashboard          /hr and /employee aggregates
/api/settings           HR read/write, employee-readable subset
```

---

## 16. Notes

- The logo's wordmark is pure white, so `assets/logo/rocket-genie-logo-dark.png`
  is a recoloured copy for light backgrounds; the hexagon-only crop
  (`rocket-genie-mark.png`) is used in the payslip PDF and as the favicon.
- `uploads/` is excluded from the static mount by design. Do not move it inside
  `frontend/`.
- Roles live in a `roles` table and permissions are checked through a single
  dependency layer, so adding a third role (say, Team Lead) does not require
  touching every route.


## New updates in this build

### HR My Profile
- Added `frontend/hr/profile.html` and HR navigation entry **My Profile**.
- HR uses the existing `/api/employees/me` profile workflow.
- HR receives the same `RGEMP###` unique ID sequence used by employees once the mandatory profile is complete.
- HR can update the supported profile fields and upload a profile photograph.
- HR electronic ID card uses the same stored profile photo and is labeled **HR Identity Card**.

### Leave Request workflow
- Employees and interns can request leave from their **Daily Reports** page.
- Leave form includes leave type, from date, to date and mandatory reason.
- Requests are persisted in PostgreSQL in `leave_requests`.
- Status lifecycle: `Pending -> Approved` or `Rejected`.
- Only HR can approve/reject.
- Rejection requires HR remarks.
- Employees/interns can see their leave history and current status.
- HR has a dedicated **Leave Requests** queue with status, department and search filters.
- HR dashboard pending-actions now includes pending leave requests.
- In-app notifications are created when a leave is submitted, approved or rejected.
- Alembic migration: `d7e8f9a0b1c2_add_leave_requests.py`.

### Photograph -> ID card
- Uploading the **Photograph** document now also updates the protected employee profile photo.
- The same photo is used by the electronic ID card PDF/UI.
- The ID-generation check runs after Photograph upload, so a complete employee/intern/HR profile can receive its ID automatically.

### Intern portal
- Added `frontend/intern/` as an intern-facing mirror of the employee portal.
- Intern accounts are routed to `/intern/dashboard.html` in the FastAPI-served app.
- Intern scope is restricted in the frontend to accounts whose department is `Internship`; backend role authorization remains unchanged.

### Verification
- Python application modules compile successfully.
- All frontend JavaScript files pass `node --check`.
- Alembic reports a single migration head: `d7e8f9a0b1c2`.
- The leave API tests are included in `backend/tests/test_leave_requests.py`.
