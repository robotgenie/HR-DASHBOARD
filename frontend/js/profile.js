/* profile.js - the employee's own profile.

   Three things the backend also enforces, mirrored here:
   - identity fields (name, phone, email, DOB, gender) lock once the profile is
     complete; changing one needs an HR-approved change request
   - the final Employee ID/ID card is issued only after HR/Admin approval
     once every mandatory field and the photograph are complete
   - only phone (while unlocked), address and emergency contact are self-editable
*/
(function () {
  "use strict";
  var SCOPE = document.body.dataset.scope || "employee";
  var IS_HR = SCOPE === "hr";
  var ID_LABEL = IS_HR ? "HR ID" : "Employee ID";
  var CARD_LABEL = IS_HR ? "HR Identity Card" : "Employee Identity Card";;
  var ctx = RG.boot({ scope: SCOPE, active: "profile", title: "My Profile", subtitle: "Personal & employment" });
  if (!ctx) return;

  var me = null;
  var lock = null;
  var requests = [];

  function kv(label, value) {
    return "<dt>" + label + "</dt><dd>" + (value === null || value === undefined || value === "" ? "\u2014" : value) + "</dd>";
  }

  function lockIcon() {
    return '<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" ' +
      'stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="11" width="16" height="9" rx="2"/>' +
      '<path d="M8 11V8a4 4 0 0 1 8 0v3"/></svg>';
  }

  /* ------------------------------------------------------------ ID card */

  function cardHtml(card) {
    var fields =
      '<div class="idcard-fields">' +
        "<div><dt>Department</dt><dd>" + RG.esc(card.department || "\u2014") + "</dd></div>" +
        "<div><dt>Date of joining</dt><dd>" + RG.fmt.date(card.joining_date) + "</dd></div>" +
        "<div><dt>Email</dt><dd>" + RG.esc(card.email || "\u2014") + "</dd></div>" +
        "<div><dt>Phone</dt><dd>" + RG.esc(card.phone || "\u2014") + "</dd></div>" +
      "</div>";

    var photo = card.photo_path
      ? '<img alt="" data-photo="' + card.employee_id + '">'
      : RG.esc(RG.fmt.initials(card.full_name));

    return '<div class="idcard">' +
        '<div class="idcard-band">' +
          '<img alt="" src="../assets/logo/rocket-genie-logo.png">' +
          "<div><b>" + RG.esc(card.company_name || "Rocket Genie") + "</b>" +
          "<span>" + CARD_LABEL + "</span></div>" +
        "</div>" +
        '<div class="idcard-body">' +
          '<div class="idcard-photo">' + photo + "</div>" +
          '<div class="idcard-who"><h4>' + RG.esc(card.full_name) + "</h4>" +
            '<p class="role">' + RG.esc(card.designation || "") + "</p>" +
            '<span class="idcard-chip">' + RG.esc(card.unique_employee_id) + "</span></div>" +
          fields +
        "</div>" +
        '<div class="idcard-foot">' + RG.esc(card.company_address || "") + "</div>" +
      "</div>";
  }

  function idCardModal() {
    var modal = RG.openModal({
      title: "Electronic ID Card",
      body: RG.skeletonCards(1),
      footer: '<button class="btn" data-close>Close</button>'
    });
    API.get("/employees/me/id-card").then(function (card) {
      if (!card.available) {
        modal.body.innerHTML = '<div class="idcard-pending"><b>Your ID card is not ready yet</b>' +
          '<p class="small muted mt-2 mb-0">It is available only after HR/Admin approves your ID request.</p>' +
          (card.missing_fields && card.missing_fields.length
            ? "<ul>" + card.missing_fields.map(function (f) { return "<li>" + RG.esc(f) + "</li>"; }).join("") + "</ul>"
            : "") +
          "</div>";
        return;
      }
      modal.body.innerHTML = '<div class="idcard-wrap">' + cardHtml(card) +
        '<div class="idcard-actions">' +
          '<button class="btn" data-print>Print card</button>' +
          '<button class="btn btn-brand" data-download>Download PDF</button>' +
        "</div></div>";
      RG.hydratePhotos(modal.body);

      modal.body.querySelector("[data-print]").addEventListener("click", function () {
        window.print();
      });
      modal.body.querySelector("[data-download]").addEventListener("click", function () {
        var button = modal.body.querySelector("[data-download]");
        RG.setBusy(button, true, "Preparing\u2026");
        API.download("/employees/me/id-card/pdf", "ID-Card-" + card.unique_employee_id + ".pdf")
          .then(function () { RG.setBusy(button, false); })
          .catch(function (err) { RG.setBusy(button, false); RG.toastErr(err); });
      });
    }).catch(function (err) {
      modal.body.innerHTML = RG.errorState(err.message);
    });
  }

  /* -------------------------------------------- profile change requests */

  function requestModal(preselect) {
    var options = (lock && lock.fields ? lock.fields : []).map(function (f) {
      return '<option value="' + RG.esc(f.field_name) + '"' +
        (f.field_name === preselect ? " selected" : "") +
        (f.pending ? " disabled" : "") + ">" + RG.esc(f.label) +
        (f.pending ? " (request pending)" : "") + "</option>";
    }).join("");

    var modal = RG.openModal({
      title: "Request a profile change",
      body: '<p class="small muted">These details are locked because your profile is complete. ' +
          "HR reviews the request and your profile only changes once it is approved.</p>" +
        '<form id="cr-form" class="form-grid">' +
          '<div class="field full"><label for="cr-field">Which detail?</label>' +
            '<select id="cr-field">' + options + "</select></div>" +
          '<div class="field full"><label for="cr-current">Current value</label>' +
            '<input id="cr-current" type="text" readonly></div>' +
          '<div class="field full"><label for="cr-value">New value</label>' +
            '<input id="cr-value" type="text" placeholder="Enter the corrected detail"></div>' +
          '<div class="field full"><label for="cr-reason">Reason (optional)</label>' +
            '<textarea id="cr-reason" rows="3" placeholder="Helps HR review it faster"></textarea></div>' +
        "</form>",
      footer: '<button class="btn" data-close>Cancel</button>' +
        '<button class="btn btn-brand" data-go>Send to HR</button>'
    });

    var select = modal.body.querySelector("#cr-field");
    var current = modal.body.querySelector("#cr-current");
    var value = modal.body.querySelector("#cr-value");

    function syncCurrent() {
      var chosen = (lock.fields || []).filter(function (f) { return f.field_name === select.value; })[0];
      current.value = (chosen && chosen.current_value) || "";
      value.placeholder = chosen && chosen.field_name === "date_of_birth"
        ? "YYYY-MM-DD" : "Enter the corrected detail";
    }
    select.addEventListener("change", syncCurrent);
    syncCurrent();

    modal.foot.querySelector("[data-go]").addEventListener("click", function () {
      var button = modal.foot.querySelector("[data-go]");
      var newValue = value.value.trim();
      if (!newValue) {
        RG.toastErr({ message: "Enter the new value you are requesting." });
        value.focus();
        return;
      }
      RG.setBusy(button, true, "Sending\u2026");
      API.post("/profile-change-requests", {
        field_name: select.value,
        new_value: newValue,
        reason: modal.body.querySelector("#cr-reason").value.trim() || null
      }).then(function () {
        modal.close();
        RG.toastOk("Request sent to HR. You will be notified once it is reviewed.");
        load();
      }).catch(function (err) { RG.setBusy(button, false); RG.toastErr(err); });
    });
  }

  function requestsCard() {
    if (!requests.length) {
      return '<div class="card span-2"><div class="card-head"><h3>My change requests</h3></div>' +
        '<div class="card-body"><p class="small muted mb-0">You have not requested any profile changes.</p></div></div>';
    }
    var rows = requests.map(function (r) {
      return "<tr><td data-label=\"Detail\">" + RG.esc(r.field_label) + "</td>" +
        '<td data-label="From" class="muted">' + RG.esc(r.old_value || "\u2014") + "</td>" +
        '<td data-label="To"><b>' + RG.esc(r.new_value) + "</b></td>" +
        '<td data-label="Status">' + RG.badge(r.status) + "</td>" +
        '<td data-label="Requested">' + RG.fmt.date(r.requested_at || r.created_at) + "</td>" +
        '<td data-label="HR remarks" class="small muted">' + RG.esc(r.hr_remarks || "\u2014") + "</td></tr>";
    }).join("");
    return '<div class="card span-2"><div class="card-head"><h3>My change requests</h3>' +
      '<span class="hint">' + requests.length + " total</span></div>" +
      '<div class="table-scroll"><table class="data"><thead><tr><th>Detail</th><th>From</th><th>To</th>' +
      "<th>Status</th><th>Requested</th><th>HR remarks</th></tr></thead><tbody>" + rows +
      "</tbody></table></div></div>";
  }

  function lockedRow(field) {
    return '<div class="locked-row"><div class="lr-main">' +
        '<div class="lr-label">' + RG.esc(field.label) + "</div>" +
        '<div class="lr-value">' + RG.esc(field.current_value || "\u2014") + "</div>" +
      "</div>" +
      (field.pending
        ? '<span class="lock-pill">Request pending</span>'
        : '<span class="lock-pill">' + lockIcon() + "Locked</span>" +
          '<button class="btn btn-sm" data-request="' + RG.esc(field.field_name) + '">Request change</button>') +
      "</div>";
  }

  /* --------------------------------------------------------------- page */

  function render() {
    var idStatus = me.id_card_status || (me.unique_employee_id ? "Approved" : "Pending");
    var idChip = me.unique_employee_id && idStatus === "Approved"
      ? '<span class="idcard-chip">' + RG.esc(me.unique_employee_id) + "</span>"
      : '<span class="lock-pill">' + RG.esc(idStatus === "Pending" && me.id_card_requested_at ? "Pending HR approval" : idStatus === "Rejected" ? "ID request rejected" : "ID not issued") + "</span>";

    var completionNote;
    if (me.unique_employee_id && idStatus === "Approved") {
      completionNote = "Your Employee ID is approved and your electronic ID card is available.";
    } else if (idStatus === "Pending" && me.id_card_requested_at) {
      completionNote = "Your ID approval request is pending with HR/Admin.";
    } else if (idStatus === "Rejected") {
      completionNote = "Your ID request was rejected. Review the HR remarks and request approval again.";
    } else if (IS_HR) {
      completionNote = "HR/Admin IDs are approved automatically once your profile and HR-approved photograph are complete.";
    } else {
      completionNote = "Complete your profile and photograph, then request HR/Admin approval before your final Employee ID is issued.";
    }

    var idAction = "";
    if (!IS_HR && me.profile_complete && !me.unique_employee_id && (!me.id_card_requested_at || idStatus === "Rejected")) {
      idAction = '<button class="btn btn-brand" data-request-id>Request ID Approval</button>';
    } else if (!IS_HR && me.profile_complete && !me.unique_employee_id && idStatus === "Pending" && me.id_card_requested_at) {
      idAction = '<span class="lock-pill">ID approval pending</span>';
    }

    var missing = (me.profile_missing_fields || []).length
      ? '<ul class="idcard-pending mt-3" style="border:0;padding:0;background:none;text-align:left">' +
          me.profile_missing_fields.map(function (f) { return "<li>" + RG.esc(f) + "</li>"; }).join("") +
        "</ul>"
      : "";

    ctx.page.innerHTML =
      '<div class="page-head"><div class="identity">' + RG.avatar(me, "lg") +
        "<div><h1>" + RG.esc(me.full_name) + "</h1>" +
        '<p class="sub">' + RG.esc(me.designation || "") + " \u00B7 " + RG.esc(me.department || "") + "</p>" +
        '<div class="row mt-2">' + idChip + RG.badge(me.employment_status) +
          (me.photo_status === "Pending" ? '<span class="badge warn">Photo pending HR approval</span>' : "") +
          (me.photo_status === "Rejected" || me.photo_status === "Re-upload Requested" ? '<span class="badge bad">Photo ' + RG.esc(me.photo_status.toLowerCase()) + "</span>" : "") +
          RG.badge(me.uan_status || "Not Submitted") + "</div></div></div>" +
        '<div class="page-actions"><button class="btn" data-photo-btn>Update photo</button>' +
        '<button class="btn" data-idcard' + (me.id_card_available ? "" : " disabled title=\"Complete your profile first\"") +
          ">View ID Card</button>" +
        '<button class="btn btn-brand" data-edit>Edit my details</button></div></div>' +

      '<div class="card mb-4"><div class="card-body">' +
        '<div class="meter-label"><span>Profile completion</span><span>' + Math.round(me.profile_completion || 0) + "%</span></div>" +
        '<div class="bar"><span style="width:' + (me.profile_completion || 0) + '%"></span></div>' +
        '<p class="small muted mt-2 mb-0">' + completionNote + "</p>" + idAction + missing +
      "</div></div>" +

      '<div class="grid grid-2">' +
        '<div class="card"><div class="card-head"><h3>Personal information</h3>' +
          '<span class="hint">' + (me.identity_locked ? "Locked \u00B7 HR approval needed" : "Editable until your profile is complete") +
          "</span></div><div class=\"card-body\">" +
          (me.identity_locked && lock
            ? '<div class="locked-list">' + (lock.fields || []).map(lockedRow).join("") + "</div>" +
              '<p class="small muted mt-3 mb-0">Address and emergency contact stay editable from ' +
              "<b>Edit my details</b>.</p>"
            : '<dl class="kv">' +
                kv("Full name", RG.esc(me.full_name)) +
                kv("Date of birth", RG.fmt.date(me.date_of_birth)) +
                kv("Gender", RG.esc(me.gender)) +
                kv("Phone", RG.esc(me.phone)) +
                kv("Email", RG.esc(me.email)) +
              "</dl>") +
          '<dl class="kv mt-3">' +
            kv("Address", RG.esc(me.address)) +
            kv("Emergency contact", RG.esc(me.emergency_contact_name) +
              (me.emergency_contact_phone ? " \u00B7 " + RG.esc(me.emergency_contact_phone) : "") +
              (me.emergency_contact_relation ? ' <span class="muted small">(' + RG.esc(me.emergency_contact_relation) + ")</span>" : "")) +
          "</dl></div></div>" +

        '<div class="card"><div class="card-head"><h3>Employment information</h3>' +
          '<span class="hint">Maintained by HR</span></div><div class="card-body">' +
          '<dl class="kv">' +
            kv(ID_LABEL, me.unique_employee_id
              ? '<span class="num">' + RG.esc(me.unique_employee_id) + "</span>"
              : '<span class="muted">Pending profile completion</span>') +
            kv("Joining code", RG.esc(me.employee_code)) +
            kv("Department", RG.esc(me.department)) +
            (me.is_intern ? kv("Internship background", RG.esc(me.internship_background)) : "") +
            kv("Designation", RG.esc(me.designation)) +
            kv("Joining date", RG.fmt.date(me.joining_date)) +
            kv("Work location", RG.esc(me.work_location || "Company default")) +
            kv("Reporting manager", RG.esc(me.reporting_manager)) +
            kv("Reporting HR", RG.esc(me.reporting_hr)) +
            kv("Role", RG.esc(me.role_label)) +
            kv("Employment status", RG.badge(me.employment_status)) +
          "</dl></div></div>" +

        '<div class="card span-2"><div class="card-head"><h3>Provident fund (UAN)</h3>' +
          '<a class="hint" href="uan.html">Manage UAN</a></div><div class="card-body">' +
          '<dl class="kv">' +
            kv("UAN", me.uan_number ? '<span class="num">' + RG.esc(me.uan_number) + "</span>" : "\u2014") +
            kv("Status", RG.badge(me.uan_status || "Not Submitted")) +
            kv("Submitted", RG.fmt.dateTime(me.uan_submitted_at)) +
            kv("HR remarks", RG.esc(me.uan_remarks)) +
          "</dl></div></div>" +

        requestsCard() +
      "</div>";
    RG.hydratePhotos(ctx.page);
  }

  function editModal() {
    var phoneLocked = me.identity_locked;
    var modal = RG.openModal({
      title: "Edit my details",
      body: '<p class="small muted">Name, department, designation and joining date are set by HR.' +
          (phoneLocked ? " Your phone number is locked \u2014 use <b>Request change</b> on your profile." : "") +
          "</p>" +
        '<form id="p-form" class="form-grid">' +
          (phoneLocked ? "" :
            '<div class="field"><label for="p-phone">Phone</label>' +
            '<input id="p-phone" type="tel" value="' + RG.esc(me.phone || "") + '"></div>') +
          '<div class="field"><label for="p-ec-name">Emergency contact name</label>' +
            '<input id="p-ec-name" type="text" value="' + RG.esc(me.emergency_contact_name || "") + '"></div>' +
          '<div class="field"><label for="p-ec-phone">Emergency contact phone</label>' +
            '<input id="p-ec-phone" type="tel" value="' + RG.esc(me.emergency_contact_phone || "") + '"></div>' +
          '<div class="field"><label for="p-ec-rel">Relationship</label>' +
            '<input id="p-ec-rel" type="text" value="' + RG.esc(me.emergency_contact_relation || "") + '"></div>' +
          '<div class="field full"><label for="p-address">Address</label>' +
            '<textarea id="p-address" rows="3">' + RG.esc(me.address || "") + "</textarea></div>" +
        "</form>",
      footer: '<button class="btn" data-close>Cancel</button>' +
        '<button class="btn btn-brand" data-go>Save my details</button>'
    });
    modal.foot.querySelector("[data-go]").addEventListener("click", function () {
      var button = modal.foot.querySelector("[data-go]");
      var phoneInput = modal.body.querySelector("#p-phone");
      var payload = {
        address: modal.body.querySelector("#p-address").value.trim() || null,
        emergency_contact_name: modal.body.querySelector("#p-ec-name").value.trim() || null,
        emergency_contact_phone: modal.body.querySelector("#p-ec-phone").value.trim() || null,
        emergency_contact_relation: modal.body.querySelector("#p-ec-rel").value.trim() || null
      };
      if (phoneInput) payload.phone = phoneInput.value.trim() || null;
      RG.setBusy(button, true, "Saving\u2026");
      API.put("/employees/me", payload).then(function () {
        modal.close(); RG.toastOk("Your details were updated."); load();
      }).catch(function (err) { RG.setBusy(button, false); RG.toastErr(err); });
    });
  }

  function photoModal() {
    var modal = RG.openModal({
      title: "Update profile photo", size: "sm",
      body: '<p class="small muted">A photograph is required before your ID card can be issued. ' +
        'New photos are sent to HR for approval; once approved they replace your profile and ID-card photo.</p>' +
        '<div class="drop" id="drop"><div class="drop-icon">' + RG.icon("upload", 20) + "</div>" +
        "<b>Choose a photo</b><span>PNG, JPG or WEBP</span>" +
        '<input type="file" id="file" accept=".png,.jpg,.jpeg,.webp"></div><ul class="file-list" id="chosen"></ul>',
      footer: '<button class="btn" data-close>Cancel</button>' +
        '<button class="btn btn-brand" data-go disabled>Upload photo</button>'
    });
    var input = modal.body.querySelector("#file");
    var go = modal.foot.querySelector("[data-go]");
    modal.body.querySelector("#drop").addEventListener("click", function () { input.click(); });
    input.addEventListener("change", function () {
      var file = input.files[0];
      if (!file) return;
      modal.body.querySelector("#chosen").innerHTML = '<li class="file-item"><span class="f-thumb">' +
        '<img alt="" src="' + URL.createObjectURL(file) + '"></span>' +
        '<div class="f-meta"><b class="truncate">' + RG.esc(file.name) + "</b><span>" +
        RG.fmt.bytes(file.size) + "</span></div></li>";
      go.disabled = false;
    });
    go.addEventListener("click", function () {
      var form = new FormData();
      form.append("file", input.files[0]);
      RG.setBusy(go, true, "Uploading\u2026");
      API.upload("/employees/me/photo", form).then(function () {
        modal.close(); RG.toastOk("Photo sent to HR for approval. It will appear on your profile and ID card once approved.", "Submitted"); load();
      }).catch(function (err) { RG.setBusy(go, false); RG.toastErr(err); });
    });
  }

  function load() {
    Promise.all([
      API.get("/employees/me"),
      API.get("/employees/me/profile-lock"),
      API.get("/profile-change-requests?page_size=25")
    ]).then(function (results) {
      me = results[0];
      lock = results[1];
      requests = (results[2] && results[2].items) || [];
      render();
    }).catch(function (err) {
      ctx.page.innerHTML = '<div class="card">' + RG.errorState(err.message, "retry") + "</div>";
      var r = document.getElementById("retry");
      if (r) r.addEventListener("click", load);
    });
  }

  RG.on(document, "[data-edit]", "click", function () { if (me) editModal(); });
  RG.on(document, "[data-photo-btn]", "click", function () { photoModal(); });
  RG.on(document, "[data-idcard]", "click", function () { if (me && me.id_card_status === "Approved") idCardModal(); });
  RG.on(document, "[data-request-id]", "click", function (event, el) {
    if (!me) return;
    RG.setBusy(el, true, "Sending…");
    API.post("/employees/me/request-id-approval", {}).then(function () {
      RG.toastOk("ID approval request sent to HR/Admin.");
      load();
    }).catch(function (err) { RG.setBusy(el, false); RG.toastErr(err); });
  });
  RG.on(document, "[data-request]", "click", function (event, el) {
    if (lock) requestModal(el.getAttribute("data-request"));
  });

  ctx.page.innerHTML = RG.skeletonCards(2);
  load();
})();
