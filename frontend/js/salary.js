// /* salary.js - HR payroll management and the employee payslip library.
//    The HTML payslip preview intentionally mirrors the reportlab PDF layout. */
// (function () {
//   "use strict";
//   var SCOPE = document.body.dataset.scope;
//   var COMPANY = {
//     name: "Rocket Genie",
//     address: "Hno. 35, Office no. 301, 3rd Floor, Metro Pillar no. 35, Near Sai Baba Mandir, Laxmi Nagar, New Delhi - 110092"
//   };
//   var EARNING_PRESETS = ["Basic", "Incentive", "Bonus", "Other"];
//   var DEDUCTION_PRESETS = ["PT", "PF", "ESI", "Loan", "Other"];

//   /* ---------------- payslip preview (mirrors the PDF) ---------------- */
//   function payslipHtml(s) {
//     var logo = RG.APP_ROOT + "/assets/logo/rocket-genie-mark.png";
//     var earnings = s.earnings || [];
//     var deductions = s.deductions || [];
//     var rows = Math.max(earnings.length, deductions.length);
//     var body = "";
//     for (var i = 0; i < rows; i++) {
//       var e = earnings[i], d = deductions[i];
//       body += "<tr>" +
//         "<td>" + (e ? RG.esc(e.name) : "") + "</td>" +
//         '<td class="amt">' + (e ? RG.fmt.number(e.amount) : "") + "</td>" +
//         "<td>" + (d ? RG.esc(d.name) : "") + "</td>" +
//         '<td class="amt">' + (d ? (Number(d.amount) ? RG.fmt.number(d.amount) : "-") : "") + "</td>" +
//       "</tr>";
//     }
//     return '<div class="payslip">' +
//       '<div class="ps-head"><div class="ps-logo"><img src="' + logo + '" alt="Rocket Genie"></div>' +
//         '<div class="ps-title"><h3>Payslip</h3>' +
//           '<div class="ps-company">' + COMPANY.name + "</div>" +
//           '<div class="ps-addr">' + COMPANY.address + "</div></div>" +
//         '<div class="ps-logo"></div></div>' +
//       '<div class="ps-info">' +
//         '<div class="pair"><span>Date of Joining</span><span>: ' + RG.fmt.date(s.joining_date) + "</span></div>" +
//         '<div class="pair"><span>Employee name</span><span>: ' + RG.esc(s.employee_name) + "</span></div>" +
//         '<div class="pair"><span>Pay Period</span><span>: ' + RG.esc(s.period_label) + "</span></div>" +
//         '<div class="pair"><span>Designation</span><span>: ' + RG.esc(s.designation || "\u2014") + "</span></div>" +
//         '<div class="pair"><span>Worked Days</span><span>: ' + s.working_days + "</span></div>" +
//         '<div class="pair"><span>Department</span><span>: ' + RG.esc(s.department || "\u2014") + "</span></div>" +
//         '<div class="pair"><span>Employee ID</span><span>: ' + RG.esc(s.employee_code) + "</span></div>" +
//       "</div>" +
//       '<table class="ps-table"><thead><tr><th>Earnings</th><th>Amount</th><th>Deductions</th><th>Amount</th></tr></thead>' +
//         "<tbody>" + body +
//         '<tr class="ps-total"><td>Total Earnings</td><td class="amt">' + RG.fmt.number(s.total_earnings) + "</td>" +
//           '<td class="right">Total Deductions</td><td class="amt">' +
//           (Number(s.total_deductions) ? RG.fmt.number(s.total_deductions) : "-") + "</td></tr>" +
//         '<tr class="ps-net"><td></td><td></td><td class="right">Net Pay</td><td class="amt">' +
//           RG.fmt.number(s.net_pay) + "</td></tr>" +
//       "</tbody></table>" +
//       '<div class="ps-words"><div class="ps-figure">' + RG.fmt.number(s.net_pay) + "</div>" +
//         "<div>" + RG.esc(s.amount_in_words) + "</div></div>" +
//       '<div class="ps-sign">Employer Signature<div class="line"></div></div>' +
//       '<div class="ps-foot">This is system generated payslip</div>' +
//     "</div>";
//   }

//   /* The server is the authority on downloading: interns need HR permission on
//      this specific salary record. The button mirrors that answer, and a denied
//      API call is still handled if the button is bypassed. */
//   function canDownload(salary) {
//     if (API.session.isHr()) return true;
//     return salary.employee_can_download_payslip !== false;
//   }

//   function downloadBlockReason(salary) {
//     return salary.download_block_reason ||
//       "Download permission has not been granted by HR.";
//   }

//   /* Intern button states, mirroring the server's own answer:
//        before a request  -> [ View ] [ Request Download ]
//        pending           -> [ View ] [ Request Pending ] (disabled)
//        approved          -> [ View ] [ Download Payslip ]
//        rejected          -> [ View ] [ Request Again ]  + HR remarks */
//   function requestLabel(salary) {
//     if (salary.download_request_status === "Pending") return "Request Pending";
//     if (salary.download_request_status === "Rejected") return "Request Again";
//     return "Request Download";
//   }

//   function rejectionNote(salary) {
//     if (salary.download_request_status !== "Rejected") return "";
//     return '<p class="small mt-2 mb-0" style="color:var(--bad)">Download request rejected.' +
//       (salary.download_request_remarks
//         ? " HR remarks: " + RG.esc(salary.download_request_remarks)
//         : "") + "</p>";
//   }

//   function payslipPdfControl(salary) {
//     if (!salary.has_payslip) {
//       return '<span class="small muted">The PDF is generated when HR publishes the payslip.</span>';
//     }
//     if (canDownload(salary)) {
//       return '<button class="btn btn-primary" data-pdf>' + RG.icon("download", 15) +
//         " Download PDF</button>";
//     }
//     if (salary.download_request_status === "Pending") {
//       return '<button class="btn btn-primary" disabled ' +
//         'title="HR is reviewing your request">Request Pending</button>';
//     }
//     if (salary.can_request_download) {
//       return '<button class="btn btn-primary" data-request="' + salary.id + '">' +
//         requestLabel(salary) + "</button>";
//     }
//     return '<button class="btn btn-primary" disabled title="' +
//       RG.esc(downloadBlockReason(salary)) + '">' + RG.icon("download", 15) +
//       " Download PDF</button>";
//   }

//   /* Asks HR for permission on one specific payslip. The reason is required:
//      HR needs to understand why before approving. */
//   function openDownloadRequest(salary, onDone) {
//     var modal = RG.openModal({
//       title: "Request Payslip Download Permission",
//       size: "sm",
//       body: '<p class="small muted">Please explain why you need to download this ' +
//           "payslip. Your request will be sent to HR for approval.</p>" +
//         '<dl class="kv mb-3"><dt>Pay period</dt><dd>' + RG.esc(salary.period_label) +
//           "</dd><dt>Net pay</dt><dd>" + RG.fmt.money(salary.net_pay) + "</dd></dl>" +
//         (salary.download_request_status === "Rejected" && salary.download_request_remarks
//           ? '<p class="small mb-3" style="color:var(--bad)">Previously rejected \u2014 HR remarks: ' +
//             RG.esc(salary.download_request_remarks) + "</p>"
//           : "") +
//         '<div class="field full"><label for="dr-reason">Reason for Download</label>' +
//           '<textarea id="dr-reason" rows="4" ' +
//           'placeholder="Enter the reason for requesting this payslip..."></textarea>' +
//           '<p class="small muted mt-1 mb-0" id="dr-hint">A short sentence is enough.</p></div>',
//       footer: '<button class="btn" data-close>Cancel</button>' +
//         '<button class="btn btn-brand" data-send>Send Request</button>'
//     });

//     var field = modal.body.querySelector("#dr-reason");
//     var hint = modal.body.querySelector("#dr-hint");
//     field.focus();

//     modal.foot.querySelector("[data-send]").addEventListener("click", function () {
//       var button = modal.foot.querySelector("[data-send]");
//       var reason = (field.value || "").trim();
//       if (!reason) {
//         hint.textContent = "Please enter a reason before sending the request.";
//         hint.style.color = "var(--bad)";
//         field.focus();
//         return;
//       }
//       if (reason.length < 10) {
//         hint.textContent = "Please give HR a little more detail (at least a short sentence).";
//         hint.style.color = "var(--bad)";
//         field.focus();
//         return;
//       }
//       RG.setBusy(button, true, "Sending\u2026");
//       API.post("/salaries/" + salary.id + "/download-request", { reason: reason })
//         .then(function () {
//           modal.close();
//           RG.toastOk("Request sent to HR. You will be notified once it is reviewed.");
//           if (onDone) onDone();
//         })
//         .catch(function (err) { RG.setBusy(button, false); RG.toastErr(err); });
//     });
//   }

//   function cardDownloadControl(s) {
//     if (s.employee_can_download_payslip !== false) {
//       return '<button class="btn btn-sm" data-pdf="' + s.id + '">Download Payslip</button>';
//     }
//     if (s.download_request_status === "Pending") {
//       return '<button class="btn btn-sm" disabled title="HR is reviewing your request">' +
//         "Request Pending</button>";
//     }
//     if (s.can_request_download) {
//       return '<button class="btn btn-sm" data-request="' + s.id + '">' +
//         requestLabel(s) + "</button>";
//     }
//     return '<button class="btn btn-sm" disabled title="' +
//       RG.esc(downloadBlockReason(s)) + '">Download Payslip</button>';
//   }

//   function openPayslip(salary) {
//     /* The downloadable payslip PDF is the single source of truth.
//        View uses the authenticated inline PDF endpoint so the document shown
//        in the viewer is the same PDF generated by the backend. */
//     var modal = RG.openModal({
//       title: "Payslip · " + salary.period_label,
//       size: "lg",
//       body:
//         '<div class="payslip-pdf-viewer">' +
//           '<div class="payslip-pdf-loading">' +
//             '<div class="spinner"></div><span>Loading payslip…</span>' +
//           '</div>' +
//         '</div>',
//       footer: '<button class="btn" data-close>Close</button>' + payslipPdfControl(salary)
//     });

//     var pdfUrl = null;
//     var viewer = modal.body.querySelector(".payslip-pdf-viewer");

//     /* Use /payslip, not /download, because interns may view a credited
//        payslip before HR grants download permission. Both endpoints stream
//        the same stored/generated PDF bytes; only Content-Disposition differs. */
//     API.blob("/salaries/" + salary.id + "/payslip")
//       .then(function (file) {
//         pdfUrl = file.url;
//         viewer.innerHTML =
//           '<iframe class="payslip-pdf-frame" title="Payslip for ' +
//             RG.esc(salary.period_label) + '" src="' + file.url + '"></iframe>';
//       })
//       .catch(function (err) {
//         viewer.innerHTML = RG.errorState(err.message, "retry-payslip");
//         var retry = viewer.querySelector("#retry-payslip");
//         if (retry) {
//           retry.addEventListener("click", function () {
//             modal.close();
//             openPayslip(salary);
//           });
//         }
//       });

//     var ask = modal.foot.querySelector("[data-request]");
//     if (ask) {
//       ask.addEventListener("click", function () {
//         modal.close();
//         if (pdfUrl) URL.revokeObjectURL(pdfUrl);
//         openDownloadRequest(salary, function () { location.reload(); });
//       });
//     }

//     var pdf = modal.foot.querySelector("[data-pdf]");
//     if (pdf) {
//       pdf.addEventListener("click", function () {
//         RG.setBusy(pdf, true, "Preparing…");
//         API.download("/salaries/" + salary.id + "/payslip/download")
//           .then(function () {
//             RG.setBusy(pdf, false);
//             RG.toastOk("Payslip downloaded.");
//           })
//           .catch(function (err) {
//             RG.setBusy(pdf, false);
//             RG.toastErr(err);
//           });
//       });
//     }

//     /* Release the blob URL when the modal is closed to avoid leaking memory. */
//     var originalClose = modal.close;
//     modal.close = function () {
//       if (pdfUrl) {
//         URL.revokeObjectURL(pdfUrl);
//         pdfUrl = null;
//       }
//       return originalClose.apply(modal, arguments);
//     };
//   }
//   /* ======================= employee: salary slips ======================= */
//   function employeeView() {
//     var ctx = RG.boot({ scope: document.body.dataset.scope || "employee", active: "salary", title: "Salary Slips", subtitle: "Payslips & history" });
//     if (!ctx) return;
//     var cache = {};

//     function card(s) {
//       return '<div class="payslip-card"><div class="pc-top"><span class="pc-period">' + RG.esc(s.period_label) + "</span>" +
//         RG.badge(s.status) + "</div>" +
//         '<div class="pc-amount">' + RG.fmt.money(s.net_pay) + "</div>" +
//         '<div class="pc-meta">' + RG.fmt.money(s.total_earnings) + " earned \u00B7 " +
//           RG.fmt.money(s.total_deductions) + " deducted \u00B7 " + s.working_days + " days" +
//           (s.credit_date ? "<br>Credited " + RG.fmt.date(s.credit_date) : "") + "</div>" +
//         '<div class="pc-actions">' +
//           (s.status === "Credited"
//             ? '<button class="btn btn-sm btn-primary" data-view="' + s.id + '">View payslip</button>' +
//               (s.has_payslip ? cardDownloadControl(s) : "")
//             : '<span class="small muted">Available once credited</span>') +
//         "</div>" +
//         (s.status === "Credited" && s.employee_can_download_payslip === false &&
//          s.download_request_status !== "Rejected"
//           ? '<p class="small muted mt-2 mb-0">' + RG.esc(downloadBlockReason(s)) + "</p>"
//           : "") +
//         rejectionNote(s) +
//         "</div>";
//     }

//     function render(rows) {
//       rows.forEach(function (s) { cache[s.id] = s; });
//       var credited = rows.filter(function (s) { return s.status === "Credited"; });
//       var latest = credited[0] || rows[0];
//       ctx.page.innerHTML =
//         '<div class="page-head"><div><h1>Salary slips</h1>' +
//           '<p class="sub">Every payslip Rocket Genie has issued to you.</p></div></div>' +
//         (latest
//           ? '<div class="kpi-strip">' +
//               '<div class="kpi accent"><div class="kpi-label">Latest net pay</div>' +
//                 '<div class="kpi-value">' + RG.fmt.money(latest.net_pay) + "</div>" +
//                 '<div class="kpi-foot">' + RG.esc(latest.period_label) + "</div></div>" +
//               '<div class="kpi"><div class="kpi-label">Status</div><div class="kpi-value" style="font-size:20px">' +
//                 RG.esc(latest.status) + '</div><div class="kpi-foot">' +
//                 (latest.credit_date ? "credited " + RG.fmt.date(latest.credit_date) : "not credited yet") + "</div></div>" +
//               '<div class="kpi"><div class="kpi-label">Payslips available</div><div class="kpi-value">' +
//                 credited.length + '</div><div class="kpi-foot">of ' + rows.length + " records</div></div>" +
//               '<div class="kpi"><div class="kpi-label">Amount in words</div>' +
//                 '<div class="kpi-foot" style="margin-top:6px">' + RG.esc(latest.amount_in_words) + "</div></div>" +
//             "</div>"
//           : "") +
//         '<div class="card"><div class="card-head"><h3>Payslip history</h3>' +
//           '<span class="hint">' + rows.length + " record" + (rows.length === 1 ? "" : "s") + "</span></div>" +
//           '<div class="card-body">' +
//           (rows.length ? '<div class="payslip-cards">' + rows.map(card).join("") + "</div>"
//             : RG.emptyState("No salary slips available yet",
//               "Once HR processes your first salary it will appear here.", "", "money")) +
//           "</div></div>";

//       var open = RG.param("open");
//       if (open && cache[open]) openPayslip(cache[open]);
//     }

//     function load() {
//       ctx.page.innerHTML = RG.skeletonCards(3);
//       API.get("/salaries/me").then(render).catch(function (err) {
//         ctx.page.innerHTML = '<div class="card">' + RG.errorState(err.message, "retry") + "</div>";
//         var r = document.getElementById("retry"); if (r) r.addEventListener("click", load);
//       });
//     }

//     RG.on(document, "[data-view]", "click", function (e, b) { openPayslip(cache[b.dataset.view]); });
//     RG.on(document, "[data-request]", "click", function (e, b) {
//       var salary = cache[b.dataset.request];
//       if (salary) openDownloadRequest(salary, load);
//     });
//     RG.on(document, "[data-pdf]", "click", function (e, b) {
//       RG.setBusy(b, true, "\u2026");
//       API.download("/salaries/" + b.dataset.pdf + "/payslip/download")
//         .then(function () { RG.setBusy(b, false); RG.toastOk("Payslip downloaded."); })
//         .catch(function (err) {
//           RG.setBusy(b, false);
//           // If permission was withdrawn between render and click, offer the
//           // request flow rather than leaving the intern with a bare error.
//           var salary = cache[b.dataset.pdf];
//           if (err.status === 403 && salary && salary.is_intern) {
//             openDownloadRequest(salary, load);
//             return;
//           }
//           RG.toastErr(err);
//         });
//     });
//     load();
//   }

//   /* ======================= HR: payroll ======================= */
//   function hrView() {
//     var ctx = RG.boot({ scope: "hr", active: "salary", title: "Salary", subtitle: "Payroll & payslips" });
//     if (!ctx) return;

//     var now = new Date();
//     var state = {
//       page: 1, page_size: 15, status: "", department_id: "",
//       employee_id: RG.param("employee_id") || "",
//       period_year: now.getFullYear(), period_month: ""
//     };
//     var cache = {};
//     var employees = [];

//     ctx.page.innerHTML =
//       '<div class="page-head"><div><h1>Payroll</h1>' +
//         '<p class="sub">Build a salary record, publish the payslip, then mark it credited.</p></div>' +
//         '<div class="page-actions"><button class="btn btn-brand" data-new>' + RG.icon("plus", 16) + " New salary record</button></div></div>" +
//       '<div id="kpis" class="kpi-strip">' +
//         '<div class="kpi"><div class="skeleton sk-line"></div></div>' +
//         '<div class="kpi"><div class="skeleton sk-line"></div></div>' +
//         '<div class="kpi"><div class="skeleton sk-line"></div></div>' +
//         '<div class="kpi"><div class="skeleton sk-line"></div></div></div>' +
//       '<div class="card"><div class="toolbar">' +
//         '<div class="filters" style="margin-left:0">' +
//           '<select id="f-dept"><option value="">All departments</option></select>' +
//           '<select id="f-status"><option value="">Any status</option><option value="Pending">Pending</option>' +
//             '<option value="Processing">Processing</option><option value="Credited">Credited</option></select>' +
//           '<select id="f-month"><option value="">Any month</option>' +
//             RG.MONTHS.map(function (m, i) { return '<option value="' + (i + 1) + '">' + m + "</option>"; }).join("") + "</select>" +
//           '<select id="f-year">' +
//             [now.getFullYear() + 1, now.getFullYear(), now.getFullYear() - 1, now.getFullYear() - 2].map(function (y) {
//               return '<option value="' + y + '"' + (y === now.getFullYear() ? " selected" : "") + ">" + y + "</option>";
//             }).join("") + "</select>" +
//         "</div></div>" +
//         '<div id="host">' + RG.skeletonRows(8) + "</div>" +
//         '<div class="pager" id="pager"></div></div>';

//     var host = document.getElementById("host");

//     API.get("/employees", { page: 1, page_size: 200 }).then(function (data) {
//       employees = data.items || [];
//     }).catch(function () { /* employee picker degrades gracefully */ });

//     API.get("/departments", { active_only: true }).then(function (rows) {
//       var departments = Array.isArray(rows) ? rows : ((rows && rows.items) || []);
//       departments = departments.filter(function (d) { return d && d.is_active !== false; });
//       document.getElementById("f-dept").innerHTML = '<option value="">All departments</option>' + RG.optionList(departments, "id", "name", state.department_id);
//     }).catch(function () { /* filters degrade gracefully */ });

//     API.get("/dashboard/hr").then(function (data) {
//       var k = data.kpis;
//       document.getElementById("kpis").innerHTML =
//         '<div class="kpi accent"><div class="kpi-label">Payroll this period</div><div class="kpi-value">' +
//           RG.fmt.money(k.monthly_payroll) + '</div><div class="kpi-foot">net pay across records</div></div>' +
//         '<div class="kpi"><div class="kpi-label">Credited</div><div class="kpi-value">' + k.salary_credited +
//           '</div><div class="kpi-foot up">paid out</div></div>' +
//         '<div class="kpi"><div class="kpi-label">Processing</div><div class="kpi-value">' + k.salary_processing +
//           '</div><div class="kpi-foot">in progress</div></div>' +
//         '<div class="kpi"><div class="kpi-label">Pending</div><div class="kpi-value">' + k.salary_pending +
//           '</div><div class="kpi-foot warn">awaiting action</div></div>';
//     }).catch(function () { document.getElementById("kpis").innerHTML = ""; });

//     function row(s) {
//       cache[s.id] = s;
//       var actions =
//         '<button class="btn btn-sm" data-view="' + s.id + '">Payslip</button>' +
//         '<button class="btn btn-sm" data-edit="' + s.id + '">Edit</button>';
//       if (s.status !== "Credited") {
//         actions += '<button class="btn btn-sm btn-ok" data-credit="' + s.id + '">Mark credited</button>';
//       }
//       actions += '<button class="btn btn-sm btn-ghost" data-slip="' + s.id + '">Upload slip</button>';
//       if (s.is_intern) {
//         actions += '<button class="btn btn-sm ' +
//           (s.intern_download_allowed ? "btn-ok" : "btn-ghost") +
//           '" data-perm="' + s.id + '" title="' +
//           (s.intern_download_allowed
//             ? "Intern can download this payslip \u2014 click to withdraw"
//             : "Intern can only view this payslip \u2014 click to allow downloading") +
//           '">' + (s.intern_download_allowed ? "Download: on" : "Download: off") + "</button>";
//       }
//       return "<tr>" +
//         '<td data-label="Employee"><div class="identity">' +
//           RG.avatar({ full_name: s.employee_name, id: s.employee_id }, "sm") +
//           '<div><div class="name truncate">' + RG.esc(s.employee_name) + "</div>" +
//           '<div class="meta">' + RG.esc(s.employee_code) + " \u00B7 " + RG.esc(s.department || "") + "</div></div></div></td>" +
//         '<td data-label="Pay period" class="nowrap">' + RG.esc(s.period_label) + "</td>" +
//         '<td data-label="Days" class="num">' + s.working_days + "</td>" +
//         '<td data-label="Earnings" class="num">' + RG.fmt.money(s.total_earnings) + "</td>" +
//         '<td data-label="Deductions" class="num">' + RG.fmt.money(s.total_deductions) + "</td>" +
//         '<td data-label="Net pay" class="num strong">' + RG.fmt.money(s.net_pay) + "</td>" +
//         '<td data-label="Status">' + RG.badge(s.status) +
//           (s.has_payslip ? ' <span class="chip">PDF</span>' : "") +
//           (s.is_intern
//             ? ' <span class="chip" title="Intern payslip download permission">' +
//               (s.intern_download_allowed ? "DL allowed" : "View only") + "</span>"
//             : "") + "</td>" +
//         '<td data-label="Credited" class="nowrap">' + (s.credit_date ? RG.fmt.date(s.credit_date) : "\u2014") + "</td>" +
//         '<td class="actions" data-label="Actions">' + actions + "</td></tr>";
//     }

//     function load() {
//       API.get("/salaries", state).then(function (data) {
//         var items = data.items || [];
//         if (!items.length) {
//           host.innerHTML = RG.emptyState("No salary records", "Create one for this pay period.",
//             '<button class="btn btn-sm btn-brand" data-new>New salary record</button>', "money");
//           document.getElementById("pager").innerHTML = "";
//           return;
//         }
//         host.innerHTML = '<div class="table-scroll"><table class="data"><thead><tr>' +
//           "<th>Employee</th><th>Pay period</th><th>Days</th><th>Earnings</th><th>Deductions</th>" +
//           "<th>Net pay</th><th>Status</th><th>Credited</th><th></th></tr></thead><tbody>" +
//           items.map(row).join("") + "</tbody></table></div>";
//         RG.hydratePhotos(host);
//         RG.renderPager(document.getElementById("pager"), data.meta, function (p) { state.page = p; load(); });
//       }).catch(function (err) {
//         host.innerHTML = RG.errorState(err.message, "retry");
//         var r = document.getElementById("retry"); if (r) r.addEventListener("click", load);
//       });
//     }

//     /* ---- component editor ---- */
//     function componentRow(type, component) {
//       var presets = type === "earning" ? EARNING_PRESETS : DEDUCTION_PRESETS;
//       var name = component ? component.name : "";
//       return '<div class="component-row" data-type="' + type + '">' +
//         '<div class="field"><input type="text" class="c-name" list="preset-' + type + '" placeholder="' +
//           (type === "earning" ? "Earning name" : "Deduction name") + '" value="' + RG.esc(name) + '"></div>' +
//         '<div class="field"><input type="number" class="c-amount" min="0" step="0.01" placeholder="0.00" value="' +
//           (component ? component.amount : "") + '"></div>' +
//         '<button type="button" class="btn btn-icon btn-ghost rm" title="Remove">' + RG.icon("x", 15) + "</button>" +
//         "<datalist id=\"preset-" + type + "\">" + presets.map(function (p) {
//           return '<option value="' + p + '"></option>';
//         }).join("") + "</datalist></div>";
//     }

//     function salaryForm(existing) {
//       var s = existing || {};
//       var earnings = (s.earnings && s.earnings.length) ? s.earnings
//         : [{ name: "Basic", amount: "" }, { name: "Incentive", amount: "" }];
//       var deductions = (s.deductions && s.deductions.length) ? s.deductions : [{ name: "PF", amount: 0 }];
//       return '<form id="sal-form">' +
//         '<div class="form-grid">' +
//           '<div class="field"><label for="s-emp">Employee <span class="req">*</span></label>' +
//             '<select id="s-emp"' + (existing ? " disabled" : "") + " required>" +
//             RG.optionList(employees, "id", "full_name", s.employee_id) + "</select></div>" +
//           '<div class="field"><label for="s-days">Worked days <span class="req">*</span></label>' +
//             '<input id="s-days" type="number" min="0" max="31" value="' + (s.working_days || 30) + '" required></div>' +
//           '<div class="field"><label for="s-month">Pay month <span class="req">*</span></label>' +
//             '<select id="s-month"' + (existing ? " disabled" : "") + ">" +
//             RG.MONTHS.map(function (m, i) {
//               var selected = (s.period_month || (now.getMonth() + 1)) === i + 1;
//               return '<option value="' + (i + 1) + '"' + (selected ? " selected" : "") + ">" + m + "</option>";
//             }).join("") + "</select></div>" +
//           '<div class="field"><label for="s-year">Pay year <span class="req">*</span></label>' +
//             '<input id="s-year" type="number" min="2000" max="2100" value="' + (s.period_year || now.getFullYear()) +
//             '"' + (existing ? " disabled" : "") + "></div>" +
//           '<div class="field"><label for="s-status">Status</label><select id="s-status">' +
//             ["Pending", "Processing", "Credited"].map(function (st) {
//               return '<option value="' + st + '"' + ((s.status || "Pending") === st ? " selected" : "") + ">" + st + "</option>";
//             }).join("") + "</select></div>" +
//           '<div class="field"><label for="s-credit">Credit date</label>' +
//             '<input id="s-credit" type="date" value="' + (s.credit_date || "") + '"></div>' +
//           '<div class="field full"><label for="s-remarks">Remarks</label>' +
//             '<input id="s-remarks" type="text" value="' + RG.esc(s.remarks || "") + '"></div>' +
//         "</div>" +
//         '<div class="grid grid-2 mt-4">' +
//           '<div><div class="form-section"><h4>Earnings</h4>' +
//             '<div id="earnings">' + earnings.map(function (c) { return componentRow("earning", c); }).join("") + "</div>" +
//             '<button type="button" class="btn btn-sm mt-2" data-add="earning">' + RG.icon("plus", 14) + " Add earning</button></div></div>" +
//           '<div><div class="form-section"><h4>Deductions</h4>' +
//             '<div id="deductions">' + deductions.map(function (c) { return componentRow("deduction", c); }).join("") + "</div>" +
//             '<button type="button" class="btn btn-sm mt-2" data-add="deduction">' + RG.icon("plus", 14) + " Add deduction</button></div></div>" +
//         "</div>" +
//         '<div class="totals-box mt-4" id="totals"></div></form>';
//     }

//     function collect(modal) {
//       var components = [];
//       modal.body.querySelectorAll(".component-row").forEach(function (rowEl) {
//         var name = rowEl.querySelector(".c-name").value.trim();
//         var amount = rowEl.querySelector(".c-amount").value;
//         if (!name) return;
//         components.push({
//           component_type: rowEl.dataset.type,
//           name: name,
//           amount: Number(amount || 0)
//         });
//       });
//       return components;
//     }

//     function refreshTotals(modal) {
//       var components = collect(modal);
//       var earn = 0, deduct = 0;
//       components.forEach(function (c) {
//         if (c.component_type === "earning") earn += c.amount; else deduct += c.amount;
//       });
//       modal.body.querySelector("#totals").innerHTML =
//         '<div class="line"><span>Total earnings</span><b>' + RG.fmt.money(earn, true) + "</b></div>" +
//         '<div class="line"><span>Total deductions</span><b>' + RG.fmt.money(deduct, true) + "</b></div>" +
//         '<div class="line net"><span>Net pay</span><b>' + RG.fmt.money(earn - deduct, true) + "</b></div>" +
//         '<div class="words">Computed on the server when saved \u2014 the payslip words follow the stored net pay.</div>';
//     }

//     function openSalaryModal(existing) {
//       var modal = RG.openModal({
//         title: existing ? "Edit salary \u00B7 " + existing.period_label : "New salary record",
//         size: "lg",
//         body: salaryForm(existing),
//         footer: '<button class="btn" data-close>Cancel</button>' +
//           '<button class="btn btn-brand" data-save>' + (existing ? "Save changes" : "Create record") + "</button>",
//         onOpen: function (m) { refreshTotals(m); }
//       });

//       modal.body.addEventListener("input", function () { refreshTotals(modal); });
//       modal.body.addEventListener("click", function (e) {
//         var add = e.target.closest("[data-add]");
//         if (add) {
//           var type = add.dataset.add;
//           var container = modal.body.querySelector(type === "earning" ? "#earnings" : "#deductions");
//           container.insertAdjacentHTML("beforeend", componentRow(type, null));
//           refreshTotals(modal);
//           return;
//         }
//         var remove = e.target.closest(".rm");
//         if (remove) { remove.closest(".component-row").remove(); refreshTotals(modal); }
//       });

//       modal.foot.querySelector("[data-save]").addEventListener("click", function () {
//         var form = modal.body.querySelector("#sal-form");
//         if (!form.reportValidity()) return;
//         var components = collect(modal);
//         if (!components.some(function (c) { return c.component_type === "earning" && c.amount > 0; })) {
//           RG.toast("Add at least one earning with an amount.", "bad", "Nothing to pay");
//           return;
//         }
//         var button = modal.foot.querySelector("[data-save]");
//         RG.setBusy(button, true, "Saving\u2026");
//         var common = {
//           working_days: Number(modal.body.querySelector("#s-days").value),
//           status: modal.body.querySelector("#s-status").value,
//           credit_date: modal.body.querySelector("#s-credit").value || null,
//           remarks: modal.body.querySelector("#s-remarks").value.trim() || null,
//           components: components
//         };
//         var request;
//         if (existing) {
//           request = API.put("/salaries/" + existing.id, common);
//         } else {
//           common.employee_id = Number(modal.body.querySelector("#s-emp").value);
//           common.period_month = Number(modal.body.querySelector("#s-month").value);
//           common.period_year = Number(modal.body.querySelector("#s-year").value);
//           request = API.post("/salaries", common);
//         }
//         request.then(function () {
//           modal.close();
//           RG.toastOk(existing ? "Salary record updated." : "Salary record created.");
//           load();
//         }).catch(function (err) { RG.setBusy(button, false); RG.toastErr(err); });
//       });
//     }

//     /* ---- credit / upload ---- */
//     function creditModal(salary) {
//       var modal = RG.openModal({
//         title: "Mark salary credited", size: "sm",
//         body: "<p>This will publish " + RG.esc(salary.employee_name) + "\u2019s " +
//             RG.esc(salary.period_label) + " payslip and notify them.</p>" +
//           '<div class="field"><label for="cd">Credit date</label>' +
//             '<input id="cd" type="date" value="' + (salary.credit_date || new Date().toISOString().slice(0, 10)) + '"></div>' +
//           '<label class="switch mt-4"><input type="checkbox" id="attach" checked><span class="track"></span>' +
//             '<span class="switch-text"><b>Attach the payslip PDF to the email</b>' +
//             "<span>Generates it first if it doesn\u2019t exist yet.</span></span></label>" +
//           '<p class="small muted mt-4 mb-0">' + RG.icon("shield", 13) +
//             " Running this twice won\u2019t send a second email or create a duplicate notification.</p>",
//         footer: '<button class="btn" data-close>Cancel</button>' +
//           '<button class="btn btn-ok" data-go>Mark credited</button>'
//       });
//       modal.foot.querySelector("[data-go]").addEventListener("click", function () {
//         var button = modal.foot.querySelector("[data-go]");
//         RG.setBusy(button, true, "Publishing\u2026");
//         API.post("/salaries/" + salary.id + "/credit", {
//           credit_date: modal.body.querySelector("#cd").value || null,
//           attach_payslip: modal.body.querySelector("#attach").checked
//         }).then(function () {
//           modal.close();
//           RG.toastOk("Salary credited \u2014 payslip published, notification and email sent.");
//           load();
//         }).catch(function (err) { RG.setBusy(button, false); RG.toastErr(err); });
//       });
//     }

//     function slipModal(salary) {
//       var modal = RG.openModal({
//         title: "Payslip \u00B7 " + salary.period_label, size: "sm",
//         body: '<p class="small muted">Generate the Rocket Genie payslip from the salary data, or upload a signed PDF of your own.</p>' +
//           '<button class="btn btn-block btn-primary" data-generate>' + RG.icon("doc", 15) + " Generate payslip PDF</button>" +
//           '<div class="divider"></div>' +
//           '<div class="drop" id="drop"><div class="drop-icon">' + RG.icon("upload", 20) + "</div>" +
//             "<b>Upload a PDF payslip</b><span>PDF only \u00B7 up to 5 MB</span>" +
//             '<input type="file" id="file" accept=".pdf"></div>' +
//           '<ul class="file-list" id="chosen"></ul>',
//         footer: '<button class="btn" data-close>Close</button>' +
//           '<button class="btn btn-brand" data-send disabled>Upload</button>'
//       });
//       var input = modal.body.querySelector("#file");
//       var send = modal.foot.querySelector("[data-send]");
//       modal.body.querySelector("#drop").addEventListener("click", function () { input.click(); });
//       input.addEventListener("change", function () {
//         var file = input.files[0];
//         if (!file) return;
//         modal.body.querySelector("#chosen").innerHTML = '<li class="file-item"><span class="f-thumb">PDF</span>' +
//           '<div class="f-meta"><b class="truncate">' + RG.esc(file.name) + "</b><span>" + RG.fmt.bytes(file.size) + "</span></div></li>";
//         send.disabled = false;
//       });
//       modal.body.querySelector("[data-generate]").addEventListener("click", function () {
//         var button = modal.body.querySelector("[data-generate]");
//         RG.setBusy(button, true, "Generating\u2026");
//         API.post("/salaries/" + salary.id + "/payslip/generate", {}).then(function () {
//           modal.close(); RG.toastOk("Payslip PDF generated."); load();
//         }).catch(function (err) { RG.setBusy(button, false); RG.toastErr(err); });
//       });
//       send.addEventListener("click", function () {
//         var form = new FormData();
//         form.append("file", input.files[0]);
//         RG.setBusy(send, true, "Uploading\u2026");
//         API.upload("/salaries/" + salary.id + "/payslip/upload", form).then(function () {
//           modal.close(); RG.toastOk("Payslip uploaded."); load();
//         }).catch(function (err) { RG.setBusy(send, false); RG.toastErr(err); });
//       });
//     }

//     [["f-dept", "department_id"], ["f-status", "status"], ["f-month", "period_month"], ["f-year", "period_year"]]
//       .forEach(function (pair) {
//         document.getElementById(pair[0]).addEventListener("change", function (e) {
//           state[pair[1]] = e.target.value; state.page = 1; load();
//         });
//       });

//     RG.on(ctx.page, "[data-new]", "click", function () { openSalaryModal(null); });
//     RG.on(ctx.page, "[data-view]", "click", function (e, b) { openPayslip(cache[b.dataset.view]); });
//     RG.on(ctx.page, "[data-edit]", "click", function (e, b) { openSalaryModal(cache[b.dataset.edit]); });
//     RG.on(ctx.page, "[data-credit]", "click", function (e, b) { creditModal(cache[b.dataset.credit]); });
//     RG.on(ctx.page, "[data-slip]", "click", function (e, b) { slipModal(cache[b.dataset.slip]); });

//     load();
//   }

//   if (SCOPE === "hr") hrView(); else employeeView();
// })();


/* salary.js - HR payroll management and the employee payslip library.
   The HTML payslip preview intentionally mirrors the reportlab PDF layout. */
(function () {
  "use strict";

  var SCOPE = document.body.dataset.scope;

  var COMPANY = {
    name: "Rocket Genie",
    address: "Hno. 35, Office no. 301, 3rd Floor, Metro Pillar no. 35, Near Sai Baba Mandir, Laxmi Nagar, New Delhi - 110092"
  };

  var EARNING_PRESETS = ["Basic", "Incentive", "Bonus", "Other"];
  var DEDUCTION_PRESETS = ["PT", "PF", "ESI", "Loan", "Other"];

  /* ---------------- payslip preview ---------------- */

  function payslipHtml(s) {
    var logo = RG.APP_ROOT + "/assets/logo/rocket-genie-mark.png";
    var earnings = s.earnings || [];
    var deductions = s.deductions || [];
    var rows = Math.max(earnings.length, deductions.length);
    var body = "";

    for (var i = 0; i < rows; i++) {
      var e = earnings[i];
      var d = deductions[i];

      body += "<tr>" +
        "<td>" + (e ? RG.esc(e.name) : "") + "</td>" +
        '<td class="amt">' + (e ? RG.fmt.number(e.amount) : "") + "</td>" +
        "<td>" + (d ? RG.esc(d.name) : "") + "</td>" +
        '<td class="amt">' +
          (d ? (Number(d.amount) ? RG.fmt.number(d.amount) : "-") : "") +
        "</td>" +
      "</tr>";
    }

    return '<div class="payslip">' +
      '<div class="ps-head">' +
        '<div class="ps-logo">' +
          '<img src="' + logo + '" alt="Rocket Genie">' +
        "</div>" +
        '<div class="ps-title">' +
          "<h3>Payslip</h3>" +
          '<div class="ps-company">' + COMPANY.name + "</div>" +
          '<div class="ps-addr">' + COMPANY.address + "</div>" +
        "</div>" +
        '<div class="ps-logo"></div>' +
      "</div>" +

      '<div class="ps-info">' +
        '<div class="pair"><span>Date of Joining</span><span>: ' +
          RG.fmt.date(s.joining_date) +
        "</span></div>" +

        '<div class="pair"><span>Employee name</span><span>: ' +
          RG.esc(s.employee_name) +
        "</span></div>" +

        '<div class="pair"><span>Pay Period</span><span>: ' +
          RG.esc(s.period_label) +
        "</span></div>" +

        '<div class="pair"><span>Designation</span><span>: ' +
          RG.esc(s.designation || "—") +
        "</span></div>" +

        '<div class="pair"><span>Worked Days</span><span>: ' +
          s.working_days +
        "</span></div>" +

        '<div class="pair"><span>Department</span><span>: ' +
          RG.esc(s.department || "—") +
        "</span></div>" +

        '<div class="pair"><span>Employee ID</span><span>: ' +
          RG.esc(s.employee_code) +
        "</span></div>" +
      "</div>" +

      '<table class="ps-table">' +
        "<thead>" +
          "<tr>" +
            "<th>Earnings</th>" +
            "<th>Amount</th>" +
            "<th>Deductions</th>" +
            "<th>Amount</th>" +
          "</tr>" +
        "</thead>" +

        "<tbody>" +
          body +

          '<tr class="ps-total">' +
            "<td>Total Earnings</td>" +
            '<td class="amt">' +
              RG.fmt.number(s.total_earnings) +
            "</td>" +

            '<td class="right">Total Deductions</td>' +
            '<td class="amt">' +
              (Number(s.total_deductions)
                ? RG.fmt.number(s.total_deductions)
                : "-") +
            "</td>" +
          "</tr>" +

          '<tr class="ps-net">' +
            "<td></td>" +
            "<td></td>" +
            '<td class="right">Net Pay</td>' +
            '<td class="amt">' +
              RG.fmt.number(s.net_pay) +
            "</td>" +
          "</tr>" +

        "</tbody>" +
      "</table>" +

      '<div class="ps-words">' +
        '<div class="ps-figure">' +
          RG.fmt.number(s.net_pay) +
        "</div>" +
        "<div>" +
          RG.esc(s.amount_in_words) +
        "</div>" +
      "</div>" +

      '<div class="ps-sign">Employer Signature<div class="line"></div></div>' +
      '<div class="ps-foot">This is system generated payslip</div>' +

    "</div>";
  }

  /* ---------------------------------------------------------
     Download permission
  --------------------------------------------------------- */

  function canDownload(salary) {
    if (API.session.isHr()) return true;
    return salary.employee_can_download_payslip !== false;
  }

  function downloadBlockReason(salary) {
    return salary.download_block_reason ||
      "Download permission has not been granted by HR.";
  }

  function requestLabel(salary) {
    if (salary.download_request_status === "Pending") {
      return "Request Pending";
    }

    if (salary.download_request_status === "Rejected") {
      return "Request Again";
    }

    return "Request Download";
  }

  function rejectionNote(salary) {
    if (salary.download_request_status !== "Rejected") {
      return "";
    }

    return '<p class="small mt-2 mb-0" style="color:var(--bad)">' +
      "Download request rejected." +
      (
        salary.download_request_remarks
          ? " HR remarks: " +
            RG.esc(salary.download_request_remarks)
          : ""
      ) +
      "</p>";
  }

  function payslipPdfControl(salary) {
    if (!salary.has_payslip) {
      return '<span class="small muted">' +
        "The PDF is generated when HR publishes the payslip." +
      "</span>";
    }

    if (canDownload(salary)) {
      return '<button class="btn btn-primary" data-pdf>' +
        RG.icon("download", 15) +
        " Download PDF</button>";
    }

    if (salary.download_request_status === "Pending") {
      return '<button class="btn btn-primary" disabled ' +
        'title="HR is reviewing your request">' +
        "Request Pending</button>";
    }

    if (salary.can_request_download) {
      return '<button class="btn btn-primary" data-request="' +
        salary.id +
        '">' +
        requestLabel(salary) +
        "</button>";
    }

    return '<button class="btn btn-primary" disabled title="' +
      RG.esc(downloadBlockReason(salary)) +
      '">' +
      RG.icon("download", 15) +
      " Download PDF</button>";
  }

  /* ---------------------------------------------------------
     Download request
  --------------------------------------------------------- */

  function openDownloadRequest(salary, onDone) {
    var modal = RG.openModal({
      title: "Request Payslip Download Permission",
      size: "sm",

      body:
        '<p class="small muted">' +
          "Please explain why you need to download this payslip. " +
          "Your request will be sent to HR for approval." +
        "</p>" +

        '<dl class="kv mb-3">' +
          "<dt>Pay period</dt>" +
          "<dd>" +
            RG.esc(salary.period_label) +
          "</dd>" +

          "<dt>Net pay</dt>" +
          "<dd>" +
            RG.fmt.money(salary.net_pay) +
          "</dd>" +
        "</dl>" +

        (
          salary.download_request_status === "Rejected" &&
          salary.download_request_remarks
            ? '<p class="small mb-3" style="color:var(--bad)">' +
                "Previously rejected — HR remarks: " +
                RG.esc(salary.download_request_remarks) +
              "</p>"
            : ""
        ) +

        '<div class="field full">' +
          '<label for="dr-reason">Reason for Download</label>' +
          '<textarea id="dr-reason" rows="4" ' +
            'placeholder="Enter the reason for requesting this payslip...">' +
          "</textarea>" +
          '<p class="small muted mt-1 mb-0" id="dr-hint">' +
            "A short sentence is enough." +
          "</p>" +
        "</div>",

      footer:
        '<button class="btn" data-close>Cancel</button>' +
        '<button class="btn btn-brand" data-send>Send Request</button>'
    });

    var field = modal.body.querySelector("#dr-reason");
    var hint = modal.body.querySelector("#dr-hint");

    field.focus();

    modal.foot.querySelector("[data-send]")
      .addEventListener("click", function () {

        var button = modal.foot.querySelector("[data-send]");
        var reason = (field.value || "").trim();

        if (!reason) {
          hint.textContent =
            "Please enter a reason before sending the request.";
          hint.style.color = "var(--bad)";
          field.focus();
          return;
        }

        if (reason.length < 10) {
          hint.textContent =
            "Please give HR a little more detail (at least a short sentence).";
          hint.style.color = "var(--bad)";
          field.focus();
          return;
        }

        RG.setBusy(button, true, "Sending…");

        API.post(
          "/salaries/" + salary.id + "/download-request",
          { reason: reason }
        )
        .then(function () {
          modal.close();

          RG.toastOk(
            "Request sent to HR. You will be notified once it is reviewed."
          );

          if (onDone) onDone();
        })
        .catch(function (err) {
          RG.setBusy(button, false);
          RG.toastErr(err);
        });
      });
  }

  function cardDownloadControl(s) {
    if (s.employee_can_download_payslip !== false) {
      return '<button class="btn btn-sm" data-pdf="' +
        s.id +
        '">' +
        "Download Payslip" +
        "</button>";
    }

    if (s.download_request_status === "Pending") {
      return '<button class="btn btn-sm" disabled ' +
        'title="HR is reviewing your request">' +
        "Request Pending</button>";
    }

    if (s.can_request_download) {
      return '<button class="btn btn-sm" data-request="' +
        s.id +
        '">' +
        requestLabel(s) +
        "</button>";
    }

    return '<button class="btn btn-sm" disabled title="' +
      RG.esc(downloadBlockReason(s)) +
      '">' +
      "Download Payslip</button>";
  }

  /* ---------------------------------------------------------
     Payslip viewer
  --------------------------------------------------------- */

  function openPayslip(salary) {

    var modal = RG.openModal({
      title: "Payslip · " + salary.period_label,
      size: "lg",

      body:
        '<div class="payslip-pdf-viewer">' +
          '<div class="payslip-pdf-loading">' +
            '<div class="spinner"></div>' +
            "<span>Loading payslip…</span>" +
          "</div>" +
        "</div>",

      footer:
        '<button class="btn" data-close>Close</button>' +
        payslipPdfControl(salary)
    });

    var pdfUrl = null;

    var viewer =
      modal.body.querySelector(".payslip-pdf-viewer");

    API.blob(
      "/salaries/" + salary.id + "/payslip"
    )
    .then(function (file) {

      pdfUrl = file.url;

      viewer.innerHTML =
        '<iframe class="payslip-pdf-frame" ' +
        'title="Payslip for ' +
        RG.esc(salary.period_label) +
        '" src="' +
        file.url +
        '"></iframe>';
    })
    .catch(function (err) {

      viewer.innerHTML =
        RG.errorState(err.message, "retry-payslip");

      var retry =
        viewer.querySelector("#retry-payslip");

      if (retry) {
        retry.addEventListener("click", function () {
          modal.close();
          openPayslip(salary);
        });
      }
    });

    var ask =
      modal.foot.querySelector("[data-request]");

    if (ask) {
      ask.addEventListener("click", function () {

        modal.close();

        if (pdfUrl) {
          URL.revokeObjectURL(pdfUrl);
        }

        openDownloadRequest(
          salary,
          function () {
            location.reload();
          }
        );
      });
    }

    var pdf =
      modal.foot.querySelector("[data-pdf]");

    if (pdf) {
      pdf.addEventListener("click", function () {

        RG.setBusy(pdf, true, "Preparing…");

        API.download(
          "/salaries/" +
          salary.id +
          "/payslip/download"
        )
        .then(function () {

          RG.setBusy(pdf, false);

          RG.toastOk("Payslip downloaded.");
        })
        .catch(function (err) {

          RG.setBusy(pdf, false);

          RG.toastErr(err);
        });
      });
    }

    var originalClose = modal.close;

    modal.close = function () {

      if (pdfUrl) {
        URL.revokeObjectURL(pdfUrl);
        pdfUrl = null;
      }

      return originalClose.apply(
        modal,
        arguments
      );
    };
  }

  /* =========================================================
     EMPLOYEE SALARY SLIPS
  ========================================================= */

  function employeeView() {

    var ctx = RG.boot({
      scope: "employee",
      active: "salary",
      title: "Salary Slips",
      subtitle: "Payslips & history"
    });

    if (!ctx) return;

    var cache = {};

    function card(s) {

      return '<div class="payslip-card">' +

        '<div class="pc-top">' +
          '<span class="pc-period">' +
            RG.esc(s.period_label) +
          "</span>" +
          RG.badge(s.status) +
        "</div>" +

        '<div class="pc-amount">' +
          RG.fmt.money(s.net_pay) +
        "</div>" +

        '<div class="pc-meta">' +
          RG.fmt.money(s.total_earnings) +
          " earned · " +
          RG.fmt.money(s.total_deductions) +
          " deducted · " +
          s.working_days +
          " days" +

          (
            s.credit_date
              ? "<br>Credited " +
                RG.fmt.date(s.credit_date)
              : ""
          ) +

        "</div>" +

        '<div class="pc-actions">' +

          (
            s.status === "Credited"

              ? '<button class="btn btn-sm btn-primary" data-view="' +
                  s.id +
                  '">' +
                  "View payslip</button>" +

                (
                  s.has_payslip
                    ? cardDownloadControl(s)
                    : ""
                )

              : '<span class="small muted">' +
                  "Available once credited" +
                "</span>"
          ) +

        "</div>" +

        (
          s.status === "Credited" &&
          s.employee_can_download_payslip === false &&
          s.download_request_status !== "Rejected"

            ? '<p class="small muted mt-2 mb-0">' +
                RG.esc(downloadBlockReason(s)) +
              "</p>"

            : ""
        ) +

        rejectionNote(s) +

      "</div>";
    }

    function render(rows) {

      rows.forEach(function (s) {
        cache[s.id] = s;
      });

      var credited =
        rows.filter(function (s) {
          return s.status === "Credited";
        });

      var latest =
        credited[0] || rows[0];

      ctx.page.innerHTML =

        '<div class="page-head">' +
          "<div>" +
            "<h1>Salary slips</h1>" +
            '<p class="sub">' +
              "Every payslip Rocket Genie has issued to you." +
            "</p>" +
          "</div>" +
        "</div>" +

        (
          latest

            ? '<div class="kpi-strip">' +

                '<div class="kpi accent">' +
                  '<div class="kpi-label">Latest net pay</div>' +
                  '<div class="kpi-value">' +
                    RG.fmt.money(latest.net_pay) +
                  "</div>" +
                  '<div class="kpi-foot">' +
                    RG.esc(latest.period_label) +
                  "</div>" +
                "</div>" +

                '<div class="kpi">' +
                  '<div class="kpi-label">Status</div>' +
                  '<div class="kpi-value" style="font-size:20px">' +
                    RG.esc(latest.status) +
                  "</div>" +
                  '<div class="kpi-foot">' +
                    (
                      latest.credit_date
                        ? "credited " +
                          RG.fmt.date(latest.credit_date)
                        : "not credited yet"
                    ) +
                  "</div>" +
                "</div>" +

                '<div class="kpi">' +
                  '<div class="kpi-label">Payslips available</div>' +
                  '<div class="kpi-value">' +
                    credited.length +
                  "</div>" +
                  '<div class="kpi-foot">' +
                    "of " +
                    rows.length +
                    " records" +
                  "</div>" +
                "</div>" +

                '<div class="kpi">' +
                  '<div class="kpi-label">Amount in words</div>' +
                  '<div class="kpi-foot" style="margin-top:6px">' +
                    RG.esc(latest.amount_in_words) +
                  "</div>" +
                "</div>" +

              "</div>"

            : ""
        ) +

        '<div class="card">' +

          '<div class="card-head">' +
            "<h3>Payslip history</h3>" +
            '<span class="hint">' +
              rows.length +
              " record" +
              (rows.length === 1 ? "" : "s") +
            "</span>" +
          "</div>" +

          '<div class="card-body">' +

            (
              rows.length

                ? '<div class="payslip-cards">' +
                    rows.map(card).join("") +
                  "</div>"

                : RG.emptyState(
                    "No salary slips available yet",
                    "Once HR processes your first salary it will appear here.",
                    "",
                    "money"
                  )
            ) +

          "</div>" +

        "</div>";

      var open = RG.param("open");

      if (open && cache[open]) {
        openPayslip(cache[open]);
      }
    }

    function load() {

      ctx.page.innerHTML =
        RG.skeletonCards(3);

      API.get("/salaries/me")
        .then(render)
        .catch(function (err) {

          ctx.page.innerHTML =
            '<div class="card">' +
              RG.errorState(err.message, "retry") +
            "</div>";

          var r =
            document.getElementById("retry");

          if (r) {
            r.addEventListener(
              "click",
              load
            );
          }
        });
    }

    RG.on(
      document,
      "[data-view]",
      "click",
      function (e, b) {
        openPayslip(
          cache[b.dataset.view]
        );
      }
    );

    RG.on(
      document,
      "[data-request]",
      "click",
      function (e, b) {

        var salary =
          cache[b.dataset.request];

        if (salary) {
          openDownloadRequest(
            salary,
            load
          );
        }
      }
    );

    RG.on(
      document,
      "[data-pdf]",
      "click",
      function (e, b) {

        RG.setBusy(
          b,
          true,
          "…"
        );

        API.download(
          "/salaries/" +
          b.dataset.pdf +
          "/payslip/download"
        )
        .then(function () {

          RG.setBusy(
            b,
            false
          );

          RG.toastOk(
            "Payslip downloaded."
          );
        })
        .catch(function (err) {

          RG.setBusy(
            b,
            false
          );

          var salary =
            cache[b.dataset.pdf];

          if (
            err.status === 403 &&
            salary &&
            salary.is_intern
          ) {

            openDownloadRequest(
              salary,
              load
            );

            return;
          }

          RG.toastErr(err);
        });
      }
    );

    load();
  }

  /* =========================================================
     HR PAYROLL
  ========================================================= */

  function hrView() {

    var ctx = RG.boot({
      scope: "hr",
      active: "salary",
      title: "Salary",
      subtitle: "Payroll & payslips"
    });

    if (!ctx) return;

    var now = new Date();

    var state = {
      page: 1,
      page_size: 15,
      status: "",
      department_id: "",
      employee_id: RG.param("employee_id") || "",
      period_year: now.getFullYear(),
      period_month: ""
    };

    var cache = {};

    /* ---------------------------------------------------------
       Employee state
    --------------------------------------------------------- */

    var employees = [];
    var employeesLoaded = false;
    var employeesLoading = null;

    /* ---------------------------------------------------------
       Page
    --------------------------------------------------------- */

    ctx.page.innerHTML =

      '<div class="page-head">' +

        "<div>" +
          "<h1>Payroll</h1>" +
          '<p class="sub">' +
            "Build a salary record, publish the payslip, then mark it credited." +
          "</p>" +
        "</div>" +

        '<div class="page-actions">' +
          '<button class="btn" data-autogen title="Create this month\'s salary records from each employee\'s previous month">' +
            "Generate this month" +
          "</button>" +
          '<button class="btn btn-brand" data-new>' +
            RG.icon("plus", 16) +
            " New salary record" +
          "</button>" +
        "</div>" +

      "</div>" +

      '<div id="kpis" class="kpi-strip">' +

        '<div class="kpi">' +
          '<div class="skeleton sk-line"></div>' +
        "</div>" +

        '<div class="kpi">' +
          '<div class="skeleton sk-line"></div>' +
        "</div>" +

        '<div class="kpi">' +
          '<div class="skeleton sk-line"></div>' +
        "</div>" +

        '<div class="kpi">' +
          '<div class="skeleton sk-line"></div>' +
        "</div>" +

      "</div>" +

      '<div class="card">' +

        '<div class="toolbar">' +

          '<div class="filters" style="margin-left:0">' +

            '<select id="f-dept">' +
              '<option value="">All departments</option>' +
            "</select>" +

            '<select id="f-status">' +
              '<option value="">Any status</option>' +
              '<option value="Pending">Pending</option>' +
              '<option value="Processing">Processing</option>' +
              '<option value="Credited">Credited</option>' +
            "</select>" +

            '<select id="f-month">' +
              '<option value="">Any month</option>' +

              RG.MONTHS.map(function (m, i) {
                return '<option value="' +
                  (i + 1) +
                  '">' +
                  m +
                  "</option>";
              }).join("") +

            "</select>" +

            '<select id="f-year">' +

              [
                now.getFullYear() + 1,
                now.getFullYear(),
                now.getFullYear() - 1,
                now.getFullYear() - 2
              ]
              .map(function (y) {

                return '<option value="' +
                  y +
                  '"' +
                  (
                    y === now.getFullYear()
                      ? " selected"
                      : ""
                  ) +
                  ">" +
                  y +
                  "</option>";
              })
              .join("") +

            "</select>" +

          "</div>" +

        "</div>" +

        '<div id="host">' +
          RG.skeletonRows(8) +
        "</div>" +

        '<div class="pager" id="pager"></div>' +

      "</div>";

    var host =
      document.getElementById("host");

    /* =========================================================
       FIXED EMPLOYEE LOADING
    ========================================================= */

    function loadEmployees() {

      if (employeesLoaded) {
        return Promise.resolve(
          employees
        );
      }

      if (employeesLoading) {
        return employeesLoading;
      }

      employeesLoading =
        API.get(
          "/employees",
          {
            page: 1,
            page_size: 100
          }
        )
        .then(function (data) {

          employees =
            Array.isArray(data)
              ? data
              : (data.items || []);

          employeesLoaded = true;
          employeesLoading = null;

          /* Update employee filter if it exists */
          var filter =
            document.getElementById("f-emp");

          if (filter) {

            filter.innerHTML =
              '<option value="">All employees</option>' +
              RG.optionList(
                employees,
                "id",
                "full_name",
                state.employee_id
              );
          }

          return employees;
        })
        .catch(function (err) {

          employeesLoading = null;
          employeesLoaded = false;

          throw err;
        });

      return employeesLoading;
    }

    /* Load employees immediately */
    loadEmployees().catch(function () {
      /* New salary button will show the actual error */
    });

    /* =========================================================
       Departments
    ========================================================= */

    API.get(
      "/departments",
      {
        active_only: true
      }
    )
    .then(function (rows) {

      var departments =
        Array.isArray(rows)
          ? rows
          : ((rows && rows.items) || []);

      departments =
        departments.filter(function (d) {
          return d &&
            d.is_active !== false;
        });

      document.getElementById(
        "f-dept"
      ).innerHTML =
        '<option value="">All departments</option>' +
        RG.optionList(
          departments,
          "id",
          "name",
          state.department_id
        );
    })
    .catch(function () {
      /* Filter degrades gracefully */
    });

    /* =========================================================
       KPI
    ========================================================= */

    API.get("/dashboard/hr")
      .then(function (data) {

        var k = data.kpis;

        document.getElementById(
          "kpis"
        ).innerHTML =

          '<div class="kpi accent">' +
            '<div class="kpi-label">Payroll this period</div>' +
            '<div class="kpi-value">' +
              RG.fmt.money(
                k.monthly_payroll
              ) +
            "</div>" +
            '<div class="kpi-foot">' +
              "net pay across records" +
            "</div>" +
          "</div>" +

          '<div class="kpi">' +
            '<div class="kpi-label">Credited</div>' +
            '<div class="kpi-value">' +
              k.salary_credited +
            "</div>" +
            '<div class="kpi-foot up">' +
              "paid out" +
            "</div>" +
          "</div>" +

          '<div class="kpi">' +
            '<div class="kpi-label">Processing</div>' +
            '<div class="kpi-value">' +
              k.salary_processing +
            "</div>" +
            '<div class="kpi-foot">' +
              "in progress" +
            "</div>" +
          "</div>" +

          '<div class="kpi">' +
            '<div class="kpi-label">Pending</div>' +
            '<div class="kpi-value">' +
              k.salary_pending +
            "</div>" +
            '<div class="kpi-foot warn">' +
              "awaiting action" +
            "</div>" +
          "</div>";

      })
      .catch(function () {

        document.getElementById(
          "kpis"
        ).innerHTML = "";
      });

    /* =========================================================
       Salary table row
    ========================================================= */

    function row(s) {

      cache[s.id] = s;

      var actions =

        '<button class="btn btn-sm" data-view="' +
          s.id +
          '">' +
          "Payslip" +
        "</button>" +

        '<button class="btn btn-sm" data-edit="' +
          s.id +
          '">' +
          "Edit" +
        "</button>";

      if (s.status !== "Credited") {

        actions +=
          '<button class="btn btn-sm btn-ok" data-credit="' +
          s.id +
          '">' +
          "Mark credited" +
          "</button>";
      }

      actions +=
        '<button class="btn btn-sm btn-ghost" data-slip="' +
        s.id +
        '">' +
        "Upload slip" +
        "</button>";

      if (s.is_intern) {

        actions +=
          '<button class="btn btn-sm ' +
          (
            s.intern_download_allowed
              ? "btn-ok"
              : "btn-ghost"
          ) +
          '" data-perm="' +
          s.id +
          '" title="' +

          (
            s.intern_download_allowed
              ? "Intern can download this payslip — click to withdraw"
              : "Intern can only view this payslip — click to allow downloading"
          ) +

          '">' +

          (
            s.intern_download_allowed
              ? "Download: on"
              : "Download: off"
          ) +

          "</button>";
      }

      return "<tr>" +

        '<td data-label="Employee">' +

          '<div class="identity">' +

            RG.avatar(
              {
                full_name: s.employee_name,
                id: s.employee_id
              },
              "sm"
            ) +

            "<div>" +

              '<div class="name truncate">' +
                RG.esc(s.employee_name) +
              "</div>" +

              '<div class="meta">' +
                RG.esc(s.employee_code) +
                " · " +
                RG.esc(s.department || "") +
              "</div>" +

            "</div>" +

          "</div>" +

        "</td>" +

        '<td data-label="Pay period" class="nowrap">' +
          RG.esc(s.period_label) +
          (s.auto_generated ? ' <span class="chip" title="Created automatically from the previous month">Auto</span>' : "") +
        "</td>" +

        '<td data-label="Days" class="num">' +
          s.working_days +
        "</td>" +

        '<td data-label="Earnings" class="num">' +
          RG.fmt.money(s.total_earnings) +
        "</td>" +

        '<td data-label="Deductions" class="num">' +
          RG.fmt.money(s.total_deductions) +
        "</td>" +

        '<td data-label="Net pay" class="num strong">' +
          RG.fmt.money(s.net_pay) +
        "</td>" +

        '<td data-label="Status">' +
          RG.badge(s.status) +

          (
            s.has_payslip
              ? ' <span class="chip">PDF</span>'
              : ""
          ) +

          (
            s.is_intern
              ? ' <span class="chip" title="Intern payslip download permission">' +
                  (
                    s.intern_download_allowed
                      ? "DL allowed"
                      : "View only"
                  ) +
                "</span>"
              : ""
          ) +

        "</td>" +

        '<td data-label="Credited" class="nowrap">' +
          (
            s.credit_date
              ? RG.fmt.date(s.credit_date)
              : "—"
          ) +
        "</td>" +

        '<td class="actions" data-label="Actions">' +
          actions +
        "</td>" +

      "</tr>";
    }

    /* =========================================================
       Load salary records
    ========================================================= */

    function load() {

      API.get(
        "/salaries",
        state
      )
      .then(function (data) {

        var items =
          data.items || [];

        if (!items.length) {

          host.innerHTML =
            RG.emptyState(
              "No salary records",
              "Create one for this pay period.",
              '<button class="btn btn-sm btn-brand" data-new>' +
                "New salary record" +
              "</button>",
              "money"
            );

          document.getElementById(
            "pager"
          ).innerHTML = "";

          return;
        }

        host.innerHTML =
          '<div class="table-scroll">' +

            "<table class=\"data\">" +

              "<thead>" +

                "<tr>" +
                  "<th>Employee</th>" +
                  "<th>Pay period</th>" +
                  "<th>Days</th>" +
                  "<th>Earnings</th>" +
                  "<th>Deductions</th>" +
                  "<th>Net pay</th>" +
                  "<th>Status</th>" +
                  "<th>Credited</th>" +
                  "<th></th>" +
                "</tr>" +

              "</thead>" +

              "<tbody>" +
                items.map(row).join("") +
              "</tbody>" +

            "</table>" +

          "</div>";

        RG.hydratePhotos(host);

        RG.renderPager(
          document.getElementById("pager"),
          data.meta,
          function (p) {
            state.page = p;
            load();
          }
        );

      })
      .catch(function (err) {

        host.innerHTML =
          RG.errorState(
            err.message,
            "retry"
          );

        var r =
          document.getElementById("retry");

        if (r) {
          r.addEventListener(
            "click",
            load
          );
        }
      });
    }

    /* =========================================================
       Salary component editor
    ========================================================= */

    function componentRow(
      type,
      component
    ) {

      var presets =
        type === "earning"
          ? EARNING_PRESETS
          : DEDUCTION_PRESETS;

      var name =
        component
          ? component.name
          : "";

      return '<div class="component-row" data-type="' +
        type +
        '">' +

        '<div class="field">' +

          '<input type="text" ' +
            'class="c-name" ' +
            'list="preset-' +
              type +
            '" ' +
            'placeholder="' +

            (
              type === "earning"
                ? "Earning name"
                : "Deduction name"
            ) +

            '" value="' +
            RG.esc(name) +
          '">' +

        "</div>" +

        '<div class="field">' +

          '<input type="number" ' +
            'class="c-amount" ' +
            'min="0" ' +
            'step="0.01" ' +
            'placeholder="0.00" ' +
            'value="' +
              (
                component
                  ? component.amount
                  : ""
              ) +
          '">' +

        "</div>" +

        '<button type="button" ' +
          'class="btn btn-icon btn-ghost rm" ' +
          'title="Remove">' +
          RG.icon("x", 15) +
        "</button>" +

        '<datalist id="preset-' +
          type +
        '">' +

          presets.map(function (p) {
            return '<option value="' +
              p +
            '"></option>';
          }).join("") +

        "</datalist>" +

      "</div>";
    }

    /* =========================================================
       Salary form
    ========================================================= */

    function salaryForm(existing) {

      var s =
        existing || {};

      var earnings =
        (
          s.earnings &&
          s.earnings.length
        )
          ? s.earnings
          : [
              {
                name: "Basic",
                amount: ""
              },
              {
                name: "Incentive",
                amount: ""
              }
            ];

      var deductions =
        (
          s.deductions &&
          s.deductions.length
        )
          ? s.deductions
          : [
              {
                name: "PF",
                amount: 0
              }
            ];

      return '<form id="sal-form">' +

        '<div class="form-grid">' +

          /* EMPLOYEE */
          '<div class="field">' +

            '<label for="s-emp">' +
              "Employee " +
              '<span class="req">*</span>' +
            "</label>" +

            '<select id="s-emp"' +
              (
                existing
                  ? " disabled"
                  : ""
              ) +
              " required>" +

              '<option value="">' +
                "Select employee" +
              "</option>" +

              employees.map(function (employee) {

                var label =
                  employee.full_name ||
                  "Unnamed employee";

                var code =
                  employee.employee_code ||
                  employee.employee_id ||
                  "";

                var department =
                  employee.department ||
                  employee.department_name ||
                  "";

                if (code) {
                  label +=
                    " — " +
                    code;
                }

                if (department) {
                  label +=
                    " — " +
                    department;
                }

                return '<option value="' +
                  RG.esc(employee.id) +
                  '"' +

                  (
                    String(
                      s.employee_id || ""
                    ) ===
                    String(employee.id)
                      ? " selected"
                      : ""
                  ) +

                  ">" +
                  RG.esc(label) +
                  "</option>";
              }).join("") +

            "</select>" +

          "</div>" +

          /* WORKED DAYS */
          '<div class="field">' +

            '<label for="s-days">' +
              "Worked days " +
              '<span class="req">*</span>' +
            "</label>" +

            '<input id="s-days" ' +
              'type="number" ' +
              'min="0" ' +
              'max="31" ' +
              'value="' +
                (
                  s.working_days ||
                  30
                ) +
              '" required>' +

          "</div>" +

          /* PAY MONTH */
          '<div class="field">' +

            '<label for="s-month">' +
              "Pay month " +
              '<span class="req">*</span>' +
            "</label>" +

            '<select id="s-month"' +
              (
                existing
                  ? " disabled"
                  : ""
              ) +
              ">" +

              RG.MONTHS.map(
                function (m, i) {

                  var selected =
                    (
                      s.period_month ||
                      (now.getMonth() + 1)
                    ) ===
                    i + 1;

                  return '<option value="' +
                    (i + 1) +
                    '"' +
                    (
                      selected
                        ? " selected"
                        : ""
                    ) +
                    ">" +
                    m +
                    "</option>";
                }
              ).join("") +

            "</select>" +

          "</div>" +

          /* PAY YEAR */
          '<div class="field">' +

            '<label for="s-year">' +
              "Pay year " +
              '<span class="req">*</span>' +
            "</label>" +

            '<input id="s-year" ' +
              'type="number" ' +
              'min="2000" ' +
              'max="2100" ' +
              'value="' +
                (
                  s.period_year ||
                  now.getFullYear()
                ) +
              '"' +
              (
                existing
                  ? " disabled"
                  : ""
              ) +
              ">" +

          "</div>" +

          /* STATUS */
          '<div class="field">' +

            '<label for="s-status">' +
              "Status" +
            "</label>" +

            '<select id="s-status">' +

              [
                "Pending",
                "Processing",
                "Credited"
              ].map(function (st) {

                return '<option value="' +
                  st +
                  '"' +

                  (
                    (
                      s.status ||
                      "Pending"
                    ) === st
                      ? " selected"
                      : ""
                  ) +

                  ">" +
                  st +
                  "</option>";
              }).join("") +

            "</select>" +

          "</div>" +

          /* CREDIT DATE */
          '<div class="field">' +

            '<label for="s-credit">' +
              "Credit date" +
            "</label>" +

            '<input id="s-credit" ' +
              'type="date" ' +
              'value="' +
                (
                  s.credit_date ||
                  ""
                ) +
              '">' +

          "</div>" +

          /* REMARKS */
          '<div class="field full">' +

            '<label for="s-remarks">' +
              "Remarks" +
            "</label>" +

            '<input id="s-remarks" ' +
              'type="text" ' +
              'value="' +
                RG.esc(
                  s.remarks || ""
                ) +
              '">' +

          "</div>" +

        "</div>" +

        '<div class="grid grid-2 mt-4">' +

          /* EARNINGS */
          '<div>' +

            '<div class="form-section">' +

              "<h4>Earnings</h4>" +

              '<div id="earnings">' +

                earnings.map(
                  function (c) {
                    return componentRow(
                      "earning",
                      c
                    );
                  }
                ).join("") +

              "</div>" +

              '<button type="button" ' +
                'class="btn btn-sm mt-2" ' +
                'data-add="earning">' +

                RG.icon(
                  "plus",
                  14
                ) +

                " Add earning" +

              "</button>" +

            "</div>" +

          "</div>" +

          /* DEDUCTIONS */
          '<div>' +

            '<div class="form-section">' +

              "<h4>Deductions</h4>" +

              '<div id="deductions">' +

                deductions.map(
                  function (c) {
                    return componentRow(
                      "deduction",
                      c
                    );
                  }
                ).join("") +

              "</div>" +

              '<button type="button" ' +
                'class="btn btn-sm mt-2" ' +
                'data-add="deduction">' +

                RG.icon(
                  "plus",
                  14
                ) +

                " Add deduction" +

              "</button>" +

            "</div>" +

          "</div>" +

        "</div>" +

        '<div class="totals-box mt-4" id="totals"></div>' +

      "</form>";
    }

    /* =========================================================
       Collect components
    ========================================================= */

    function collect(modal) {

      var components = [];

      modal.body
        .querySelectorAll(
          ".component-row"
        )
        .forEach(function (rowEl) {

          var name =
            rowEl.querySelector(
              ".c-name"
            ).value.trim();

          var amount =
            rowEl.querySelector(
              ".c-amount"
            ).value;

          if (!name) return;

          components.push({
            component_type:
              rowEl.dataset.type,

            name: name,

            amount:
              Number(
                amount || 0
              )
          });
        });

      return components;
    }

    /* =========================================================
       Totals
    ========================================================= */

    function refreshTotals(modal) {

      var components =
        collect(modal);

      var earn = 0;
      var deduct = 0;

      components.forEach(
        function (c) {

          if (
            c.component_type ===
            "earning"
          ) {
            earn += c.amount;
          } else {
            deduct += c.amount;
          }
        }
      );

      modal.body.querySelector(
        "#totals"
      ).innerHTML =

        '<div class="line">' +
          "<span>Total earnings</span>" +
          "<b>" +
            RG.fmt.money(
              earn,
              true
            ) +
          "</b>" +
        "</div>" +

        '<div class="line">' +
          "<span>Total deductions</span>" +
          "<b>" +
            RG.fmt.money(
              deduct,
              true
            ) +
          "</b>" +
        "</div>" +

        '<div class="line net">' +
          "<span>Net pay</span>" +
          "<b>" +
            RG.fmt.money(
              earn - deduct,
              true
            ) +
          "</b>" +
        "</div>" +

        '<div class="words">' +
          "Computed on the server when saved — " +
          "the payslip words follow the stored net pay." +
        "</div>";
    }

    /* =========================================================
       OPEN SALARY MODAL
    ========================================================= */

    function openSalaryModal(existing) {

      /* Existing salary can open directly.
         New salary requires employees to be loaded first. */

      var modal =
        RG.openModal({

          title:
            existing
              ? "Edit salary · " +
                existing.period_label
              : "New salary record",

          size: "lg",

          body:
            salaryForm(existing),

          footer:
            '<button class="btn" data-close>' +
              "Cancel" +
            "</button>" +

            '<button class="btn btn-brand" data-save>' +
              (
                existing
                  ? "Save changes"
                  : "Create record"
              ) +
            "</button>",

          onOpen:
            function (m) {
              refreshTotals(m);
            }
        });

      modal.body.addEventListener(
        "input",
        function () {
          refreshTotals(modal);
        }
      );

      modal.body.addEventListener(
        "click",
        function (e) {

          var add =
            e.target.closest(
              "[data-add]"
            );

          if (add) {

            var type =
              add.dataset.add;

            var container =
              modal.body.querySelector(
                type === "earning"
                  ? "#earnings"
                  : "#deductions"
              );

            container.insertAdjacentHTML(
              "beforeend",
              componentRow(
                type,
                null
              )
            );

            refreshTotals(modal);

            return;
          }

          var remove =
            e.target.closest(".rm");

          if (remove) {

            remove
              .closest(
                ".component-row"
              )
              .remove();

            refreshTotals(modal);
          }
        }
      );

      modal.foot
        .querySelector(
          "[data-save]"
        )
        .addEventListener(
          "click",
          function () {

            var form =
              modal.body.querySelector(
                "#sal-form"
              );

            if (
              !form.reportValidity()
            ) {
              return;
            }

            var components =
              collect(modal);

            if (
              !components.some(
                function (c) {

                  return (
                    c.component_type ===
                      "earning" &&
                    c.amount > 0
                  );
                }
              )
            ) {

              RG.toast(
                "Add at least one earning with an amount.",
                "bad",
                "Nothing to pay"
              );

              return;
            }

            var button =
              modal.foot.querySelector(
                "[data-save]"
              );

            RG.setBusy(
              button,
              true,
              "Saving…"
            );

            var common = {

              working_days:
                Number(
                  modal.body.querySelector(
                    "#s-days"
                  ).value
                ),

              status:
                modal.body.querySelector(
                  "#s-status"
                ).value,

              credit_date:
                modal.body.querySelector(
                  "#s-credit"
                ).value || null,

              remarks:
                modal.body.querySelector(
                  "#s-remarks"
                ).value.trim() || null,

              components:
                components
            };

            var request;

            if (existing) {

              request =
                API.put(
                  "/salaries/" +
                  existing.id,
                  common
                );

            } else {

              common.employee_id =
                Number(
                  modal.body.querySelector(
                    "#s-emp"
                  ).value
                );

              common.period_month =
                Number(
                  modal.body.querySelector(
                    "#s-month"
                  ).value
                );

              common.period_year =
                Number(
                  modal.body.querySelector(
                    "#s-year"
                  ).value
                );

              request =
                API.post(
                  "/salaries",
                  common
                );
            }

            request
              .then(function () {

                modal.close();

                RG.toastOk(
                  existing
                    ? "Salary record updated."
                    : "Salary record created."
                );

                load();
              })
              .catch(function (err) {

                RG.setBusy(
                  button,
                  false
                );

                /* One slip per employee and month: open the existing
                   slip for editing instead of creating a second one. */
                if (
                  !existing &&
                  err.status === 409 &&
                  err.body &&
                  err.body.code === "SALARY_EXISTS"
                ) {
                  modal.close();
                  RG.toast(
                    "A salary slip for " + (err.body.context.period_label || "that month") +
                      " already exists \u2014 opening it for editing.",
                    "info",
                    "Already created"
                  );
                  API.get("/salaries/" + err.body.context.salary_id)
                    .then(openSalaryModal)
                    .catch(RG.toastErr);
                  return;
                }

                RG.toastErr(err);
              });
          }
        );
    }

    /* =========================================================
       CREDIT SALARY
    ========================================================= */

    function creditModal(salary) {

      var modal =
        RG.openModal({

          title:
            "Mark salary credited",

          size: "sm",

          body:
            "<p>This will publish " +
            RG.esc(
              salary.employee_name
            ) +
            "’s " +
            RG.esc(
              salary.period_label
            ) +
            " payslip and notify them.</p>" +

            '<div class="field">' +

              '<label for="cd">' +
                "Credit date" +
              "</label>" +

              '<input id="cd" type="date" value="' +
                (
                  salary.credit_date ||
                  new Date()
                    .toISOString()
                    .slice(0, 10)
                ) +
              '">' +

            "</div>" +

            '<label class="switch mt-4">' +

              '<input type="checkbox" id="attach" checked>' +

              '<span class="track"></span>' +

              '<span class="switch-text">' +

                "<b>" +
                  "Attach the payslip PDF to the email" +
                "</b>" +

                "<span>" +
                  "Generates it first if it doesn’t exist yet." +
                "</span>" +

              "</span>" +

            "</label>" +

            '<p class="small muted mt-4 mb-0">' +
              RG.icon("shield", 13) +
              " Running this twice won’t send a second email " +
              "or create a duplicate notification." +
            "</p>",

          footer:
            '<button class="btn" data-close>' +
              "Cancel" +
            "</button>" +

            '<button class="btn btn-ok" data-go>' +
              "Mark credited" +
            "</button>"
        });

      modal.foot
        .querySelector(
          "[data-go]"
        )
        .addEventListener(
          "click",
          function () {

            var button =
              modal.foot.querySelector(
                "[data-go]"
              );

            RG.setBusy(
              button,
              true,
              "Publishing…"
            );

            API.post(
              "/salaries/" +
              salary.id +
              "/credit",
              {
                credit_date:
                  modal.body.querySelector(
                    "#cd"
                  ).value || null,

                attach_payslip:
                  modal.body.querySelector(
                    "#attach"
                  ).checked
              }
            )
            .then(function () {

              modal.close();

              RG.toastOk(
                "Salary credited — payslip published, notification and email sent."
              );

              load();
            })
            .catch(function (err) {

              RG.setBusy(
                button,
                false
              );

              RG.toastErr(err);
            });
          }
        );
    }

    /* =========================================================
       PAYSLIP GENERATION / UPLOAD
    ========================================================= */

    function slipModal(salary) {

      var modal =
        RG.openModal({

          title:
            "Payslip · " +
            salary.period_label,

          size: "sm",

          body:
            '<p class="small muted">' +
              "Generate the Rocket Genie payslip from the salary data, " +
              "or upload a signed PDF of your own." +
            "</p>" +

            '<button class="btn btn-block btn-primary" data-generate>' +
              RG.icon("doc", 15) +
              " Generate payslip PDF" +
            "</button>" +

            '<div class="divider"></div>' +

            '<div class="drop" id="drop">' +

              '<div class="drop-icon">' +
                RG.icon("upload", 20) +
              "</div>" +

              "<b>Upload a PDF payslip</b>" +

              "<span>PDF only · up to 5 MB</span>" +

              '<input type="file" id="file" accept=".pdf">' +

            "</div>" +

            '<ul class="file-list" id="chosen"></ul>',

          footer:
            '<button class="btn" data-close>' +
              "Close" +
            "</button>" +

            '<button class="btn btn-brand" data-send disabled>' +
              "Upload" +
            "</button>"
        });

      var input =
        modal.body.querySelector(
          "#file"
        );

      var send =
        modal.foot.querySelector(
          "[data-send]"
        );

      modal.body
        .querySelector("#drop")
        .addEventListener(
          "click",
          function () {
            input.click();
          }
        );

      input.addEventListener(
        "change",
        function () {

          var file =
            input.files[0];

          if (!file) return;

          modal.body.querySelector(
            "#chosen"
          ).innerHTML =

            '<li class="file-item">' +

              '<span class="f-thumb">PDF</span>' +

              '<div class="f-meta">' +

                '<b class="truncate">' +
                  RG.esc(file.name) +
                "</b>" +

                "<span>" +
                  RG.fmt.bytes(
                    file.size
                  ) +
                "</span>" +

              "</div>" +

            "</li>";

          send.disabled = false;
        }
      );

      modal.body
        .querySelector(
          "[data-generate]"
        )
        .addEventListener(
          "click",
          function () {

            var button =
              modal.body.querySelector(
                "[data-generate]"
              );

            RG.setBusy(
              button,
              true,
              "Generating…"
            );

            API.post(
              "/salaries/" +
              salary.id +
              "/payslip/generate",
              {}
            )
            .then(function () {

              modal.close();

              RG.toastOk(
                "Payslip PDF generated."
              );

              load();
            })
            .catch(function (err) {

              RG.setBusy(
                button,
                false
              );

              RG.toastErr(err);
            });
          }
        );

      send.addEventListener(
        "click",
        function () {

          var form =
            new FormData();

          form.append(
            "file",
            input.files[0]
          );

          RG.setBusy(
            send,
            true,
            "Uploading…"
          );

          API.upload(
            "/salaries/" +
            salary.id +
            "/payslip/upload",
            form
          )
          .then(function () {

            modal.close();

            RG.toastOk(
              "Payslip uploaded."
            );

            load();
          })
          .catch(function (err) {

            RG.setBusy(
              send,
              false
            );

            RG.toastErr(err);
          });
        }
      );
    }

    /* =========================================================
       FILTERS
    ========================================================= */

    [
      ["f-dept", "department_id"],
      ["f-status", "status"],
      ["f-month", "period_month"],
      ["f-year", "period_year"]
    ]
    .forEach(function (pair) {

      document.getElementById(
        pair[0]
      ).addEventListener(
        "change",
        function (e) {

          state[pair[1]] =
            e.target.value;

          state.page = 1;

          load();
        }
      );
    });

    /* =========================================================
       NEW SALARY RECORD
       IMPORTANT FIX
    ========================================================= */

    RG.on(
      ctx.page,
      "[data-new]",
      "click",
      function (e, button) {

        /*
          Do NOT open the salary form until employees
          have successfully loaded.
        */

        if (employeesLoaded) {

          openSalaryModal(null);

          return;
        }

        RG.setBusy(
          button,
          true,
          "Loading employees…"
        );

        loadEmployees()
          .then(function () {

            openSalaryModal(null);

          })
          .catch(function (err) {

            RG.toastErr(err);

          })
          .finally(function () {

            RG.setBusy(
              button,
              false
            );

          });
      }
    );

    /* =========================================================
       OTHER ACTIONS
    ========================================================= */

    RG.on(
      ctx.page,
      "[data-view]",
      "click",
      function (e, b) {

        openPayslip(
          cache[
            b.dataset.view
          ]
        );
      }
    );

    RG.on(
      ctx.page,
      "[data-edit]",
      "click",
      function (e, b) {

        openSalaryModal(
          cache[
            b.dataset.edit
          ]
        );
      }
    );

    RG.on(
      ctx.page,
      "[data-credit]",
      "click",
      function (e, b) {

        creditModal(
          cache[
            b.dataset.credit
          ]
        );
      }
    );

    RG.on(
      ctx.page,
      "[data-slip]",
      "click",
      function (e, b) {

        slipModal(
          cache[
            b.dataset.slip
          ]
        );
      }
    );

    RG.on(
      ctx.page,
      "[data-autogen]",
      "click",
      function (e, b) {
        RG.confirmAction({
          title: "Generate this month's salary slips?",
          message: "A salary record is created for every employee you manage who has a previous month and no record for this month yet. Amounts are copied from their previous month; you then edit the payment amounts before crediting.",
          note: "Existing records are never duplicated. This also runs automatically every month.",
          confirmLabel: "Generate"
        }).then(function (ok) {
          if (!ok) return;
          RG.setBusy(b, true, "Generating\u2026");
          API.post("/salaries/auto-generate", {}).then(function (r) {
            RG.setBusy(b, false);
            RG.toastOk(r.created
              ? r.created + " salary record(s) created up to " + r.period + "."
              : "Nothing to create \u2014 every salary up to " + r.period + " already exists.");
            load();
          }).catch(function (err) { RG.setBusy(b, false); RG.toastErr(err); });
        });
      }
    );

    /* =========================================================
       INITIAL LOAD
    ========================================================= */

    load();
  }

  /* =========================================================
     START
  ========================================================= */

  if (RG.mgmtView()) {
    hrView();
  } else {
    employeeView();
  }

})();