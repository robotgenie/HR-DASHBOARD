/* manager-dashboard.js - TEAM COMMAND DESK (Manager portal layout).
   MY TEAM is the primary visual: one swimlane per person across the working
   day (10 AM - 6 PM), with check-in, every hourly period, leave, Noon / EOD
   report state and workload. The Manager's own lane is pinned on top and is
   live - Check-In / Check-Out and hourly-update slots work right there.
   Below: task flow, deadlines, team activity, then "My work" tabs.

   Registered with the shared engine (employee-dashboard.js), which still owns
   every personal action. Team data is the Manager's team only (the API
   enforces it): /attendance/hr/today, /leave-requests/summary, /reports,
   /tasks and /hourly-updates?date=today. Per-hour lane colours are drawn from
   the submitted updates and the day's rules; the counts shown are the API's. */
(function () {
  "use strict";
  if (!window.RG || !window.API) return;
  var LAYOUTS = window.RGDashLayouts = window.RGDashLayouts || {};
  var START = 600, HOURS = 8;

  function todayIso() { var d = new Date(); return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0"); }
  function toMin(t) { if (!t) return null; var p = String(t).split(":"); return parseInt(p[0], 10) * 60 + parseInt(p[1], 10); }
  function nowMin() { var n = new Date(); return n.getHours() * 60 + n.getMinutes(); }
  function hhmm(m) { return String(Math.floor(m / 60)).padStart(2, "0") + ":" + String(m % 60).padStart(2, "0"); }

  function fetchTeam() {
    return Promise.all([
      API.get("/attendance/hr/today"),
      API.get("/leave-requests/summary"),
      API.get("/reports", { status: "Submitted", page: 1, page_size: 1 }),
      API.get("/tasks", { limit: 200 }).catch(function () { return { items: [] }; }),
      API.get("/reports", { page: 1, page_size: 10 }).catch(function () { return { items: [] }; }),
      API.get("/hourly-updates", { date: todayIso(), limit: 500 }).catch(function () { return { items: [] }; })
    ]).then(function (res) {
      return { team: { today: res[0], leave: res[1], reports: (res[2].meta || {}).total || 0, tasks: res[3].items || [], recent: res[4].items || [], updates: res[5].items || [] } };
    }, function (err) { return { team: null, teamError: err }; });
  }

  function personState(r) {
    var s = r.session;
    if (s) {
      if (s.checked_out || s.check_out_time) return { key: "out", label: "Checked out" };
      if (s.late_minutes) return { key: "late", label: "Late · " + (s.late_label || "") };
      return { key: "in", label: "Working" };
    }
    if (r.leave_status) return { key: "leave", label: r.leave_status };
    return { key: "none", label: "Not checked in" };
  }

  /* Lane cells for a team member, from submitted updates + the day's rules. */
  function memberCells(r, updates) {
    var done = {};
    updates.filter(function (u) { return u.employee_id === r.employee_id; }).forEach(function (u) { done[u.slot_index] = u; });
    var s = r.session, ci = s ? toMin(s.check_in_time) : null, co = s && s.check_out_time ? toMin(s.check_out_time) : null;
    var lp = r.leave_period || "", wp = s ? s.work_period : "";
    var now = nowMin(), cells = [];
    for (var k = 0; k < HOURS; k++) {
      var a = START + k * 60, b = a + 60, st;
      var onLeave = lp === "Full Day" || (lp === "Morning Half" && b <= 780) || (lp === "Afternoon Half" && a >= 780);
      var outside = (wp === "Second Half" && b <= 780) || (wp === "First Half" && a >= 780);
      if (done[k]) st = "ok";
      else if (onLeave) st = "leave";
      else if (!s) st = b <= now ? "absent" : "up";
      else if (outside || b <= ci || (co !== null && a >= co)) st = "na";
      else if (b <= now) st = "miss";
      else if (a <= now) st = "open";
      else st = "up";
      cells.push({ st: st, u: done[k] });
    }
    return cells;
  }
  var CELL_LABEL = { ok: "Update submitted", leave: "Approved leave", absent: "No attendance", up: "Upcoming", na: "Not applicable", miss: "Due or missed", open: "Current hour" };

  function laneHead(hoursOnly) {
    var now = nowMin();
    var needle = now >= START && now <= START + HOURS * 60 ? '<span class="sw-now" style="left:' + ((now - START) * 100 / (HOURS * 60)) + '%"><i>' + RG.fmt.time(hhmm(now)) + "</i></span>" : "";
    var hrs = "";
    for (var k = 0; k < HOURS; k++) { var h = 10 + k; hrs += "<span>" + ((h % 12) || 12) + (h < 12 ? " AM" : " PM") + "</span>"; }
    return '<div class="sw-row sw-headrow" aria-hidden="true"><div class="sw-who">' + (hoursOnly || "Team member") + '</div><div class="sw-hours">' + hrs + needle + '</div><div class="sw-rep">Noon · EOD</div><div class="sw-load">Workload</div></div>';
  }

  function myLane(data, ex) {
    var W = window.RGWork, st = ex.status, h = ex.hourly;
    if (!st || !st.applicable) return "";
    var s = st.session, state = st.state;
    var slots = (h && h.slots) || [];
    var TONE = { "Submitted": "ok", "Due": "miss", "Missed": "miss", "Open": "open", "Upcoming": "up", "Not Applicable": "na", "Not Checked In": "up" };
    var cells = slots.map(function (x) {
      var tone = TONE[x.status] || "na";
      var attr = x.can_submit ? 'data-hourly-slot="' + x.slot_index + '"' : (x.update_id ? 'data-hourly-view="' + x.update_id + '"' : "disabled");
      return '<button type="button" class="sw-cell c-' + tone + (x.can_submit ? " act" : "") + '" ' + attr + ' title="' + RG.esc(x.label + " · " + (x.reason || x.status)) + '"><span>' + (x.can_submit ? "Submit" : tone === "ok" ? RG.icon("check", 12) : "") + "</span></button>";
    }).join("");
    var rep = st.reports || {};
    function chip(req, done) { return !req ? '<span class="rc na">n/a</span>' : done ? '<span class="rc ok">' + RG.icon("check", 11) + "</span>" : '<span class="rc due">due</span>'; }
    var open = ((h && h.tasks) || []).filter(function (t) { return t.status === "Pending" || t.status === "In Progress"; }).length;
    var ci = s ? toMin(s.check_in_time) : null;
    return '<div class="sw-row sw-me">' +
      '<div class="sw-who"><span class="sw-av">' + RG.avatar({ full_name: data.employee.full_name, photo_path: data.employee.photo_path, id: data.employee.id }) + '<i class="dot d-' + (state === "checked_in" ? (s && s.late_minutes ? "late" : "in") : state === "checked_out" ? "out" : "none") + '"></i></span>' +
        '<span class="sw-name"><b>You</b><em>' + (s ? "In " + W.t12(s.check_in_time) + " · " + W.mins(s.worked_minutes) : "Not checked in") + "</em></span>" +
        '<span class="sw-me-btns"><button type="button" class="btn btn-sm btn-brand" data-check-in' + (st.can_check_in ? "" : " disabled") + ">Check-In</button>" +
        '<button type="button" class="btn btn-sm" data-check-out' + (state === "checked_in" ? "" : " disabled") + ">Check-Out</button></span></div>" +
      '<div class="sw-hours"><div class="sw-cells">' + cells + "</div>" + (ci !== null ? pin(ci, s.late_minutes) : "") + nowLine() + "</div>" +
      '<div class="sw-rep">' + chip(rep.noon_required, rep.noon_submitted) + chip(rep.eod_required, rep.eod_submitted) + "</div>" +
      '<div class="sw-load"><a href="work.html"><b>' + open + "</b> open task" + (open === 1 ? "" : "s") + "</a></div></div>";
  }
  function nowLine() {
    var now = nowMin();
    return now >= START && now <= START + HOURS * 60 ? '<span class="sw-nowl" aria-hidden="true" style="left:' + ((now - START) * 100 / (HOURS * 60)) + '%"></span>' : "";
  }
  function pin(ci, late) {
    if (ci < START || ci > START + HOURS * 60) return "";
    return '<span class="sw-pin' + (late ? " late" : "") + '" style="left:' + ((ci - START) * 100 / (HOURS * 60)) + '%" title="Checked in ' + RG.fmt.time(hhmm(ci)) + '"></span>';
  }

  function memberLane(r, team, me) {
    var st = personState(r), cells = memberCells(r, team.updates);
    var s = r.session, ci = s ? toMin(s.check_in_time) : null;
    var tasks = team.tasks.filter(function (t) { return t.employee_id === r.employee_id && t.status !== "Cancelled"; });
    var open = tasks.filter(function (t) { return t.status === "Pending" || t.status === "In Progress"; });
    var avg = open.length ? Math.round(open.reduce(function (x, t) { return x + Number(t.progress_percent || 0); }, 0) / open.length) : 0;
    function rc(v) { return v === "Not Required" ? '<span class="rc na" title="Not required">n/a</span>' : (v === "Submitted" || v === "Reviewed") ? '<span class="rc ok" title="' + v + '">' + RG.icon("check", 11) + "</span>" : '<span class="rc due" title="' + RG.esc(v) + '">' + (v === "Pending" ? "due" : RG.esc(v).toLowerCase()) + "</span>"; }
    var maxOpen = Math.max.apply(null, (team.today.items || []).map(function (x) {
      return team.tasks.filter(function (t) { return t.employee_id === x.employee_id && (t.status === "Pending" || t.status === "In Progress"); }).length;
    }).concat([1]));
    var today = todayIso();
    return '<details class="sw-lane">' +
      '<summary class="sw-row">' +
        '<div class="sw-who"><span class="sw-av">' + RG.avatar({ full_name: r.employee_name }) + '<i class="dot d-' + st.key + '"></i></span>' +
          '<span class="sw-name"><b>' + RG.esc(r.employee_name) + "</b><em>" + RG.esc(st.label) + (r.person_type === "Intern" ? ' · <span class="tag">Intern</span>' : "") + "</em></span>" +
          '<span class="sw-chev" aria-hidden="true">' + RG.icon("chevron", 14) + "</span></div>" +
        '<div class="sw-hours"><div class="sw-cells">' + cells.map(function (c, k) {
          return '<span class="sw-cell c-' + c.st + '" title="' + (10 + k) + ":00 · " + CELL_LABEL[c.st] + (c.u && c.u.task_title ? " · " + RG.esc(c.u.task_title) : "") + '">' + (c.st === "ok" ? RG.icon("check", 12) : "") + "</span>";
        }).join("") + "</div>" + (ci !== null ? pin(ci, s.late_minutes) : "") + nowLine() + "</div>" +
        '<div class="sw-rep">' + rc(r.noon_report) + rc(r.eod_report) + "</div>" +
        '<div class="sw-load"><span class="wl"><span style="width:' + (open.length * 100 / maxOpen) + '%"></span></span><b>' + open.length + "</b><em>" + (open.length ? avg + "% avg" : "free") + "</em></div>" +
      "</summary>" +
      '<div class="sw-expand">' +
        '<div class="sw-x-facts"><span>Hourly <b>' + r.hourly_submitted + "/" + r.hourly_applicable + "</b>" + (r.hourly_missing ? ' · <b class="bad">' + r.hourly_missing + " due</b>" : "") + "</span>" +
          "<span>Check-in <b>" + (s ? RG.fmt.time(s.check_in_time) : "—") + "</b>" + (s && s.late_minutes ? ' <b class="bad">' + RG.esc(s.late_label) + " late</b>" : "") + "</span>" +
          "<span>Check-out <b>" + (s && s.check_out_time ? RG.fmt.time(s.check_out_time) : "—") + "</b></span>" +
          (r.leave_status ? "<span>Leave <b>" + RG.esc(r.leave_status) + "</b></span>" : "") +
          "<span>" + RG.esc(r.department || "") + "</span></div>" +
        (tasks.length ? '<ul class="sw-x-tasks">' + tasks.slice(0, 6).map(function (t) {
          var od = t.due_date && t.status !== "Completed" && t.due_date < today;
          return '<li><span class="st s-' + t.status.replace(" ", "-").toLowerCase() + '"></span><b>' + RG.esc(t.title) + "</b>" +
            '<span class="bar thin"><span style="width:' + Number(t.progress_percent || 0) + '%"></span></span><em' + (od ? ' class="bad"' : "") + ">" +
            (t.status === "Completed" ? "Done" : t.due_date ? (od ? "Overdue · " : "Due ") + RG.fmt.date(t.due_date) : "No due date") + "</em></li>";
        }).join("") + "</ul>" : '<p class="small muted">No tasks assigned yet.</p>') +
        '<div class="row wrap"><a class="btn btn-sm" href="person.html?id=' + r.employee_id + '">' + RG.icon("eye", 14) + " Open " + RG.esc(r.employee_name.split(" ")[0]) + "</a>" +
          '<a class="btn btn-sm" href="team-tasks.html">' + RG.icon("plus", 14) + " Assign task</a>" +
          '<a class="btn btn-sm" href="team-reports.html">Reports</a></div>' +
      "</div></details>";
  }

  function taskFlow(team, me) {
    var today = todayIso();
    var list = team.tasks.filter(function (t) { return t.employee_id !== me && t.status !== "Cancelled"; });
    var cols = [["Pending", "To do"], ["In Progress", "In progress"], ["Completed", "Completed"]];
    var total = list.length || 1;
    return '<div class="tf-bar" aria-hidden="true">' + cols.map(function (c) {
        var n = list.filter(function (t) { return t.status === c[0]; }).length;
        return '<span class="s-' + c[0].replace(" ", "-").toLowerCase() + '" style="flex:' + (n || 0.0001) + '"></span>';
      }).join("") + "</div>" +
      '<div class="tf-cols">' + cols.map(function (c) {
        var rows = list.filter(function (t) { return t.status === c[0]; });
        if (c[0] === "Completed") rows.sort(function (a, b) { return String(b.completed_at || "") < String(a.completed_at || "") ? -1 : 1; });
        return '<div class="tf-col"><h4><span class="st s-' + c[0].replace(" ", "-").toLowerCase() + '"></span>' + c[1] + "<b>" + rows.length + "</b></h4>" +
          (rows.length ? "<ul>" + rows.slice(0, 4).map(function (t) {
            var od = t.due_date && t.status !== "Completed" && t.due_date < today;
            return '<li class="' + (od ? "od" : "") + '"><a href="team-tasks.html"><b>' + RG.esc(t.title) + "</b><span>" + RG.esc((t.employee_name || "").split(" ")[0]) + " · " +
              (t.target ? t.completed + "/" + t.target : Number(t.progress_percent || 0) + "%") + "</span></a></li>";
          }).join("") + (rows.length > 4 ? '<li class="more"><a href="team-tasks.html">+ ' + (rows.length - 4) + " more</a></li>" : "") + "</ul>" : '<p class="tf-empty">Nothing here</p>') + "</div>";
      }).join("") + "</div>";
  }

  function deadlines(team, me) {
    var today = todayIso();
    var rows = team.tasks.filter(function (t) { return t.employee_id !== me && t.due_date && (t.status === "Pending" || t.status === "In Progress"); })
      .sort(function (a, b) { return a.due_date < b.due_date ? -1 : 1; }).slice(0, 8);
    if (!rows.length) return RG.emptyState("No upcoming deadlines", "Open team tasks with a due date appear here.", "", "calendar");
    return '<ol class="dl-list">' + rows.map(function (t) {
      var d = new Date(t.due_date + "T00:00:00"), diff = Math.round((d - new Date(today + "T00:00:00")) / 86400000);
      var cls = diff < 0 ? "od" : diff === 0 ? "td" : diff <= 2 ? "soon" : "";
      return '<li class="' + cls + '"><span class="dl-date"><b>' + d.getDate() + "</b>" + RG.MONTHS[d.getMonth()].slice(0, 3) + "</span>" +
        '<span class="dl-x"><b>' + RG.esc(t.title) + "</b><em>" + RG.esc(t.employee_name || "") + " · " + Number(t.progress_percent || 0) + "% done</em></span>" +
        '<span class="dl-tag">' + (diff < 0 ? Math.abs(diff) + "d overdue" : diff === 0 ? "Today" : diff === 1 ? "Tomorrow" : "in " + diff + "d") + "</span></li>";
    }).join("") + "</ol>";
  }

  function activity(team) {
    var ev = [];
    var day = String(team.today.date || todayIso());
    function at(v) { return new Date(/Z|[+-]\d{2}:?\d{2}$/.test(String(v)) ? v : v + "Z"); }
    (team.today.items || []).forEach(function (r) {
      var s = r.session; if (!s) return;
      if (s.check_in_time) ev.push({ at: new Date(day + "T" + s.check_in_time), icon: "user", tone: s.late_minutes ? "warn" : "ok", text: "<b>" + RG.esc(r.employee_name) + "</b> checked in" + (s.late_minutes ? " · " + RG.esc(s.late_label) + " late" : "") });
      if (s.check_out_time) ev.push({ at: new Date(day + "T" + s.check_out_time), icon: "logout", tone: "", text: "<b>" + RG.esc(r.employee_name) + "</b> checked out" });
    });
    (team.updates || []).forEach(function (u) { if (u.submitted_at) ev.push({ at: at(u.submitted_at), icon: "bell", tone: "info", text: "<b>" + RG.esc(u.employee_name || "") + "</b> hourly update · " + RG.esc(u.slot_label || "") }); });
    (team.recent || []).forEach(function (rep) { if (rep.submitted_at) ev.push({ at: at(rep.submitted_at), icon: "clipboard", tone: rep.status === "Reviewed" ? "ok" : "info", text: "<b>" + RG.esc(rep.employee_name || "") + "</b> submitted " + RG.esc(rep.report_type) + " report" }); });
    (team.tasks || []).forEach(function (t) { if (t.status === "Completed" && t.completed_at) ev.push({ at: at(t.completed_at), icon: "check", tone: "ok", text: "<b>" + RG.esc(t.employee_name || "") + "</b> completed “" + RG.esc(t.title) + "”" }); });
    ev = ev.filter(function (e) { return !isNaN(e.at) && e.at.getTime() <= Date.now() + 60000; }).sort(function (a, b) { return b.at - a.at; }).slice(0, 10);
    if (!ev.length) return RG.emptyState("No team activity yet", "Check-ins, updates, reports and completed tasks appear as they happen.", "", "clock");
    var last = "";
    return '<ol class="act">' + ev.map(function (e) {
      var k = e.at.toDateString(), head = "";
      if (k !== last) { last = k; head = '<li class="act-day">' + (k === new Date().toDateString() ? "Today" : RG.fmt.date(e.at)) + "</li>"; }
      return head + '<li class="ev ' + e.tone + '"><span class="t">' + RG.fmt.time(hhmm(e.at.getHours() * 60 + e.at.getMinutes())) + '</span><span class="ic">' + RG.icon(e.icon, 12) + '</span><span class="tx">' + e.text + "</span></li>";
    }).join("") + "</ol>";
  }

  LAYOUTS.manager = {
    fetch: fetchTeam,
    render: function (data, ex, more, B) {
      var emp = data.employee, k = data.kpis, st = ex.status, hourly = ex.hourly, team = more.team;
      var rows = team ? (team.today.items || []) : [];
      var states = rows.map(personState);
      function c(kk) { return states.filter(function (s) { return s.key === kk; }).length; }
      var waiting = team ? team.leave.awaiting_me : 0;
      var t = team ? team.today.totals : null;

      var head = '<header class="sw-head"><div class="sw-title"><span class="sw-kicker">Team Command Desk · ' + RG.esc(new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long" })) + "</span>" +
          "<h1>My Team</h1>" +
          (team ? '<div class="sw-avail">' +
            '<span class="av-n"><b>' + rows.length + "</b> people</span>" +
            '<span class="av ok"><i></i><b>' + (c("in") + c("late")) + "</b> working</span>" +
            '<span class="av warn"><i></i><b>' + c("late") + "</b> late</span>" +
            '<span class="av leave"><i></i><b>' + c("leave") + "</b> on leave</span>" +
            '<span class="av none"><i></i><b>' + c("none") + "</b> not in</span>" +
            '<span class="av out"><i></i><b>' + c("out") + "</b> checked out</span></div>" : "") + "</div>" +
        '<div class="sw-actions">' +
          '<a class="sw-act" href="team-leave.html">' + RG.icon("calendar", 16) + "<span>Leave to decide</span><b" + (waiting ? ' class="hot"' : "") + ">" + waiting + "</b></a>" +
          '<a class="sw-act" href="team-reports.html">' + RG.icon("clipboard", 16) + "<span>Reports to review</span><b" + (team && team.reports ? ' class="hot"' : "") + ">" + (team ? team.reports : 0) + "</b></a>" +
          '<a class="sw-act" href="team-monitor.html?tab=hourly">' + RG.icon("bell", 16) + "<span>Hourly due</span><b" + (t && t.hourly_due ? ' class="hot"' : "") + ">" + (t ? t.hourly_due : 0) + "</b></a>" +
          '<a class="btn btn-brand" href="team-tasks.html">' + RG.icon("plus", 16) + " Assign task</a>" +
        "</div></header>";

      var board = '<section class="sw-board" aria-label="Team swimlanes">' + laneHead() + myLane(data, ex) +
        (team ? (rows.length ? rows.map(function (r) { return memberLane(r, team, emp.id); }).join("")
            : '<div class="sw-empty">' + RG.emptyState("No team members yet", "HR or the Admin assigns employees and interns to you.", "", "users") + "</div>")
          : '<div class="sw-empty">' + RG.errorState((more.teamError && more.teamError.message) || "Team data could not be loaded.") + "</div>") +
        '<footer class="sw-legend"><span><i class="c-ok"></i>Update submitted</span><span><i class="c-open"></i>Current hour</span><span><i class="c-miss"></i>Due / missed</span>' +
          '<span><i class="c-leave"></i>Leave</span><span><i class="c-na"></i>Not applicable</span><span><i class="c-up"></i>Upcoming</span><span><i class="pin"></i>Check-in</span>' +
          '<a href="team-monitor.html">Team attendance &amp; work ' + RG.icon("arrow", 13) + "</a></footer></section>";

      var under = team ? '<div class="sw-under">' +
          '<section class="sw-panel"><header><h3>' + RG.icon("grid", 15) + ' Task flow</h3><a href="team-tasks.html">Team tasks</a></header><div class="inner">' + taskFlow(team, emp.id) + "</div></section>" +
          '<section class="sw-panel"><header><h3>' + RG.icon("flag", 15) + ' Deadlines</h3><a href="team-tasks.html">All</a></header><div class="inner">' + deadlines(team, emp.id) + "</div></section>" +
          '<section class="sw-panel"><header><h3>' + RG.icon("pulse", 15) + ' Team activity</h3><a href="team-reports.html">Team reports</a></header><div class="inner">' + activity(team) + "</div></section>" +
        "</div>" : "";

      var mine = '<section class="sw-mine" aria-labelledby="mw-h"><header><h2 id="mw-h">' + RG.icon("user", 16) + " My work</h2>" +
          '<div class="mw-tabs" role="tablist" aria-label="My work">' +
            '<button role="tab" aria-selected="true" data-mw="day" id="mw-t-day" aria-controls="mw-day">My day</button>' +
            '<button role="tab" aria-selected="false" data-mw="rec" id="mw-t-rec" aria-controls="mw-rec" tabindex="-1">Pay &amp; records</button>' +
            '<button role="tab" aria-selected="false" data-mw="not" id="mw-t-not" aria-controls="mw-not" tabindex="-1">Notifications' + (k.unread_notifications ? " (" + k.unread_notifications + ")" : "") + "</button></div></header>" +
        '<div class="mw-panel" role="tabpanel" id="mw-day" aria-labelledby="mw-t-day"><div class="mw-grid">' +
          B.card("", "My attendance", "work.html", "Tasks &amp; hourly", B.attendance(st) + '<div class="inner">' + B.leaveReports(st, ex.leaves, null, true) + "</div>", "clock") +
          B.card("", "My tasks &amp; hourly updates", "work.html", "History", '<div class="inner">' + B.hourly(st, hourly) + '<div class="mt-4">' + B.tasks(st, hourly) + "</div></div>", "calendar") +
          B.card("", "My daily reports", "daily-reports.html", RG.fmt.date(data.daily_report.date || todayIso()), '<div class="inner">' + B.reportCard(data.daily_report) + "</div>", "clipboard") +
          B.card("", "Today’s meetings", "meetings.html", "All meetings", '<div class="inner">' + B.meetings(data.todays_meetings) + "</div>", "video") +
        "</div></div>" +
        '<div class="mw-panel" role="tabpanel" id="mw-rec" aria-labelledby="mw-t-rec" hidden><div class="mw-grid">' +
          B.card("", "Latest salary", "salary-slips.html", "All payslips", '<div class="inner">' + B.pay(data.latest_salary) + "</div>", "money") +
          B.card("", "Document progress", "documents.html", RG.esc(k.documents_label), '<div class="inner">' + B.docs(data) + "</div>", "doc") +
          B.card("", "Me &amp; my records", "profile.html", "Profile", '<div class="inner">' + B.identity(data) + "</div>", "user") +
        "</div></div>" +
        '<div class="mw-panel" role="tabpanel" id="mw-not" aria-labelledby="mw-t-not" hidden>' +
          B.card("", "Notifications", "notifications.html", "Notification centre", B.notifs(data), "bell") + "</div>" +
      "</section>";
      return '<div class="sw">' + head + board + under + mine + "</div>";
    },
    after: function () {
      var page = document.getElementById("page");
      if (page.dataset.mwWired) return;
      page.dataset.mwWired = "1";
      function show(key) {
        page.querySelectorAll("[data-mw]").forEach(function (b) {
          var on = b.dataset.mw === key;
          b.setAttribute("aria-selected", on ? "true" : "false"); b.tabIndex = on ? 0 : -1;
          var p = document.getElementById("mw-" + b.dataset.mw); if (p) p.hidden = !on;
        });
      }
      RG.on(page, "[data-mw]", "click", function (e, b) { show(b.dataset.mw); });
      RG.on(page, ".mw-tabs", "keydown", function (e) {
        if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
        var tabs = Array.prototype.slice.call(page.querySelectorAll("[data-mw]"));
        var i = tabs.indexOf(document.activeElement); if (i < 0) return;
        var n = tabs[(i + (e.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length]; n.focus(); show(n.dataset.mw);
      });
      // Buttons inside a lane summary must act, not toggle the lane.
      RG.on(page, ".sw-lane summary a, .sw-lane summary button", "click", function (e) { e.stopPropagation(); });
    }
  };
})();
