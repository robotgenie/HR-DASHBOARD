/* person.js - one person's complete monitoring view, shared by the Admin
   (anyone; HR monitoring drill-down), HR (their hierarchy) and Managers (their
   team). Every panel is read from the normal, hierarchy-scoped API: if the
   viewer may not see something (e.g. a Manager and salary) the API refuses and
   the panel says so. Nothing is computed or invented in the browser.

   Profile -> Attendance -> Work reports (Noon / EOD) -> Hourly -> Tasks ->
   Leave -> Documents -> Salary -> Managers & teams */
(function (global) {
  "use strict";
  var RG = global.RG, API = global.API;

  function localISO(d) { return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0"); }
  function daysAgo(n) { var d = new Date(); d.setDate(d.getDate() - n); return localISO(d); }
  function mins(n) { n = Math.max(0, Number(n || 0)); return Math.floor(n / 60) + "h " + String(n % 60).padStart(2, "0") + "m"; }
  function denied(err) {
    if (err && err.status === 403) return RG.emptyState("Not available to you", "This information is outside your access level.", "", "shield");
    return RG.errorState(err && err.message);
  }

  var TABS = [
    ["profile", "Profile"], ["attendance", "Attendance"], ["reports", "Work reports"], ["hourly", "Hourly updates"],
    ["tasks", "Tasks"], ["leave", "Leave"], ["documents", "Documents"], ["salary", "Salary"], ["team", "Managers & teams"]
  ];

  function chainHtml(chain) {
    return '<ul class="chain">' + (chain || []).map(function (c) {
      return '<li><span class="lvl">' + RG.esc(c.level) + "</span><b>" + RG.esc(c.name) + "</b></li>";
    }).join("") + "</ul>";
  }

  function personRow(p, link) {
    var cls = { Intern: "intern", Manager: "manager", HR: "hr" }[p.role_label || p.type] || "";
    return '<li class="org-person">' + RG.avatar(p, "sm") +
      '<a class="nm" href="' + link + p.id + '">' + RG.esc(p.full_name) + "</a>" +
      '<span class="tag ' + cls + '">' + RG.esc(p.role_label || p.type || "") + "</span></li>";
  }

  function mount(host, id, scope) {
    var link = "person.html?id=";
    if (scope === "admin") link = "person.html?id=";
    var state = { tab: RG.param("tab") || "profile", person: null };
    host.innerHTML = '<div class="card mb-4"><div class="card-body" id="p-hero">' + RG.skeletonRows(2) + "</div></div>" +
      '<div class="card"><div class="tabs" role="tablist">' + TABS.map(function (t) {
        return '<button class="tab" data-ptab="' + t[0] + '">' + t[1] + "</button>";
      }).join("") + '</div><div class="person-panels" id="p-body">' + RG.skeletonRows(5) + "</div></div>";
    var body = host.querySelector("#p-body");

    function hero(e, today) {
      var s = today && today[0];
      var stateText = s ? (s.check_out_time ? "Checked out " + RG.fmt.time(s.check_out_time) : "Checked in " + RG.fmt.time(s.check_in_time)) : "Not checked in today";
      host.querySelector("#p-hero").innerHTML = '<div class="person-hero">' + RG.avatar(e, "lg") +
        '<div class="who"><h2>' + RG.esc(e.full_name) + "</h2>" +
          '<div class="muted small">' + RG.esc(e.role_label || "") + " · " + RG.esc(e.designation || "") + " · " + RG.esc(e.department || "") +
          " · " + RG.esc(e.display_employee_id || e.employee_code || "") + "</div>" +
          '<div class="mt-2">' + chainHtml(e.reporting_chain) + "</div></div>" +
        '<div class="col" style="align-items:flex-end;gap:6px">' + RG.badge(e.employment_status) +
          '<span class="small">' + RG.esc(stateText) + (s && s.late_minutes ? ' · <span class="text-bad">' + RG.esc(s.late_label) + " late</span>" : "") + "</span>" +
          (scope !== "manager" ? '<a class="btn btn-sm" href="' + (scope === "hr" ? "employee-details.html?id=" : "employee-details.html?id=") + e.id + '">Full record</a>' : "") +
        "</div></div>";
      RG.hydratePhotos(host);
    }

    function show() {
      host.querySelectorAll("[data-ptab]").forEach(function (b) { b.classList.toggle("active", b.dataset.ptab === state.tab); });
      body.innerHTML = RG.skeletonRows(5);
      ({ profile: profile, attendance: attendance, reports: reports, hourly: hourly, tasks: tasks, leave: leave,
         documents: documents, salary: salary, team: team }[state.tab] || profile)();
    }

    function profile() {
      var e = state.person;
      var kv = function (k, v) { return "<dt>" + k + "</dt><dd>" + (v ? RG.esc(v) : "—") + "</dd>"; };
      body.innerHTML = '<div class="grid grid-2"><div><h4>Employment</h4><dl class="kv">' +
        kv("Type", e.role_label) + kv("Department", e.department) + kv("Designation", e.designation) +
        kv("Joining date", e.joining_date ? RG.fmt.date(e.joining_date) : "") + kv("Work location", e.work_location || "Company default") + kv("Status", e.employment_status) +
        kv("Reporting manager", e.reporting_manager) + kv("Reporting HR", e.reporting_hr) +
        (e.internship_background ? kv("Internship background", e.internship_background) : "") +
        (e.internship_details ? kv("Internship details", e.internship_details) : "") +
        "</dl></div><div><h4>Contact</h4><dl class=\"kv\">" +
        kv("Email", e.email) + kv("Phone", e.phone) + kv("Gender", e.gender) +
        kv("Date of birth", e.date_of_birth ? RG.fmt.date(e.date_of_birth) : "") + kv("Address", e.address) +
        kv("Emergency contact", [e.emergency_contact_name, e.emergency_contact_relation, e.emergency_contact_phone].filter(Boolean).join(" · ")) +
        kv("Documents", e.document_label) + kv("ID card", e.id_card_status) +
        "</dl></div></div>";
    }

    function attendance() {
      body.innerHTML = '<div class="grid grid-2"><div><h4>Monthly reports</h4><div id="pa-months"></div></div>' +
        '<div><h4>Recent Check-In / Check-Out</h4><div id="pa-sessions">' + RG.skeletonRows(4) + "</div></div></div>" +
        '<div id="pa-view" class="mt-4 hidden"></div>';
      if (global.RGMonthly) global.RGMonthly.monthList(body.querySelector("#pa-months"), body.querySelector("#pa-view"), id);
      API.get("/attendance/sessions", { employee_id: id, date_from: daysAgo(30) }).then(function (d) {
        var rows = d.items || [];
        body.querySelector("#pa-sessions").innerHTML = rows.length ? '<div class="table-scroll"><table class="data compact"><thead><tr><th>Date</th><th>In</th><th>Out</th><th>Worked</th><th>Status</th></tr></thead><tbody>' +
          rows.map(function (s) {
            return "<tr><td>" + RG.fmt.date(s.date) + "</td><td>" + RG.fmt.time(s.check_in_time) +
              (s.late_minutes ? '<div class="small text-bad">' + RG.esc(s.late_label) + " late</div>" : "") + "</td><td>" +
              (s.check_out_time ? RG.fmt.time(s.check_out_time) : "—") + "</td><td>" + mins(s.worked_minutes) +
              (s.extra_minutes ? '<div class="small text-ok">+' + mins(s.extra_minutes) + "</div>" : "") + "</td><td>" + RG.badge(s.attendance_status) + "</td></tr>";
          }).join("") + "</tbody></table></div>" : RG.emptyState("No check-ins in the last 30 days", "");
      }).catch(function (err) { body.querySelector("#pa-sessions").innerHTML = denied(err); });
    }

    function reports() {
      API.get("/reports", { employee_id: id, page: 1, page_size: 60, report_type: state.rtype || "all" }).then(function (d) {
        var items = d.items || [];
        body.innerHTML = '<div class="toolbar" style="padding:0 0 12px"><div class="filters" style="margin-left:0"><select id="pr-type"><option value="all">Noon &amp; EOD</option><option value="Noon">Noon</option><option value="EOD">EOD</option></select></div></div>' +
          (items.length ? '<div class="table-scroll"><table class="data"><thead><tr><th>Date</th><th>Report</th><th>Status</th><th>Work summary</th><th>Files</th><th></th></tr></thead><tbody>' +
          items.map(function (r) {
            return "<tr><td>" + RG.fmt.date(r.report_date) + "</td><td><b>" + RG.esc(r.report_type) + "</b></td><td>" + RG.badge(r.status) +
              (r.reviewed_by_name ? '<div class="small muted">by ' + RG.esc(r.reviewed_by_name) + "</div>" : "") + "</td>" +
              '<td><div class="truncate" style="max-width:320px">' + RG.esc(r.work_summary || "") + "</div></td><td>" + (r.attachments || []).length + "</td>" +
              '<td class="actions"><button class="btn btn-sm" data-read-report="' + r.id + '">Read</button></td></tr>';
          }).join("") + "</tbody></table></div>" : RG.emptyState("No reports", "Noon and EOD reports appear here once submitted."));
        var sel = body.querySelector("#pr-type");
        sel.value = state.rtype || "all";
        sel.addEventListener("change", function () { state.rtype = sel.value; reports(); });
      }).catch(function (err) { body.innerHTML = denied(err); });
    }

    function hourly() {
      API.get("/hourly-updates", { employee_id: id, date_from: daysAgo(14), limit: 300 }).then(function (d) {
        var items = d.items || [];
        state.hourly = items;
        body.innerHTML = items.length ? '<div class="table-scroll"><table class="data"><thead><tr><th>Date</th><th>Hour</th><th>Task</th><th>Work completed</th><th>Progress</th><th></th></tr></thead><tbody>' +
          items.map(function (u) {
            return "<tr><td>" + RG.fmt.date(u.update_date) + "</td><td class=\"nowrap\">" + RG.esc(u.slot_label) + "</td><td>" + RG.esc(u.task_title || "General work") + "</td>" +
              '<td><div class="truncate" style="max-width:300px">' + RG.esc(u.work_completed) + "</div></td><td>" + RG.badge(u.task_status) + "</td>" +
              '<td class="actions"><button class="btn btn-sm" data-hourly="' + u.id + '">View</button></td></tr>';
          }).join("") + "</tbody></table></div>" : RG.emptyState("No hourly updates in the last 14 days", "");
      }).catch(function (err) { body.innerHTML = denied(err); });
    }

    function tasks() {
      API.get("/tasks", { employee_id: id, limit: 200 }).then(function (d) {
        var items = d.items || [];
        body.innerHTML = items.length ? '<div class="table-scroll"><table class="data"><thead><tr><th>Task</th><th>Assigned by</th><th>Dates</th><th>Progress</th><th>Status</th></tr></thead><tbody>' +
          items.map(function (t) {
            return "<tr><td><b>" + RG.esc(t.title) + "</b>" + (t.parent_task_title ? '<div class="small muted">Part of: ' + RG.esc(t.parent_task_title) + "</div>" : "") +
              (t.subtasks_count ? '<div class="small muted">Divided into ' + t.subtasks_count + " parts</div>" : "") + "</td>" +
              "<td>" + RG.esc(t.assigned_by || "—") + "</td><td class=\"nowrap\">" + RG.fmt.date(t.task_date) + (t.due_date ? " → " + RG.fmt.date(t.due_date) : "") + "</td>" +
              '<td style="min-width:120px"><div class="bar thin"><span style="width:' + t.progress_percent + '%"></span></div><span class="small">' + t.progress_percent + "%" +
              (t.target ? " · " + t.completed + "/" + t.target : "") + "</span></td><td>" + RG.badge(t.status) + "</td></tr>";
          }).join("") + "</tbody></table></div>" : RG.emptyState("No tasks", "");
      }).catch(function (err) { body.innerHTML = denied(err); });
    }

    function leave() {
      API.get("/leave-requests", { employee_id: id, page: 1, page_size: 50, awaiting_me: false }).then(function (d) {
        body.innerHTML = RG.leaveTable(d.items || [], { emptyText: "No leave requests from this person." });
      }).catch(function (err) {
        if (err.status === 403) {
          // A person's own leave is not part of their supervisor queue view.
          body.innerHTML = denied(err);
          return;
        }
        body.innerHTML = denied(err);
      });
    }

    function documents() {
      API.get("/documents/employee/" + id).then(function (d) {
        var c = d.completion || {};
        body.innerHTML = '<div class="mini-kpis"><div><span>Mandatory uploaded</span><b>' + (c.uploaded || 0) + " / " + (c.total_required || 0) + "</b></div>" +
          "<div><span>Verified</span><b>" + (c.verified || 0) + "</b></div><div><span>Completion</span><b>" + RG.fmt.percent(c.percent) + "</b></div></div>" +
          '<div class="table-scroll"><table class="data compact"><thead><tr><th>Document</th><th>Mandatory</th><th>Status</th><th>Versions</th><th>HR remarks</th></tr></thead><tbody>' +
          (d.items || []).map(function (i) {
            return "<tr><td><b>" + RG.esc(i.document_type || i.name) + "</b></td><td>" + (i.is_required ? "Yes" : "No") + "</td><td>" + RG.badge(i.status) + "</td><td>" +
              (i.version_count || 0) + "</td><td>" + RG.esc(i.hr_remarks || "—") + "</td></tr>";
          }).join("") + "</tbody></table></div>" +
          (scope !== "manager" ? '<p class="small muted mt-3 mb-0">Open and verify files from the Documents queue.</p>' : '<p class="small muted mt-3 mb-0">Managers see document status only; files stay with HR.</p>');
      }).catch(function (err) { body.innerHTML = denied(err); });
    }

    function salary() {
      if (scope === "manager") { body.innerHTML = RG.emptyState("Salary is not shared with managers", "Salary and payslips are visible to the person, their HR and the Admin.", "", "shield"); return; }
      API.get("/salaries", { employee_id: id, page: 1, page_size: 24 }).then(function (d) {
        var items = d.items || [];
        body.innerHTML = items.length ? '<div class="table-scroll"><table class="data"><thead><tr><th>Period</th><th>Working days</th><th>Earnings</th><th>Deductions</th><th>Net pay</th><th>Status</th><th>Payslip</th></tr></thead><tbody>' +
          items.map(function (s) {
            return "<tr><td><b>" + RG.esc(s.period_label) + "</b></td><td>" + s.working_days + "</td><td>" + RG.fmt.money(s.total_earnings) + "</td><td>" +
              RG.fmt.money(s.total_deductions) + "</td><td><b>" + RG.fmt.money(s.net_pay) + "</b></td><td>" + RG.badge(s.status) + "</td><td>" +
              (s.has_payslip || s.payslip_available ? RG.badge("Available", "ok") : "—") + "</td></tr>";
          }).join("") + "</tbody></table></div>" : RG.emptyState("No salary records", scope === "hr" && state.person && state.person.role_label === "HR" ? "" : "");
      }).catch(function (err) { body.innerHTML = denied(err); });
    }

    function team() {
      API.get("/hierarchy/employees/" + id).then(function (d) {
        var reports = d.direct_reports || [];
        if (!reports.length) {
          body.innerHTML = RG.emptyState("Nobody reports to " + (state.person.full_name || "this person"), state.person.role_label === "HR" || state.person.role_label === "Manager" ? "Assign people from Organization & Hierarchy." : "Only HR and Managers have teams.", "", "users");
          return;
        }
        if (state.person.role_label !== "HR") {
          body.innerHTML = '<ul class="org-mgr" style="list-style:none">' + reports.map(function (p) { return personRow(p, link); }).join("") + "</ul>";
          RG.hydratePhotos(body);
          return;
        }
        body.innerHTML = '<div class="org-mgrs" style="padding:0">' + reports.map(function (m) {
          return '<div class="org-mgr" data-mgr="' + m.id + '"><div class="head">' + RG.avatar(m, "sm") +
            '<div class="who"><a href="' + link + m.id + '"><b>' + RG.esc(m.full_name) + "</b></a>" +
            '<div class="small muted">Manager · ' + RG.esc(m.designation || "") + "</div></div></div><ul>" + RG.skeletonRows(1) + "</ul></div>";
        }).join("") + "</div>";
        RG.hydratePhotos(body);
        reports.forEach(function (m) {
          API.get("/hierarchy/employees/" + m.id).then(function (md) {
            var ul = body.querySelector('[data-mgr="' + m.id + '"] ul');
            ul.innerHTML = (md.direct_reports || []).map(function (p) { return personRow(p, link); }).join("") ||
              '<li class="small muted">No team members yet</li>';
            RG.hydratePhotos(ul);
          }).catch(function () {});
        });
      }).catch(function (err) { body.innerHTML = denied(err); });
    }

    RG.on(host, "[data-ptab]", "click", function (e, b) { state.tab = b.dataset.ptab; show(); });
    RG.on(host, "[data-hourly]", "click", function (e, b) {
      var u = (state.hourly || []).filter(function (x) { return String(x.id) === b.dataset.hourly; })[0];
      if (u && global.RGWork) global.RGWork.showUpdate(u);
    });
    RG.on(host, "[data-read-report]", "click", function (e, b) {
      API.get("/reports/" + b.dataset.readReport).then(function (r) {
        var html = '<div class="report-read"><div class="report-meta"><b>' + RG.esc(r.employee_name || "") + "</b><span>" + RG.esc(r.report_type) + " · " +
          RG.fmt.dateLong(r.report_date) + "</span>" + RG.badge(r.status) + "</div>" +
          ["work_summary", "tasks_completed", "tasks_in_progress", "tasks_pending", "challenges"].map(function (k) {
            return r[k] ? "<section><h4>" + k.replace(/_/g, " ").replace(/^./, function (c) { return c.toUpperCase(); }) + '</h4><div class="body">' + RG.esc(r[k]) + "</div></section>" : "";
          }).join("") +
          "<section><h4>Attachments</h4>" + ((r.attachments || []).map(function (a) { return '<button class="btn btn-sm" data-att="' + a.id + '">' + RG.esc(a.original_filename) + "</button>"; }).join(" ") || "None") + "</section>" +
          (r.review_notes ? '<section><h4>Reviewer comments</h4><div class="body">' + RG.esc(r.review_notes) + "</div></section>" : "") + "</div>" +
          (r.status === "Submitted" ? '<div class="field mt-4"><label for="pr-notes">Comments (optional)</label><textarea id="pr-notes" rows="3"></textarea></div>' : "");
        var m = RG.openModal({ title: r.report_type + " Report", size: "lg", body: html,
          footer: '<button class="btn" data-close>Close</button>' + (r.status === "Submitted" ? '<button class="btn btn-brand" data-rv>Mark reviewed</button>' : "") });
        RG.on(m.body, "[data-att]", "click", function (ev, a) { API.blob("/reports/attachments/" + a.dataset.att + "/download").then(function (f) { global.open(f.url, "_blank"); }).catch(RG.toastErr); });
        var rv = m.foot.querySelector("[data-rv]");
        if (rv) rv.addEventListener("click", function () {
          RG.setBusy(rv, true, "Saving…");
          API.post("/reports/" + r.id + "/review", { review_notes: (m.body.querySelector("#pr-notes") || {}).value || null })
            .then(function () { m.close(); RG.toastOk("Report reviewed."); reports(); })
            .catch(function (err) { RG.setBusy(rv, false); RG.toastErr(err); });
        });
      }).catch(RG.toastErr);
    });

    Promise.all([
      API.get("/employees/" + id),
      API.get("/attendance/sessions", { employee_id: id, date: localISO(new Date()) }).then(function (d) { return d.items; }).catch(function () { return []; })
    ]).then(function (res) {
      state.person = res[0];
      hero(res[0], res[1]);
      document.title = res[0].full_name + " · Rocket Genie HRMS";
      show();
    }).catch(function (err) {
      host.innerHTML = '<div class="card">' + denied(err) + "</div>";
    });
  }

  global.RGPerson = { mount: mount, chainHtml: chainHtml, personRow: personRow };

  // Stand-alone page: person.html?id=123
  if (document.body.dataset.page === "person") {
    var ctx = RG.boot({ scope: document.body.dataset.scope, active: document.body.dataset.active || "employees", title: "Person", subtitle: "Monitoring" });
    if (!ctx) return;
    var id = RG.param("id");
    if (!id) { ctx.page.innerHTML = '<div class="card">' + RG.emptyState("Pick someone first", "Open a person from a list.") + "</div>"; return; }
    ctx.page.innerHTML = '<div class="page-head"><div><h1>Monitoring</h1><p class="sub">Attendance, reports, tasks, leave and records for one person.</p></div>' +
      '<div class="page-actions"><button class="btn" onclick="history.back()">Back</button></div></div><div id="person-host"></div>';
    mount(document.getElementById("person-host"), id, ctx.scope);
  }
})(window);
