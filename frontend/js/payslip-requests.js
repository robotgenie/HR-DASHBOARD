/* payslip-requests.js - HR review queue for intern payslip download requests.

   Approving grants permission on that one salary record only; rejecting leaves
   the download blocked and tells the intern why. The backend enforces both -
   this page is the way HR sees the reason before deciding. */
(function () {
  "use strict";
  var ctx = RG.boot({
    scope: "hr", active: "payslip-requests",
    title: "Intern Payslip Download Requests", subtitle: "Interns asking to download a payslip"
  });
  if (!ctx) return;

  var state = { status: "Pending", search: "", page: 1, page_size: 25 };
  var data = { items: [], meta: { total: 0, pages: 1, page: 1 } };

  function shell() {
    ctx.page.innerHTML =
      '<div class="page-head"><div><h1>Intern Payslip Download Requests</h1>' +
        '<p class="sub">Interns can always view a payslip. Downloading needs your approval, ' +
        "for that pay period only.</p></div></div>" +
      '<div class="tabs" id="tabs"></div>' +
      '<div class="card"><div class="toolbar">' +
        '<div class="search">' + RG.icon("search", 16) +
          '<input id="q" type="text" placeholder="Search intern, employee ID or reason" ' +
          'aria-label="Search download requests"></div>' +
        '<div class="filters"><button class="btn btn-sm" id="reset" type="button">Clear</button></div>' +
      "</div>" +
      '<div id="rows"></div>' +
      '<div class="pager" id="pager"></div></div>';

    renderTabs();

    document.getElementById("q").addEventListener("input", RG.debounce(function (e) {
      state.search = e.target.value.trim();
      state.page = 1;
      load();
    }, 300));
    document.getElementById("reset").addEventListener("click", function () {
      state.search = "";
      state.status = "Pending";
      state.page = 1;
      document.getElementById("q").value = "";
      renderTabs();
      load();
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

  function row(r) {
    return "<tr>" +
      '<td data-label="Intern"><div class="cell-id"><b>' + RG.esc(r.employee_name || "\u2014") + "</b>" +
        '<span class="muted small">' + RG.esc(r.employee_display_id || "") +
        (r.department ? " \u00B7 " + RG.esc(r.department) : "") + "</span></div></td>" +
      '<td data-label="Pay period">' + RG.esc(r.period_label || "\u2014") + "</td>" +
      '<td data-label="Net pay" class="num">' + RG.fmt.money(r.net_pay) + "</td>" +
      '<td data-label="Reason"><span class="truncate" style="max-width:260px;display:inline-block">' +
        RG.esc(r.reason) + "</span></td>" +
      '<td data-label="Requested">' + RG.fmt.date(r.requested_at || r.created_at) + "</td>" +
      '<td data-label="Status">' + RG.badge(r.status) + "</td>" +
      '<td data-label="Action" class="right"><button class="btn btn-sm" data-open="' + r.id + '">' +
        (r.status === "Pending" ? "Review" : "Details") + "</button></td></tr>";
  }

  function renderRows() {
    var host = document.getElementById("rows");
    if (!data.items.length) {
      host.innerHTML = state.status === "Pending"
        ? RG.emptyState("Nothing to review", "No intern is waiting on a payslip download.")
        : RG.emptyState("No requests found", "No download requests match these filters.");
      document.getElementById("pager").innerHTML = "";
      return;
    }
    host.innerHTML = '<div class="table-scroll"><table class="data"><thead><tr>' +
      "<th>Intern</th><th>Pay period</th><th>Net pay</th><th>Reason for download</th>" +
      '<th>Requested</th><th>Status</th><th class="right">Action</th>' +
      "</tr></thead><tbody>" + data.items.map(row).join("") + "</tbody></table></div>";
    RG.renderPager(document.getElementById("pager"), data.meta, function (p) {
      state.page = p;
      load();
    });
  }

  function reviewModal(request) {
    var pending = request.status === "Pending";
    var modal = RG.openModal({
      title: "Payslip download request \u00B7 " + (request.employee_name || ""),
      body:
        '<dl class="kv mb-3">' +
          "<dt>Intern</dt><dd>" + RG.esc(request.employee_name || "\u2014") +
            ' <span class="muted small">' + RG.esc(request.employee_display_id || "") + "</span></dd>" +
          "<dt>Department</dt><dd>" + RG.esc(request.department || "\u2014") + "</dd>" +
          "<dt>Pay period</dt><dd>" + RG.esc(request.period_label || "\u2014") + "</dd>" +
          "<dt>Net pay</dt><dd>" + RG.fmt.money(request.net_pay) + "</dd>" +
          "<dt>Requested</dt><dd>" + RG.fmt.dateTime(request.requested_at || request.created_at) + "</dd>" +
          "<dt>Status</dt><dd>" + RG.badge(request.status) + "</dd>" +
        "</dl>" +
        '<div class="lr-label">Reason given by the intern</div>' +
        '<p class="mb-0">' + RG.esc(request.reason) + "</p>" +
        (pending
          ? '<div class="field full mt-3"><label for="dr-remarks">Remarks</label>' +
            '<textarea id="dr-remarks" rows="3" ' +
            'placeholder="Required when rejecting; optional when approving"></textarea></div>' +
            '<p class="small muted mb-0">Approving allows the download for ' +
            RG.esc(request.period_label || "this period") + " only.</p>"
          : '<div class="mt-3"><div class="lr-label">HR remarks</div><p class="mb-0">' +
            RG.esc(request.hr_remarks || "\u2014") + "</p>" +
            '<p class="small muted mt-2 mb-0">Reviewed ' + RG.fmt.dateTime(request.reviewed_at) +
            (request.hr_reviewer ? " by " + RG.esc(request.hr_reviewer) : "") + "</p></div>"),
      footer: pending
        ? '<button class="btn" data-close>Cancel</button>' +
          '<button class="btn btn-danger" data-reject>Reject</button>' +
          '<button class="btn btn-brand" data-approve>Approve download</button>'
        : '<button class="btn" data-close>Close</button>'
    });

    if (!pending) return;

    function act(kind) {
      var button = modal.foot.querySelector("[data-" + kind + "]");
      var remarks = modal.body.querySelector("#dr-remarks").value.trim();
      if (kind === "reject" && !remarks) {
        RG.toastErr({ message: "Add a reason so the intern knows why it was rejected." });
        modal.body.querySelector("#dr-remarks").focus();
        return;
      }
      RG.setBusy(button, true, kind === "approve" ? "Approving\u2026" : "Rejecting\u2026");
      API.post("/payslip-download-requests/" + request.id + "/" + kind,
               { remarks: remarks || null })
        .then(function () {
          modal.close();
          RG.toastOk(kind === "approve"
            ? "Approved. The intern can now download that payslip."
            : "Rejected. The intern has been notified with your remarks.");
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
    API.get("/payslip-download-requests", {
      status: state.status || null,
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
  RG.on(document, "[data-open]", "click", function (event, el) {
    var id = Number(el.getAttribute("data-open"));
    var request = data.items.filter(function (r) { return r.id === id; })[0];
    if (request) reviewModal(request);
  });

  shell();
  load();
})();
