/* ==========================================================================
   work.js - attendance (Check-In / Check-Out), assigned tasks and hourly work
   updates for employees and interns. Loaded on every employee/intern page so
   the hourly-update popup works wherever the person is in the portal.

   Every rule shown here is decided and enforced by the API: late login,
   approved leave, working period, check-in state, report requirements and
   hourly-update eligibility. The UI only presents that state.
   ========================================================================== */
(function (global) {
  "use strict";
  if (!global.RG || !global.API) return;
  var RG = global.RG, API = global.API;

  function t12(hhmm) {
    if (!hhmm) return "—";
    var p = String(hhmm).split(":"), h = parseInt(p[0], 10);
    return ((h % 12) || 12) + ":" + p[1] + " " + (h >= 12 ? "PM" : "AM");
  }
  function mins(n) {
    n = Math.max(0, Number(n || 0));
    var h = Math.floor(n / 60), m = n % 60;
    return h + "h " + (m < 10 ? "0" : "") + m + "m";
  }
  function scope() { return document.body.dataset.scope || "employee"; }
  function loc(l) {
    if (!l) return '<span class="muted">—</span>';
    return '<a href="' + RG.esc(l.map_url) + '" target="_blank" rel="noopener">' + RG.esc(l.label) + "</a>" +
      (l.accuracy_m ? ' <span class="muted small">±' + l.accuracy_m + " m</span>" : "");
  }

  /* ---------------- late-login / work-period dialog ---------------- */
  function lateDialog(ctx, code, message) {
    return new Promise(function (resolve, reject) {
      var options = ctx.work_period_options || ["Full Day"];
      var lateBy = ctx.late_by_period || {};
      var selected = ctx.work_period && options.indexOf(ctx.work_period) >= 0 ? ctx.work_period : options[0];
      var modal = RG.openModal({
        title: code === "WORK_PERIOD_REQUIRED" ? "Confirm your work period" : "Late check-in",
        size: "sm",
        body: '<form class="late-form" novalidate>' +
          (message ? '<p class="small muted">' + RG.esc(message) + "</p>" : "") +
          (ctx.leave_period ? '<p class="mb-3">' + RG.badge(ctx.leave_period + " Leave") + "</p>" : "") +
          '<dl class="late-times">' +
            "<div><dt>Expected</dt><dd data-exp>" + t12(ctx.expected_login) + "</dd></div>" +
            "<div><dt>Actual</dt><dd>" + t12(ctx.actual_login) + "</dd></div>" +
            '<div><dt>Late by</dt><dd data-late>—</dd></div></dl>' +
          '<div class="field"><label for="late-period">Work period today</label>' +
            (options.length > 1
              ? '<select id="late-period">' + options.map(function (o) { return "<option" + (o === selected ? " selected" : "") + ">" + RG.esc(o) + "</option>"; }).join("") + "</select>"
              : '<div class="la-fixed">' + RG.esc(options[0]) + "</div>") + "</div>" +
          '<div class="field" data-reason-wrap><label for="late-reason">Reason for late login <span class="req">*</span></label>' +
            '<textarea id="late-reason" rows="3" maxlength="500" placeholder="e.g. Metro delay on the Blue Line"></textarea></div>' +
          "</form>",
        footer: '<button class="btn" data-close>Cancel</button><button class="btn btn-brand" data-go>Continue to selfie</button>',
        onClose: function () { if (!done) reject(new Error("cancelled")); }
      });
      var done = false;
      var body = modal.body;
      var periodEl = body.querySelector("#late-period");
      var reasonEl = body.querySelector("#late-reason");
      function period() { return periodEl ? periodEl.value : options[0]; }
      function sync() {
        var late = Number(lateBy[period()] || 0);
        body.querySelector("[data-late]").textContent = late > 0 ? mins(late) : "On time";
        body.querySelector("[data-reason-wrap]").style.display = late > 0 ? "" : "none";
      }
      if (periodEl) periodEl.addEventListener("change", sync);
      sync();
      modal.foot.querySelector("[data-go]").addEventListener("click", function () {
        var late = Number(lateBy[period()] || 0);
        var reason = reasonEl.value.trim();
        if (late > 0 && reason.length < 3) { RG.toastErr({ message: "Please enter the reason for your late login." }); reasonEl.focus(); return; }
        done = true;
        modal.close();
        resolve({ work_period: period(), reason: late > 0 ? reason : null });
      });
    });
  }

  /* ---------------- report gate (shared with the logout helper) ---------------- */
  function gateLine(label, required, done, reason, available, opens, needsFile) {
    var b = !required ? RG.badge("Not Required") : done ? RG.badge("Submitted") : RG.badge(available ? "Pending" : "Opens " + opens, available ? "warn" : "");
    return '<li class="lg-line"><span><b>' + label + "</b>" +
      (!required && reason ? '<small class="muted">' + RG.esc(reason) + "</small>" : "") +
      (required && needsFile ? '<small class="muted">Proof-of-work attachment required</small>' : "") + "</span>" + b + "</li>";
  }
  function gateModal(state) {
    RG.openModal({
      title: "Before you check out", size: "sm", footer: null,
      body: '<div class="logout-gate"><div class="lg-icon">' + RG.icon("clipboard", 24) + "</div>" +
        "<h3>Complete the required report before Check-Out.</h3>" +
        (state.leave_status ? '<p class="small mb-2">' + RG.badge(state.leave_status) + "</p>" : "") +
        '<ul class="lg-list">' +
          gateLine("Noon Report", state.noon_required, state.noon_submitted, state.noon_blocked_reason, state.noon_available, "1:00 PM", state.noon_attachment_required) +
          gateLine("EOD Report", state.eod_required, state.eod_submitted, state.eod_blocked_reason, state.eod_available, "6:00 PM", state.eod_required) +
        "</ul>" +
        ((state.pending_actions || []).length ? '<p class="muted small">Pending: ' + RG.esc(state.pending_actions.join("; ")) + ".</p>" : "") +
        '<div class="lg-actions"><a class="btn btn-brand" href="' +
  (scope() === "hr" ? "my-reports.html?from=checkout" : "daily-reports.html?from=checkout") +
  '">Open Daily Reports</a>' +
        '<button class="btn" data-close>Back to work</button></div></div>'
    });
  }

  /* ---------------- Check-In / Check-Out ---------------- */
  function checkIn(onDone) {
    return API.get("/attendance/status").then(function (st) {
      if (!st.can_check_in) { RG.toastErr({ message: (st.check_in_blocker || {}).message || "Check-In isn't available now." }, "Check-In"); return; }
      var ctx = st.check_in_context || {};
      var period = ctx.work_period || null;
      var late = Number((ctx.late_by_period || {})[period || (ctx.work_period_options || [])[0]] || 0);
      var answer = { work_period: period, reason: null };
      var ask = (!period || late > 0)
        ? lateDialog(ctx, period ? "LATE_LOGIN_REASON_REQUIRED" : "WORK_PERIOD_REQUIRED",
            period ? "You are checking in after your expected time. Please tell us why." : "It is past 1:00 PM, so today is recorded as a Second Half working day.")
        : Promise.resolve(answer);
      return ask.then(function (a) {
        answer = a;
        return global.RGSelfie.attendance("check-in", { subtitle: "Today " + t12(ctx.actual_login) });
      }).then(function (cap) {
        function send() {
          return API.post("/attendance/check-in", Object.assign({}, cap, {
            late_login_reason: answer.reason, work_period: answer.work_period
          }));
        }
        return send().catch(function (err) {
          var code = err && err.body && err.body.code;
          if (code === "LATE_LOGIN_REASON_REQUIRED" || code === "WORK_PERIOD_REQUIRED") {
            return lateDialog(err.body.context || {}, code, err.body.detail).then(function (a) { answer = a; return send(); });
          }
          throw err;
        });
      }).then(function (res) {
        RG.toastOk("Checked in at " + t12(res.session.check_in_time) + (res.session.late_minutes ? " · " + res.session.late_label + " late" : "") + ".", "Checked in");
        if (onDone) onDone();
        startHourlyWatcher(true);
      });
    }).catch(function (err) {
      if (err && (err.message === "cancelled" || err.message === "Selfie capture cancelled.")) return;
      RG.toastErr(err, "Check-In");
    });
  }

  function checkOut(onDone) {
    return API.get("/reports/logout-check").then(function (gate) {
      if (gate.logout_blocked) { gateModal(gate); return; }
      return RG.confirmAction({ title: "Check out for today?", message: "Your live selfie and location will be recorded with your Check-Out.", confirmLabel: "Continue" })
        .then(function (ok) {
          if (!ok) return;
          return global.RGSelfie.attendance("check-out").then(function (cap) {
            return API.post("/attendance/check-out", cap);
          }).then(function (res) {
            RG.toastOk("Checked out at " + t12(res.session.check_out_time) + " · worked " + mins(res.session.worked_minutes) +
              (res.session.extra_minutes ? " (" + mins(res.session.extra_minutes) + " extra)" : "") + ".", "Checked out");
            stopAlert();
            if (onDone) onDone();
          });
        });
    }).catch(function (err) {
      if (err && err.message === "Selfie capture cancelled.") return;
      if (err && err.body && err.body.code === "CHECKOUT_BLOCKED") { gateModal(err.body.context || {}); return; }
      RG.toastErr(err, "Check-Out");
    });
  }

  function attendanceCard(st) {
    if (!st || !st.applicable) return "";
    var s = st.session;
    var state = st.state;
    var stateBadge = state === "checked_in" ? '<span class="att-state is-in">' + RG.icon("check", 14) + " Checked in</span>"
      : state === "checked_out" ? '<span class="att-state is-out">Checked out</span>'
      : '<span class="att-state is-none">Not checked in</span>';
    var leave = st.plan && st.plan.leave_status ? RG.badge(st.plan.leave_status) : "";
    var blocker = !st.can_check_in && state === "not_checked_in" && st.check_in_blocker ? st.check_in_blocker.message : "";
    var late = s && s.late_minutes ? '<span class="badge bad">' + RG.esc(s.late_label) + " late</span>" : (s ? '<span class="badge ok">On time</span>' : "");
    return '<div class="card att-panel">' +
      '<div class="att-top"><div><div class="att-kicker">Attendance · ' + RG.fmt.dateLong(st.date) + "</div>" +
        '<div class="att-title">' + stateBadge + " " + leave + "</div>" +
        '<div class="small muted">Working hours 10:00 AM – 6:00 PM' + (st.plan && st.plan.expected_login && st.plan.leave_period ? " · today " + t12(st.plan.expected_login) + " – " + t12(st.plan.expected_logout) : "") + "</div></div>" +
        '<div class="att-actions">' +
          '<button class="btn btn-brand att-btn" data-check-in' + (st.can_check_in ? "" : " disabled") + ">" + RG.icon("user", 18) + " Check-In</button>" +
          '<button class="btn att-btn att-out" data-check-out' + (state === "checked_in" ? "" : " disabled") + ">" + RG.icon("logout", 18) + " Check-Out</button>" +
        "</div></div>" +
      (blocker ? '<p class="att-note">' + RG.esc(blocker) + "</p>" : "") +
      '<div class="att-grid">' +
        "<div><span>Check-In</span><b>" + (s ? t12(s.check_in_time) : "—") + "</b>" + (s ? late : "") + "</div>" +
        "<div><span>Check-Out</span><b>" + (s && s.check_out_time ? t12(s.check_out_time) : "—") + "</b>" +
          (s && s.extra_minutes ? '<span class="badge ok">+' + mins(s.extra_minutes) + " extra</span>" : "") + "</div>" +
        "<div><span>Working hours</span><b>" + (s ? mins(s.worked_minutes) : "0h 00m") + "</b>" + (s && !s.checked_out ? '<span class="small muted">running</span>' : "") + "</div>" +
        "<div><span>Work period</span><b>" + RG.esc(s ? s.work_period : (st.check_in_context && st.check_in_context.work_period) || "Full Day") + "</b></div>" +
      "</div>" +
      (s && s.late_reason ? '<p class="small muted mb-0 mt-2">Late reason: ' + RG.esc(s.late_reason) + "</p>" : "") +
      (s ? '<p class="small muted mb-0 mt-2">Check-In location: ' + loc(s.check_in_location) + (s.check_out_location ? " · Check-Out: " + loc(s.check_out_location) : "") + "</p>" : "") +
    "</div>";
  }

  function wireAttendance(root, reload) {
    RG.on(root, "[data-check-in]", "click", function (e, b) { if (!b.disabled) checkIn(reload); });
    RG.on(root, "[data-check-out]", "click", function (e, b) { if (!b.disabled) checkOut(reload); });
  }

  /* ---------------- tasks ---------------- */
  function taskCards(tasks, opts) {
    opts = opts || {};
    if (!tasks || !tasks.length) return RG.emptyState("No tasks assigned", "Tasks HR assigns to you appear here.", "", "clipboard");
    return '<div class="task-list">' + tasks.map(function (t) {
      var pct = Number(t.progress_percent || 0);
      return '<div class="task-card">' +
        '<div class="task-row"><b class="task-title">' + RG.esc(t.title) + "</b>" + RG.badge(t.status) + "</div>" +
        '<div class="task-meta">Assigned by ' + RG.esc(t.assigned_by || "HR") + " · " + RG.fmt.date(t.task_date) +
          (t.due_date ? " → due " + RG.fmt.date(t.due_date) : "") + (opts.showEmployee ? " · " + RG.esc(t.employee_name) : "") + "</div>" +
        (t.description ? '<div class="task-desc">' + RG.esc(t.description) + "</div>" : "") +
        '<div class="task-progress"><div class="bar thin"><span style="width:' + pct + '%"></span></div><span>' + pct + "%</span></div>" +
        '<div class="task-nums">' +
          (t.target ? "<div><span>Target</span><b>" + t.target + (t.unit ? " " + RG.esc(t.unit) : "") + "</b></div>" +
            "<div><span>Completed</span><b>" + t.completed + "</b></div><div><span>Remaining</span><b>" + t.remaining + "</b></div>"
            : "<div><span>Progress</span><b>" + pct + "%</b></div><div><span>Updates</span><b>" + (t.updates_count || 0) + "</b></div>") +
        "</div></div>";
    }).join("") + "</div>";
  }

  /* ---------------- hourly updates ---------------- */
  var SLOT_TONE = { "Submitted": "ok", "Due": "bad", "Open": "info", "Missed": "bad", "Upcoming": "", "Not Applicable": "", "Not Checked In": "" };
  function slotGrid(slots) {
    return '<div class="slot-grid">' + slots.map(function (s) {
      var tone = SLOT_TONE[s.status] || "";
      return '<button type="button" class="slot is-' + (tone || "muted") + (s.can_submit ? " is-actionable" : "") + '" ' +
        (s.can_submit ? 'data-hourly-slot="' + s.slot_index + '"' : (s.update_id ? 'data-hourly-view="' + s.update_id + '"' : "disabled")) +
        ' title="' + RG.esc(s.reason || s.status) + '">' +
        '<span class="slot-time">' + RG.esc(s.label.replace(/:00/g, "")) + "</span>" +
        '<span class="slot-status">' + RG.esc(s.status === "Open" ? "In progress" : s.status) + "</span></button>";
    }).join("") + "</div>";
  }

  function hourlyForm(slotIndex, state, onDone) {
    var slots = (state.slots || []).filter(function (s) { return s.can_submit; });
    var open = (state.tasks || []).filter(function (t) { return t.status === "Pending" || t.status === "In Progress"; });
    if (!slots.length) { RG.toastErr({ message: "No hourly period is open for an update right now." }, "Hourly update"); return; }
    var modal = RG.openModal({
      title: "Hourly work update", size: "lg",
      body: '<form id="hourly-form" class="form-grid" novalidate>' +
        '<div class="field"><label for="h-slot">Hour</label><select id="h-slot">' + slots.map(function (s) {
          return '<option value="' + s.slot_index + '"' + (String(s.slot_index) === String(slotIndex) ? " selected" : "") + ">" + RG.esc(s.label) + " · " + RG.esc(s.status === "Open" ? "current hour" : "due") + "</option>";
        }).join("") + "</select></div>" +
        '<div class="field"><label for="h-task">Assigned task' + (open.length ? ' <span class="req">*</span>' : "") + "</label>" +
          (open.length ? '<select id="h-task">' + open.map(function (t) {
            return '<option value="' + t.id + '">' + RG.esc(t.title) + (t.target ? " (" + t.completed + "/" + t.target + ")" : "") + " · by " + RG.esc(t.assigned_by || "HR") + "</option>";
          }).join("") + "</select>" : '<div class="la-fixed">No task assigned — update will be recorded as general work</div>') + "</div>" +
        '<div class="field full"><label for="h-done">Work completed during this hour <span class="req">*</span></label><textarea id="h-done" rows="3" maxlength="5000" required></textarea></div>' +
        '<div class="field full"><label for="h-desc">Work description</label><textarea id="h-desc" rows="2" maxlength="5000"></textarea></div>' +
        '<div class="field" data-units><label for="h-units">Units completed this hour</label><input id="h-units" type="number" min="0" value="0"><span class="help" data-units-help></span></div>' +
        '<div class="field" data-percent><label for="h-percent">Overall progress (%)</label><input id="h-percent" type="number" min="0" max="100" placeholder="0-100"></div>' +
        '<div class="field"><label for="h-status">Task status</label><select id="h-status"><option>In Progress</option><option>Completed</option></select></div>' +
        '<div class="field full"><label for="h-remaining">Remaining work</label><textarea id="h-remaining" rows="2" maxlength="5000"></textarea></div>' +
        '<div class="field full"><label for="h-notes">Notes / comments</label><textarea id="h-notes" rows="2" maxlength="3000"></textarea></div>' +
        '<div class="field full"><label for="h-files">Work proof / attachments</label><input id="h-files" type="file" multiple accept=".png,.jpg,.jpeg,.webp,.pdf,.doc,.docx"><span class="help">Images, PDF or Word · up to 5 files, 10 MB each</span></div>' +
        "</form>",
      footer: '<button class="btn" data-close>Cancel</button><button class="btn btn-brand" data-submit-hourly>Submit update</button>'
    });
    var b = modal.body;
    var taskEl = b.querySelector("#h-task");
    function syncTask() {
      var t = taskEl ? open.filter(function (x) { return String(x.id) === taskEl.value; })[0] : null;
      b.querySelector("[data-units]").style.display = t && t.target ? "" : "none";
      b.querySelector("[data-percent]").style.display = t && !t.target ? "" : "none";
      if (t && t.target) b.querySelector("[data-units-help]").textContent = t.completed + " of " + t.target + (t.unit ? " " + t.unit : "") + " done · " + t.remaining + " remaining";
    }
    if (taskEl) taskEl.addEventListener("change", syncTask);
    syncTask();
    modal.foot.querySelector("[data-submit-hourly]").addEventListener("click", function () {
      var btn = this;
      var done = b.querySelector("#h-done").value.trim();
      if (done.length < 3) { RG.toastErr({ message: "Describe the work completed during this hour." }); b.querySelector("#h-done").focus(); return; }
      var files = b.querySelector("#h-files").files || [];
      if (files.length > 5) { RG.toastErr({ message: "Attach up to 5 files." }); return; }
      var pct = b.querySelector("#h-percent").value;
      var payload = {
        slot_index: Number(b.querySelector("#h-slot").value),
        task_id: taskEl ? Number(taskEl.value) : null,
        work_completed: done,
        description: b.querySelector("#h-desc").value.trim() || null,
        units_completed: Number(b.querySelector("#h-units").value || 0),
        progress_percent: pct === "" ? null : Number(pct),
        task_status: b.querySelector("#h-status").value,
        remaining_work: b.querySelector("#h-remaining").value.trim() || null,
        notes: b.querySelector("#h-notes").value.trim() || null
      };
      RG.setBusy(btn, true, "Submitting…");
      API.post("/hourly-updates", payload).then(function (saved) {
        var chain = Promise.resolve();
        Array.prototype.forEach.call(files, function (f) {
          chain = chain.then(function () { var fd = new FormData(); fd.append("file", f); return API.upload("/hourly-updates/" + saved.id + "/attachments", fd); });
        });
        return chain.then(function () { return saved; });
      }).then(function (saved) {
        modal.close();
        dismissPopup(payload.slot_index, true);
        RG.toastOk("Update for " + saved.slot_label + " submitted.", "Hourly update");
        RG.refreshUnread();
        if (onDone) onDone();
        document.dispatchEvent(new CustomEvent("rg:hourly-submitted"));
      }).catch(function (err) { RG.setBusy(btn, false); RG.toastErr(err, "Hourly update"); });
    });
  }

  function viewUpdate(id) {
    API.get("/hourly-updates", {}).then(function (res) {
      var u = (res.items || []).filter(function (x) { return String(x.id) === String(id); })[0];
      if (!u) return;
      showUpdate(u);
    }).catch(RG.toastErr);
  }
  function showUpdate(u) {
    var m = RG.openModal({
      title: "Hourly update · " + u.slot_label, size: "md",
      body: '<div class="report-read"><div class="report-meta"><b>' + RG.fmt.dateLong(u.update_date) + "</b>" + RG.badge(u.task_status) + "</div>" +
        '<section><h4>Task</h4><div class="body">' + RG.esc(u.task_title || "General work") + (u.assigned_by ? " · assigned by " + RG.esc(u.assigned_by) : "") +
          (u.task_target ? " · " + u.task_completed + "/" + u.task_target + " done, " + u.task_remaining + " remaining" : "") + "</div></section>" +
        '<section><h4>Work completed</h4><div class="body">' + RG.esc(u.work_completed) + "</div></section>" +
        (u.description ? '<section><h4>Description</h4><div class="body">' + RG.esc(u.description) + "</div></section>" : "") +
        (u.remaining_work ? '<section><h4>Remaining work</h4><div class="body">' + RG.esc(u.remaining_work) + "</div></section>" : "") +
        (u.notes ? '<section><h4>Notes</h4><div class="body">' + RG.esc(u.notes) + "</div></section>" : "") +
        "<section><h4>Attachments</h4>" + (u.attachments.length ? u.attachments.map(function (a) { return '<button class="btn btn-sm" data-hatt="' + a.id + '">' + RG.esc(a.original_filename) + "</button>"; }).join(" ") : '<span class="small muted">None</span>') + "</section>" +
        '<p class="small muted">Submitted ' + RG.fmt.dateTime(u.submitted_at) + "</p></div>",
      footer: '<button class="btn" data-close>Close</button>'
    });
    RG.on(m.body, "[data-hatt]", "click", function (e, el) {
      API.blob("/hourly-updates/attachments/" + el.dataset.hatt + "/download").then(function (f) { window.open(f.url, "_blank"); }).catch(RG.toastErr);
    });
  }

  /* ---------------- alert sound (Web Audio, ~18 s) ---------------- */
  var audio = { ctx: null, timer: null, stopAt: 0 };
  function audioCtx() {
    if (!audio.ctx) {
      var AC = global.AudioContext || global.webkitAudioContext;
      if (!AC) return null;
      audio.ctx = new AC();
    }
    return audio.ctx;
  }
  function chime(ctx, at) {
    [880, 1175, 1568].forEach(function (f, i) {
      var o = ctx.createOscillator(), g = ctx.createGain();
      o.type = "sine"; o.frequency.value = f;
      var t = at + i * 0.18;
      g.gain.setValueAtTime(0.0001, t);
      g.gain.exponentialRampToValueAtTime(0.22, t + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, t + 0.5);
      o.connect(g); g.connect(ctx.destination);
      o.start(t); o.stop(t + 0.55);
    });
  }
  function playAlert(seconds) {
    var ctx = audioCtx();
    if (!ctx) return Promise.resolve(false);
    stopAlert();
    return (ctx.state === "suspended" ? ctx.resume() : Promise.resolve()).then(function () {
      if (ctx.state !== "running") return false;
      audio.stopAt = Date.now() + (seconds || 18) * 1000;
      chime(ctx, ctx.currentTime + 0.05);
      audio.timer = setInterval(function () {
        if (Date.now() >= audio.stopAt) { stopAlert(); return; }
        chime(ctx, ctx.currentTime + 0.05);
      }, 2000);
      return true;
    }).catch(function () { return false; });
  }
  function stopAlert() { if (audio.timer) { clearInterval(audio.timer); audio.timer = null; } }
  // Browsers only allow sound after the person has interacted with the page.
  document.addEventListener("pointerdown", function unlock() {
    var ctx = audioCtx();
    if (ctx && ctx.state === "suspended") ctx.resume().catch(function () {});
  }, { once: true, capture: true });

  /* ---------------- hourly popup watcher ---------------- */
  var watcher = { timer: null, state: null, shown: {} };
  function seenKey(date, slot) { return "rg_hourly_seen_" + date + "_" + slot; }
  function wasSeen(date, slot) {
    if (watcher.shown[date + ":" + slot]) return true;
    try { return localStorage.getItem(seenKey(date, slot)) === "1"; } catch (e) { return false; }
  }
  function markSeen(date, slot) {
    watcher.shown[date + ":" + slot] = true;
    try { localStorage.setItem(seenKey(date, slot), "1"); } catch (e) { /* ignore */ }
  }
  function dismissPopup(slot, submitted) {
    var el = document.querySelector(".hourly-pop");
    if (el && (slot === undefined || String(el.dataset.slot) === String(slot))) {
      el.remove(); stopAlert();
    }
  }
  function showPopup(state, slot) {
    dismissPopup();
    var pop = document.createElement("div");
    pop.className = "hourly-pop";
    pop.dataset.slot = slot.slot_index;
    pop.setAttribute("role", "alertdialog");
    pop.setAttribute("aria-labelledby", "hp-title");
    pop.innerHTML = '<div class="hp-icon">' + RG.icon("bell", 20) + "</div>" +
      '<div class="hp-main"><b id="hp-title">Hourly work update due</b>' +
      "<p>Your update for <b>" + RG.esc(slot.label) + "</b> is due. Share what you completed on your assigned task.</p>" +
      '<div class="hp-actions"><button class="btn btn-brand btn-sm" data-hp-open>Submit update</button>' +
      '<button class="btn btn-sm" data-hp-later>Later</button>' +
      '<button class="btn btn-sm btn-ghost hidden" data-hp-sound>' + RG.icon("bell", 14) + " Enable sound</button></div></div>" +
      '<button class="hp-close" data-hp-later aria-label="Dismiss">&times;</button>';
    document.body.appendChild(pop);
    markSeen(state.date, slot.slot_index);
    pop.querySelector("[data-hp-open]").addEventListener("click", function () {
      dismissPopup(); hourlyForm(slot.slot_index, state, refreshWidgets);
    });
    pop.querySelectorAll("[data-hp-later]").forEach(function (b) { b.addEventListener("click", function () { dismissPopup(); }); });
    playAlert(18).then(function (ok) {
      if (!ok) {
        var s = pop.querySelector("[data-hp-sound]");
        if (s) { s.classList.remove("hidden"); s.addEventListener("click", function () { s.classList.add("hidden"); playAlert(18); }); }
      }
    });
  }
  function refreshWidgets() { document.dispatchEvent(new CustomEvent("rg:work-refresh")); }

  function pollHourly() {
    return API.get("/hourly-updates/today").then(function (state) {
      watcher.state = state;
      if (!state.checked_in || state.checked_out) return state;
      var due = (state.due_slots || []).filter(function (s) { return !wasSeen(state.date, s.slot_index); });
      if (due.length && !document.querySelector(".hourly-pop") && !document.querySelector(".modal-backdrop")) {
        showPopup(state, due[due.length - 1]);
        due.slice(0, -1).forEach(function (s) { markSeen(state.date, s.slot_index); });
      }
      return state;
    }).catch(function () { return null; });
  }
  function startHourlyWatcher(now) {
    var sc = scope();
    if (!RG.isWorkerPortal(sc)) return;
    if (!watcher.timer) watcher.timer = setInterval(pollHourly, 60000);
    if (now !== false) pollHourly();
  }

  global.RGWork = {
    t12: t12, mins: mins, loc: loc,
    lateDialog: lateDialog, gateModal: gateModal,
    checkIn: checkIn, checkOut: checkOut, attendanceCard: attendanceCard, wireAttendance: wireAttendance,
    taskCards: taskCards, slotGrid: slotGrid, hourlyForm: hourlyForm, showUpdate: showUpdate, viewUpdate: viewUpdate,
    playAlert: playAlert, stopAlert: stopAlert, pollHourly: pollHourly, startHourlyWatcher: startHourlyWatcher
  };

  // Start on every employee/intern page once the shell is up.
  // HR and Managers are employees too: they get the same hourly reminders.
  if (API.session.token() && RG.isWorkerPortal(scope())) {
    setTimeout(function () { startHourlyWatcher(true); }, 1200);
  }
})(window);
