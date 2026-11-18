/* org.js - the reporting hierarchy: Admin -> HR -> Manager -> Employee / Intern.
   admin/organization.html : whole organisation; change anyone's role and line.
   hr/hierarchy.html       : the HR's own branch; place managers / employees under
                             yourself and assign employees to your managers.
   manager/team.html       : the Manager's team with today's status.
   Every change goes through PUT /hierarchy/employees/{id}; the API validates
   the hierarchy and refuses anything outside the user's authority. */
(function () {
  "use strict";
  var page = document.body.dataset.page;
  var isTeam = page === "team";
  var ctx = RG.boot({
    scope: document.body.dataset.scope, active: isTeam ? "team" : "organization",
    title: isTeam ? "My Team" : "Organization & Hierarchy", subtitle: "Reporting lines"
  });
  if (!ctx) return;
  var SCOPE = ctx.scope;
  var me = API.session.user() || {};
  var personLink = SCOPE === "hr" ? "employee-details.html?id=" : "person.html?id=";

  if (isTeam) { teamPage(); return; }

  var state = { q: "", tree: [] };
  ctx.page.innerHTML =
    '<div class="page-head"><div><h1>' + (SCOPE === "admin" ? "Organization &amp; Hierarchy" : "My Hierarchy") + "</h1>" +
      '<p class="sub">' + (SCOPE === "admin"
        ? "Admin → HR → Manager → Employees / Interns. Change roles and reporting lines here; every module follows this structure."
        : "The managers, employees and interns assigned to you. Place people under yourself and assign employees to your managers.") + "</p></div>" +
      '<div class="page-actions"><a class="btn" href="excel.html">' + RG.icon("upload", 16) + " Bulk update via Excel</a></div></div>" +
    (SCOPE === "admin" ? '<div class="card mb-4"><div class="card-body row wrap" style="justify-content:space-between;gap:12px">' +
      '<div><b>People without a Reporting HR</b><div class="small muted">When on, every HR can see (and claim) employees and managers that have no Reporting HR yet. Turn off for strict HR-only hierarchies.</div></div>' +
      '<label class="row" style="gap:8px"><input type="checkbox" id="pool"> Visible to all HR</label></div></div>' : "") +
    '<div class="card mb-4"><div class="toolbar"><div class="filters" style="margin-left:0"><input type="search" id="o-q" placeholder="Find a person"></div></div></div>' +
    '<div id="o-host">' + RG.skeletonCards(2) + "</div>";
  var host = document.getElementById("o-host");

  function tagClass(t) { return { Intern: "intern", Manager: "manager", HR: "hr" }[t] || ""; }
  function hit(p) { return !state.q || (p.full_name + " " + (p.employee_code || "")).toLowerCase().indexOf(state.q) >= 0; }
  function person(p) {
    return '<li class="org-person">' + RG.avatar(p, "sm") + '<a class="nm" href="' + personLink + p.id + '">' + RG.esc(p.full_name) + "</a>" +
      '<span class="tag ' + tagClass(p.type) + '">' + RG.esc(p.type) + "</span>" +
      (p.is_active ? "" : '<span class="tag">Inactive</span>') +
      '<button class="icon-link" title="Change reporting line" data-move="' + p.id + '">' + RG.icon("gear", 15) + "</button></li>";
  }

  function render() {
    var tree = state.tree;
    if (!tree.length) {
      host.innerHTML = '<div class="card">' + RG.emptyState("No hierarchy yet", SCOPE === "admin" ? "Create HR accounts, then managers under them." : "Nobody is assigned to you yet.", "", "users") + "</div>";
      return;
    }
    host.innerHTML = '<div class="org-tree">' + tree.map(function (hr) {
      var mgrs = (hr.managers || []).map(function (m) {
        var team = (m.team || []).filter(hit);
        if (state.q && !hit(m) && !team.length) return "";
        return '<div class="org-mgr"><div class="head">' + RG.avatar(m, "sm") +
          '<div class="who"><a href="' + personLink + m.id + '"><b>' + RG.esc(m.full_name) + "</b></a>" +
          '<div class="small muted">Manager · ' + RG.esc(m.designation || "") + " · " + (m.team || []).length + " in team</div></div>" +
          '<button class="icon-link" title="Change reporting line" data-move="' + m.id + '">' + RG.icon("gear", 15) + "</button></div>" +
          "<ul>" + (team.map(person).join("") || '<li class="small muted">No team members</li>') + "</ul></div>";
      }).join("");
      var direct = (hr.direct || []).filter(hit);
      if (state.q && !mgrs && !direct.length && !(hr.id && hit(hr))) return "";
      var unassigned = !hr.id;
      return '<section class="org-hr' + (unassigned ? " unassigned" : "") + '"><header>' +
        (unassigned ? RG.icon("alert", 20) : RG.avatar(hr, "sm")) +
        '<div class="who">' + (unassigned ? "<b>Not assigned to an HR</b><span class=\"small muted\">Pick a Reporting HR for these people.</span>"
          : '<b><a href="' + (SCOPE === "admin" ? "hr-monitoring.html?id=" : personLink) + hr.id + '">' + RG.esc(hr.full_name) + "</a></b>" +
            '<span class="small muted">HR · ' + RG.esc(hr.designation || "") + " · " + RG.esc(hr.department || "") + "</span>") + "</div>" +
        '<div class="stats"><span>' + (hr.managers || []).length + " managers</span><span>" +
          ((hr.managers || []).reduce(function (n, m) { return n + (m.team || []).length; }, 0) + (hr.direct || []).length) + " employees &amp; interns</span></div>" +
        (!unassigned && SCOPE === "admin" ? '<button class="icon-link" title="Change role" data-move="' + hr.id + '">' + RG.icon("gear", 15) + "</button>" : "") +
        "</header>" +
        (mgrs ? '<div class="org-mgrs">' + mgrs + "</div>" : "") +
        (direct.length ? '<div class="org-direct"><h4>' + (unassigned ? "Employees &amp; interns" : "Reporting directly to HR") + "</h4><ul class=\"org-mgr\" style=\"list-style:none\">" + direct.map(person).join("") + "</ul></div>" : "") +
        (!mgrs && !direct.length ? '<div class="card-body small muted">No managers or employees yet.</div>' : "") +
        "</section>";
    }).join("") + "</div>";
    RG.hydratePhotos(host);
  }

  function load() {
    return API.get("/hierarchy/tree").then(function (d) { state.tree = d.items || []; render(); })
      .catch(function (err) { host.innerHTML = '<div class="card">' + RG.errorState(err.message) + "</div>"; });
  }

  function moveModal(id) {
    Promise.all([
      API.get("/employees/" + id),
      API.get("/hierarchy/candidates", { role: "HR_ADMIN" }),
      API.get("/hierarchy/candidates", { role: "MANAGER" })
    ]).then(function (res) {
      var e = res[0], hrs = res[1].items, mgrs = res[2].items;
      var roles = SCOPE === "admin" ? [["HR_ADMIN", "HR"], ["MANAGER", "Manager"], ["EMPLOYEE", e.is_intern ? "Intern" : "Employee"]]
                                    : [["MANAGER", "Manager"], ["EMPLOYEE", e.is_intern ? "Intern" : "Employee"]];
      var m = RG.openModal({
        title: "Reporting line · " + e.full_name, size: "md",
        body: '<form class="form-grid" novalidate>' +
          '<div class="field full"><label for="mv-role">Role</label><select id="mv-role">' + roles.map(function (r) {
            return '<option value="' + r[0] + '"' + (r[0] === e.role ? " selected" : "") + ">" + r[1] + "</option>"; }).join("") + "</select>" +
            '<span class="help">HR reports to the Admin, a Manager to an HR, employees and interns to a Manager (or directly to an HR).</span></div>' +
          '<div class="field full" data-hr-wrap><label for="mv-hr">Reporting HR</label><select id="mv-hr"><option value="">— None —</option>' +
            RG.optionList(hrs, "id", "full_name", e.reporting_hr_id) + "</select></div>" +
          '<div class="field full" data-mgr-wrap><label for="mv-mgr">Reporting manager</label><select id="mv-mgr"></select>' +
            '<span class="help">Choosing a manager also sets the HR to that manager\'s HR.</span></div>' +
          '<div class="full">' + window.RGPerson.chainHtml(e.reporting_chain) + "</div>" +
          "</form>",
        footer: '<button class="btn" data-close>Cancel</button><button class="btn btn-brand" data-save>Save</button>'
      });
      var b = m.body, roleEl = b.querySelector("#mv-role"), hrEl = b.querySelector("#mv-hr"), mgrEl = b.querySelector("#mv-mgr");
      function sync() {
        var role = roleEl.value;
        b.querySelector("[data-hr-wrap]").style.display = role === "HR_ADMIN" ? "none" : "";
        b.querySelector("[data-mgr-wrap]").style.display = role === "EMPLOYEE" ? "" : "none";
        var hrId = hrEl.value;
        var options = mgrs.filter(function (x) { return x.id !== e.id && (!hrId || String(x.reporting_hr_id) === hrId); });
        var current = mgrEl.value || e.reporting_manager_id;
        mgrEl.innerHTML = '<option value="">— Reports directly to the HR —</option>' + options.map(function (x) {
          return '<option value="' + x.id + '"' + (String(current) === String(x.id) ? " selected" : "") + ">" + RG.esc(x.full_name) +
            (x.reporting_hr ? " (HR: " + RG.esc(x.reporting_hr) + ")" : " (no HR)") + "</option>";
        }).join("");
      }
      roleEl.addEventListener("change", sync);
      hrEl.addEventListener("change", function () { mgrEl.value = ""; sync(); });
      sync();
      m.foot.querySelector("[data-save]").addEventListener("click", function () {
        var btn = this, role = roleEl.value, body = { role: role };
        if (role === "HR_ADMIN") { body.reporting_hr_id = null; body.reporting_manager_id = null; }
        else if (role === "MANAGER") { body.reporting_hr_id = hrEl.value ? Number(hrEl.value) : null; body.reporting_manager_id = null; }
        else {
          body.reporting_manager_id = mgrEl.value ? Number(mgrEl.value) : null;
          if (!body.reporting_manager_id) body.reporting_hr_id = hrEl.value ? Number(hrEl.value) : null;
        }
        if (role === e.role) delete body.role;
        RG.setBusy(btn, true, "Saving…");
        API.put("/hierarchy/employees/" + e.id, body).then(function (r) {
          m.close();
          RG.toastOk(Object.keys(r.changes || {}).length ? "Reporting line updated." : "Nothing changed.");
          load();
        }).catch(function (err) { RG.setBusy(btn, false); RG.toastErr(err); });
      });
    }).catch(RG.toastErr);
  }

  RG.on(ctx.page, "[data-move]", "click", function (e, b) { e.preventDefault(); moveModal(b.dataset.move); });
  document.getElementById("o-q").addEventListener("input", RG.debounce(function (e) { state.q = e.target.value.trim().toLowerCase(); render(); }, 200));
  var pool = document.getElementById("pool");
  if (pool) {
    API.get("/settings").then(function (s) { pool.checked = !!s.values.hr_sees_unassigned; }).catch(function () {});
    pool.addEventListener("change", function () {
      API.put("/settings", { values: { hr_sees_unassigned: pool.checked } })
        .then(function () { RG.toastOk(pool.checked ? "Unassigned people are visible to every HR." : "Unassigned people are visible to the Admin only."); })
        .catch(function (err) { pool.checked = !pool.checked; RG.toastErr(err); });
    });
  }
  load();

  /* ---------------- manager: my team ---------------- */
  function teamPage() {
    ctx.page.innerHTML = '<div class="page-head"><div><h1>My Team</h1><p class="sub">The employees and interns reporting to you. Open anyone to see attendance, reports, tasks and leave.</p></div>' +
      '<div class="page-actions"><a class="btn" href="team-tasks.html">' + RG.icon("target", 16) + " Assign tasks</a></div></div>" +
      '<div class="card mb-4"><div class="card-body" id="t-line"></div></div>' +
      '<div class="card"><div id="t-host">' + RG.skeletonRows(5) + "</div></div>";
    Promise.all([API.get("/hierarchy/me"), API.get("/attendance/hr/today")]).then(function (res) {
      var line = res[0], today = {};
      (res[1].items || []).forEach(function (r) { today[r.employee_id] = r; });
      document.getElementById("t-line").innerHTML = "<b>Your reporting line</b><div class=\"mt-2\">" + window.RGPerson.chainHtml(line.chain) + "</div>";
      var team = line.direct_reports || [];
      var host = document.getElementById("t-host");
      if (!team.length) { host.innerHTML = RG.emptyState("No team members yet", "HR or the Admin assigns employees and interns to you.", "", "users"); return; }
      host.innerHTML = '<div class="table-scroll"><table class="data"><thead><tr><th>Name</th><th>Department</th><th>Today</th><th>Noon</th><th>EOD</th><th>Hourly</th><th>Open tasks</th><th></th></tr></thead><tbody>' +
        team.map(function (p) {
          var t = today[p.id] || {}, s = t.session;
          return '<tr><td data-label="Name"><div class="identity">' + RG.avatar(p, "sm") + '<div><a class="name" href="person.html?id=' + p.id + '">' + RG.esc(p.full_name) + "</a>" +
            '<div class="meta">' + RG.esc(p.role_label || "") + " · " + RG.esc(p.designation || "") + "</div></div></div></td>" +
            '<td data-label="Department">' + RG.esc(p.department || "—") + "</td>" +
            '<td data-label="Today">' + (s ? "<b>" + RG.fmt.time(s.check_in_time) + "</b>" + (s.check_out_time ? " – " + RG.fmt.time(s.check_out_time) : "") +
              (s.late_minutes ? '<div class="small text-bad">' + RG.esc(s.late_label) + " late</div>" : "") : (t.leave_status ? RG.badge(t.leave_status) : RG.badge("Not Logged In"))) + "</td>" +
            '<td data-label="Noon">' + RG.badge(t.noon_report || "—") + "</td><td data-label=\"EOD\">" + RG.badge(t.eod_report || "—") + "</td>" +
            '<td data-label="Hourly">' + (t.hourly_submitted != null ? t.hourly_submitted + "/" + t.hourly_applicable : "—") + "</td>" +
            '<td data-label="Open tasks">' + ((t.tasks || []).filter(function (x) { return x.status === "Pending" || x.status === "In Progress"; }).length) + "</td>" +
            '<td class="actions"><a class="btn btn-sm" href="person.html?id=' + p.id + '">Open</a></td></tr>';
        }).join("") + "</tbody></table></div>";
      RG.hydratePhotos(host);
    }).catch(function (err) { document.getElementById("t-host").innerHTML = RG.errorState(err.message); });
  }
})();
