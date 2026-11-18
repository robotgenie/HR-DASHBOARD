/* uan.js - employee UAN submission and the HR verification queue. */
(function () {
  "use strict";
  var SCOPE = document.body.dataset.scope;

  /* ======================= employee ======================= */
  function employeeView() {
    var ctx = RG.boot({ scope: document.body.dataset.scope || "employee", active: "uan", title: "UAN", subtitle: "Universal Account Number" });
    if (!ctx) return;

    function render(uan) {
      var status = uan.status || "Not Submitted";
      var locked = status === "Verified" || status === "Submitted" || status === "Under Verification";
      ctx.page.innerHTML =
        '<div class="page-head"><div><h1>Universal Account Number</h1>' +
          '<p class="sub">Your 12-digit UAN links your provident fund across employers.</p></div></div>' +
        '<div class="grid grid-2">' +
          '<div class="card"><div class="card-head"><h3>Current record</h3>' + RG.badge(status) + "</div>" +
            '<div class="card-body"><dl class="kv" style="grid-template-columns:140px 1fr">' +
              "<dt>UAN</dt><dd class=\"num\">" + (uan.uan_number ? RG.esc(uan.uan_number) : "\u2014") + "</dd>" +
              "<dt>Status</dt><dd>" + RG.badge(status) + "</dd>" +
              "<dt>Submitted</dt><dd>" + RG.fmt.dateTime(uan.submitted_at) + "</dd>" +
              "<dt>Verified</dt><dd>" + RG.fmt.dateTime(uan.verified_at) + "</dd>" +
              "<dt>HR remarks</dt><dd>" + (uan.hr_remarks ? RG.esc(uan.hr_remarks) : "\u2014") + "</dd>" +
            "</dl>" +
            (status === "Verified"
              ? '<p class="small muted mt-4 mb-0">' + RG.icon("check", 13) + " Verified by HR. Contact HR if it needs changing.</p>"
              : status === "Rejected"
                ? '<p class="small mt-4 mb-0" style="color:var(--bad)">HR rejected this number. Correct it and submit again.</p>'
                : locked
                  ? '<p class="small muted mt-4 mb-0">Submitted \u2014 HR is reviewing it.</p>'
                  : "") +
            "</div></div>" +
          '<div class="card"><div class="card-head"><h3>' + (uan.uan_number ? "Update UAN" : "Submit your UAN") + "</h3></div>" +
            '<div class="card-body">' +
            (status === "Verified"
              ? RG.emptyState("Locked after verification", "Your UAN is verified, so it can only be changed by HR.", "", "shield")
              : '<form id="uan-form"><div class="field"><label for="uan_number">UAN number <span class="req">*</span></label>' +
                '<input id="uan_number" type="text" inputmode="numeric" maxlength="12" pattern="\\d{12}" ' +
                  'placeholder="12 digits" value="' + RG.esc(uan.uan_number || "") + '" required>' +
                '<span class="help">Exactly 12 digits, as printed on your PF passbook.</span>' +
                '<span class="err">Enter all 12 digits.</span></div>' +
                '<button class="btn btn-brand mt-4" type="submit">' +
                  (uan.uan_number ? "Submit updated UAN" : "Submit UAN") + "</button></form>") +
            "</div></div>" +
        "</div>";

      var form = document.getElementById("uan-form");
      if (!form) return;
      form.addEventListener("submit", function (event) {
        event.preventDefault();
        var input = document.getElementById("uan_number");
        var field = input.closest(".field");
        if (!/^\d{12}$/.test(input.value.trim())) { field.classList.add("invalid"); return; }
        field.classList.remove("invalid");
        var button = form.querySelector('button[type="submit"]');
        RG.setBusy(button, true, "Submitting\u2026");
        API.post("/uan", { uan_number: input.value.trim() }).then(function () {
          RG.toastOk("UAN submitted. HR will verify it.");
          load();
        }).catch(function (err) { RG.setBusy(button, false); RG.toastErr(err); });
      });
    }

    function load() {
      ctx.page.innerHTML = RG.skeletonCards(2);
      API.get("/uan/me").then(render).catch(function (err) {
        ctx.page.innerHTML = '<div class="card">' + RG.errorState(err.message, "retry") + "</div>";
        var r = document.getElementById("retry"); if (r) r.addEventListener("click", load);
      });
    }
    load();
  }

  /* ======================= HR ======================= */
  function hrView() {
    var ctx = RG.boot({ scope: "hr", active: "uan", title: "UAN", subtitle: "Verification queue" });
    if (!ctx) return;
    var TABS = ["All", "Submitted", "Under Verification", "Verified", "Rejected", "Not Submitted"];
    var state = { page: 1, page_size: 15, status: "Submitted", search: "", department_id: "" };

    ctx.page.innerHTML =
      '<div class="page-head"><div><h1>UAN records</h1>' +
        '<p class="sub">Check each number against the PF portal, then verify or reject it.</p></div></div>' +
      '<div class="card"><div class="tabs" id="tabs">' +
        TABS.map(function (t) {
          return '<button class="tab' + (t === state.status ? " active" : "") + '" data-tab="' + t + '">' + t + "</button>";
        }).join("") + "</div>" +
        '<div class="toolbar"><div class="search">' + RG.icon("search", 16) +
          '<input id="q" type="text" placeholder="Search employee name"></div>' +
          '<div class="filters"><select id="f-dept"><option value="">All departments</option></select></div></div>' +
        '<div id="host">' + RG.skeletonRows(8) + "</div>" +
        '<div class="pager" id="pager"></div></div>';

    var host = document.getElementById("host");
    API.get("/departments").then(function (rows) {
      document.getElementById("f-dept").innerHTML = '<option value="">All departments</option>' +
        RG.optionList(rows, "id", "name");
    }).catch(function () { /* keep all */ });

    function row(u) {
      var actions = "";
      if (u.status === "Submitted" || u.status === "Under Verification") {
        if (u.status === "Submitted") {
          actions += '<button class="btn btn-sm" data-checking="' + u.id + '">Mark under verification</button>';
        }
        actions += '<button class="btn btn-sm btn-ok" data-verify="' + u.id + '">Verify</button>';
        actions += '<button class="btn btn-sm btn-danger" data-reject="' + u.id + '">Reject</button>';
      }
      return "<tr>" +
        '<td data-label="Employee"><div class="identity">' +
          RG.avatar({ full_name: u.employee_name, id: u.employee_id }, "sm") +
          '<div><div class="name truncate">' + RG.esc(u.employee_name || "") + "</div>" +
          '<div class="meta">' + RG.esc(u.employee_code || "") + "</div></div></div></td>" +
        '<td data-label="Department">' + RG.esc(u.department || "\u2014") + "</td>" +
        '<td data-label="UAN" class="num">' + RG.esc(u.uan_number || "\u2014") + "</td>" +
        '<td data-label="Status">' + RG.badge(u.status) + "</td>" +
        '<td data-label="Submitted" class="nowrap">' + RG.fmt.date(u.submitted_at) + "</td>" +
        '<td data-label="Remarks" class="small muted">' + RG.esc(u.hr_remarks || "\u2014") + "</td>" +
        '<td class="actions" data-label="Actions">' + (actions || '<span class="small muted">\u2014</span>') + "</td></tr>";
    }

    function load() {
      API.get("/uan", state).then(function (data) {
        var items = data.items || [];
        if (!items.length) {
          host.innerHTML = RG.emptyState("Nothing here", "No UAN records match those filters.", "", "check");
          document.getElementById("pager").innerHTML = "";
          return;
        }
        host.innerHTML = '<div class="table-scroll"><table class="data"><thead><tr>' +
          "<th>Employee</th><th>Department</th><th>UAN</th><th>Status</th><th>Submitted</th><th>Remarks</th><th></th>" +
          "</tr></thead><tbody>" + items.map(row).join("") + "</tbody></table></div>";
        RG.hydratePhotos(host);
        RG.renderPager(document.getElementById("pager"), data.meta, function (p) { state.page = p; load(); });
      }).catch(function (err) {
        host.innerHTML = RG.errorState(err.message, "retry");
        var r = document.getElementById("retry"); if (r) r.addEventListener("click", load);
      });
    }

    function review(path, config) {
      var modal = RG.openModal({
        title: config.title, size: "sm",
        body: '<div class="field"><label for="remark">' + config.label +
          (config.required ? ' <span class="req">*</span>' : "") + "</label>" +
          '<textarea id="remark" rows="3" placeholder="' + RG.esc(config.placeholder || "") + '"></textarea></div>',
        footer: '<button class="btn" data-close>Cancel</button><button class="btn ' +
          (config.danger ? "btn-danger" : "btn-primary") + '" data-go>' + config.action + "</button>"
      });
      modal.foot.querySelector("[data-go]").addEventListener("click", function () {
        var text = modal.body.querySelector("#remark").value.trim();
        if (config.required && !text) { RG.toast("A reason is required.", "bad", "Add a remark"); return; }
        var button = modal.foot.querySelector("[data-go]");
        RG.setBusy(button, true, "Saving\u2026");
        API.post(path, { remarks: text || null }).then(function () {
          modal.close(); RG.toastOk(config.done); load();
        }).catch(function (err) { RG.setBusy(button, false); RG.toastErr(err); });
      });
    }

    document.getElementById("tabs").addEventListener("click", function (e) {
      var tab = e.target.closest("[data-tab]");
      if (!tab) return;
      document.querySelectorAll("#tabs .tab").forEach(function (t) { t.classList.remove("active"); });
      tab.classList.add("active");
      state.status = tab.dataset.tab === "All" ? "" : tab.dataset.tab;
      state.page = 1;
      load();
    });
    document.getElementById("q").addEventListener("input", RG.debounce(function (e) {
      state.search = e.target.value.trim(); state.page = 1; load();
    }));
    document.getElementById("f-dept").addEventListener("change", function (e) {
      state.department_id = e.target.value; state.page = 1; load();
    });

    RG.on(ctx.page, "[data-verify]", "click", function (e, b) {
      review("/uan/" + b.dataset.verify + "/verify", { title: "Verify UAN", label: "Remark (optional)",
        action: "Verify", done: "UAN verified." });
    });
    RG.on(ctx.page, "[data-reject]", "click", function (e, b) {
      review("/uan/" + b.dataset.reject + "/reject", { title: "Reject UAN", label: "Why is it being rejected?",
        required: true, danger: true, placeholder: "e.g. The number doesn't match EPFO records.",
        action: "Reject", done: "UAN rejected and the employee notified." });
    });
    RG.on(ctx.page, "[data-checking]", "click", function (e, b) {
      API.post("/uan/" + b.dataset.checking + "/under-verification", {})
        .then(function () { RG.toastOk("Marked as under verification."); load(); })
        .catch(RG.toastErr);
    });

    load();
  }

  if (RG.mgmtView()) hrView(); else employeeView();
})();
