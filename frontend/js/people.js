/* people.js - Admin monitoring lists.
   hr-monitoring.html      : every HR with today's attendance and their teams'
                             pending work; ?id= opens the full HR monitoring view.
   people.html?type=X      : Manager / Employee / Intern monitoring with
                             department, HR and manager filters. */
(function () {
  "use strict";
  var isHrPage = document.body.dataset.page === "hr-monitoring";
  var type = isHrPage ? "HR" : (RG.param("type") || "Employee");
  var TITLES = {
    HR: ["HR Monitoring", "The primary monitoring view: each HR's attendance, reports, tasks, leave and the managers and teams under them."],
    Manager: ["Manager Monitoring", "Every manager with their reporting HR, team size and today's attendance."],
    Employee: ["Employee Monitoring", "Every employee with their reporting manager and HR and today's attendance."],
    Intern: ["Intern Monitoring", "Every intern with their reporting manager and HR and today's attendance."]
  };
  var ctx = RG.boot({ scope: "admin", active: isHrPage ? "hr-monitoring" : "people-" + type, title: TITLES[type][0], subtitle: "Monitoring" });
  if (!ctx) return;

  var id = RG.param("id");
  if (isHrPage && id) {
    ctx.page.innerHTML = '<div class="page-head"><div><h1>HR Monitoring</h1><p class="sub">Profile → attendance → work reports → hourly → tasks → leave → documents → salary → managers → teams.</p></div>' +
      '<div class="page-actions"><a class="btn" href="hr-monitoring.html">All HR</a></div></div><div id="person-host"></div>';
    window.RGPerson.mount(document.getElementById("person-host"), id, "admin");
    return;
  }

  var state = { department_id: RG.param("department_id") || "", reporting_hr_id: RG.param("reporting_hr_id") || "",
                reporting_manager_id: RG.param("reporting_manager_id") || "", search: "" };

  ctx.page.innerHTML =
    '<div class="page-head"><div><h1>' + TITLES[type][0] + '</h1><p class="sub">' + TITLES[type][1] + "</p></div>" +
      '<div class="page-actions"><a class="btn" href="excel.html?export=employees&person_type=' + type + '">' + RG.icon("download", 16) + " Export</a>" +
      '<a class="btn btn-brand" href="employees.html?new=1">' + RG.icon("plus", 16) + " Add</a></div></div>" +
    '<div class="today-strip" id="pp-strip"></div>' +
    '<div class="card"><div class="toolbar"><div class="filters" style="margin-left:0">' +
      '<input type="search" id="pp-q" placeholder="Search name or ID">' +
      '<select id="pp-dept"><option value="">All departments</option></select>' +
      (type !== "HR" ? '<select id="pp-hr"><option value="">All HR</option></select>' : "") +
      (type === "Employee" || type === "Intern" ? '<select id="pp-mgr"><option value="">All managers</option></select>' : "") +
    '</div></div><div id="pp-host">' + RG.skeletonRows(8) + "</div></div>";

  var host = document.getElementById("pp-host");

  function todayCell(t) {
    if (!t) return "—";
    var s = t.session;
    if (!s) return RG.badge(t.state === "Not Checked In" ? "Not Logged In" : t.state);
    return "<b>" + RG.fmt.time(s.check_in_time) + "</b>" + (s.check_out_time ? " – " + RG.fmt.time(s.check_out_time) : ' <span class="badge info">Working</span>') +
      (s.late_minutes ? '<div class="small text-bad">' + RG.esc(s.late_label) + " late</div>" : "");
  }

  function strip(items) {
    var inn = items.filter(function (i) { return i.today && i.today.session; }).length;
    var late = items.filter(function (i) { return i.today && i.today.session && i.today.session.late_minutes; }).length;
    var leave = items.filter(function (i) { return i.today && i.today.leave_status; }).length;
    var active = items.filter(function (i) { return i.is_active; }).length;
    document.getElementById("pp-strip").innerHTML = [
      [type === "HR" ? "HR accounts" : type + "s", items.length, ""], ["Active", active, "ok"], ["Checked in today", inn, "ok"],
      ["Late today", late, late ? "warn" : ""], ["On leave today", leave, ""]
    ].map(function (c) { return '<div class="ts ' + c[2] + '"><span>' + c[0] + "</span><b>" + c[1] + "</b></div>"; }).join("");
  }

  function renderHr(items) {
    strip(items);
    if (!items.length) { host.innerHTML = RG.emptyState("No HR accounts", "Create HR accounts from the People Directory or Excel import.", "", "shield"); return; }
    host.innerHTML = '<div class="table-scroll"><table class="data"><thead><tr><th>HR</th><th>Today</th><th>Managers</th><th>Employees &amp; interns</th><th>Team leave pending</th><th>Team reports to review</th><th>Open tasks</th><th>Own leave pending</th><th></th></tr></thead><tbody>' +
      items.map(function (h) {
        var c = h.counts || {};
        return '<tr><td data-label="HR"><div class="identity">' + RG.avatar(h, "sm") + '<div><a class="name" href="hr-monitoring.html?id=' + h.id + '">' + RG.esc(h.full_name) + "</a>" +
          '<div class="meta">' + RG.esc(h.designation) + " · " + RG.esc(h.department || "") + " · " + RG.esc(h.display_employee_id || "") + "</div></div></div></td>" +
          '<td data-label="Today">' + todayCell(h.today) + "</td>" +
          '<td data-label="Managers"><a href="people.html?type=Manager&reporting_hr_id=' + h.id + '"><b>' + (c.managers || 0) + "</b></a></td>" +
          '<td data-label="Employees"><a href="people.html?type=Employee&reporting_hr_id=' + h.id + '"><b>' + (c.employees || 0) + "</b></a></td>" +
          '<td data-label="Team leave">' + (c.pending_leave_in_team || 0) + "</td>" +
          '<td data-label="Reports">' + (c.reports_to_review || 0) + "</td>" +
          '<td data-label="Open tasks">' + (c.own_open_tasks || 0) + "</td>" +
          '<td data-label="Own leave">' + (c.own_pending_leave ? RG.badge(c.own_pending_leave + " for you", "warn") : "0") + "</td>" +
          '<td class="actions"><a class="btn btn-sm btn-brand" href="hr-monitoring.html?id=' + h.id + '">Monitor</a></td></tr>';
      }).join("") + "</tbody></table></div>";
    RG.hydratePhotos(host);
  }

  function renderPeople(items) {
    strip(items);
    if (!items.length) { host.innerHTML = RG.emptyState("Nobody matches", "Try another filter.", "", "users"); return; }
    host.innerHTML = '<div class="table-scroll"><table class="data"><thead><tr><th>Name</th><th>Department</th>' +
      (type === "Manager" ? "<th>Reporting HR</th><th>Team</th>" : "<th>Reporting manager</th><th>Reporting HR</th>") +
      "<th>Today</th><th>Documents</th><th>Status</th><th></th></tr></thead><tbody>" +
      items.map(function (e) {
        return '<tr><td data-label="Name"><div class="identity">' + RG.avatar(e, "sm") + '<div><a class="name" href="person.html?id=' + e.id + '">' + RG.esc(e.full_name) + "</a>" +
          '<div class="meta">' + RG.esc(e.designation) + " · " + RG.esc(e.display_employee_id || "") + "</div></div></div></td>" +
          '<td data-label="Department">' + RG.esc(e.department || "—") + (e.internship_background ? '<div class="small muted">' + RG.esc(e.internship_background) + "</div>" : "") + "</td>" +
          (type === "Manager"
            ? '<td data-label="Reporting HR">' + (e.reporting_hr ? RG.esc(e.reporting_hr) : RG.badge("Not assigned", "warn")) + "</td>" +
              '<td data-label="Team"><a href="people.html?type=Employee&reporting_manager_id=' + e.id + '">' + (e.team_size || 0) + "</a></td>"
            : '<td data-label="Manager">' + RG.esc(e.reporting_manager || "—") + "</td>" +
              '<td data-label="HR">' + (e.reporting_hr ? RG.esc(e.reporting_hr) : RG.badge("Not assigned", "warn")) + "</td>") +
          '<td data-label="Today">' + todayCell(e.today) + "</td>" +
          '<td data-label="Documents">' + (e.document_completion != null ? RG.fmt.percent(e.document_completion) : "—") + "</td>" +
          '<td data-label="Status">' + RG.badge(e.employment_status) + "</td>" +
          '<td class="actions"><a class="btn btn-sm" href="person.html?id=' + e.id + '">Monitor</a></td></tr>';
      }).join("") + "</tbody></table></div>";
    RG.hydratePhotos(host);
  }

  function load() {
    host.innerHTML = RG.skeletonRows(8);
    var q;
    if (type === "HR") q = API.get("/admin/hr", { department_id: state.department_id }).then(function (d) {
      var items = d.items;
      if (state.search) {
        var s = state.search.toLowerCase();
        items = items.filter(function (i) { return (i.full_name + " " + i.employee_code + " " + (i.display_employee_id || "")).toLowerCase().indexOf(s) >= 0; });
      }
      renderHr(items);
    });
    else q = API.get("/admin/people", { person_type: type, department_id: state.department_id, reporting_hr_id: state.reporting_hr_id,
      reporting_manager_id: state.reporting_manager_id, search: state.search }).then(function (d) { renderPeople(d.items); });
    q.catch(function (err) { host.innerHTML = RG.errorState(err.message); });
  }

  API.get("/departments").then(function (d) {
    document.getElementById("pp-dept").innerHTML = '<option value="">All departments</option>' + RG.optionList(d, "id", "name", state.department_id);
  }).catch(function () {});
  if (document.getElementById("pp-hr")) API.get("/hierarchy/candidates", { role: "HR_ADMIN" }).then(function (d) {
    document.getElementById("pp-hr").innerHTML = '<option value="">All HR</option>' + RG.optionList(d.items, "id", "full_name", state.reporting_hr_id);
  }).catch(function () {});
  if (document.getElementById("pp-mgr")) API.get("/hierarchy/candidates", { role: "MANAGER" }).then(function (d) {
    document.getElementById("pp-mgr").innerHTML = '<option value="">All managers</option>' + RG.optionList(d.items, "id", "full_name", state.reporting_manager_id);
  }).catch(function () {});

  ["pp-dept", "pp-hr", "pp-mgr"].forEach(function (i) {
    var el = document.getElementById(i);
    if (el) el.addEventListener("change", function () {
      state.department_id = document.getElementById("pp-dept").value;
      state.reporting_hr_id = (document.getElementById("pp-hr") || {}).value || "";
      state.reporting_manager_id = (document.getElementById("pp-mgr") || {}).value || "";
      load();
    });
  });
  document.getElementById("pp-q").addEventListener("input", RG.debounce(function (e) { state.search = e.target.value.trim(); load(); }, 300));
  load();
})();
