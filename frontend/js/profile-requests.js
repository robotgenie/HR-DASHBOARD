/* profile-requests.js - HR review queue for employee profile change requests.

   Approving is what actually writes the employee's locked identity field; the
   employee can never write it themselves. Rejecting leaves the old value alone
   and requires a reason, which the employee is notified with. */
(function () {
  "use strict";
  var ctx = RG.boot({
    scope: "hr", active: "profile-requests",
    title: "Profile Change Requests", subtitle: "Identity changes awaiting HR approval"
  });
  if (!ctx) return;

  var state = { status: "Pending", field_name: "", search: "", page: 1, page_size: 25 };
  var fields = [];
  var data = { items: [], meta: { total: 0, pages: 1, page: 1 } };

  function shell() {
    ctx.page.innerHTML =
      '<div class="profile-requests-page">' +
        '<div class="page-head pr-page-head"><div>' +
          '<h1>Profile Change Requests</h1>' +
          '<p class="sub">Employees cannot edit locked identity fields. Your approval is what applies the change.</p>' +
        '</div></div>' +
        '<div class="tabs pr-tabs" id="tabs"></div>' +
        '<div class="card pr-request-card">' +
          '<div class="toolbar pr-toolbar">' +
            '<div class="search pr-search">' + RG.icon("search", 16) +
              '<input id="q" type="search" placeholder="Search employee, ID or new value" ' +
                'value="' + RG.esc(state.search) + '" aria-label="Search change requests"></div>' +
            '<div class="filters pr-filters">' +
              '<div class="pr-filter-field"><label for="f-field">Field</label>' +
                '<select id="f-field" aria-label="Filter by field"></select></div>' +
              '<button class="btn btn-sm pr-clear" id="reset" type="button">Clear filters</button>' +
            '</div>' +
          "</div>" +
          '<div class="pr-table-wrap" id="rows"></div>' +
          '<div class="pr-pager" id="pager"></div>' +
        "</div>" +
      "</div>";

    renderTabs();
    renderFieldFilter();

    RG.on(ctx.page, "#q", "input", RG.debounce(function () {
      state.search = document.getElementById("q").value.trim();
      state.page = 1;
      load();
    }, 300));
    document.getElementById("f-field").addEventListener("change", function () {
      state.field_name = this.value;
      state.page = 1;
      load();
    });
    document.getElementById("reset").addEventListener("click", function () {
      state.search = ""; state.field_name = ""; state.status = "Pending"; state.page = 1;
      document.getElementById("q").value = "";
      renderFieldFilter(); renderTabs(); load();
    });
  }

  function renderTabs() {
    var tabs = ["Pending", "Approved", "Rejected", "All"];
    document.getElementById("tabs").innerHTML = tabs.map(function (t) {
      var active = (state.status === "" && t === "All") || state.status === t;
      return '<button class="tab' + (active ? " active" : "") + '" data-tab="' +
        (t === "All" ? "" : t) + '">' + t + "</button>";
    }).join("");
  }

  function renderFieldFilter() {
    var select = document.getElementById("f-field");
    if (!select) return;
    select.innerHTML = '<option value="">All details</option>' + fields.map(function (f) {
      return '<option value="' + RG.esc(f.field_name) + '"' +
        (state.field_name === f.field_name ? " selected" : "") + ">" + RG.esc(f.label) + "</option>";
    }).join("");
  }

  function row(request) {
    var actions = request.status === "Pending"
      ? '<button class="btn btn-sm" data-view="' + request.id + '">Review</button>'
      : '<button class="btn btn-sm" data-view="' + request.id + '">Details</button>';
    return "<tr>" +
      '<td data-label="Employee"><div class="cell-id"><b>' + RG.esc(request.employee_name || "\u2014") + "</b>" +
        '<span class="muted small">' + RG.esc(request.employee_display_id || "") +
        (request.department ? " \u00B7 " + RG.esc(request.department) : "") + "</span></div></td>" +
      '<td data-label="Detail">' + RG.esc(request.field_label) + "</td>" +
      '<td data-label="Current" class="muted">' + RG.esc(request.old_value || "\u2014") + "</td>" +
      '<td data-label="Requested"><b>' + RG.esc(request.new_value) + "</b></td>" +
      '<td data-label="Status">' + RG.badge(request.status) + "</td>" +
      '<td data-label="Raised">' + RG.fmt.date(request.requested_at || request.created_at) + "</td>" +
      '<td data-label="Action" class="right">' + actions + "</td></tr>";
  }

  function renderRows() {
    var host = document.getElementById("rows");
    if (!data.items.length) {
      host.innerHTML = state.status === "Pending"
        ? RG.emptyState("Nothing to review",
            "No employee has a pending profile change request.")
        : RG.emptyState("No change requests found",
            "No change requests match these filters.");
      document.getElementById("pager").innerHTML = "";
      return;
    }
    host.innerHTML = '<div class="table-scroll"><table class="data"><thead><tr>' +
      "<th>Employee</th><th>Detail</th><th>Current value</th><th>Requested value</th>" +
      '<th>Status</th><th>Raised</th><th class="right">Action</th>' +
      "</tr></thead><tbody>" + data.items.map(row).join("") + "</tbody></table></div>";
    RG.renderPager(document.getElementById("pager"), data.meta, function (p) {
      state.page = p;
      load();
    });
  }

  function diff(request) {
    return '<div class="value-diff">' +
        '<div class="vd-box vd-old"><div class="vd-label">Current</div>' +
          '<div class="vd-value">' + RG.esc(request.old_value || "\u2014") + "</div></div>" +
        '<div class="vd-arrow">\u2192</div>' +
        '<div class="vd-box vd-new"><div class="vd-label">Requested</div>' +
          '<div class="vd-value">' + RG.esc(request.new_value) + "</div></div>" +
      "</div>";
  }

  function reviewModal(request) {
    var pending = request.status === "Pending";
    var modal = RG.openModal({
      title: request.field_label + " change \u00B7 " + (request.employee_name || ""),
      body:
        '<dl class="kv mb-3">' +
          "<dt>Employee</dt><dd>" + RG.esc(request.employee_name || "\u2014") +
            ' <span class="muted small">' + RG.esc(request.employee_display_id || "") + "</span></dd>" +
          "<dt>Department</dt><dd>" + RG.esc(request.department || "\u2014") + "</dd>" +
          "<dt>Detail</dt><dd>" + RG.esc(request.field_label) + "</dd>" +
          "<dt>Raised</dt><dd>" + RG.fmt.dateTime(request.requested_at || request.created_at) + "</dd>" +
          "<dt>Status</dt><dd>" + RG.badge(request.status) + "</dd>" +
        "</dl>" +
        diff(request) +
        (request.reason
          ? '<div class="mt-3"><div class="lr-label">Employee\u2019s reason</div><p class="mb-0">' +
            RG.esc(request.reason) + "</p></div>"
          : "") +
        (pending
          ? '<div class="field full mt-3"><label for="cr-remarks">Remarks</label>' +
            '<textarea id="cr-remarks" rows="3" placeholder="Required when rejecting; optional when approving"></textarea></div>'
          : '<div class="mt-3"><div class="lr-label">HR remarks</div><p class="mb-0">' +
            RG.esc(request.hr_remarks || "\u2014") + "</p>" +
            '<p class="small muted mt-2 mb-0">Reviewed ' + RG.fmt.dateTime(request.reviewed_at) +
            (request.reviewed_by ? " by " + RG.esc(request.reviewed_by) : "") + "</p></div>"),
      footer: pending
        ? '<button class="btn" data-close>Cancel</button>' +
          '<button class="btn btn-danger" data-reject>Reject</button>' +
          '<button class="btn btn-brand" data-approve>Approve &amp; apply</button>'
        : '<button class="btn" data-close>Close</button>'
    });

    if (!pending) return;

    function act(kind) {
      var button = modal.foot.querySelector("[data-" + kind + "]");
      var remarks = modal.body.querySelector("#cr-remarks").value.trim();
      if (kind === "reject" && !remarks) {
        RG.toastErr({ message: "Add a reason so the employee knows why it was rejected." });
        modal.body.querySelector("#cr-remarks").focus();
        return;
      }
      RG.setBusy(button, true, kind === "approve" ? "Applying\u2026" : "Rejecting\u2026");
      API.post("/profile-change-requests/" + request.id + "/" + kind, { remarks: remarks || null })
        .then(function () {
          modal.close();
          RG.toastOk(kind === "approve"
            ? "Approved. The employee\u2019s profile has been updated."
            : "Rejected. The employee has been notified with your remarks.");
          load();
        })
        .catch(function (err) { RG.setBusy(button, false); RG.toastErr(err); });
    }

    modal.foot.querySelector("[data-approve]").addEventListener("click", function () { act("approve"); });
    modal.foot.querySelector("[data-reject]").addEventListener("click", function () { act("reject"); });
  }

  function load() {
    var host = document.getElementById("rows");
    if (host) host.innerHTML = RG.skeletonRows(5);
    API.get("/profile-change-requests", {
      status: state.status || null,
      field_name: state.field_name || null,
      search: state.search || null,
      page: state.page,
      page_size: state.page_size
    }).then(function (result) {
      data = result;
      renderRows();
    }).catch(function (err) {
      if (host) host.innerHTML = RG.errorState(err.message, "retry");
      var r = document.getElementById("retry");
      if (r) r.addEventListener("click", load);
    });
  }

  RG.on(document, "[data-tab]", "click", function (event, el) {
    state.status = el.getAttribute("data-tab");
    state.page = 1;
    renderTabs();
    load();
  });
  RG.on(document, "[data-view]", "click", function (event, el) {
    var id = Number(el.getAttribute("data-view"));
    var request = data.items.filter(function (r) { return r.id === id; })[0];
    if (request) reviewModal(request);
  });

  API.get("/profile-change-requests/fields").then(function (list) {
    fields = list || [];
    shell();
    load();
  }).catch(function () {
    shell();
    load();
  });
})();
