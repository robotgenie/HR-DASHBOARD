/* settings.js - HR configuration (company, departments, backgrounds, documents,
   email, daily-report rule) and the employee's own preferences.
   SMTP credentials are never returned by the API, so they are never rendered. */
(function () {
  "use strict";
  var SCOPE = document.body.dataset.scope;

  /* ======================= HR ======================= */
  function hrView() {
    var ctx = RG.boot({ scope: "hr", active: "settings", title: "Settings", subtitle: "Company configuration" });
    if (!ctx) return;
    var current = null;

    function switchRow(key, title, note, value) {
      return '<label class="switch" style="padding:10px 0;border-bottom:1px solid var(--line)">' +
        '<input type="checkbox" data-setting="' + key + '"' + (value ? " checked" : "") + ">" +
        '<span class="track"></span><span class="switch-text"><b>' + title + "</b><span>" + note + "</span></span></label>";
    }

    function render(data) {
      current = data;
      var v = data.values;
      ctx.page.innerHTML =
        '<div class="page-head"><div><h1>Settings</h1>' +
          '<p class="sub">Company details, the lists that drive the app, and notification rules.</p></div>' +
          '<div class="page-actions"><a class="btn" href="../change-password.html">Change my password</a>' +
          '<button class="btn btn-brand" data-save>Save changes</button></div></div>' +
        '<div class="grid grid-2">' +
          '<div class="card"><div class="card-head"><h3>Company information</h3></div><div class="card-body">' +
            '<div class="field mb-4"><label for="c-name">Company name</label>' +
              '<input id="c-name" type="text" value="' + RG.esc(v.company_name || "") + '"></div>' +
            '<div class="field"><label for="c-addr">Registered address</label>' +
              '<textarea id="c-addr" rows="3">' + RG.esc(v.company_address || "") + "</textarea>" +
              '<span class="help">Printed on every generated payslip.</span></div>' +
            '<div class="field mt-4"><label for="c-loc">Default work location</label>' +
              '<input id="c-loc" type="text" maxlength="120" placeholder="e.g. New Delhi" value="' + RG.esc(v.default_work_location || "") + '">' +
              '<span class="help">Printed as \u201cLocation\u201d on salary slips of employees who have no work location of their own.</span></div>' +
          "</div></div>" +
          '<div class="card"><div class="card-head"><h3>Rules &amp; notifications</h3></div><div class="card-body">' +
            switchRow("daily_report_mandatory", "Daily report required before logout",
              "Employees can't complete logout until today's report is submitted.", v.daily_report_mandatory) +
            switchRow("notify_on_salary_credit", "Notify on salary credit",
              "Dashboard notification plus email when a salary is marked credited.", v.notify_on_salary_credit) +
            switchRow("notify_on_document_review", "Notify on document review",
              "Tells the employee when a document is verified or rejected.", v.notify_on_document_review) +
            switchRow("payslip_auto_generate", "Generate payslips automatically",
              "Builds the PDF when salary is credited, if none was uploaded.", v.payslip_auto_generate) +
            switchRow("salary_auto_generate", "Create monthly salary slips automatically",
              "Each month every employee's salary record is created from their previous month; you then edit only the payment amounts.", v.salary_auto_generate !== false) +
            switchRow("email_enabled", "Send email",
              "Turn off to keep notifications in-app only. Emails are still logged.", v.email_enabled) +
            (document.body.dataset.scope === "admin" ? switchRow("hr_sees_unassigned", "HR can see unassigned people",
              "Employees and managers without a Reporting HR are visible to every HR until you assign them. Admin only.", v.hr_sees_unassigned) : "") +
          "</div></div>" +
          '<div class="card"><div class="card-head"><h3>Email delivery</h3>' +
            (data.email.smtp_configured ? RG.badge("Verified") : RG.badge("Pending")) + "</div>" +
            '<div class="card-body"><dl class="kv" style="grid-template-columns:120px 1fr">' +
              "<dt>SMTP host</dt><dd>" + RG.esc(data.email.smtp_host || "not configured") + "</dd>" +
              "<dt>From name</dt><dd>" + RG.esc(data.email.from_name) + "</dd>" +
              "<dt>From email</dt><dd>" + RG.esc(data.email.from_email) + "</dd>" +
            "</dl>" +
            '<p class="small muted mt-4 mb-0">' +
              (data.email.smtp_configured
                ? "Mail is being delivered through the configured SMTP relay."
                : "Without SMTP, every email is written to the server log and the email log so workflows stay testable.") +
              " Credentials live in the server environment and are never shown here.</p></div></div>" +
          '<div class="card"><div class="card-head"><h3>Uploads</h3></div><div class="card-body">' +
            '<dl class="kv" style="grid-template-columns:120px 1fr">' +
              "<dt>Max file size</dt><dd>" + data.uploads.max_file_size_mb + " MB</dd>" +
              "<dt>Allowed types</dt><dd>" + RG.esc(data.uploads.allowed_extensions.join(", ")) + "</dd>" +
            "</dl>" +
            '<p class="small muted mt-2 mb-0">Uploaded files are served only through authorised endpoints \u2014 never as public URLs.</p>' +
          "</div></div>" +
          '<div class="card"><div class="card-head"><h3>Departments</h3>' +
            '<button class="btn btn-sm" data-add-dept>' + RG.icon("plus", 14) + " Add</button></div>" +
            '<div id="dept-host">' + RG.skeletonRows(4) + "</div></div>" +
          '<div class="card"><div class="card-head"><h3>Internship backgrounds</h3>' +
            '<button class="btn btn-sm" data-add-bg>' + RG.icon("plus", 14) + " Add</button></div>" +
            '<div id="bg-host">' + RG.skeletonRows(4) + "</div></div>" +
        "</div>";
      loadLists();
    }

    function loadLists() {
      API.get("/departments").then(function (rows) {
        document.getElementById("dept-host").innerHTML = '<div class="table-scroll"><table class="data compact">' +
          "<thead><tr><th>Name</th><th>Code</th><th>People</th><th>Status</th><th></th></tr></thead><tbody>" +
          rows.map(function (d) {
            return "<tr><td>" + RG.esc(d.name) + '</td><td class="small muted">' + RG.esc(d.code) + "</td>" +
              '<td class="num">' + (d.employee_count || 0) + "</td>" +
              "<td>" + (d.is_active ? RG.badge("Active") : RG.badge("Inactive")) + "</td>" +
              '<td class="actions"><button class="btn btn-sm" data-edit-dept=\'' +
                RG.esc(JSON.stringify({ id: d.id, name: d.name, code: d.code, is_active: d.is_active })) +
                "'>Edit</button></td></tr>";
          }).join("") + "</tbody></table></div>";
      }).catch(function (err) { document.getElementById("dept-host").innerHTML = RG.errorState(err.message); });

      API.get("/internship-backgrounds").then(function (rows) {
        document.getElementById("bg-host").innerHTML = '<div class="table-scroll"><table class="data compact">' +
          "<thead><tr><th>Background</th><th>Status</th><th></th></tr></thead><tbody>" +
          rows.map(function (b) {
            return "<tr><td>" + RG.esc(b.name) + "</td>" +
              "<td>" + (b.is_active ? RG.badge("Active") : RG.badge("Inactive")) + "</td>" +
              '<td class="actions"><button class="btn btn-sm" data-edit-bg=\'' +
                RG.esc(JSON.stringify({ id: b.id, name: b.name, is_active: b.is_active })) +
                "'>Edit</button></td></tr>";
          }).join("") + "</tbody></table></div>";
      }).catch(function (err) { document.getElementById("bg-host").innerHTML = RG.errorState(err.message); });
    }

    function listModal(config) {
      var item = config.item || {};
      var modal = RG.openModal({
        title: config.title, size: "sm",
        body: '<div class="field mb-4"><label for="l-name">Name <span class="req">*</span></label>' +
            '<input id="l-name" type="text" value="' + RG.esc(item.name || "") + '" required></div>' +
          (config.withCode
            ? '<div class="field mb-4"><label for="l-code">Short code <span class="req">*</span></label>' +
              '<input id="l-code" type="text" maxlength="20" value="' + RG.esc(item.code || "") + '" required></div>'
            : "") +
          '<label class="switch"><input type="checkbox" id="l-active"' +
            (item.id === undefined || item.is_active ? " checked" : "") + '><span class="track"></span>' +
            '<span class="switch-text"><b>Active</b><span>Inactive entries stop appearing in dropdowns.</span></span></label>',
        footer: '<button class="btn" data-close>Cancel</button><button class="btn btn-primary" data-go>Save</button>'
      });
      modal.foot.querySelector("[data-go]").addEventListener("click", function () {
        var payload = {
          name: modal.body.querySelector("#l-name").value.trim(),
          is_active: modal.body.querySelector("#l-active").checked
        };
        if (config.withCode) payload.code = modal.body.querySelector("#l-code").value.trim().toUpperCase();
        if (!payload.name || (config.withCode && !payload.code)) {
          RG.toast("Fill in the required fields.", "bad", "Missing details"); return;
        }
        var button = modal.foot.querySelector("[data-go]");
        RG.setBusy(button, true, "Saving\u2026");
        (item.id ? API.put(config.path + "/" + item.id, payload) : API.post(config.path, payload))
          .then(function () { modal.close(); RG.toastOk("Saved."); loadLists(); })
          .catch(function (err) { RG.setBusy(button, false); RG.toastErr(err); });
      });
    }

    RG.on(ctx.page, "[data-save]", "click", function (e, btn) {
      var values = {
        company_name: document.getElementById("c-name").value.trim(),
        company_address: document.getElementById("c-addr").value.trim(),
        default_work_location: document.getElementById("c-loc").value.trim()
      };
      document.querySelectorAll("[data-setting]").forEach(function (input) {
        values[input.dataset.setting] = input.checked;
      });
      RG.setBusy(btn, true, "Saving\u2026");
      API.put("/settings", { values: values }).then(function () {
        RG.setBusy(btn, false);
        RG.toastOk("Settings saved.");
      }).catch(function (err) { RG.setBusy(btn, false); RG.toastErr(err); });
    });
    RG.on(ctx.page, "[data-add-dept]", "click", function () {
      listModal({ title: "Add department", path: "/departments", withCode: true });
    });
    RG.on(ctx.page, "[data-edit-dept]", "click", function (e, btn) {
      listModal({ title: "Edit department", path: "/departments", withCode: true,
        item: JSON.parse(btn.dataset.editDept) });
    });
    RG.on(ctx.page, "[data-add-bg]", "click", function () {
      listModal({ title: "Add internship background", path: "/internship-backgrounds" });
    });
    RG.on(ctx.page, "[data-edit-bg]", "click", function (e, btn) {
      listModal({ title: "Edit internship background", path: "/internship-backgrounds",
        item: JSON.parse(btn.dataset.editBg) });
    });

    ctx.page.innerHTML = RG.skeletonCards(2);
    API.get("/settings").then(render).catch(function (err) {
      ctx.page.innerHTML = '<div class="card">' + RG.errorState(err.message) + "</div>";
    });
  }

  /* ======================= employee ======================= */
  function employeeView() {
    var ctx = RG.boot({ scope: document.body.dataset.scope || "employee", active: "settings", title: "Settings", subtitle: "Your account" });
    if (!ctx) return;

    API.get("/employees/me").then(function (me) {
      ctx.page.innerHTML =
        '<div class="page-head"><div><h1>Settings</h1>' +
          '<p class="sub">Your account and the details you control.</p></div></div>' +
        '<div class="grid grid-2">' +
          '<div class="card"><div class="card-head"><h3>Account</h3></div><div class="card-body">' +
            '<dl class="kv" style="grid-template-columns:130px 1fr">' +
              "<dt>Name</dt><dd>" + RG.esc(me.full_name) + "</dd>" +
              "<dt>Employee ID</dt><dd>" + RG.esc(me.employee_code) + "</dd>" +
              "<dt>Work email</dt><dd>" + RG.esc(me.email) + "</dd>" +
              "<dt>Department</dt><dd>" + RG.esc(me.department || "\u2014") + "</dd>" +
              "<dt>Designation</dt><dd>" + RG.esc(me.designation || "\u2014") + "</dd>" +
            "</dl>" +
            '<p class="small muted mt-4">Name, department, designation and email are maintained by HR.</p>' +
            '<a class="btn btn-primary" href="../change-password.html">Change password</a>' +
          "</div></div>" +
          '<div class="card"><div class="card-head"><h3>What you can edit</h3></div><div class="card-body">' +
            '<p class="small muted">Phone, address and emergency contact are yours to keep current.</p>' +
            '<a class="btn" href="profile.html">Open my profile</a>' +
            '<div class="divider"></div>' +
            "<h4 style=\"font-size:13px\">Notifications</h4>" +
            '<p class="small muted mb-0">Salary, document, UAN and meeting notifications are always on so you don\u2019t miss ' +
              "a payslip or a verification. Read them in the notification centre.</p>" +
            '<a class="btn btn-sm mt-4" href="notifications.html">Notification centre</a>' +
          "</div></div>" +
        "</div>";
    }).catch(function (err) {
      ctx.page.innerHTML = '<div class="card">' + RG.errorState(err.message) + "</div>";
    });
  }

  if (RG.mgmtView()) hrView(); else employeeView();
})();
