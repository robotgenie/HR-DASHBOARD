/* work-monitor.js - attendance (check-in/out selfies + location), assigned
   tasks and hourly updates, per day. Used by the Admin (whole organisation,
   HR included), HR (their hierarchy) and Managers (their team). Who appears
   is decided by the API's hierarchy rules. */
(function () {
  "use strict";
  var ctx = RG.boot({ scope: "hr", active: "work-monitor", title: "Work Monitor", subtitle: "Attendance, tasks & hourly updates" });
  if (!ctx) return;

  function t12(v) { return v ? RG.fmt.time(v) : "—"; }
  function mins(n) { n = Math.max(0, Number(n || 0)); return Math.floor(n / 60) + "h " + String(n % 60).padStart(2, "0") + "m"; }
  function localISO(d) { return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0"); }
  function locLink(l) {
    if (!l) return '<span class="muted">—</span>';
    return '<a href="' + RG.esc(l.map_url) + '" target="_blank" rel="noopener">' + RG.esc(l.label) + "</a>" + (l.accuracy_m ? ' <span class="small muted">±' + l.accuracy_m + "m</span>" : "");
  }

  var SCOPE = ctx.scope;
  var state = { tab: RG.param("tab") || "today", date: RG.param("date") || localISO(new Date()), type: "", q: "", employees: [],
                department_id: RG.param("department_id") || "", reporting_hr_id: RG.param("reporting_hr_id") || "",
                reporting_manager_id: RG.param("reporting_manager_id") || "" };
  var PERSON_LINK = SCOPE === "hr" ? "employee-details.html?id=" : "person.html?id=";
  var HEAD = {
    admin: ["Attendance & Hourly", "Check-In/Check-Out of every HR, manager, employee and intern, with selfies, location, tasks, hourly updates and report status."],
    hr: ["Work Monitor", "Check-In/Check-Out with live selfie and location, assigned tasks, hourly updates and report status for your hierarchy."],
    manager: ["Team Attendance & Work", "Your team's Check-In/Check-Out, selfies, hourly updates, tasks and report status."]
  }[SCOPE] || ["Work Monitor", ""];

  ctx.page.innerHTML =
    '<div class="page-head"><div><h1>' + RG.esc(HEAD[0]) + '</h1><p class="sub">' + RG.esc(HEAD[1]) + '</p></div>' +
      '<div class="page-actions"><button class="btn btn-brand" data-assign>' + RG.icon("plus", 16) + " Assign task</button></div></div>" +
    '<div id="strip"></div>' +
    '<div class="card"><div class="tabs" role="tablist">' +
      '<button class="tab" data-tab="today">Attendance &amp; work</button>' +
      '<button class="tab" data-tab="tasks">Tasks</button>' +
      '<button class="tab" data-tab="hourly">Hourly updates</button></div>' +
      '<div class="toolbar"><div class="filters" style="margin-left:0">' +
        '<input type="date" id="m-date" value="' + state.date + '" aria-label="Date">' +
        '<select id="m-type" aria-label="Type"><option value="">Everyone</option>' +
          (SCOPE === "admin" ? '<option value="HR">HR</option>' : '') +
          (SCOPE !== "manager" ? '<option value="Manager">Managers</option>' : '') +
          '<option value="employee">Employees</option><option value="intern">Interns</option></select>' +
        (SCOPE !== "manager" ? '<select id="m-dept" aria-label="Department"><option value="">All departments</option></select>' : '') +
        (SCOPE === "admin" ? '<select id="m-hr" aria-label="HR"><option value="">All HR</option></select>' : '') +
        (SCOPE !== "manager" ? '<select id="m-mgr" aria-label="Manager"><option value="">All managers</option></select>' : '') +
        '<input type="search" id="m-q" placeholder="Search name or ID" aria-label="Search">' +
      "</div></div>" +
      '<div id="m-host">' + RG.skeletonRows(6) + "</div></div>";

  var host = document.getElementById("m-host");
  var cache = {};

  function match(name, code, isIntern, ptype) {
    if (state.type === "intern" && !isIntern) return false;
    if (state.type === "employee" && (isIntern || (ptype && ptype !== "Employee"))) return false;
    if ((state.type === "HR" || state.type === "Manager") && ptype !== state.type) return false;
    if (!state.q) return true;
    var q = state.q.toLowerCase();
    return String(name || "").toLowerCase().indexOf(q) >= 0 || String(code || "").toLowerCase().indexOf(q) >= 0;
  }

  function strip(t) {
    document.getElementById("strip").innerHTML = '<div class="today-strip">' + [
      [SCOPE === "manager" ? "Team members" : "People", t.employees, ""], ["Checked in", t.checked_in, "ok"], ["Checked out", t.checked_out, ""],
      ["Late check-ins", t.late, t.late ? "warn" : ""], ["On leave", t.on_leave, ""],
      ["Hourly updates", t.hourly_submitted, "ok"], ["Hourly due / missed", t.hourly_due, t.hourly_due ? "bad" : ""],
      ["Open tasks", t.open_tasks, ""]
    ].map(function (c) { return '<div class="ts ' + c[2] + '"><span>' + c[0] + "</span><b>" + c[1] + "</b></div>"; }).join("") + "</div>";
  }

  function selfieCell(s) {
    if (!s) return "—";
    return '<div class="selfie-pair">' +
      (s.check_in_selfie ? '<img class="selfie-thumb" alt="Check-In selfie" data-selfie="' + s.id + '/check-in" title="Check-In selfie">' : "") +
      (s.check_out_selfie ? '<img class="selfie-thumb" alt="Check-Out selfie" data-selfie="' + s.id + '/check-out" title="Check-Out selfie">' : "") + "</div>";
  }
  function hydrateSelfies(root) {
    root.querySelectorAll("img[data-selfie]").forEach(function (img) {
      if (img.dataset.loaded) return;
      img.dataset.loaded = "1";
      API.blob("/attendance/sessions/" + img.dataset.selfie.replace("/", "/selfie/")).then(function (f) { img.src = f.url; img.dataset.full = f.url; })
        .catch(function () { img.replaceWith(document.createTextNode("—")); });
    });
  }

  function renderToday(data) {
    strip(data.totals);
    var rows = data.items.filter(function (r) { return match(r.employee_name, r.employee_code, r.is_intern, r.person_type); });
    if (!rows.length) { host.innerHTML = RG.emptyState("Nobody matches", "Try another date or filter.", "", "users"); return; }
    host.innerHTML = '<div class="table-scroll"><table class="data"><thead><tr>' +
      "<th>Employee</th><th>Check-In</th><th>Check-Out</th><th>Selfies</th><th>Hours</th><th>Leave</th><th>Noon</th><th>EOD</th><th>Hourly</th><th>Tasks</th></tr></thead><tbody>" +
      rows.map(function (r) {
        var s = r.session;
        var tasks = r.tasks || [];
        return "<tr>" +
          '<td data-label="Employee"><a href="' + PERSON_LINK + r.employee_id + '"><b>' + RG.esc(r.employee_name) + "</b></a>" +
            '<div class="small muted">' + RG.esc(r.employee_code || "") + " · " + RG.esc(r.person_type || "") + " · " + RG.esc(r.department || "") + "</div>" +
            (r.reporting_manager || r.reporting_hr ? '<div class="small muted">Reports to ' + RG.esc(r.reporting_manager || r.reporting_hr) + "</div>" : "") + "</td>" +
          '<td data-label="Check-In" class="mon-cell">' + (s ? "<b>" + t12(s.check_in_time) + "</b>" +
            (s.late_minutes ? '<small class="text-bad">' + RG.esc(s.late_label) + " late · " + RG.esc(s.late_reason || "") + "</small>" : "<small>On time</small>") +
            "<small>" + locLink(s.check_in_location) + "</small>" : '<span class="muted">Not checked in</span>') + "</td>" +
          '<td data-label="Check-Out" class="mon-cell">' + (s && s.check_out_time ? "<b>" + t12(s.check_out_time) + "</b>" +
            (s.extra_minutes ? '<small class="text-ok">+' + mins(s.extra_minutes) + " extra</small>" : "") + "<small>" + locLink(s.check_out_location) + "</small>"
            : (s ? '<span class="badge info">Working</span>' : "—")) + "</td>" +
          '<td data-label="Selfies">' + selfieCell(s) + "</td>" +
          '<td data-label="Hours">' + (s ? mins(s.worked_minutes) : "—") + "</td>" +
          '<td data-label="Leave">' + (r.leave_status ? RG.badge(r.leave_status) : '<span class="muted">—</span>') + "</td>" +
          '<td data-label="Noon">' + RG.badge(r.noon_report) + "</td>" +
          '<td data-label="EOD">' + RG.badge(r.eod_report) + "</td>" +
          '<td data-label="Hourly"><b>' + r.hourly_submitted + "/" + r.hourly_applicable + "</b>" + (r.hourly_missing ? '<div class="small text-bad">' + r.hourly_missing + " due/missed</div>" : "") +
            (r.hourly_submitted ? '<div><button class="btn btn-sm btn-ghost" data-show-hourly="' + r.employee_id + '">View</button></div>' : "") + "</td>" +
          '<td data-label="Tasks">' + (tasks.length ? tasks.map(function (t) {
            return '<div class="small"><b>' + RG.esc(t.title) + "</b> · " + t.progress_percent + "%" + (t.target ? " (" + t.completed + "/" + t.target + ")" : "") + "</div>";
          }).join("") : '<span class="muted">—</span>') + "</td>" +
          "</tr>";
      }).join("") + "</tbody></table></div>";
    hydrateSelfies(host);
  }

  function renderTasks(items) {
    var rows = items.filter(function (t) { return match(t.employee_name, t.employee_code, t.is_intern, t.person_type); });
    if (!rows.length) { host.innerHTML = RG.emptyState("No tasks yet", "Use “Assign task” to give employees and interns their work.", "", "clipboard"); return; }
    host.innerHTML = '<div class="table-scroll"><table class="data"><thead><tr><th>Task</th><th>Employee</th><th>Assigned by</th><th>Dates</th><th>Target</th><th>Progress</th><th>Status</th><th></th></tr></thead><tbody>' +
      rows.map(function (t) {
        return "<tr>" +
          '<td data-label="Task"><b>' + RG.esc(t.title) + "</b>" + (t.description ? '<div class="small muted truncate" style="max-width:260px">' + RG.esc(t.description) + "</div>" : "") + "</td>" +
          '<td data-label="Employee">' + RG.esc(t.employee_name) + '<div class="small muted">' + RG.esc(t.person_type || (t.is_intern ? "Intern" : "Employee")) + "</div>" +
            (t.parent_task_title ? '<div class="small muted">Part of: ' + RG.esc(t.parent_task_title) + "</div>" : "") + "</td>" +
          '<td data-label="Assigned by">' + RG.esc(t.assigned_by || "—") + "</td>" +
          '<td data-label="Dates" class="nowrap">' + RG.fmt.date(t.task_date) + (t.due_date ? " → " + RG.fmt.date(t.due_date) : "") + "</td>" +
          '<td data-label="Target">' + (t.target ? t.completed + " / " + t.target + (t.unit ? " " + RG.esc(t.unit) : "") + '<div class="small muted">' + t.remaining + " remaining</div>" : "—") + "</td>" +
          '<td data-label="Progress" style="min-width:120px"><div class="bar thin"><span style="width:' + t.progress_percent + '%"></span></div><span class="small">' + t.progress_percent + "% · " + t.updates_count + " updates</span></td>" +
          '<td data-label="Status">' + RG.badge(t.status) + "</td>" +
          '<td class="actions"><button class="btn btn-sm" data-task="' + t.id + '">Open</button></td></tr>';
      }).join("") + "</tbody></table></div>";
  }

  function renderHourly(items) {
    var rows = items.filter(function (u) { return match(u.employee_name, u.employee_code, !!(cache.interns && cache.interns[u.employee_id])); });
    if (!rows.length) { host.innerHTML = RG.emptyState("No hourly updates", "Nothing was submitted for this date.", "", "bell"); return; }
    host.innerHTML = '<div class="table-scroll"><table class="data"><thead><tr><th>Employee</th><th>Hour</th><th>Task</th><th>Assigned by</th><th>Work completed</th><th>Progress</th><th>Remaining</th><th>Files</th><th></th></tr></thead><tbody>' +
      rows.map(function (u) {
        return "<tr>" +
          '<td data-label="Employee"><b>' + RG.esc(u.employee_name) + '</b><div class="small muted">' + RG.esc(u.department || "") + "</div></td>" +
          '<td data-label="Hour" class="nowrap">' + RG.esc(u.slot_label) + '<div class="small muted">sent ' + RG.fmt.dateTime(u.submitted_at) + "</div></td>" +
          '<td data-label="Task">' + RG.esc(u.task_title || "General work") + "</td>" +
          '<td data-label="Assigned by">' + RG.esc(u.assigned_by || "—") + "</td>" +
          '<td data-label="Work completed"><div class="truncate" style="max-width:260px">' + RG.esc(u.work_completed) + "</div></td>" +
          '<td data-label="Progress">' + (u.task_target ? u.task_completed + "/" + u.task_target : (u.task_progress != null ? u.task_progress + "%" : "—")) + " " + RG.badge(u.task_status) + "</td>" +
          '<td data-label="Remaining"><div class="truncate" style="max-width:200px">' + RG.esc(u.remaining_work || "—") + "</div></td>" +
          '<td data-label="Files">' + u.attachments.length + "</td>" +
          '<td class="actions"><button class="btn btn-sm" data-update="' + u.id + '">View</button></td></tr>';
      }).join("") + "</tbody></table></div>";
    cache.updates = rows;
  }

  function load() {
    document.querySelectorAll("[data-tab]").forEach(function (b) { b.classList.toggle("active", b.dataset.tab === state.tab); });
    host.innerHTML = RG.skeletonRows(6);
    var filters = { department_id: state.department_id, reporting_hr_id: state.reporting_hr_id, reporting_manager_id: state.reporting_manager_id };
    var today = API.get("/attendance/hr/today", Object.assign({ date: state.date }, filters)).then(function (d) {
      cache.today = d; cache.interns = {};
      d.items.forEach(function (r) { cache.interns[r.employee_id] = r.is_intern; });
      strip(d.totals); return d;
    });
    if (state.tab === "today") return today.then(renderToday).catch(fail);
    if (state.tab === "tasks") return today.then(function () { return API.get("/tasks", Object.assign({ limit: 300 }, filters)); }).then(function (d) { cache.tasks = d.items; renderTasks(d.items); }).catch(fail);
    return today.then(function () { return API.get("/hourly-updates", { date: state.date, limit: 500 }); }).then(function (d) {
      var visible = {};
      (cache.today.items || []).forEach(function (r) { visible[r.employee_id] = true; });
      var items = (state.department_id || state.reporting_hr_id || state.reporting_manager_id)
        ? d.items.filter(function (u) { return visible[u.employee_id]; }) : d.items;
      cache.hourly = items; renderHourly(items);
    }).catch(fail);
  }
  function fail(err) { host.innerHTML = RG.errorState(err.message, "retry"); var r = document.getElementById("retry"); if (r) r.addEventListener("click", load); }

  function showUpdate(u) {
    if (window.RGWork) { window.RGWork.showUpdate(u); return; }
  }

  function assignModal() {
    var list = state.employees;
    var modal = RG.openModal({
      title: "Assign task", size: "lg",
      body: '<form class="form-grid" id="task-form" novalidate>' +
        '<div class="field full"><label for="t-title">Task <span class="req">*</span></label><input id="t-title" maxlength="200" placeholder="e.g. Hire 5 Employees"></div>' +
        '<div class="field full"><label for="t-desc">Description</label><textarea id="t-desc" rows="3" maxlength="5000"></textarea></div>' +
        '<div class="field"><label for="t-target">Target (optional)</label><input id="t-target" type="number" min="1" placeholder="e.g. 5"><span class="help">Numeric target — completed and remaining are tracked from hourly updates.</span></div>' +
        '<div class="field"><label for="t-unit">Unit</label><input id="t-unit" maxlength="40" placeholder="e.g. hires, calls, pages"></div>' +
        '<div class="field"><label for="t-date">Start date</label><input id="t-date" type="date" value="' + state.date + '"></div>' +
        '<div class="field"><label for="t-due">Due date</label><input id="t-due" type="date"></div>' +
        '<div class="field full"><label>Assign to <span class="req">*</span></label>' +
          '<div class="row wrap mb-2"><button type="button" class="btn btn-sm" data-pick="employee">All employees</button><button type="button" class="btn btn-sm" data-pick="intern">All interns</button><button type="button" class="btn btn-sm btn-ghost" data-pick="none">Clear</button></div>' +
          '<div class="chip-select">' + list.map(function (e) {
            return '<label><input type="checkbox" value="' + e.id + '" data-kind="' + (e.department === "Internship" ? "intern" : "employee") + '"> ' + RG.esc(e.full_name) +
              ' <span class="small muted">' + RG.esc(e.role_label || "") + (e.department ? " · " + RG.esc(e.department) : "") + "</span></label>";
          }).join("") + "</div></div></form>",
      footer: '<button class="btn" data-close>Cancel</button><button class="btn btn-brand" data-save-task>Assign</button>'
    });
    var b = modal.body;
    RG.on(b, "[data-pick]", "click", function (e, btn) {
      b.querySelectorAll(".chip-select input").forEach(function (i) { i.checked = btn.dataset.pick !== "none" && i.dataset.kind === btn.dataset.pick ? true : (btn.dataset.pick === "none" ? false : i.checked); });
    });
    modal.foot.querySelector("[data-save-task]").addEventListener("click", function () {
      var btn = this;
      var ids = Array.prototype.map.call(b.querySelectorAll(".chip-select input:checked"), function (i) { return Number(i.value); });
      var title = b.querySelector("#t-title").value.trim();
      if (title.length < 3) { RG.toastErr({ message: "Enter the task (at least 3 characters)." }); return; }
      if (!ids.length) { RG.toastErr({ message: "Choose at least one employee or intern." }); return; }
      var target = b.querySelector("#t-target").value;
      RG.setBusy(btn, true, "Assigning…");
      API.post("/tasks", {
        employee_ids: ids, title: title, description: b.querySelector("#t-desc").value.trim() || null,
        target: target ? Number(target) : null, unit: b.querySelector("#t-unit").value.trim() || null,
        task_date: b.querySelector("#t-date").value || null, due_date: b.querySelector("#t-due").value || null
      }).then(function (res) {
        modal.close(); RG.toastOk("Task assigned to " + res.items.length + (res.items.length === 1 ? " person." : " people."));
        state.tab = "tasks"; load();
      }).catch(function (err) { RG.setBusy(btn, false); RG.toastErr(err); });
    });
  }

  function taskModal(id) {
    API.get("/tasks/" + id).then(function (t) {
      var m = RG.openModal({
        title: t.title, size: "lg",
        body: (window.RGWork ? window.RGWork.taskCards([t], { showEmployee: true }) : "") +
          '<h4 class="mt-4">Hourly updates on this task</h4>' +
          (t.hourly_updates.length ? '<ul class="status-list">' + t.hourly_updates.map(function (u) {
            return '<li><span><b>' + RG.fmt.date(u.update_date) + " · " + RG.esc(u.slot_label) + "</b><small>" + RG.esc(u.work_completed) + "</small></span>" +
              '<button class="btn btn-sm" data-update-inline="' + u.id + '">View</button></li>';
          }).join("") + "</ul>" : '<p class="small muted">No hourly updates yet.</p>') +
          '<div class="form-grid mt-4"><div class="field"><label for="tm-status">Status</label><select id="tm-status">' +
            ["Pending", "In Progress", "Completed", "Cancelled"].map(function (s) { return "<option" + (s === t.status ? " selected" : "") + ">" + s + "</option>"; }).join("") + "</select></div>" +
          '<div class="field"><label for="tm-due">Due date</label><input id="tm-due" type="date" value="' + (t.due_date || "") + '"></div></div>',
        footer: '<button class="btn" data-close>Close</button><button class="btn btn-brand" data-save>Save</button>'
      });
      RG.on(m.body, "[data-update-inline]", "click", function (e, b) {
        var u = t.hourly_updates.filter(function (x) { return String(x.id) === b.dataset.updateInline; })[0];
        if (u) showUpdate(u);
      });
      m.foot.querySelector("[data-save]").addEventListener("click", function () {
        var btn = this; RG.setBusy(btn, true, "Saving…");
        API.patch("/tasks/" + t.id, { status: m.body.querySelector("#tm-status").value, due_date: m.body.querySelector("#tm-due").value || null })
          .then(function () { m.close(); RG.toastOk("Task updated."); load(); })
          .catch(function (err) { RG.setBusy(btn, false); RG.toastErr(err); });
      });
    }).catch(RG.toastErr);
  }

  function lookups() {
    if (SCOPE === "manager") return;
    API.get("/departments").then(function (d) {
      var el = document.getElementById("m-dept");
      if (el) el.innerHTML = '<option value="">All departments</option>' + RG.optionList(d, "id", "name", state.department_id);
    }).catch(function () {});
    if (SCOPE === "admin") API.get("/hierarchy/candidates", { role: "HR_ADMIN" }).then(function (r) {
      document.getElementById("m-hr").innerHTML = '<option value="">All HR</option>' + RG.optionList(r.items, "id", "full_name", state.reporting_hr_id);
    }).catch(function () {});
    API.get("/hierarchy/candidates", { role: "MANAGER" }).then(function (r) {
      document.getElementById("m-mgr").innerHTML = '<option value="">All managers</option>' + RG.optionList(r.items, "id", "full_name", state.reporting_manager_id);
    }).catch(function () {});
  }
  ["m-dept", "m-hr", "m-mgr"].forEach(function (id) {
    var el = document.getElementById(id);
    if (!el) return;
    el.addEventListener("change", function () {
      state.department_id = (document.getElementById("m-dept") || {}).value || "";
      state.reporting_hr_id = (document.getElementById("m-hr") || {}).value || "";
      state.reporting_manager_id = (document.getElementById("m-mgr") || {}).value || "";
      load();
    });
  });
  lookups();

  RG.on(ctx.page, "[data-tab]", "click", function (e, b) { state.tab = b.dataset.tab; load(); });
  document.getElementById("m-date").addEventListener("change", function (e) { state.date = e.target.value; load(); });
  document.getElementById("m-type").addEventListener("change", function (e) { state.type = e.target.value; load(); });
  document.getElementById("m-q").addEventListener("input", RG.debounce(function (e) { state.q = e.target.value.trim(); load(); }, 300));
  RG.on(ctx.page, "[data-assign]", "click", function () {
    if (state.employees.length) { assignModal(); return; }
    // Who can be given work: Admin -> HR/managers/employees/interns,
    // HR -> managers/employees/interns of their hierarchy, Manager -> team.
    var LEVEL = { ADMIN: 4, HR_ADMIN: 3, MANAGER: 2, EMPLOYEE: 1 };
    var mine = LEVEL[(API.session.user() || {}).role] || 0;
    API.get("/employees", { page: 1, page_size: 100, employment_status: "Active", include_self: false }).then(function (res) {
      state.employees = (res.items || []).filter(function (e) { return e.is_active && (LEVEL[e.role] || 0) < mine; });
      if (!state.employees.length) { RG.toastErr({ message: "There is nobody you can assign tasks to yet." }); return; }
      assignModal();
    }).catch(RG.toastErr);
  });
  RG.on(ctx.page, "[data-task]", "click", function (e, b) { taskModal(b.dataset.task); });
  RG.on(ctx.page, "[data-update]", "click", function (e, b) {
    var u = (cache.updates || []).filter(function (x) { return String(x.id) === b.dataset.update; })[0];
    if (u) showUpdate(u);
  });
  RG.on(ctx.page, "[data-show-hourly]", "click", function (e, b) {
    state.tab = "hourly";
    var row = (cache.today.items || []).filter(function (r) { return String(r.employee_id) === b.dataset.showHourly; })[0];
    state.q = row ? row.employee_name : ""; document.getElementById("m-q").value = state.q; load();
  });
  RG.on(ctx.page, "img[data-selfie]", "click", function (e, img) {
    if (!img.dataset.full) return;
    RG.openModal({ title: img.alt, size: "sm", body: '<img src="' + img.dataset.full + '" alt="' + RG.esc(img.alt) + '" style="width:100%;border-radius:12px">', footer: '<button class="btn" data-close>Close</button>' });
  });
  load();
})();
