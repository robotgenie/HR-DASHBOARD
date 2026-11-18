/* admin-dashboard.js - ORGANISATION CONTROL ROOM.
   A full-bleed canvas instead of a card dashboard:
     command strip (Ctrl+K jump + live status lamps)
     left instruments (organisation health)  |  centre ORGANISATION LENS  |  right alerts + approval streams
     workforce movement (today's arrivals / departures), HR branches, pipelines, log.
   The lens switches between a radial reporting-line constellation (every
   person coloured by today's attendance state) and a department treemap.

   Data (read-only, existing endpoints): /admin/dashboard, /attendance/hr/today,
   /admin/departments/overview, /hierarchy/tree and the pending queues
   (/leave-requests, /documents, /reports, /uan, /salaries) for the streams.
   The Admin is not an employee: there is no check-in here. */
(function () {
  "use strict";
  var ctx = RG.boot({ scope: "admin", active: "dashboard", title: "Control Room", subtitle: "Whole organisation", shell: "overlay" });
  if (!ctx) return;

  var MONO = "IBM Plex Mono";
  var STATE = {
    in: { c: "#12B76A", l: "Present" }, late: { c: "#F79009", l: "Late" }, out: { c: "#667085", l: "Checked out" },
    leave: { c: "#2E90FA", l: "On leave" }, none: { c: "#D0D5DD", l: "Not checked in" }, off: { c: "#EAECF0", l: "Inactive" }
  };
  var STATUS_COLOURS = {
    "Verified": "#12B76A", "Pending": "#F79009", "Rejected": "#F04438", "Re-upload Requested": "#FB6514",
    "Credited": "#12B76A", "Processing": "#4F5BD5", "Submitted": "#4F5BD5", "Reviewed": "#12B76A", "Draft": "#F79009"
  };
  var charts = {};
  var S = { dash: null, today: null, tree: null, depts: null, streams: {}, lens: "lines" };
  var personState = {};

  function sk(h) { return '<div class="skeleton" style="height:' + (h || 80) + 'px;border-radius:6px"></div>'; }

  /* ================================ layout ================================ */
  function shell() {
    ctx.page.innerHTML =
      '<div class="cr">' +
      '<section class="cr-strip" aria-label="Command strip">' +
        '<div class="cr-title"><span class="cr-live">Live</span><h1>Organisation Control Room</h1>' +
          '<span class="cr-date" id="cr-date"></span></div>' +
        '<button type="button" class="cr-command" data-cmd>' + RG.icon("search", 18) +
          "<span>Find a person, department or page…</span><kbd>Ctrl K</kbd></button>" +
        '<div class="cr-lamps" id="lamps" aria-label="System status">' + sk(34) + "</div>" +
        '<div class="cr-quick">' +
          '<a class="cr-ibtn" href="organization.html" title="Organisation & hierarchy">' + RG.icon("tree", 17) + '<span class="sr-only">Hierarchy</span></a>' +
          '<a class="cr-ibtn" href="excel.html" title="Excel import / export">' + RG.icon("upload", 17) + '<span class="sr-only">Excel</span></a>' +
          '<a class="cr-ibtn primary" href="employees.html?new=1">' + RG.icon("plus", 17) + "<span>Add person</span></a>" +
        "</div>" +
      "</section>" +

      '<div class="cr-stage">' +
        '<aside class="cr-col cr-left" aria-label="Organisation health">' +
          '<div class="cr-label">Organisation health</div><div id="health">' + sk(300) + "</div>" +
          '<div class="cr-label">Workforce</div><div id="workforce">' + sk(120) + "</div>" +
        "</aside>" +

        '<section class="cr-lens" aria-label="Organisation lens">' +
          '<header class="lens-bar"><div class="lens-tabs" role="tablist" aria-label="Lens">' +
              '<button role="tab" aria-selected="true" data-lens="lines">' + RG.icon("tree", 15) + " Reporting lines</button>" +
              '<button role="tab" aria-selected="false" data-lens="depts">' + RG.icon("grid", 15) + " Departments</button></div>" +
            '<div class="lens-key" id="lens-key"></div></header>' +
          '<div class="lens-body" id="lens">' + '<div class="lens-loading">' + sk(420) + "</div></div>" +
          '<div class="lens-detail" id="lens-detail" hidden></div>' +
        "</section>" +

        '<aside class="cr-col cr-right" aria-label="Alerts and approvals">' +
          '<div class="cr-label">Priority alerts</div><div id="alerts">' + sk(140) + "</div>" +
          '<div class="cr-label">Approval streams</div><div id="streams">' + sk(260) + "</div>" +
        "</aside>" +
      "</div>" +

      '<section class="cr-deck">' +
        '<div class="deck-panel deck-move"><header><h2>' + RG.icon("pulse", 16) + " Workforce movement</h2><span>Today · check-ins and check-outs across the day</span>" +
          '<a href="work-monitor.html">Attendance &amp; hourly ' + RG.icon("arrow", 13) + "</a></header>" +
          '<div class="deck-chart"><canvas id="c-move" role="img" aria-label="Check-ins and check-outs through the day"></canvas></div>' +
          '<div class="move-foot" id="move-foot"></div></div>' +
        '<div class="deck-panel deck-hr"><header><h2>' + RG.icon("shield", 16) + " HR branches</h2><span>Expand a branch to monitor it</span>" +
          '<a href="hr-monitoring.html">HR monitoring ' + RG.icon("arrow", 13) + "</a></header><div id=\"hr-host\">" + sk(160) + "</div></div>" +
      "</section>" +

      '<section class="cr-deck three">' +
        pipe("Leave approval pipeline", "Pending, by stage", "leave-requests.html", "c-stage", "") +
        pipe("Document verification", "Whole organisation", "documents.html", "c-docs", "l-docs") +
        pipe("Work report review", "Submitted vs reviewed", "work-reports.html", "c-reports", "") +
      "</section>" +

      '<section class="cr-deck">' +
        '<div class="deck-panel"><header><h2>' + RG.icon("clock", 16) + " Late check-ins today</h2><span>Expected vs actual login</span>" +
          '<a href="work-monitor.html">Details ' + RG.icon("arrow", 13) + '</a></header><div id="late-today">' + sk(120) + "</div></div>" +
        '<div class="deck-panel"><header><h2>' + RG.icon("layers", 16) + " Organisation log</h2><span>New people records and today’s meetings</span>" +
          '<a href="employees.html">People directory ' + RG.icon("arrow", 13) + '</a></header><div id="activity">' + sk(120) + "</div></div>" +
      "</section>" +
      "</div>";
    document.getElementById("cr-date").textContent = new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  }
  function pipe(title, sub, href, canvas, legend) {
    return '<div class="deck-panel"><header><h2>' + title + "</h2><span>" + sub + '</span><a href="' + href + '">Open ' + RG.icon("arrow", 13) + "</a></header>" +
      '<div class="pipe-chart"><canvas id="' + canvas + '" role="img" aria-label="' + RG.esc(title) + '"></canvas></div>' + (legend ? '<div class="cc-legend" id="' + legend + '"></div>' : "") + "</div>";
  }

  RG.on(ctx.page, "[data-cmd]", "click", function () { RG.openPalette(); });
  RG.on(ctx.page, "[data-lens]", "click", function (e, b) { setLens(b.dataset.lens); });

  /* ================================ status lamps ================================ */
  function renderLamps() {
    var d = S.dash; if (!d) return;
    var k = d.kpis, t = S.today ? S.today.totals : null;
    var att = t && t.employees ? Math.round(t.checked_in * 100 / t.employees) : null;
    var open = queueItems(d).reduce(function (s, a) { return s + (a.count || 0); }, 0);
    function lamp(label, val, tone, href) {
      return '<a class="lamp ' + tone + '" href="' + href + '"><i aria-hidden="true"></i><span>' + label + "</span><b>" + val + "</b></a>";
    }
    document.getElementById("lamps").innerHTML =
      lamp("Attendance", att === null ? "—" : att + "%", att === null ? "" : att >= 80 ? "ok" : att >= 50 ? "warn" : "bad", "work-monitor.html") +
      lamp("Approvals", open, open === 0 ? "ok" : open <= 10 ? "warn" : "bad", "leave-requests.html") +
      lamp("Hierarchy", d.unassigned_people ? d.unassigned_people + " gaps" : "Complete", d.unassigned_people ? "warn" : "ok", "organization.html") +
      lamp("Documents", k.documents_pending + " pending", k.documents_pending ? (k.documents_pending > 10 ? "bad" : "warn") : "ok", "documents.html") +
      lamp("Payroll", k.salary_pending ? k.salary_pending + " pending" : "Clear", k.salary_pending ? "warn" : "ok", "salary.html");
  }

  /* ================================ health instruments ================================ */
  function renderHealth() {
    var d = S.dash; if (!d) return;
    var k = d.kpis, t = S.today ? S.today.totals : {}, c = d.charts;
    var docs = {}; c.document_status.forEach(function (r) { docs[r.status] = r.count; });
    var reps = {}; c.report_status.forEach(function (r) { reps[r.status] = r.count; });
    var sal = {}; c.salary_status.forEach(function (r) { sal[r.status] = r.count; });
    var pt = d.people_by_type || {};
    var lineTotal = (pt.Manager || 0) + (pt.Employee || 0) + (pt.Intern || 0);
    function pct(n, of) { return of ? Math.round(n * 100 / of) : null; }
    var rows = [
      ["Attendance today", pct(t.checked_in, t.employees), (t.checked_in || 0) + " of " + (t.employees || 0) + " checked in", "work-monitor.html"],
      ["On-time arrival", pct((t.checked_in || 0) - (t.late || 0), t.checked_in), (t.late || 0) + " late check-ins", "work-monitor.html"],
      ["Hourly compliance", pct(t.hourly_submitted, (t.hourly_submitted || 0) + (t.hourly_due || 0)), (t.hourly_due || 0) + " updates due or missed", "work-monitor.html?tab=hourly"],
      ["Hierarchy coverage", pct(lineTotal - d.unassigned_people, lineTotal), d.unassigned_people + " without a Reporting HR", "organization.html"],
      ["Documents verified", pct(docs.Verified || 0, (docs.Verified || 0) + (docs.Pending || 0) + (docs.Rejected || 0) + (docs["Re-upload Requested"] || 0)), (docs.Pending || 0) + " awaiting verification", "documents.html"],
      ["Reports reviewed", pct(reps.Reviewed || 0, (reps.Reviewed || 0) + (reps.Submitted || 0)), (reps.Submitted || 0) + " waiting for review", "work-reports.html"],
      ["Payroll credited", pct(sal.Credited || 0, Object.keys(sal).reduce(function (s, x) { return s + sal[x]; }, 0)), RG.fmt.money(k.monthly_payroll) + " net this period", "salary.html"]
    ];
    document.getElementById("health").innerHTML = '<ul class="instr">' + rows.map(function (r) {
      var v = r[1], tone = v === null ? "" : v >= 80 ? "ok" : v >= 50 ? "warn" : "bad";
      return '<li><a href="' + r[3] + '"><div class="i-top"><span>' + r[0] + '</span><b class="' + tone + '">' + (v === null ? "—" : v + "%") + "</b></div>" +
        '<div class="i-track" aria-hidden="true"><span class="' + tone + '" style="width:' + (v || 0) + '%"></span><em style="left:80%"></em></div>' +
        '<div class="i-note">' + RG.esc(r[2]) + "</div></a></li>";
    }).join("") + "</ul>";

    var a = d.active_by_type || {};
    var total = (a.HR || 0) + (a.Manager || 0) + (a.Employee || 0) + (a.Intern || 0);
    var TYPES = [["HR", "#A48AFB", "hr-monitoring.html"], ["Manager", "#4F5BD5", "people.html?type=Manager"], ["Employee", "#36BFFA", "people.html?type=Employee"], ["Intern", "#FDB022", "people.html?type=Intern"]];
    document.getElementById("workforce").innerHTML = '<div class="wf"><div class="wf-big"><b>' + total + "</b><span>active people · " + k.total_employees + " records</span></div>" +
      '<div class="wf-bar" aria-hidden="true">' + TYPES.map(function (x) { return '<span style="flex:' + (a[x[0]] || 0) + ";background:" + x[1] + '"></span>'; }).join("") + "</div>" +
      '<ul class="wf-list">' + TYPES.map(function (x) {
        return '<li><a href="' + x[2] + '"><i style="background:' + x[1] + '"></i>' + (x[0] === "HR" ? "HR" : x[0] + "s") + "<b>" + (a[x[0]] || 0) + "</b></a></li>";
      }).join("") + "</ul></div>";
  }

  /* ================================ alerts + streams ================================ */
  function queueItems(d) {
    var stage = d.leave_by_stage || {};
    return [
      { label: "HR leave requests waiting on you", count: stage.Admin || 0, link: "leave-requests.html" },
      { label: "documents awaiting verification", count: d.kpis.documents_pending, link: "documents.html" },
      { label: "work reports not yet reviewed", count: d.kpis.reports_pending, link: "work-reports.html" },
      { label: "UANs awaiting verification", count: d.kpis.uan_pending, link: "uan.html" },
      { label: "salaries not yet credited", count: d.kpis.salary_pending, link: "salary.html" },
      { label: "people without a Reporting HR", count: d.unassigned_people, link: "organization.html" }
    ];
  }
  function renderAlerts() {
    var d = S.dash; if (!d) return;
    var k = d.kpis, t = S.today ? S.today.totals : {};
    var al = [];
    if (d.hr_leave_awaiting_admin) al.push(["bad", d.hr_leave_awaiting_admin, "HR leave awaiting your decision", "leave-requests.html"]);
    if (t.hourly_due) al.push(["bad", t.hourly_due, "Hourly updates due or missed", "work-monitor.html?tab=hourly"]);
    if (d.unassigned_people) al.push(["warn", d.unassigned_people, "People outside the hierarchy", "organization.html"]);
    if (k.late_logins_today) al.push(["warn", k.late_logins_today, "Late check-ins today", "work-monitor.html"]);
    if (k.documents_rejected) al.push(["info", k.documents_rejected, "Rejected documents awaiting re-upload", "documents.html"]);
    var notIn = t.employees ? Math.max(0, t.employees - t.checked_in - t.on_leave) : 0;
    if (notIn) al.push(["info", notIn, "Not checked in yet (excl. leave)", "work-monitor.html"]);
    document.getElementById("alerts").innerHTML = al.length ? '<ul class="alerts">' + al.map(function (a) {
      return '<li class="' + a[0] + '"><a href="' + a[3] + '"><span class="sev" aria-hidden="true"></span><span class="t">' + RG.esc(a[2]) + '</span><b>' + a[1] + "</b></a></li>";
    }).join("") + "</ul>" : '<div class="allclear">' + RG.icon("check", 16) + " No critical alerts</div>";
  }

  /* Each stream: the count from the dashboard + the first real records. */
  var STREAMS = [
    { key: "leave", title: "HR leave → Admin", href: "leave-requests.html", path: "/leave-requests", q: { status: "Pending", stage: "Admin", page: 1, page_size: 3 },
      row: function (r) { return [r.employee_name, (r.leave_type_label || r.leave_type) + " · " + RG.fmt.date(r.from_date), r.requested_at]; } },
    { key: "docs", title: "Document verification", href: "documents.html", path: "/documents", q: { status: "Pending", page: 1, page_size: 3 },
      row: function (r) { return [r.employee_name, r.document_type, r.uploaded_at]; } },
    { key: "reports", title: "Work report review", href: "work-reports.html", path: "/reports", q: { status: "Submitted", page: 1, page_size: 3 },
      row: function (r) { return [r.employee_name, r.report_type + " report · " + RG.fmt.date(r.report_date), r.submitted_at]; } },
    { key: "uan", title: "UAN verification", href: "uan.html", path: "/uan", q: { status: "Submitted", page: 1, page_size: 3 },
      row: function (r) { return [r.employee_name, "UAN " + (r.uan_number || ""), r.submitted_at]; } },
    { key: "salary", title: "Salary crediting", href: "salary.html", path: "/salaries", q: { status: "Pending", page: 1, page_size: 3 },
      row: function (r) { return [r.employee_name, r.period_label + " · " + RG.fmt.money(r.net_pay), null]; } }
  ];
  function streamCount(key) {
    var d = S.dash; if (!d) return 0;
    return { leave: (d.leave_by_stage || {}).Admin || 0, docs: d.kpis.documents_pending, reports: d.kpis.reports_pending, uan: d.kpis.uan_pending, salary: d.kpis.salary_pending }[key] || 0;
  }
  function renderStreams() {
    var host = document.getElementById("streams"); if (!host || !S.dash) return;
    var max = Math.max.apply(null, STREAMS.map(function (s) { return streamCount(s.key); }).concat([1]));
    host.innerHTML = '<div class="streams">' + STREAMS.map(function (s, i) {
      var n = streamCount(s.key), rows = S.streams[s.key];
      var items = rows === undefined ? '<div class="small muted">Loading…</div>'
        : rows.length ? '<ul>' + rows.map(function (r) {
            var x = s.row(r);
            return "<li><b>" + RG.esc(x[0] || "") + "</b><span>" + RG.esc(x[1] || "") + "</span>" + (x[2] ? "<em>" + RG.fmt.ago(x[2]) + "</em>" : "") + "</li>";
          }).join("") + (n > rows.length ? '<li class="more">+ ' + (n - rows.length) + " more</li>" : "") + "</ul>"
        : '<div class="small muted">Nothing waiting.</div>';
      return '<details class="stream' + (n ? "" : " zero") + '"' + (i < 2 && n ? " open" : "") + '><summary><span class="st-flow" aria-hidden="true"><span style="width:' + (n * 100 / max) + '%"></span></span>' +
          '<span class="st-t">' + s.title + '</span><b>' + n + "</b></summary>" +
        '<div class="st-body">' + items + '<a class="st-go" href="' + s.href + '">Open queue ' + RG.icon("arrow", 13) + "</a></div></details>";
    }).join("") + "</div>";
  }
  function loadStreams() {
    STREAMS.forEach(function (s) {
      API.get(s.path, s.q).then(function (r) { S.streams[s.key] = (r && r.items) || []; })
        .catch(function () { S.streams[s.key] = []; })
        .then(renderStreams);
    });
  }

  /* ================================ the lens ================================ */
  function setLens(which) {
    S.lens = which;
    ctx.page.querySelectorAll("[data-lens]").forEach(function (b) { b.setAttribute("aria-selected", b.dataset.lens === which ? "true" : "false"); });
    document.getElementById("lens-detail").hidden = true;
    renderLens();
  }
  function renderLens() {
    var host = document.getElementById("lens");
    var key = document.getElementById("lens-key");
    if (S.lens === "lines") {
      key.innerHTML = ["in", "late", "out", "leave", "none"].map(function (s) { return '<span><i style="background:' + STATE[s].c + '"></i>' + STATE[s].l + "</span>"; }).join("");
      if (!S.tree) return;
      host.innerHTML = constellation(S.tree);
    } else {
      key.innerHTML = '<span><i style="background:#E6F4EA"></i>Low attendance</span><span><i style="background:#12B76A"></i>High attendance</span><span>Tile size = people</span>';
      if (!S.depts) return;
      host.innerHTML = treemap(S.depts);
    }
  }

  /* Radial constellation: Organisation → HR ring → managers → people. */
  function constellation(items) {
    if (!items.length) return RG.emptyState("No hierarchy yet", "Create HR accounts and assign managers to see the organisation.", '<a class="btn btn-sm" href="organization.html">Open hierarchy</a>', "tree");
    var W = 980, H = 640, cx = W / 2, cy = H / 2;
    var R1 = 118, R2 = 228, R3 = 308;
    var branches = items.map(function (hr) {
      var mgrs = (hr.managers || []).map(function (m) { return { node: m, team: m.team || [] }; });
      var direct = hr.direct || [];
      var weight = 1 + mgrs.reduce(function (s, m) { return s + 1 + m.team.length; }, 0) + direct.length;
      return { hr: hr, mgrs: mgrs, direct: direct, weight: weight };
    });
    var total = branches.reduce(function (s, b) { return s + b.weight; }, 0);
    var gap = 0.06, angle = -Math.PI / 2;
    var avail = Math.PI * 2 - gap * branches.length;
    var edges = [], nodes = [], labels = [], arcs = [];
    function pt(r, a) { return [cx + r * Math.cos(a), cy + r * Math.sin(a)]; }
    function curve(a, b) {
      var mx = (a[0] + b[0]) / 2, my = (a[1] + b[1]) / 2;
      var qx = cx + (mx - cx) * 0.82, qy = cy + (my - cy) * 0.82;
      return "M" + a[0].toFixed(1) + "," + a[1].toFixed(1) + " Q" + qx.toFixed(1) + "," + qy.toFixed(1) + " " + b[0].toFixed(1) + "," + b[1].toFixed(1);
    }
    function stateOf(p) { return p.is_active === false ? "off" : (personState[p.id] || "none"); }
    function person(p, xy, r, href, label) {
      var st = stateOf(p);
      var title = p.full_name + " · " + (p.type || "") + (p.designation ? " · " + p.designation : "") + " · " + STATE[st].l + (p.department ? " · " + p.department : "");
      nodes.push('<a href="' + href + '" class="cn cn-' + st + '" aria-label="' + RG.esc(title) + '"><title>' + RG.esc(title) + "</title>" +
        '<circle cx="' + xy[0].toFixed(1) + '" cy="' + xy[1].toFixed(1) + '" r="' + r + '" fill="' + STATE[st].c + '"/>' +
        (label ? '<text x="' + xy[0].toFixed(1) + '" y="' + (xy[1] + 3.5).toFixed(1) + '" text-anchor="middle" class="cn-i">' + RG.esc(RG.fmt.initials(p.full_name)) + "</text>" : "") + "</a>");
    }
    branches.forEach(function (b) {
      var span = avail * b.weight / total;
      var a0 = angle, aMid = a0 + span / 2;
      var hrXY = pt(R1, aMid);
      arcs.push('<path class="sector" d="' + sector(cx, cy, R1 - 34, R3 + 34, a0, a0 + span) + '"/>');
      edges.push('<path class="e e0" d="M' + cx + "," + cy + " L" + hrXY[0].toFixed(1) + "," + hrXY[1].toFixed(1) + '"/>');
      // managers + their teams share the sector, weighted by size
      var inner = b.mgrs.map(function (m) { return { m: m, w: 1 + m.team.length }; });
      if (b.direct.length) inner.push({ direct: true, w: b.direct.length });
      var wsum = inner.reduce(function (s, x) { return s + x.w; }, 0) || 1;
      var cur = a0 + span * 0.04, usable = span * 0.92;
      inner.forEach(function (x) {
        var sp = usable * x.w / wsum, mid = cur + sp / 2;
        if (x.direct) {
          b.direct.forEach(function (p, i) {
            var a = cur + sp * (i + 0.5) / b.direct.length;
            var xy = pt(R3, a);
            edges.push('<path class="e e2 dashed" d="' + curve(hrXY, xy) + '"/>');
            person(p, xy, 11, "person.html?id=" + p.id, true);
          });
        } else {
          var mXY = pt(R2, mid);
          edges.push('<path class="e e1" d="' + curve(hrXY, mXY) + '"/>');
          x.m.team.forEach(function (p, i) {
            var a = cur + sp * (i + 0.5) / Math.max(1, x.m.team.length);
            var xy = pt(R3, a);
            edges.push('<path class="e e2" d="' + curve(mXY, xy) + '"/>');
            person(p, xy, 11, "person.html?id=" + p.id, true);
          });
          person(x.m.node, mXY, 17, "person.html?id=" + x.m.node.id, true);
          var lx = pt(R2 + 0, mid);
          labels.push(label(x.m.node.full_name.split(" ")[0], "Manager · " + x.m.team.length, lx, mid, 22));
        }
        cur += sp;
      });
      if (b.hr.id) {
        person(b.hr, hrXY, 23, "hr-monitoring.html?id=" + b.hr.id, true);
        labels.push(labelAt(b.hr.full_name, "HR · " + (b.weight - 1) + " people", hrXY[0], hrXY[1] + 38, "middle"));
      } else {
        nodes.push('<a href="organization.html" class="cn"><title>Not assigned to an HR</title><circle cx="' + hrXY[0].toFixed(1) + '" cy="' + hrXY[1].toFixed(1) + '" r="19" fill="#FEF0C7" stroke="#F79009" stroke-width="2" stroke-dasharray="4 3"/>' +
          '<text x="' + hrXY[0].toFixed(1) + '" y="' + (hrXY[1] + 4).toFixed(1) + '" text-anchor="middle" class="cn-i warn">!</text></a>');
        labels.push(label("Unassigned", (b.weight - 1) + " people", hrXY, aMid, 28));
      }
      angle += span + gap;
    });
    var people = branches.reduce(function (s, b) { return s + b.weight; }, 0);
    return '<svg class="constellation" viewBox="0 0 ' + W + " " + H + '" role="group" aria-label="Organisation reporting lines coloured by today’s attendance">' +
      '<defs><radialGradient id="cr-glow"><stop offset="0" stop-color="#4F5BD5" stop-opacity=".16"/><stop offset="1" stop-color="#4F5BD5" stop-opacity="0"/></radialGradient></defs>' +
      '<circle cx="' + cx + '" cy="' + cy + '" r="' + (R3 + 36) + '" class="ring r3"/><circle cx="' + cx + '" cy="' + cy + '" r="' + R2 + '" class="ring"/><circle cx="' + cx + '" cy="' + cy + '" r="' + R1 + '" class="ring"/>' +
      arcs.join("") + '<circle cx="' + cx + '" cy="' + cy + '" r="90" fill="url(#cr-glow)"/>' +
      edges.join("") +
      '<a href="organization.html" class="cn"><title>Organisation — open hierarchy</title><circle cx="' + cx + '" cy="' + cy + '" r="40" class="core"/>' +
        '<image href="' + RG.APP_ROOT + '/assets/logo/rocket-genie-mark.png" x="' + (cx - 15) + '" y="' + (cy - 24) + '" width="30" height="30"/>' +
        '<text x="' + cx + '" y="' + (cy + 21) + '" text-anchor="middle" class="core-t">' + people + " people</text></a>" +
      nodes.join("") + labels.join("") + "</svg>";
  }
  function labelAt(t1, t2, x, y, anchor) {
    return '<g class="lbl hr" aria-hidden="true"><text x="' + x.toFixed(1) + '" y="' + y.toFixed(1) + '" text-anchor="' + anchor + '" class="l1">' + RG.esc(t1) + "</text>" +
      '<text x="' + x.toFixed(1) + '" y="' + (y + 13).toFixed(1) + '" text-anchor="' + anchor + '" class="l2">' + RG.esc(t2) + "</text></g>";
  }
  function label(t1, t2, xy, a, off) {
    var dx = Math.cos(a), dy = Math.sin(a);
    var x = xy[0] + dx * off, y = xy[1] + dy * off;
    var anchor = Math.abs(dx) < 0.3 ? "middle" : dx > 0 ? "start" : "end";
    return '<g class="lbl" aria-hidden="true"><text x="' + x.toFixed(1) + '" y="' + (y - 2).toFixed(1) + '" text-anchor="' + anchor + '" class="l1">' + RG.esc(t1) + "</text>" +
      '<text x="' + x.toFixed(1) + '" y="' + (y + 11).toFixed(1) + '" text-anchor="' + anchor + '" class="l2">' + RG.esc(t2) + "</text></g>";
  }
  function sector(cx, cy, r0, r1, a0, a1) {
    function p(r, a) { return (cx + r * Math.cos(a)).toFixed(1) + "," + (cy + r * Math.sin(a)).toFixed(1); }
    var big = a1 - a0 > Math.PI ? 1 : 0;
    return "M" + p(r0, a0) + " L" + p(r1, a0) + " A" + r1 + "," + r1 + " 0 " + big + " 1 " + p(r1, a1) + " L" + p(r0, a1) + " A" + r0 + "," + r0 + " 0 " + big + " 0 " + p(r0, a0) + "Z";
  }

  /* Department treemap: tile area = people, fill = share checked in today. */
  function treemap(items) {
    var full = items.filter(function (d) { return d.total > 0; }).sort(function (a, b) { return b.total - a.total; });
    var empty = items.filter(function (d) { return !d.total; });
    if (!full.length) return RG.emptyState("No people in departments yet", "", "", "grid");
    var rects = [];
    (function split(list, x, y, w, h) {
      if (!list.length) return;
      if (list.length === 1) { rects.push({ d: list[0], x: x, y: y, w: w, h: h }); return; }
      var tot = list.reduce(function (s, d) { return s + d.total; }, 0), acc = 0, i = 0;
      while (i < list.length - 1 && acc + list[i].total <= tot / 2) { acc += list[i].total; i++; }
      if (i === 0) { acc = list[0].total; i = 1; }
      var a = list.slice(0, i), b = list.slice(i), r = acc / tot;
      if (w >= h) { split(a, x, y, w * r, h); split(b, x + w * r, y, w * (1 - r), h); }
      else { split(a, x, y, w, h * r); split(b, x, y + h * r, w, h * (1 - r)); }
    })(full, 0, 0, 100, 100);
    function fill(p) { // light green -> strong green
      var c0 = [230, 244, 234], c1 = [18, 183, 106];
      return "rgb(" + c0.map(function (v, i) { return Math.round(v + (c1[i] - v) * p); }).join(",") + ")";
    }
    return '<div class="tm" role="list">' + rects.map(function (r) {
      var d = r.d, p = d.total ? d.checked_in_today / d.total : 0;
      var dark = p > 0.55;
      var c = d.counts;
      return '<button type="button" role="listitem" class="tm-tile' + (dark ? " dark" : "") + '" data-dept="' + d.id + '" style="left:' + r.x + "%;top:" + r.y + "%;width:" + r.w + "%;height:" + r.h + "%;background:" + fill(p) + '">' +
        '<span class="tm-n">' + RG.esc(d.name) + "</span>" +
        '<span class="tm-v">' + d.total + " people · " + d.checked_in_today + "/" + d.total + " in</span>" +
        '<span class="tm-mix">' + ["HR", "Manager", "Employee", "Intern"].filter(function (k) { return c[k]; }).map(function (k) { return c[k] + " " + (k === "HR" ? "HR" : k.toLowerCase() + (c[k] > 1 ? "s" : "")); }).join(" · ") + "</span>" +
        (d.documents_pending ? '<span class="tm-doc">' + d.documents_pending + " docs pending</span>" : "") + "</button>";
    }).join("") + "</div>" +
    (empty.length ? '<div class="tm-empty">No people yet: ' + empty.map(function (d) { return '<a href="departments.html?id=' + d.id + '">' + RG.esc(d.name) + "</a>"; }).join(", ") + "</div>" : "");
  }
  RG.on(ctx.page, "[data-dept]", "click", function (e, b) {
    var d = (S.depts || []).filter(function (x) { return String(x.id) === b.dataset.dept; })[0];
    if (!d) return;
    var box = document.getElementById("lens-detail");
    var c = d.counts;
    box.innerHTML = '<div class="ld-head"><div><span class="cr-label">Department</span><h3>' + RG.esc(d.name) + "</h3></div>" +
      '<button type="button" class="icon-btn" data-ld-close aria-label="Close">' + RG.icon("x", 15) + "</button></div>" +
      '<dl class="ld-grid"><div><dt>HR</dt><dd>' + c.HR + "</dd></div><div><dt>Managers</dt><dd>" + c.Manager + "</dd></div><div><dt>Employees</dt><dd>" + c.Employee + "</dd></div>" +
      "<div><dt>Interns</dt><dd>" + c.Intern + "</dd></div><div><dt>Checked in</dt><dd>" + d.checked_in_today + "/" + d.total + "</dd></div><div><dt>Docs pending</dt><dd>" + d.documents_pending + "</dd></div></dl>" +
      '<a class="btn btn-sm" href="departments.html?id=' + d.id + '">Open department monitoring</a>';
    box.hidden = false;
    box.querySelector("[data-ld-close]").focus();
  });
  RG.on(ctx.page, "[data-ld-close]", "click", function () { document.getElementById("lens-detail").hidden = true; });

  /* ================================ workforce movement ================================ */
  function renderMovement() {
    var canvas = document.getElementById("c-move");
    var t = S.today; if (!t || !canvas || typeof Chart === "undefined") return;
    var START = 8 * 60, END = 20 * 60, STEP = 30;
    var labels = [], arrive = [], leave = [], present = [];
    var ins = [], outs = [];
    (t.items || []).forEach(function (r) {
      var s = r.session; if (!s) return;
      if (s.check_in_time) ins.push(toMin(s.check_in_time));
      if (s.check_out_time) outs.push(toMin(s.check_out_time));
    });
    var now = new Date(), nowMin = now.getHours() * 60 + now.getMinutes();
    for (var m = START; m < END; m += STEP) {
      labels.push(RG.fmt.time(String(Math.floor(m / 60)).padStart(2, "0") + ":" + String(m % 60).padStart(2, "0")).replace(":00", ""));
      arrive.push(ins.filter(function (x) { return x >= m && x < m + STEP; }).length);
      leave.push(-outs.filter(function (x) { return x >= m && x < m + STEP; }).length);
      present.push(m <= nowMin ? ins.filter(function (x) { return x < m + STEP; }).length - outs.filter(function (x) { return x < m + STEP; }).length : null);
    }
    if (charts.move) charts.move.destroy();
    charts.move = new Chart(canvas, {
      data: { labels: labels, datasets: [
        { type: "line", label: "On the floor", data: present, borderColor: "#4F5BD5", backgroundColor: "rgba(79,91,213,.08)", fill: true, tension: .35, pointRadius: 0, borderWidth: 2, yAxisID: "y", spanGaps: false },
        { type: "bar", label: "Check-ins", data: arrive, backgroundColor: "#12B76A", borderRadius: 2, maxBarThickness: 16, yAxisID: "y" },
        { type: "bar", label: "Check-outs", data: leave, backgroundColor: "#98A2B3", borderRadius: 2, maxBarThickness: 16, yAxisID: "y" }
      ] },
      options: { responsive: true, maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
        plugins: { legend: { position: "bottom", labels: { boxWidth: 10, font: { size: 11 } } },
          tooltip: { callbacks: { label: function (c) { return c.dataset.label + ": " + Math.abs(c.raw); } } } },
        scales: { x: { stacked: true, grid: { display: false }, ticks: { font: { family: MONO, size: 10.5 }, maxRotation: 0, autoSkip: true } },
                  y: { stacked: false, grid: { color: "#EEF0F5" }, ticks: { precision: 0, font: { family: MONO, size: 10.5 }, callback: function (v) { return Math.abs(v); } } } } }
    });
    var tt = t.totals;
    var first = ins.length ? Math.min.apply(null, ins) : null;
    document.getElementById("move-foot").innerHTML =
      "<span><b>" + tt.checked_in + "</b> checked in</span><span><b>" + tt.checked_out + "</b> checked out</span>" +
      "<span><b>" + tt.late + "</b> late</span><span><b>" + tt.on_leave + "</b> on leave</span>" +
      "<span>First arrival <b>" + (first === null ? "—" : RG.fmt.time(String(Math.floor(first / 60)).padStart(2, "0") + ":" + String(first % 60).padStart(2, "0"))) + "</b></span>" +
      "<span><b>" + tt.open_tasks + "</b> open tasks</span>";
  }
  function toMin(t) { var p = String(t).split(":"); return parseInt(p[0], 10) * 60 + parseInt(p[1], 10); }

  /* ================================ HR branches (expandable) ================================ */
  function renderHr(rows) {
    var host = document.getElementById("hr-host");
    if (!rows.length) {
      host.innerHTML = RG.emptyState("No HR accounts yet", "Create an HR from the People Directory or import them from Excel.", '<a class="btn btn-sm" href="employees.html?new=1">Add HR</a>', "shield");
      return;
    }
    host.innerHTML = '<div class="branches">' + rows.map(function (h, i) {
      var c = h.counts, t = h.today || {};
      var s = t.session;
      var flags = (c.pending_leave_in_team ? 1 : 0) + (c.reports_to_review ? 1 : 0) + (c.own_pending_leave ? 1 : 0);
      return '<details class="branch"' + (i === 0 ? " open" : "") + "><summary>" + RG.avatar(h, "sm") +
          '<span class="b-name"><b>' + RG.esc(h.full_name) + "</b><span>" + RG.esc(h.designation || "") + " · " + RG.esc(h.department || "") + "</span></span>" +
          '<span class="b-today">' + RG.badge(t.state || "—") + (s ? ' <span class="mono">' + RG.fmt.time(s.check_in_time) + "</span>" : "") + "</span>" +
          '<span class="b-size"><b>' + c.managers + "</b> mgr · <b>" + c.employees + "</b> staff</span>" +
          (flags ? '<span class="b-flag">' + flags + " to act</span>" : '<span class="b-ok">' + RG.icon("check", 13) + "</span>") + "</summary>" +
        '<div class="b-body"><dl>' +
          "<div><dt>Team leave pending</dt><dd>" + c.pending_leave_in_team + "</dd></div>" +
          "<div><dt>Reports to review</dt><dd>" + c.reports_to_review + "</dd></div>" +
          "<div><dt>HR’s open tasks</dt><dd>" + c.own_open_tasks + "</dd></div>" +
          "<div><dt>HR leave for you</dt><dd>" + c.own_pending_leave + "</dd></div></dl>" +
          '<div class="row wrap"><a class="btn btn-sm" href="hr-monitoring.html?id=' + h.id + '">' + RG.icon("eye", 14) + " Monitor branch</a>" +
          (c.own_pending_leave ? '<a class="btn btn-sm" href="leave-requests.html">Decide leave</a>' : "") + "</div></div></details>";
    }).join("") + "</div>";
    RG.hydratePhotos(host);
  }

  /* ================================ late + log ================================ */
  function renderLate(rows) {
    var host = document.getElementById("late-today");
    if (!rows.length) { host.innerHTML = RG.emptyState("No late check-ins today", "Everyone who checked in today was on time.", "", "check"); return; }
    host.innerHTML = '<div class="table-scroll"><table class="data compact"><thead><tr><th>Person</th><th>Expected</th><th>Actual</th><th>Late by</th><th>Reason</th></tr></thead><tbody>' +
      rows.map(function (r) {
        return '<tr><td data-label="Person"><a href="person.html?id=' + r.employee_id + '"><b>' + RG.esc(r.employee_name) + "</b></a>" +
          '<div class="small muted">' + RG.esc(r.department || "") + "</div></td>" +
          '<td data-label="Expected" class="mono">' + RG.fmt.time(r.expected_login) + "</td>" +
          '<td data-label="Actual" class="mono">' + RG.fmt.time(r.actual_login) + "</td>" +
          '<td data-label="Late by"><b style="color:var(--bad)">' + RG.esc(r.late_label) + "</b></td>" +
          '<td data-label="Reason">' + RG.esc(r.late_reason || "—") + "</td></tr>";
      }).join("") + "</tbody></table></div>";
  }
  function renderActivity(d) {
    var rows = [];
    (d.todays_meetings || []).slice().sort(function (a, b) { return a.start_time < b.start_time ? -1 : 1; }).forEach(function (m) {
      rows.push('<li><span class="lg-t">' + RG.fmt.time(m.start_time) + '</span><span class="lg-k meet">Meeting</span><span class="lg-x"><b>' + RG.esc(m.title) + "</b> · " + RG.esc(m.department || "All departments") + (m.status === "Cancelled" ? " (cancelled)" : "") + "</span></li>");
    });
    (d.recent_employees || []).forEach(function (e) {
      rows.push('<li><span class="lg-t">' + RG.fmt.date(e.joining_date).replace(/ \d{4}$/, "") + '</span><span class="lg-k join">Joined</span><span class="lg-x"><a href="person.html?id=' + e.id + '"><b>' + RG.esc(e.full_name) + "</b></a> · " + RG.esc(e.designation || "") + " · " + RG.esc(e.department || "—") + "</span></li>");
    });
    document.getElementById("activity").innerHTML = rows.length ? '<ol class="log">' + rows.join("") + "</ol>" : RG.emptyState("Nothing recent", "New people and today’s meetings appear here.");
  }

  /* ================================ pipelines (Chart.js) ================================ */
  function chart(id, type, labels, values, opts) {
    var canvas = document.getElementById(id);
    if (!canvas || typeof Chart === "undefined") return;
    opts = opts || {};
    var colours = labels.map(function (l, i) { return (opts.colours && opts.colours[i]) || STATUS_COLOURS[l] || "#4F5BD5"; });
    if (charts[id]) charts[id].destroy();
    var wrap = canvas.parentNode, old = wrap.querySelector(".cc-chart-empty");
    if (old) old.remove();
    if (!values.some(function (v) { return v > 0; })) {
      wrap.insertAdjacentHTML("beforeend", '<div class="cc-chart-empty"><div><b>' + RG.esc(opts.empty || "Nothing to show") + "</b>All counts are zero right now.</div></div>");
    }
    var o = { responsive: true, maintainAspectRatio: false, animation: { duration: 500 }, plugins: { legend: { display: false }, tooltip: { bodyFont: { family: MONO } } } };
    if (type === "doughnut") o.cutout = "72%";
    else {
      o.indexAxis = opts.horizontal ? "y" : "x";
      o.scales = {
        x: { grid: { display: !!opts.horizontal, color: "#EEF0F5" }, border: { display: false }, beginAtZero: true, ticks: { precision: 0, font: { size: 11 }, color: "#5D6577" } },
        y: { grid: { display: !opts.horizontal, color: "#EEF0F5" }, border: { display: false }, beginAtZero: true, ticks: { precision: 0, font: { size: 11 }, color: "#5D6577" } }
      };
    }
    charts[id] = new Chart(canvas, { type: type, data: { labels: labels, datasets: [{ data: values, backgroundColor: colours, borderWidth: 0, borderRadius: type === "bar" ? 3 : 0, maxBarThickness: 24 }] }, options: o });
    if (opts.legend) document.getElementById(opts.legend).innerHTML = labels.map(function (l, i) { return '<a><i style="background:' + colours[i] + '"></i>' + RG.esc(l) + " <b>" + values[i] + "</b></a>"; }).join("");
  }

  /* ================================ load ================================ */
  function buildStates(t) {
    personState = {};
    (t.items || []).forEach(function (r) {
      var s = r.session;
      personState[r.employee_id] = s ? (s.checked_out || s.check_out_time ? "out" : s.late_minutes ? "late" : "in") : (r.leave_status ? "leave" : "none");
    });
  }
  function registerPeople(tree) {
    var cmds = [];
    tree.forEach(function (hr) {
      if (hr.id) cmds.push({ label: hr.full_name, hint: "HR · " + (hr.designation || ""), href: "hr-monitoring.html?id=" + hr.id, icon: "shield", kind: "Person" });
      (hr.managers || []).forEach(function (m) {
        cmds.push({ label: m.full_name, hint: "Manager · " + (m.department || ""), href: "person.html?id=" + m.id, icon: "users", kind: "Person" });
        (m.team || []).forEach(function (p) { cmds.push({ label: p.full_name, hint: p.type + " · " + (p.department || ""), href: "person.html?id=" + p.id, icon: "user", kind: "Person" }); });
      });
      (hr.direct || []).forEach(function (p) { cmds.push({ label: p.full_name, hint: p.type + " · " + (p.department || ""), href: "person.html?id=" + p.id, icon: "user", kind: "Person" }); });
    });
    RG.registerCommands(cmds);
  }

  function load() {
    var todayReq = API.get("/attendance/hr/today").then(function (t) {
      S.today = t; buildStates(t); renderMovement();
    }).catch(function () { S.today = null; });
    var treeReq = API.get("/hierarchy/tree").then(function (d) { S.tree = d.items || []; registerPeople(S.tree); })
      .catch(function (err) { S.tree = []; document.getElementById("lens").innerHTML = RG.errorState(err.message); });
    API.get("/admin/departments/overview").then(function (d) {
      S.depts = d.items || [];
      RG.registerCommands(S.depts.map(function (x) { return { label: x.name, hint: x.total + " people", href: "departments.html?id=" + x.id, icon: "grid", kind: "Department" }; }));
      if (S.lens === "depts") renderLens();
    }).catch(function () { S.depts = []; });
    Promise.all([todayReq, treeReq]).then(function () { if (S.lens === "lines") renderLens(); });

    API.get("/admin/dashboard").then(function (d) {
      S.dash = d;
      renderLamps(); renderHealth(); renderAlerts(); renderStreams(); loadStreams();
      renderHr(d.hr_monitoring || []);
      renderLate(d.late_logins_today || []);
      renderActivity(d);
      var st = d.leave_by_stage || {};
      chart("c-stage", "bar", ["At manager", "At HR", "At Admin"], [st.Manager || 0, st.HR || 0, st.Admin || 0],
        { horizontal: true, colours: ["#36BFFA", "#4F5BD5", "#F79009"], empty: "No leave waiting at any stage" });
      chart("c-docs", "doughnut", d.charts.document_status.map(function (r) { return r.status; }),
        d.charts.document_status.map(function (r) { return r.count; }), { legend: "l-docs", empty: "No documents yet" });
      chart("c-reports", "bar", d.charts.report_status.map(function (r) { return r.status; }),
        d.charts.report_status.map(function (r) { return r.count; }), { empty: "No work reports yet" });
      todayReq.then(function () { renderLamps(); renderHealth(); renderAlerts(); });
    }).catch(function (err) {
      ctx.page.innerHTML = '<div class="card">' + RG.errorState(err.message, "retry") + "</div>";
      var retry = document.getElementById("retry");
      if (retry) retry.addEventListener("click", function () { shell(); load(); });
    });
  }

  shell();
  load();
})();
