/* employees.js - HR employee directory (search, filters, sort, pagination,
   create/edit, activate/deactivate) and the employee detail page. */
// (function () {
//   "use strict";

//   var PAGE = document.body.dataset.page;
//   var STATUSES = ["Active", "Inactive", "On Leave", "Resigned", "Terminated"];
//   var GENDERS = ["Female", "Male", "Other", "Prefer not to say"];
//   var lookups = { departments: [], backgrounds: [], managers: [] };

//   var DESIGNATIONS_BY_DEPARTMENT = {
//     "Teaching": ["Trainer", "Senior Trainer", "Faculty Coordinator", "Curriculum Designer", "Academic Coordinator"],
//     "Marketing": ["Marketing Executive", "Marketing Lead", "Business Development Executive", "Sales Executive", "Sales Manager"],
//     "Digital Marketing": ["Digital Marketing Executive", "SEO Specialist", "Content Strategist", "Social Media Manager", "Digital Marketing Manager"],
//     "Managers": ["Project Manager", "Operations Manager", "Program Manager", "Team Manager"],
//     "HR": ["HR Executive", "HR Manager", "Recruiter", "HR Coordinator"],
//     "Internship": ["Trainee", "Intern", "Project Trainee"],
//     "Senior HR": ["Senior HR Manager", "HR Lead", "Head of People"],
//     "Finance": ["Finance Executive", "Accountant", "Finance Manager", "Senior Accountant"]
//   };

//   function asList(value) {
//     if (Array.isArray(value)) return value;
//     if (value && Array.isArray(value.items)) return value.items;
//     if (value && Array.isArray(value.data)) return value.data;
//     return [];
//   }

//   function loadLookups() {
//     return Promise.all([
//       API.get("/departments", { active_only: true }),
//       API.get("/internship-backgrounds"),
//       API.get("/employees", { page: 1, page_size: 200 })
//     ]).then(function (res) {
//       lookups.departments = asList(res[0]).filter(function (d) { return d && d.is_active !== false; });
//       lookups.backgrounds = asList(res[1]).filter(function (b) { return b && b.is_active !== false; });
//       lookups.managers = asList(res[2]);
//       return lookups;
//     });
//   }

//   function designationOptions(departmentId, selected) {
//     var dept = lookups.departments.filter(function (d) { return String(d.id) === String(departmentId || ""); })[0];
//     var names = dept ? (DESIGNATIONS_BY_DEPARTMENT[dept.name] || []).slice() : [];
//     if (selected && names.indexOf(selected) === -1) names.push(selected);
//     return '<option value="">Select designation</option>' + names.map(function (name) {
//       return '<option value="' + RG.esc(name) + '"' + (String(selected || "") === String(name) ? " selected" : "") + '>' + RG.esc(name) + '</option>';
//     }).join("");
//   }

//   function allDesignations() {
//     var values = [];
//     Object.keys(DESIGNATIONS_BY_DEPARTMENT).forEach(function (dept) {
//       DESIGNATIONS_BY_DEPARTMENT[dept].forEach(function (name) { if (values.indexOf(name) === -1) values.push(name); });
//     });
//     lookups.managers.forEach(function (m) { if (m && m.designation && values.indexOf(m.designation) === -1) values.push(m.designation); });
//     return values.sort();
//   }

//   function internDeptId() {
//     var hit = lookups.departments.filter(function (d) { return /internship/i.test(d.name); })[0];
//     return hit ? hit.id : null;
//   }

//   /* ======================= create / edit form ======================= */
//   function employeeForm(existing) {
//     var e = existing || {};
//     var isEdit = !!existing;
//     function field(label, name, type, value, required, extra) {
//       return '<div class="field"><label for="f-' + name + '">' + label +
//         (required ? ' <span class="req">*</span>' : "") + "</label>" +
//         '<input id="f-' + name + '" name="' + name + '" type="' + type + '" value="' +
//         RG.esc(value === null || value === undefined ? "" : value) + '"' + (required ? " required" : "") +
//         (extra || "") + "></div>";
//     }
//     return '<form id="emp-form" class="form-grid">' +
//       '<div class="form-section full"><h4>Personal information</h4><div class="form-grid">' +
//         field("Full name", "full_name", "text", e.full_name, true) +
//         (isEdit ? field("Work email", "email", "email", e.email, false, " readonly") :
//           field("Work email", "email", "email", "", true)) +
//         field("Phone", "phone", "tel", e.phone) +
//         field("Date of birth", "date_of_birth", "date", e.date_of_birth) +
//         '<div class="field"><label for="f-gender">Gender</label><select id="f-gender" name="gender">' +
//           '<option value="">Not specified</option>' +
//           GENDERS.map(function (g) {
//             return '<option value="' + g + '"' + (e.gender === g ? " selected" : "") + ">" + g + "</option>";
//           }).join("") + "</select></div>" +
//         '<div class="field full"><label for="f-address">Address</label><textarea id="f-address" name="address" rows="2">' +
//           RG.esc(e.address || "") + "</textarea></div>" +
//       "</div></div>" +
//       '<div class="form-section full"><h4>Employment</h4><div class="form-grid">' +
//         (isEdit ? field("Employee ID", "employee_code", "text", e.employee_code, false, " readonly") :
//           '<div class="field"><label for="f-employee_code">Employee ID</label>' +
//           '<input id="f-employee_code" type="text" value="" placeholder="Automatically generated" readonly>' +
//           '<span class="help">Employee ID is generated automatically when the account is created.</span></div>') +
//         '<div class="field"><label for="f-department_id">Department <span class="req">*</span></label>' +
//           '<select id="f-department_id" name="department_id" required>' +
//           '<option value="">Select department</option>' +
//           lookups.departments.map(function (d) {
//             return '<option value="' + RG.esc(d.id) + '"' + (String(e.department_id || "") === String(d.id) ? " selected" : "") + '>' + RG.esc(d.name) + '</option>';
//           }).join("") + '</select></div>' +
//         '<div class="field"><label for="f-designation">Designation <span class="req">*</span></label>' +
//           '<select id="f-designation" name="designation" required>' + designationOptions(e.department_id, e.designation) + '</select></div>' +
//         '<div class="field" id="bg-field"><label for="f-internship_background_id">Internship background</label>' +
//           '<select id="f-internship_background_id" name="internship_background_id">' +
//           '<option value="">Select a background</option>' +
//           RG.optionList(lookups.backgrounds, "id", "name", e.internship_background_id) + "</select>" +
//           '<span class="help">Required when the department is Internship.</span></div>' +
//         field("Joining date", "joining_date", "date", e.joining_date, true) +
//         '<div class="field"><label for="f-employment_status">Employment status</label>' +
//           '<select id="f-employment_status" name="employment_status">' +
//           STATUSES.map(function (s) {
//             return '<option value="' + s + '"' + ((e.employment_status || "Active") === s ? " selected" : "") + ">" + s + "</option>";
//           }).join("") + "</select></div>" +
//         '<div class="field"><label for="f-reporting_manager_id">Reporting manager</label>' +
//           '<select id="f-reporting_manager_id" name="reporting_manager_id"><option value="">None</option>' +
//           lookups.managers.filter(function (m) { return m.id !== e.id && /^(HR|Senior HR)$/i.test(m.department || ""); }).map(function (m) {
//             return '<option value="' + RG.esc(m.id) + '"' + (String(e.reporting_manager_id || "") === String(m.id) ? " selected" : "") + '>HR' + (m.full_name ? ' - ' + RG.esc(m.full_name) : '') + '</option>';
//           }).join("") + '</select></div>' +
//       "</div></div>" +
//       '<div class="form-section full"><h4>Emergency contact</h4><div class="form-grid">' +
//         field("Contact name", "emergency_contact_name", "text", e.emergency_contact_name) +
//         field("Contact phone", "emergency_contact_phone", "tel", e.emergency_contact_phone) +
//         field("Relationship", "emergency_contact_relation", "text", e.emergency_contact_relation) +
//       "</div></div>" +
//       "</form>";
//   }

//   function readForm(form) {
//     var data = {};
//     new FormData(form).forEach(function (value, key) {
//       data[key] = typeof value === "string" ? value.trim() : value;
//     });
//     ["date_of_birth", "phone", "gender", "address", "emergency_contact_name",
//       "emergency_contact_phone", "emergency_contact_relation", "employee_code"].forEach(function (k) {
//       if (data[k] === "") data[k] = null;
//     });
//     data.department_id = data.department_id ? Number(data.department_id) : null;
//     data.internship_background_id = data.internship_background_id ? Number(data.internship_background_id) : null;
//     data.reporting_manager_id = data.reporting_manager_id ? Number(data.reporting_manager_id) : null;
//     return data;
//   }

//   function wireInternToggle(root) {
//     var dept = root.querySelector("#f-department_id");
//     var bgField = root.querySelector("#bg-field");
//     function sync() {
//       var isIntern = Number(dept.value) === internDeptId();
//       bgField.style.display = isIntern ? "" : "none";
//       bgField.querySelector("select").required = isIntern;
//     }
//     dept.addEventListener("change", sync);
//     sync();
//   }

//   function createEmployeeModal(existing, onSaved) {
//     var modal = RG.openModal({
//       title: existing ? "Edit " + existing.full_name : "Add employee",
//       size: "lg",
//       body: employeeForm(existing),
//       footer: '<button class="btn" data-close>Cancel</button>' +
//         '<button class="btn btn-brand" data-save>' + (existing ? "Save changes" : "Create employee &amp; account") + "</button>",
//       onOpen: function (m) { wireInternToggle(m.body); }
//     });

//     var departmentSelect = modal.body.querySelector("#f-department_id");
//     var designationSelect = modal.body.querySelector("#f-designation");
//     if (departmentSelect && designationSelect) {
//       departmentSelect.addEventListener("change", function () {
//         designationSelect.innerHTML = designationOptions(departmentSelect.value, "");
//       });
//     }

//     modal.foot.querySelector("[data-save]").addEventListener("click", function () {
//       var form = modal.body.querySelector("#emp-form");
//       if (!form.reportValidity()) return;
//       var payload = readForm(form);
//       var button = modal.foot.querySelector("[data-save]");
//       RG.setBusy(button, true, "Saving\u2026");

//       var request;
//       if (existing) {
//         delete payload.email;
//         delete payload.employee_code;
//         request = API.put("/employees/" + existing.id, payload);
//       } else {
//         payload.send_account_email = true;
//         request = API.post("/employees", payload);
//       }
//       request.then(function (res) {
//         modal.close();
//         RG.toastOk(existing ? "Employee updated." : "Employee created with a portal account.");
//         if (!existing && res && res.initial_password) {
//           RG.openModal({
//             title: "Account created", size: "sm",
//             body: "<p>Share these sign-in details with " + RG.esc(payload.full_name) + ":</p>" +
//               '<div class="totals-box"><div class="line"><span>Email</span><b>' + RG.esc(payload.email) + "</b></div>" +
//               '<div class="line"><span>Employee ID</span><b>' + RG.esc((res.employee && res.employee.employee_code) || "") + "</b></div>" +
//               '<div class="line"><span>Temporary password</span><b>' + RG.esc(res.initial_password) + "</b></div></div>" +
//               '<p class="small muted mt-4 mb-0">They\u2019ll be asked to change it at first sign-in.</p>',
//             footer: '<button class="btn btn-primary" data-close>Got it</button>'
//           });
//         }
//         if (onSaved) onSaved();
//       }).catch(function (err) {
//         RG.setBusy(button, false);
//         RG.toastErr(err);
//       });
//     });
//   }

//   function openEmployeeModal(existing, onSaved) {
//     loadLookups().then(function () { createEmployeeModal(existing, onSaved); })
//       .catch(function (err) { RG.toastErr(err); });
//   }

//   /* ======================= list page ======================= */
//   function listPage() {
//     var ctx = RG.boot({ scope: "hr", active: "employees", title: "Employees", subtitle: "Directory & accounts" });
//     if (!ctx) return;

//     var state = { page: 1, page_size: 10, search: "", department_id: "", employment_status: "",
//       employee_type: "", internship_background_id: "",
//       designation: "", joined_from: "", document_status: "", salary_status: "",
//       sort_by: "full_name", sort_dir: "asc" };

//     ctx.page.innerHTML =
//       '<div class="page-head"><div><h1>Employees</h1><p class="sub">Every account, document state and salary state in one table.</p></div>' +
//         '<div class="page-actions"><button class="btn btn-brand" data-new>' + RG.icon("plus", 16) + " Add employee</button></div></div>" +
//       '<div class="card"><div class="toolbar">' +
//         '<div class="search">' + RG.icon("search", 16) +
//           '<input id="q" type="text" placeholder="Search name, employee ID or email" aria-label="Search employees"></div>' +
//         '<div class="filters">' +
//           '<select id="f-dept" aria-label="Department"><option value="">All departments</option></select>' +
//           '<select id="f-status" aria-label="Status"><option value="">Any status</option>' +
//             STATUSES.map(function (s) { return '<option value="' + s + '">' + s + "</option>"; }).join("") + "</select>" +
//           '<select id="f-docs" aria-label="Document status"><option value="">Any documents</option>' +
//             '<option value="complete">Documents complete</option><option value="incomplete">Documents incomplete</option></select>' +
//           '<select id="f-salary" aria-label="Salary status"><option value="">Any salary</option>' +
//             '<option value="Credited">Salary credited</option><option value="Pending">Salary pending</option>' +
//             '<option value="Processing">Salary processing</option><option value="None">No salary record</option></select>' +
//           '<select id="f-type" aria-label="Employee type"><option value="">All employee types</option>' +
//             '<option value="Regular">Regular employees</option><option value="Intern">Interns</option></select>' +
//           '<select id="f-bg" aria-label="Internship background" title="Applies to interns" disabled>' +
//             '<option value="">All backgrounds</option></select>' +
//           '<select id="f-desig" aria-label="Designation"><option value="">Any designation</option></select>' +
//           '<input id="f-joined" type="date" aria-label="Joined on or after" title="Joined on or after">' +
//           '<button class="btn btn-sm" id="f-clear" type="button">Clear</button>' +
//         "</div></div>" +
//         '<div id="table-host">' + RG.skeletonRows(8) + "</div>" +
//         '<div class="pager" id="pager"></div></div>';

//     var host = document.getElementById("table-host");

//     function header(label, key, extra) {
//       var sorted = state.sort_by === key;
//       return '<th class="' + (sorted ? "sorted " : "") + 'sortable" data-sort="' + key + '"' + (extra || "") + ">" +
//         label + '<span class="arrow">' + (sorted && state.sort_dir === "desc" ? "\u2193" : "\u2191") + "</span></th>";
//     }

//     function row(e) {
//       var docPct = e.document_completion === null || e.document_completion === undefined ? 0 : e.document_completion;
//       return "<tr>" +
//         '<td data-label="Employee"><div class="identity">' + RG.avatar(e) +
//           '<div><div class="name truncate">' + RG.esc(e.full_name) + "</div>" +
//           '<div class="meta truncate">' + RG.esc(e.email) + "</div></div></div></td>" +
//         '<td data-label="Employee ID" class="num nowrap">' +
//           (e.unique_employee_id
//             ? RG.esc(e.unique_employee_id)
//             : '<span class="muted" title="Issued when the profile is complete">' +
//               RG.esc(e.employee_code) + "</span>") + "</td>" +
//         '<td data-label="Department">' + RG.esc(e.department || "\u2014") +
//           (e.internship_background ? '<div class="small muted">' + RG.esc(e.internship_background) + "</div>" : "") + "</td>" +
//         '<td data-label="Designation">' + RG.esc(e.designation) + "</td>" +
//         '<td data-label="Joined" class="nowrap">' + RG.fmt.date(e.joining_date) + "</td>" +
//         '<td data-label="Status">' + RG.badge(e.employment_status) + "</td>" +
//         '<td data-label="Documents"><div class="meter-label"><span>' + RG.esc(e.document_label || "\u2014") + "</span></div>" +
//           '<div class="bar thin" style="min-width:78px"><span style="width:' + docPct + '%"></span></div></td>' +
//         '<td data-label="Salary">' + RG.badge(e.salary_status || "None") + "</td>" +
//         '<td class="actions" data-label="Actions">' +
//           '<a class="btn btn-sm" href="employee-details.html?id=' + e.id + '">View</a>' +
//           '<button class="btn btn-sm" data-edit="' + e.id + '">Edit</button>' +
//           (e.is_active
//             ? '<button class="btn btn-sm btn-ghost" data-deactivate="' + e.id + '">Deactivate</button>'
//             : '<button class="btn btn-sm btn-ok" data-activate="' + e.id + '">Activate</button>') +
//         "</td></tr>";
//     }

//     function render(data) {
//       if (!data.items.length) {
//         host.innerHTML = RG.emptyState("No employees match those filters",
//           "Clear the filters, or add someone new.",
//           '<button class="btn btn-sm btn-brand" data-new>Add employee</button>', "users");
//         document.getElementById("pager").innerHTML = "";
//         return;
//       }
//       host.innerHTML = '<div class="table-scroll"><table class="data"><thead><tr>' +
//         header("Employee", "full_name") +
//         header("Employee ID", "employee_code") +
//         header("Department", "department") +
//         "<th>Designation</th>" +
//         header("Joining date", "joining_date") +
//         "<th>Status</th><th>Documents</th><th>Salary</th><th></th>" +
//         "</tr></thead><tbody>" + data.items.map(row).join("") + "</tbody></table></div>";
//       RG.hydratePhotos(host);
//       RG.renderPager(document.getElementById("pager"), data.meta, function (p) { state.page = p; load(); });
//       host.querySelectorAll("th[data-sort]").forEach(function (th) {
//         th.addEventListener("click", function () {
//           var key = th.dataset.sort;
//           state.sort_dir = state.sort_by === key && state.sort_dir === "asc" ? "desc" : "asc";
//           state.sort_by = key;
//           state.page = 1;
//           load();
//         });
//       });
//     }

//     function load() {
//       host.setAttribute("aria-busy", "true");
//       API.get("/employees", state).then(function (data) {
//         host.removeAttribute("aria-busy");
//         render(data);
//       }).catch(function (err) {
//         host.innerHTML = RG.errorState(err.message, "retry");
//         var retry = document.getElementById("retry");
//         if (retry) retry.addEventListener("click", load);
//       });
//     }

//     loadLookups().then(function () {
//       document.getElementById("f-dept").innerHTML = '<option value="">All departments</option>' +
//         RG.optionList(lookups.departments, "id", "name");
//       var designations = allDesignations();
//       document.getElementById("f-desig").innerHTML = '<option value="">Any designation</option>' +
//         designations.map(function (d) { return '<option value="' + RG.esc(d) + '">' + RG.esc(d) + "</option>"; }).join("");
//       var bg = document.getElementById("f-bg");
//       bg.innerHTML = '<option value="">All backgrounds</option>' +
//         lookups.backgrounds.map(function (b) {
//           return '<option value="' + b.id + '">' + RG.esc(b.name) + "</option>";
//         }).join("");
//       syncBackgroundFilter();
//       if (RG.param("new")) openEmployeeModal(null, load);
//     });

//     /* Internship background only means something for interns, so it stays
//        disabled (and cleared) unless the view is scoped to the Internship
//        department or to interns. */
//     function internshipDeptId() {
//       var match = (lookups.departments || []).filter(function (d) {
//         return d.name === "Internship";
//       })[0];
//       return match ? String(match.id) : "";
//     }

//     function syncBackgroundFilter() {
//       var bg = document.getElementById("f-bg");
//       if (!bg) return;
//       var internDept = internshipDeptId();
//       var relevant = state.employee_type === "Intern" ||
//         (internDept && String(state.department_id) === internDept);
//       bg.disabled = !relevant;
//       bg.title = relevant
//         ? "Filter interns by background"
//         : "Choose the Internship department or Interns to use this";
//       if (!relevant && state.internship_background_id) {
//         state.internship_background_id = "";
//         bg.value = "";
//       }
//     }

//     document.getElementById("q").addEventListener("input", RG.debounce(function (e) {
//       state.search = e.target.value.trim(); state.page = 1; load();
//     }));
//     [["f-dept", "department_id"], ["f-status", "employment_status"], ["f-docs", "document_status"],
//      ["f-salary", "salary_status"], ["f-desig", "designation"], ["f-joined", "joined_from"],
//      ["f-type", "employee_type"], ["f-bg", "internship_background_id"]]
//       .forEach(function (pair) {
//         document.getElementById(pair[0]).addEventListener("change", function (e) {
//           state[pair[1]] = e.target.value;
//           state.page = 1;
//           // department and type both decide whether background applies
//           if (pair[0] === "f-dept" || pair[0] === "f-type") syncBackgroundFilter();
//           load();
//         });
//       });

//     document.getElementById("f-clear").addEventListener("click", function () {
//       state.search = "";
//       state.department_id = "";
//       state.employment_status = "";
//       state.employee_type = "";
//       state.internship_background_id = "";
//       state.designation = "";
//       state.joined_from = "";
//       state.document_status = "";
//       state.salary_status = "";
//       state.page = 1;
//       ["q", "f-dept", "f-status", "f-docs", "f-salary", "f-desig", "f-joined",
//        "f-type", "f-bg"].forEach(function (id) {
//         var el = document.getElementById(id);
//         if (el) el.value = "";
//       });
//       syncBackgroundFilter();
//       load();
//     });

//     RG.on(ctx.page, "[data-new]", "click", function () { openEmployeeModal(null, load); });
//     RG.on(ctx.page, "[data-edit]", "click", function (e, btn) {
//       API.get("/employees/" + btn.dataset.edit)
//         .then(function (emp) { openEmployeeModal(emp, load); })
//         .catch(RG.toastErr);
//     });
//     RG.on(ctx.page, "[data-deactivate]", "click", function (e, btn) {
//       RG.confirmAction({
//         title: "Deactivate this employee?",
//         message: "They won't be able to sign in. Their records, documents and payslips stay intact.",
//         confirmLabel: "Deactivate", danger: true
//       }).then(function (ok) {
//         if (!ok) return;
//         API.post("/employees/" + btn.dataset.deactivate + "/deactivate", {})
//           .then(function () { RG.toastOk("Employee deactivated."); load(); })
//           .catch(RG.toastErr);
//       });
//     });
//     RG.on(ctx.page, "[data-activate]", "click", function (e, btn) {
//       API.post("/employees/" + btn.dataset.activate + "/activate", {})
//         .then(function () { RG.toastOk("Employee activated."); load(); })
//         .catch(RG.toastErr);
//     });

//     load();
//   }

//   /* ======================= detail page ======================= */
//   function detailPage() {
//     var ctx = RG.boot({ scope: "hr", active: "employees", title: "Employee details", subtitle: "Full record" });
//     if (!ctx) return;
//     var id = RG.param("id");
//     if (!id) { ctx.page.innerHTML = RG.errorState("No employee was selected."); return; }

//     ctx.page.innerHTML = RG.skeletonCards(2);

//     function changeRequestsCard(requests, employee) {
//       var body;
//       if (!requests.length) {
//         body = '<p class="small muted mb-0">No profile change requests from this employee.</p>';
//       } else {
//         body = '<ul class="mini-list">' + requests.map(function (r) {
//           return '<li><div style="min-width:0"><b>' + RG.esc(r.field_label) + "</b>" +
//             '<div class="small muted truncate">' + RG.esc(r.old_value || "\u2014") +
//             " \u2192 " + RG.esc(r.new_value) + "</div></div>" +
//             '<span class="when">' + RG.badge(r.status) + "</span></li>";
//         }).join("") + "</ul>";
//       }
//       var pending = requests.filter(function (r) { return r.status === "Pending"; }).length;
//       return '<div class="card span-2"><div class="card-head"><h3>Profile change requests</h3>' +
//         '<a class="hint" href="profile-requests.html">' +
//         (pending ? pending + " pending \u00B7 review" : "Open review queue") + "</a></div>" +
//         '<div class="card-body">' + body + "</div></div>";
//     }

//     function idCardModal(employee) {
//       var modal = RG.openModal({
//         title: "Electronic ID Card \u00B7 " + employee.full_name,
//         body: RG.skeletonCards(1),
//         footer: '<button class="btn" data-close>Close</button>'
//       });
//       API.get("/employees/" + employee.id + "/id-card").then(function (card) {
//         if (!card.available) {
//           modal.body.innerHTML = '<div class="idcard-pending"><b>No ID card yet</b>' +
//             '<p class="small muted mt-2 mb-0">The card is issued once the profile is complete.</p>' +
//             (card.missing_fields && card.missing_fields.length
//               ? "<ul>" + card.missing_fields.map(function (f) {
//                   return "<li>" + RG.esc(f) + "</li>";
//                 }).join("") + "</ul>"
//               : "") + "</div>";
//           return;
//         }
//         modal.body.innerHTML = '<div class="idcard-wrap">' +
//           '<div class="idcard">' +
//             '<div class="idcard-band"><img alt="" src="../assets/logo/rocket-genie-logo.png">' +
//               "<div><b>" + RG.esc(card.company_name || "Rocket Genie") + "</b>" +
//               "<span>Employee Identity Card</span></div></div>" +
//             '<div class="idcard-body">' +
//               '<div class="idcard-photo">' + (card.photo_path
//                 ? '<img alt="" data-photo="' + card.employee_id + '">'
//                 : RG.esc(RG.fmt.initials(card.full_name))) + "</div>" +
//               '<div class="idcard-who"><h4>' + RG.esc(card.full_name) + "</h4>" +
//                 '<p class="role">' + RG.esc(card.designation || "") + "</p>" +
//                 '<span class="idcard-chip">' + RG.esc(card.unique_employee_id) + "</span></div>" +
//               '<div class="idcard-fields">' +
//                 "<div><dt>Department</dt><dd>" + RG.esc(card.department || "\u2014") + "</dd></div>" +
//                 "<div><dt>Date of joining</dt><dd>" + RG.fmt.date(card.joining_date) + "</dd></div>" +
//                 "<div><dt>Email</dt><dd>" + RG.esc(card.email || "\u2014") + "</dd></div>" +
//                 "<div><dt>Phone</dt><dd>" + RG.esc(card.phone || "\u2014") + "</dd></div>" +
//               "</div></div>" +
//             '<div class="idcard-foot">' + RG.esc(card.company_address || "") + "</div>" +
//           "</div>" +
//           '<div class="idcard-actions">' +
//             '<button class="btn btn-brand" data-card-pdf>Download PDF</button></div></div>';
//         RG.hydratePhotos(modal.body);
//         modal.body.querySelector("[data-card-pdf]").addEventListener("click", function () {
//           var button = modal.body.querySelector("[data-card-pdf]");
//           RG.setBusy(button, true, "Preparing\u2026");
//           API.download("/employees/" + employee.id + "/id-card/pdf",
//                        "ID-Card-" + card.unique_employee_id + ".pdf")
//             .then(function () { RG.setBusy(button, false); })
//             .catch(function (err) { RG.setBusy(button, false); RG.toastErr(err); });
//         });
//       }).catch(function (err) { modal.body.innerHTML = RG.errorState(err.message); });
//     }

//     function kv(label, value) {
//       return "<dt>" + label + "</dt><dd>" + (value === null || value === undefined || value === "" ? "\u2014" : value) + "</dd>";
//     }

//     Promise.all([
//       API.get("/employees/" + id),
//       API.get("/documents/employee/" + id).catch(function () { return null; }),
//       API.get("/salaries", { employee_id: id, page: 1, page_size: 6 }).catch(function () { return { items: [] }; }),
//       API.get("/profile-change-requests", { employee_id: id, page: 1, page_size: 10 })
//         .catch(function () { return { items: [] }; })
//     ]).then(function (res) {
//       var e = res[0], docs = res[1], salaries = res[2].items || [];
//       var changeRequests = (res[3] && res[3].items) || [];

//       var docRows = docs ? docs.items.map(function (d) {
//         return '<li class="row" style="padding:8px 0;border-bottom:1px solid var(--line)">' +
//           '<span class="truncate" style="flex:1 1 auto">' + RG.esc(d.document_type) + "</span>" +
//           RG.badge(d.status) +
//           (d.document_id ? '<button class="btn btn-sm" data-doc="' + d.document_id + '">Open</button>' : "") +
//           "</li>";
//       }).join("") : "";

//       ctx.page.innerHTML =
//         '<div class="page-head"><div class="identity">' + RG.avatar(e, "lg") +
//           "<div><h1>" + RG.esc(e.full_name) + "</h1>" +
//           '<p class="sub">' + RG.esc(e.designation) + " \u00B7 " +
//             RG.esc(e.department || "") + "</p>" +
//           '<div class="row mt-2">' +
//             (e.unique_employee_id
//               ? '<span class="idcard-chip">' + RG.esc(e.unique_employee_id) + "</span>"
//               : '<span class="lock-pill">ID pending profile completion</span>') +
//             RG.badge(e.employment_status) + RG.badge(e.uan_status || "Not Submitted") +
//             (e.identity_locked ? '<span class="lock-pill">Identity locked</span>' : "") +
//           "</div></div></div>" +
//           '<div class="page-actions"><a class="btn" href="employees.html">Back to directory</a>' +
//             '<button class="btn" data-idcard' +
//               (e.id_card_available ? "" : " disabled title=\"Profile is incomplete\"") +
//               ">View ID Card</button>" +
//             '<button class="btn btn-primary" data-edit-this>Edit record</button></div></div>' +
//         '<div class="grid grid-2 mb-4">' +
//           '<div class="card"><div class="card-head"><h3>Personal information</h3></div><div class="card-body">' +
//             '<dl class="kv">' +
//               kv("Full name", RG.esc(e.full_name)) + kv("Date of birth", RG.fmt.date(e.date_of_birth)) +
//               kv("Gender", RG.esc(e.gender)) + kv("Phone", RG.esc(e.phone)) + kv("Email", RG.esc(e.email)) +
//               kv("Address", RG.esc(e.address)) +
//               kv("Emergency contact", RG.esc(e.emergency_contact_name) +
//                 (e.emergency_contact_phone ? " \u00B7 " + RG.esc(e.emergency_contact_phone) : "") +
//                 (e.emergency_contact_relation ? ' <span class="muted small">(' + RG.esc(e.emergency_contact_relation) + ")</span>" : "")) +
//             "</dl></div></div>" +
//           '<div class="card"><div class="card-head"><h3>Employment</h3></div><div class="card-body">' +
//             '<dl class="kv">' +
//               kv("Employee ID", e.unique_employee_id
//                 ? '<span class="num">' + RG.esc(e.unique_employee_id) + "</span>"
//                 : '<span class="muted">Pending profile completion</span>') +
//               kv("Joining code", RG.esc(e.employee_code)) +
//               kv("Department", RG.esc(e.department)) +
//               (e.is_intern ? kv("Internship background", RG.esc(e.internship_background) || '<span class="badge warn">Not set</span>') : "") +
//               kv("Designation", RG.esc(e.designation)) + kv("Joining date", RG.fmt.date(e.joining_date)) +
//               kv("Reporting manager", RG.esc(e.reporting_manager)) +
//               kv("Employment status", RG.badge(e.employment_status)) +
//               kv("Profile completion", Math.round(e.profile_completion || 0) + "%" +
//                 ((e.profile_missing_fields || []).length
//                   ? ' <span class="muted small">(missing: ' +
//                     RG.esc(e.profile_missing_fields.join(", ")) + ")</span>"
//                   : "")) +
//               kv("Identity fields", e.identity_locked
//                 ? '<span class="lock-pill">Locked \u00B7 change needs approval</span>'
//                 : '<span class="muted">Editable until the profile is complete</span>') +
//             "</dl></div></div>" +
//         "</div>" +
//         '<div class="grid grid-3">' +
//           '<div class="card"><div class="card-head"><h3>UAN</h3><a class="hint" href="uan.html">Review queue</a></div>' +
//             '<div class="card-body"><dl class="kv" style="grid-template-columns:120px 1fr">' +
//               kv("Number", RG.esc(e.uan_number) || "\u2014") +
//               kv("Status", RG.badge(e.uan_status || "Not Submitted")) +
//               kv("Submitted", RG.fmt.date(e.uan_submitted_at)) +
//               kv("HR remarks", RG.esc(e.uan_remarks)) +
//             "</dl></div></div>" +
//           '<div class="card"><div class="card-head"><h3>Documents</h3>' +
//             "<span class=\"hint\">" + RG.esc(docs ? docs.completion.label : "") + "</span></div>" +
//             '<div class="card-body">' + (docs
//               ? '<div class="bar mb-4"><span style="width:' + docs.completion.percent + '%"></span></div>' +
//                 '<ul style="list-style:none;margin:0;padding:0">' + docRows + "</ul>"
//               : RG.emptyState("No documents", "Nothing uploaded yet.")) + "</div></div>" +
//           '<div class="card"><div class="card-head"><h3>Salary history</h3><a class="hint" href="salary.html?employee_id=' + e.id + '">Manage</a></div>' +
//             "<div>" + (salaries.length
//               ? '<ul class="mini-list">' + salaries.map(function (s) {
//                   return "<li><div><b>" + RG.esc(s.period_label) + "</b><div class=\"small muted\">" +
//                     RG.fmt.money(s.net_pay) + " net</div></div><span class=\"when\">" + RG.badge(s.status) + "</span></li>";
//                 }).join("") + "</ul>"
//               : RG.emptyState("No salary records", "Create the first one from the salary page.")) + "</div></div>" +
//           changeRequestsCard(changeRequests, e) +
//         "</div>";

//       RG.hydratePhotos(ctx.page);
//       loadLookups().then(function () {
//         RG.on(ctx.page, "[data-edit-this]", "click", function () {
//           openEmployeeModal(e, function () { location.reload(); });
//         });
//       });
//       RG.on(ctx.page, "[data-idcard]", "click", function () { idCardModal(e); });
//       RG.on(ctx.page, "[data-doc]", "click", function (ev, btn) {
//         API.blob("/documents/" + btn.dataset.doc + "/download").then(function (file) {
//           window.open(file.url, "_blank");
//         }).catch(RG.toastErr);
//       });
//     }).catch(function (err) {
//       ctx.page.innerHTML = '<div class="card">' + RG.errorState(err.message) + "</div>";
//     });
//   }

//   if (PAGE === "employee-details") detailPage(); else listPage();
// })();


/* employees.js - HR employee directory
   Department dropdown + designation mapping + employee management
*/
(function () {
  "use strict";

  var PAGE = document.body.dataset.page;

  var STATUSES = [
    "Active",
    "Inactive",
    "On Leave",
    "Resigned",
    "Terminated"
  ];

  var GENDERS = [
    "Female",
    "Male",
    "Other",
    "Prefer not to say"
  ];

  /*
   * ============================================================
   * MASTER DEPARTMENTS
   * ============================================================
   *
   * These IDs match your roboo_hr database:
   *
   * 1 Finance
   * 2 Teaching
   * 3 Marketing
   * 4 Digital Marketing
   * 5 Managers
   * 6 HR
   * 7 Internship
   * 8 Senior HR
   *
   * This guarantees that the dropdown is never empty.
   */
  var DEPARTMENTS = [
    {
      id: 1,
      name: "Finance",
      code: "FIN"
    },
    {
      id: 2,
      name: "Teaching",
      code: "TEACH"
    },
    {
      id: 3,
      name: "Marketing",
      code: "MKT"
    },
    {
      id: 4,
      name: "Digital Marketing",
      code: "DMKT"
    },
    {
      id: 5,
      name: "Managers",
      code: "MGR"
    },
    {
      id: 6,
      name: "HR",
      code: "HR"
    },
    {
      id: 7,
      name: "Internship",
      code: "INTERN"
    },
    {
      id: 8,
      name: "Senior HR",
      code: "SRHR"
    }
  ];

  /*
   * ============================================================
   * DESIGNATIONS BY DEPARTMENT
   * ============================================================
   */
  var DESIGNATIONS_BY_DEPARTMENT = {

    "Teaching": [
      "Trainer",
      "Senior Trainer",
      "Faculty Coordinator",
      "Curriculum Designer",
      "Academic Coordinator"
    ],

    "Marketing": [
      "Marketing Executive",
      "Marketing Lead",
      "Business Development Executive",
      "Sales Executive",
      "Sales Manager"
    ],

    "Digital Marketing": [
      "Digital Marketing Executive",
      "SEO Specialist",
      "Content Strategist",
      "Social Media Manager",
      "Digital Marketing Manager"
    ],

    "Managers": [
      "Project Manager",
      "Operations Manager",
      "Program Manager",
      "Team Manager"
    ],

    "HR": [
      "HR Executive",
      "HR Manager",
      "Recruiter",
      "HR Coordinator"
    ],

    "Internship": [
      "Trainee",
      "Intern",
      "Project Trainee"
    ],

    "Senior HR": [
      "Senior HR Manager",
      "HR Lead",
      "Head of People"
    ],

    "Finance": [
      "Finance Executive",
      "Accountant",
      "Finance Manager",
      "Senior Accountant"
    ]
  };

  var lookups = {
    departments: DEPARTMENTS.slice(),
    backgrounds: [],
    managers: []
  };

  /*
   * ============================================================
   * HELPERS
   * ============================================================
   */

  function asList(value) {
    if (Array.isArray(value)) {
      return value;
    }

    if (
      value &&
      Array.isArray(value.items)
    ) {
      return value.items;
    }

    if (
      value &&
      Array.isArray(value.data)
    ) {
      return value.data;
    }

    return [];
  }

  /*
   * Always use the known department list.
   *
   * The backend/database can still be used for filtering,
   * but the UI department dropdown will never be empty.
   */
  function getDepartments() {
    return DEPARTMENTS.slice();
  }

  /*
   * ============================================================
   * LOAD LOOKUPS
   * ============================================================
   */
  /*
   * The database is the source of truth for departments: the list above is
   * only a fallback when the API can't be reached. The ids in it match one
   * particular installation, so the live list always replaces it in place.
   */
  var departmentsSynced = null;
  function syncDepartments() {
    if (departmentsSynced) return departmentsSynced;
    departmentsSynced = API.get("/departments").then(function (rows) {
      var live = asList(rows).filter(function (d) { return d && d.is_active !== false; });
      if (live.length) {
        DEPARTMENTS.length = 0;
        live.forEach(function (d) { DEPARTMENTS.push({ id: d.id, name: d.name, code: d.code }); });
      }
      return DEPARTMENTS;
    }).catch(function () { return DEPARTMENTS; });
    return departmentsSynced;
  }
  syncDepartments();

  function loadLookups() {

    /*
     * Departments come from the database (see syncDepartments).
     */
    lookups.departments = getDepartments();

    /*
     * Backgrounds
     */
    var backgroundRequest = API.get(
      "/internship-backgrounds"
    )
      .then(function (data) {

        return asList(data).filter(function (b) {
          return (
            b &&
            b.is_active !== false
          );
        });

      })
      .catch(function () {

        return [];

      });

    /*
     * Managers
     *
     * This request is optional.
     * If it fails, the department dropdown still works.
     */
    var managerRequest = API.get(
      "/employees",
      {
        page: 1,
        page_size: 100
      }
    )
      .then(function (data) {

        return asList(data);

      })
      .catch(function () {

        return [];

      });

    /*
     * Reporting hierarchy: who can be a Reporting HR / Reporting Manager
     * for the signed-in user (Admin: everyone; HR: themselves and their
     * own managers). Optional - the form still works without it.
     */
    var hrRequest = API.get("/hierarchy/candidates", { role: "HR_ADMIN" })
      .then(function (d) { return asList(d); }).catch(function () { return []; });
    var mgrRequest = API.get("/hierarchy/candidates", { role: "MANAGER" })
      .then(function (d) { return asList(d); }).catch(function () { return []; });

    return Promise.all([
      backgroundRequest,
      managerRequest,
      hrRequest,
      mgrRequest,
      syncDepartments()
    ]).then(function (res) {

      lookups.departments =
        DEPARTMENTS.slice();

      lookups.backgrounds =
        res[0];

      lookups.managers =
        res[1];

      lookups.hrCandidates = res[2];
      lookups.managerCandidates = res[3];

      return lookups;

    });
  }

  /*
   * ============================================================
   * DEPARTMENT HTML
   * ============================================================
   */
  function departmentOptions(selected) {

    var html =
      '<option value="">Select department</option>';

    DEPARTMENTS.forEach(function (department) {

      var isSelected =
        String(selected || "") ===
        String(department.id);

      html +=
        '<option value="' +
        department.id +
        '"' +
        (
          isSelected
            ? " selected"
            : ""
        ) +
        ">" +
        RG.esc(
          department.name
        ) +
        "</option>";
    });

    return html;
  }

  /*
   * ============================================================
   * DESIGNATION OPTIONS
   * ============================================================
   */
  function designationOptions(
    departmentId,
    selected
  ) {

    var department =
      DEPARTMENTS.filter(
        function (d) {
          return (
            String(d.id) ===
            String(
              departmentId || ""
            )
          );
        }
      )[0];

    var names =
      department
        ? (
            DESIGNATIONS_BY_DEPARTMENT[
              department.name
            ] || []
          ).slice()
        : [];

    if (
      selected &&
      names.indexOf(selected) === -1
    ) {
      names.push(selected);
    }

    var html =
      '<option value="">Select designation</option>';

    names.forEach(function (name) {

      html +=
        '<option value="' +
        RG.esc(name) +
        '"' +
        (
          String(selected || "") ===
          String(name)
            ? " selected"
            : ""
        ) +
        ">" +
        RG.esc(name) +
        "</option>";
    });

    return html;
  }

  /*
   * ============================================================
   * ALL DESIGNATIONS FOR FILTER
   * ============================================================
   */
  function allDesignations() {

    var values = [];

    Object.keys(
      DESIGNATIONS_BY_DEPARTMENT
    ).forEach(function (department) {

      DESIGNATIONS_BY_DEPARTMENT[
        department
      ].forEach(function (name) {

        if (
          values.indexOf(name) === -1
        ) {
          values.push(name);
        }

      });

    });

    lookups.managers.forEach(
      function (manager) {

        if (
          manager &&
          manager.designation &&
          values.indexOf(
            manager.designation
          ) === -1
        ) {
          values.push(
            manager.designation
          );
        }

      }
    );

    return values.sort();
  }

  /*
   * ============================================================
   * INTERNSHIP DEPARTMENT
   * ============================================================
   */
  function internDeptId() {

    var department =
      DEPARTMENTS.filter(
        function (d) {
          return (
            d.name ===
            "Internship"
          );
        }
      )[0];

    return department
      ? department.id
      : null;
  }

  /*
   * ============================================================
   * FORM FIELD
   * ============================================================
   */
  function field(
    label,
    name,
    type,
    value,
    required,
    extra
  ) {

    return (
      '<div class="field">' +

      '<label for="f-' +
      name +
      '">' +

      RG.esc(label) +

      (
        required
          ? ' <span class="req">*</span>'
          : ""
      ) +

      "</label>" +

      '<input id="f-' +
      name +
      '" ' +
      'name="' +
      name +
      '" ' +
      'type="' +
      type +
      '" ' +
      'value="' +
      RG.esc(
        value === null ||
        value === undefined
          ? ""
          : value
      ) +
      '"' +

      (
        required
          ? " required"
          : ""
      ) +

      (
        extra || ""
      ) +

      ">" +

      "</div>"
    );
  }

  /*
   * ============================================================
   * EMPLOYEE FORM
   * ============================================================
   */
  function employeeForm(existing) {

    var e =
      existing || {};

    var isEdit =
      !!existing;

    return (

      '<form id="emp-form" class="form-grid">' +

      /*
       * PERSONAL INFORMATION
       */
      '<div class="form-section full">' +

      "<h4>Personal information</h4>" +

      '<div class="form-grid">' +

      field(
        "Full name",
        "full_name",
        "text",
        e.full_name,
        true
      ) +

      (
        isEdit
          ? field(
              "Work email",
              "email",
              "email",
              e.email,
              false,
              " readonly"
            )
          : field(
              "Work email",
              "email",
              "email",
              "",
              true
            )
      ) +

      field(
        "Phone",
        "phone",
        "tel",
        e.phone
      ) +

      field(
        "Date of birth",
        "date_of_birth",
        "date",
        e.date_of_birth
      ) +

      /*
       * GENDER
       */
      '<div class="field">' +

      '<label for="f-gender">' +
      "Gender" +
      "</label>" +

      '<select id="f-gender" name="gender">' +

      '<option value="">' +
      "Not specified" +
      "</option>" +

      GENDERS.map(
        function (gender) {

          return (
            '<option value="' +
            RG.esc(gender) +
            '"' +

            (
              e.gender ===
              gender
                ? " selected"
                : ""
            ) +

            ">" +

            RG.esc(gender) +

            "</option>"
          );

        }
      ).join("") +

      "</select>" +

      "</div>" +

      /*
       * ADDRESS
       */
      '<div class="field full">' +

      '<label for="f-address">' +
      "Address" +
      "</label>" +

      '<textarea id="f-address" ' +
      'name="address" rows="2">' +

      RG.esc(
        e.address || ""
      ) +

      "</textarea>" +

      "</div>" +

      "</div>" +

      "</div>" +

      /*
       * EMPLOYMENT
       */
      '<div class="form-section full">' +

      "<h4>Employment</h4>" +

      '<div class="form-grid">' +

      /*
       * EMPLOYEE ID
       */
      (
        isEdit
          ? field(
              "Employee ID",
              "employee_code",
              "text",
              e.employee_code,
              false,
              " readonly"
            )
          : (
              '<div class="field">' +

              '<label for="f-employee_code">' +
              "Employee ID" +
              "</label>" +

              '<input id="f-employee_code" ' +
              'type="text" value="" ' +
              'placeholder="Automatically generated" ' +
              "readonly>" +

              '<span class="help">' +
              "Employee ID is generated automatically when the account is created." +
              "</span>" +

              "</div>"
            )
      ) +

      /*
       * EMPLOYEE TYPE (Employee / Intern). Interns belong to the
       * Internship department and need an internship background.
       */
      '<div class="field">' +
      '<label for="f-employee_type">Employee type <span class="req">*</span></label>' +
      '<select id="f-employee_type" name="employee_type"' + (isEdit ? " disabled" : "") + ">" +
      '<option value="Employee"' + (e.department === "Internship" ? "" : " selected") + ">Employee</option>" +
      '<option value="Intern"' + (e.department === "Internship" ? " selected" : "") + ">Intern</option>" +
      "</select>" +
      '<span class="help">' + (isEdit ? "Change the department to move between employee and intern." : "Interns are placed in the Internship department.") + "</span>" +
      "</div>" +

      /*
       * ========================================================
       * DEPARTMENT
       * ========================================================
       */
      '<div class="field">' +

      '<label for="f-department_id">' +

      "Department " +

      '<span class="req">*</span>' +

      "</label>" +

      '<select id="f-department_id" ' +
      'name="department_id" required>' +

      departmentOptions(
        e.department_id
      ) +

      "</select>" +

      "</div>" +

      /*
       * ========================================================
       * DESIGNATION
       * ========================================================
       */
      '<div class="field">' +

      '<label for="f-designation">' +

      "Designation " +

      '<span class="req">*</span>' +

      "</label>" +

      '<select id="f-designation" ' +
      'name="designation" required>' +

      designationOptions(
        e.department_id,
        e.designation
      ) +

      "</select>" +

      "</div>" +

      /*
       * INTERNSHIP BACKGROUND
       */
      '<div class="field" id="bg-field">' +

      '<label for="f-internship_background_id">' +

      "Internship background" +

      "</label>" +

      '<select id="f-internship_background_id" ' +
      'name="internship_background_id">' +

      '<option value="">' +
      "Select a background" +
      "</option>" +

      RG.optionList(
        lookups.backgrounds,
        "id",
        "name",
        e.internship_background_id
      ) +

      "</select>" +

      '<span class="help">' +
      "Required when the department is Internship." +
      "</span>" +

      "</div>" +

      /*
       * JOINING DATE
       */
      field(
        "Joining date",
        "joining_date",
        "date",
        e.joining_date,
        true
      ) +

      /*
       * WORK LOCATION (printed as "Location" on salary slips)
       */
      field(
        "Work location",
        "work_location",
        "text",
        e.work_location,
        false,
        ' maxlength="120" placeholder="e.g. New Delhi \u2014 blank uses the company default"'
      ) +

      /*
       * EMPLOYMENT STATUS
       */
      '<div class="field">' +

      '<label for="f-employment_status">' +
      "Employment status" +
      "</label>" +

      '<select id="f-employment_status" ' +
      'name="employment_status">' +

      STATUSES.map(
        function (status) {

          return (
            '<option value="' +
            RG.esc(status) +
            '"' +

            (
              (
                e.employment_status ||
                "Active"
              ) === status
                ? " selected"
                : ""
            ) +

            ">" +

            RG.esc(status) +

            "</option>"
          );

        }
      ).join("") +

      "</select>" +

      "</div>" +

      /*
       * ROLE & REPORTING HIERARCHY
       * Admin -> HR -> Manager -> Employee / Intern. The API validates
       * every combination; these fields only offer what the signed-in
       * user is allowed to choose.
       */
      hierarchyFields(e) +

      "</div>" +

      "</div>" +

      /*
       * EMERGENCY CONTACT
       */
      '<div class="form-section full">' +

      "<h4>Emergency contact</h4>" +

      '<div class="form-grid">' +

      field(
        "Contact name",
        "emergency_contact_name",
        "text",
        e.emergency_contact_name
      ) +

      field(
        "Contact phone",
        "emergency_contact_phone",
        "tel",
        e.emergency_contact_phone
      ) +

      field(
        "Relationship",
        "emergency_contact_relation",
        "text",
        e.emergency_contact_relation
      ) +

      "</div>" +

      "</div>" +

      "</form>"
    );
  }

  /*
   * ============================================================
   * HIERARCHY FIELDS (role, Reporting HR, Reporting Manager)
   * ============================================================
   */
  function hierarchyFields(e) {
    var isAdmin = API.session.isAdmin && API.session.isAdmin();
    var role = e.role || "EMPLOYEE";
    var roles = isAdmin
      ? [["EMPLOYEE", "Employee / Intern"], ["MANAGER", "Manager"], ["HR_ADMIN", "HR"]]
      : [["EMPLOYEE", "Employee / Intern"], ["MANAGER", "Manager"]];
    if (!isAdmin && role === "HR_ADMIN") roles = [["HR_ADMIN", "HR"]];
    var hrs = lookups.hrCandidates || [];
    var mgrs = (lookups.managerCandidates || []).filter(function (m) { return m.id !== e.id; });
    return '<div class="field"><label for="f-role">Role</label>' +
        '<select id="f-role" name="role">' + roles.map(function (r) {
          return '<option value="' + r[0] + '"' + (r[0] === role ? " selected" : "") + ">" + r[1] + "</option>";
        }).join("") + "</select>" +
        '<span class="help">HR reports to the Admin, a Manager to an HR, employees and interns to a Manager.</span></div>' +
      '<div class="field" data-hr-field><label for="f-reporting_hr_id">Reporting HR</label>' +
        '<select id="f-reporting_hr_id" name="reporting_hr_id"><option value="">' + (isAdmin ? "Not assigned" : "None") + "</option>" +
        hrs.map(function (h) {
          return '<option value="' + h.id + '"' + (String(e.reporting_hr_id || (!e.id && !isAdmin ? h.id : "")) === String(h.id) ? " selected" : "") + ">" + RG.esc(h.full_name) + "</option>";
        }).join("") + "</select></div>" +
      '<div class="field" data-mgr-field><label for="f-reporting_manager_id">Reporting manager</label>' +
        '<select id="f-reporting_manager_id" name="reporting_manager_id" data-current="' + RG.esc(e.reporting_manager_id || "") + '"><option value="">None (reports to the HR)</option>' +
        mgrs.map(function (m) {
          return '<option value="' + m.id + '" data-hr="' + (m.reporting_hr_id || "") + '"' + (String(e.reporting_manager_id || "") === String(m.id) ? " selected" : "") + ">" +
            RG.esc(m.full_name) + (m.reporting_hr ? " (HR: " + RG.esc(m.reporting_hr) + ")" : "") + "</option>";
        }).join("") + "</select>" +
        '<span class="help">Picking a manager also sets the Reporting HR to that manager\'s HR.</span></div>';
  }

  function wireHierarchy(root) {
    var roleEl = root.querySelector("#f-role");
    var hrEl = root.querySelector("#f-reporting_hr_id");
    var mgrEl = root.querySelector("#f-reporting_manager_id");
    if (!roleEl || !hrEl || !mgrEl) return;
    function sync() {
      var role = roleEl.value;
      root.querySelector("[data-hr-field]").style.display = role === "HR_ADMIN" ? "none" : "";
      root.querySelector("[data-mgr-field]").style.display = role === "EMPLOYEE" ? "" : "none";
      Array.prototype.forEach.call(mgrEl.options, function (o) {
        if (!o.value) return;
        o.hidden = !!hrEl.value && o.dataset.hr !== hrEl.value;
      });
      if (mgrEl.selectedOptions[0] && mgrEl.selectedOptions[0].hidden) mgrEl.value = "";
    }
    roleEl.addEventListener("change", sync);
    hrEl.addEventListener("change", sync);
    mgrEl.addEventListener("change", function () {
      var o = mgrEl.selectedOptions[0];
      if (o && o.dataset.hr) hrEl.value = o.dataset.hr;
      sync();
    });
    sync();
  }

  /*
   * ============================================================
   * READ FORM
   * ============================================================
   */
  function readForm(form) {

    var data = {};

    new FormData(form).forEach(
      function (value, key) {

        data[key] =
          typeof value === "string"
            ? value.trim()
            : value;

      }
    );

    [
      "date_of_birth",
      "phone",
      "gender",
      "address",
      "work_location",
      "emergency_contact_name",
      "emergency_contact_phone",
      "emergency_contact_relation",
      "employee_code"
    ].forEach(
      function (key) {

        if (
          data[key] === ""
        ) {
          data[key] = null;
        }

      }
    );

    data.department_id =
      data.department_id
        ? Number(
            data.department_id
          )
        : null;

    data.internship_background_id =
      data.internship_background_id
        ? Number(
            data.internship_background_id
          )
        : null;

    data.reporting_manager_id =
      data.reporting_manager_id
        ? Number(
            data.reporting_manager_id
          )
        : null;

    data.reporting_hr_id =
      data.reporting_hr_id ? Number(data.reporting_hr_id) : null;

    // The fields that don't apply to the chosen role are cleared, so the
    // API receives one consistent reporting line.
    if (data.role === "HR_ADMIN") {
      data.reporting_hr_id = null;
      data.reporting_manager_id = null;
    } else if (data.role === "MANAGER") {
      data.reporting_manager_id = null;
    } else if (data.reporting_manager_id) {
      delete data.reporting_hr_id;
    }
    if (!data.role) delete data.role;

    return data;
  }

  /*
   * ============================================================
   * INTERNSHIP TOGGLE
   * ============================================================
   */
  function wireInternToggle(root) {

    var department =
      root.querySelector(
        "#f-department_id"
      );

    var backgroundField =
      root.querySelector(
        "#bg-field"
      );

    if (
      !department ||
      !backgroundField
    ) {
      return;
    }

    function sync() {

      var isIntern =
        Number(
          department.value
        ) ===
        Number(
          internDeptId()
        );

      backgroundField.style.display =
        isIntern
          ? ""
          : "none";

      var select =
        backgroundField.querySelector(
          "select"
        );

      if (select) {
        select.required =
          isIntern;
      }
    }

    department.addEventListener(
      "change",
      sync
    );

    var typeSelect = root.querySelector("#f-employee_type");
    if (typeSelect && !typeSelect.disabled) {
      var internId = String(internDeptId() || "");
      var applyType = function () {
        var intern = typeSelect.value === "Intern";
        Array.prototype.forEach.call(department.options, function (opt) {
          if (!opt.value) return;
          var isInternDept = opt.value === internId;
          opt.hidden = intern ? !isInternDept : isInternDept;
          opt.disabled = opt.hidden;
        });
        if (intern && internId) {
          department.value = internId;
        } else if (!intern && department.value === internId) {
          department.value = "";
        }
        department.dispatchEvent(new Event("change"));
      };
      typeSelect.addEventListener("change", applyType);
      applyType();
    }
    sync();
  }

  /*
   * ============================================================
   * CREATE / EDIT MODAL
   * ============================================================
   */
  function createEmployeeModal(
    existing,
    onSaved
  ) {

    var modal =
      RG.openModal({

        title:
          existing
            ? "Edit " +
              existing.full_name
            : "Add employee",

        size: "lg",

        body:
          employeeForm(
            existing
          ),

        footer:

          '<button class="btn" data-close>' +
          "Cancel" +
          "</button>" +

          '<button class="btn btn-brand" data-save>' +

          (
            existing
              ? "Save changes"
              : "Create employee &amp; account"
          ) +

          "</button>",

        onOpen:
          function (m) {
            wireInternToggle(
              m.body
            );
            wireHierarchy(m.body);
          }
      });

    var departmentSelect =
      modal.body.querySelector(
        "#f-department_id"
      );

    var designationSelect =
      modal.body.querySelector(
        "#f-designation"
      );

    /*
     * ==========================================================
     * DEPARTMENT -> DESIGNATION
     * ==========================================================
     */
    if (
      departmentSelect &&
      designationSelect
    ) {

      function updateDesignation() {

        designationSelect.innerHTML =
          designationOptions(
            departmentSelect.value,
            ""
          );

        /*
         * Keep designation disabled
         * until department is selected.
         */
        designationSelect.disabled =
          !departmentSelect.value;
      }

      departmentSelect.addEventListener(
        "change",
        updateDesignation
      );

      /*
       * Initial state
       */
      designationSelect.disabled =
        !departmentSelect.value;
    }

    /*
     * SAVE
     */
    modal.foot
      .querySelector(
        "[data-save]"
      )
      .addEventListener(
        "click",
        function () {

          var form =
            modal.body.querySelector(
              "#emp-form"
            );

          if (
            !form.reportValidity()
          ) {
            return;
          }

          var payload =
            readForm(form);

          var button =
            modal.foot.querySelector(
              "[data-save]"
            );

          RG.setBusy(
            button,
            true,
            "Saving\u2026"
          );

          var request;

          if (existing) {

            delete payload.email;
            delete payload.employee_code;

            request =
              API.put(
                "/employees/" +
                existing.id,
                payload
              );

          } else {

            payload.send_account_email =
              true;

            request =
              API.post(
                "/employees",
                payload
              );
          }

          request
            .then(
              function (res) {

                modal.close();

                RG.toastOk(
                  existing
                    ? "Employee updated."
                    : "Employee created with a portal account."
                );

                /*
                 * Account information
                 */
                if (
                  !existing &&
                  res &&
                  res.initial_password
                ) {

                  RG.openModal({

                    title:
                      "Account created",

                    size: "sm",

                    body:

                      "<p>Share these sign-in details with " +

                      RG.esc(
                        payload.full_name
                      ) +

                      ":</p>" +

                      '<div class="totals-box">' +

                      '<div class="line">' +

                      "<span>Email</span>" +

                      "<b>" +

                      RG.esc(
                        payload.email
                      ) +

                      "</b>" +

                      "</div>" +

                      '<div class="line">' +

                      "<span>Employee ID</span>" +

                      "<b>" +

                      RG.esc(
                        (
                          res.employee &&
                          res.employee.employee_code
                        ) || ""
                      ) +

                      "</b>" +

                      "</div>" +

                      '<div class="line">' +

                      "<span>Temporary password</span>" +

                      "<b>" +

                      RG.esc(
                        res.initial_password
                      ) +

                      "</b>" +

                      "</div>" +

                      "</div>" +

                      '<p class="small muted mt-4 mb-0">' +

                      "They’ll be asked to change it at first sign-in." +

                      "</p>",

                    footer:

                      '<button class="btn btn-primary" data-close>' +

                      "Got it" +

                      "</button>"
                  });
                }

                if (onSaved) {
                  onSaved();
                }

              }
            )
            .catch(
              function (err) {

                RG.setBusy(
                  button,
                  false
                );

                RG.toastErr(
                  err
                );

              }
            );
        }
      );
  }

  /*
   * ============================================================
   * OPEN EMPLOYEE MODAL
   * ============================================================
   */
  function openEmployeeModal(
    existing,
    onSaved
  ) {

    /*
     * Department list already exists synchronously.
     * We only wait for backgrounds/managers.
     */
    loadLookups()
      .then(
        function () {

          createEmployeeModal(
            existing,
            onSaved
          );

        }
      )
      .catch(
        function (err) {

          console.error(
            "Employee lookup error:",
            err
          );

          /*
           * IMPORTANT:
           * Even if API lookup fails,
           * still open the form.
           *
           * Departments are already
           * available from DEPARTMENTS.
           */
          lookups.departments =
            DEPARTMENTS.slice();

          createEmployeeModal(
            existing,
            onSaved
          );
        }
      );
  }

  /*
   * ============================================================
   * EMPLOYEE LIST PAGE
   * ============================================================
   */
  function listPage() {

    var ctx =
      RG.boot({
        scope: "hr",
        active: "employees",
        title: "Employees",
        subtitle: "Directory & accounts"
      });

    if (!ctx) {
      return;
    }

    var state = {
      page: 1,
      page_size: 10,
      search: "",
      department_id: "",
      employment_status: "",
      employee_type: RG.param("employee_type") === "Intern" || RG.param("employee_type") === "Regular" ? RG.param("employee_type") : "",
      internship_background_id: "",
      designation: "",
      joined_from: "",
      document_status: "",
      salary_status: "",
      sort_by: "full_name",
      sort_dir: "asc"
    };

    ctx.page.innerHTML =

      '<div class="page-head">' +

      '<div>' +

      "<h1>Employees</h1>" +

      '<p class="sub">' +

      "Every account, document state and salary state in one table." +

      "</p>" +

      "</div>" +

      '<div class="page-actions">' +

      '<button class="btn btn-brand" data-new>' +

      RG.icon(
        "plus",
        16
      ) +

      " Add employee" +

      "</button>" +

      "</div>" +

      "</div>" +

      '<div class="card">' +

      '<div class="toolbar">' +

      '<div class="search">' +

      RG.icon(
        "search",
        16
      ) +

      '<input id="q" type="text" ' +
      'placeholder="Search name, employee ID or email" ' +
      'aria-label="Search employees">' +

      "</div>" +

      '<div class="filters">' +

      /*
       * DEPARTMENT FILTER
       */
      '<select id="f-dept" aria-label="Department">' +

      '<option value="">' +
      "All departments" +
      "</option>" +

      "</select>" +

      /*
       * STATUS
       */
      '<select id="f-status" aria-label="Status">' +

      '<option value="">' +
      "Any status" +
      "</option>" +

      STATUSES.map(
        function (status) {

          return (
            '<option value="' +
            RG.esc(status) +
            '">' +

            RG.esc(status) +

            "</option>"
          );

        }
      ).join("") +

      "</select>" +

      /*
       * DOCUMENTS
       */
      '<select id="f-docs" aria-label="Document status">' +

      '<option value="">' +
      "Any documents" +
      "</option>" +

      '<option value="complete">' +
      "Documents complete" +
      "</option>" +

      '<option value="incomplete">' +
      "Documents incomplete" +
      "</option>" +

      "</select>" +

      /*
       * SALARY
       */
      '<select id="f-salary" aria-label="Salary status">' +

      '<option value="">' +
      "Any salary" +
      "</option>" +

      '<option value="Credited">' +
      "Salary credited" +
      "</option>" +

      '<option value="Pending">' +
      "Salary pending" +
      "</option>" +

      '<option value="Processing">' +
      "Salary processing" +
      "</option>" +

      '<option value="None">' +
      "No salary record" +
      "</option>" +

      "</select>" +

      /*
       * EMPLOYEE TYPE
       */
      '<select id="f-type" aria-label="Employee type">' +

      '<option value="">' +
      "All employee types" +
      "</option>" +

      '<option value="Regular">' +
      "Regular employees" +
      "</option>" +

      '<option value="Intern">' +
      "Interns" +
      "</option>" +

      "</select>" +

      /*
       * BACKGROUND
       */
      '<select id="f-bg" aria-label="Internship background" ' +
      'title="Applies to interns" disabled>' +

      '<option value="">' +
      "All backgrounds" +
      "</option>" +

      "</select>" +

      /*
       * DESIGNATION FILTER
       */
      '<select id="f-desig" aria-label="Designation">' +

      '<option value="">' +
      "Any designation" +
      "</option>" +

      "</select>" +

      '<input id="f-joined" type="date" ' +
      'aria-label="Joined on or after" ' +
      'title="Joined on or after">' +

      '<button class="btn btn-sm" id="f-clear" type="button">' +

      "Clear" +

      "</button>" +

      "</div>" +

      "</div>" +

      '<div id="table-host">' +

      RG.skeletonRows(
        8
      ) +

      "</div>" +

      '<div class="pager" id="pager"></div>' +

      "</div>";

    if (state.employee_type) {
      var typeFilter = document.getElementById("f-type");
      if (typeFilter) typeFilter.value = state.employee_type;
    }

    var host =
      document.getElementById(
        "table-host"
      );

    /*
     * ==========================================================
     * TABLE HEADER
     * ==========================================================
     */
    function header(
      label,
      key,
      extra
    ) {

      var sorted =
        state.sort_by ===
        key;

      return (

        '<th class="' +

        (
          sorted
            ? "sorted "
            : ""
        ) +

        'sortable" data-sort="' +
        key +
        '"' +

        (
          extra ||
          ""
        ) +

        ">" +

        label +

        '<span class="arrow">' +

        (
          sorted &&
          state.sort_dir ===
            "desc"
            ? "\u2193"
            : "\u2191"
        ) +

        "</span>" +

        "</th>"
      );
    }

    /*
     * ==========================================================
     * TABLE ROW
     * ==========================================================
     */
    function row(employee) {

      var docPct =
        employee.document_completion ===
          null ||
        employee.document_completion ===
          undefined

          ? 0

          : employee.document_completion;

      return (

        "<tr>" +

        '<td data-label="Employee">' +

        '<div class="identity">' +

        RG.avatar(
          employee
        ) +

        "<div>" +

        '<div class="name truncate">' +

        RG.esc(
          employee.full_name
        ) +

        "</div>" +

        '<div class="meta truncate">' +

        RG.esc(
          employee.email
        ) +

        "</div>" +

        "</div>" +

        "</div>" +

        "</td>" +

        '<td data-label="Employee ID" class="num nowrap">' +

        (
          employee.unique_employee_id

            ? RG.esc(
                employee.unique_employee_id
              )

            : (
                '<span class="muted" ' +
                'title="Issued when the profile is complete">' +

                RG.esc(
                  employee.employee_code
                ) +

                "</span>"
              )
        ) +

        "</td>" +

        '<td data-label="Department">' +

        RG.esc(
          employee.department ||
          "\u2014"
        ) +

        /* role, with the reporting line on hover (hierarchy) */
        '<div class="small muted" title="' + RG.esc(
          (employee.reporting_manager ? "Manager: " + employee.reporting_manager + "  " : "") +
          (employee.reporting_hr && employee.role !== "HR_ADMIN" ? "HR: " + employee.reporting_hr : "")
        ) + '">' + RG.esc(employee.role_label || "") + "</div>" +

        (
          employee.internship_background

            ? (
                '<div class="small muted">' +

                RG.esc(
                  employee.internship_background
                ) +

                "</div>"
              )

            : ""
        ) +

        "</td>" +

        '<td data-label="Designation">' +

        RG.esc(
          employee.designation
        ) +

        "</td>" +

        '<td data-label="Joined" class="nowrap">' +

        RG.fmt.date(
          employee.joining_date
        ) +

        "</td>" +

        '<td data-label="Status">' +

        RG.badge(
          employee.employment_status
        ) +

        "</td>" +

        '<td data-label="Documents">' +

        '<div class="meter-label">' +

        "<span>" +

        RG.esc(
          employee.document_label ||
          "\u2014"
        ) +

        "</span>" +

        "</div>" +

        '<div class="bar thin" style="min-width:78px">' +

        '<span style="width:' +
        docPct +
        '%"></span>' +

        "</div>" +

        "</td>" +

        '<td data-label="Salary">' +

        RG.badge(
          employee.salary_status ||
          "None"
        ) +

        "</td>" +

        '<td class="actions" data-label="Actions">' +

        '<a class="btn btn-sm" href="employee-details.html?id=' +
        employee.id +
        '">' +

        "View" +

        "</a>" +

        '<button class="btn btn-sm" data-edit="' +
        employee.id +
        '">' +

        "Edit" +

        "</button>" +

        (
          employee.is_active

            ? (
                '<button class="btn btn-sm btn-ghost" data-deactivate="' +
                employee.id +
                '">' +

                "Deactivate" +

                "</button>"
              )

            : (
                '<button class="btn btn-sm btn-ok" data-activate="' +
                employee.id +
                '">' +

                "Activate" +

                "</button>"
              )
        ) +

        "</td>" +

        "</tr>"
      );
    }

    /*
     * ==========================================================
     * RENDER TABLE
     * ==========================================================
     */
    function render(data) {

      if (
        !data.items.length
      ) {

        host.innerHTML =
          RG.emptyState(
            "No employees match those filters",
            "Clear the filters, or add someone new.",
            '<button class="btn btn-sm btn-brand" data-new>' +
            "Add employee" +
            "</button>",
            "users"
          );

        document.getElementById(
          "pager"
        ).innerHTML = "";

        return;
      }

      host.innerHTML =

        '<div class="table-scroll">' +

        '<table class="data">' +

        "<thead>" +

        "<tr>" +

        header(
          "Employee",
          "full_name"
        ) +

        header(
          "Employee ID",
          "employee_code"
        ) +

        header(
          "Department",
          "department"
        ) +

        "<th>Designation</th>" +

        header(
          "Joining date",
          "joining_date"
        ) +

        "<th>Status</th>" +

        "<th>Documents</th>" +

        "<th>Salary</th>" +

        "<th></th>" +

        "</tr>" +

        "</thead>" +

        "<tbody>" +

        data.items
          .map(row)
          .join("") +

        "</tbody>" +

        "</table>" +

        "</div>";

      RG.hydratePhotos(
        host
      );

      RG.renderPager(
        document.getElementById(
          "pager"
        ),
        data.meta,
        function (page) {

          state.page =
            page;

          load();
        }
      );

      host
        .querySelectorAll(
          "th[data-sort]"
        )
        .forEach(
          function (th) {

            th.addEventListener(
              "click",
              function () {

                var key =
                  th.dataset.sort;

                state.sort_dir =
                  state.sort_by ===
                    key &&
                  state.sort_dir ===
                    "asc"

                    ? "desc"

                    : "asc";

                state.sort_by =
                  key;

                state.page =
                  1;

                load();
              }
            );

          }
        );
    }

    /*
     * ==========================================================
     * LOAD EMPLOYEES
     * ==========================================================
     */
    function load() {

      host.setAttribute(
        "aria-busy",
        "true"
      );

      API.get(
        "/employees",
        state
      )
        .then(
          function (data) {

            host.removeAttribute(
              "aria-busy"
            );

            render(
              data
            );
          }
        )
        .catch(
          function (err) {

            host.innerHTML =
              RG.errorState(
                err.message,
                "retry"
              );

            var retry =
              document.getElementById(
                "retry"
              );

            if (retry) {

              retry.addEventListener(
                "click",
                load
              );

            }

          }
        );
    }

    /*
     * ==========================================================
     * LOAD FILTER DROPDOWNS
     * ==========================================================
     */
    loadLookups()
      .then(
        function () {

          /*
           * Department filter
           */
          var departmentFilter =
            document.getElementById(
              "f-dept"
            );

          departmentFilter.innerHTML =

            '<option value="">' +
            "All departments" +
            "</option>" +

            DEPARTMENTS.map(
              function (department) {

                return (
                  '<option value="' +
                  department.id +
                  '">' +

                  RG.esc(
                    department.name
                  ) +

                  "</option>"
                );

              }
            ).join("");

          /*
           * Designation filter
           */
          var designations =
            allDesignations();

          document.getElementById(
            "f-desig"
          ).innerHTML =

            '<option value="">' +
            "Any designation" +
            "</option>" +

            designations.map(
              function (designation) {

                return (
                  '<option value="' +
                  RG.esc(
                    designation
                  ) +
                  '">' +

                  RG.esc(
                    designation
                  ) +

                  "</option>"
                );

              }
            ).join("");

          /*
           * Background filter
           */
          var backgroundFilter =
            document.getElementById(
              "f-bg"
            );

          backgroundFilter.innerHTML =

            '<option value="">' +
            "All backgrounds" +
            "</option>" +

            lookups.backgrounds
              .map(
                function (background) {

                  return (
                    '<option value="' +
                    RG.esc(
                      background.id
                    ) +
                    '">' +

                    RG.esc(
                      background.name
                    ) +

                    "</option>"
                  );

                }
              )
              .join("");

          syncBackgroundFilter();

          /*
           * Automatically open Add Employee
           */
          if (
            RG.param("new")
          ) {

            openEmployeeModal(
              null,
              load
            );
          }

        }
      )
      .catch(
        function (err) {

          console.error(
            "Filter loading failed:",
            err
          );

          /*
           * Department filter MUST still work.
           */
          var departmentFilter =
            document.getElementById(
              "f-dept"
            );

          departmentFilter.innerHTML =

            '<option value="">' +
            "All departments" +
            "</option>" +

            DEPARTMENTS.map(
              function (department) {

                return (
                  '<option value="' +
                  department.id +
                  '">' +

                  RG.esc(
                    department.name
                  ) +

                  "</option>"
                );

              }
            ).join("");

          if (
            RG.param("new")
          ) {

            openEmployeeModal(
              null,
              load
            );
          }
        }
      );

    /*
     * ==========================================================
     * BACKGROUND FILTER
     * ==========================================================
     */
    function syncBackgroundFilter() {

      var background =
        document.getElementById(
          "f-bg"
        );

      if (!background) {
        return;
      }

      var internshipId =
        String(
          internDeptId()
        );

      var relevant =
        state.employee_type ===
          "Intern" ||

        (
          internshipId &&
          String(
            state.department_id
          ) === internshipId
        );

      background.disabled =
        !relevant;

      background.title =
        relevant

          ? "Filter interns by background"

          : "Choose the Internship department or Interns to use this";

      if (
        !relevant &&
        state.internship_background_id
      ) {

        state.internship_background_id =
          "";

        background.value =
          "";
      }
    }

    /*
     * ==========================================================
     * SEARCH
     * ==========================================================
     */
    document
      .getElementById(
        "q"
      )
      .addEventListener(
        "input",
        RG.debounce(
          function (event) {

            state.search =
              event.target.value.trim();

            state.page =
              1;

            load();
          }
        )
      );

    /*
     * ==========================================================
     * FILTER EVENTS
     * ==========================================================
     */
    [
      [
        "f-dept",
        "department_id"
      ],
      [
        "f-status",
        "employment_status"
      ],
      [
        "f-docs",
        "document_status"
      ],
      [
        "f-salary",
        "salary_status"
      ],
      [
        "f-desig",
        "designation"
      ],
      [
        "f-joined",
        "joined_from"
      ],
      [
        "f-type",
        "employee_type"
      ],
      [
        "f-bg",
        "internship_background_id"
      ]
    ].forEach(
      function (pair) {

        document
          .getElementById(
            pair[0]
          )
          .addEventListener(
            "change",
            function (event) {

              state[
                pair[1]
              ] =
                event.target.value;

              state.page =
                1;

              if (
                pair[0] ===
                  "f-dept" ||
                pair[0] ===
                  "f-type"
              ) {

                syncBackgroundFilter();
              }

              load();
            }
          );
      }
    );

    /*
     * ==========================================================
     * CLEAR FILTERS
     * ==========================================================
     */
    document
      .getElementById(
        "f-clear"
      )
      .addEventListener(
        "click",
        function () {

          state.search = "";
          state.department_id = "";
          state.employment_status = "";
          state.employee_type = "";
          state.internship_background_id = "";
          state.designation = "";
          state.joined_from = "";
          state.document_status = "";
          state.salary_status = "";
          state.page = 1;

          [
            "q",
            "f-dept",
            "f-status",
            "f-docs",
            "f-salary",
            "f-desig",
            "f-joined",
            "f-type",
            "f-bg"
          ].forEach(
            function (id) {

              var element =
                document.getElementById(
                  id
                );

              if (element) {
                element.value =
                  "";
              }

            }
          );

          syncBackgroundFilter();

          load();
        }
      );

    /*
     * ==========================================================
     * ADD EMPLOYEE
     * ==========================================================
     */
    RG.on(
      ctx.page,
      "[data-new]",
      "click",
      function () {

        openEmployeeModal(
          null,
          load
        );
      }
    );

    /*
     * ==========================================================
     * EDIT EMPLOYEE
     * ==========================================================
     */
    RG.on(
      ctx.page,
      "[data-edit]",
      "click",
      function (event, button) {

        API.get(
          "/employees/" +
          button.dataset.edit
        )
          .then(
            function (employee) {

              openEmployeeModal(
                employee,
                load
              );

            }
          )
          .catch(
            RG.toastErr
          );
      }
    );

    /*
     * ==========================================================
     * DEACTIVATE
     * ==========================================================
     */
    RG.on(
      ctx.page,
      "[data-deactivate]",
      "click",
      function (event, button) {

        RG.confirmAction({

          title:
            "Deactivate this employee?",

          message:
            "They won't be able to sign in. Their records, documents and payslips stay intact.",

          confirmLabel:
            "Deactivate",

          danger: true

        }).then(
          function (ok) {

            if (!ok) {
              return;
            }

            API.post(
              "/employees/" +
              button.dataset.deactivate +
              "/deactivate",
              {}
            )
              .then(
                function () {

                  RG.toastOk(
                    "Employee deactivated."
                  );

                  load();

                }
              )
              .catch(
                RG.toastErr
              );
          }
        );
      }
    );

    /*
     * ==========================================================
     * ACTIVATE
     * ==========================================================
     */
    RG.on(
      ctx.page,
      "[data-activate]",
      "click",
      function (event, button) {

        API.post(
          "/employees/" +
          button.dataset.activate +
          "/activate",
          {}
        )
          .then(
            function () {

              RG.toastOk(
                "Employee activated."
              );

              load();

            }
          )
          .catch(
            RG.toastErr
          );
      }
    );

    load();
  }

  /*
   * ============================================================
   * DETAIL PAGE
   * ============================================================
   *
   * Keep the existing employee detail functionality.
   * The important employee-form/dropdown logic above is shared
   * and is now fixed.
   */
  /*
   * ------------------------------------------------------------
   * Employee profile: attendance, leave records, monthly reports
   * (HR -> Employees -> View Employee). Data comes from the API;
   * the monthly report renderer is shared with the employee page.
   * ------------------------------------------------------------
   */
  function profileSections(employee) {
    return '<div class="grid grid-2 mt-4">' +
        '<div class="card"><div class="card-head"><h3>Profile photo &amp; ID</h3></div><div class="card-body"><dl class="kv">' +
          "<dt>Photograph</dt><dd>" + RG.badge(employee.photo_status || "Missing") +
            (employee.photo_status === "Pending" ? ' <a class="small" href="documents.html">Review in Documents</a>' : "") + "</dd>" +
          "<dt>ID status</dt><dd>" + RG.badge(employee.id_card_status || "Pending") + "</dd>" +
          "<dt>Employee ID</dt><dd>" + RG.esc(employee.unique_employee_id || "Not issued") + "</dd>" +
        "</dl></div></div>" +
        '<div class="card"><div class="card-head"><h3>Late logins</h3><span class="hint">Last 60 days</span></div>' +
          '<div id="emp-late">' + RG.skeletonRows(3) + "</div></div>" +
      "</div>" +
      '<div class="card mt-4"><div class="card-head"><h3>Attendance \u00B7 Check-In / Check-Out</h3><span class="hint">Last 14 days \u00B7 live selfie and location</span></div>' +
        '<div id="emp-att">' + RG.skeletonRows(3) + "</div></div>" +
      '<div class="card mt-4"><div class="card-head"><h3>Tasks</h3><a class="hint" href="work-monitor.html?tab=tasks">Assign in Work Monitor</a></div>' +
        '<div class="card-body" id="emp-tasks">' + RG.skeletonRows(2) + "</div></div>" +
      '<div class="card mt-4"><div class="card-head"><h3>Leave records</h3><span class="hint">All requests and HR decisions</span></div>' +
        '<div class="card-body" id="emp-leaves">' + RG.skeletonRows(3) + "</div></div>" +
      '<div class="card mt-4" id="monthly-reports"><div class="card-head"><h3>Monthly Reports</h3>' +
        '<span class="hint">Attendance, login, hours, daily reports, leave and salary per month</span></div>' +
        '<div id="emp-months">' + RG.skeletonRows(3) + "</div></div>" +
      '<div id="emp-month-view" class="mr-view hidden"></div>';
  }

  function loadProfileSections(employee) {
    var today = new Date();
    var from = new Date(today.getTime() - 60 * 86400000).toISOString().slice(0, 10);
    API.get("/attendance/hr/late-logins", { employee_id: employee.id, date_from: from }).then(function (res) {
      var host = document.getElementById("emp-late");
      var rows = res.items || [];
      if (!rows.length) { host.innerHTML = RG.emptyState("No late logins", "Nothing recorded in the last 60 days.", "", "check"); return; }
      host.innerHTML = '<div class="table-scroll"><table class="data compact"><thead><tr><th>Date</th><th>Expected</th><th>Actual</th><th>Late by</th><th>Reason</th></tr></thead><tbody>' +
        rows.map(function (r) {
          return '<tr><td data-label="Date" class="nowrap">' + RG.fmt.date(r.date) + '</td><td data-label="Expected">' + RG.fmt.time(r.expected_login) +
            '</td><td data-label="Actual">' + RG.fmt.time(r.actual_login) + '</td><td data-label="Late by"><span class="text-bad">' + RG.esc(r.late_label) +
            '</span></td><td data-label="Reason">' + RG.esc(r.late_reason || "\u2014") + "</td></tr>";
        }).join("") + "</tbody></table></div>";
    }).catch(function (err) { document.getElementById("emp-late").innerHTML = RG.errorState(err.message); });

    var from14 = new Date(today.getTime() - 14 * 86400000).toISOString().slice(0, 10);
    API.get("/attendance/sessions", { employee_id: employee.id, date_from: from14 }).then(function (res) {
      var host = document.getElementById("emp-att");
      var rows = res.items || [];
      if (!rows.length) { host.innerHTML = RG.emptyState("No check-ins yet", "Check-In / Check-Out records from the last 14 days appear here.", "", "calendar"); return; }
      var t = function (v) { return v ? RG.fmt.time(v) : "\u2014"; };
      var m = function (n) { n = Number(n || 0); return Math.floor(n / 60) + "h " + String(n % 60).padStart(2, "0") + "m"; };
      var l = function (x) { return x ? '<a href="' + RG.esc(x.map_url) + '" target="_blank" rel="noopener">' + RG.esc(x.label) + "</a>" : "\u2014"; };
      host.innerHTML = '<div class="table-scroll"><table class="data compact"><thead><tr><th>Date</th><th>Check-In</th><th>Check-In location</th><th>Check-Out</th><th>Check-Out location</th><th>Selfies</th><th>Hours</th><th>Late</th></tr></thead><tbody>' +
        rows.map(function (r) {
          return '<tr><td data-label="Date" class="nowrap">' + RG.fmt.date(r.date) + "</td>" +
            '<td data-label="Check-In">' + t(r.check_in_time) + "</td>" +
            '<td data-label="Check-In location">' + l(r.check_in_location) + "</td>" +
            '<td data-label="Check-Out">' + (r.check_out_time ? t(r.check_out_time) : RG.badge(r.date === res.items[0].date ? "Working" : "No check-out", "info")) + "</td>" +
            '<td data-label="Check-Out location">' + l(r.check_out_location) + "</td>" +
            '<td data-label="Selfies"><div class="selfie-pair">' +
              (r.check_in_selfie ? '<img class="selfie-thumb" alt="Check-In selfie" data-selfie="' + r.id + '/check-in">' : "") +
              (r.check_out_selfie ? '<img class="selfie-thumb" alt="Check-Out selfie" data-selfie="' + r.id + '/check-out">' : "") + "</div></td>" +
            '<td data-label="Hours">' + m(r.worked_minutes) + (r.extra_minutes ? ' <span class="small text-ok">+' + m(r.extra_minutes) + "</span>" : "") + "</td>" +
            '<td data-label="Late">' + (r.late_minutes ? '<span class="text-bad">' + RG.esc(r.late_label) + "</span>" : "\u2014") + "</td></tr>";
        }).join("") + "</tbody></table></div>";
      host.querySelectorAll("img[data-selfie]").forEach(function (img) {
        API.blob("/attendance/sessions/" + img.dataset.selfie.replace("/", "/selfie/")).then(function (f) { img.src = f.url; img.dataset.full = f.url; }).catch(function () { img.remove(); });
      });
      RG.on(host, "img[data-selfie]", "click", function (e, img) {
        if (img.dataset.full) RG.openModal({ title: img.alt, size: "sm", body: '<img src="' + img.dataset.full + '" alt="" style="width:100%;border-radius:12px">', footer: '<button class="btn" data-close>Close</button>' });
      });
    }).catch(function (err) { document.getElementById("emp-att").innerHTML = RG.errorState(err.message); });

    API.get("/tasks", { employee_id: employee.id, limit: 50 }).then(function (res) {
      document.getElementById("emp-tasks").innerHTML = window.RGWork
        ? window.RGWork.taskCards(res.items || [])
        : RG.emptyState("Tasks unavailable", "");
    }).catch(function (err) { document.getElementById("emp-tasks").innerHTML = RG.errorState(err.message); });

    API.get("/leave-requests", { employee_id: employee.id, page: 1, page_size: 100 }).then(function (res) {
      document.getElementById("emp-leaves").innerHTML = RG.leaveTable(res.items || [], { emptyText: "This employee has no leave requests." });
    }).catch(function (err) { document.getElementById("emp-leaves").innerHTML = RG.errorState(err.message); });

    if (window.RGMonthly) {
      window.RGMonthly.monthList(document.getElementById("emp-months"), document.getElementById("emp-month-view"), employee.id)
        .then(function () {
          if (location.hash === "#monthly-reports") {
            var el = document.getElementById("monthly-reports");
            if (el) el.scrollIntoView({ block: "start" });
          }
        });
    }
  }

  function detailPage() {

    var ctx =
      RG.boot({
        scope: "hr",
        active: "employees",
        title: "Employee details",
        subtitle: "Full record"
      });

    if (!ctx) {
      return;
    }

    var id =
      RG.param("id");

    if (!id) {

      ctx.page.innerHTML =
        RG.errorState(
          "No employee was selected."
        );

      return;
    }

    ctx.page.innerHTML =
      RG.skeletonCards(
        2
      );

    Promise.all([
      API.get(
        "/employees/" +
        id
      ),

      API.get(
        "/documents/employee/" +
        id
      ).catch(
        function () {
          return null;
        }
      ),

      API.get(
        "/salaries",
        {
          employee_id: id,
          page: 1,
          page_size: 6
        }
      ).catch(
        function () {
          return {
            items: []
          };
        }
      )
    ])
      .then(
        function (result) {

          var employee =
            result[0];

          var documents =
            result[1];

          var salaries =
            result[2].items ||
            [];

          ctx.page.innerHTML =

            '<div class="page-head">' +

            "<div>" +

            "<h1>" +

            RG.esc(
              employee.full_name
            ) +

            "</h1>" +

            '<p class="sub">' +

            RG.esc(
              employee.designation ||
              ""
            ) +

            " \u00B7 " +

            RG.esc(
              employee.department ||
              ""
            ) +

            "</p>" +

            "</div>" +

            '<div class="page-actions">' +

            '<a class="btn" href="employees.html">' +

            "Back to directory" +

            "</a>" +

            '<button class="btn btn-primary" data-edit-this>' +

            "Edit record" +

            "</button>" +

            "</div>" +

            "</div>" +

            '<div class="grid grid-2">' +

            '<div class="card">' +

            '<div class="card-head">' +

            "<h3>Personal information</h3>" +

            "</div>" +

            '<div class="card-body">' +

            '<dl class="kv">' +

            "<dt>Full name</dt>" +

            "<dd>" +

            RG.esc(
              employee.full_name
            ) +

            "</dd>" +

            "<dt>Email</dt>" +

            "<dd>" +

            RG.esc(
              employee.email
            ) +

            "</dd>" +

            "<dt>Phone</dt>" +

            "<dd>" +

            RG.esc(
              employee.phone ||
              "\u2014"
            ) +

            "</dd>" +

            "</dl>" +

            "</div>" +

            "</div>" +

            '<div class="card">' +

            '<div class="card-head">' +

            "<h3>Employment</h3>" +

            "</div>" +

            '<div class="card-body">' +

            '<dl class="kv">' +

            "<dt>Employee ID</dt>" +

            "<dd>" +

            RG.esc(
              employee.unique_employee_id ||
              employee.employee_code ||
              "\u2014"
            ) +

            "</dd>" +

            "<dt>Department</dt>" +

            "<dd>" +

            RG.esc(
              employee.department ||
              "\u2014"
            ) +

            "</dd>" +

            "<dt>Designation</dt>" +

            "<dd>" +

            RG.esc(
              employee.designation ||
              "\u2014"
            ) +

            "</dd>" +

            "<dt>Joining date</dt>" +

            "<dd>" +

            RG.fmt.date(
              employee.joining_date
            ) +

            "</dd>" +

            "<dt>Work location</dt>" +

            "<dd>" +

            RG.esc(
              employee.work_location ||
              "Company default"
            ) +

            "</dd>" +

            "<dt>Status</dt>" +

            "<dd>" +

            RG.badge(
              employee.employment_status
            ) +

            "</dd>" +

            "</dl>" +

            "</div>" +

            "</div>" +

            "</div>" +

            profileSections(employee);

          loadProfileSections(employee);

          loadLookups()
            .then(
              function () {

                RG.on(
                  ctx.page,
                  "[data-edit-this]",
                  "click",
                  function () {

                    openEmployeeModal(
                      employee,
                      function () {
                        location.reload();
                      }
                    );

                  }
                );

              }
            );

        }
      )
      .catch(
        function (err) {

          ctx.page.innerHTML =
            '<div class="card">' +
            RG.errorState(
              err.message
            ) +
            "</div>";

        }
      );
  }

  /*
   * ============================================================
   * START PAGE
   * ============================================================
   */
  if (
    PAGE ===
    "employee-details"
  ) {

    detailPage();

  } else {

    listPage();

  }

})();