/* meetings.js - department meeting timeline. Employees see only their own
   department's meetings (enforced server-side); HR creates and manages all. */
(function () {
  "use strict";
  var SCOPE = document.body.dataset.scope;
  var isHr = RG.mgmtView();

  function iso(date) { return date.toISOString().slice(0, 10); }
  function today() { return iso(new Date()); }
  function plusDays(days) {
    var d = new Date();
    d.setDate(d.getDate() + days);
    return iso(d);
  }

  function meetingCard(m, canManage) {
    var cls = m.status === "Cancelled" ? "is-cancelled" : (m.is_today ? "" : "is-done");
    var joinable = m.google_meet_url && m.status !== "Cancelled";
    return '<div class="tl-item ' + cls + '">' +
      '<div class="tl-time">' + RG.fmt.time(m.start_time) + "</div>" +
      '<div class="tl-card"><div class="tl-main">' +
        '<div class="tl-dept">' + RG.esc(m.department || "") + "</div>" +
        "<h4>" + RG.esc(m.title) + "</h4>" +
        (m.agenda ? '<div class="tl-agenda">' + RG.esc(m.agenda) + "</div>" : "") +
        '<div class="tl-when">' + RG.fmt.date(m.meeting_date) + " \u00B7 " + RG.fmt.time(m.start_time) +
          (m.end_time ? " \u2013 " + RG.fmt.time(m.end_time) : "") + "</div>" +
      "</div>" +
      '<div class="tl-actions">' + RG.badge(m.status) +
        (joinable
          ? '<a class="btn btn-sm meet-btn" target="_blank" rel="noopener" href="' + RG.esc(m.google_meet_url) + '">' +
            RG.icon("video", 15) + " Join Google Meet</a>"
          : (m.status === "Cancelled" ? "" : '<span class="small muted">No meet link yet</span>')) +
        (canManage
          ? '<button class="btn btn-sm" data-edit="' + m.id + '">Edit</button>' +
            (m.status !== "Cancelled" ? '<button class="btn btn-sm btn-ghost" data-cancel="' + m.id + '">Cancel</button>' : "")
          : "") +
      "</div></div></div>";
  }

  function groupByDay(rows, canManage) {
    var days = {};
    rows.forEach(function (m) {
      if (!days[m.meeting_date]) days[m.meeting_date] = [];
      days[m.meeting_date].push(m);
    });
    return Object.keys(days).sort().map(function (day) {
      var list = days[day].sort(function (a, b) { return String(a.start_time).localeCompare(String(b.start_time)); });
      return '<div class="day-head"><span>' + RG.fmt.dateLong(day) + "</span>" +
          (day === today() ? '<span class="badge info today-chip plain">Today</span>' : "") +
          '<span class="rule"></span><span class="small muted">' + list.length + " meeting" +
          (list.length === 1 ? "" : "s") + "</span></div>" +
        '<div class="timeline">' + list.map(function (m) { return meetingCard(m, canManage); }).join("") + "</div>";
    }).join("");
  }

  /* ---------------- HR form ---------------- */
  function meetingForm(existing, departments) {
    var m = existing || {};
    return '<form id="meet-form" class="form-grid">' +
      '<div class="field full"><label for="m-title">Meeting title <span class="req">*</span></label>' +
        '<input id="m-title" type="text" value="' + RG.esc(m.title || "") + '" required ' +
        'placeholder="e.g. Daily Sales Day Plan"></div>' +
      '<div class="field"><label for="m-dept">Department <span class="req">*</span></label>' +
        '<select id="m-dept" required>' + RG.optionList(departments, "id", "name", m.department_id) + "</select>" +
        '<span class="help">Only this department\u2019s employees will see it.</span></div>' +
      '<div class="field"><label for="m-date">Date <span class="req">*</span></label>' +
        '<input id="m-date" type="date" value="' + (m.meeting_date || today()) + '" required></div>' +
      '<div class="field"><label for="m-start">Start time <span class="req">*</span></label>' +
        '<input id="m-start" type="time" value="' + (m.start_time || "10:15").slice(0, 5) + '" required></div>' +
      '<div class="field"><label for="m-end">End time</label>' +
        '<input id="m-end" type="time" value="' + (m.end_time ? m.end_time.slice(0, 5) : "") + '"></div>' +
      '<div class="field full"><label for="m-url">Google Meet URL</label>' +
        '<input id="m-url" type="url" value="' + RG.esc(m.google_meet_url || "") + '" ' +
        'placeholder="https://meet.google.com/xxx-xxxx-xxx"></div>' +
      '<div class="field full"><label for="m-agenda">Agenda</label>' +
        '<textarea id="m-agenda" rows="3">' + RG.esc(m.agenda || "") + "</textarea></div>" +
      (existing ? '<div class="field"><label for="m-status">Status</label><select id="m-status">' +
        ["Scheduled", "Completed", "Cancelled"].map(function (s) {
          return '<option value="' + s + '"' + (m.status === s ? " selected" : "") + ">" + s + "</option>";
        }).join("") + "</select></div>" : "") +
      "</form>";
  }

  function hrView() {
    var ctx = RG.boot({ scope: "hr", active: "meetings", title: "Meetings", subtitle: "Department schedule" });
    if (!ctx) return;
    var state = { department_id: "", status: "", date_from: today(), date_to: plusDays(14) };
    var departments = [];
    var cache = {};

    ctx.page.innerHTML =
      '<div class="page-head"><div><h1>Department meetings</h1>' +
        '<p class="sub">Each meeting is visible only to the department it belongs to.</p></div>' +
        '<div class="page-actions"><button class="btn btn-brand" data-new>' + RG.icon("plus", 16) + " Schedule meeting</button></div></div>" +
      '<div class="card mb-4"><div class="toolbar">' +
        '<div class="filters" style="margin-left:0">' +
          '<select id="f-dept"><option value="">All departments</option></select>' +
          '<select id="f-status"><option value="">Any status</option><option value="Scheduled">Scheduled</option>' +
            '<option value="Completed">Completed</option><option value="Cancelled">Cancelled</option></select>' +
          '<input id="f-from" type="date" value="' + state.date_from + '" title="From">' +
          '<input id="f-to" type="date" value="' + state.date_to + '" title="To">' +
        "</div></div></div>" +
      '<div id="host">' + RG.skeletonRows(4) + "</div>";

    var host = document.getElementById("host");

    API.get("/departments").then(function (rows) {
      departments = rows.filter(function (d) { return d.is_active; });
      document.getElementById("f-dept").innerHTML = '<option value="">All departments</option>' +
        RG.optionList(departments, "id", "name");
    });

    function load() {
      API.get("/meetings", state).then(function (rows) {
        rows.forEach(function (m) { cache[m.id] = m; });
        host.innerHTML = rows.length
          ? groupByDay(rows, true)
          : '<div class="card">' + RG.emptyState("No meetings in this range",
              "Schedule a daily meeting for a department.",
              '<button class="btn btn-sm btn-brand" data-new>Schedule meeting</button>', "calendar") + "</div>";
      }).catch(function (err) {
        host.innerHTML = '<div class="card">' + RG.errorState(err.message, "retry") + "</div>";
        var r = document.getElementById("retry"); if (r) r.addEventListener("click", load);
      });
    }

    function openForm(existing) {
      var modal = RG.openModal({
        title: existing ? "Edit meeting" : "Schedule a meeting",
        body: meetingForm(existing, departments),
        footer: '<button class="btn" data-close>Cancel</button>' +
          '<button class="btn btn-brand" data-save>' + (existing ? "Save changes" : "Schedule") + "</button>"
      });
      modal.foot.querySelector("[data-save]").addEventListener("click", function () {
        var form = modal.body.querySelector("#meet-form");
        if (!form.reportValidity()) return;
        var payload = {
          title: modal.body.querySelector("#m-title").value.trim(),
          department_id: Number(modal.body.querySelector("#m-dept").value),
          meeting_date: modal.body.querySelector("#m-date").value,
          start_time: modal.body.querySelector("#m-start").value,
          end_time: modal.body.querySelector("#m-end").value || null,
          agenda: modal.body.querySelector("#m-agenda").value.trim() || null,
          google_meet_url: modal.body.querySelector("#m-url").value.trim() || null
        };
        var statusField = modal.body.querySelector("#m-status");
        if (statusField) payload.status = statusField.value;
        var button = modal.foot.querySelector("[data-save]");
        RG.setBusy(button, true, "Saving\u2026");
        (existing ? API.put("/meetings/" + existing.id, payload) : API.post("/meetings", payload))
          .then(function () {
            modal.close();
            RG.toastOk(existing ? "Meeting updated." : "Meeting scheduled.");
            load();
          })
          .catch(function (err) { RG.setBusy(button, false); RG.toastErr(err); });
      });
    }

    [["f-dept", "department_id"], ["f-status", "status"], ["f-from", "date_from"], ["f-to", "date_to"]]
      .forEach(function (pair) {
        document.getElementById(pair[0]).addEventListener("change", function (e) {
          state[pair[1]] = e.target.value; load();
        });
      });

    RG.on(ctx.page, "[data-new]", "click", function () { openForm(null); });
    RG.on(ctx.page, "[data-edit]", "click", function (e, b) { openForm(cache[b.dataset.edit]); });
    RG.on(ctx.page, "[data-cancel]", "click", function (e, b) {
      RG.confirmAction({
        title: "Cancel this meeting?", danger: true, confirmLabel: "Cancel meeting",
        message: "The department will see it as cancelled. The record and its Meet link are kept."
      }).then(function (ok) {
        if (!ok) return;
        API.post("/meetings/" + b.dataset.cancel + "/cancel", {})
          .then(function () { RG.toastOk("Meeting cancelled."); load(); })
          .catch(RG.toastErr);
      });
    });

    load();
  }

  /* ---------------- employee view ---------------- */
  function employeeView() {
    var ctx = RG.boot({ scope: document.body.dataset.scope || "employee", active: "meetings", title: "Meetings", subtitle: "Your department" });
    if (!ctx) return;
    var user = ctx.user;

    ctx.page.innerHTML =
      '<div class="page-head"><div><h1>Meetings</h1>' +
        '<p class="sub">Scheduled for ' + RG.esc(user.department || "your department") + ".</p></div>" +
        '<div class="page-actions"><div class="filters">' +
          '<select id="range"><option value="today">Today</option>' +
            '<option value="week" selected>Next 7 days</option>' +
            '<option value="past">Past 14 days</option></select></div></div></div>' +
      '<div id="host">' + RG.skeletonRows(3) + "</div>";

    var host = document.getElementById("host");

    function load() {
      var range = document.getElementById("range").value;
      var query = range === "today" ? { date_from: today(), date_to: today() }
        : range === "week" ? { date_from: today(), date_to: plusDays(7) }
        : { date_from: plusDays(-14), date_to: today() };
      API.get("/meetings", query).then(function (rows) {
        host.innerHTML = rows.length
          ? groupByDay(rows, false)
          : '<div class="card">' + RG.emptyState("No meetings in this range",
              "Your department's meetings appear here as soon as HR schedules them.", "", "calendar") + "</div>";
      }).catch(function (err) {
        host.innerHTML = '<div class="card">' + RG.errorState(err.message, "retry") + "</div>";
        var r = document.getElementById("retry"); if (r) r.addEventListener("click", load);
      });
    }

    document.getElementById("range").addEventListener("change", load);
    load();
  }

  if (isHr) hrView(); else employeeView();
})();
