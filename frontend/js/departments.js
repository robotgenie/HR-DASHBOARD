/* departments.js - Admin department-wise monitoring. Each department shows
   who works there by type and opens the filtered monitoring screens:
   Department -> HR -> Managers -> Employees / Interns -> work. */
(function () {
  "use strict";
  var ctx = RG.boot({ scope: "admin", active: "departments", title: "Departments", subtitle: "Department-wise monitoring" });
  if (!ctx) return;
  var id = RG.param("id");

  ctx.page.innerHTML = '<div class="page-head"><div><h1>Departments</h1><p class="sub">Head-count by type, today\'s check-ins and pending documents per department. Open one to drill into its people and work.</p></div></div>' +
    '<div id="d-host">' + RG.skeletonRows(6) + "</div>";
  var host = document.getElementById("d-host");

  API.get("/admin/departments/overview").then(function (d) {
    var items = d.items || [];
    var cur = items.filter(function (x) { return String(x.id) === String(id); })[0];
    host.innerHTML = '<div class="card mb-4"><div class="table-scroll"><table class="data"><thead><tr><th>Department</th><th>Total</th><th>HR</th><th>Managers</th><th>Employees</th><th>Interns</th><th>Checked in today</th><th>Documents pending</th><th></th></tr></thead><tbody>' +
      items.map(function (x) {
        return '<tr' + (cur && cur.id === x.id ? ' class="row-update"' : "") + '><td data-label="Department"><b>' + RG.esc(x.name) + "</b>" + (x.is_active ? "" : ' <span class="badge">Inactive</span>') + "</td>" +
          '<td data-label="Total">' + x.total + "</td><td data-label=\"HR\">" + x.counts.HR + "</td><td data-label=\"Managers\">" + x.counts.Manager + "</td>" +
          '<td data-label="Employees">' + x.counts.Employee + "</td><td data-label=\"Interns\">" + x.counts.Intern + "</td>" +
          '<td data-label="Checked in">' + x.checked_in_today + "</td><td data-label=\"Documents\">" + x.documents_pending + "</td>" +
          '<td class="actions"><a class="btn btn-sm" href="departments.html?id=' + x.id + '">Open</a></td></tr>';
      }).join("") + "</tbody></table></div></div>" + (cur ? '<div id="d-detail"></div>' : "");
    if (cur) detail(cur);
  }).catch(function (err) { host.innerHTML = '<div class="card">' + RG.errorState(err.message) + "</div>"; });

  function detail(dept) {
    var box = document.getElementById("d-detail");
    var q = "department_id=" + dept.id;
    box.innerHTML = '<div class="section-title">' + RG.icon("grid", 16) + " " + RG.esc(dept.name) + "</div>" +
      '<div class="module-grid mb-4">' + [
        ["work-monitor.html?" + q, "clock", "Attendance & hourly", "Today, by person"],
        ["tasks.html", "target", "Tasks", "Filter by department"],
        ["leave-requests.html", "calendar", "Leave", "Filter by department"],
        ["work-reports.html", "clipboard", "Work reports", "Noon & EOD"],
        ["monthly-reports.html", "dashboard", "Monthly reports", "This department"],
        ["excel.html?export=employees", "download", "Export", "Department to Excel"]
      ].map(function (m) { return '<a href="' + m[0] + '"><span class="mi">' + RG.icon(m[1], 17) + "</span><span>" + m[2] + "<small>" + m[3] + "</small></span></a>"; }).join("") + "</div>" +
      '<div class="card"><div class="card-head"><h3>People in ' + RG.esc(dept.name) + "</h3></div><div id=\"d-people\">" + RG.skeletonRows(4) + "</div></div>";
    API.get("/admin/people", { department_id: dept.id }).then(function (d) {
      var el = document.getElementById("d-people");
      var items = d.items || [];
      if (!items.length) { el.innerHTML = RG.emptyState("Nobody in this department yet", ""); return; }
      el.innerHTML = '<div class="table-scroll"><table class="data"><thead><tr><th>Name</th><th>Type</th><th>Reporting manager</th><th>Reporting HR</th><th>Today</th><th></th></tr></thead><tbody>' +
        items.map(function (e) {
          var s = e.today && e.today.session;
          return '<tr><td data-label="Name"><div class="identity">' + RG.avatar(e, "sm") + '<div><a class="name" href="person.html?id=' + e.id + '">' + RG.esc(e.full_name) + '</a><div class="meta">' + RG.esc(e.designation) + "</div></div></div></td>" +
            '<td data-label="Type">' + RG.esc(e.role_label) + "</td><td data-label=\"Manager\">" + RG.esc(e.reporting_manager || "—") + "</td>" +
            '<td data-label="HR">' + RG.esc(e.reporting_hr || (e.role_label === "HR" ? "Admin" : "—")) + "</td>" +
            '<td data-label="Today">' + (s ? RG.fmt.time(s.check_in_time) + (s.check_out_time ? " – " + RG.fmt.time(s.check_out_time) : "") : RG.badge(e.today ? e.today.state : "—")) + "</td>" +
            '<td class="actions"><a class="btn btn-sm" href="person.html?id=' + e.id + '">Monitor</a></td></tr>';
        }).join("") + "</tbody></table></div>";
      RG.hydratePhotos(el);
    }).catch(function (err) { document.getElementById("d-people").innerHTML = RG.errorState(err.message); });
  }
})();
