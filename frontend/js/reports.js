/* Daily work reports: exactly one Noon + one EOD report per working day. */
(function () {
  "use strict";
  var scope = document.body.dataset.scope || "employee";

  // The office date comes from the server (IST). The browser's UTC date can be
  // a day behind in the early morning, so it is never used to date a report.
  var officeDate = null;
  function today() { return officeDate || new Date().toISOString().slice(0, 10); }

  function employeeView() {
    var ctx = RG.boot({ scope: scope, active: "reports", title: "Daily Reports", subtitle: "Noon and EOD submissions" });
    if (!ctx) return;

    var fromLogout = RG.param("from") === "logout" || RG.param("from") === "checkout";
    var reports = { Noon: null, EOD: null };
    var gate = null;   // today's rules from the API (approved leave applied)

    function rule(type) {
      var isEod = type === "EOD";
      return {
        required: gate ? (isEod ? gate.eod_required : gate.noon_required) : true,
        available: gate ? (isEod ? gate.eod_available : gate.noon_available) : false,
        submitted: gate ? (isEod ? gate.eod_submitted : gate.noon_submitted) : false,
        needsFile: isEod ? true : !!(gate && gate.noon_attachment_required),
        reason: gate ? (isEod ? gate.eod_blocked_reason : gate.noon_blocked_reason) : null,
        opens: isEod ? "6:00 PM" : "1:00 PM"
      };
    }

    function reportCard(type) {
      var r = reports[type] || {};
      var x = rule(type);
      var head = '<div class="card-head"><div><h3>' + type + " Report</h3>" +
        '<span class="hint">' + (x.required ? "Available from " + x.opens : "Not applicable today") + "</span></div>" +
        "<div>" + RG.badge(x.required ? "Required" : "Not Required") + "</div></div>";
      if (!x.required) {
        return '<div class="card report-card is-na">' + head + '<div class="card-body">' +
          '<p class="na-reason">' + RG.icon("calendar", 16) + " " + RG.esc(x.reason || "Not required today.") + "</p>" +
          '<button class="btn" disabled aria-disabled="true">' + type + " Report not required</button></div></div>";
      }
      var status = x.submitted ? (r.status || "Submitted") : (r.status === "Draft" ? "Draft" : (r.status === "Submitted" && type === "EOD" ? "No Attachment" : "Pending"));
      var label = x.submitted ? "View / Update" : (x.available ? "Submit " + type + " Report" : (r.status === "Draft" ? "Continue draft" : "Save a draft"));
      return '<div class="card report-card">' + head + '<div class="card-body">' +
        '<div class="report-status-line mb-3">' + RG.badge(status) +
          (r.submitted_at ? '<span class="small muted">Submitted ' + RG.fmt.dateTime(r.submitted_at) + "</span>" : "") +
          (!x.available && !x.submitted ? '<span class="small muted">Submission opens at ' + x.opens + "</span>" : "") +
        "</div>" +
        '<button class="btn ' + (x.submitted ? "" : "btn-brand") + '" data-open-report="' + type + '">' + label + "</button>" +
        (x.needsFile ? '<p class="small muted mt-2 mb-0">A proof-of-work attachment is required for the ' + type + " Report" + (type === "Noon" ? " (it is your closing report on an Afternoon Half leave)." : ".") + "</p>" : "") +
        (r.source === "Hourly Updates" ? '<p class="small mt-2 mb-0">' + RG.badge("From hourly updates", "info") + " Filled automatically from your hourly updates after 1:00 PM.</p>" : "") +
        "</div></div>";
    }

    function formHtml(type, report) {
      var r = report || {};
      var x = rule(type);
      return '<form id="report-form" class="report-form">' +
        '<div class="report-meta"><div><b>' + RG.fmt.dateLong(today()) + '</b><div class="small muted">' + type + " Report · available from " + x.opens + "</div></div>" +
        '<div style="margin-left:auto">' + RG.badge(r.status || "Pending") + "</div></div>" +
        '<div class="rf-grid">' +
        '<div class="field"><label for="done">Tasks completed</label><textarea id="done" class="task" placeholder="What did you complete?">' + RG.esc(r.tasks_completed || "") + "</textarea></div>" +
        '<div class="field"><label for="doing">Tasks in progress</label><textarea id="doing" class="task" placeholder="What are you working on?">' + RG.esc(r.tasks_in_progress || "") + "</textarea></div>" +
        '<div class="field"><label for="todo">Tasks pending</label><textarea id="todo" class="task" placeholder="What remains pending?">' + RG.esc(r.tasks_pending || "") + "</textarea></div>" +
        '</div><div class="form-grid mt-4">' +
        '<div class="field full"><label for="summary">Work details / summary</label><textarea id="summary" rows="4" required>' + RG.esc(r.work_summary || "") + "</textarea></div>" +
        '<div class="field"><label for="challenges">Challenges or blockers</label><textarea id="challenges" rows="3">' + RG.esc(r.challenges || "") + "</textarea></div>" +
        '<div class="field"><label for="comments">Additional comments</label><textarea id="comments" rows="3">' + RG.esc(r.additional_comments || "") + "</textarea></div>" +
        "</div>" +
        (x.needsFile ? '<div class="report-meta mt-4"><div><b>' + type + ' attachment</b><div class="small muted">At least one proof-of-work attachment is required. ' +
          ((r.attachments || []).length ? (r.attachments.length + " already attached.") : "") + '</div></div><input id="eod-file" type="file" accept=".png,.jpg,.jpeg,.webp,.pdf,.doc,.docx" multiple></div>' : "") +
        '<div class="row mt-5 wrap">' +
          (x.available ? '<button class="btn btn-brand" type="submit">Submit ' + type + " Report</button>" : '<span class="small muted">Submission opens at ' + x.opens + ".</span>") +
          '<button class="btn" type="button" data-draft>Save Draft</button></div>' +
        "</form>";
    }

    function loadToday() {
      return Promise.all([
        API.get("/reports/logout-check"),
        API.get("/reports/me/today", { report_type: "Noon" }),
        API.get("/reports/me/today", { report_type: "EOD" }),
        API.get("/reports", { page: 1, page_size: 30, report_type: "all", mine: true }),
        API.get("/leave-requests/me", { page: 1, page_size: 20 })
      ]).then(function (res) {
        gate = res[0]; reports.Noon = res[1]; reports.EOD = res[2];
        officeDate = gate.date || officeDate;
        render(res[3].items || [], res[4].items || []);
      });
    }

    function leaveBanner() {
      if (!gate || !gate.leave_status) return "";
      return '<div class="card mb-4 leave-banner"><div class="card-body row wrap">' + RG.badge(gate.leave_status) +
        '<span>Approved leave today. Noon Report: <b>' + (gate.noon_required ? "Required" : "Not Required") +
        "</b> · EOD Report: <b>" + (gate.eod_required ? "Required" : "Not Required") + "</b></span></div></div>";
    }

    function render(history, leaves) {
      var pending = gate && gate.missing_reports && gate.missing_reports.length;
      ctx.page.innerHTML = '<div class="page-head"><div><h1>Daily Work Reports</h1><p class="sub">Noon and EOD reports for each working day — approved leave decides which ones apply.</p></div><div class="page-actions"><button class="btn btn-brand" data-request-leave>Request Leave</button></div></div>' +
        (fromLogout && pending ? '<div class="card mb-4"><div class="card-body"><b>Before logout:</b> ' + RG.esc((gate.pending_actions || []).join("; ")) + ".</div></div>" : "") +
        leaveBanner() +
        '<div class="grid grid-2">' + reportCard("Noon") + reportCard("EOD") + "</div>" +
        '<div class="card mt-4"><div class="card-head"><h3>Report History</h3></div><div class="card-body">' + historyHtml(history) + "</div></div>" +
        '<div class="card mt-4"><div class="card-head"><h3>My Leave Records</h3><span class="hint">Type, period, duration and HR decision</span></div><div class="card-body">' +
          RG.leaveTable(leaves, { emptyText: "You haven't requested any leave yet." }) + "</div></div>";
    }

    function historyHtml(rows) {
      if (!rows.length) return RG.emptyState("No reports yet", "Your submitted Noon and EOD reports will appear here.");
      return '<div class="table-scroll"><table class="data"><thead><tr><th>Date</th><th>Type</th><th>Work details</th><th>Status</th><th>Submitted</th><th></th></tr></thead><tbody>' +
        rows.map(function (r) { return '<tr><td data-label="Date">' + RG.fmt.date(r.report_date) + '</td><td data-label="Type"><b>' + RG.esc(r.report_type || "EOD") + '</b></td><td data-label="Work details"><div class="truncate" style="max-width:320px">' + RG.esc(r.work_summary || "—") + '</div></td><td data-label="Status">' + RG.badge(r.status) + '</td><td data-label="Submitted">' + RG.fmt.dateTime(r.submitted_at) + '</td><td><button class="btn btn-sm" data-history="' + r.id + '">Read</button></td></tr>'; }).join("") +
        "</tbody></table></div>";
    }

    function collect(form, type, submit) {
      return {
        report_type: type,
        report_date: null,   // server assigns today's office (IST) date
        tasks_completed: form.querySelector("#done").value.trim() || null,
        tasks_in_progress: form.querySelector("#doing").value.trim() || null,
        tasks_pending: form.querySelector("#todo").value.trim() || null,
        work_summary: form.querySelector("#summary").value.trim() || null,
        challenges: form.querySelector("#challenges").value.trim() || null,
        additional_comments: form.querySelector("#comments").value.trim() || null,
        submit: submit
      };
    }

    function uploadFiles(reportId, files) {
      var chain = Promise.resolve();
      Array.prototype.forEach.call(files || [], function (file) {
        chain = chain.then(function () { var fd = new FormData(); fd.append("file", file); return API.upload("/reports/" + reportId + "/attachments", fd); });
      });
      return chain;
    }

    function openReport(type) {
      if (!rule(type).required) { RG.toastErr({ message: rule(type).reason || (type + " Report is not required today.") }, "Not required"); return; }
      var modal = RG.openModal({ title: type + " Report", size: "lg", body: formHtml(type, reports[type]), footer: '<button class="btn" data-close>Cancel</button>' });
      var form = modal.body.querySelector("#report-form");
      form.addEventListener("submit", function (e) {
        e.preventDefault();
        var payload = collect(form, type, true);
        var button = form.querySelector('button[type="submit"]');
        RG.setBusy(button, true, "Submitting…");
        var needsFile = rule(type).needsFile;
        var files = needsFile ? form.querySelector("#eod-file").files : [];
        // Reports without a required attachment submit directly; otherwise the
        // report is saved as a draft, attachments uploaded, then submitted.
        API.post("/reports", Object.assign({}, payload, { submit: !needsFile })).then(function (saved) {
          return uploadFiles(saved.id, files).then(function () {
            return needsFile ? API.post("/reports", payload) : saved;
          });
        }).then(function () { modal.close(); RG.toastOk(type + " report submitted."); loadToday(); })
          .catch(function (err) { RG.setBusy(button, false); RG.toastErr(err); if (err && err.body && err.body.code === "REPORT_NOT_APPLICABLE") { modal.close(); loadToday(); } });
      });
      modal.body.querySelector("[data-draft]").addEventListener("click", function () {
        var b = this;
        RG.setBusy(b, true, "Saving…");
        var files = rule(type).needsFile ? form.querySelector("#eod-file").files : [];
        API.post("/reports", collect(form, type, false)).then(function (saved) {
          return uploadFiles(saved.id, files);
        }).then(function () { modal.close(); RG.toastOk(type + " report saved as draft."); loadToday(); })
          .catch(function (err) { RG.setBusy(b, false); RG.toastErr(err); });
      });
    }

    function openHistory(id) {
      API.get("/reports/" + id).then(function (r) {
        var modal = RG.openModal({ title: (r.report_type || "EOD") + " Report", size: "lg", body: '<div class="report-read"><div class="report-meta"><b>' + RG.fmt.dateLong(r.report_date) + "</b>" + RG.badge(r.status) + '</div><section><h4>Work details</h4><div class="body">' + RG.esc(r.work_summary || "") + '</div></section><section><h4>Tasks completed</h4><div class="body">' + RG.esc(r.tasks_completed || "") + '</div></section><section><h4>Tasks in progress</h4><div class="body">' + RG.esc(r.tasks_in_progress || "") + '</div></section><section><h4>Tasks pending</h4><div class="body">' + RG.esc(r.tasks_pending || "") + "</div></section>" + (r.review_notes ? '<section><h4>Reviewer comments</h4><div class="body">' + RG.esc(r.review_notes) + "</div></section>" : "") + '<section><h4>Attachments</h4><div class="attach-grid">' + ((r.attachments || []).map(function (a) { return '<button class="btn btn-sm" data-att="' + a.id + '">' + RG.esc(a.original_filename) + "</button>"; }).join(" ") || '<span class="small muted">None</span>') + "</div></section></div>", footer: '<button class="btn" data-close>Close</button>' });
        RG.on(modal.body, "[data-att]", "click", function (e, el) { API.blob("/reports/attachments/" + el.dataset.att + "/download").then(function (f) { window.open(f.url, "_blank"); }).catch(RG.toastErr); });
      }).catch(RG.toastErr);
    }

    RG.on(document, "[data-open-report]", "click", function (e, el) { openReport(el.dataset.openReport); });
    RG.on(document, "[data-history]", "click", function (e, el) { openHistory(el.dataset.history); });
    RG.on(document, "[data-request-leave]", "click", function () { RG.leaveModal(loadToday); });
    ctx.page.innerHTML = RG.skeletonCards(2);
    function boot() {
      loadToday().catch(function (err) { ctx.page.innerHTML = '<div class="card">' + RG.errorState(err.message, "retry") + "</div>"; var r = document.getElementById("retry"); if (r) r.addEventListener("click", boot); });
    }
    boot();
  }

  function hrView() {
    var ctx = RG.boot({ scope:"hr", active:"reports", title:"Work Reports", subtitle:"Noon and EOD submissions" });
    if (!ctx) return;
    var state={page:1,page_size:20,status:"",department_id:"",employee_id:"",report_date:"",report_type:"",reporting_hr_id:"",reporting_manager_id:""};
    ctx.page.innerHTML='<div class="page-head"><div><h1>'+(document.body.dataset.scope==="manager"?"Team Reports":"Work Reports")+'</h1><p class="sub">'+({admin:"Noon and EOD reports from the whole organisation. HR reports are reviewed here.",manager:"Noon and EOD reports from your team. Reviewing here is the first level; HR and the Admin can see them too.",hr:"Noon and EOD reports from the managers, employees and interns in your hierarchy."}[document.body.dataset.scope]||"")+'</p></div></div><div class="card"><div class="toolbar"><div class="filters" style="margin-left:0"><select id="f-type"><option value="">All report types</option><option value="Noon">Noon</option><option value="EOD">EOD</option></select><select id="f-dept"><option value="">All departments</option></select><select id="f-emp"><option value="">All employees</option></select><select id="f-status"><option value="">Any status</option><option>Submitted</option><option>Draft</option><option>Reviewed</option></select><input id="f-date" type="date"></div></div><div id="host">'+RG.skeletonRows(8)+'</div><div class="pager" id="pager"></div></div>';
    var host=document.getElementById("host");
    Promise.all([API.get("/departments"),API.get("/employees",{page:1,page_size:100,include_self:false})]).then(function(res){document.getElementById("f-dept").innerHTML='<option value="">All departments</option>'+RG.optionList(res[0],"id","name");document.getElementById("f-emp").innerHTML='<option value="">All employees</option>'+RG.optionList(res[1].items||[],"id","full_name");}).catch(function(){});
    function load(){API.get("/reports",state).then(function(data){var items=data.items||[];if(!items.length){host.innerHTML=RG.emptyState("No reports match","Try another filter.");document.getElementById("pager").innerHTML="";return;}host.innerHTML='<div class="table-scroll"><table class="data"><thead><tr><th>Employee</th><th>Department</th><th>Report</th><th>Date</th><th>Status</th><th>Submitted</th><th>Files</th><th></th></tr></thead><tbody>'+items.map(function(r){return '<tr><td>'+RG.esc(r.employee_name||"—")+(r.person_type?'<div class="small muted">'+RG.esc(r.person_type)+'</div>':"")+'</td><td>'+RG.esc(r.department||"—")+'</td><td><b>'+RG.esc(r.report_type||"EOD")+'</b></td><td>'+RG.fmt.date(r.report_date)+'</td><td>'+RG.badge(r.status)+'</td><td>'+RG.fmt.dateTime(r.submitted_at)+'</td><td>'+((r.attachments||[]).length)+'</td><td><button class="btn btn-sm" data-open="'+r.id+'">Read</button></td></tr>';}).join("")+'</tbody></table></div>';RG.renderPager(document.getElementById("pager"),data.meta,function(p){state.page=p;load();});}).catch(function(err){host.innerHTML=RG.errorState(err.message,"retry");});}
    ["f-type","f-dept","f-emp","f-status","f-date"].forEach(function(id){document.getElementById(id).addEventListener("change",function(){state.page=1;state.report_type=document.getElementById("f-type").value;state.department_id=document.getElementById("f-dept").value;state.employee_id=document.getElementById("f-emp").value;state.status=document.getElementById("f-status").value;state.report_date=document.getElementById("f-date").value;load();});});
    RG.on(document,"[data-open]","click",function(e,el){API.get("/reports/"+el.dataset.open).then(function(r){var body='<div class="report-read"><div class="report-meta"><b>'+RG.esc(r.employee_name||"")+'</b><span>'+RG.esc(r.report_type||"EOD")+' · '+RG.fmt.dateLong(r.report_date)+'</span>'+RG.badge(r.status)+'</div><section><h4>Work details</h4><div class="body">'+RG.esc(r.work_summary||"")+'</div></section><section><h4>Tasks completed</h4><div class="body">'+RG.esc(r.tasks_completed||"")+'</div></section><section><h4>Tasks in progress</h4><div class="body">'+RG.esc(r.tasks_in_progress||"")+'</div></section><section><h4>Tasks pending</h4><div class="body">'+RG.esc(r.tasks_pending||"")+'</div></section><section><h4>Attachments</h4>'+((r.attachments||[]).map(function(a){return '<button class="btn btn-sm" data-att="'+a.id+'">'+RG.esc(a.original_filename)+'</button>';}).join(" ")||"None")+'</section></div>';if(r.review_notes){body+='<section><h4>Reviewer comments</h4><div class="body">'+RG.esc(r.review_notes)+'</div></section>';}if(r.status!=="Reviewed"){body+='<div class="field mt-4"><label for="review-notes">Comments (optional)</label><textarea id="review-notes" rows="3"></textarea></div>';}var m=RG.openModal({title:(r.report_type||"EOD")+" Report",size:"lg",body:body,footer:'<button class="btn" data-close>Close</button>'+ (r.status!=="Reviewed"?'<button class="btn btn-brand" data-review>Mark reviewed</button>':"")});RG.on(m.body,"[data-att]","click",function(e,a){API.blob("/reports/attachments/"+a.dataset.att+"/download").then(function(f){window.open(f.url,"_blank");}).catch(RG.toastErr);});var rb=m.foot.querySelector("[data-review]");if(rb)rb.addEventListener("click",function(){RG.setBusy(rb,true,"Saving…");API.post("/reports/"+r.id+"/review",{review_notes:(m.body.querySelector("#review-notes")||{}).value||null}).then(function(){m.close();load();}).catch(function(err){RG.setBusy(rb,false);RG.toastErr(err);});});}).catch(RG.toastErr);});
    load();
  }

  if (RG.mgmtView()) hrView(); else employeeView();
})();
