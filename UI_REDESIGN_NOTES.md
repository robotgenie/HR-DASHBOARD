# UI/UX reinvention: five role-specific experiences (round 2)

Frontend only. **The backend is byte-for-byte unchanged** (`diff -rq` against the original ZIP: identical).
No API, schema, permission or business rule was touched. Every figure and record still comes from the existing API.

## Concept exploration: three per role, one chosen

| Role | Concept A | Concept B | Concept C | **Chosen** |
|---|---|---|---|---|
| Admin | Organisation constellation: radial reporting lines + docked data panels | Department "city" treemap with drill-in | Operations wall: tickers and status lamps | **Control Room**: A as the main lens, B as a second lens, C's lamps in the command strip. Adds approval streams, health instruments and a workforce-movement chart |
| HR | Three-pane triage workspace (queues / item stream / detail) | Lifecycle kanban of people | People activity timeline | **Triage workspace**: A, with B's lifecycle as the pipeline ribbon that filters the stream |
| Manager | Team-day swimlanes (one lane per person, 10 AM–6 PM) | Portrait wall of team cards | Project-style kanban | **Team Command Desk**: A, with the manager's own lane pinned and live, plus task flow, deadlines and activity below |
| Employee | Vertical day agenda + guided flow | Checklist only | Focus-timer mode | **Personal Workspace**: A, a date/timer line, a 5-step flow, a vertical agenda and "up next" |
| Intern | Horizontal journey timeline over weeks | Chapters per stage | Skill tree | **Growth Journey**: A, with milestone flags, task bars, feedback pins, an attendance strip and a "today" marker, plus a stage panel |

The others were rejected for these reasons. The treemap or wall alone hides people. Kanban and wall layouts lose the time of day, which is what attendance and hourly rules are about. A checklist alone has no sense of time. A skill tree would need data the system does not record.

## What each experience is now
- **Admin: Organisation Control Room.** Full-bleed light blueprint canvas; the navigation becomes an overlay drawer.
  - Command strip: a Ctrl+K search over pages, people and departments, plus live status lamps.
  - Left: seven organisation-health instruments and the workforce composition.
  - Centre, *Organisation Lens*: a radial constellation of the whole hierarchy, every person coloured by today's attendance state. A second lens shows a department treemap, sized by headcount and shaded by check-ins, with drill-in.
  - Right: priority alerts, and expandable approval streams showing the first real pending records.
  - Below: workforce movement (check-ins and check-outs through the day), expandable HR branches, the three pipelines, late check-ins and the organisation log.
- **HR: People Operations Workspace.** Editorial header with a compact "My day" bar (Check-In/Out plus an expandable attendance, reports and leave panel). Under it, a lifecycle pipeline ribbon (Onboarding → Documents → Attendance → Leave → Work reports → Payroll), then three panes:
  - Smart queues, with a search filter.
  - A unified stream of every open item, ageing-flagged and sortable.
  - A detail pane with the record, a file preview, actions, and expandable employee information.

  Then the floor, meetings, new people, tabbed insights charts, and every HR workflow link.
- **Manager: Team Command Desk.** "My Team" as swimlanes across the working day:
  - Per lane: each hourly period, the check-in pin, leave, Noon/EOD state, workload and a now-line.
  - Lanes expand to show tasks and links.
  - Your own lane is live, with Check-In/Out and submit-able hourly slots.
  - Below: task flow, deadlines, team activity, then "My work" tabs (day, pay and records, notifications).
- **Employee: Personal Workspace.**
  - Top line: date, a live working timer, and Check-In/Out.
  - *Today's flow*: check in → hourly updates → Noon → EOD → check out, with the next action inline.
  - A vertical agenda showing hourly periods (clickable), meetings, report deadlines, the working session and now.
  - *Up next* and *To complete*.
  - A shelf of month, pay, documents, profile, notifications and today's reports.
- **Intern: Growth Journey.**
  - Header with internship week and guides (reporting manager and HR).
  - A horizontal timeline from the joining week: milestone flags, task bars filled by progress, feedback pins, an attendance strip, and a Today button.
  - A seven-step milestone stage with the next milestone.
  - Today (attendance, hourly, leave, reports), assigned work, feedback, growth signals and sessions.
  - Records.

Shared across every portal page: role themes and navigation (`css/roles.css`, `js/common.js`), and a **Ctrl+K command palette**, which only navigates and performs no actions.

## Functionality preserved
- Same API calls as before for every original panel; extra calls are read-only GETs to existing endpoints (listed in each dashboard script's header).
- All actions run through the original code paths: `RGWork` (selfie Check-In/Out, late-login dialog, Check-Out report gate, hourly form, hourly reminders and popup), `RG.leaveModal`, payslip PDF download, notification read/delete, document file download.
- Approvals and decisions remain on their module pages. The workspaces link straight to them; no business logic was duplicated in the dashboards.
- Navigation: every original entry is kept with the same `href`/`key` (Admin 25, HR 25, Manager 18, Employee 11, Intern 11).

## Honest notes
- The Manager lane colour for each hour is drawn from submitted updates plus the day's rules. The counts shown come from the API.
- Intern milestones use recorded facts only. There is no evaluation or completion data, so those stages are not shown. "Mentor" is shown as reporting manager plus reporting HR, because no separate mentor field exists.
- There is no "Review" task status, so task flows use To do, In progress and Completed (cancelled tasks are hidden).

## Verification (local: SQLite + seeded data + live check-ins/tasks created through the API, Chromium)
- Backend: `pytest` **311 passed**. Project verifiers match the original: `verify_frontend` (97 pages + 210 assets), `verify_requested_updates` 8/8, `verify_all_functionalities` 17/17.
- End-to-end browser checks: **49/49**. They cover:
  - Real selfie Check-In for Intern, Manager and HR, and Check-Out for Employee.
  - Hourly update from the agenda and the slots, and leave requests in four portals.
  - Notification actions.
  - HR queue filter, search, detail pane, file preview and employee details.
  - Manager lane expansion, tabs, and keyboard dropdown.
  - Admin lens switch, department drill-in, Ctrl+K jump, overlay menu and node links.
  - Every chart, with no page errors and no 5xx.
- All **94 portal pages** load with the correct nav item active.
- No horizontal overflow at 360 / 390 / 820 / 1100 / 1440 / 1920 px.
- axe-core WCAG 2 A/AA: **0 violations** on all five dashboards.

Not verified here: PostgreSQL, a physical camera/GPS, and Safari/Firefox. Google Fonts and Chart.js were served from identical local copies during tests.
