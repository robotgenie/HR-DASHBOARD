# Changelog

## 2026-10-05 - Dashboard reinvention, round 2 (frontend only)
- Admin Organisation Control Room (constellation + department lens, lamps, approval streams, workforce movement).
- HR People Operations Workspace (pipeline ribbon, smart queues, item stream, detail pane).
- Manager Team Command Desk (team swimlanes with a live own lane, task flow, deadlines, activity).
- Employee Personal Workspace (today's flow, vertical agenda, up next).
- Intern Growth Journey (horizontal timeline of milestones, tasks, feedback and attendance).
- Ctrl+K command palette on every portal page. Backend unchanged. See `UI_REDESIGN_NOTES.md`.

## 2026-10-05 - Role-specific dashboard redesign (frontend only)
- Five distinct experiences: Admin Command Center, HR People Operations Hub, Manager Team Operating Desk, Employee My Workday, Intern Learning & Growth Journey.
- Role-themed shell on every portal page (`css/roles.css`); role-grouped navigation with all original routes kept.
- Backend unchanged. See `UI_REDESIGN_NOTES.md` for details and verification.

## 2026-10-03 — Work location on salary slips

Alembic head moves from `e2f3a4b5c6d7` to **`f3a4b5c6d7e8`** (adds one setting row; no schema change).

- **Fixed:** the payslip "Location" was blank ("-") for every employee created through the app:
  it reads `employees.work_location`, which only the demo seed script ever filled.
- Employee create/edit form, `POST/PUT /api/employees` and the employee detail now have
  **Work location** (max 120 chars, trimmed; blank = company default).
- Settings → Company information → **Default work location** (`default_work_location`). The
  migration fills it with the work location most existing employees already have (empty if none).
- Payslips print the employee's work location, else the default, else "-".
- Changing an employee's work location (form or Excel) or the default re-renders generated
  payslips that are not yet credited; credited payslips keep what they printed.
- Excel: "Work Location" column in the template (after Address), import (create + bulk update)
  and the employees export.
- Profile, person view and employee detail show the work location.
- Tests: `tests/test_work_location.py` (5). 311 passing on SQLite and PostgreSQL.

## 2026-10-03 — Bank details approval + automatic monthly salary slips

Alembic head moves from `d1e2f3a4b5c6` to **`e2f3a4b5c6d7`** (additive, existing data kept).

### Added
- **Bank Details** section inside the Documents page (employee, intern, manager, HR "My documents"):
  mandatory Bank Name, Account Number + confirmation, IFSC, PAN; client + server validation;
  masked review screen with the confirmation checkbox; Submit for Approval.
- `bank_detail_requests` table (history of submissions), `employees.ifsc_code`,
  `employees.bank_details_approved_at`. Approved values stay on the existing
  `bank_name / bank_account_no / pan_number` columns, which payslips already print.
- HR/Admin approval: Documents → **Bank details** tab (masked list, reveal full number in the
  review dialog, approve / reject with reason). Hierarchy enforced by `hierarchy_service`
  (manage level: never your own, never a Manager; HR's own details → Admin). Audited
  (submitted / approved / rejected / viewed) and notified.
- Login onboarding redirect to Documents also covers missing approved bank details.
- `salary_autogen_service`: creates each month's salary record from the previous month
  (`salary_records.auto_generated`, `generated_from_id`); background loop in the API process,
  `generate_monthly_salaries.py` CLI, `POST /api/salaries/auto-generate`, Settings switch
  `salary_auto_generate`, config `SALARY_AUTOGEN_ENABLED / _INTERVAL_MINUTES / _MAX_BACKFILL_MONTHS`.
- Payroll: "Generate this month" button and an *Auto* chip on generated records.

### Changed
- `PUT /api/salaries/{id}` refuses `employee_id / period_year / period_month` (payment-only edit)
  and re-renders an existing generated payslip PDF when amounts or days change.
- Duplicate `POST /api/salaries` answers 409 with `code: SALARY_EXISTS` and the existing id;
  the UI opens that record for editing.
- Approving bank details re-renders generated payslips that are not yet credited (credited
  ones only when the employee had no approved details before).

### Tests
- `tests/test_bank_details_salary.py` (23). 306 passing on SQLite and PostgreSQL.

## 2026-10-01 — Admin, Manager & reporting hierarchy

Alembic head moves from `c9d0e1f2a3b4` to **`d1e2f3a4b5c6`** (additive migration, existing data kept).

### Added — roles and hierarchy
- **ADMIN** role: organisation administrator with no employee record. No check-in/check-out,
  no attendance, no hourly updates, no employee profile. Admin profile lives on `users`
  (`full_name`, `phone`, `title`).
- **MANAGER** role: an employee who supervises the employees/interns reporting to them.
- Reporting hierarchy stored in the database: `employees.reporting_hr_id` (new) and
  `employees.reporting_manager_id` (existing, now validated to point at a Manager).
  Employees' Reporting HR is kept in sync with their manager's HR; moving a manager moves the team.
- `app/services/hierarchy_service.py` — the single authorization engine:
  `visible_ids_select / restrict / restrict_sensitive / restrict_managed`,
  `get_subordinates / get_direct_reports / get_team / get_reporting_manager / get_reporting_hr / reporting_chain`,
  `can_access_employee / can_view_sensitive / can_supervise_employee / can_manage_employee`,
  `can_access_report / can_review_report / can_access_leave / can_act_on_leave / can_access_task /
  can_edit_task / can_assign_task / can_access_document / can_access_salary`,
  `validate_assignment / authorize_assignment / apply_assignment`, `hierarchy_tree`, `candidates`.
- Setting `hr_sees_unassigned` (Admin-only): whether every HR sees people without a Reporting HR.
- Access refusals are audited as `access_denied`.

### Changed — every module now follows the hierarchy (backend)
- `require_hr` now means HR **or** Admin authority; every route then scopes data through the engine.
  New dependencies `require_admin`, `require_supervisor`. `assert_can_access_employee` takes a level
  (`view`, `sensitive`, `supervise`, `manage`).
- **Employees**: list scoped (Admin all, HR hierarchy, Manager team); new filters `role`,
  `person_type`, `reporting_hr_id`, `reporting_manager_id`, `include_self`; create/update accept
  `role`, `reporting_hr_id`, `reporting_manager_id`, `internship_details`; Managers see profiles
  without UAN/salary; edits, activation, ID approval need *manage*. The legacy form value
  (an HR chosen as "reporting manager") is converted to Reporting HR.
- **Attendance**: HR and Managers check in/out with the existing selfie + location flow (HR keeps the
  no-late-login exception); the Admin cannot. Work monitor, late logins, sessions, selfies and
  monthly summaries are hierarchy-scoped, with department / HR / manager / type filters. Monthly
  reports and PDFs hide salary from Managers.
- **Leave**: `approval_stage` (Manager → HR → Admin). Manager approval forwards to HR; HR (hierarchy)
  or the Admin gives the final decision; HR's own leave goes to the Admin. New filters
  `awaiting_me`, `stage`, `leave_type`, dates, HR/manager; outputs carry stage, manager decision and
  `can_act`. Notifications go to whoever acts next.
- **Work reports / hourly updates**: listing scoped (`mine=true` for own); review by Manager/HR/Admin,
  never your own; HR and Managers submit hourly updates.
- **Tasks**: Admin → HR/Manager/Employee/Intern, HR → Manager/Employee/Intern, Manager → team;
  `POST /tasks/{id}/divide` (Manager/HR splits a task among their people, `work_tasks.parent_task_id`);
  department/HR/manager filters, `assigned_by_me`, `mine`.
- **Documents**: queue scoped; verification needs *manage* (HR's own → Admin); Managers see status only.
- **Salary / payslips / UAN / intern payslip requests / profile change requests**: scoped and
  levelled; HR's own salary is managed by the Admin; Managers never see team salary.
- **Dashboard** figures scoped to the viewer; **audit / email logs** scoped for HR.
- **Auth**: role-based routing (`admin | hr | manager | employee | intern`), `/auth/me` returns
  `portal`, `role_label`, reporting line.

### Added — APIs
- `/api/hierarchy/tree | me | team | candidates | employees/{id}` (GET) and `PUT /api/hierarchy/employees/{id}`.
- `/api/admin/dashboard | hr | people | people/{id}/overview | departments/overview | profile | admins`.
- `/api/excel/template`, `/api/excel/import/preview`, `/api/excel/import/{token}`,
  `/api/excel/import/{token}/errors`, `/api/excel/import/{token}/confirm`, `/api/excel/export`,
  `/api/excel/export/types`.

### Added — Excel
- Template with Reference dropdowns (departments, backgrounds, HRs, managers, statuses) and Instructions.
- Preview with per-row validation, counts (total/valid/invalid/duplicates/missing/invalid
  departments/designations/managers/HRs/hierarchy errors), diffs for bulk updates
  (old → new, reporting-line changes flagged), downloadable error report.
- Confirm re-validates, applies valid rows only, requires explicit confirmation of hierarchy
  changes, returns one-time temporary passwords. Never overwrites existing Employee IDs.
- Hierarchy-scoped exports for 10 data sets with filters. Imports/exports audit-logged (counts only).
- New dependency: `openpyxl==3.1.5`.

### Added — frontend (HTML/CSS/vanilla JS, existing design system)
- **Admin console** (`frontend/admin/`): dashboard (HR monitoring first), HR monitoring with a full
  per-HR drill-down (profile → attendance → reports → hourly → tasks → leave → documents → salary →
  managers → teams), Manager/Employee/Intern monitoring, Organization & Hierarchy (tree + reassign),
  departments, attendance & hourly, leave, work reports, tasks, monthly reports, people directory,
  documents, salary, UAN, ID approvals, profile/payslip requests, Excel, meetings, notifications,
  audit logs, Admin profile (+ Admin accounts), settings.
- **Manager portal** (`frontend/manager/`): the employee dashboard plus a team panel, My Team,
  Team attendance & work, Team tasks (assign + divide), Team reports (review), Team leave
  (first-level approval), Team monthly reports, Team export, and all employee self-service pages.
- **HR**: "My day" check-in card on the dashboard; My Hierarchy, Tasks, Monthly Reports (real
  hierarchy summary instead of the old redirect), Excel; "My work" pages (tasks & hourly, daily
  reports & leave, documents, salary slips, monthly report).
- Shared shell: role-aware navigation with section labels, portal routing, one guard for all
  portals; reused page scripts render the right view per folder (`data-view` self/team).
- Employee form: Role, Reporting HR, Reporting manager. Departments now load from the database
  (the old hard-coded id list is only a fallback).
- Leave tables show the approval stage and manager decision.
- `css/hierarchy.css` (tree, chain, Excel preview, person view) built from existing tokens;
  filter controls now sit side by side; search/month inputs share the input style.

### Fixed
- Sidebar avatar requested `/employees/{user_id}/photo` (user id instead of employee id).
- Employee form department ids were hard-coded to one installation's ids.

### Tests
- `tests/test_hierarchy.py` (28) and `tests/test_excel.py` (7) added; conftest seeds the new roles;
  `test_hr_login_and_no_check_in` replaced by `test_hr_checks_in_without_late_login_rule`
  (HR now checks in, per the new requirements). 283 passing on SQLite and PostgreSQL.
