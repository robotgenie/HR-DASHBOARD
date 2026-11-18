/* work-page.js - employee/intern "Tasks & Hourly Updates" page. */
(function () {
  "use strict";
  var scope = document.body.dataset.scope || "employee";
  var ctx = RG.boot({ scope: scope, active: "work", title: "Tasks & Hourly Updates", subtitle: "Today's work, 10:00 AM – 6:00 PM" });
  if (!ctx || !window.RGWork) return;
  var W = window.RGWork;
  var data = {};

  function historyTable(rows) {
    if (!rows.length) return RG.emptyState("No hourly updates yet", "Updates you submit appear here with their task and attachments.", "", "clipboard");
    return '<div class="table-scroll"><table class="data"><thead><tr><th>Date</th><th>Hour</th><th>Task</th><th>Work completed</th><th>Progress</th><th>Status</th><th>Files</th><th></th></tr></thead><tbody>' +
      rows.map(function (u) {
        return "<tr>" +
          '<td data-label="Date" class="nowrap">' + RG.fmt.date(u.update_date) + "</td>" +
          '<td data-label="Hour" class="nowrap">' + RG.esc(u.slot_label) + "</td>" +
          '<td data-label="Task"><b>' + RG.esc(u.task_title || "General work") + '</b><div class="small muted">' + RG.esc(u.assigned_by ? "by " + u.assigned_by : "") + "</div></td>" +
          '<td data-label="Work completed"><div class="truncate" style="max-width:280px">' + RG.esc(u.work_completed) + "</div></td>" +
          '<td data-label="Progress">' + (u.task_target ? u.task_completed + "/" + u.task_target : (u.task_progress != null ? u.task_progress + "%" : "—")) + "</td>" +
          '<td data-label="Status">' + RG.badge(u.task_status) + "</td>" +
          '<td data-label="Files">' + u.attachments.length + "</td>" +
          '<td class="actions"><button class="btn btn-sm" data-open-update="' + u.id + '">View</button></td></tr>';
      }).join("") + "</tbody></table></div>";
  }

  function render() {
    var h = data.hourly || {};
    var slots = h.slots || [];
    var checkedIn = data.status && data.status.state !== "not_checked_in";
    var canSubmit = slots.some(function (s) { return s.can_submit; });
    ctx.page.innerHTML =
      '<div class="page-head"><div><h1>Tasks &amp; Hourly Updates</h1><p class="sub">Hourly updates are in addition to your Noon and EOD reports, and follow your approved leave.</p></div>' +
        '<div class="page-actions">' + (canSubmit ? '<button class="btn btn-brand" data-hourly-open>Submit hourly update</button>' : "") + "</div></div>" +
      W.attendanceCard(data.status) +
      '<div class="card mt-4"><div class="card-head"><h3>Today’s hourly periods</h3><span class="hint">' + (h.submitted_count || 0) + " of " + (h.applicable_count || 0) + " submitted</span></div>" +
        '<div class="card-body">' + (checkedIn ? W.slotGrid(slots) +
          '<p class="small muted mt-3 mb-0">Tap a highlighted hour to submit. Periods covered by approved leave, before Check-In or after Check-Out are not applicable. No new periods open after 6:00 PM.</p>'
          : '<div class="lock-note">' + RG.icon("bell", 18) + "<span>Check in to start today’s hourly updates.</span></div>") + "</div></div>" +
      '<div class="grid grid-2 mt-4">' +
        '<div class="card"><div class="card-head"><h3>Today’s tasks</h3></div><div class="card-body">' +
          (checkedIn ? W.taskCards(h.tasks || []) : '<div class="lock-note">' + RG.icon("calendar", 18) + "<span>Check in to see today’s assigned tasks.</span></div>") + "</div></div>" +
        '<div class="card"><div class="card-head"><h3>All my tasks</h3><span class="hint">Most recent first</span></div><div class="card-body">' + W.taskCards(data.tasks || []) + "</div></div>" +
      "</div>" +
      '<div class="card mt-4"><div class="card-head"><h3>My hourly update history</h3></div>' + historyTable(data.history || []) + "</div>";
  }

  function load() {
    return Promise.all([
      API.get("/attendance/status"),
      API.get("/hourly-updates/today"),
      API.get("/tasks"),
      API.get("/hourly-updates", { limit: 100 })
    ]).then(function (res) {
      data = { status: res[0], hourly: res[1], tasks: (res[2].items || []).slice(0, 20), history: res[3].items || [] };
      render();
    }).catch(function (err) {
      ctx.page.innerHTML = '<div class="card">' + RG.errorState(err.message, "retry") + "</div>";
      var r = document.getElementById("retry"); if (r) r.addEventListener("click", load);
    });
  }

  W.wireAttendance(ctx.page, load);
  RG.on(ctx.page, "[data-hourly-open]", "click", function () { W.hourlyForm(RG.param("slot"), data.hourly, load); });
  RG.on(ctx.page, "[data-hourly-slot]", "click", function (e, b) { W.hourlyForm(b.dataset.hourlySlot, data.hourly, load); });
  RG.on(ctx.page, "[data-hourly-view], [data-open-update]", "click", function (e, b) {
    var id = b.dataset.hourlyView || b.dataset.openUpdate;
    var u = (data.history || []).concat((data.hourly || {}).updates || []).filter(function (x) { return String(x.id) === String(id); })[0];
    if (u) W.showUpdate(u);
  });
  document.addEventListener("rg:work-refresh", load);
  document.addEventListener("rg:hourly-submitted", load);
  ctx.page.innerHTML = RG.skeletonCards(3);
  load().then(function () {
    if (RG.param("slot") && data.hourly) W.hourlyForm(RG.param("slot"), data.hourly, load);
  });
})();
