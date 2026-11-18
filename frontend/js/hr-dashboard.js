/* hr-dashboard.js - PEOPLE OPERATIONS WORKSPACE.
   A triage workspace instead of a dashboard:
     header (greeting + My day check-in pill)  |  lifecycle pipeline ribbon
     smart queues  |  unified stream of real pending items  |  detail pane
     floor + meetings + new joiners + insights (charts) + workflow shortcuts.
   Items come from the existing, hierarchy-scoped list endpoints (documents,
   leave awaiting HR, reports, UAN, ID approvals, profile change and payslip
   requests, salaries) plus late check-ins and hourly gaps from today's
   monitor. Decisions are still taken on the module pages - the workspace
   links straight to them. HR is an employee too: Check-In / Check-Out,
   reports and leave use the shared RGWork + RG.leaveModal flows. */
(function () {
  "use strict";
  var ctx = RG.boot({ scope: "hr", active: "dashboard", title: "People Operations", subtitle: "Your hierarchy" });
  if (!ctx) return;

  var TEAL = ["#0F6B66", "#4C9A8A", "#8FBFB2", "#C2410C", "#E0A458", "#7A8C85", "#B7C7C1"];
  var STATUS_COLOURS = {
    "Verified": "#0F6B66", "Pending": "#E0A458", "Rejected": "#C2410C", "Missing": "#D6CFC1",
    "Re-upload Requested": "#E07A5F", "Credited": "#0F6B66", "Processing": "#4C9A8A",
    "Submitted": "#4C9A8A", "Reviewed": "#0F6B66", "Draft": "#E0A458", "Not Submitted": "#D6CFC1"
  };
  var charts = {};
  var W = window.RGWork;

  /* Lifecycle stages and the queues inside them. */
  var STAGES = [
    { key: "onboarding", label: "Onboarding", icon: "user", queues: ["id", "profile"] },
    { key: "documents", label: "Documents", icon: "doc", queues: ["docs"] },
    { key: "attendance", label: "Attendance", icon: "clock", queues: ["late", "hourly"] },
    { key: "leave", label: "Leave", icon: "calendar", queues: ["leave"] },
    { key: "reports", label: "Work reports", icon: "clipboard", queues: ["reports"] },
    { key: "payroll", label: "Payroll", icon: "money", queues: ["uan", "salary", "payslip"] }
  ];
  var QUEUES = {
    id: { open: "Open ID Approvals", label: "ID approvals", href: "id-approvals.html", verb: "Approve or reject ID card" },
    profile: { open: "Open Profile Requests", label: "Profile change requests", href: "profile-requests.html", verb: "Review a locked-field change" },
    docs: { open: "Open Documents", label: "Documents to verify", href: "documents.html", verb: "Verify document" },
    late: { open: "Open Work Monitor", label: "Late check-ins today", href: "work-monitor.html", verb: "Late check-in" },
    hourly: { open: "Open hourly monitor", label: "Hourly updates due / missed", href: "work-monitor.html?tab=hourly", verb: "Hourly updates missing" },
    leave: { open: "Open Leave Requests", label: "Leave awaiting you", href: "leave-requests.html", verb: "Decide leave request" },
    reports: { open: "Open Work Reports", label: "Reports to review", href: "work-reports.html", verb: "Review work report" },
    uan: { open: "Open UAN", label: "UAN verification", href: "uan.html", verb: "Verify UAN" },
    salary: { open: "Open Salary", label: "Salaries not credited", href: "salary.html", verb: "Credit salary" },
    payslip: { open: "Open Payslip Requests", label: "Payslip download requests", href: "payslip-requests.html", verb: "Decide payslip request" }
  };
  var S = { items: {}, totals: {}, filter: "all", q: "", sort: "oldest", selected: null, dash: null, today: null, person: {} };

  function greeting() { var h = new Date().getHours(); return h < 12 ? "Good morning" : (h < 17 ? "Good afternoon" : "Good evening"); }

  /* ================================ layout ================================ */
  function shell() {
    ctx.page.innerHTML =
      '<div class="tw">' +
      '<header class="tw-head"><div class="tw-hello">' +
          '<div class="tw-date">' + RG.esc(new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long" })) + "</div>" +
          "<h1>" + greeting() + ", " + RG.esc((ctx.user.full_name || "").split(" ")[0]) + '.</h1><p id="tw-summary">Collecting your open people work…</p></div>' +
        '<div class="tw-head-r"><div class="myday" id="my-day"><div class="skeleton" style="height:52px;width:320px;border-radius:12px"></div></div>' +
          '<div class="tw-actions"><a class="btn" href="meetings.html">' + RG.icon("video", 15) + " Schedule meeting</a>" +
          '<a class="btn btn-brand" href="employees.html?new=1">' + RG.icon("plus", 15) + " Add employee</a></div></div>" +
      "</header>" +
      '<nav class="tw-pipe" id="pipe" aria-label="Lifecycle pipeline"></nav>' +
      '<div class="tw-panes">' +
        '<aside class="tw-queues" aria-label="Queues"><label class="tw-search">' + RG.icon("search", 16) +
          '<input type="search" id="tw-q" placeholder="Filter by name, ID or department" aria-label="Filter items"></label>' +
          '<div id="queues">' + RG.skeletonRows(6) + "</div></aside>" +
        '<section class="tw-stream" aria-label="Items"><header><h2 id="stream-title">All open items</h2>' +
          '<label class="tw-sort">Sort <select id="tw-sort"><option value="oldest">Oldest first</option><option value="newest">Newest first</option><option value="name">Name</option></select></label></header>' +
          '<div id="stream" aria-labelledby="stream-title" tabindex="0">' + RG.skeletonRows(6) + "</div></section>" +
        '<section class="tw-detail" id="detail" aria-live="polite" aria-label="Selected item">' +
          '<div class="tw-detail-empty">' + RG.icon("inbox", 22) + "<p>Select an item to see the person and what is needed.</p></div></section>" +
      "</div>" +
      '<div class="tw-under">' +
        '<section class="tw-card"><header><h3>' + RG.icon("clock", 15) + ' Today on the floor</h3><a href="work-monitor.html">Work monitor</a></header><div id="work-today">' + RG.skeletonRows(2) + "</div></section>" +
        '<section class="tw-card"><header><h3>' + RG.icon("video", 15) + ' Today’s meetings</h3><a href="meetings.html">Manage</a></header><div id="meetings">' + RG.skeletonRows(2) + "</div></section>" +
        '<section class="tw-card"><header><h3>' + RG.icon("users", 15) + ' New &amp; recent people</h3><a href="employees.html">Employees</a></header><div id="recent">' + RG.skeletonRows(3) + "</div></section>" +
      "</div>" +
      '<div class="tw-under two">' +
        '<section class="tw-card insights"><header><h3>' + RG.icon("pulse", 15) + " Insights</h3><span class=\"muted small\">Your hierarchy</span></header>" +
          '<div class="tw-tabs" role="tablist" aria-label="Insights">' + tab("dept", "Headcount", true) + tab("docs", "Documents") + tab("salary", "Salary") + tab("reports", "Reports") + "</div>" +
          tabPanel("dept", "c-dept", true) + tabPanel("docs", "c-docs") + tabPanel("salary", "c-salary") + tabPanel("reports", "c-reports") + "</section>" +
        '<section class="tw-card"><header><h3>' + RG.icon("layers", 15) + " HR workflows</h3></header>" + workflows() + "</section>" +
      "</div></div>";
  }
  function tab(key, label, on) {
    return '<button role="tab" id="t-' + key + '" aria-controls="p-' + key + '" aria-selected="' + (on ? "true" : "false") + '" tabindex="' + (on ? "0" : "-1") + '" data-tab="' + key + '">' + label + "</button>";
  }
  function tabPanel(key, canvas, on) {
    return '<div class="tw-tabpanel" role="tabpanel" id="p-' + key + '" aria-labelledby="t-' + key + '"' + (on ? "" : " hidden") + ">" +
      '<div class="chart-wrap"><canvas id="' + canvas + '" role="img" aria-label="' + key + ' chart"></canvas></div><p class="insight" id="i-' + key + '"></p></div>';
  }
  function workflows() {
    var g = [
      ["Onboard", [["employees.html?new=1", "plus", "Add employee"], ["employees.html", "users", "Employees"], ["employees.html?employee_type=Intern", "badge", "Interns"], ["hierarchy.html", "tree", "My Hierarchy"]]],
      ["Verify", [["documents.html", "doc", "Documents"], ["id-approvals.html", "badge", "ID Approvals"], ["uan.html", "badge", "UAN"], ["profile-requests.html", "user", "Profile requests"]]],
      ["Run the day", [["work-monitor.html", "calendar", "Attendance"], ["work-monitor.html?tab=tasks", "clipboard", "Tasks"], ["work-monitor.html?tab=hourly", "bell", "Hourly updates"], ["leave-requests.html", "calendar", "Leave"]]],
      ["Review & pay", [["work-reports.html", "clipboard", "Noon & EOD reports"], ["monthly-reports.html", "dashboard", "Monthly reports"], ["salary.html", "money", "Salary"], ["payslip-requests.html", "download", "Payslip requests"], ["excel.html", "upload", "Excel"], ["notifications.html", "bell", "Notifications"]]]
    ];
    return '<div class="wf-cols">' + g.map(function (x) {
      return '<div><h4>' + x[0] + "</h4><ul>" + x[1].map(function (l) { return '<li><a href="' + l[0] + '">' + RG.icon(l[1], 14) + RG.esc(l[2]) + "</a></li>"; }).join("") + "</ul></div>";
    }).join("") + "</div>";
  }

  /* ================================ data -> items ================================ */
  function item(queue, id, person, title, sub, since, data) {
    return { key: queue + ":" + id, queue: queue, person: person, title: title, sub: sub, since: since, data: data };
  }
  var LOADERS = {
    docs: function () { return API.get("/documents", { status: "Pending", page: 1, page_size: 50 }).then(function (r) {
      return [r, r.items.map(function (d) { return item("docs", d.document_id, { id: d.employee_id, name: d.employee_name, code: d.employee_code, dept: d.department }, d.document_type, "Uploaded " + RG.fmt.ago(d.uploaded_at) + " · v" + d.version_count, d.uploaded_at, d); })]; }); },
    leave: function () { return API.get("/leave-requests", { status: "Pending", awaiting_me: true, page: 1, page_size: 50 }).then(function (r) {
      return [r, r.items.map(function (l) { return item("leave", l.id, { id: l.employee_id, name: l.employee_name, code: l.employee_code, dept: l.department }, (l.leave_type_label || l.leave_type) + " · " + (l.leave_period_label || l.leave_period || ""), RG.fmt.date(l.from_date) + (l.to_date !== l.from_date ? " – " + RG.fmt.date(l.to_date) : ""), l.requested_at, l); })]; }); },
    reports: function () { return API.get("/reports", { status: "Submitted", page: 1, page_size: 50 }).then(function (r) {
      return [r, r.items.map(function (x) { return item("reports", x.id, { id: x.employee_id, name: x.employee_name, code: x.employee_code, dept: x.department }, x.report_type + " report · " + RG.fmt.date(x.report_date), (x.attachments || []).length + " attachment(s)", x.submitted_at, x); })]; }); },
    uan: function () { return Promise.all([API.get("/uan", { status: "Submitted", page: 1, page_size: 50 }), API.get("/uan", { status: "Under Verification", page: 1, page_size: 50 }).catch(function () { return { items: [], meta: { total: 0 } }; })]).then(function (rs) {
      var items = rs[0].items.concat(rs[1].items);
      return [{ meta: { total: ((rs[0].meta || {}).total || 0) + ((rs[1].meta || {}).total || 0) } }, items.map(function (u) { return item("uan", u.id, { id: u.employee_id, name: u.employee_name, code: u.employee_code, dept: u.department }, "UAN " + (u.uan_number || ""), u.status, u.submitted_at, u); })]; }); },
    id: function () { return API.get("/employees/id-approval-requests", { status: "Pending", page: 1, page_size: 50 }).then(function (r) {
      return [r, r.items.map(function (e) { return item("id", e.id, { id: e.id, name: e.full_name, code: e.display_employee_id || e.employee_code, dept: e.department }, "Employee ID card", (e.designation || "") + " · profile " + Math.round(e.profile_completion || 0) + "%", e.id_card_requested_at || e.created_at, e); })]; }); },
    profile: function () { return API.get("/profile-change-requests", { status: "Pending", page: 1, page_size: 50 }).then(function (r) {
      return [r, r.items.map(function (p) { return item("profile", p.id, { id: p.employee_id, name: p.employee_name, code: p.employee_display_id, dept: p.department }, "Change " + (p.field_label || p.field_name), "From “" + (p.old_value || "—") + "”", p.requested_at || p.created_at, p); })]; }); },
    payslip: function () { return API.get("/payslip-download-requests", { status: "Pending", page: 1, page_size: 50 }).then(function (r) {
      return [r, r.items.map(function (p) { return item("payslip", p.id, { id: p.employee_id, name: p.employee_name, code: p.employee_display_id, dept: p.department }, "Payslip download · " + (p.period_label || ""), p.reason || "", p.requested_at || p.created_at, p); })]; }); },
    salary: function () { return API.get("/salaries", { status: "Pending", page: 1, page_size: 50 }).then(function (r) {
      return [r, r.items.map(function (s) { return item("salary", s.id, { id: s.employee_id, name: s.employee_name, code: s.employee_code, dept: s.department }, s.period_label + " salary", RG.fmt.money(s.net_pay) + " net · " + s.working_days + " days", null, s); })]; }); }
  };
  function loadQueues() {
    Object.keys(LOADERS).forEach(function (k) {
      LOADERS[k]().then(function (res) {
        S.items[k] = res[1];
        S.totals[k] = (res[0].meta && res[0].meta.total) || res[1].length;
      }).catch(function () { S.items[k] = []; S.totals[k] = 0; S.failed = (S.failed || []).concat(k); })
        .then(renderAll);
    });
  }
  function todayItems() {
    var d = S.dash, t = S.today;
    S.items.late = d ? (d.late_logins_today || []).map(function (r) {
      return item("late", r.employee_id + "-" + r.date, { id: r.employee_id, name: r.employee_name, code: r.employee_code, dept: r.department },
        "Late by " + r.late_label, "Expected " + RG.fmt.time(r.expected_login) + " · actual " + RG.fmt.time(r.actual_login), null, r);
    }) : S.items.late;
    S.totals.late = S.items.late ? S.items.late.length : undefined;
    S.items.hourly = t ? (t.items || []).filter(function (r) { return r.hourly_missing > 0; }).map(function (r) {
      return item("hourly", r.employee_id, { id: r.employee_id, name: r.employee_name, code: r.employee_code, dept: r.department },
        r.hourly_missing + " hourly update" + (r.hourly_missing === 1 ? "" : "s") + " due or missed", r.hourly_submitted + " of " + r.hourly_applicable + " submitted today", null, r);
    }) : S.items.hourly;
    S.totals.hourly = S.items.hourly ? S.items.hourly.length : undefined;
  }

  /* ================================ rendering ================================ */
  function count(q) { return S.totals[q]; }
  function stageCount(st) { return st.queues.reduce(function (s, q) { return s + (count(q) || 0); }, 0); }
  function renderAll() { todayItems(); renderPipe(); renderQueues(); renderStream(); renderSummary(); }

  function renderSummary() {
    var actionable = ["id", "profile", "docs", "leave", "reports", "uan", "salary", "payslip"];
    var total = actionable.reduce(function (s, q) { return s + (count(q) || 0); }, 0);
    var busiest = STAGES.slice().sort(function (a, b) { return stageCount(b) - stageCount(a); })[0];
    document.getElementById("tw-summary").innerHTML = total
      ? "<b>" + total + " open item" + (total === 1 ? "" : "s") + "</b> across your hierarchy. Most of it is in <b>" + RG.esc(busiest.label.toLowerCase()) + "</b>."
      : "Nothing is waiting on you. Your hierarchy is up to date.";
  }
  function renderPipe() {
    document.getElementById("pipe").innerHTML = '<button type="button" class="pipe-all' + (S.filter === "all" ? " on" : "") + '" data-filter="all"><span>All</span><b>' +
      STAGES.reduce(function (s, st) { return s + stageCount(st); }, 0) + "</b></button>" +
      STAGES.map(function (st, i) {
        var n = stageCount(st), on = S.filter === "stage:" + st.key;
        return '<button type="button" class="pipe-stage' + (on ? " on" : "") + (n ? " has" : "") + '" data-filter="stage:' + st.key + '" aria-pressed="' + on + '">' +
          '<span class="ps-i">' + RG.icon(st.icon, 16) + '</span><span class="ps-t"><em>' + (i + 1) + "</em>" + st.label + '</span><b>' + n + "</b></button>";
      }).join("");
  }
  function renderQueues() {
    document.getElementById("queues").innerHTML = '<ul class="q-list">' +
      '<li><button type="button" data-filter="all" class="' + (S.filter === "all" ? "on" : "") + '">' + RG.icon("inbox", 15) + "<span>All open items</span><b>" +
        Object.keys(QUEUES).reduce(function (s, q) { return s + (count(q) || 0); }, 0) + "</b></button></li>" +
      STAGES.map(function (st) {
        return '<li class="q-group">' + RG.esc(st.label) + "</li>" + st.queues.map(function (q) {
          var n = count(q);
          return '<li><button type="button" data-filter="queue:' + q + '" class="' + (S.filter === "queue:" + q ? "on" : "") + (n ? "" : " zero") + '" aria-pressed="' + (S.filter === "queue:" + q) + '">' +
            "<span>" + QUEUES[q].label + "</span><b>" + (n === undefined ? "…" : n) + "</b></button></li>";
        }).join("");
      }).join("") + "</ul>";
  }
  function visible() {
    var list = [];
    var queues = S.filter === "all" ? Object.keys(QUEUES)
      : S.filter.indexOf("stage:") === 0 ? STAGES.filter(function (s) { return "stage:" + s.key === S.filter; })[0].queues
      : [S.filter.slice(6)];
    queues.forEach(function (q) { (S.items[q] || []).forEach(function (it) { list.push(it); }); });
    var q = S.q.toLowerCase();
    if (q) list = list.filter(function (it) { return ((it.person.name || "") + " " + (it.person.code || "") + " " + (it.person.dept || "") + " " + it.title).toLowerCase().indexOf(q) >= 0; });
    list.sort(function (a, b) {
      if (S.sort === "name") return String(a.person.name).localeCompare(String(b.person.name));
      var x = a.since ? String(a.since) : "9", y = b.since ? String(b.since) : "9";
      return S.sort === "oldest" ? (x < y ? -1 : x > y ? 1 : 0) : (x > y ? -1 : x < y ? 1 : 0);
    });
    return list;
  }
  function ageDays(since) {
    if (!since) return null;
    var d = new Date(String(since).length === 10 ? since + "T00:00:00" : (/Z|[+-]\d{2}:?\d{2}$/.test(since) ? since : since + "Z"));
    return isNaN(d) ? null : Math.floor((Date.now() - d.getTime()) / 86400000);
  }
  function renderStream() {
    var host = document.getElementById("stream");
    var title = S.filter === "all" ? "All open items" : S.filter.indexOf("stage:") === 0 ? STAGES.filter(function (s) { return "stage:" + s.key === S.filter; })[0].label : QUEUES[S.filter.slice(6)].label;
    document.getElementById("stream-title").textContent = title;
    var loading = Object.keys(LOADERS).some(function (k) { return S.items[k] === undefined; });
    var list = visible();
    if (!list.length) {
      host.innerHTML = loading ? RG.skeletonRows(5) : RG.emptyState(S.q ? "No matches" : "All clear here", S.q ? "Try a different name, ID or department." : "Nothing in this queue needs you right now.", "", "check");
      return;
    }
    var stageOf = {}; STAGES.forEach(function (s) { s.queues.forEach(function (q) { stageOf[q] = s.label; }); });
    host.innerHTML = '<ul class="items">' + list.map(function (it) {
      var age = ageDays(it.since), old = age !== null && age >= 3;
      return '<li><button type="button" class="it' + (S.selected === it.key ? " on" : "") + '" aria-pressed="' + (S.selected === it.key) + '" data-item="' + RG.esc(it.key) + '">' +
        RG.avatar({ full_name: it.person.name }, "sm") +
        '<span class="it-main"><span class="it-who"><b>' + RG.esc(it.person.name || "") + "</b><em>" + RG.esc(it.person.dept || "") + "</em></span>" +
          '<span class="it-what">' + RG.esc(it.title) + "</span><span class=\"it-sub\">" + RG.esc(it.sub || "") + "</span></span>" +
        '<span class="it-side"><span class="it-q">' + RG.esc(stageOf[it.queue]) + "</span>" +
          (age !== null ? '<span class="it-age' + (old ? " old" : "") + '">' + (age === 0 ? "today" : age + "d") + "</span>" : '<span class="it-age">now</span>') + "</span></button></li>";
    }).join("") + "</ul>" +
      (S.filter.indexOf("queue:") === 0 && count(S.filter.slice(6)) > list.length && !S.q
        ? '<a class="it-more" href="' + QUEUES[S.filter.slice(6)].href + '">Showing ' + list.length + " of " + count(S.filter.slice(6)) + " — open the full queue</a>" : "");
    // Wide screens open with the oldest item ready in the detail pane.
    if (!S.selected && !loading && window.matchMedia("(min-width: 1101px)").matches) {
      var first = host.querySelector("[data-item]");
      S.selected = list[0].key;
      first.classList.add("on");
      first.setAttribute("aria-pressed", "true");
      renderDetail(list[0]);
    }
  }

  /* ================================ detail pane ================================ */
  function find(key) {
    var q = key.split(":")[0];
    return (S.items[q] || []).filter(function (it) { return it.key === key; })[0];
  }
  function renderDetail(it) {
    var host = document.getElementById("detail");
    if (!it) { host.innerHTML = '<div class="tw-detail-empty">' + RG.icon("inbox", 22) + "<p>Select an item to see the person and what is needed.</p></div>"; return; }
    var Q = QUEUES[it.queue], d = it.data, rows = [];
    function row(k, v) { if (v !== undefined && v !== null && v !== "") rows.push("<div><dt>" + k + "</dt><dd>" + v + "</dd></div>"); }
    var extra = "", preview = "";
    if (it.queue === "docs") { row("Document", RG.esc(d.document_type)); row("File", RG.esc(d.original_filename || "—")); row("Uploaded", RG.fmt.dateTime(d.uploaded_at)); row("Versions", d.version_count); row("Status", RG.badge(d.status));
      preview = '<button type="button" class="btn btn-sm" data-preview="' + d.document_id + '">' + RG.icon("eye", 14) + " Preview file</button>"; }
    if (it.queue === "leave") { row("Leave type", RG.esc(d.leave_type_label || d.leave_type)); row("Dates", RG.esc(RG.fmt.date(d.from_date) + (d.to_date !== d.from_date ? " – " + RG.fmt.date(d.to_date) : ""))); row("Period", RG.esc(d.leave_period_label || d.leave_period)); row("Duration", d.duration_days + " day(s)"); row("Paid", d.is_paid === false ? RG.badge("Unpaid", "bad") : RG.badge("Paid", "ok")); row("Stage", RG.esc(RG.stageText(d))); if (d.manager_status) row("Manager", RG.esc(d.manager_status + (d.manager_reviewed_by_name ? " · " + d.manager_reviewed_by_name : "")));
      extra = d.reason ? '<blockquote class="tw-quote">' + RG.esc(d.reason) + "</blockquote>" : ""; }
    if (it.queue === "reports") { row("Report", RG.esc(d.report_type + " · " + RG.fmt.date(d.report_date))); row("Submitted", RG.fmt.dateTime(d.submitted_at)); row("Attachments", (d.attachments || []).length); row("Status", RG.badge(d.status));
      extra = (d.work_summary || d.tasks_completed) ? '<div class="tw-excerpt"><h4>Work summary</h4><p>' + RG.esc((d.work_summary || d.tasks_completed || "").slice(0, 420)) + "</p></div>" : ""; }
    if (it.queue === "uan") { row("UAN", '<span class="mono">' + RG.esc(d.uan_number || "—") + "</span>"); row("Status", RG.badge(d.status)); row("Submitted", RG.fmt.dateTime(d.submitted_at)); }
    if (it.queue === "id") { row("Designation", RG.esc(d.designation)); row("Profile", Math.round(d.profile_completion || 0) + "% complete"); row("Documents", RG.esc(d.document_label || "")); row("Requested", RG.fmt.dateTime(d.id_card_requested_at)); row("Joined", RG.fmt.date(d.joining_date)); }
    if (it.queue === "profile") { row("Field", RG.esc(d.field_label || d.field_name)); row("Current", RG.esc(d.old_value || "—")); row("Requested", "<b>" + RG.esc(d.new_value || "—") + "</b>"); row("Asked", RG.fmt.dateTime(d.requested_at || d.created_at));
      extra = d.reason ? '<blockquote class="tw-quote">' + RG.esc(d.reason) + "</blockquote>" : ""; }
    if (it.queue === "payslip") { row("Period", RG.esc(d.period_label)); row("Net pay", RG.fmt.money(d.net_pay)); row("Payslip", d.has_payslip ? "Published" : "Not yet published"); row("Requested", RG.fmt.dateTime(d.requested_at || d.created_at));
      extra = d.reason ? '<blockquote class="tw-quote">' + RG.esc(d.reason) + "</blockquote>" : ""; }
    if (it.queue === "salary") { row("Period", RG.esc(d.period_label)); row("Earnings", RG.fmt.money(d.total_earnings)); row("Deductions", RG.fmt.money(d.total_deductions)); row("Net pay", "<b>" + RG.fmt.money(d.net_pay) + "</b>"); row("Worked days", d.working_days); row("Status", RG.badge(d.status)); }
    if (it.queue === "late") { row("Date", RG.fmt.date(d.date)); row("Expected login", RG.fmt.time(d.expected_login)); row("Actual login", RG.fmt.time(d.actual_login)); row("Late by", '<b style="color:var(--attention)">' + RG.esc(d.late_label) + "</b>");
      extra = '<blockquote class="tw-quote">' + RG.esc(d.late_reason || "No reason given") + "</blockquote>"; }
    if (it.queue === "hourly") { var s = d.session; row("Checked in", s ? RG.fmt.time(s.check_in_time) : "—"); row("Hourly", d.hourly_submitted + " of " + d.hourly_applicable + " submitted"); row("Due / missed", "<b style=\"color:var(--attention)\">" + d.hourly_missing + "</b>"); row("Noon report", RG.badge(d.noon_report)); row("EOD report", RG.badge(d.eod_report)); row("Manager", RG.esc(d.reporting_manager || "—")); }

    var p = it.person;
    host.innerHTML = '<div class="dt-top"><span class="dt-q">' + RG.esc(Q.verb) + "</span>" +
        '<div class="dt-who">' + RG.avatar({ full_name: p.name }, "lg") + "<div><h3>" + RG.esc(p.name || "") + "</h3><span>" + RG.esc([p.code, p.dept].filter(Boolean).join(" · ")) + "</span></div></div></div>" +
      '<dl class="dt-dl">' + rows.join("") + "</dl>" + extra +
      '<div class="dt-actions"><a class="btn btn-brand" href="' + Q.href + '">' + RG.icon("arrow", 14) + " " + RG.esc(Q.open) + "</a>" +
        preview + '<a class="btn btn-sm" href="employee-details.html?id=' + p.id + '">' + RG.icon("user", 14) + " Employee profile</a></div>" +
      '<details class="dt-more" data-person="' + p.id + '"><summary>' + RG.icon("chevron", 14) + " More about " + RG.esc((p.name || "").split(" ")[0]) + "</summary><div class=\"dt-person\">Loading…</div></details>";
  }
  function loadPerson(details) {
    var id = details.dataset.person, box = details.querySelector(".dt-person");
    if (S.person[id]) { box.innerHTML = S.person[id]; return; }
    API.get("/employees/" + id).then(function (e) {
      var chain = (e.reporting_chain || []).map(function (c) { return RG.esc(c.name || c.full_name || "") + (c.level ? ' <span class="muted">(' + RG.esc(c.level) + ")</span>" : ""); }).join(" → ");
      var html = '<dl class="dt-dl small">' +
        "<div><dt>Role</dt><dd>" + RG.esc(e.designation || "") + (e.is_intern ? " · Intern" : "") + "</dd></div>" +
        "<div><dt>Joined</dt><dd>" + RG.fmt.date(e.joining_date) + "</dd></div>" +
        "<div><dt>Email</dt><dd>" + RG.esc(e.email || "—") + "</dd></div>" +
        "<div><dt>Phone</dt><dd>" + RG.esc(e.phone || "—") + "</dd></div>" +
        "<div><dt>Status</dt><dd>" + RG.badge(e.employment_status) + "</dd></div>" +
        "<div><dt>Profile</dt><dd>" + Math.round(e.profile_completion || 0) + "%</dd></div>" +
        "<div><dt>Documents</dt><dd>" + RG.esc(e.document_label || "—") + "</dd></div>" +
        "<div><dt>UAN</dt><dd>" + RG.badge(e.uan_status || "Not Submitted") + "</dd></div>" +
        "<div><dt>ID card</dt><dd>" + RG.badge(e.id_card_status) + "</dd></div>" +
        (chain ? '<div class="full"><dt>Reporting line</dt><dd>' + chain + "</dd></div>" : "") + "</dl>";
      S.person[id] = html; box.innerHTML = html;
    }).catch(function (err) { box.innerHTML = '<p class="small muted">' + RG.esc(err.message) + "</p>"; });
  }

  /* ================================ interactions ================================ */
  function select(key) {
    S.selected = key;
    ctx.page.querySelectorAll("[data-item]").forEach(function (b) {
      var on = b.dataset.item === key; b.classList.toggle("on", on); b.setAttribute("aria-pressed", on);
    });
    renderDetail(find(key));
    if (window.matchMedia("(max-width: 1100px)").matches) document.getElementById("detail").scrollIntoView({ behavior: "smooth", block: "start" });
  }
  RG.on(ctx.page, "[data-filter]", "click", function (e, b) { S.filter = b.dataset.filter; renderPipe(); renderQueues(); renderStream(); });
  RG.on(ctx.page, "[data-item]", "click", function (e, b) { select(b.dataset.item); });
  RG.on(ctx.page, "#stream", "keydown", function (e) {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    var btns = Array.prototype.slice.call(ctx.page.querySelectorAll("[data-item]"));
    if (!btns.length) return;
    e.preventDefault();
    var i = btns.findIndex(function (b) { return b.dataset.item === S.selected; });
    var next = btns[Math.max(0, Math.min(btns.length - 1, i + (e.key === "ArrowDown" ? 1 : -1)))];
    select(next.dataset.item); next.focus();
  });
  RG.on(ctx.page, "#tw-q", "input", RG.debounce(function (e) { S.q = e.target.value.trim(); renderStream(); }, 180));
  RG.on(ctx.page, "#tw-sort", "change", function (e) { S.sort = e.target.value; renderStream(); });
  ctx.page.addEventListener("toggle", function (e) { if (e.target.matches && e.target.matches("details.dt-more") && e.target.open) loadPerson(e.target); }, true);
  RG.on(ctx.page, "[data-preview]", "click", function (e, b) {
    RG.setBusy(b, true, "Opening…");
    API.blob("/documents/" + b.dataset.preview + "/download").then(function (f) { RG.setBusy(b, false); window.open(f.url, "_blank"); })
      .catch(function (err) { RG.setBusy(b, false); RG.toastErr(err); });
  });

  /* ================================ My day (HR as employee) ================================ */
  function renderMyDay() {
    var host = document.getElementById("my-day");
    if (!host || !W) return;
    Promise.all([
      API.get("/attendance/status").catch(function () { return null; }),
      API.get("/leave-requests/me", { page: 1, page_size: 5 }).catch(function () { return { items: [] }; }),
      API.get("/hierarchy/me").catch(function () { return null; })
    ]).then(function (res) {
      var st = res[0], leaves = (res[1] && res[1].items) || [], line = res[2];
      if (!st || !st.applicable) { host.innerHTML = ""; return; }
      var s = st.session, state = st.state;
      var pending = leaves.filter(function (l) { return l.status === "Pending"; });
      var rep = st.reports || {};
      var wasOpen = host.querySelector("details[open]") !== null;
      host.innerHTML = '<div class="md-bar"><details class="md"' + (wasOpen ? " open" : "") + '><summary aria-label="My day details">' +
          '<span class="md-dot is-' + state + '"></span><span class="md-t"><b>' + (state === "checked_in" ? "Checked in" : state === "checked_out" ? "Checked out" : "Not checked in") + "</b>" +
          "<em>" + (s ? W.t12(s.check_in_time) + " · " + W.mins(s.worked_minutes) : "My day") + "</em></span>" +
          '<span class="md-more" aria-hidden="true">' + RG.icon("down", 14) + "</span></summary>" +
        '<div class="md-pop">' + W.attendanceCard(st) +
          '<ul class="status-list">' +
            "<li><span><b>Noon Report</b><small>" + (rep.noon_required ? "Available from 1:00 PM" : RG.esc(rep.noon_blocked_reason || "")) + "</small></span>" +
              RG.badge(!rep.noon_required ? "Not Required" : (rep.noon_submitted ? "Submitted" : "Pending")) + "</li>" +
            "<li><span><b>EOD Report</b><small>" + (rep.eod_required ? "Available from 6:00 PM" : RG.esc(rep.eod_blocked_reason || "")) + "</small></span>" +
              RG.badge(!rep.eod_required ? "Not Required" : (rep.eod_submitted ? "Submitted" : "Pending")) + "</li>" +
            "<li><span><b>My leave requests</b><small>" + (pending.length ? "Decided by the Admin" : "None pending") + "</small></span>" +
              (pending.length ? RG.badge(pending.length + " pending", "warn") : RG.badge("Clear", "ok")) + "</li>" +
            (line && line.direct_reports ? "<li><span><b>Managers reporting to you</b><small>" + RG.esc(line.direct_reports.map(function (m) { return m.full_name; }).join(", ") || "None yet") + "</small></span>" +
              RG.badge(String(line.direct_reports.length)) + "</li>" : "") +
          "</ul>" +
          '<div class="row wrap mt-3"><button class="btn btn-sm" data-request-leave>Request leave</button><a class="btn btn-sm" href="my-reports.html">My reports</a><a class="btn btn-sm" href="my-work.html">My tasks &amp; hourly</a><a class="btn btn-sm" href="my-monthly-report.html">My monthly report</a></div>' +
        "</div></details>" +
        '<span class="md-btns"><button type="button" class="btn btn-sm btn-brand" data-check-in' + (st.can_check_in ? "" : " disabled") + ">Check-In</button>" +
          '<button type="button" class="btn btn-sm" data-check-out' + (state === "checked_in" ? "" : " disabled") + ">Check-Out</button></span>" + "</div>";
    });
  }
  RG.on(ctx.page, "[data-request-leave]", "click", function () { RG.leaveModal(renderMyDay); });
  if (W) W.wireAttendance(ctx.page, renderMyDay);
  document.addEventListener("click", function (e) {
    var md = ctx.page.querySelector("details.md[open]");
    if (md && !md.contains(e.target) && !e.target.closest(".modal-backdrop, .selfie-backdrop, #toasts")) md.open = false;
  });

  /* ================================ under the panes ================================ */
  function renderWorkToday(d) {
    S.today = d;
    var t = d.totals, pct = t.employees ? Math.round(t.checked_in * 100 / t.employees) : 0;
    document.getElementById("work-today").innerHTML = '<div class="floor"><div class="fl-big"><b>' + t.checked_in + "</b><span>/ " + t.employees + " checked in</span></div>" +
      '<div class="bar"><span style="width:' + pct + '%"></span></div>' +
      '<dl class="fl-grid"><div><dt>Checked out</dt><dd>' + t.checked_out + "</dd></div><div><dt>Late</dt><dd>" + t.late + "</dd></div><div><dt>On leave</dt><dd>" + t.on_leave + "</dd></div>" +
      "<div><dt>Hourly in</dt><dd>" + t.hourly_submitted + "</dd></div><div><dt>Hourly due</dt><dd>" + t.hourly_due + "</dd></div><div><dt>Open tasks</dt><dd>" + t.open_tasks + "</dd></div></dl></div>";
    renderAll();
  }
  function renderMeetings(rows) {
    var host = document.getElementById("meetings");
    if (!rows.length) { host.innerHTML = RG.emptyState("No meetings today", "Schedule one for a department.", '<a class="btn btn-sm" href="meetings.html">Schedule</a>', "calendar"); return; }
    host.innerHTML = '<ul class="mini-list">' + rows.map(function (m) {
      return '<li><div style="min-width:0"><div class="small strong" style="color:#0F6B66">' + RG.fmt.time(m.start_time) + "</div>" +
        '<div class="truncate" style="font-weight:600">' + RG.esc(m.title) + '</div><div class="small muted">' + RG.esc(m.department || "") + "</div></div>" +
        (m.google_meet_url && m.status !== "Cancelled" ? '<a class="btn btn-sm meet-btn when" target="_blank" rel="noopener" href="' + RG.esc(m.google_meet_url) + '">Join</a>' : '<span class="when">' + RG.badge(m.status) + "</span>") + "</li>";
    }).join("") + "</ul>";
  }
  function renderRecent(rows) {
    var host = document.getElementById("recent");
    if (!rows.length) { host.innerHTML = RG.emptyState("No employees yet", "Add your first employee to get started."); return; }
    host.innerHTML = '<ul class="mini-list">' + rows.map(function (e) {
      return "<li>" + RG.avatar(e, "sm") + '<div style="min-width:0"><a class="truncate" style="font-weight:600;display:block;color:var(--text)" href="employee-details.html?id=' + e.id + '">' + RG.esc(e.full_name) + "</a>" +
        '<div class="small muted truncate">' + RG.esc(e.designation) + " · " + RG.esc(e.department || "—") + '</div></div><span class="when">' + RG.fmt.date(e.joining_date) + "</span></li>";
    }).join("") + "</ul>";
    RG.hydratePhotos(host);
  }

  /* ---------------- insights (Chart.js, existing data) ---------------- */
  var chartJobs = {};
  function showTab(key) {
    ctx.page.querySelectorAll("[data-tab]").forEach(function (b) {
      var on = b.dataset.tab === key;
      b.setAttribute("aria-selected", on ? "true" : "false"); b.tabIndex = on ? 0 : -1;
      document.getElementById("p-" + b.dataset.tab).hidden = !on;
    });
    if (chartJobs[key]) { chartJobs[key](); delete chartJobs[key]; }
  }
  RG.on(ctx.page, "[data-tab]", "click", function (e, b) { showTab(b.dataset.tab); });
  RG.on(ctx.page, ".tw-tabs", "keydown", function (e) {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    var tabs = Array.prototype.slice.call(ctx.page.querySelectorAll("[data-tab]"));
    var i = tabs.indexOf(document.activeElement); if (i < 0) return;
    var next = tabs[(i + (e.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length];
    next.focus(); showTab(next.dataset.tab);
  });
  function draw(id, type, rows, labelKey, valueKey, horizontal) {
    var canvas = document.getElementById(id);
    if (!canvas || typeof Chart === "undefined") return;
    var labels = rows.map(function (r) { return r[labelKey]; }), values = rows.map(function (r) { return r[valueKey]; });
    var colours = labels.map(function (l, i) { return STATUS_COLOURS[l] || TEAL[i % TEAL.length]; });
    if (charts[id]) charts[id].destroy();
    var font = { family: "Plus Jakarta Sans", size: 11 };
    charts[id] = new Chart(canvas, {
      type: type,
      data: { labels: labels, datasets: [{ data: values, backgroundColor: colours, borderWidth: 0, borderRadius: type === "bar" ? 4 : 0, maxBarThickness: 26, hoverOffset: 6 }] },
      options: type === "doughnut"
        ? { responsive: true, maintainAspectRatio: false, cutout: "66%", plugins: { legend: { position: "right", labels: { boxWidth: 10, font: font } } } }
        : { indexAxis: horizontal ? "y" : "x", responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } },
            scales: { x: { grid: { display: !!horizontal, color: "#EFEBE2" }, border: { display: false }, beginAtZero: true, ticks: { precision: 0, font: font } },
                      y: { grid: { display: !horizontal, color: "#EFEBE2" }, border: { display: false }, beginAtZero: true, ticks: { precision: 0, font: font } } } }
    });
  }
  function renderInsights(d) {
    var c = d.charts, k = d.kpis;
    var depts = c.employees_by_department.filter(function (r) { return r.count > 0; });
    var docTotal = c.document_status.reduce(function (s, r) { return s + r.count; }, 0);
    var rep = {}; c.report_status.forEach(function (r) { rep[r.status] = r.count; });
    document.getElementById("i-dept").innerHTML = "<b>" + depts.length + "</b> departments have people in your hierarchy · " + k.active_employees + " of " + k.total_employees + " active · " + k.new_employees + " joined in 30 days.";
    document.getElementById("i-docs").innerHTML = "<b>" + (docTotal ? Math.round(k.documents_verified * 100 / docTotal) : 0) + "%</b> of submitted documents verified · " + k.documents_pending + " pending · " + k.documents_rejected + " rejected.";
    document.getElementById("i-salary").innerHTML = "<b>" + RG.fmt.money(k.monthly_payroll) + "</b> payroll this period · " + k.salary_credited + " credited · " + k.salary_processing + " processing · " + k.salary_pending + " pending.";
    document.getElementById("i-reports").innerHTML = "<b>" + k.reports_pending + "</b> reports waiting for review · " + (rep.Reviewed || 0) + " reviewed.";
    chartJobs = {
      dept: function () { draw("c-dept", "bar", c.employees_by_department, "department", "count", true); },
      docs: function () { draw("c-docs", "doughnut", c.document_status, "status", "count"); },
      salary: function () { draw("c-salary", "bar", c.salary_status, "status", "count"); },
      reports: function () { draw("c-reports", "bar", c.report_status, "status", "count"); }
    };
    var cur = ctx.page.querySelector('[data-tab][aria-selected="true"]');
    showTab(cur ? cur.dataset.tab : "dept");
  }

  /* ================================ load ================================ */
  function load() {
    renderMyDay();
    API.get("/attendance/hr/today").then(renderWorkToday).catch(function (err) {
      var el = document.getElementById("work-today"); if (el) el.innerHTML = RG.errorState(err.message);
    });
    API.get("/dashboard/hr").then(function (d) {
      S.dash = d;
      // The dashboard's own pending counts are authoritative for its queues.
      (d.pending_actions || []).forEach(function (a) {
        var map = { "documents.html": "docs", "work-reports.html": "reports", "uan.html": "uan", "salary.html": "salary" };
        var q = map[a.link.replace(/^\/hr\//, "")]; if (q && S.totals[q] === undefined) S.totals[q] = a.count;
      });
      renderMeetings(d.todays_meetings || []);
      renderRecent(d.recent_employees || []);
      renderInsights(d);
      renderAll();
      loadQueues();
    }).catch(function (err) {
      ctx.page.innerHTML = '<div class="card">' + RG.errorState(err.message, "retry") + "</div>";
      var retry = document.getElementById("retry");
      if (retry) retry.addEventListener("click", function () { shell(); load(); });
    });
  }

  shell();
  renderAll();
  load();
})();
