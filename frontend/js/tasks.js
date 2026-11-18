/* tasks.js - task centre for the Admin, HR and Managers.
   ADMIN -> HR / Manager / Employee / Intern, HR -> Manager / Employee / Intern,
   Manager -> own team. A task assigned to you can be divided among the people
   below you (each part is a normal task linked to the original). The API
   enforces who may assign to whom. */
(function () {
  "use strict";
  var ctx = RG.boot({ scope: document.body.dataset.scope, active: "tasks", title: "Tasks", subtitle: "Assign, divide and track" });
  if (!ctx) return;
  var SCOPE = ctx.scope;
  var LEVEL = { ADMIN: 4, HR_ADMIN: 3, MANAGER: 2, EMPLOYEE: 1 };
  var myLevel = LEVEL[(API.session.user() || {}).role] || 0;
  var state = { tab: RG.param("tab") || "team", status: "", department_id: "", reporting_hr_id: "", reporting_manager_id: "", people: null, items: [] };

  var TABS = [["team", SCOPE === "manager" ? "Team tasks" : "All tasks"], ["assigned", "Assigned by me"]];
  if (SCOPE !== "admin") TABS.push(["mine", "Assigned to me"]);

  ctx.page.innerHTML =
    '<div class="page-head"><div><h1>' + (SCOPE === "manager" ? "Team Tasks" : "Tasks") + "</h1>" +
      '<p class="sub">' + ({
        admin: "Assign work to HR, managers, employees and interns, and track every task in the organisation.",
        hr: "Assign work to the managers, employees and interns in your hierarchy. Divide tasks the Admin gives you.",
        manager: "Assign work to your team and divide tasks you receive from HR among team members."
      }[SCOPE] || "") + "</p></div>" +
      '<div class="page-actions"><button class="btn btn-brand" data-assign>' + RG.icon("plus", 16) + " Assign task</button></div></div>" +
    '<div class="card"><div class="tabs" role="tablist">' + TABS.map(function (t) { return '<button class="tab" data-tab="' + t[0] + '">' + t[1] + "</button>"; }).join("") + "</div>" +
      '<div class="toolbar"><div class="filters" style="margin-left:0">' +
        '<select id="k-status"><option value="">Any status</option><option>Pending</option><option>In Progress</option><option>Completed</option><option>Cancelled</option></select>' +
        (SCOPE !== "manager" ? '<select id="k-dept"><option value="">All departments</option></select>' : "") +
        (SCOPE === "admin" ? '<select id="k-hr"><option value="">All HR</option></select>' : "") +
        (SCOPE !== "manager" ? '<select id="k-mgr"><option value="">All managers</option></select>' : "") +
      '</div></div><div id="k-host">' + RG.skeletonRows(6) + "</div></div>";
  var host = document.getElementById("k-host");

  function people() {
    if (state.people) return Promise.resolve(state.people);
    return API.get("/employees", { page: 1, page_size: 100, employment_status: "Active", include_self: false }).then(function (r) {
      state.people = (r.items || []).filter(function (e) { return e.is_active && (LEVEL[e.role] || 0) < myLevel; });
      return state.people;
    });
  }

  function render() {
    var items = state.items;
    if (!items.length) {
      host.innerHTML = RG.emptyState(state.tab === "mine" ? "Nothing assigned to you" : "No tasks", state.tab === "mine" ? "Tasks from your HR or the Admin appear here." : "Use “Assign task” to give people their work.", "", "target");
      return;
    }
    host.innerHTML = '<div class="table-scroll"><table class="data"><thead><tr><th>Task</th><th>Assigned to</th><th>Assigned by</th><th>Dates</th><th>Progress</th><th>Status</th><th></th></tr></thead><tbody>' +
      items.map(function (t) {
        var canDivide = state.tab === "mine" && t.status !== "Cancelled" && t.status !== "Completed";
        return "<tr>" +
          '<td data-label="Task"><b>' + RG.esc(t.title) + "</b>" +
            (t.parent_task_title ? '<div class="small muted">Part of: ' + RG.esc(t.parent_task_title) + "</div>" : "") +
            (t.subtasks_count ? '<div class="small muted">Divided into ' + t.subtasks_count + " part(s)</div>" : "") + "</td>" +
          '<td data-label="Assigned to">' + RG.esc(t.employee_name) + '<div class="small muted">' + RG.esc(t.person_type || "") + " · " + RG.esc(t.department || "") + "</div></td>" +
          '<td data-label="Assigned by">' + RG.esc(t.assigned_by || "—") + "</td>" +
          '<td data-label="Dates" class="nowrap">' + RG.fmt.date(t.task_date) + (t.due_date ? " → " + RG.fmt.date(t.due_date) : "") + "</td>" +
          '<td data-label="Progress" style="min-width:120px"><div class="bar thin"><span style="width:' + t.progress_percent + '%"></span></div><span class="small">' +
            t.progress_percent + "%" + (t.target ? " · " + t.completed + "/" + t.target + (t.unit ? " " + RG.esc(t.unit) : "") : "") + "</span></td>" +
          '<td data-label="Status">' + RG.badge(t.status) + "</td>" +
          '<td class="actions">' + (canDivide ? '<button class="btn btn-sm btn-brand" data-divide="' + t.id + '">Divide</button> ' : "") +
            (state.tab !== "mine" ? '<button class="btn btn-sm" data-edit="' + t.id + '">Update</button>' : "") + "</td></tr>";
      }).join("") + "</tbody></table></div>";
  }

  function load() {
    host.innerHTML = RG.skeletonRows(6);
    ctx.page.querySelectorAll("[data-tab]").forEach(function (b) { b.classList.toggle("active", b.dataset.tab === state.tab); });
    var q = { limit: 400, status: state.status, department_id: state.department_id, reporting_hr_id: state.reporting_hr_id,
              reporting_manager_id: state.reporting_manager_id };
    if (state.tab === "mine") q = { mine: true, limit: 200, status: state.status };
    if (state.tab === "assigned") q.assigned_by_me = true;
    API.get("/tasks", q).then(function (d) { state.items = d.items || []; render(); })
      .catch(function (err) { host.innerHTML = RG.errorState(err.message); });
  }

  function assignModal(prefill) {
    people().then(function (list) {
      if (!list.length) { RG.toastErr({ message: "There is nobody below you to assign tasks to yet." }); return; }
      var m = RG.openModal({
        title: "Assign task", size: "lg",
        body: '<form class="form-grid" novalidate>' +
          '<div class="field full"><label for="a-title">Task <span class="req">*</span></label><input id="a-title" maxlength="200" value="' + RG.esc((prefill && prefill.title) || "") + '"></div>' +
          '<div class="field full"><label for="a-desc">Description</label><textarea id="a-desc" rows="3" maxlength="5000"></textarea></div>' +
          '<div class="field"><label for="a-target">Target (optional)</label><input id="a-target" type="number" min="1"></div>' +
          '<div class="field"><label for="a-unit">Unit</label><input id="a-unit" maxlength="40" placeholder="e.g. calls, posts"></div>' +
          '<div class="field"><label for="a-date">Start date</label><input id="a-date" type="date"></div>' +
          '<div class="field"><label for="a-due">Due date</label><input id="a-due" type="date"></div>' +
          '<div class="field full"><label>Assign to <span class="req">*</span></label><div class="chip-select">' + list.map(function (e) {
            return '<label><input type="checkbox" value="' + e.id + '"> ' + RG.esc(e.full_name) + ' <span class="small muted">' + RG.esc(e.role_label || "") +
              (e.department ? " · " + RG.esc(e.department) : "") + "</span></label>";
          }).join("") + "</div></div></form>",
        footer: '<button class="btn" data-close>Cancel</button><button class="btn btn-brand" data-go>Assign</button>'
      });
      m.foot.querySelector("[data-go]").addEventListener("click", function () {
        var b = m.body, btn = this;
        var ids = Array.prototype.map.call(b.querySelectorAll(".chip-select input:checked"), function (i) { return Number(i.value); });
        var title = b.querySelector("#a-title").value.trim();
        if (title.length < 3) { RG.toastErr({ message: "Enter the task (at least 3 characters)." }); return; }
        if (!ids.length) { RG.toastErr({ message: "Choose at least one person." }); return; }
        var target = b.querySelector("#a-target").value;
        RG.setBusy(btn, true, "Assigning…");
        API.post("/tasks", { employee_ids: ids, title: title, description: b.querySelector("#a-desc").value.trim() || null,
          target: target ? Number(target) : null, unit: b.querySelector("#a-unit").value.trim() || null,
          task_date: b.querySelector("#a-date").value || null, due_date: b.querySelector("#a-due").value || null
        }).then(function (r) { m.close(); RG.toastOk("Assigned to " + r.items.length + (r.items.length === 1 ? " person." : " people.")); state.tab = "assigned"; load(); })
          .catch(function (err) { RG.setBusy(btn, false); RG.toastErr(err); });
      });
    }).catch(RG.toastErr);
  }

  function divideModal(id) {
    var task = state.items.filter(function (t) { return String(t.id) === String(id); })[0];
    people().then(function (list) {
      if (!list.length) { RG.toastErr({ message: "You have no team members to divide this task among." }); return; }
      function rowHtml() {
        return '<div class="form-grid divide-row" style="grid-template-columns:2fr 2fr 1fr auto;align-items:end">' +
          '<div class="field"><label>Team member</label><select data-dv-emp>' + RG.optionList(list, "id", "full_name") + "</select></div>" +
          '<div class="field"><label>Part</label><input data-dv-title maxlength="200" value="' + RG.esc(task.title) + '"></div>' +
          '<div class="field"><label>Target</label><input data-dv-target type="number" min="1"></div>' +
          '<button type="button" class="btn btn-sm btn-ghost" data-dv-del title="Remove">' + RG.icon("x", 14) + "</button></div>";
      }
      var m = RG.openModal({
        title: "Divide task · " + task.title, size: "lg",
        body: '<p class="small muted">Each part becomes a task for that person, linked to “' + RG.esc(task.title) + '”. Their hourly updates and progress roll up here.' +
          (task.target ? " Original target: " + task.target + (task.unit ? " " + RG.esc(task.unit) : "") + "." : "") + "</p>" +
          '<div data-dv-rows>' + rowHtml() + rowHtml() + "</div>" +
          '<button type="button" class="btn btn-sm mt-2" data-dv-add>' + RG.icon("plus", 14) + " Add part</button>",
        footer: '<button class="btn" data-close>Cancel</button><button class="btn btn-brand" data-go>Divide</button>'
      });
      var rows = m.body.querySelector("[data-dv-rows]");
      RG.on(m.body, "[data-dv-add]", "click", function () { rows.insertAdjacentHTML("beforeend", rowHtml()); });
      RG.on(m.body, "[data-dv-del]", "click", function (e, b) { if (rows.children.length > 1) b.closest(".divide-row").remove(); });
      m.foot.querySelector("[data-go]").addEventListener("click", function () {
        var btn = this;
        var parts = Array.prototype.map.call(rows.querySelectorAll(".divide-row"), function (r) {
          var t = r.querySelector("[data-dv-target]").value;
          return { employee_id: Number(r.querySelector("[data-dv-emp]").value), title: r.querySelector("[data-dv-title]").value.trim() || null,
                   target: t ? Number(t) : null };
        });
        RG.setBusy(btn, true, "Dividing…");
        API.post("/tasks/" + task.id + "/divide", { parts: parts }).then(function (r) {
          m.close(); RG.toastOk("Task divided into " + r.items.length + " part(s)."); load();
        }).catch(function (err) { RG.setBusy(btn, false); RG.toastErr(err); });
      });
    }).catch(RG.toastErr);
  }

  function editModal(id) {
    var t = state.items.filter(function (x) { return String(x.id) === String(id); })[0];
    var m = RG.openModal({
      title: t.title, size: "sm",
      body: '<div class="form-grid"><div class="field full"><label for="e-status">Status</label><select id="e-status">' +
        ["Pending", "In Progress", "Completed", "Cancelled"].map(function (s) { return "<option" + (s === t.status ? " selected" : "") + ">" + s + "</option>"; }).join("") +
        '</select></div><div class="field full"><label for="e-due">Due date</label><input id="e-due" type="date" value="' + (t.due_date || "") + '"></div></div>',
      footer: '<button class="btn" data-close>Cancel</button><button class="btn btn-brand" data-go>Save</button>'
    });
    m.foot.querySelector("[data-go]").addEventListener("click", function () {
      var btn = this; RG.setBusy(btn, true, "Saving…");
      API.patch("/tasks/" + t.id, { status: m.body.querySelector("#e-status").value, due_date: m.body.querySelector("#e-due").value || null })
        .then(function () { m.close(); RG.toastOk("Task updated."); load(); })
        .catch(function (err) { RG.setBusy(btn, false); RG.toastErr(err); });
    });
  }

  RG.on(ctx.page, "[data-tab]", "click", function (e, b) { state.tab = b.dataset.tab; load(); });
  RG.on(ctx.page, "[data-assign]", "click", function () { assignModal(); });
  RG.on(ctx.page, "[data-divide]", "click", function (e, b) { divideModal(b.dataset.divide); });
  RG.on(ctx.page, "[data-edit]", "click", function (e, b) { editModal(b.dataset.edit); });
  document.getElementById("k-status").addEventListener("change", function (e) { state.status = e.target.value; load(); });
  [["k-dept", "department_id", "/departments", null], ["k-hr", "reporting_hr_id", "/hierarchy/candidates", "HR_ADMIN"], ["k-mgr", "reporting_manager_id", "/hierarchy/candidates", "MANAGER"]].forEach(function (f) {
    var el = document.getElementById(f[0]);
    if (!el) return;
    API.get(f[2], f[3] ? { role: f[3] } : null).then(function (d) {
      el.innerHTML = el.options[0].outerHTML + RG.optionList(d.items || d, "id", f[3] ? "full_name" : "name");
    }).catch(function () {});
    el.addEventListener("change", function () { state[f[1]] = el.value; load(); });
  });
  load();
})();
