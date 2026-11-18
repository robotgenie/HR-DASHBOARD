/* Leave review queue for Admin, HR and Managers. Who may decide is enforced
   by the API (hierarchy): Employee -> Manager -> HR -> Admin. The page only
   offers Approve / Reject when the API says the request is waiting on you. */
(function () {
  "use strict";
  var ctx = RG.boot({ scope: "hr", active: "leave-requests", title: "Leave Requests", subtitle: "Review employee & intern leave" });
  if (!ctx) return;

  var SCOPE = ctx.scope;
  var state = { page: 1, page_size: 15, status: "Pending", department_id: "", search: "", awaiting_me: true,
                stage: "", leave_type: "", reporting_hr_id: "" };
  var SUB = {
    admin: "Every leave request in the organisation. HR leave comes to you for the decision.",
    hr: "Leave from the managers, employees and interns in your hierarchy. You give the final decision.",
    manager: "Leave from your team. Approving forwards the request to HR for the final decision."
  };

  ctx.page.innerHTML =
    '<div class="page-head"><div><h1>' + (SCOPE === "manager" ? "Team Leave" : "Leave Requests") + '</h1>' +
      '<p class="sub">' + RG.esc(SUB[SCOPE] || "") + '</p></div></div>' +
    '<div class="today-strip" id="leave-strip"></div>' +
    '<div class="card"><div class="toolbar"><div class="filters" style="margin-left:0">' +
      '<input id="l-search" type="search" placeholder="Search employee or ID">' +
      '<label class="row" style="gap:6px"><input type="checkbox" id="l-mine" checked> Waiting on me</label>' +
      '<select id="l-dept"><option value="">All departments</option></select>' +
      (SCOPE === "admin" ? '<select id="l-hr"><option value="">All HR</option></select>' : '') +
      '<select id="l-stage"><option value="">Any stage</option><option value="Manager">At manager</option><option value="HR">At HR</option><option value="Admin">At Admin</option><option value="Closed">Closed</option></select>' +
      '<select id="l-type"><option value="">All leave types</option>' +
        ["Casual Leave", "Sick Leave", "Earned Leave", "Unpaid Leave", "Other", "Half Day Leave"].map(function (t) {
          return '<option value="' + t + '">' + RG.esc(RG.leaveTypeLabel(t)) + "</option>"; }).join("") + '</select>' +
      '<select id="l-status"><option value="">All statuses</option><option value="Pending" selected>Pending</option><option value="Approved">Approved</option><option value="Rejected">Rejected</option></select>' +
    '</div></div>' +
    '<div id="leave-host">' + RG.skeletonRows(8) + '</div><div class="pager" id="leave-pager"></div></div>';

  function loadLookups() {
    var jobs = [API.get("/departments").then(function (departments) {
      document.getElementById("l-dept").innerHTML =
        '<option value="">All departments</option>' + RG.optionList(departments, "id", "name");
    })];
    if (SCOPE === "admin") {
      jobs.push(API.get("/hierarchy/candidates", { role: "HR_ADMIN" }).then(function (res) {
        document.getElementById("l-hr").innerHTML = '<option value="">All HR</option>' + RG.optionList(res.items, "id", "full_name");
      }));
    }
    return Promise.all(jobs).catch(function () {});
  }

  function loadStrip() {
    API.get("/leave-requests/summary").then(function (s) {
      document.getElementById("leave-strip").innerHTML = [
        ["Waiting on you", s.awaiting_me, s.awaiting_me ? "warn" : ""], ["Pending", s.pending, ""],
        ["Approved", s.approved, "ok"], ["Rejected", s.rejected, ""]
      ].map(function (c) { return '<div class="ts ' + c[2] + '"><span>' + c[0] + "</span><b>" + c[1] + "</b></div>"; }).join("");
    }).catch(function () {});
  }

  function reviewModal(row) {
    var canAct = row.status === "Pending" && row.can_act;
    var approveLabel = SCOPE === "manager" ? "Approve & send to HR" : "Approve";
    var action = canAct ? '<button class="btn btn-brand" data-approve>' + approveLabel + '</button>' +
      '<button class="btn btn-danger" data-reject>Reject</button>' : "";
    var modal = RG.openModal({
      title: "Leave Request",
      size: "lg",
      body:
        '<div class="grid grid-2">' +
          '<div class="card"><div class="card-body"><dl class="kv">' +
            '<dt>Employee</dt><dd>' + RG.esc(row.employee_name || "—") + '</dd>' +
            '<dt>Employee ID</dt><dd>' + RG.esc(row.employee_code || "—") + '</dd>' +
            '<dt>Department</dt><dd>' + RG.esc(row.department || "—") + '</dd>' +
            (row.internship_background ? '<dt>Internship background</dt><dd>' + RG.esc(row.internship_background) + '</dd>' : '') +
          '</dl></div></div>' +
          '<div class="card"><div class="card-body"><dl class="kv">' +
            '<dt>Leave type</dt><dd>' + RG.esc(row.leave_type_label || row.leave_type) + '</dd>' +
            '<dt>Period</dt><dd>' + RG.esc(row.leave_period_label || row.leave_period || "Full Day") + '</dd>' +
            '<dt>Duration</dt><dd>' + (row.duration_days === 0.5 ? "Half day" : RG.esc(row.duration_days) + " day(s)") + '</dd>' +
            '<dt>Paid</dt><dd>' + RG.badge(row.is_paid === false ? "Unpaid" : "Paid") + '</dd>' +
            '<dt>From</dt><dd>' + RG.fmt.dateLong(row.from_date) + '</dd>' +
            '<dt>To</dt><dd>' + RG.fmt.dateLong(row.to_date) + '</dd>' +
            '<dt>Status</dt><dd>' + RG.badge(row.status) + '</dd>' +
            '<dt>Approval stage</dt><dd>' + RG.esc(RG.stageText(row)) + '</dd>' +
          '</dl></div></div>' +
        '</div>' +
        '<div class="card mt-4"><div class="card-head"><h3>Reason</h3></div><div class="card-body"><p class="mb-0">' +
          RG.esc(row.reason) + '</p></div></div>' +
        (row.manager_status ? '<div class="card mt-4"><div class="card-head"><h3>Reporting manager</h3></div><div class="card-body"><p class="mb-0">' +
          RG.badge(row.manager_status) + ' ' + RG.esc(row.manager_reviewed_by_name || "") +
          (row.manager_reviewed_at ? ' · ' + RG.fmt.dateTime(row.manager_reviewed_at) : '') +
          (row.manager_remarks ? '</p><p class="mb-0 mt-2">' + RG.esc(row.manager_remarks) : '') + '</p></div></div>' : '') +
        (row.hr_remarks ? '<div class="card mt-4"><div class="card-head"><h3>Decision remarks</h3></div><div class="card-body"><p class="mb-0">' + RG.esc(row.hr_remarks) +
          (row.reviewed_by_name ? ' <span class="small muted">— ' + RG.esc(row.reviewed_by_name) + '</span>' : '') + '</p></div></div>' : '') +
        (canAct ? '<div class="field mt-4"><label for="leave-remarks">Remarks</label><textarea id="leave-remarks" rows="4" placeholder="Optional for approval; required when rejecting"></textarea></div>'
          : (row.status === "Pending" ? '<p class="small muted mt-4 mb-0">' + RG.esc(RG.stageText(row)) + '. This request is not waiting on you.</p>' : '')),
      footer: '<button class="btn" data-close>Close</button>' + action
    });

    function act(status, button) {
      var remarksEl = modal.body.querySelector("#leave-remarks");
      var remarks = remarksEl ? remarksEl.value.trim() : "";
      if (status === "Rejected" && !remarks) {
        RG.toastErr({ message: "Please provide a rejection reason." });
        if (remarksEl) remarksEl.focus();
        return;
      }
      RG.setBusy(button, true, status === "Approved" ? "Approving…" : "Rejecting…");
      API.patch("/leave-requests/" + row.id, { status: status, hr_remarks: remarks || null })
        .then(function () {
          modal.close();
          RG.toastOk(SCOPE === "manager" && status === "Approved" ? "Approved and sent to HR." : "Leave request " + status.toLowerCase() + ".");
          load(); loadStrip();
        })
        .catch(function (err) { RG.setBusy(button, false); RG.toastErr(err); });
    }

    var approve = modal.foot.querySelector("[data-approve]");
    var reject = modal.foot.querySelector("[data-reject]");
    if (approve) approve.addEventListener("click", function () { act("Approved", approve); });
    if (reject) reject.addEventListener("click", function () { act("Rejected", reject); });
  }

  function row(r) {
    return '<tr>' +
      '<td data-label="Employee"><div class="identity">' +
        RG.avatar({ full_name: r.employee_name, id: r.employee_id }, "sm") +
        '<div><div class="name truncate">' + RG.esc(r.employee_name) + '</div><div class="meta">' + RG.esc(r.employee_code || "") +
        (r.person_type ? " · " + RG.esc(r.person_type) : "") + '</div></div>' +
      '</div></td>' +
      '<td data-label="Department">' + RG.esc(r.department || "—") + '</td>' +
      '<td data-label="Leave">' + RG.esc(r.leave_type_label || r.leave_type) +
        '<div class="small muted">' + RG.esc(r.leave_period || "Full Day") + (r.is_paid === false ? " \u00B7 Unpaid" : "") + '</div></td>' +
      '<td data-label="Dates" class="nowrap">' + (r.from_date === r.to_date ? RG.fmt.date(r.from_date) : RG.fmt.date(r.from_date) + ' – ' + RG.fmt.date(r.to_date)) +
        '<div class="small muted">' + (r.duration_days === 0.5 ? "Half day" : RG.esc(r.duration_days) + " day(s)") + '</div></td>' +
      '<td data-label="Reason"><div class="truncate" style="max-width:260px">' + RG.esc(r.reason) + '</div></td>' +
      '<td data-label="Status">' + RG.badge(r.status) + '<div class="small muted">' + RG.esc(r.status === "Pending" ? RG.stageText(r) : (r.reviewed_by_name ? "by " + r.reviewed_by_name : "")) + '</div></td>' +
      '<td class="actions" data-label="Action"><button class="btn btn-sm' + (r.can_act ? ' btn-brand' : '') + '" data-open="' + r.id + '">' + (r.can_act ? "Review" : "View") + '</button></td>' +
    '</tr>';
  }

  function load() {
    API.get("/leave-requests", state).then(function (data) {
      var items = data.items || [];
      var host = document.getElementById("leave-host");
      if (!items.length) {
        host.innerHTML = RG.emptyState("No leave requests", state.awaiting_me ? "Nothing is waiting on you. Untick “Waiting on me” to see everything you can monitor." : (state.status ? "There are no " + state.status.toLowerCase() + " requests matching your filters." : "No leave requests have been submitted yet."), "", "calendar");
        document.getElementById("leave-pager").innerHTML = "";
        return;
      }
      host.innerHTML = '<div class="table-scroll"><table class="data"><thead><tr>' +
        '<th>Employee</th><th>Department</th><th>Leave</th><th>Dates</th><th>Reason</th><th>Status</th><th></th>' +
        '</tr></thead><tbody>' + items.map(row).join("") + '</tbody></table></div>';
      RG.hydratePhotos(host);
      RG.renderPager(document.getElementById("leave-pager"), data.meta, function (p) { state.page = p; load(); });
    }).catch(function (err) {
      document.getElementById("leave-host").innerHTML = RG.errorState(err.message, "retry-leave");
      var retry = document.getElementById("retry-leave");
      if (retry) retry.addEventListener("click", load);
    });
  }

  RG.on(ctx.page, "[data-open]", "click", function (e, b) {
    API.get("/leave-requests/" + b.dataset.open).then(reviewModal).catch(RG.toastErr);
  });

  document.getElementById("l-status").addEventListener("change", function (e) {
    state.status = e.target.value; state.page = 1; load();
  });
  document.getElementById("l-mine").addEventListener("change", function (e) {
    state.awaiting_me = e.target.checked; state.page = 1; load();
  });
  document.getElementById("l-stage").addEventListener("change", function (e) {
    state.stage = e.target.value; state.page = 1; load();
  });
  document.getElementById("l-type").addEventListener("change", function (e) {
    state.leave_type = e.target.value; state.page = 1; load();
  });
  if (document.getElementById("l-hr")) document.getElementById("l-hr").addEventListener("change", function (e) {
    state.reporting_hr_id = e.target.value; state.page = 1; load();
  });
  document.getElementById("l-dept").addEventListener("change", function (e) {
    state.department_id = e.target.value; state.page = 1; load();
  });
  document.getElementById("l-search").addEventListener("input", RG.debounce(function (e) {
    state.search = e.target.value.trim(); state.page = 1; load();
  }, 350));

  loadStrip();
  loadLookups().finally(load);
})();
