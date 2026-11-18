/* monthly-summary.js - monthly reports for everyone the viewer may monitor.
   Admin: whole organisation. HR: their hierarchy. Manager: their team (no
   salary figures). Each figure comes from the same calculation as the
   person's own monthly report (attendance, leave, half days, late logins,
   hours, extra hours, Noon/EOD and payable). Click a row to open the report. */
(function () {
  "use strict";
  var ctx = RG.boot({ scope: document.body.dataset.scope, active: "monthly-reports", title: "Monthly Reports", subtitle: "Attendance, leave and reports" });
  if (!ctx) return;
  var SCOPE = ctx.scope;
  var now = new Date();
  var state = { month: RG.param("month") || (now.getFullYear() + "-" + String(now.getMonth() + 1).padStart(2, "0")),
                department_id: "", reporting_hr_id: "", reporting_manager_id: "", person_type: "", q: "" };

  function mins(n) { n = Math.max(0, Number(n || 0)); return Math.floor(n / 60) + "h " + String(n % 60).padStart(2, "0") + "m"; }

  ctx.page.innerHTML =
    '<div class="page-head"><div><h1>' + (SCOPE === "manager" ? "Team Monthly Reports" : "Monthly Reports") + "</h1>" +
      '<p class="sub">' + ({ admin: "Every HR, manager, employee and intern.", hr: "Everyone in your hierarchy (and you).", manager: "Your team and you. Salary figures stay with HR." }[SCOPE] || "") + "</p></div>" +
      '<div class="page-actions"><a class="btn" href="' + (SCOPE === "manager" ? "exports.html" : "excel.html") + '?export=monthly">' + RG.icon("download", 16) + " Export to Excel</a></div></div>" +
    '<div class="card"><div class="toolbar"><div class="filters" style="margin-left:0">' +
      '<input type="month" id="ms-month" value="' + state.month + '">' +
      '<input type="search" id="ms-q" placeholder="Search name">' +
      (SCOPE !== "manager" ? '<select id="ms-dept"><option value="">All departments</option></select>' : "") +
      (SCOPE === "admin" ? '<select id="ms-hr"><option value="">All HR</option></select>' : "") +
      (SCOPE !== "manager" ? '<select id="ms-mgr"><option value="">All managers</option></select>' : "") +
      '<select id="ms-type"><option value="">Everyone</option>' + (SCOPE === "admin" ? "<option>HR</option>" : "") +
        (SCOPE !== "manager" ? "<option>Manager</option>" : "") + "<option>Employee</option><option>Intern</option></select>" +
    '</div></div><div id="ms-host">' + RG.skeletonRows(8) + '</div></div><div id="ms-view" class="mt-4"></div>';
  var host = document.getElementById("ms-host");

  function load() {
    host.innerHTML = RG.skeletonRows(8);
    API.get("/attendance/hr/monthly-summary", { month: state.month, department_id: state.department_id, reporting_hr_id: state.reporting_hr_id,
      reporting_manager_id: state.reporting_manager_id, person_type: state.person_type }).then(function (d) {
      var items = (d.items || []).filter(function (r) { return !state.q || String(r.name || "").toLowerCase().indexOf(state.q) >= 0; });
      if (!items.length) { host.innerHTML = RG.emptyState("Nobody matches", "Try another month or filter."); return; }
      host.innerHTML = '<div class="table-scroll"><table class="data"><thead><tr><th>Name</th><th>Department</th><th>Days worked</th><th>Leave days</th><th>Late logins</th><th>Total hours</th><th>Extra hours</th><th>Noon</th><th>EOD</th><th>Missing reports</th><th></th></tr></thead><tbody>' +
        items.map(function (r) {
          return '<tr><td data-label="Name"><b>' + RG.esc(r.name) + '</b><div class="small muted">' + RG.esc(r.employee_code || "") + (r.is_intern ? " · Intern" : "") + "</div></td>" +
            '<td data-label="Department">' + RG.esc(r.department || "—") + "</td>" +
            '<td data-label="Days worked">' + r.days_worked + "</td><td data-label=\"Leave\">" + r.leave_days + "</td>" +
            '<td data-label="Late logins">' + (r.late_login_count ? '<span class="text-bad">' + r.late_login_count + "</span>" : "0") + "</td>" +
            '<td data-label="Hours">' + mins(r.total_work_minutes) + "</td><td data-label=\"Extra\">" + mins(r.extra_work_minutes) + "</td>" +
            '<td data-label="Noon">' + r.noon_reports + "</td><td data-label=\"EOD\">" + r.eod_reports + "</td>" +
            '<td data-label="Missing">' + (r.missing_reports ? RG.badge(String(r.missing_reports), "warn") : "0") + "</td>" +
            '<td class="actions"><button class="btn btn-sm" data-open="' + r.id + '">Open</button></td></tr>';
        }).join("") + "</tbody></table></div>";
    }).catch(function (err) { host.innerHTML = RG.errorState(err.message); });
  }

  RG.on(ctx.page, "[data-open]", "click", function (e, b) {
    var view = document.getElementById("ms-view");
    window.RGMonthly.load(view, state.month, b.dataset.open, { extraActions: '<button class="btn" data-ms-close>Close</button>' }).then(function () {
      var c = view.querySelector("[data-ms-close]");
      if (c) c.addEventListener("click", function () { view.innerHTML = ""; });
      view.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });
  document.getElementById("ms-month").addEventListener("change", function (e) { state.month = e.target.value; load(); });
  document.getElementById("ms-q").addEventListener("input", RG.debounce(function (e) { state.q = e.target.value.trim().toLowerCase(); load(); }, 300));
  document.getElementById("ms-type").addEventListener("change", function (e) { state.person_type = e.target.value; load(); });
  [["ms-dept", "department_id", "/departments", null], ["ms-hr", "reporting_hr_id", "/hierarchy/candidates", "HR_ADMIN"], ["ms-mgr", "reporting_manager_id", "/hierarchy/candidates", "MANAGER"]].forEach(function (f) {
    var el = document.getElementById(f[0]);
    if (!el) return;
    API.get(f[2], f[3] ? { role: f[3] } : null).then(function (d) {
      el.innerHTML = el.options[0].outerHTML + RG.optionList(d.items || d, "id", f[3] ? "full_name" : "name");
    }).catch(function () {});
    el.addEventListener("change", function () { state[f[1]] = el.value; load(); });
  });
  load();
})();
