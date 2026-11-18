/* audit.js - HR-only audit trail and the email log. Read-only by design. */
(function () {
  "use strict";
  var ctx = RG.boot({ scope: "hr", active: "audit", title: "Audit Logs", subtitle: "Who did what, when" });
  if (!ctx) return;

  var view = "audit";
  var state = { page: 1, page_size: 25, action: "", entity_type: "", search: "" };
  var emailState = { page: 1, page_size: 25 };

  ctx.page.innerHTML =
    '<div class="page-head"><div><h1>Audit logs</h1>' +
      '<p class="sub">Every sign-in, verification, salary change and email is recorded. Nothing here can be edited.</p></div></div>' +
    '<div class="card"><div class="tabs" id="tabs">' +
      '<button class="tab active" data-tab="audit">Activity</button>' +
      '<button class="tab" data-tab="email">Email log</button></div>' +
      '<div class="toolbar" id="toolbar">' +
        '<div class="search">' + RG.icon("search", 16) +
          '<input id="q" type="text" placeholder="Search actor or entity"></div>' +
        '<div class="filters"><select id="f-action"><option value="">All actions</option></select></div></div>' +
      '<div id="host">' + RG.skeletonRows(10) + "</div>" +
      '<div class="pager" id="pager"></div></div>';

  var host = document.getElementById("host");

  API.get("/audit-logs/actions").then(function (actions) {
    document.getElementById("f-action").innerHTML = '<option value="">All actions</option>' +
      actions.map(function (a) { return '<option value="' + RG.esc(a) + '">' + RG.esc(a) + "</option>"; }).join("");
  }).catch(function () { /* filter degrades */ });

  function metaSummary(meta) {
    if (!meta || typeof meta !== "object") return "\u2014";
    var keys = Object.keys(meta).slice(0, 3);
    if (!keys.length) return "\u2014";
    return keys.map(function (k) {
      var value = meta[k];
      if (value === null || value === undefined) value = "\u2014";
      if (typeof value === "object") value = JSON.stringify(value).slice(0, 40);
      return RG.esc(k.replace(/_/g, " ")) + ": " + RG.esc(String(value).slice(0, 48));
    }).join(" \u00B7 ");
  }

  function auditRow(log) {
    return "<tr>" +
      '<td data-label="When" class="nowrap small">' + RG.fmt.dateTime(log.created_at) + "</td>" +
      '<td data-label="Actor"><div>' + RG.esc(log.actor_email || "system") + "</div>" +
        '<div class="small muted">' + RG.esc(log.role_name || "") + "</div></td>" +
      '<td data-label="Action"><span class="chip">' + RG.esc(log.action) + "</span></td>" +
      '<td data-label="Entity">' + RG.esc(log.entity_type || "\u2014") +
        (log.entity_id ? ' <span class="small muted">#' + log.entity_id + "</span>" : "") + "</td>" +
      '<td data-label="Details" class="small muted">' + metaSummary(log.meta) + "</td>" +
      '<td data-label="IP" class="small muted nowrap">' + RG.esc(log.ip_address || "\u2014") + "</td>" +
      "</tr>";
  }

  function emailRow(log) {
    return "<tr>" +
      '<td data-label="When" class="nowrap small">' + RG.fmt.dateTime(log.created_at) + "</td>" +
      '<td data-label="To">' + RG.esc(log.to_email) + "</td>" +
      '<td data-label="Subject">' + RG.esc(log.subject) + "</td>" +
      '<td data-label="Template" class="small muted">' + RG.esc(log.template || "\u2014") + "</td>" +
      '<td data-label="Status">' + RG.badge(log.status === "sent" ? "Verified" : (log.status === "failed" ? "Rejected" : "Pending")) +
        ' <span class="small muted">' + RG.esc(log.status) + "</span></td>" +
      '<td data-label="Error" class="small muted">' + RG.esc(log.error || "\u2014") + "</td>" +
      "</tr>";
  }

  function loadAudit() {
    API.get("/audit-logs", state).then(function (data) {
      if (!data.items.length) {
        host.innerHTML = RG.emptyState("No matching activity", "Try a different action or search term.", "", "shield");
        document.getElementById("pager").innerHTML = "";
        return;
      }
      host.innerHTML = '<div class="table-scroll"><table class="data compact"><thead><tr>' +
        "<th>When</th><th>Actor</th><th>Action</th><th>Entity</th><th>Details</th><th>IP</th>" +
        "</tr></thead><tbody>" + data.items.map(auditRow).join("") + "</tbody></table></div>";
      RG.renderPager(document.getElementById("pager"), data.meta, function (p) { state.page = p; loadAudit(); });
    }).catch(function (err) {
      host.innerHTML = RG.errorState(err.message, "retry");
      var r = document.getElementById("retry"); if (r) r.addEventListener("click", loadAudit);
    });
  }

  function loadEmails() {
    API.get("/audit-logs/emails", emailState).then(function (rows) {
      var items = rows.items || rows;
      if (!items.length) {
        host.innerHTML = RG.emptyState("No emails logged yet",
          "Salary, document and account emails are recorded here \u2014 including when SMTP isn't configured.", "", "inbox");
        document.getElementById("pager").innerHTML = "";
        return;
      }
      host.innerHTML = '<div class="table-scroll"><table class="data compact"><thead><tr>' +
        "<th>When</th><th>To</th><th>Subject</th><th>Template</th><th>Status</th><th>Error</th>" +
        "</tr></thead><tbody>" + items.map(emailRow).join("") + "</tbody></table></div>";
      if (rows.meta) {
        RG.renderPager(document.getElementById("pager"), rows.meta, function (p) { emailState.page = p; loadEmails(); });
      } else {
        document.getElementById("pager").innerHTML = "";
      }
    }).catch(function (err) {
      host.innerHTML = RG.errorState(err.message, "retry");
      var r = document.getElementById("retry"); if (r) r.addEventListener("click", loadEmails);
    });
  }

  document.getElementById("tabs").addEventListener("click", function (e) {
    var tab = e.target.closest("[data-tab]");
    if (!tab) return;
    document.querySelectorAll("#tabs .tab").forEach(function (t) { t.classList.remove("active"); });
    tab.classList.add("active");
    view = tab.dataset.tab;
    document.getElementById("toolbar").style.display = view === "audit" ? "" : "none";
    host.innerHTML = RG.skeletonRows(8);
    if (view === "audit") loadAudit(); else loadEmails();
  });

  document.getElementById("q").addEventListener("input", RG.debounce(function (e) {
    state.search = e.target.value.trim(); state.page = 1; loadAudit();
  }));
  document.getElementById("f-action").addEventListener("change", function (e) {
    state.action = e.target.value; state.page = 1; loadAudit();
  });

  loadAudit();
})();
