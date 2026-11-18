/* documents.js - employee upload checklist and the HR verification queue.
   Note: no delete control exists for employees, and the backend rejects
   DELETE /api/documents/{id} for them regardless of what the UI shows. */
(function () {
  "use strict";
  var SCOPE = document.body.dataset.scope;

  /* ---------- shared: preview & version history ---------- */
  function previewDocument(documentId, title) {
    var modal = RG.openModal({
      title: title || "Document",
      size: "lg",
      body: '<div class="skeleton" style="height:50vh"></div>',
      footer: '<button class="btn" data-close>Close</button>' +
        '<button class="btn btn-primary" data-dl>' + RG.icon("download", 15) + " Download</button>"
    });
    modal.foot.querySelector("[data-dl]").addEventListener("click", function () {
      API.download("/documents/" + documentId + "/download").catch(RG.toastErr);
    });
    API.blob("/documents/" + documentId + "/download").then(function (file) {
      if (/^image\//.test(file.type)) {
        modal.body.innerHTML = '<img class="preview-img" src="' + file.url + '" alt="Document preview">';
      } else if (file.type === "application/pdf") {
        modal.body.innerHTML = '<iframe class="preview-frame" src="' + file.url + '" title="Document preview"></iframe>';
      } else {
        modal.body.innerHTML = RG.emptyState("Preview isn't available for this file type",
          RG.esc(file.filename) + " \u00B7 download it to open.", "", "doc");
      }
    }).catch(function (err) { modal.body.innerHTML = RG.errorState(err.message); });
  }

  function versionHistory(documentId, name) {
    var modal = RG.openModal({
      title: "History \u00B7 " + (name || "Document"),
      body: '<div class="skeleton sk-row"></div><div class="skeleton sk-row"></div>',
      footer: '<button class="btn" data-close>Close</button>'
    });
    API.get("/documents/" + documentId + "/versions").then(function (versions) {
      if (!versions.length) { modal.body.innerHTML = RG.emptyState("No versions yet", ""); return; }
      modal.body.innerHTML = '<p class="small muted">Every submission is kept. Nothing is overwritten or removed.</p>' +
        '<ul class="version-list">' + versions.map(function (v, index) {
          return "<li>" + '<span class="v-no' + (index === 0 ? " current" : "") + '">v' + v.version_no + "</span>" +
            '<div class="v-main"><b>' + RG.esc(v.original_filename || "file") + "</b>" +
              "<span>" + RG.fmt.dateTime(v.created_at) + " \u00B7 " + RG.fmt.bytes(v.file_size) +
              (v.reviewed_at ? " \u00B7 reviewed " + RG.fmt.date(v.reviewed_at) : "") + "</span>" +
              (v.hr_remarks ? '<span class="small" style="color:var(--bad)">' + RG.esc(v.hr_remarks) + "</span>" : "") +
            "</div>" + RG.badge(v.status) + "</li>";
        }).join("") + "</ul>";
    }).catch(function (err) { modal.body.innerHTML = RG.errorState(err.message); });
  }


  /* ======================= bank details (part of Documents) ======================= */
  var BANK_RULES = {
    bank_name: { re: /^[A-Za-z][A-Za-z0-9&().,' \-]{1,119}$/, label: "Bank Name", msg: "Enter a valid bank name." },
    account_number: { re: /^[0-9]{9,18}$/, label: "Bank Account Number", msg: "Account number must be 9 to 18 digits." },
    confirm_account_number: { label: "Confirm Bank Account Number" },
    ifsc_code: { re: /^[A-Z]{4}0[A-Z0-9]{6}$/, label: "IFSC Code", msg: "IFSC is 11 characters: 4 letters, 0, then 6 letters/digits (e.g. HDFC0001234)." },
    pan_number: { re: /^[A-Z]{5}[0-9]{4}[A-Z]$/, label: "PAN Card Number", msg: "PAN is 10 characters: 5 letters, 4 digits, 1 letter (e.g. ABCDE1234F)." }
  };
  function maskAccount(v) { v = String(v || "").replace(/\s/g, ""); return v ? "XXXX XXXX " + v.slice(-4) : "—"; }

  function bankKv(rows) {
    return '<dl class="kv bank-kv">' + rows.map(function (r) {
      return "<dt>" + RG.esc(r[0]) + "</dt><dd>" + RG.esc(r[1] || "—") + "</dd>";
    }).join("") + "</dl>";
  }

  function bankSection(host) {
    var current = null;
    var showForm = false;

    function field(name, type, extra) {
      var r = BANK_RULES[name];
      return '<div class="field" data-f="' + name + '"><label for="bk-' + name + '">' + r.label +
        ' <span class="req">*</span></label>' +
        '<input id="bk-' + name + '" name="' + name + '" type="' + type + '" autocomplete="off" required ' + (extra || "") + ">" +
        '<span class="err"></span></div>';
    }

    function formHtml() {
      return '<form id="bank-form" class="bank-form" novalidate>' +
        '<div class="form-grid">' +
          field("bank_name", "text", 'maxlength="120" placeholder="e.g. HDFC Bank"') +
          field("ifsc_code", "text", 'maxlength="11" placeholder="e.g. HDFC0001234" class="upper"') +
          field("account_number", "password", 'inputmode="numeric" maxlength="18" placeholder="9 to 18 digits"') +
          field("confirm_account_number", "text", 'inputmode="numeric" maxlength="18" placeholder="Re-enter the account number"') +
          field("pan_number", "text", 'maxlength="10" placeholder="e.g. ABCDE1234F" class="upper"') +
        "</div>" +
        '<div class="row wrap mt-4">' +
          '<button type="submit" class="btn btn-brand">Review details</button>' +
          (current && current.status !== "Not Submitted" ? '<button type="button" class="btn btn-ghost" data-bank-cancel>Cancel</button>' : "") +
        "</div></form>";
    }

    function values(form) {
      var v = {};
      Object.keys(BANK_RULES).forEach(function (k) {
        var raw = form.elements[k].value;
        v[k] = k === "bank_name" ? raw.replace(/\s+/g, " ").trim()
          : (k === "ifsc_code" || k === "pan_number") ? raw.trim().toUpperCase()
          : raw.replace(/[\s-]/g, "");
      });
      return v;
    }

    function validate(form) {
      var v = values(form), ok = true;
      Object.keys(BANK_RULES).forEach(function (k) {
        var r = BANK_RULES[k], box = form.querySelector('[data-f="' + k + '"]'), msg = "";
        if (!v[k]) msg = r.label + " is mandatory.";
        else if (r.re && !r.re.test(v[k])) msg = r.msg;
        else if (k === "confirm_account_number" && v[k] !== v.account_number) msg = "Account numbers do not match.";
        box.classList.toggle("invalid", !!msg);
        box.querySelector(".err").textContent = msg;
        if (msg) ok = false;
      });
      return ok ? v : null;
    }

    function confirmModal(v) {
      var modal = RG.openModal({
        title: "Confirm bank details", size: "sm",
        body: '<p class="small muted">Check every value carefully. Salary is paid into this account once HR approves it.</p>' +
          bankKv([["Bank Name", v.bank_name], ["Bank Account Number", maskAccount(v.account_number)],
                  ["IFSC Code", v.ifsc_code], ["PAN Card Number", v.pan_number]]) +
          '<label class="row bank-confirm mt-4"><input type="checkbox" id="bk-ok">' +
          "<span>I confirm that the bank details entered above are correct.</span></label>",
        footer: '<button class="btn" data-close>Edit</button>' +
          '<button class="btn btn-brand" data-submit disabled>Submit for Approval</button>'
      });
      var box = modal.body.querySelector("#bk-ok"), go = modal.foot.querySelector("[data-submit]");
      box.addEventListener("change", function () { go.disabled = !box.checked; });
      go.addEventListener("click", function () {
        if (!box.checked) return;
        RG.setBusy(go, true, "Submitting…");
        API.post("/bank-details/me", Object.assign({}, v, { confirmed: true })).then(function (res) {
          modal.close();
          RG.toastOk("Bank details submitted for approval.");
          showForm = false; render(res.state);
        }).catch(function (err) { RG.setBusy(go, false); RG.toastErr(err); });
      });
    }

    function render(data) {
      current = data;
      var st = data.status, a = data.approved, last = data.latest_request;
      var cls = st === "Approved" ? "is-verified" : st === "Pending Approval" ? "is-pending" : st === "Rejected" ? "is-rejected" : "is-missing";
      var formOpen = showForm || st === "Not Submitted" || st === "Rejected";
      var body = "";
      if (a) {
        body += '<div class="bank-block"><div class="small muted mb-2">Approved details (used on your salary slips)</div>' +
          bankKv([["Bank Name", a.bank_name], ["Bank Account Number", a.account_number_masked],
                  ["IFSC Code", a.ifsc_code], ["PAN Card Number", a.pan_number]]) +
          (!a.ifsc_code ? '<p class="small muted mt-2 mb-0">These details were recorded before IFSC codes were collected. Use \u201cChange bank details\u201d to add your IFSC code.</p>' : "") +
          "</div>";
      }
      if (st === "Pending Approval" && last) {
        body += '<div class="bank-block"><div class="small muted mb-2">Submitted ' + RG.fmt.date(last.submitted_at) +
          " — waiting for HR approval" + (a ? " (your approved details stay in use until then)" : "") + "</div>" +
          bankKv([["Bank Name", last.bank_name], ["Bank Account Number", last.account_number_masked],
                  ["IFSC Code", last.ifsc_code], ["PAN Card Number", last.pan_number]]) + "</div>";
      }
      if (st === "Rejected" && last) {
        body += '<div class="d-remark">' + RG.icon("alert", 13) + " Rejected" +
          (last.reviewed_by_name ? " by " + RG.esc(last.reviewed_by_name) : "") + ": " +
          RG.esc(last.review_remarks || "") + " Please correct the details below and submit again.</div>";
      }
      if (formOpen) body += formHtml();
      else body += '<div class="row wrap mt-4"><button class="btn" data-bank-edit>' +
        (st === "Pending Approval" ? "Correct submission" : "Change bank details") + "</button></div>";

      host.innerHTML = '<div class="card mb-4 bank-card ' + cls + '" id="bank-details">' +
        '<div class="card-head"><h3>' + RG.icon("shield", 15) + ' Bank Details <span class="badge bad plain mandatory-tag">MANDATORY</span></h3>' +
          RG.badge(st) + "</div>" +
        '<div class="card-body"><p class="small muted mt-0">All fields are mandatory. Your account number is never shown in full after you submit it.</p>' +
          body + "</div></div>";

      var form = host.querySelector("#bank-form");
      if (form) {
        if (st === "Rejected" && last) {
          form.elements.bank_name.value = last.bank_name || "";
          form.elements.ifsc_code.value = last.ifsc_code || "";
        }
        form.querySelectorAll(".upper").forEach(function (el) {
          el.addEventListener("input", function () { var p = el.selectionStart; el.value = el.value.toUpperCase(); el.setSelectionRange(p, p); });
        });
        /* After a first attempt, re-check while typing (not on blur: a blur
           that removes error text shifts the layout under the pointer). */
        form.querySelectorAll("input").forEach(function (el) {
          el.addEventListener("input", function () { if (form.dataset.tried) validate(form); });
        });
        ["paste", "drop"].forEach(function (evt) {
          form.elements.confirm_account_number.addEventListener(evt, function (e) { e.preventDefault(); });
        });
        form.addEventListener("submit", function (e) {
          e.preventDefault();
          form.dataset.tried = "1";
          var v = validate(form);
          if (!v) { RG.toast("Please fix the highlighted fields.", "bad", "Bank details incomplete"); return; }
          confirmModal(v);
        });
      }
    }

    RG.on(host, "[data-bank-edit]", "click", function () { showForm = true; render(current); });
    RG.on(host, "[data-bank-cancel]", "click", function () { showForm = false; render(current); });

    API.get("/bank-details/me").then(render).catch(function (err) {
      host.innerHTML = '<div class="card mb-4"><div class="card-body">' + RG.errorState(err.message) + "</div></div>";
    });
  }

  /* ======================= employee view ======================= */
  function employeeView() {
    var ctx = RG.boot({ scope: document.body.dataset.scope || "employee", active: "documents", title: "My Documents", subtitle: "Uploads & verification" });
    if (!ctx) return;

    function card(d) {
      var cls = d.status === "Verified" ? "is-verified"
        : d.status === "Pending" ? "is-pending"
        : (d.status === "Rejected" || d.status === "Re-upload Requested") ? "is-rejected" : "is-missing";
      var canUpload = d.status !== "Verified" && d.status !== "Pending";
      var glyph = d.status === "Verified" ? "check" : d.status === "Pending" ? "clipboard"
        : cls === "is-rejected" ? "alert" : "upload";
      return '<div class="doc-card ' + cls + '">' +
        '<span class="d-icon">' + RG.icon(glyph, 18) + "</span>" +
        '<div class="d-main"><b>' + RG.esc(d.document_type) +
            (d.is_required ? "" : ' <span class="muted small">(optional)</span>') + "</b>" +
          '<div class="d-meta">' +
            (d.uploaded_at ? "Uploaded " + RG.fmt.date(d.uploaded_at) + " \u00B7 version " + d.version_count
                           : "Not uploaded yet") +
            " \u00B7 " + d.allowed_extensions.join(", ") + " up to " + d.max_size_mb + " MB</div>" +
          (d.hr_remarks ? '<div class="d-remark">' + RG.icon("alert", 13) + " " + RG.esc(d.hr_remarks) + "</div>" : "") +
        "</div>" +
        '<div class="d-actions">' + RG.badge(d.status) +
          (d.document_id ? '<button class="btn btn-sm" data-view="' + d.document_id + '" data-name="' + RG.esc(d.document_type) + '">View</button>' : "") +
          (d.document_id && d.version_count > 1 ? '<button class="btn btn-sm btn-ghost" data-history="' + d.document_id + '" data-name="' + RG.esc(d.document_type) + '">History</button>' : "") +
          (canUpload ? '<button class="btn btn-sm btn-brand" data-upload="' + d.document_type_id +
            '" data-name="' + RG.esc(d.document_type) + '" data-ext="' + d.allowed_extensions.join(",") +
            '" data-max="' + d.max_size_mb + '">' + (d.document_id ? "Re-upload" : "Upload") + "</button>" : "") +
        "</div></div>";
    }

    function render(data) {
      var c = data.completion;
      ctx.page.innerHTML =
        '<div class="page-head"><div><h1>My documents</h1>' +
          '<p class="sub">Upload each required document once. HR reviews and verifies them.</p></div></div>' +
        '<div class="card mb-4"><div class="card-body"><div class="doc-summary">' +
          '<div class="ring" style="--pct:' + c.percent + '"><div><div class="pct">' + Math.round(c.percent) +
            '%</div><div class="cap">complete</div></div></div>' +
          '<div class="counts">' +
            "<div><b>" + c.label + "</b><span>Required uploaded</span></div>" +
            "<div><b>" + c.verified + "</b><span>Verified</span></div>" +
            "<div><b>" + c.pending + "</b><span>Awaiting review</span></div>" +
            "<div><b>" + c.rejected + "</b><span>Needs attention</span></div>" +
            "<div><b>" + c.missing + "</b><span>Still missing</span></div>" +
          "</div></div>" +
          '<p class="small muted mt-4 mb-0">' + RG.icon("shield", 13) +
            " Submitted documents can't be deleted \u2014 if something is wrong, upload a new version and the history is kept.</p>" +
        "</div></div>" +
        '<div id="bank-host"></div>' +
        '<div class="doc-list">' + data.items.map(card).join("") + "</div>";
      bankSection(document.getElementById("bank-host"));
    }

    function load() {
      ctx.page.innerHTML = RG.skeletonCards(3);
      API.get("/documents/me").then(render).catch(function (err) {
        ctx.page.innerHTML = '<div class="card">' + RG.errorState(err.message, "retry") + "</div>";
        var r = document.getElementById("retry"); if (r) r.addEventListener("click", load);
      });
    }

    function uploadModal(typeId, name, extensions, maxMb) {
      var modal = RG.openModal({
        title: "Upload \u00B7 " + name,
        size: "sm",
        body: '<div class="drop" id="drop"><div class="drop-icon">' + RG.icon("upload", 22) + "</div>" +
          "<b>Choose a file or drop it here</b><span>" + RG.esc(extensions) + " \u00B7 up to " + maxMb + " MB</span>" +
          '<input type="file" id="file" accept="' + extensions.split(",").map(function (x) { return "." + x.trim(); }).join(",") + '"></div>' +
          '<ul class="file-list" id="chosen"></ul>' +
          '<p class="small muted mt-4 mb-0">Once submitted this file stays on record. A later upload is saved as a new version.</p>',
        footer: '<button class="btn" data-close>Cancel</button>' +
          '<button class="btn btn-brand" data-send disabled>Upload</button>'
      });
      var drop = modal.body.querySelector("#drop");
      var input = modal.body.querySelector("#file");
      var send = modal.foot.querySelector("[data-send]");
      var chosen = modal.body.querySelector("#chosen");

      function pick(file) {
        if (!file) return;
        if (file.size > maxMb * 1024 * 1024) {
          RG.toast("That file is larger than " + maxMb + " MB.", "bad", "Too large");
          return;
        }
        chosen.innerHTML = '<li class="file-item"><span class="f-thumb">' +
          RG.esc((file.name.split(".").pop() || "").toUpperCase().slice(0, 4)) + "</span>" +
          '<div class="f-meta"><b class="truncate">' + RG.esc(file.name) + "</b><span>" + RG.fmt.bytes(file.size) +
          '</span><div class="bar thin hidden" id="prog"><span style="width:0"></span></div></div></li>';
        send.disabled = false;
      }
      drop.addEventListener("click", function () { input.click(); });
      input.addEventListener("change", function () { pick(input.files[0]); });
      ["dragenter", "dragover"].forEach(function (evt) {
        drop.addEventListener(evt, function (e) { e.preventDefault(); drop.classList.add("over"); });
      });
      ["dragleave", "drop"].forEach(function (evt) {
        drop.addEventListener(evt, function (e) { e.preventDefault(); drop.classList.remove("over"); });
      });
      drop.addEventListener("drop", function (e) {
        if (e.dataTransfer.files.length) { input.files = e.dataTransfer.files; pick(e.dataTransfer.files[0]); }
      });

      send.addEventListener("click", function () {
        var file = input.files[0];
        if (!file) return;
        var form = new FormData();
        form.append("document_type_id", typeId);
        form.append("file", file);
        RG.setBusy(send, true, "Uploading\u2026");
        var progress = modal.body.querySelector("#prog");
        if (progress) { progress.classList.remove("hidden"); progress.firstElementChild.style.width = "70%"; }
        API.upload("/documents/upload", form).then(function () {
          if (progress) progress.firstElementChild.style.width = "100%";
          modal.close();
          RG.toastOk(name + " uploaded. HR will review it.");
          load();
        }).catch(function (err) { RG.setBusy(send, false); RG.toastErr(err); });
      });
    }

    RG.on(document, "[data-upload]", "click", function (e, btn) {
      uploadModal(btn.dataset.upload, btn.dataset.name, btn.dataset.ext, btn.dataset.max);
    });
    RG.on(document, "[data-view]", "click", function (e, btn) { previewDocument(btn.dataset.view, btn.dataset.name); });
    RG.on(document, "[data-history]", "click", function (e, btn) { versionHistory(btn.dataset.history, btn.dataset.name); });
    load();
  }

  /* ======================= HR view ======================= */
  function hrView() {
    var ctx = RG.boot({ scope: "hr", active: "documents", title: "Documents", subtitle: "Verification queue" });
    if (!ctx) return;

    var TABS = ["All", "Pending", "Verified", "Rejected", "Re-upload Requested", "Missing"];
    var state = { page: 1, page_size: 15, status: "Pending", search: "", department_id: "" };
    var bankMode = false;
    var bankState = { page: 1, page_size: 15, status: "Pending Approval" };

    ctx.page.innerHTML =
      '<div class="page-head"><div><h1>Documents</h1><p class="sub">Verify, reject or ask for a clearer copy.</p></div>' +
        '<div class="page-actions"><button class="btn" data-types>Document requirements</button></div></div>' +
      '<div class="card"><div class="tabs" id="tabs">' +
        TABS.map(function (t) {
          return '<button class="tab' + (t === state.status ? " active" : "") + '" data-tab="' + t + '">' + t + "</button>";
        }).join("") +
        '<button class="tab" data-tab="__bank">Bank details <span class="chip hidden" id="bank-count"></span></button>' +
        "</div>" +
        '<div class="toolbar"><div class="search">' + RG.icon("search", 16) +
          '<input id="q" type="text" placeholder="Search employee or ID"></div>' +
          '<div class="filters"><select id="f-bank" class="hidden">' +
            '<option value="Pending Approval">Pending approval</option><option value="Approved">Approved</option>' +
            '<option value="Rejected">Rejected</option><option value="all">All</option></select>' +
          '<select id="f-dept"><option value="">All departments</option></select></div></div>' +
        '<div id="host">' + RG.skeletonRows(8) + "</div>" +
        '<div class="pager" id="pager"></div></div>';

    var host = document.getElementById("host");

    API.get("/departments").then(function (rows) {
      document.getElementById("f-dept").innerHTML = '<option value="">All departments</option>' +
        RG.optionList(rows, "id", "name");
    }).catch(function () { /* filter stays as all */ });

    function row(d) {
      var actions = "";
      if (d.status !== "Missing") {
        actions += '<button class="btn btn-sm" data-view="' + d.document_id + '" data-name="' + RG.esc(d.document_type) + '">View</button>';
        actions += '<button class="btn btn-sm btn-ghost" data-history="' + d.document_id + '" data-name="' + RG.esc(d.document_type) + '">History</button>';
      }
      if (d.status === "Pending" || d.status === "Re-upload Requested") {
        actions += '<button class="btn btn-sm btn-ok" data-verify="' + d.document_id + '">Verify</button>';
        actions += '<button class="btn btn-sm btn-danger" data-reject="' + d.document_id + '">Reject</button>';
      }
      if (d.status === "Verified") {
        actions += '<button class="btn btn-sm" data-reupload="' + d.document_id + '">Request re-upload</button>';
      }
      if (d.status === "Rejected") {
        actions += '<button class="btn btn-sm" data-reupload="' + d.document_id + '">Request re-upload</button>';
      }
      return "<tr>" +
        '<td data-label="Employee"><div class="identity">' + RG.avatar({ full_name: d.employee_name, id: d.employee_id }, "sm") +
          '<div><div class="name truncate">' + RG.esc(d.employee_name) + "</div>" +
          '<div class="meta">' + RG.esc(d.employee_code) + "</div></div></div></td>" +
        '<td data-label="Department">' + RG.esc(d.department || "\u2014") + "</td>" +
        '<td data-label="Document">' + RG.esc(d.document_type) +
          (d.version_count > 1 ? ' <span class="chip">v' + d.version_count + "</span>" : "") + "</td>" +
        '<td data-label="Status">' + RG.badge(d.status) + "</td>" +
        '<td data-label="Uploaded" class="nowrap">' + (d.uploaded_at ? RG.fmt.date(d.uploaded_at) : "\u2014") + "</td>" +
        '<td data-label="HR remarks" class="small muted">' + RG.esc(d.hr_remarks || "\u2014") + "</td>" +
        '<td class="actions" data-label="Actions">' + actions + "</td></tr>";
    }

    function bankRow(r) {
      return "<tr>" +
        '<td data-label="Employee"><div class="identity">' + RG.avatar({ full_name: r.employee_name, id: r.employee_id }, "sm") +
          '<div><div class="name truncate">' + RG.esc(r.employee_name) + "</div>" +
          '<div class="meta">' + RG.esc(r.employee_code || "") + (r.person_type ? " \u00B7 " + RG.esc(r.person_type) : "") + "</div></div></div></td>" +
        '<td data-label="Department">' + RG.esc(r.department || "\u2014") + "</td>" +
        '<td data-label="Bank">' + RG.esc(r.bank_name) + '<div class="meta small muted">' + RG.esc(r.ifsc_code) + "</div></td>" +
        '<td data-label="Account" class="nowrap">' + RG.esc(r.account_number_masked) + "</td>" +
        '<td data-label="Status">' + RG.badge(r.status) + (r.replaces_approved && r.status === "Pending Approval" ? ' <span class="chip">Change</span>' : "") + "</td>" +
        '<td data-label="Submitted" class="nowrap">' + RG.fmt.date(r.submitted_at) + "</td>" +
        '<td data-label="Remarks" class="small muted">' + RG.esc(r.review_remarks || "\u2014") + "</td>" +
        '<td class="actions" data-label="Actions"><button class="btn btn-sm' + (r.status === "Pending Approval" ? " btn-brand" : "") +
          '" data-bank-review="' + r.id + '">' + (r.status === "Pending Approval" ? "Review" : "View") + "</button></td></tr>";
    }

    function loadBank() {
      var params = Object.assign({}, bankState, { search: state.search, department_id: state.department_id });
      API.get("/bank-details", params).then(function (data) {
        if (!data.items.length) {
          host.innerHTML = RG.emptyState("Nothing here",
            bankState.status === "Pending Approval" ? "No bank details are waiting for approval." : "No bank details match those filters.",
            "", "check");
          document.getElementById("pager").innerHTML = "";
          return;
        }
        host.innerHTML = '<div class="table-scroll"><table class="data"><thead><tr>' +
          "<th>Employee</th><th>Department</th><th>Bank / IFSC</th><th>Account</th><th>Status</th><th>Submitted</th><th>Remarks</th><th></th>" +
          "</tr></thead><tbody>" + data.items.map(bankRow).join("") + "</tbody></table></div>";
        RG.hydratePhotos(host);
        RG.renderPager(document.getElementById("pager"), data.meta, function (p) { bankState.page = p; loadBank(); });
      }).catch(function (err) {
        host.innerHTML = RG.errorState(err.message, "retry");
        var r = document.getElementById("retry"); if (r) r.addEventListener("click", loadBank);
      });
    }

    function refreshBankCount() {
      API.get("/bank-details", { status: "Pending Approval", page_size: 1 }).then(function (d) {
        var chip = document.getElementById("bank-count");
        chip.textContent = d.meta.total;
        chip.classList.toggle("hidden", !d.meta.total);
      }).catch(function () { /* count is optional */ });
    }

    function bankReview(id) {
      var modal = RG.openModal({ title: "Bank details", size: "sm", body: RG.skeletonRows(4),
        footer: '<button class="btn" data-close>Close</button>' });
      API.get("/bank-details/" + id).then(function (r) {
        var pending = r.status === "Pending Approval";
        modal.body.innerHTML =
          '<div class="row between mb-2"><b>' + RG.esc(r.employee_name) + '</b>' + RG.badge(r.status) + "</div>" +
          '<div class="small muted mb-2">' + RG.esc(r.employee_code || "") + " \u00B7 submitted " + RG.fmt.date(r.submitted_at) +
            " \u00B7 confirmed by the employee</div>" +
          '<dl class="kv bank-kv">' +
            "<dt>Bank Name</dt><dd>" + RG.esc(r.bank_name) + "</dd>" +
            '<dt>Bank Account Number</dt><dd><span id="acct">' + RG.esc(r.account_number_masked) + "</span> " +
              '<button class="btn btn-sm btn-ghost" id="reveal" type="button">Show</button></dd>' +
            "<dt>IFSC Code</dt><dd>" + RG.esc(r.ifsc_code) + "</dd>" +
            "<dt>PAN Card Number</dt><dd>" + RG.esc(r.pan_number) + "</dd></dl>" +
          (r.approved && pending ? '<p class="small muted mt-4 mb-0">Currently approved: ' + RG.esc(r.approved.bank_name) + " \u00B7 " +
            RG.esc(r.approved.account_number_masked) + ". It stays in use until you approve this change.</p>" : "") +
          (r.review_remarks ? '<p class="small mt-4 mb-0"><b>Remarks:</b> ' + RG.esc(r.review_remarks) + "</p>" : "") +
          (pending ? '<div class="field mt-4"><label for="bk-remark">Remarks <span class="muted">(required to reject)</span></label>' +
            '<textarea id="bk-remark" rows="2" placeholder="e.g. The account number does not match the cancelled cheque."></textarea></div>' : "");
        var shown = false;
        modal.body.querySelector("#reveal").addEventListener("click", function (e) {
          shown = !shown;
          modal.body.querySelector("#acct").textContent = shown ? r.account_number : r.account_number_masked;
          e.target.textContent = shown ? "Hide" : "Show";
        });
        if (pending) {
          modal.foot.innerHTML = '<button class="btn" data-close>Close</button>' +
            '<button class="btn btn-danger" data-bk="reject">Reject</button>' +
            '<button class="btn btn-ok" data-bk="approve">Approve</button>';
          modal.foot.querySelectorAll("[data-bk]").forEach(function (btn) {
            btn.addEventListener("click", function () {
              var action = btn.dataset.bk, remark = modal.body.querySelector("#bk-remark").value.trim();
              if (action === "reject" && !remark) {
                RG.toast("Add a reason so the employee knows what to correct.", "bad", "Reason required"); return;
              }
              RG.setBusy(btn, true, "Saving\u2026");
              API.post("/bank-details/" + id + "/" + action, { remarks: remark || null }).then(function () {
                modal.close();
                RG.toastOk(action === "approve" ? "Bank details approved. Salary slips will use them." : "Bank details rejected and the employee notified.");
                loadBank(); refreshBankCount();
              }).catch(function (err) { RG.setBusy(btn, false); RG.toastErr(err); });
            });
          });
        }
      }).catch(function (err) { modal.body.innerHTML = RG.errorState(err.message); });
    }

    function load() {
      if (bankMode) { loadBank(); return; }
      API.get("/documents", state).then(function (data) {
        if (!data.items.length) {
          host.innerHTML = RG.emptyState("Nothing in this queue",
            state.status === "Pending" ? "Every submitted document has been reviewed." : "No documents match those filters.",
            "", "check");
          document.getElementById("pager").innerHTML = "";
          return;
        }
        host.innerHTML = '<div class="table-scroll"><table class="data"><thead><tr>' +
          "<th>Employee</th><th>Department</th><th>Document</th><th>Status</th><th>Uploaded</th><th>HR remarks</th><th></th>" +
          "</tr></thead><tbody>" + data.items.map(row).join("") + "</tbody></table></div>";
        RG.hydratePhotos(host);
        RG.renderPager(document.getElementById("pager"), data.meta, function (p) { state.page = p; load(); });
      }).catch(function (err) {
        host.innerHTML = RG.errorState(err.message, "retry");
        var r = document.getElementById("retry"); if (r) r.addEventListener("click", load);
      });
    }

    function remarkModal(config) {
      var modal = RG.openModal({
        title: config.title, size: "sm",
        body: '<div class="field"><label for="remark">' + config.label +
          (config.required ? ' <span class="req">*</span>' : "") + "</label>" +
          '<textarea id="remark" rows="3" placeholder="' + RG.esc(config.placeholder || "") + '"></textarea>' +
          '<span class="help">The employee sees this, and it is emailed to them.</span></div>',
        footer: '<button class="btn" data-close>Cancel</button>' +
          '<button class="btn ' + (config.danger ? "btn-danger" : "btn-primary") + '" data-go>' + config.action + "</button>"
      });
      modal.foot.querySelector("[data-go]").addEventListener("click", function () {
        var text = modal.body.querySelector("#remark").value.trim();
        if (config.required && !text) { RG.toast("A remark is required so the employee knows what to fix.", "bad", "Add a remark"); return; }
        var button = modal.foot.querySelector("[data-go]");
        RG.setBusy(button, true, "Saving\u2026");
        API.post(config.path, { remarks: text || null }).then(function () {
          modal.close(); RG.toastOk(config.done); load();
        }).catch(function (err) { RG.setBusy(button, false); RG.toastErr(err); });
      });
    }

    document.getElementById("tabs").addEventListener("click", function (e) {
      var tab = e.target.closest("[data-tab]");
      if (!tab) return;
      document.querySelectorAll("#tabs .tab").forEach(function (t) { t.classList.remove("active"); });
      tab.classList.add("active");
      bankMode = tab.dataset.tab === "__bank";
      document.getElementById("f-bank").classList.toggle("hidden", !bankMode);
      if (!bankMode) state.status = tab.dataset.tab === "All" ? "" : tab.dataset.tab;
      state.page = 1; bankState.page = 1;
      load();
    });
    document.getElementById("q").addEventListener("input", RG.debounce(function (e) {
      state.search = e.target.value.trim(); state.page = 1; bankState.page = 1; load();
    }));
    document.getElementById("f-bank").addEventListener("change", function (e) {
      bankState.status = e.target.value; bankState.page = 1; load();
    });
    RG.on(ctx.page, "[data-bank-review]", "click", function (e, b) { bankReview(b.dataset.bankReview); });
    document.getElementById("f-dept").addEventListener("change", function (e) {
      state.department_id = e.target.value; state.page = 1; bankState.page = 1; load();
    });

    RG.on(ctx.page, "[data-view]", "click", function (e, b) { previewDocument(b.dataset.view, b.dataset.name); });
    RG.on(ctx.page, "[data-history]", "click", function (e, b) { versionHistory(b.dataset.history, b.dataset.name); });
    RG.on(ctx.page, "[data-verify]", "click", function (e, b) {
      remarkModal({ title: "Verify document", label: "Remark (optional)", action: "Verify",
        path: "/documents/" + b.dataset.verify + "/verify", done: "Document verified." });
    });
    RG.on(ctx.page, "[data-reject]", "click", function (e, b) {
      remarkModal({ title: "Reject document", label: "Why is it being rejected?", required: true, danger: true,
        placeholder: "e.g. The PAN card image is blurred \u2014 please upload a clearer copy.",
        action: "Reject", path: "/documents/" + b.dataset.reject + "/reject", done: "Document rejected and the employee notified." });
    });
    RG.on(ctx.page, "[data-reupload]", "click", function (e, b) {
      remarkModal({ title: "Request a re-upload", label: "What should they send?", required: true,
        action: "Request re-upload", path: "/documents/" + b.dataset.reupload + "/request-reupload",
        done: "Re-upload requested." });
    });

    RG.on(ctx.page, "[data-types]", "click", function () {
      var modal = RG.openModal({
        title: "Document requirements", size: "lg",
        body: RG.skeletonRows(5),
        footer: '<button class="btn" data-close>Close</button>'
      });
      API.get("/documents/types").then(function (types) {
        modal.body.innerHTML = '<p class="small muted">Requirements are configurable \u2014 switch one off and it stops counting towards completion.</p>' +
          '<table class="data compact"><thead><tr><th>Document</th><th>Code</th><th>Required</th><th>Allowed</th><th>Max</th><th>Active</th></tr></thead><tbody>' +
          types.map(function (t) {
            return "<tr><td>" + RG.esc(t.name) + "</td><td class=\"small muted\">" + RG.esc(t.code) + "</td>" +
              "<td>" + (t.is_required ? '<span class="badge ok">Required</span>' : '<span class="badge">Optional</span>') + "</td>" +
              '<td class="small">' + RG.esc(t.allowed_extensions) + "</td><td>" + t.max_size_mb + " MB</td>" +
              "<td>" + (t.is_active ? '<span class="badge ok">On</span>' : '<span class="badge bad">Off</span>') + "</td></tr>";
          }).join("") + "</tbody></table>";
      }).catch(function (err) { modal.body.innerHTML = RG.errorState(err.message); });
    });

    refreshBankCount();
    if (location.hash === "#bank") {
      var bankTab = document.querySelector('#tabs [data-tab="__bank"]');
      if (bankTab) { bankTab.click(); return; }
    }
    load();
  }

  if (RG.mgmtView()) hrView(); else employeeView();
})();
