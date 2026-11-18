(function () {
  "use strict";
  var ctx = RG.boot({ scope: "hr", active: "id-approvals", title: "ID Approvals", subtitle: "Review Employee ID card requests" });
  if (!ctx) return;

  var state = { page: 1, page_size: 20, status: "Pending", search: "", department_id: "" };
  var host;

  function load() {
    host.innerHTML = RG.skeletonRows(7);
    API.get("/employees/id-approval-requests", state).then(function (data) {
      var rows = data.items || [];
      if (!rows.length) {
        host.innerHTML = RG.emptyState("No ID requests", "No employee ID requests match the selected filters.", "", "badge");
        document.getElementById("pager").innerHTML = "";
        return;
      }
      host.innerHTML = '<div class="table-scroll"><table class="data"><thead><tr>' +
        '<th>Employee</th><th>Department</th><th>Designation</th><th>Photo</th><th>Status</th><th>Requested</th><th>Actions</th>' +
        '</tr></thead><tbody>' + rows.map(function (e) {
          var actions = e.id_card_status === "Pending"
            ? '<button class="btn btn-sm btn-brand" data-approve="' + e.id + '">Approve</button> ' +
              '<button class="btn btn-sm" data-reject="' + e.id + '">Reject</button>'
            : '<button class="btn btn-sm" data-view="' + e.id + '">View</button>';
          return '<tr>' +
            '<td data-label="Employee"><div class="identity">' + RG.avatar({full_name:e.full_name,id:e.id}, "sm") + '<div><div class="name">' + RG.esc(e.full_name) + '</div><div class="meta">' + RG.esc(e.employee_code) + '</div></div></div></td>' +
            '<td data-label="Department">' + RG.esc(e.department || "—") + '</td>' +
            '<td data-label="Designation">' + RG.esc(e.designation || "—") + '</td>' +
            '<td data-label="Photo">' + (e.photo_path ? 'Uploaded' : 'Missing') + '</td>' +
            '<td data-label="Status">' + RG.badge(e.id_card_status) + '</td>' +
            '<td data-label="Requested">' + RG.fmt.dateTime(e.id_card_requested_at) + '</td>' +
            '<td class="actions" data-label="Actions">' + actions + '</td>' +
            '</tr>';
        }).join("") + '</tbody></table></div>';
      RG.renderPager(document.getElementById("pager"), data.meta, function (p) { state.page = p; load(); });
    }).catch(function (err) {
      host.innerHTML = RG.errorState(err.message, "retry");
      var retry = document.getElementById("retry"); if (retry) retry.addEventListener("click", load);
    });
  }

  function approve(id, button) {
    RG.setBusy(button, true, "Approving…");
    API.post("/employees/" + id + "/approve-id", {}).then(function () {
      RG.toastOk("Employee ID approved and issued.");
      load();
    }).catch(function (err) { RG.setBusy(button, false); RG.toastErr(err); });
  }

  function reject(id) {
    var modal = RG.openModal({
      title: "Reject ID request",
      body: '<div class="field"><label for="reject-remarks">Reason / remarks</label><textarea id="reject-remarks" rows="4" maxlength="1000" placeholder="Explain why the ID request is being rejected."></textarea></div>',
      footer: '<button class="btn" data-close>Cancel</button><button class="btn btn-brand" data-confirm>Reject Request</button>'
    });
    modal.foot.querySelector("[data-confirm]").addEventListener("click", function () {
      var remarks = modal.body.querySelector("#reject-remarks").value.trim();
      if (!remarks) { RG.toastErr({message:"Enter rejection remarks."}); return; }
      var b = this; RG.setBusy(b, true, "Rejecting…");
      API.post("/employees/" + id + "/reject-id?remarks=" + encodeURIComponent(remarks), {}).then(function () {
        modal.close(); RG.toastOk("ID request rejected."); load();
      }).catch(function (err) { RG.setBusy(b, false); RG.toastErr(err); });
    });
  }

  function view(id) {
    API.get("/employees/" + id + "/id-card").then(function (card) {
      var body = '<dl class="kv"><dt>Employee</dt><dd>' + RG.esc(card.full_name) + '</dd>' +
        '<dt>Employee ID</dt><dd>' + RG.esc(card.unique_employee_id || "—") + '</dd>' +
        '<dt>Status</dt><dd>' + RG.badge(card.id_card_status) + '</dd>' +
        '<dt>Designation</dt><dd>' + RG.esc(card.designation) + '</dd></dl>';
      var modal = RG.openModal({ title: "ID Card", body: body, footer: '<button class="btn" data-close>Close</button><button class="btn btn-brand" data-download>Download PDF</button>' });
      modal.foot.querySelector("[data-download]").addEventListener("click", function () {
        API.download("/employees/" + id + "/id-card/pdf", "ID-Card-" + (card.unique_employee_id || "employee") + ".pdf").catch(RG.toastErr);
      });
    }).catch(RG.toastErr);
  }

  ctx.page.innerHTML = '<div class="page-head"><div><h1>ID approvals</h1><p class="sub">Approve or reject final Employee ID cards after profile completion.</p></div></div>' +
    '<div class="card"><div class="toolbar"><div class="filters" style="margin-left:0">' +
    '<select id="f-status"><option value="Pending">Pending</option><option value="Approved">Approved</option><option value="Rejected">Rejected</option><option value="All">All</option></select>' +
    '<input id="f-search" type="search" placeholder="Search employee, ID or email">' +
    '</div></div><div id="host"></div><div class="pager" id="pager"></div></div>';
  host = document.getElementById("host");

  document.getElementById("f-status").addEventListener("change", function () { state.status = this.value; state.page = 1; load(); });
  document.getElementById("f-search").addEventListener("input", function () { state.search = this.value; state.page = 1; load(); });
  RG.on(document, "[data-approve]", "click", function (e, el) { approve(el.dataset.approve, el); });
  RG.on(document, "[data-reject]", "click", function (e, el) { reject(el.dataset.reject); });
  RG.on(document, "[data-view]", "click", function (e, el) { view(el.dataset.view); });
  load();
})();
