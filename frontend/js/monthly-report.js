/* ==========================================================================
   monthly-report.js - the monthly employee report.

   One renderer (RGMonthly.render) is used in two places so they always match:
     * employee / intern: "My Monthly Report" page (own data only)
     * HR: Employees -> View Employee -> Monthly Reports (per employee)
   Every number comes from GET /attendance/monthly-report, which calculates it
   from attendance, leave, login/logout, daily reports and salary records.
   ========================================================================== */
(function (global) {
  "use strict";

  function mins(v) {
    v = Math.max(0, Number(v || 0));
    var h = Math.floor(v / 60), m = v % 60;
    return h + "h " + (m < 10 ? "0" : "") + m + "m";
  }
  function t12(v) { return v ? RG.fmt.time(v) : "—"; }
  function num(v) { var n = Number(v || 0); return n % 1 ? n.toFixed(1) : String(n); }
  function money(v) { return v === null || v === undefined ? "—" : RG.fmt.money(v, true); }

  function kv(rows) {
    return '<dl class="kv mr-kv">' + rows.map(function (r) {
      return "<dt>" + RG.esc(r[0]) + "</dt><dd>" + r[1] + "</dd>";
    }).join("") + "</dl>";
  }

  function kpis(d) {
    var a = d.attendance, h = d.hours, r = d.reports, l = d.login;
    var cells = [
      ["Working days", a.working_days, a.working_days_elapsed + " elapsed"],
      ["Days worked", a.days_worked, a.full_day_attendance + " full · " + (a.first_half_attendance + a.second_half_attendance) + " half"],
      ["Leave days", num(a.leave_days), d.leave.unpaid_leave_days ? num(d.leave.unpaid_leave_days) + " unpaid" : "all paid"],
      ["Late logins", l.late_login_count, l.late_login_minutes ? mins(l.late_login_minutes) + " total" : "none"],
      ["Hours worked", mins(h.actual_minutes), "of " + mins(h.expected_minutes) + " expected"],
      ["Extra hours", mins(h.extra_minutes), h.extra_days + " day(s)"],
      ["Reports", r.submitted_total, r.missing_total ? r.missing_total + " missing" : "none missing"]
    ];
    return '<div class="kpi-strip mr-kpis">' + cells.map(function (c) {
      return '<div class="kpi"><div class="kpi-label">' + c[0] + '</div><div class="kpi-value">' + c[1] + "</div>" +
        '<div class="kpi-foot">' + RG.esc(c[2]) + "</div></div>";
    }).join("") + "</div>";
  }

  function attendanceCard(d) {
    var a = d.attendance;
    return '<div class="card"><div class="card-head"><h3>Attendance</h3></div><div class="card-body">' + kv([
      ["Working days", a.working_days],
      ["Days worked", a.days_worked],
      ["Full-day attendance", a.full_day_attendance],
      ["First-half attendance", a.first_half_attendance],
      ["Second-half attendance", a.second_half_attendance],
      ["Full-day leave", a.full_day_leave],
      ["Morning half leave", a.morning_half_leave],
      ["Afternoon half leave", a.afternoon_half_leave],
      ["Absent (no leave)", a.absent_days]
    ]) + "</div></div>";
  }

  function loginCard(d) {
    var l = d.login, h = d.hours;
    return '<div class="card"><div class="card-head"><h3>Login &amp; working hours</h3></div><div class="card-body">' + kv([
      ["Expected login", t12(l.expected_login)],
      ["Number of late logins", l.late_login_count],
      ["Total late time", mins(l.late_login_minutes)],
      ["Expected working hours", mins(h.expected_minutes)],
      ["Actual working hours", mins(h.actual_minutes)],
      ["Extra working hours", mins(h.extra_minutes)]
    ]) + "</div></div>";
  }

  function reportsCard(d) {
    var r = d.reports;
    return '<div class="card"><div class="card-head"><h3>Daily reports</h3><span class="hint">Counted on days worked</span></div><div class="card-body">' + kv([
      ["Noon reports", r.noon_submitted + " submitted / " + r.noon_required + " required"],
      ["EOD reports", r.eod_submitted + " submitted / " + r.eod_required + " required"],
      ["Submitted reports", r.submitted_total],
      ["Missing reports", r.missing_total ? '<span class="text-bad">' + r.missing_total + "</span>" : "0"],
      ["Reviewed by HR", r.reviewed],
      ["Drafts", r.drafts]
    ]) + "</div></div>";
  }

  function salaryCard(d) {
    var s = d.salary;
    if (!s) {
      return '<div class="card"><div class="card-head"><h3>Salary</h3></div><div class="card-body">' +
        RG.emptyState("No salary record for " + d.period_label, "Salary figures appear once HR creates this month's payroll record.", "", "money") +
        "</div></div>";
    }
    return '<div class="card"><div class="card-head"><h3>Salary</h3>' + RG.badge(s.status) + '</div><div class="card-body">' + kv([
      ["Gross earnings", money(s.total_earnings)],
      ["Deductions", money(s.total_deductions)],
      ["Recorded net pay", "<b>" + money(s.net_pay) + "</b>"],
      ["Working days (month)", s.working_days],
      ["Unpaid leave days", num(s.unpaid_leave_days)],
      ["Paid days", num(s.paid_days)],
      ["Per-day rate", money(s.per_day_rate)],
      ["Unpaid leave deduction", money(s.unpaid_leave_deduction)],
      ["Payable (gross)", money(s.estimated_payable)],
      ["Payable after deductions", "<b>" + money(s.estimated_net_payable) + "</b>"],
      ["Payslip LOP days", s.recorded_lop_days]
    ]) + '<p class="small muted mt-3 mb-0">' + RG.esc(d.salary_rule) + "</p></div></div>";
  }

  function dayRows(d) {
    return d.days.filter(function (x) { return x.is_working_day || x.sessions; }).map(function (x) {
      var leave = x.leave_status ? RG.badge(x.leave_status) : "";
      return "<tr class=\"" + (x.attendance === "Absent" ? "row-bad" : "") + "\">" +
        '<td data-label="Date" class="nowrap"><b>' + RG.fmt.date(x.date) + '</b> <span class="muted small">' + x.weekday + "</span></td>" +
        '<td data-label="Attendance">' + RG.badge(x.attendance) + (leave && x.attendance !== x.leave_status ? " " + leave : "") + "</td>" +
        '<td data-label="Expected login">' + t12(x.expected_login) + "</td>" +
        '<td data-label="Actual login">' + t12(x.actual_login) + "</td>" +
        '<td data-label="Late">' + (x.late_minutes ? '<span class="text-bad">' + mins(x.late_minutes) + "</span>" : "—") + "</td>" +
        '<td data-label="Late reason"><div class="truncate" style="max-width:200px" title="' + RG.esc(x.late_reason || "") + '">' + RG.esc(x.late_reason || "—") + "</div></td>" +
        '<td data-label="Expected logout">' + t12(x.expected_logout) + "</td>" +
        '<td data-label="Actual logout">' + (x.actual_logout ? t12(x.actual_logout) : (x.still_logged_in ? RG.badge("Active", "info") : "—")) + "</td>" +
        '<td data-label="Worked">' + (x.worked_minutes ? mins(x.worked_minutes) : "—") + "</td>" +
        '<td data-label="Extra">' + (x.extra_minutes ? '<span class="text-ok">' + mins(x.extra_minutes) + "</span>" : "—") + "</td>" +
        '<td data-label="Noon">' + RG.badge(x.noon_report) + "</td>" +
        '<td data-label="EOD">' + RG.badge(x.eod_report) + "</td>" +
        "</tr>";
    }).join("");
  }

  function render(host, d, opts) {
    opts = opts || {};
    var e = d.employee;
    host.innerHTML =
      '<div class="card mr-head"><div class="card-body">' +
        '<div><div class="mr-period">' + RG.esc(d.period_label) + (d.is_current_month ? ' <span class="badge info">Month to date</span>' : "") + "</div>" +
        '<div class="muted small">' + RG.esc(e.name) + " · " + RG.esc(e.employee_code || "") + " · " +
          RG.esc(e.department || "") + (e.designation ? " · " + RG.esc(e.designation) : "") +
          " · Office hours " + t12(d.office_hours.login) + " – " + t12(d.office_hours.logout) + "</div></div>" +
        '<div class="page-actions">' + (opts.extraActions || "") +
          '<button class="btn btn-brand" data-mr-download="' + d.period + '">' + RG.icon("download", 16) + " Download PDF</button></div>" +
      "</div></div>" +
      kpis(d) +
      '<div class="grid grid-3 mt-4">' + attendanceCard(d) + loginCard(d) + reportsCard(d) + "</div>" +
      '<div class="card mt-4"><div class="card-head"><h3>Attendance details</h3><span class="hint">Login, logout, late reason, extra hours and report status per day</span></div>' +
        '<div class="table-scroll"><table class="data mr-days"><thead><tr><th>Date</th><th>Attendance</th><th>Exp. login</th><th>Login</th><th>Late</th><th>Late reason</th><th>Exp. logout</th><th>Logout</th><th>Worked</th><th>Extra</th><th>Noon</th><th>EOD</th></tr></thead><tbody>' +
        dayRows(d) + "</tbody></table></div></div>" +
      '<div class="grid grid-2 mt-4">' +
        '<div class="card"><div class="card-head"><h3>Leave</h3><span class="hint">' + num(d.leave.approved_days) + " approved day(s) · " +
          num(d.leave.paid_leave_days) + " paid · " + num(d.leave.unpaid_leave_days) + " unpaid" +
          (d.leave.pending_requests ? " · " + d.leave.pending_requests + " pending" : "") + "</span></div>" +
          '<div class="card-body">' + RG.leaveTable(d.leave.items, { emptyText: "No leave requests in " + d.period_label + "." }) + "</div></div>" +
        salaryCard(d) +
      "</div>";

    RG.on(host, "[data-mr-download]", "click", function (ev, btn) {
      if (btn.dataset.busy) return;
      btn.dataset.busy = "1";
      download(btn, d.period, opts.employeeId).then(function () { delete btn.dataset.busy; });
    });
  }

  function download(btn, period, employeeId) {
    RG.setBusy(btn, true, "Preparing…");
    var q = "?month=" + encodeURIComponent(period) + (employeeId ? "&employee_id=" + encodeURIComponent(employeeId) : "");
    return API.download("/attendance/monthly-pdf" + q)
      .then(function () { RG.setBusy(btn, false); RG.toastOk("Monthly report downloaded."); })
      .catch(function (err) { RG.setBusy(btn, false); RG.toastErr(err); });
  }

  function load(host, period, employeeId, opts) {
    host.innerHTML = RG.skeletonCards(3);
    return API.get("/attendance/monthly-report", { month: period, employee_id: employeeId || null })
      .then(function (d) { render(host, d, Object.assign({ employeeId: employeeId }, opts || {})); return d; })
      .catch(function (err) { host.innerHTML = '<div class="card">' + RG.errorState(err.message) + "</div>"; });
  }

  /* Month list with View | Download, used on the HR employee profile. */
  function monthList(listHost, viewHost, employeeId) {
    listHost.innerHTML = RG.skeletonRows(3);
    return API.get("/attendance/months", { employee_id: employeeId }).then(function (res) {
      var items = res.items || [];
      if (!items.length) { listHost.innerHTML = RG.emptyState("No months yet", "Reports appear from the joining month onward."); return; }
      listHost.innerHTML = '<ul class="mr-months">' + items.map(function (m, i) {
        return '<li data-month-row="' + m.period + '"' + (i >= 12 ? ' class="hidden" data-older' : "") + '><span class="mr-month-name">' + RG.icon("calendar", 16) + " <b>" + RG.esc(m.label) + "</b>" +
          (m.is_current ? ' <span class="badge info">Current</span>' : "") + "</span>" +
          '<span class="mr-month-actions"><button class="btn btn-sm" data-mr-view="' + m.period + '">' + RG.icon("eye", 14) + " View</button>" +
          '<button class="btn btn-sm" data-mr-dl="' + m.period + '">' + RG.icon("download", 14) + " Download</button></span></li>";
      }).join("") + "</ul>" +
        (items.length > 12 ? '<div class="card-body"><button class="btn btn-sm" data-mr-older>Show older months (' + (items.length - 12) + ")</button></div>" : "");
      var older = listHost.querySelector("[data-mr-older]");
      if (older) older.addEventListener("click", function () {
        listHost.querySelectorAll("[data-older]").forEach(function (li) { li.classList.remove("hidden"); });
        older.parentNode.remove();
      });
      RG.on(listHost, "[data-mr-view]", "click", function (e, b) {
        listHost.querySelectorAll("[data-month-row]").forEach(function (li) { li.classList.toggle("active", li.dataset.monthRow === b.dataset.mrView); });
        viewHost.classList.remove("hidden");
        load(viewHost, b.dataset.mrView, employeeId, {
          extraActions: '<button class="btn" data-mr-close>Close</button>'
        }).then(function () {
          var close = viewHost.querySelector("[data-mr-close]");
          if (close) close.addEventListener("click", function () {
            viewHost.innerHTML = ""; viewHost.classList.add("hidden");
            listHost.querySelectorAll("[data-month-row]").forEach(function (li) { li.classList.remove("active"); });
          });
          viewHost.scrollIntoView({ behavior: "smooth", block: "start" });
        });
      });
      RG.on(listHost, "[data-mr-dl]", "click", function (e, b) {
        if (b.dataset.busy) return;
        b.dataset.busy = "1";
        download(b, b.dataset.mrDl, employeeId).then(function () { delete b.dataset.busy; });
      });
    }).catch(function (err) { listHost.innerHTML = RG.errorState(err.message); });
  }

  /* Employee / intern page: own report, month selector, view + download. */
  function ownPage() {
    var scope = document.body.dataset.scope || "employee";
    var ctx = RG.boot({ scope: scope, active: "monthly-report", title: "My Monthly Report", subtitle: "Attendance, leave, reports and salary" });
    if (!ctx) return;
    ctx.page.innerHTML =
      '<div class="page-head"><div><h1>My Monthly Report</h1><p class="sub">Calculated from your attendance, leave, daily reports and salary records.</p></div>' +
      '<div class="page-actions"><label class="sr-only" for="mr-month">Month</label><select id="mr-month" class="mr-select"></select></div></div>' +
      '<div id="mr-host">' + RG.skeletonCards(3) + "</div>";
    var host = document.getElementById("mr-host");
    var select = document.getElementById("mr-month");
    API.get("/attendance/months").then(function (res) {
      var items = res.items || [];
      var wanted = RG.param("month");
      select.innerHTML = items.map(function (m) {
        return '<option value="' + m.period + '"' + (m.period === wanted ? " selected" : "") + ">" + RG.esc(m.label) + "</option>";
      }).join("");
      select.addEventListener("change", function () {
        try { history.replaceState(null, "", "?month=" + select.value); } catch (e) { /* ignore */ }
        load(host, select.value);
      });
      load(host, select.value || null);
    }).catch(function (err) { host.innerHTML = '<div class="card">' + RG.errorState(err.message) + "</div>"; });
  }

  global.RGMonthly = { render: render, load: load, monthList: monthList };

  var page = document.body.dataset.page;
  if (page === "monthly-report") ownPage();
})(window);
