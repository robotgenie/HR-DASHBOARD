# Verification report — Bank details + salary slip automation (2026-10-03)

| Run | Result |
|---|---|
| `pytest tests` on SQLite | **306 passed** |
| `RG_TEST_DB=postgres pytest tests` on PostgreSQL 16 | **306 passed** |
| `alembic upgrade head` → `downgrade -1` → `upgrade head` on a copy of the demo database (21 employees, 70 salary records) | OK, row counts unchanged, no model/DB drift |
| `generate_monthly_salaries.py` twice on that copy | 1st: 1 created; 2nd: 0 created (no duplicates); 1 skipped as last salary too old; future month refused |
| Browser end-to-end (Chromium, 1366 px + 390 px) | all checks passed, no page errors |

| # | Acceptance test | Where verified |
|---|---|---|
| 1 | Employee creation needs no bank details | `test_01_*` |
| 2 | Bank Details fields on Documents (MANDATORY), no extra nav item | `test_02_*`, browser |
| 3 | Validation (missing, mismatch, IFSC, PAN, digits) | `test_03_*` (11 cases, API), browser (client) |
| 4 | Confirmation screen, masked account, checkbox gates submit | `test_04_*`, browser |
| 5 | Pending Approval after submit; masked in HR list | `test_05_*`, browser |
| 6 | HR/Admin approve; HR B / Manager / employees refused | `test_06_07_*` |
| 7 | Payslip shows approved Bank Name / Account / PAN; no IFSC or new rows | `test_06_07_*` (PDF text), demo-DB PDF |
| 8 | Reject with reason, employee sees it, resubmits, approved values unchanged meanwhile | `test_08_*`, browser |
| 9 | Next month generated automatically (unattended job), same structure, scoped per HR | `test_09_*`, `test_09b_*`, CLI |
| 10 | No duplicate slip; duplicate create → existing slip opened | `test_10_*`, browser |
| 11 | Payment-only edit of the generated slip; PDF follows amounts | `test_11_*` |
| 12 | Existing edit still works on manual slips | `test_12_*`, existing `test_salary.py` |
| 13 | Privacy / authorization | `test_13_*` |

Remaining limitations of this update:
* Demo/legacy employees who already had bank details stored count as approved; they have no
  IFSC until they use "Change bank details" (the page tells them).
* The background loop runs inside the API process; with the API stopped, use the CLI on a
  system scheduler (both are safe to run together).
* An employee's very first salary record (or one after more than 3 months' gap) is still
  created by HR; the automation copies from an existing month.

---

# Verification report — Admin, Manager & hierarchy release

Date: 1 Oct 2026 · Alembic head `d1e2f3a4b5c6` · Python 3.11 · PostgreSQL 16

How things were verified:
* **Automated tests** (`pytest`, real API calls through FastAPI's TestClient) on SQLite **and** PostgreSQL.
* **Migration** run on a PostgreSQL database built with the *original* code and seed data, then
  downgraded and upgraded again; `alembic check` reports models and schema identical.
* **Browser**: headless Chromium (Playwright, test harness only — not part of the project) logged in
  as Admin, HR, Manager, Employee and Intern and opened **every navigation entry of every portal
  (90 pages)** watching for script errors, failed API calls and error panels; plus a 25-step
  end-to-end run with a fake camera and geolocation (selfie check-in, leave chain, tasks, Excel,
  hierarchy changes, phone width).

---

## 1. Test results

| Suite | Result |
|---|---|
| `pytest tests` (SQLite) | **283 passed** |
| `RG_TEST_DB=postgres pytest tests` (PostgreSQL 16) | **283 passed** |
| of which original suite | 248 (247 unchanged + 1 updated: HR now checks in — required by §4/§18) |
| `tests/test_hierarchy.py` (new) | 28 passed |
| `tests/test_excel.py` (new) | 7 passed |
| Browser sweep, 5 roles × every nav page (90 pages) | 0 script errors, 0 failed API calls, 0 error panels, 0 wrong redirects |
| Browser end-to-end (fixed clock 10:20 AM IST) | **25 / 25 passed** (list in §5) |
| Migration on legacy PostgreSQL data | upgrade ✔, downgrade ✔, re-upgrade ✔, `alembic check`: no differences |
| Static checks: `python -m py_compile`, JS parse of every `frontend/js/*.js` | all pass |
| Legacy scripts `verify_spec.py` 38/38, `verify_requested_updates.py` 8/8, `verify_all_functionalities.py` 17/17, `verify_frontend.py` all 200 | pass |
| Legacy `verify_update.py`, `verify_workflows.py` 50/51, `verify_controls.py` | same failures as the **original** code on a fresh seed (pre-existing, time-of-day / data dependent) — plus 2 expected differences: `verify_controls` filters salaries/reports by Teaching/Marketing **as HR Ananya**, and those departments now belong to HR Rohit's hierarchy, so HR Ananya correctly gets 0 rows |

## 2. Required test cases (§32) and API security tests (§33)

All of these are executed against the API in `tests/test_hierarchy.py` / `tests/test_excel.py`
(✔ = automated test) and, where marked 🌐, also in the browser.

| Case | Status |
|---|---|
| Admin login works / reaches Admin Dashboard | ✔ 🌐 |
| Admin has no check-in/check-out | ✔ (status not applicable, check-in 403, hourly 404) 🌐 |
| Admin views all HRs / managers / employees / interns | ✔ |
| Admin filters by department (and by HR) | ✔ |
| Admin monitors HR reports, leave, tasks, documents, salary | ✔ 🌐 |
| HR login → HR Dashboard; HR check-in/out with the employee flow; own attendance | ✔ 🌐 |
| HR sees assigned managers and their employees/interns | ✔ 🌐 |
| HR cannot access another HR's hierarchy (profile, attendance, documents, edits, tasks, leave) | ✔ 🌐 |
| Manager login → Manager Dashboard; check-in/out (late-login rule applies) | ✔ 🌐 |
| Manager sees own team; reviews team reports; first-level leave; assigns/divides tasks | ✔ 🌐 |
| Manager cannot access another manager's team | ✔ 🌐 |
| Employee / Intern existing flows; own reports, leave, documents, salary | ✔ (existing 248 tests + new) 🌐 |
| Employee A → Employee B denied; Intern A → Employee B denied | ✔ 🌐 |
| Manager A → employee of Manager B **denied (403)** | ✔ 🌐 |
| HR A → employee of HR B **denied (403)** | ✔ 🌐 |
| Admin → any employee **allowed** | ✔ |
| HR A → manager of HR A **allowed** | ✔ |
| Manager A → employee of Manager A **allowed** | ✔ |
| Refusals are audit-logged | ✔ |

## 3. Requirement-by-requirement

| § | Requirement | Where | Status |
|---|---|---|---|
| 1 | Extend, don't replace; existing HR dashboard intact | all original pages/APIs kept; 247/248 original tests unchanged | Done |
| 2 | Hierarchy ADMIN → HR → MANAGER → EMPLOYEE/INTERN | `roles` rows, `employees.reporting_hr_id`, `reporting_manager_id`, `hierarchy_service` | Done |
| 3 | Admin is not an employee, no attendance | no employee record; check-in/status/hourly refuse the Admin; no check-in UI | Done |
| 4 | HR/Manager/Employee/Intern use the employee-side features; role-based dashboards | HR "My day" + "My work" pages; Manager portal reuses employee pages | Done |
| 5 | Separate Admin Dashboard, same design language, HR first | `admin/dashboard.html`, `admin-dashboard.js` | Done |
| 6 | Admin org-wide access with filters (dept, HR, manager, type, date, month, report type, status, leave type, task status, document status) | list APIs + Admin pages filters | Done |
| 7 | HR monitoring drill-down (profile → … → managers → teams) | `admin/hr-monitoring.html?id=`, `/api/admin/people/{id}/overview` | Done |
| 8 | HR sees only own hierarchy | `visible_ids_select`; tests | Done (see unassigned-pool note) |
| 9 | Manager has Reporting HR; manages only own team | validation + scope; tests | Done |
| 10 | Reporting chain stored in DB and used consistently | columns + `reporting_chain` in profile/monitoring | Done |
| 11 | Centralized hierarchy/authorization service | `app/services/hierarchy_service.py` (all named functions provided) | Done |
| 12 | Hierarchy in every module (23 listed) | attendance, check-in monitoring, selfies, leave (+approval), Noon/EOD/hourly/work reports, tasks (+assignment, division), documents (+verification), salary (+slips), monthly reports, employee/intern/manager/HR profiles, notifications, plus UAN, profile changes, payslip requests, dashboard, audit/email logs, Excel | Done |
| 13 | Leave flow Employee → Manager → HR → Admin; Manager → HR; HR → Admin; half-day rules kept | `leave_service.decide`, `approval_stage` | Done |
| 14 | Work-report flow; drafts/attachments/review kept | `reports.py` | Done |
| 15 | Task flow incl. division; department filters | `task_service`, `/tasks/{id}/divide`, task centre | Done |
| 16 | Document flow; mandatory/optional + approval kept | `documents.py` levels | Done |
| 17 | Salary: Admin/HR manage; Manager no access; own salary kept | `salaries.py` sensitive/manage levels | Done |
| 18 | Attendance rules kept (late login, reason, HR exception, check-out rules, extra hours, half day) | `attendance_service` unchanged except the role gate | Done |
| 19 | Admin profile separate | `users.full_name/phone/title`, `admin/profile.html` | Done |
| 20 | Role-based login routing, one auth system | `auth_service.portal_for/home_for`, `auth.js` | Done |
| 21 | Existing HR dashboard preserved | same layout; adds "My day", scoped figures | Done |
| 22 | Employee/intern dashboards preserved | unchanged except leave wording | Done |
| 23 | Department-wise monitoring from DB data | `admin/departments.html`, filters; employee form now loads departments from DB | Done |
| 24 | DB changes via Alembic, no data loss, no duplicate models | migration `d1e2f3a4b5c6` | Done |
| 25 | Backend enforcement, not UI hiding | every rule server-side; 403 tests | Done |
| 26 | Frontend reflects permissions; nav per role | per-portal nav; guard in `RG.boot` | Done |
| 27 | Notifications respect hierarchy; delete-after-read kept | personal notifications; routing to manager/HR/Admin | Done |
| 28 | Monthly reports per hierarchy with existing calculations | `/attendance/hr/monthly-summary` scoped; salary hidden from managers | Done |
| 29 | Data privacy per role | levels view/sensitive/supervise/manage | Done |
| 30 | Don't break existing functionality | 247 original tests unchanged & passing; 90-page browser sweep | Done |
| 31 | Implementation order incl. migrations, seed, tests | — | Done |
| 39-A | Excel import of employee fields | `excel_service.COLUMNS` (+ emergency contacts, internship details) | Done |
| 39-A | 14 validations | `validate_rows` | Done |
| 39-B | Preview with totals and categories | preview counts + table | Done |
| 39-C | Downloadable error report (7 columns) | `/excel/import/{token}/errors` | Done |
| 39-D | Hierarchy validation incl. manager-belongs-to-HR, no circular lines | `validate_rows` + `validate_assignment` | Done |
| 39-E/F | Exports (16 kinds via 10 export types + filters), permission-scoped, department-wise | `/excel/export` | Done |
| 39-G | Template with dropdowns from the DB | Reference sheet + data validation | Done |
| 39-H | Employee ID generation preserved; format validated; no overwrite | `RG-YYYY-NNNN`; create mode rejects existing IDs | Done |
| 39-I | Bulk update with old/new values and hierarchy confirmation | preview diff; 428 until confirmed | Done |
| 39-J | Audit log for import/export without file contents | `excel_import_previewed/confirmed`, `excel_exported` | Done |
| 39-K | Same role hierarchy for Excel | Admin all, HR own hierarchy, Manager team export (no salary), employees own | Done |
| 39-L | openpyxl | `requirements.txt` | Done |
| 39-M | No second source of truth | imports go through `employee_service` / `hierarchy_service` | Done |

## 4. Database changes

New migration `backend/migrations/versions/d1e2f3a4b5c6_admin_manager_hierarchy.py`:

| Object | Change |
|---|---|
| `roles` | rows `ADMIN`, `MANAGER` added; `HR_ADMIN` relabelled "HR" (name kept for compatibility) |
| `users` | + `full_name`, `phone`, `title` (Admin profile) |
| `employees` | + `reporting_hr_id` (FK employees, SET NULL, indexed), + `internship_details`; index on `reporting_manager_id` |
| `leave_requests` | + `approval_stage` (default 'HR', indexed), `manager_status`, `manager_remarks`, `manager_reviewed_at`, `manager_reviewed_by_id` (FK users) |
| `work_tasks` | + `parent_task_id` (FK work_tasks, SET NULL, indexed) |
| `excel_import_batches` | new table (token, creator, file name, mode, status, counts, normalised rows/errors JSON — cleared of raw rows after confirm) |
| `app_settings` | + `hr_sees_unassigned` = true |

Data normalisation on upgrade (verified on the original seed): an HR selected as "reporting manager"
becomes the Reporting HR; HR accounts lose reporting lines; employees that others report to are promoted
to MANAGER (interns are not — the reference is cleared); managers never report to managers; with exactly
one active HR, all unassigned people are assigned to that HR; employees inherit their manager's HR; pending
leave stays at the HR stage (pending HR leave moves to the Admin); decided leave is marked Closed.

## 5. Browser end-to-end steps (all passed)

HR lands on HR dashboard · HR selfie check-in without late reason · Manager dashboard shows team panel ·
Manager late check-in with reason dialog · Manager team page lists only own team · Manager API call for
another manager's employee denied · Employee leave starts at Manager stage · Employee can't open another
employee · Manager approval forwards leave to HR · Other HR cannot approve · HR final approval closes ·
HR assigns task to manager in the UI · Manager divides it into sub-tasks · Admin lands on Admin dashboard ·
no check-in on Admin dashboard · HR monitoring shows the HR checked in · HR monitoring shows managers and
teams · Excel preview flags invalid rows and the hierarchy error · error report downloads · confirm imports
only the valid row · imported person follows the hierarchy · Admin export downloads · Admin moves a person
to another manager and the HR follows · Admin dashboard and Organization page fit a 390 px phone.

## 6. Files changed

**New — backend:** `app/services/hierarchy_service.py`, `app/services/excel_service.py`, `app/api/hierarchy.py`,
`app/api/admin.py`, `app/api/excel.py`, `app/models/excel_import_batch.py`,
`migrations/versions/d1e2f3a4b5c6_admin_manager_hierarchy.py`, `create_admin.py`, `tests/test_hierarchy.py`,
`tests/test_excel.py`.

**Changed — backend:** `app/api/{__init__,attendance,audit_logs,auth,dashboard,documents,employees,hourly_updates,intern_payslip_requests,leave_requests,profile_change_requests,reports,salaries,serializers,settings,tasks,uan}.py`,
`app/core/{constants,dependencies}.py`, `app/models/{__init__,daily_report,employee,leave_request,user,work_task}.py`,
`app/schemas/{auth,employee,leave,report}.py`,
`app/services/{attendance_service,auth_service,employee_service,hourly_service,intern_payslip_request_service,leave_service,profile_change_service,settings_service,task_service}.py`,
`requirements.txt`, `seed_data.py`, `tests/conftest.py`, `tests/test_attendance_leave_rules.py`.

**New — frontend:** `admin/` (25 pages), `manager/` (19 pages), `hr/{excel,hierarchy,person,tasks,my-work,my-reports,my-documents,my-salary,my-monthly-report}.html`,
`js/{admin-dashboard,admin-profile,departments,excel,manager-dashboard,monthly-summary,org,people,person,tasks}.js`, `css/hierarchy.css`.

**Changed — frontend:** `js/{api,auth,common,documents,employee-dashboard,employees,hr-dashboard,leave-requests,meetings,profile,reports,salary,settings,uan,work-monitor,work}.js`,
`css/{forms,sidebar,tables}.css`, `login.html`, `hr/monthly-reports.html` (was a redirect, now the hierarchy summary),
and every existing page head (two stylesheet links added: `work.css`, `hierarchy.css`).

**Docs:** `README.md` (new release guide on top; original README kept below), `CHANGELOG.md`, this report.

## 7. Behaviour changes to be aware of

1. **HR now checks in and out** (selfie + location) and must submit Noon/EOD reports to check out,
   like every employee (§4, §18). HR keeps the existing exemption from the late-login rule.
2. **HR sees only their hierarchy.** With several HRs and legacy data, people without a Reporting HR
   stay visible to all HRs until the Admin assigns them (setting *HR can see unassigned people*);
   with exactly one HR the migration assigns everyone to that HR.
3. **HR's own records are handled by the Admin**: HR can't approve their own leave, verify their own
   documents, create/edit their own salary or edit their own record from the directory (own profile
   page still works).
4. Existing pending leave keeps HR as the deciding stage; new requests from employees with a manager
   start at the manager.

## 8. Remaining limitations (honest list)

* Real-device camera / GPS and SMTP delivery were exercised with Chromium's fake camera, fixed
  geolocation and the logged-email fallback, not physical devices or a real mail server.
* Excel import validates *designations* as free text (length/characters) because the HRMS has no
  designation master table; the template offers existing designations as non-binding suggestions.
* The "Internship Details" column is stored in a new free-text field (`employees.internship_details`).
* Exports and imports are synchronous and capped (2 000 rows per import); very large organisations
  would want background jobs.
* Meetings remain department-scoped (unchanged); they are not part of the reporting hierarchy.
* The Windows `backend/venv` shipped in the original ZIP is left as-is; run
  `pip install -r requirements.txt` in it to add `openpyxl`.
* Legacy `verify_update.py` / `verify_workflows.py` / `verify_controls.py` already had failures with
  the original code on a fresh seed (time-of-day and data dependent); they were not rewritten.
