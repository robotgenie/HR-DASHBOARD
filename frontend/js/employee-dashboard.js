/* employee-dashboard.js - the personal dashboard engine shared by the
   Employee, Intern and Manager portals.

   Data and actions (unchanged): /dashboard/employee, /attendance/status,
   /hourly-updates/today and /leave-requests/me, plus Check-In / Check-Out
   (RGWork), hourly updates, leave requests, payslip PDF download and
   notification read/delete - all wired by delegation on the page, so every
   layout only needs to render the same data-* hooks.

   Presentation: each portal registers its own layout in window.RGDashLayouts
   (manager-dashboard.js, intern-dashboard.js) with optional extra read-only
   fetches. The Employee "My Workday" layout lives here and is the default. */
(function () {
  "use strict";
  var SCOPE = document.body.dataset.scope || "employee";
  var TITLES = { employee: ["My Workday", "Today"], intern: ["My Journey", "Learning & growth"], manager: ["Team Desk", "Your team today"] };
  var T = TITLES[SCOPE] || ["Dashboard", "Rocket Genie"];
  var ctx = RG.boot({ scope: SCOPE, active: "dashboard", title: T[0], subtitle: T[1] });
  if (!ctx) return;

  var W = window.RGWork;
  var LAYOUTS = window.RGDashLayouts = window.RGDashLayouts || {};

  function greeting() {
    var h = new Date().getHours();
    if (h < 12) return "Good morning";
    if (h < 17) return "Good afternoon";
    return "Good evening";
  }
  function firstName(emp) { return RG.esc(((emp && emp.full_name) || "").split(" ")[0]); }
  function hhmm(d) { return String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0"); }
  function minutesOf(t) { if (!t) return null; var p = String(t).split(":"); return parseInt(p[0], 10) * 60 + parseInt(p[1], 10); }

  /* ======================= shared building blocks ======================= */
  var B = {
    greeting: greeting, firstName: firstName, minutesOf: minutesOf, hhmm: hhmm,

    loading: function () {
      return '<div class="skeleton" style="height:180px;border-radius:16px;margin-bottom:24px"></div>' + RG.skeletonCards(3);
    },

    card: function (cls, title, link, linkText, body, iconName) {
      return '<section class="dcard ' + (cls || "") + '"><header>' + (iconName ? RG.icon(iconName, 16) : "") + "<h3>" + title + "</h3>" +
        (link ? '<a href="' + link + '">' + linkText + "</a>" : "") + "</header>" + body + "</section>";
    },

    attendance: function (st) { return W ? W.attendanceCard(st) : ""; },

    /* Leave today, upcoming / pending leave, Noon & EOD state. */
    leaveReports: function (st, leaves, reportsHref, leaveOnly) {
      if (!st || !st.applicable) return "";
      var plan = st.plan || {}, rep = st.reports || {};
      function repRow(label, required, done, status, reason, opens) {
        var b = !required ? RG.badge("Not Required") : done ? RG.badge(status === "Reviewed" ? "Reviewed" : "Submitted") : RG.badge("Pending", "warn");
        return "<li><span><b>" + label + "</b>" + (!required && reason ? "<small>" + RG.esc(reason) + "</small>" : "<small>Available from " + opens + "</small>") + "</span>" + b + "</li>";
      }
      var upcoming = (leaves || []).filter(function (l) { return l.status === "Approved" && l.to_date >= String(st.date); })[0];
      var pending = (leaves || []).filter(function (l) { return l.status === "Pending"; }).length;
      return '<ul class="status-list">' +
        "<li><span><b>Leave today</b><small>" + (plan.leave_status ? RG.esc(plan.leave_status) + " · " + RG.esc(W.t12(plan.expected_login) + " – " + W.t12(plan.expected_logout) + " working") : "No approved leave today") + "</small></span>" +
          (plan.leave_status ? RG.badge(plan.leave_status) : RG.badge("Working", "ok")) + "</li>" +
        (upcoming && upcoming.from_date > String(st.date) ? "<li><span><b>Next approved leave</b><small>" + RG.esc(upcoming.leave_type_label || upcoming.leave_type) + " · " + RG.fmt.date(upcoming.from_date) + " · " + RG.esc(upcoming.leave_period) + "</small></span>" + RG.badge("Approved") + "</li>" : "") +
        (pending ? "<li><span><b>Leave requests</b><small>Awaiting approval (manager → HR)</small></span>" + RG.badge(pending + " pending", "warn") + "</li>" : "") +
        (leaveOnly ? "" :
          repRow("Noon Report", rep.noon_required, rep.noon_submitted, rep.noon_status, rep.noon_blocked_reason, "1:00 PM") +
          repRow("EOD Report", rep.eod_required, rep.eod_submitted, rep.eod_status, rep.eod_blocked_reason, "6:00 PM")) +
        "</ul>" +
        '<div class="row wrap mt-3"><button class="btn btn-sm" data-request-leave>Request leave</button>' +
        (leaveOnly ? "" : '<a class="btn btn-sm" href="' + (reportsHref || "daily-reports.html") + '">Daily reports</a><a class="btn btn-sm" href="monthly-report.html">Monthly report</a>') + "</div>";
    },

    tasks: function (st, hourly, emptyLock) {
      var checkedIn = st && st.state !== "not_checked_in";
      if (st && st.applicable && !checkedIn) {
        return '<div class="lock-note">' + RG.icon("calendar", 18) + "<span>" + (emptyLock || "Check in to see today’s assigned tasks.") + "</span></div>";
      }
      return W.taskCards((hourly && hourly.tasks) || []);
    },

    hourlySummary: function (hourly, checkedIn) {
      var applicable = hourly ? hourly.applicable_count : 0;
      var submitted = hourly ? hourly.submitted_count : 0;
      var current = hourly && hourly.current_slot;
      var due = hourly && hourly.due_slots ? hourly.due_slots.length : 0;
      var canSubmit = (hourly && hourly.slots || []).some(function (x) { return x.can_submit; });
      if (!checkedIn) return '<div class="lock-note">' + RG.icon("bell", 18) + "<span>Hourly updates (10 AM – 6 PM) start after Check-In.</span></div>";
      return '<div class="hourly-summary"><div><b>' + (current ? "Current hour: " + RG.esc(current.label) : (hourly && hourly.hourly_active ? "Between hourly periods" : "Hourly updates closed for today")) + "</b>" +
        '<div class="small muted">' + submitted + " of " + applicable + " applicable updates submitted" + (due ? " · " + due + " due" : "") + "</div></div>" +
        '<div class="meter"><div class="bar"><span style="width:' + (applicable ? Math.round(submitted * 100 / applicable) : 0) + '%"></span></div></div>' +
        (canSubmit ? '<button class="btn btn-brand btn-sm" data-hourly-open>Submit hourly update</button>' : "") + "</div>";
    },

    hourly: function (st, hourly) {
      var checkedIn = st && st.state !== "not_checked_in";
      var slots = hourly && hourly.slots ? hourly.slots : [];
      return B.hourlySummary(hourly, checkedIn) + (checkedIn ? W.slotGrid(slots) : "");
    },

    meetings: function (rows, emptyTitle) {
      return (rows || []).length
        ? '<div class="timeline">' + rows.map(function (m) {
            return '<div class="tl-item ' + (m.status === "Cancelled" ? "is-cancelled" : "") + '">' +
              '<div class="tl-time">' + RG.fmt.time(m.start_time) + "</div>" +
              '<div class="tl-card"><div class="tl-main"><div class="tl-dept">' + RG.esc(m.department || "") + "</div>" +
                "<h4>" + RG.esc(m.title) + "</h4>" +
                (m.agenda ? '<div class="tl-agenda">' + RG.esc(m.agenda) + "</div>" : "") + "</div>" +
              '<div class="tl-actions">' +
                (m.google_meet_url && m.status !== "Cancelled"
                  ? '<a class="btn btn-sm meet-btn" target="_blank" rel="noopener" href="' + RG.esc(m.google_meet_url) + '">' + RG.icon("video", 15) + " Join Google Meet</a>"
                  : RG.badge(m.status)) +
              "</div></div></div>";
          }).join("") + "</div>"
        : RG.emptyState(emptyTitle || "No meetings for your department today", "You’ll see them here as soon as HR schedules one.", "", "calendar");
    },

    nextMeeting: function (rows) {
      var now = new Date(), nowMin = now.getHours() * 60 + now.getMinutes();
      var live = (rows || []).filter(function (m) { return m.status !== "Cancelled"; });
      var next = live.filter(function (m) { return minutesOf(m.end_time || m.start_time) >= nowMin; })[0];
      return next || null;
    },

    pay: function (salary) {
      return salary
        ? '<div class="pay-summary"><div><div class="period">' + RG.esc(salary.period_label) + "</div>" +
            '<div class="amount">' + RG.fmt.money(salary.net_pay) + "</div>" +
            "<div>" + RG.badge(salary.status) + "</div></div></div>" +
          '<div class="pay-breakdown"><div><span>Earnings</span><b>' + RG.fmt.money(salary.total_earnings) + "</b></div>" +
            "<div><span>Deductions</span><b>" + RG.fmt.money(salary.total_deductions) + "</b></div>" +
            "<div><span>Worked days</span><b>" + salary.working_days + "</b></div></div>" +
          '<p class="small muted mt-2 mb-0">' + RG.esc(salary.amount_in_words) + "</p>" +
          '<div class="row wrap mt-4">' +
            (salary.has_payslip
              ? '<a class="btn btn-sm btn-primary" href="salary-slips.html?open=' + salary.id + '">View payslip</a>' +
                '<button class="btn btn-sm" data-pdf="' + salary.id + '">Download PDF</button>'
              : '<span class="small muted">The payslip appears here once HR publishes it.</span>') +
          "</div>"
        : RG.emptyState("No salary record yet", "Your first payslip will show up here.", "", "money");
    },

    docs: function (data) {
      var k = data.kpis;
      var rows = (data.document_progress || []).map(function (d) {
        return '<li class="doc-row"><span class="badge ' + RG.tone(d.status) + '">' + RG.esc(d.status) + "</span>" +
          '<span class="truncate" style="flex:1 1 auto">' + RG.esc(d.document_type) + "</span>" +
          '<span class="small muted nowrap">' + (d.uploaded_at ? "v" + d.version_count : "—") + "</span></li>";
      }).join("");
      return '<div class="meter-label"><span>Completed</span><span>' + Math.round(k.documents_percent) + "%</span></div>" +
        '<div class="bar"><span style="width:' + k.documents_percent + '%"></span></div>' +
        '<ul class="doc-list">' + rows + "</ul>" +
        '<a class="btn btn-sm mt-4" href="documents.html">Manage documents</a>';
    },

    notifs: function (data) {
      return (data.recent_notifications || []).length
        ? '<ul class="notif-list">' + data.recent_notifications.map(RG.notificationRow).join("") + "</ul>"
        : RG.emptyState("Nothing yet", "Updates about documents, salary and meetings appear here.");
    },

    /* Today's Noon / EOD state and the Check-Out gate. */
    reportCard: function (report, reportsHref) {
      function reportRow(label, required, done, status, reason, available, opens) {
        var b = !required ? RG.badge("Not Required")
          : done ? RG.badge(status === "Reviewed" ? "Reviewed" : "Submitted")
          : RG.badge(available ? "Required" : "Opens " + opens, available ? "warn" : "");
        return '<li><span><b>' + label + "</b>" + (!required && reason ? "<small>" + RG.esc(reason) + "</small>" : "") + "</span>" + b + "</li>";
      }
      return (report.leave_status ? '<p class="mb-2">' + RG.badge(report.leave_status) + "</p>" : "") +
        '<ul class="status-list">' +
          reportRow("Noon Report", report.noon_required, report.noon_submitted, report.noon_status, report.noon_blocked_reason, report.noon_available, "1:00 PM") +
          reportRow("EOD Report", report.eod_required, report.eod_submitted, report.eod_status, report.eod_blocked_reason, report.eod_available, "6:00 PM") +
        "</ul>" +
        (report.logout_blocked && report.pending_actions && report.pending_actions.length
          ? '<p class="small muted mt-2 mb-0">Before Check-Out: ' + RG.esc(report.pending_actions.join("; ")) + ".</p>" : "") +
        '<div class="row wrap mt-4"><a class="btn btn-sm ' + (report.report_submitted_today ? "" : "btn-brand") + '" href="' + (reportsHref || "daily-reports.html") + '">' +
          (report.report_submitted_today ? "View today’s reports" : "Open daily reports") + "</a>" +
        '<a class="btn btn-sm" href="monthly-report.html">My monthly report</a></div>';
    },

    identity: function (data) {
      var emp = data.employee, k = data.kpis;
      return '<dl class="id-list">' +
        "<div><dt>Employee ID</dt><dd>" + RG.esc(emp.employee_code) + "</dd></div>" +
        "<div><dt>Role</dt><dd>" + RG.esc(emp.designation || "—") + "</dd></div>" +
        "<div><dt>Department</dt><dd>" + RG.esc(emp.department || "—") + "</dd></div>" +
        (emp.internship_background ? "<div><dt>Internship background</dt><dd>" + RG.esc(emp.internship_background) + "</dd></div>" : "") +
        "<div><dt>UAN</dt><dd>" + RG.badge(k.uan_status) + "</dd></div>" +
        "<div><dt>Profile</dt><dd>" + Math.round(k.profile_completion) + '% complete<div class="bar thin mt-2"><span style="width:' + k.profile_completion + '%"></span></div></dd></div>' +
        "<div><dt>Documents</dt><dd>" + RG.esc(k.documents_label) + "</dd></div>" +
        "<div><dt>Salary</dt><dd>" + RG.esc(k.salary_period || "—") + " " + RG.badge(k.salary_status) + "</dd></div>" +
        "</dl>";
    },

    openTasks: function (hourly) {
      return ((hourly && hourly.tasks) || []).filter(function (t) { return t.status === "Pending" || t.status === "In Progress"; }).length;
    },

    reportsDue: function (st) {
      var rep = (st && st.reports) || {};
      return (rep.noon_required && !rep.noon_submitted ? 1 : 0) + (rep.eod_required && !rep.eod_submitted ? 1 : 0);
    },

    /* Chart.js bar of worked hours per day for the current month (personal). */
    monthChart: function (canvasId, month, colour) {
      var canvas = document.getElementById(canvasId);
      if (!canvas || typeof Chart === "undefined" || !month) return null;
      var days = (month.days || []).filter(function (d) { return d.is_working_day && d.date <= todayIso(); });
      return new Chart(canvas, {
        type: "bar",
        data: {
          labels: days.map(function (d) { return String(d.date).slice(8) + " " + d.weekday; }),
          datasets: [{ data: days.map(function (d) { return Math.round((d.worked_minutes || 0) / 6) / 10; }),
            backgroundColor: days.map(function (d) { return d.late_minutes ? "#E39B4D" : (colour || "#C2570C"); }), borderRadius: 4, maxBarThickness: 18 }]
        },
        options: {
          responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false },
            tooltip: { callbacks: { label: function (c) { var d = days[c.dataIndex]; return c.raw + " h worked · " + d.attendance + (d.late_minutes ? " · late " + d.late_minutes + "m" : ""); } } } },
          scales: { x: { grid: { display: false }, ticks: { font: { size: 10 }, maxRotation: 0, autoSkip: true } },
                    y: { beginAtZero: true, suggestedMax: 8, grid: { color: "#EEF0F3" }, ticks: { font: { size: 10 }, callback: function (v) { return v + "h"; } } } }
        }
      });
    }
  };
  function todayIso() { var d = new Date(); return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0"); }
  window.RGDash = { B: B, ctx: ctx };

  /* ================= Employee: PERSONAL WORKSPACE (day planner) =================
     A personal productivity layout instead of a dashboard:
       top line   - date, live working timer, Check-In / Check-Out
       left       - TODAY'S FLOW: check in -> hourly updates -> Noon -> EOD -> check out
       centre     - the day as a vertical agenda (hourly periods, meetings, report
                    deadlines, the working session and a "now" line)
       right      - up next: meeting, things to complete, leave
       shelf      - month, pay, documents, me, notifications
     Every control keeps the engine's hooks (data-check-in/out, data-hourly-*,
     data-request-leave, data-pdf, notification rows). */
  var workTimer = null;
  var employeeLayout = {
    fetch: function () {
      return API.get("/attendance/me").catch(function () { return null; }).then(function (m) { return { month: m }; });
    },
    render: function (data, ex, more) {
      var st = ex.status, hourly = ex.hourly, emp = data.employee, k = data.kpis;
      var applicable = st && st.applicable;
      var s = st && st.session, state = st ? st.state : "not_checked_in";
      var meetings = data.todays_meetings || [];
      var next = B.nextMeeting(meetings);
      var leave = st && st.plan && st.plan.leave_status;
      var blocker = st && !st.can_check_in && state === "not_checked_in" && st.check_in_blocker ? st.check_in_blocker.message : "";

      var top = '<section class="pd-top" aria-label="Today">' +
        '<div class="pd-date"><span>' + RG.esc(new Date().toLocaleDateString("en-IN", { weekday: "long" })) + "</span>" +
          "<b>" + RG.esc(new Date().toLocaleDateString("en-IN", { day: "numeric", month: "long" })) + "</b>" +
          "<em>" + greeting() + ", " + firstName(emp) + "</em></div>" +
        (applicable
          ? '<div class="pd-clock"><div class="pd-state is-' + state + '"><i></i>' + (state === "checked_in" ? "Working now" : state === "checked_out" ? "Day complete" : "Not checked in") +
              (leave ? " " + RG.badge(leave) : "") + "</div>" +
              '<div class="pd-timer"><span data-worked>' + (s ? W.mins(s.worked_minutes) : "0h 00m") + "</span><small>" + (s ? "since " + W.t12(s.check_in_time) + (s.checked_out ? " · out " + W.t12(s.check_out_time) : "") : "worked today") + "</small></div>" +
              (s ? '<div class="pd-facts">' +
                "<span>" + (s.late_minutes ? '<b class="bad">' + RG.esc(s.late_label) + " late</b>" : '<b class="ok">On time</b>') + "</span>" +
                "<span>Period <b>" + RG.esc(s.work_period || "Full Day") + "</b></span>" +
                (s.extra_minutes ? '<span><b class="ok">+' + W.mins(s.extra_minutes) + " extra</b></span>" : "") +
                (s.late_reason ? "<span>Reason: " + RG.esc(s.late_reason) + "</span>" : "") +
                "<span>In: " + W.loc(s.check_in_location) + (s.check_out_location ? " · Out: " + W.loc(s.check_out_location) : "") + "</span>" +
                "<span>Office 10:00 AM – 6:00 PM" + (st.plan && st.plan.expected_login && st.plan.leave_period ? " · today " + W.t12(st.plan.expected_login) + " – " + W.t12(st.plan.expected_logout) : "") + "</span></div>" : "") +
            "</div>" +
            '<div class="pd-cta"><button class="btn btn-brand att-btn" data-check-in' + (st.can_check_in ? "" : " disabled") + ">" + RG.icon("user", 18) + " Check-In</button>" +
              '<button class="btn att-btn att-out" data-check-out' + (state === "checked_in" ? "" : " disabled") + ">" + RG.icon("logout", 18) + " Check-Out</button>" +
              (blocker ? '<p class="att-note">' + RG.esc(blocker) + "</p>" : "") + "</div>"
          : '<p class="muted">Attendance is not tracked for this account.</p>') +
        "</section>";

      var cols = '<div class="pd-cols">' +
        '<section class="pd-flow" aria-labelledby="pd-flow-h"><h2 id="pd-flow-h">Today’s flow</h2>' + (applicable ? flow(st, hourly, data.daily_report) : "") +
          '<div class="pd-leave"><h3>' + RG.icon("calendar", 15) + " Leave</h3>" + (applicable ? B.leaveReports(st, ex.leaves, null, true) : "") + "</div></section>" +
        '<section class="pd-agenda" aria-labelledby="pd-ag-h"><header><h2 id="pd-ag-h">Your day</h2>' + (applicable ? B.hourlySummary(hourly, state !== "not_checked_in") : "") + "</header>" +
          (applicable ? agenda(st, hourly, meetings) : "") + "</section>" +
        '<aside class="pd-next" aria-label="Up next">' + upNext(next, meetings) +
          '<section class="pd-todo"><h2>To complete <a href="work.html">All tasks</a></h2>' + B.tasks(st, hourly) + "</section></aside>" +
      "</div>";

      var shelf = '<div class="pd-shelf">' +
        B.card("pd-w2", "My month", "monthly-report.html", "Monthly report", monthBody(more.month), "calendar") +
        B.card("", "Latest salary", "salary-slips.html", "All payslips", '<div class="inner">' + B.pay(data.latest_salary) + "</div>", "money") +
        B.card("", "Documents", "documents.html", RG.esc(k.documents_label), '<div class="inner">' + B.docs(data) + "</div>", "doc") +
        B.card("", "Me &amp; my records", "profile.html", "Profile", '<div class="inner">' + B.identity(data) + "</div>", "user") +
        B.card("pd-w2", "Notifications", "notifications.html", (k.unread_notifications ? k.unread_notifications + " unread" : "See all"), B.notifs(data), "bell") +
        B.card("pd-w2", "Today’s reports", "daily-reports.html", "Daily reports", '<div class="inner">' + B.reportCard(data.daily_report) + "</div>", "clipboard") +
      "</div>";
      return '<div class="pd">' + top + cols + shelf + "</div>";
    },
    after: function (data, ex, more) {
      if (more.month) B.monthChart("c-month", more.month, "#C2570C");
      if (workTimer) clearInterval(workTimer);
      var s = ex.status && ex.status.session;
      var el = ctx.page.querySelector("[data-worked]");
      if (s && !s.checked_out && el) {
        var base = Number(s.worked_minutes || 0), t0 = Date.now();
        workTimer = setInterval(function () {
          if (!document.body.contains(el)) { clearInterval(workTimer); return; }
          el.textContent = W.mins(base + Math.floor((Date.now() - t0) / 60000));
        }, 15000);
      }
      var ag = ctx.page.querySelector(".ag-scroll"), now = ctx.page.querySelector(".ag-now");
      if (ag && now) ag.scrollTop = Math.max(0, now.offsetTop - ag.clientHeight / 2);
    }
  };

  /* The guided flow of the day. Each step reflects API state only. */
  function flow(st, hourly, report) {
    var s = st.session, state = st.state, rep = st.reports || {};
    var hs = hourly ? hourly.submitted_count : 0, ha = hourly ? hourly.applicable_count : 0;
    var canHourly = ((hourly && hourly.slots) || []).some(function (x) { return x.can_submit; });
    function step(n, status, title, note, action) {
      return '<li class="fs is-' + status + '"><span class="fs-n" aria-hidden="true">' + (status === "done" ? RG.icon("check", 14) : n) + "</span>" +
        '<div class="fs-b"><b>' + title + "</b><span>" + note + "</span>" + (action || "") + "</div></li>";
    }
    function repStep(n, label, req, done, statusTxt, available, opens, reason) {
      if (!req) return step(n, "skip", label, RG.esc(reason || "Not required today"));
      if (done) return step(n, "done", label, RG.esc(statusTxt === "Reviewed" ? "Submitted · reviewed" : "Submitted"));
      return step(n, available ? "now" : "wait", label, available ? "Open now — submit it" : "Opens at " + opens,
        available ? '<a class="btn btn-sm btn-brand" href="daily-reports.html">Write ' + label + "</a>" : "");
    }
    var inStep = s ? step(1, "done", "Check in", W.t12(s.check_in_time) + (s.late_minutes ? " · " + RG.esc(s.late_label) + " late" : " · on time"))
      : step(1, st.can_check_in ? "now" : "wait", "Check in", st.can_check_in ? "Start your day with a selfie check-in" : RG.esc((st.check_in_blocker || {}).message || "Not available yet"),
          st.can_check_in ? '<button class="btn btn-sm btn-brand" data-check-in>Check in now</button>' : "");
    var hStatus = state === "not_checked_in" ? "wait" : (ha && hs >= ha ? "done" : canHourly ? "now" : "prog");
    var outStatus = state === "checked_out" ? "done" : state === "checked_in" ? (report && report.logout_blocked ? "wait" : "now") : "wait";
    return '<ol class="flow">' + inStep +
      step(2, hStatus, "Hourly updates", state === "not_checked_in" ? "Start after Check-In" : hs + " of " + ha + " applicable submitted",
        canHourly ? '<button class="btn btn-sm btn-brand" data-hourly-open>Submit update</button>' : "") +
      repStep(3, "Noon report", rep.noon_required, rep.noon_submitted, rep.noon_status, report && report.noon_available, "1:00 PM", rep.noon_blocked_reason) +
      repStep(4, "EOD report", rep.eod_required, rep.eod_submitted, rep.eod_status, report && report.eod_available, "6:00 PM", rep.eod_blocked_reason) +
      step(5, outStatus, "Check out", state === "checked_out" ? "Done for the day" :
        report && report.logout_blocked && (report.pending_actions || []).length ? "First: " + RG.esc(report.pending_actions.join("; ")) : "Selfie + location at the end of your day",
        state === "checked_in" ? '<button class="btn btn-sm" data-check-out>Check out</button>' : "") +
      "</ol>";
  }

  /* Vertical agenda, 9 AM - 7 PM. Hourly slots keep the same data hooks. */
  function agenda(st, hourly, meetings) {
    var START = 540, END = 1140, PX = 60;
    var slots = (hourly && hourly.slots) || [];
    var s = st.session, now = new Date(), nowMin = now.getHours() * 60 + now.getMinutes();
    function y(m) { return ((m - START) * PX / 60).toFixed(1); }
    var lines = "";
    for (var h = 9; h <= 19; h++) lines += '<div class="ag-hour" style="top:' + y(h * 60) + 'px"><span>' + ((h % 12) || 12) + (h < 12 ? " AM" : " PM") + "</span></div>";
    var TONE = { "Submitted": "ok", "Due": "due", "Open": "open", "Missed": "due", "Upcoming": "up", "Not Applicable": "na", "Not Checked In": "na" };
    var blocks = slots.map(function (x) {
      var m = minutesOf(x.start || (10 + x.slot_index) + ":00");
      var tone = TONE[x.status] || "na";
      var attr = x.can_submit ? 'data-hourly-slot="' + x.slot_index + '"' : (x.update_id ? 'data-hourly-view="' + x.update_id + '"' : "disabled");
      return '<button type="button" class="ag-slot t-' + tone + (x.can_submit ? " act" : "") + '" ' + attr + ' style="top:' + y(m) + "px;height:" + (PX - 4) + 'px" title="' + RG.esc(x.reason || x.status) + '">' +
        '<b>' + RG.esc(x.label) + "</b><span>" + RG.esc(x.can_submit ? "Submit hourly update" : x.status === "Open" ? "In progress" : x.status) + "</span></button>";
    }).join("");
    var meets = (meetings || []).map(function (m) {
      var a = minutesOf(m.start_time), b = minutesOf(m.end_time) || a + 30;
      if (a === null || b < START || a > END) return "";
      return '<div class="ag-meet' + (m.status === "Cancelled" ? " cancel" : "") + '" style="top:' + y(Math.max(a, START)) + "px;height:" + Math.max(26, (b - a) * PX / 60 - 3) + 'px">' +
        "<b>" + RG.esc(m.title) + "</b><span>" + RG.fmt.time(m.start_time) + (m.end_time ? " – " + RG.fmt.time(m.end_time) : "") + "</span>" +
        (m.google_meet_url && m.status !== "Cancelled" ? '<a class="meet-btn btn btn-sm" target="_blank" rel="noopener" href="' + RG.esc(m.google_meet_url) + '">Join</a>' : "") + "</div>";
    }).join("");
    var marks = [[780, "Noon report opens"], [1080, "EOD report opens · office closes"]].map(function (x) {
      return '<div class="ag-mark" style="top:' + y(x[0]) + 'px"><span>' + x[1] + "</span></div>";
    }).join("");
    var work = "";
    if (s && s.check_in_time) {
      var a = minutesOf(s.check_in_time), b = s.check_out_time ? minutesOf(s.check_out_time) : nowMin;
      if (b > a) work = '<div class="ag-work' + (s.check_out_time ? " done" : "") + '" style="top:' + y(Math.max(a, START)) + "px;height:" + Math.max(4, (Math.min(b, END) - Math.max(a, START)) * PX / 60) + 'px" title="Working session"></div>';
    }
    var nowEl = nowMin >= START && nowMin <= END ? '<div class="ag-now" style="top:' + y(nowMin) + 'px"><span>' + RG.fmt.time(hhmm(now)) + "</span></div>" : "";
    return '<div class="ag-scroll" tabindex="0" aria-label="Agenda from 9 AM to 7 PM"><div class="ag" style="height:' + ((END - START) * PX / 60 + 20) + 'px">' +
      lines + marks + work + '<div class="ag-slots">' + blocks + "</div>" + '<div class="ag-meets">' + meets + "</div>" + nowEl + "</div></div>" +
      '<p class="ag-foot">Select a highlighted hour to submit its update, or a submitted hour to view it. Periods covered by approved leave, before Check-In or after Check-Out are not applicable.</p>';
  }

  function upNext(next, meetings) {
    var html = '<section class="pd-up"><h2>Up next</h2>';
    if (next) {
      html += '<div class="up-meet"><span class="up-k">' + RG.icon("video", 14) + " Next meeting</span><b>" + RG.esc(next.title) + "</b>" +
        "<span>" + RG.fmt.time(next.start_time) + (next.end_time ? " – " + RG.fmt.time(next.end_time) : "") + " · " + RG.esc(next.department || "") + "</span>" +
        (next.agenda ? "<p>" + RG.esc(next.agenda) + "</p>" : "") +
        (next.google_meet_url ? '<a class="btn btn-sm meet-btn" target="_blank" rel="noopener" href="' + RG.esc(next.google_meet_url) + '">' + RG.icon("video", 14) + " Join Google Meet</a>" : "") + "</div>";
    } else {
      html += '<div class="up-meet empty"><span class="up-k">' + RG.icon("video", 14) + " Meetings</span><b>Nothing else scheduled today</b>" +
        "<span>" + (meetings.length ? meetings.length + " earlier today" : "No department meetings today") + ' · <a href="meetings.html">All meetings</a></span></div>';
    }
    return html + "</section>";
  }

  function monthBody(month) {
    if (!month) return '<div class="inner">' + RG.emptyState("No attendance yet", "Your month fills in as you check in.", "", "calendar") + "</div>";
    var a = month.attendance || {};
    var r = month.reports || {};
    var worked = (month.days || []).filter(function (d) { return d.sessions; }).length;
    var late = (month.days || []).filter(function (d) { return d.late_minutes; }).length;
    var mins = (month.days || []).reduce(function (s, d) { return s + (d.worked_minutes || 0); }, 0);
    return '<div class="inner"><div class="wd-month-stats">' +
        "<div><span>Days worked</span><b>" + worked + "</b><em>of " + (a.working_days_elapsed !== undefined ? a.working_days_elapsed : "—") + " so far</em></div>" +
        "<div><span>Hours logged</span><b>" + W.mins(mins).replace(/m$/, "m") + "</b><em>" + RG.esc(month.period_label || "") + "</em></div>" +
        "<div><span>Late days</span><b>" + late + "</b><em>shown in light amber</em></div>" +
        "<div><span>Reports filed</span><b>" + ((r.noon_submitted || 0) + (r.eod_submitted || 0)) + "</b><em>of " + ((r.noon_required || 0) + (r.eod_required || 0)) + " required</em></div>" +
      '</div><div class="wd-chart"><canvas id="c-month" role="img" aria-label="Hours worked per day this month"></canvas></div></div>';
  }

  LAYOUTS.employee = LAYOUTS.employee || employeeLayout;

  /* ============================== engine ============================== */
  var extra = {};
  var more = {};
  var wired = false;
  function layout() { return LAYOUTS[ctx.scope] || employeeLayout; }

  function load() {
    if (!ctx.page.querySelector("[data-dash-root]")) ctx.page.innerHTML = B.loading();
    var L = layout();
    Promise.all([
      API.get("/dashboard/employee"),
      API.get("/attendance/status").catch(function () { return null; }),
      API.get("/hourly-updates/today").catch(function () { return null; }),
      API.get("/leave-requests/me", { page: 1, page_size: 20 }).then(function (r) { return r.items || []; }).catch(function () { return []; }),
      L.fetch ? L.fetch().catch(function () { return {}; }) : Promise.resolve({})
    ]).then(function (res) {
      extra = { status: res[1], hourly: res[2], leaves: res[3] };
      more = res[4] || {};
      ctx.page.innerHTML = '<div class="dash dash-' + ctx.scope + '" data-dash-root>' + L.render(res[0], extra, more, B) + "</div>";
      RG.wireNotificationRows(ctx.page);
      RG.hydratePhotos(ctx.page);
      if (L.after) L.after(res[0], extra, more, B);
      // Portal add-ons can still hook in after each render.
      document.dispatchEvent(new CustomEvent("rg:dashboard-rendered", { detail: { page: ctx.page } }));
      if (!wired && W) {
        wired = true;
        W.wireAttendance(ctx.page, load);
        RG.on(ctx.page, "[data-hourly-open]", "click", function () { W.hourlyForm(null, extra.hourly, load); });
        RG.on(ctx.page, "[data-hourly-slot]", "click", function (e, b) { W.hourlyForm(b.dataset.hourlySlot, extra.hourly, load); });
        RG.on(ctx.page, "[data-hourly-view]", "click", function (e, b) {
          var u = ((extra.hourly && extra.hourly.updates) || []).filter(function (x) { return String(x.id) === b.dataset.hourlyView; })[0];
          if (u) W.showUpdate(u);
        });
        RG.on(ctx.page, "[data-request-leave]", "click", function () { RG.leaveModal(load); });
        RG.on(ctx.page, "[data-pdf]", "click", function (e, btn) {
          RG.setBusy(btn, true, "Preparing…");
          API.download("/salaries/" + btn.dataset.pdf + "/payslip/download")
            .then(function () { RG.setBusy(btn, false); RG.toastOk("Payslip downloaded."); })
            .catch(function (err) { RG.setBusy(btn, false); RG.toastErr(err); });
        });
        document.addEventListener("rg:work-refresh", load);
        document.addEventListener("rg:hourly-submitted", load);
      }
    }).catch(function (err) {
      ctx.page.innerHTML = '<div class="card">' + RG.errorState(err.message, "retry") + "</div>";
      var retry = document.getElementById("retry");
      if (retry) retry.addEventListener("click", load);
    });
  }
  window.RGDash.reload = load;
  load();
})();
