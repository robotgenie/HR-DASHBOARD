/* excel.js - Excel import (template -> upload -> preview -> errors -> confirm)
   and hierarchy-scoped exports.
   Admin: everything. HR: import/export inside their own hierarchy.
   Manager (exports.html): team exports only, never salary.
   The database stays the source of truth: nothing is written until "Confirm",
   and only rows that pass validation again at that moment are applied. */
(function () {
  "use strict";
  var exportOnly = document.body.dataset.page === "exports";
  var ctx = RG.boot({ scope: document.body.dataset.scope, active: "excel", title: exportOnly ? "Team Export" : "Excel Import / Export", subtitle: "Spreadsheets" });
  if (!ctx) return;
  var SCOPE = ctx.scope;
  var state = { tab: exportOnly ? "export" : (RG.param("export") ? "export" : "import"), preview: null, file: null };

  ctx.page.innerHTML =
    '<div class="page-head"><div><h1>' + (exportOnly ? "Team Export" : "Excel Import / Export") + "</h1>" +
      '<p class="sub">' + (exportOnly
        ? "Download your team's attendance, leave, reports, hourly updates, tasks and monthly figures as Excel."
        : SCOPE === "admin" ? "Create or update HR, managers, employees and interns in bulk, and export any organisation data."
        : "Create or update people in your hierarchy in bulk, and export the data you manage.") + "</p></div></div>" +
    '<div class="card">' + (exportOnly ? "" : '<div class="tabs" role="tablist"><button class="tab" data-xtab="import">Import</button><button class="tab" data-xtab="export">Export</button><button class="tab" data-xtab="history">Import history</button></div>') +
    '<div class="card-body" id="x-host"></div></div>';
  var host = document.getElementById("x-host");

  function show() {
    ctx.page.querySelectorAll("[data-xtab]").forEach(function (b) { b.classList.toggle("active", b.dataset.xtab === state.tab); });
    if (state.tab === "import") importView();
    else if (state.tab === "history") historyView();
    else exportView();
  }

  /* ------------------------------------------------------------- import */
  function steps(active) {
    var names = ["Template", "Upload", "Validation & preview", "Confirm", "Done"];
    return '<ol class="import-steps">' + names.map(function (n, i) { return '<li class="' + (i <= active ? "on" : "") + '">' + (i + 1) + ". " + n + "</li>"; }).join("") + "</ol>";
  }

  function importView() {
    host.innerHTML = steps(1) +
      '<div class="grid grid-2 mb-4">' +
        '<div><h4>1. Download the template</h4><p class="small muted">The template lists your departments, internship backgrounds, ' +
          (SCOPE === "admin" ? "HRs and managers" : "yourself and your managers") + " as dropdowns on the Reference sheet, plus instructions.</p>" +
          '<button class="btn" data-template>' + RG.icon("download", 16) + " Download template</button></div>" +
        '<div><h4>2. Choose what the file does</h4><div class="field"><select id="x-mode">' +
          '<option value="auto">Create new people and update existing ones (by Employee ID)</option>' +
          '<option value="create">Create new people only (existing IDs are rejected)</option>' +
          '<option value="update">Update existing people only (bulk update)</option></select>' +
          '<span class="help">Blank cells never overwrite existing values.</span></div></div>' +
      "</div>" +
      '<label class="drop-zone" id="x-drop" for="x-file">' + RG.icon("upload", 24) + '<div><b>Drop the .xlsx file here or click to choose</b></div>' +
        '<p>Max 5 MB, up to 2000 rows. The file is validated, not imported, until you confirm.</p>' +
        '<input type="file" id="x-file" accept=".xlsx" class="sr-only"></label>' +
      '<div id="x-preview" class="mt-4"></div>';
    var drop = document.getElementById("x-drop"), input = document.getElementById("x-file");
    ["dragenter", "dragover"].forEach(function (ev) { drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.add("over"); }); });
    ["dragleave", "drop"].forEach(function (ev) { drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.remove("over"); }); });
    drop.addEventListener("drop", function (e) { if (e.dataTransfer.files[0]) upload(e.dataTransfer.files[0]); });
    input.addEventListener("change", function () { if (input.files[0]) upload(input.files[0]); });
  }

  function upload(file) {
    var out = document.getElementById("x-preview");
    if (!/\.xlsx$/i.test(file.name)) { RG.toastErr({ message: "Choose an .xlsx file." }); return; }
    out.innerHTML = '<div class="card">' + RG.skeletonRows(4) + "</div>";
    var fd = new FormData();
    fd.append("file", file);
    fd.append("mode", document.getElementById("x-mode").value);
    API.upload("/excel/import/preview", fd).then(function (p) { state.preview = p; renderPreview(p); })
      .catch(function (err) { out.innerHTML = '<div class="card">' + RG.errorState(err.message) + "</div>"; });
  }

  function countStrip(c) {
    return '<div class="today-strip">' + [
      ["Total rows", c.total_rows, ""], ["Valid rows", c.valid_rows, "ok"], ["Invalid rows", c.invalid_rows, c.invalid_rows ? "bad" : ""],
      ["New people", c.create_rows, ""], ["Updates", c.update_rows, ""], ["Unchanged", c.unchanged_rows, ""],
      ["Duplicates", c.duplicate_rows, c.duplicate_rows ? "warn" : ""], ["Missing fields", c.missing_fields, c.missing_fields ? "warn" : ""],
      ["Invalid departments", c.invalid_departments, c.invalid_departments ? "warn" : ""],
      ["Invalid designations", c.invalid_designations, c.invalid_designations ? "warn" : ""],
      ["Invalid managers", c.invalid_reporting_managers, c.invalid_reporting_managers ? "warn" : ""],
      ["Invalid HRs", c.invalid_reporting_hrs, c.invalid_reporting_hrs ? "warn" : ""],
      ["Hierarchy errors", c.hierarchy_errors, c.hierarchy_errors ? "bad" : ""],
      ["Reporting-line changes", c.hierarchy_changes, c.hierarchy_changes ? "warn" : ""]
    ].map(function (x) { return '<div class="ts ' + x[2] + '"><span>' + x[0] + "</span><b>" + (x[1] || 0) + "</b></div>"; }).join("") + "</div>";
  }

  function renderPreview(p) {
    var out = document.getElementById("x-preview");
    var c = p.counts;
    var invalidOnly = state.invalidOnly;
    var rows = p.rows.filter(function (r) { return !invalidOnly || r.errors.length; });
    var hier = p.rows.some(function (r) { return !r.errors.length && r.hierarchy_change; });
    out.innerHTML = steps(p.status === "Confirmed" ? 4 : 2) +
      '<div class="row wrap mb-3" style="justify-content:space-between"><div><b>' + RG.esc(p.file_name) + "</b> " + RG.badge(p.status === "Confirmed" ? "Completed" : "Previewed") +
        '<div class="small muted">Mode: ' + RG.esc(p.mode) + "</div></div>" +
        '<div class="row wrap">' + (c.invalid_rows || (p.result_counts && p.result_counts.failed) ? '<button class="btn" data-errors>' + RG.icon("download", 16) + " Error report (.xlsx)</button>" : "") +
          '<label class="row" style="gap:6px"><input type="checkbox" id="x-invalid"' + (invalidOnly ? " checked" : "") + "> Show invalid rows only</label></div></div>" +
      countStrip(c) +
      '<div class="table-scroll"><table class="data"><thead><tr><th>Row</th><th>Action</th><th>Person</th><th>Type</th><th>Department</th><th>Reporting</th><th>Result</th></tr></thead><tbody>' +
      rows.map(function (r) {
        var cls = r.errors.length ? "row-invalid" : (r.action === "update" && r.changes.length ? "row-update" : "");
        return '<tr class="' + cls + '"><td data-label="Row">' + r.row + "</td>" +
          '<td data-label="Action">' + RG.badge(r.action === "create" ? "New" : "Update") + "</td>" +
          '<td data-label="Person"><b>' + RG.esc(r.full_name || "—") + '</b><div class="small muted">' + RG.esc(r.employee_code || "new ID") + (r.email ? " · " + RG.esc(r.email) : "") + "</div></td>" +
          '<td data-label="Type">' + RG.esc(r.person_type || "—") + "</td>" +
          '<td data-label="Department">' + RG.esc(r.department || "—") + "</td>" +
          '<td data-label="Reporting" class="small">' + (r.reporting_manager ? "Manager: " + RG.esc(r.reporting_manager) + "<br>" : "") + (r.reporting_hr ? "HR: " + RG.esc(r.reporting_hr) : "") + "</td>" +
          '<td data-label="Result">' + (r.errors.length
            ? RG.badge("Invalid") + '<ul class="row-errors">' + r.errors.map(function (e) {
                return "<li><b>" + RG.esc(e.field) + ":</b> " + RG.esc(e.message) + (e.suggestion ? ' <span class="muted">— ' + RG.esc(e.suggestion) + "</span>" : "") + "</li>";
              }).join("") + "</ul>"
            : (r.changes.length
                ? RG.badge("Valid") + '<ul class="row-changes">' + r.changes.map(function (ch) {
                    return '<li class="' + (ch.hierarchy ? "hier" : "") + '">' + RG.esc(ch.field) + ': <span class="old">' + RG.esc(ch.old == null ? "—" : ch.old) +
                      '</span> → <span class="new">' + RG.esc(ch.new) + "</span>" + (ch.hierarchy ? " (reporting line)" : "") + "</li>";
                  }).join("") + "</ul>"
                : RG.badge(r.action === "update" ? "No change" : "Valid"))) + "</td></tr>";
      }).join("") + "</tbody></table></div>" +
      (p.status === "Previewed"
        ? '<div class="card mt-4"><div class="card-body">' +
            (hier ? '<label class="row mb-2" style="gap:8px;align-items:flex-start"><input type="checkbox" id="x-hier"> <span><b>I have reviewed the reporting-line changes</b> (old → new Reporting HR / Manager / Type shown above in amber).</span></label>' : "") +
            '<label class="row mb-3" style="gap:8px"><input type="checkbox" id="x-mail"> Email new people their login details</label>' +
            '<div class="row wrap"><button class="btn btn-brand" data-confirm' + (c.valid_rows ? "" : " disabled") + ">Import " + c.valid_rows + " valid row(s)</button>" +
            '<span class="small muted">' + (c.invalid_rows ? c.invalid_rows + " invalid row(s) will be skipped and stay in the error report." : "All rows are valid.") + "</span></div></div></div>"
        : "") +
      '<div id="x-result"></div>';
    var inv = document.getElementById("x-invalid");
    inv.addEventListener("change", function () { state.invalidOnly = inv.checked; renderPreview(p); });
    var err = out.querySelector("[data-errors]");
    if (err) err.addEventListener("click", function () { API.download("/excel/import/" + p.token + "/errors", "import_errors.xlsx").catch(RG.toastErr); });
    var go = out.querySelector("[data-confirm]");
    if (go) go.addEventListener("click", function () {
      var hierBox = document.getElementById("x-hier");
      if (hierBox && !hierBox.checked) { RG.toastErr({ message: "Tick the box to confirm the reporting-line changes." }); return; }
      RG.setBusy(go, true, "Importing…");
      API.post("/excel/import/" + p.token + "/confirm", {
        confirm_hierarchy_changes: !!(hierBox && hierBox.checked),
        send_account_emails: document.getElementById("x-mail").checked
      }).then(function (res) {
        state.preview = res.preview;
        renderPreview(res.preview);
        showResult(res);
        RG.toastOk(res.created + " created, " + res.updated + " updated, " + res.failed + " failed.");
      }).catch(function (e) { RG.setBusy(go, false); RG.toastErr(e); });
    });
  }

  function showResult(res) {
    var host2 = document.getElementById("x-result");
    host2.innerHTML = '<div class="card mt-4"><div class="card-head"><h3>Import finished</h3></div><div class="card-body">' +
      '<div class="today-strip"><div class="ts ok"><span>Created</span><b>' + res.created + '</b></div><div class="ts"><span>Updated</span><b>' + res.updated +
      '</b></div><div class="ts' + (res.failed ? " bad" : "") + '"><span>Failed</span><b>' + res.failed + '</b></div><div class="ts"><span>Unchanged</span><b>' + res.unchanged + "</b></div></div>" +
      (res.apply_errors.length ? '<ul class="row-errors">' + res.apply_errors.map(function (e) { return "<li>Row " + e.row + ": " + RG.esc(e.message) + "</li>"; }).join("") + "</ul>" : "") +
      (res.credentials.length ? '<h4 class="mt-4">Temporary passwords (shown once)</h4><p class="small muted">Share these privately. Everyone must change the password at first sign-in.</p>' +
        '<div class="table-scroll"><table class="data compact cred-table"><thead><tr><th>Row</th><th>Employee ID</th><th>Name</th><th>Email</th><th>Temporary password</th></tr></thead><tbody>' +
        res.credentials.map(function (c) {
          return "<tr><td>" + c.row + "</td><td>" + RG.esc(c.employee_code) + "</td><td>" + RG.esc(c.full_name) + "</td><td>" + RG.esc(c.email) + "</td><td><code>" + RG.esc(c.initial_password) + "</code></td></tr>";
        }).join("") + "</tbody></table></div>" : "") +
      '<div class="row wrap mt-3"><a class="btn" href="' + (SCOPE === "admin" ? "organization.html" : "hierarchy.html") + '">View hierarchy</a><button class="btn" data-again>Import another file</button></div>' +
      "</div></div>";
    host2.querySelector("[data-again]").addEventListener("click", function () { state.preview = null; importView(); });
  }

  function historyView() {
    host.innerHTML = RG.skeletonRows(4);
    API.get("/audit-logs", { action: "excel_import_confirmed", page_size: 50 }).then(function (d) {
      var items = d.items || [];
      host.innerHTML = items.length ? '<div class="table-scroll"><table class="data"><thead><tr><th>When</th><th>By</th><th>File</th><th>Rows</th><th>Created</th><th>Updated</th><th>Failed</th></tr></thead><tbody>' +
        items.map(function (l) {
          var m = l.meta || {};
          return "<tr><td>" + RG.fmt.dateTime(l.created_at) + "</td><td>" + RG.esc(l.actor_email || "") + "</td><td>" + RG.esc(m.file_name || "") + "</td><td>" + (m.rows || 0) +
            "</td><td>" + (m.created || 0) + "</td><td>" + (m.updated || 0) + "</td><td>" + (m.failed || 0) + "</td></tr>";
        }).join("") + "</tbody></table></div>" : RG.emptyState("No imports yet", "Confirmed imports are listed here from the audit log.", "", "upload");
    }).catch(function (err) { host.innerHTML = RG.errorState(err.message); });
  }

  /* ------------------------------------------------------------- export */
  function exportView() {
    host.innerHTML = RG.skeletonRows(3);
    Promise.all([
      API.get("/excel/export/types"),
      API.get("/departments").catch(function () { return []; }),
      SCOPE === "admin" ? API.get("/hierarchy/candidates", { role: "HR_ADMIN" }).catch(function () { return { items: [] }; }) : Promise.resolve({ items: [] }),
      SCOPE !== "manager" ? API.get("/hierarchy/candidates", { role: "MANAGER" }).catch(function () { return { items: [] }; }) : Promise.resolve({ items: [] })
    ]).then(function (res) {
      var types = res[0].items, scopeName = { organisation: "the whole organisation", hierarchy: "your hierarchy", team: "your team", own: "your own records" }[res[0].scope];
      var wanted = RG.param("export");
      var now = new Date();
      var month = now.getFullYear() + "-" + String(now.getMonth() + 1).padStart(2, "0");
      host.innerHTML = (exportOnly ? "" : steps(-1).replace(/class="on"/g, "")) +
        '<p class="small muted">Exports contain ' + RG.esc(scopeName) + " only. Every export is recorded in the audit log.</p>" +
        '<h4>What to export</h4><div class="export-grid mb-4">' + types.map(function (t, i) {
          return '<label class="opt"><input type="radio" name="xtype" value="' + t.value + '"' + ((wanted ? wanted === t.value : i === 0) ? " checked" : "") + "><span><b>" + RG.esc(t.label) + "</b></span></label>";
        }).join("") + "</div>" +
        '<h4>Filters</h4><div class="form-grid">' +
          (SCOPE !== "manager" ? '<div class="field"><label for="f-dept">Department</label><select id="f-dept"><option value="">All</option>' + RG.optionList(res[1], "id", "name") + "</select></div>" : "") +
          (SCOPE === "admin" ? '<div class="field"><label for="f-hr">HR</label><select id="f-hr"><option value="">All</option>' + RG.optionList(res[2].items, "id", "full_name") + "</select></div>" : "") +
          (SCOPE !== "manager" ? '<div class="field"><label for="f-mgr">Manager</label><select id="f-mgr"><option value="">All</option>' + RG.optionList(res[3].items, "id", "full_name") + "</select></div>" : "") +
          '<div class="field"><label for="f-ptype">Employee type</label><select id="f-ptype"><option value="">All</option>' +
            (SCOPE === "admin" ? "<option>HR</option>" : "") + (SCOPE !== "manager" ? "<option>Manager</option>" : "") + "<option>Employee</option><option>Intern</option></select></div>" +
          '<div class="field"><label for="f-estatus">Employee status</label><select id="f-estatus"><option value="">All</option><option>Active</option><option>Inactive</option><option>On Leave</option><option>Resigned</option><option>Terminated</option></select></div>' +
          '<div class="field"><label for="f-month">Month</label><input id="f-month" type="month" value="' + month + '"><span class="help">Used by monthly reports and salary; overrides the date range.</span></div>' +
          '<div class="field"><label for="f-from">From date</label><input id="f-from" type="date"></div>' +
          '<div class="field"><label for="f-to">To date</label><input id="f-to" type="date"></div>' +
          '<div class="field"><label for="f-rtype">Report type</label><select id="f-rtype"><option value="">Noon &amp; EOD</option><option value="Noon">Noon</option><option value="EOD">EOD</option></select></div>' +
          '<div class="field"><label for="f-status">Status</label><input id="f-status" list="f-status-list" placeholder="e.g. Pending, Approved, Completed"><datalist id="f-status-list">' +
            ["Pending", "Approved", "Rejected", "Submitted", "Reviewed", "Draft", "In Progress", "Completed", "Cancelled", "Verified", "Credited", "Processing"].map(function (s) { return "<option>" + s + "</option>"; }).join("") + "</datalist>" +
            '<span class="help">Leave, report, task, document or salary status.</span></div>' +
          '<div class="field"><label for="f-ltype">Leave type</label><select id="f-ltype"><option value="">All</option><option>Casual Leave</option><option>Sick Leave</option><option>Earned Leave</option><option>Unpaid Leave</option><option value="Other">Other Leave</option><option>Half Day Leave</option></select></div>' +
        "</div>" +
        '<div class="row wrap mt-4"><button class="btn btn-brand" data-export>' + RG.icon("download", 16) + " Download Excel</button>" +
          '<span class="small muted">Filters that don\'t apply to the chosen export are ignored.</span></div>';
      var pre = RG.param("person_type");
      if (pre && document.getElementById("f-ptype")) document.getElementById("f-ptype").value = pre;
      host.querySelector("[data-export]").addEventListener("click", function () {
        var btn = this, v = function (idn) { var el = document.getElementById(idn); return el ? el.value : ""; };
        var type = (host.querySelector("input[name=xtype]:checked") || {}).value;
        var monthVal = v("f-month");
        var useMonth = type === "monthly" || type === "salary" || (!v("f-from") && !v("f-to") && ["attendance", "leave", "reports", "hourly", "tasks"].indexOf(type) >= 0);
        var q = { type: type, department_id: v("f-dept"), reporting_hr_id: v("f-hr"), reporting_manager_id: v("f-mgr"),
                  person_type: v("f-ptype"), employment_status: v("f-estatus"), date_from: v("f-from"), date_to: v("f-to"),
                  month: useMonth ? monthVal : "", report_type: v("f-rtype"), status: v("f-status"), leave_type: v("f-ltype") };
        var parts = Object.keys(q).filter(function (k) { return q[k]; }).map(function (k) { return encodeURIComponent(k) + "=" + encodeURIComponent(q[k]); });
        RG.setBusy(btn, true, "Preparing…");
        API.download("/excel/export?" + parts.join("&"), type + ".xlsx")
          .then(function () { RG.setBusy(btn, false); RG.toastOk("Export downloaded."); })
          .catch(function (err) { RG.setBusy(btn, false); RG.toastErr(err); });
      });
    }).catch(function (err) { host.innerHTML = RG.errorState(err.message); });
  }

  RG.on(ctx.page, "[data-xtab]", "click", function (e, b) { state.tab = b.dataset.xtab; show(); });
  RG.on(ctx.page, "[data-template]", "click", function (e, b) {
    RG.setBusy(b, true, "Preparing…");
    API.download("/excel/template", "employee_import_template.xlsx").then(function () { RG.setBusy(b, false); })
      .catch(function (err) { RG.setBusy(b, false); RG.toastErr(err); });
  });
  show();
})();
