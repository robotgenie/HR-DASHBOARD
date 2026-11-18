/* notifications.js - notification centre for both roles. */
(function () {
  "use strict";
  var SCOPE = document.body.dataset.scope;
  var ctx = RG.boot({
    scope: SCOPE, active: "notifications",
    title: "Notifications", subtitle: SCOPE === "hr" ? "Activity & alerts" : "Your updates"
  });
  if (!ctx) return;

  var state = { page: 1, page_size: 20, unread_only: false };

  ctx.page.innerHTML =
    '<div class="page-head"><div><h1>Notifications</h1>' +
      '<p class="sub">Documents, UAN, salary, meetings and reminders.</p></div>' +
      '<div class="page-actions">' +
        '<label class="switch"><input type="checkbox" id="only-unread"><span class="track"></span>' +
          '<span class="switch-text"><b>Unread only</b></span></label>' +
        '<button class="btn" data-readall>Mark all read</button>' +
        '<button class="btn" data-delread>' + RG.icon("trash", 15) + ' Delete read</button></div></div>' +
    '<div class="card"><div id="host">' + RG.skeletonRows(6) + "</div>" +
    '<div class="pager" id="pager"></div></div>';

  var host = document.getElementById("host");

  function load() {
    API.get("/notifications", state).then(function (data) {
      var items = data.items || [];
      if (!items.length) {
        host.innerHTML = RG.emptyState(
          state.unread_only ? "Nothing unread" : "No notifications yet",
          state.unread_only ? "You're all caught up." : "Updates will appear here as things happen.",
          "", "bell");
        document.getElementById("pager").innerHTML = "";
        RG.refreshUnread();
        return;
      }
      host.innerHTML = '<ul class="notif-list">' + items.map(RG.notificationRow).join("") + "</ul>";
      RG.wireNotificationRows(host, function (what) { if (what === "deleted") load(); });
      RG.renderPager(document.getElementById("pager"),
        { page: state.page, page_size: state.page_size, total: data.total,
          pages: Math.ceil(data.total / state.page_size) },
        function (p) { state.page = p; load(); });
      RG.refreshUnread();
    }).catch(function (err) {
      host.innerHTML = RG.errorState(err.message, "retry");
      var r = document.getElementById("retry"); if (r) r.addEventListener("click", load);
    });
  }

  document.getElementById("only-unread").addEventListener("change", function (e) {
    state.unread_only = e.target.checked; state.page = 1; load();
  });
  RG.on(ctx.page, "[data-readall]", "click", function (e, btn) {
    RG.setBusy(btn, true, "Marking\u2026");
    API.post("/notifications/read-all", {}).then(function () {
      RG.setBusy(btn, false); RG.toastOk("All notifications marked read."); load();
    }).catch(function (err) { RG.setBusy(btn, false); RG.toastErr(err); });
  });

  RG.on(ctx.page, "[data-delread]", "click", function (e, btn) {
    RG.confirmAction({ title: "Delete read notifications?", message: "All notifications you have already read will be removed. Unread ones stay.", confirmLabel: "Delete", danger: true })
      .then(function (ok) {
        if (!ok) return;
        RG.setBusy(btn, true, "Deleting\u2026");
        API.del("/notifications/read").then(function (res) {
          RG.setBusy(btn, false); RG.toastOk(res.detail); state.page = 1; load();
        }).catch(function (err) { RG.setBusy(btn, false); RG.toastErr(err); });
      });
  });

  load();
})();
