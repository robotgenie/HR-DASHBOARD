/* intern-dashboard.js - PROFESSIONAL GROWTH JOURNEY (Intern portal layout).
   The internship drawn as a timeline: from the joining week to the coming
   weeks, with milestone flags, every assigned task as a bar (start -> due /
   completion, filled by progress), feedback pins where a report was reviewed,
   this month's attendance as a day strip, and a "today" marker. Below it:
   where you are (stage), today (check-in, hourly, reports, leave), current
   work, feedback, sessions and growth signals, then records.

   Registered with the shared engine (employee-dashboard.js), which owns every
   action. Extra data is read-only: /hierarchy/me, /employees/me,
   /tasks?mine, /reports?mine&status=Reviewed, /attendance/me. Milestones are
   derived only from recorded facts - nothing is invented. */
(function () {
  "use strict";
  var LAYOUTS = window.RGDashLayouts = window.RGDashLayouts || {};
  var DAY = 86400000, PX = 24;

  function d0(v) { if (!v) return null; var s = String(v); var d = new Date(s.length === 10 ? s + "T00:00:00" : (/Z|[+-]\d{2}:?\d{2}$/.test(s) ? s : s + "Z")); if (isNaN(d)) return null; d.setHours(0, 0, 0, 0); return d; }
  function pct(n, d) { return d ? Math.round(n * 100 / d) : 0; }

  LAYOUTS.intern = {
    fetch: function () {
      function safe(p, fb) { return p.catch(function () { return fb; }); }
      return Promise.all([
        safe(API.get("/hierarchy/me"), null),
        safe(API.get("/employees/me"), null),
        safe(API.get("/tasks", { mine: true, limit: 100 }), { items: [] }),
        safe(API.get("/reports", { mine: true, status: "Reviewed", page: 1, page_size: 20 }), { items: [], meta: { total: 0 } }),
        safe(API.get("/attendance/me"), null)
      ]).then(function (r) {
        return { line: r[0], me: r[1], tasks: (r[2] && r[2].items) || [], reviewed: r[3] || { items: [] }, month: r[4] };
      });
    },

    render: function (data, ex, more, B) {
      var emp = data.employee, k = data.kpis, me = more.me || {}, line = more.line || {};
      var st = ex.status, hourly = ex.hourly;
      var tasks = (more.tasks || []).filter(function (t) { return t.status !== "Cancelled"; });
      var done = tasks.filter(function (t) { return t.status === "Completed"; });
      var active = tasks.filter(function (t) { return t.status === "In Progress"; });
      var todo = tasks.filter(function (t) { return t.status === "Pending"; });
      var reviewed = more.reviewed.items || [];
      var reviewedTotal = (more.reviewed.meta && more.reviewed.meta.total) || reviewed.length;
      var docs = (data.document_progress || []).filter(function (d) { return d.is_required; });
      var docsVerified = docs.filter(function (d) { return d.status === "Verified"; }).length;
      var today = new Date(); today.setHours(0, 0, 0, 0);
      var joined = d0(me.joining_date);
      var week = joined ? Math.max(1, Math.floor((today - joined) / DAY / 7) + 1) : null;

      /* ---------- milestones (recorded facts only) ---------- */
      var firstTask = tasks.slice().sort(function (a, b) { return a.task_date < b.task_date ? -1 : 1; })[0];
      var firstDone = done.slice().sort(function (a, b) { return String(a.completed_at) < String(b.completed_at) ? -1 : 1; })[0];
      var firstReview = reviewed.slice().sort(function (a, b) { return String(a.reviewed_at) < String(b.reviewed_at) ? -1 : 1; })[0];
      var steps = [
        { key: "Joined", done: !!joined, when: joined, note: joined ? RG.fmt.date(me.joining_date) : "Joining date not set", href: "profile.html" },
        { key: "Profile complete", done: Number(k.profile_completion) >= 100, note: Math.round(k.profile_completion) + "% complete", href: "profile.html" },
        { key: "Documents verified", done: docs.length > 0 && docsVerified === docs.length, note: docsVerified + " of " + docs.length + " required verified", href: "documents.html" },
        { key: "Employee ID issued", done: me.id_card_status === "Approved", when: d0(me.id_card_approved_at), note: me.id_card_status ? "ID " + me.id_card_status.toLowerCase() : "Request it from your profile", href: "profile.html" },
        { key: "First assignment", done: tasks.length > 0, when: firstTask ? d0(firstTask.task_date) : null, note: firstTask ? RG.fmt.date(firstTask.task_date) : "Waiting for your first task", href: "work.html" },
        { key: "Work delivered", done: done.length > 0, when: firstDone ? d0(firstDone.completed_at) : null, note: done.length + " of " + tasks.length + " tasks completed", href: "work.html" },
        { key: "Manager feedback", done: reviewedTotal > 0, when: firstReview ? d0(firstReview.reviewed_at) : null, note: reviewedTotal ? reviewedTotal + " reviewed report" + (reviewedTotal === 1 ? "" : "s") : "No reviews yet", href: "daily-reports.html" }
      ];
      var current = -1;
      for (var i = 0; i < steps.length; i++) { if (!steps[i].done) { current = i; break; } }
      var completeCount = steps.filter(function (s) { return s.done; }).length;
      var journeyPct = pct(completeCount, steps.length);

      /* ---------- header ---------- */
      var mgr = line.reporting_manager, hr = line.reporting_hr;
      function guide(p, role) {
        return '<div class="jg"><span class="jg-r">' + role + "</span>" + (p
          ? '<span class="jg-p">' + RG.avatar({ full_name: p.full_name }, "sm") + "<b>" + RG.esc(p.full_name) + "</b></span><em>" + RG.esc(p.designation || "") + "</em>"
          : "<b>Not assigned yet</b>") + "</div>";
      }
      var C = 2 * Math.PI * 26;
      var head = '<header class="jt-head">' +
        '<div class="jt-id"><span class="jt-kicker">' + RG.icon("flag", 14) + " Internship journey" + (week ? " · week " + week : "") + "</span>" +
          "<h1>" + RG.esc(emp.full_name) + "</h1>" +
          '<div class="jt-meta">' + (emp.internship_background ? '<span class="pill">' + RG.esc(emp.internship_background) + "</span>" : "") +
            "<span>" + RG.esc(emp.designation || "Intern") + "</span><span>" + RG.esc(emp.department || "") + "</span><span>ID " + RG.esc(emp.employee_code) + "</span></div></div>" +
        '<div class="jt-guides">' + guide(mgr, "Reporting manager") + guide(hr, "Reporting HR") + "</div>" +
        '<div class="jt-ring" role="img" aria-label="' + completeCount + " of " + steps.length + ' milestones reached"><svg width="64" height="64" viewBox="0 0 64 64" aria-hidden="true"><circle cx="32" cy="32" r="26" fill="none" stroke="#E6E3F0" stroke-width="6"/>' +
          '<circle cx="32" cy="32" r="26" fill="none" stroke="#6D3FE0" stroke-width="6" stroke-linecap="round" stroke-dasharray="' + (C * journeyPct / 100) + " " + C + '" transform="rotate(-90 32 32)"/></svg>' +
          "<div><b>" + completeCount + "/" + steps.length + "</b><span>milestones</span></div></div>" +
      "</header>";

      /* ---------- the timeline canvas ---------- */
      var start = joined ? new Date(joined) : new Date(today.getTime() - 28 * DAY);
      tasks.forEach(function (t) { var a = d0(t.task_date); if (a && a < start) start = a; });
      start = new Date(start.getTime() - ((start.getDay() + 6) % 7) * DAY - 7 * DAY);
      var end = new Date(today.getTime() + 21 * DAY);
      tasks.forEach(function (t) { var b = d0(t.due_date); if (b && b > end) end = new Date(b.getTime() + 7 * DAY); });
      var days = Math.round((end - start) / DAY);
      var W = days * PX;
      function x(d) { return Math.round((d - start) / DAY * PX); }

      var axis = "", grid = "";
      for (var w = 0; w * 7 < days; w++) {
        var ws = new Date(start.getTime() + w * 7 * DAY);
        var wk = joined ? Math.floor((ws - joined) / DAY / 7) + 1 : null;
        axis += '<span class="jx-w" style="left:' + (w * 7 * PX) + "px;width:" + (7 * PX) + 'px"><b>' + (wk && wk > 0 ? "W" + wk : "") + "</b>" + ws.getDate() + " " + RG.MONTHS[ws.getMonth()].slice(0, 3) + "</span>";
        grid += '<span class="jx-g" style="left:' + (w * 7 * PX) + 'px"></span>';
      }
      var flags = steps.filter(function (s) { return s.done && s.when; }).map(function (s) {
        return '<a class="jf" href="' + s.href + '" style="left:' + x(s.when) + 'px" title="' + RG.esc(s.key + " · " + RG.fmt.date(s.when)) + '"><i>' + RG.icon("flag", 11) + "</i><span>" + RG.esc(s.key) + "</span></a>";
      }).join("");
      var lanes = [], bars = "";
      tasks.slice().sort(function (a, b) { return a.task_date < b.task_date ? -1 : 1; }).forEach(function (t) {
        var a = d0(t.task_date) || today, b = d0(t.completed_at) || d0(t.due_date) || today;
        if (b < a) b = a;
        var x0 = x(a), x1 = x(b) + PX;
        var lane = 0; while (lanes[lane] !== undefined && lanes[lane] > x0 - 6) lane++;
        var bw = Math.max(PX * 2, x1 - x0), narrow = bw < 230;
        lanes[lane] = x0 + bw + (narrow ? 12 + Math.min(260, t.title.length * 7) : 0);
        var p = Number(t.progress_percent || 0);
        var od = t.due_date && t.status !== "Completed" && d0(t.due_date) < today;
        bars += '<a class="jb s-' + t.status.replace(" ", "-").toLowerCase() + (od ? " od" : "") + (narrow ? " narrow" : "") + '" href="work.html" style="left:' + x0 + "px;width:" + bw + "px;top:" + (lane * 40) + 'px" title="' +
          RG.esc(t.title + " · " + t.status + " · " + p + "%" + (t.due_date ? " · due " + RG.fmt.date(t.due_date) : "")) + '">' +
          '<span class="jb-fill" style="width:' + p + '%"></span><b>' + RG.esc(t.title) + "</b><em>" + (t.target ? t.completed + "/" + t.target + (t.unit ? " " + RG.esc(t.unit) : "") : p + "%") + "</em></a>" +
          (narrow ? '<span class="jb-out" style="left:' + (x0 + bw + 8) + "px;top:" + (lane * 40) + 'px" aria-hidden="true">' + RG.esc(t.title) + "</span>" : "");
      });
      var laneH = Math.max(1, lanes.length) * 40;
      var pins = reviewed.map(function (r) {
        var d = d0(r.reviewed_at) || d0(r.report_date); if (!d) return "";
        return '<span class="jp" style="left:' + x(d) + 'px" title="' + RG.esc(r.report_type + " report " + RG.fmt.date(r.report_date) + " reviewed" + (r.reviewed_by_name ? " by " + r.reviewed_by_name : "") + (r.review_notes ? ": " + r.review_notes : "")) + '">' + RG.icon("message", 12) + "</span>";
      }).join("");
      var ATT = { "Full Day": "ok", "First Half": "half", "Second Half": "half", "Absent": "bad", "Full Day Leave": "leave", "Weekly Off": "off" };
      var strip = ((more.month && more.month.days) || []).map(function (dd) {
        var d = d0(dd.date); if (!d || d > today) return "";
        var c = ATT[dd.attendance] || (dd.leave_status ? "leave" : "none");
        return '<span class="ja ' + c + '" style="left:' + x(d) + 'px" title="' + RG.esc(RG.fmt.date(dd.date) + " · " + dd.attendance) + '"></span>';
      }).join("");
      var todayX = x(today);
      var canvas = '<section class="jt-canvas" aria-label="Internship timeline">' +
        '<div class="jt-legend"><span><i class="l-flag"></i>Milestone</span><span><i class="l-active"></i>In progress</span><span><i class="l-todo"></i>To do</span><span><i class="l-done"></i>Completed</span><span><i class="l-pin"></i>Feedback</span><span><i class="l-att"></i>Attended</span><span><i class="l-abs"></i>Absent</span>' +
          '<button type="button" class="btn btn-sm" data-jt-today>' + RG.icon("target", 14) + " Today</button></div>" +
        '<div class="jt-scroll" tabindex="0" aria-label="Timeline, scroll horizontally"><div class="jt-track" style="width:' + W + 'px">' +
          '<div class="jx">' + axis + "</div>" +
          '<div class="jt-body">' + grid +
            '<div class="jrow jflags"><span class="jrow-l">Milestones</span>' + flags + "</div>" +
            '<div class="jrow jbars" style="height:' + (laneH + 8) + 'px"><span class="jrow-l">Assignments</span>' + (bars || '<span class="jt-none" style="left:' + Math.max(0, todayX - 260) + 'px">No assignments yet — they will appear here as bars.</span>') + "</div>" +
            '<div class="jrow jpins"><span class="jrow-l">Feedback</span>' + pins + "</div>" +
            '<div class="jrow jatt"><span class="jrow-l">Attendance</span>' + strip + "</div>" +
            '<div class="jt-today" style="left:' + todayX + 'px"><span>Today</span></div>' +
          "</div></div></div></section>";

      /* ---------- where you are ---------- */
      var stage = '<section class="jt-stage" aria-label="Milestones"><ol>' + steps.map(function (s, i) {
        var cls = s.done ? "done" : (i === current ? "current" : "next");
        return '<li class="' + cls + '"><a href="' + s.href + '"' + (i === current ? ' aria-current="step"' : "") + '><span class="n">' + (s.done ? RG.icon("check", 12) : i + 1) + "</span>" +
          "<b>" + RG.esc(s.key) + "</b><em>" + RG.esc(s.note) + "</em></a></li>";
      }).join("") + "</ol>" +
        (current >= 0 ? '<p class="jt-next">' + RG.icon("arrow", 14) + " <b>Next milestone:</b> " + RG.esc(steps[current].key) + " — " + RG.esc(steps[current].note) + ' <a href="' + steps[current].href + '">Go</a></p>'
          : '<p class="jt-next">' + RG.icon("check", 14) + " Every recorded milestone is complete.</p>") + "</section>";

      /* ---------- now ---------- */
      function taskRow(t) {
        var p = Number(t.progress_percent || 0);
        var od = t.due_date && t.status !== "Completed" && d0(t.due_date) < today;
        return '<li class="jw"><div class="jw-t"><b>' + RG.esc(t.title) + "</b>" + RG.badge(t.status) + "</div>" +
          '<div class="jw-m">From ' + RG.esc(t.assigned_by || "your manager") + (t.due_date ? " · due " + RG.fmt.date(t.due_date) : "") + (od ? ' · <span class="od">overdue</span>' : "") + "</div>" +
          '<div class="jw-p"><span class="bar thin"><span style="width:' + p + '%"></span></span><i>' + (t.target ? t.completed + "/" + t.target + (t.unit ? " " + RG.esc(t.unit) : "") : p + "%") + "</i></div></li>";
      }
      var work = tasks.length
        ? (active.length ? '<h4 class="jh">Learning now</h4><ul class="jws">' + active.map(taskRow).join("") + "</ul>" : "") +
          (todo.length ? '<h4 class="jh">Up next</h4><ul class="jws">' + todo.map(taskRow).join("") + "</ul>" : "") +
          (done.length ? '<h4 class="jh">Completed</h4><ul class="jws done">' + done.slice(0, 3).map(taskRow).join("") + "</ul>" : "")
        : RG.emptyState("No assignments yet", "Tasks your manager or HR assigns appear here with your progress.", "", "book");

      var m = more.month || {}, a = m.attendance || {}, rr = m.reports || {};
      var req = (rr.noon_required || 0) + (rr.eod_required || 0);
      function signal(label, v, of, note) {
        var p = pct(v, of);
        return '<div class="sg"><div class="sg-t"><span>' + label + "</span><b>" + (of ? p + "%" : "—") + '</b></div><div class="bar"><span style="width:' + p + '%"></span></div><em>' + note + "</em></div>";
      }
      var growth = '<div class="inner sgs">' +
        signal("Attendance this month", a.days_worked || 0, a.working_days_elapsed || 0, (a.days_worked || 0) + " of " + (a.working_days_elapsed || 0) + " working days so far") +
        signal("Report consistency", rr.submitted_total || 0, req, (rr.submitted_total || 0) + " of " + req + " Noon/EOD reports filed") +
        signal("Assignments completed", done.length, tasks.length, done.length + " of " + tasks.length + " tasks") +
        signal("Hourly updates today", hourly ? hourly.submitted_count : 0, hourly ? hourly.applicable_count : 0, (hourly ? hourly.submitted_count : 0) + " of " + (hourly ? hourly.applicable_count : 0) + " applicable hours") +
        '<a class="btn btn-sm" href="monthly-report.html">Full attendance &amp; progress</a></div>';

      var feedback = reviewed.length
        ? '<ul class="jfb">' + reviewed.slice(0, 4).map(function (r) {
            return "<li><div class=\"jfb-t\"><b>" + RG.esc(r.report_type) + " report · " + RG.fmt.date(r.report_date) + "</b>" + RG.badge("Reviewed") + "</div>" +
              (r.review_notes ? "<blockquote>“" + RG.esc(r.review_notes) + "”</blockquote>" : '<p class="small muted mb-0">Reviewed — no written notes.</p>') +
              '<div class="small muted">' + (r.reviewed_by_name ? RG.esc(r.reviewed_by_name) + " · " : "") + (r.reviewed_at ? RG.fmt.date(r.reviewed_at) : "") + "</div></li>";
          }).join("") + "</ul>"
        : RG.emptyState("No feedback yet", "When your manager or HR reviews a Noon or EOD report, their notes appear here.", "", "message");

      var todayCard = '<div class="jt-today-card">' + B.attendance(st) +
        '<div class="inner">' + B.hourly(st, hourly) + "</div>" +
        '<div class="inner jt-split"><div><h4 class="jh">Leave</h4>' + (st && st.applicable ? B.leaveReports(st, ex.leaves, null, true) : "") + "</div>" +
          '<div><h4 class="jh">Today’s reports</h4>' + B.reportCard(data.daily_report) + "</div></div></div>";

      return '<div class="jt">' + head + canvas + stage +
        '<div class="jt-grid">' +
          B.card("jt-today-box", "Today", "daily-reports.html", "Daily reports", todayCard, "sun") +
          '<div class="jt-col">' +
            B.card("", "Assigned work &amp; learning", "work.html", "Tasks &amp; hourly", '<div class="inner">' + work + "</div>", "book") +
            B.card("", "Feedback from your guides", "daily-reports.html", "My reports", '<div class="inner">' + feedback + "</div>", "message") +
          "</div>" +
          '<div class="jt-col">' +
            B.card("", "Growth signals", "", "", growth, "pulse") +
            B.card("", "Upcoming sessions", "meetings.html", "All sessions", '<div class="inner">' + B.meetings(data.todays_meetings, "No sessions for your department today") + "</div>", "video") +
          "</div>" +
        "</div>" +
        '<div class="jt-records">' +
          B.card("", "Documents", "documents.html", RG.esc(k.documents_label), '<div class="inner">' + B.docs(data) + "</div>", "doc") +
          B.card("", "Salary slips", "salary-slips.html", "All slips", '<div class="inner">' + B.pay(data.latest_salary) + "</div>", "money") +
          B.card("", "Notifications", "notifications.html", (k.unread_notifications ? k.unread_notifications + " unread" : "See all"), B.notifs(data), "bell") +
        "</div></div>";
    },

    after: function () {
      var page = document.getElementById("page");
      var sc = page.querySelector(".jt-scroll"), t = page.querySelector(".jt-today");
      if (sc && t) sc.scrollLeft = Math.max(0, t.offsetLeft - sc.clientWidth * 0.7);
      if (!page.dataset.jtWired) {
        page.dataset.jtWired = "1";
        RG.on(page, "[data-jt-today]", "click", function () {
          var s2 = page.querySelector(".jt-scroll"), t2 = page.querySelector(".jt-today");
          if (s2 && t2) s2.scrollTo({ left: Math.max(0, t2.offsetLeft - s2.clientWidth * 0.7), behavior: "smooth" });
        });
      }
    }
  };
})();
