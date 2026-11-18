/* ==========================================================================
   common.js - shared shell and UI primitives for every signed-in page.
   Renders the sidebar/topbar, guards the role, and provides toasts, modals,
   formatters, status badges, pagination and loading/empty/error states.
   ========================================================================== */
(function (global) {
  "use strict";

  var APP_ROOT = (function () {
    var path = global.location.pathname;
    var marker = path.indexOf("/app/");
    if (marker >= 0) return path.slice(0, marker) + "/app";
    return path.replace(/\/(admin|hr|manager|employee|intern)\/[^/]*$/, "").replace(/\/[^/]*$/, "");
  })();

  var ICONS = {
    dashboard: '<path d="M3 3h7v7H3zM14 3h7v4h-7zM14 10h7v11h-7zM3 14h7v7H3z"/>',
    users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/>',
    doc: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/>',
    badge: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 9h4M7 13h10"/>',
    money: '<circle cx="12" cy="12" r="9"/><path d="M12 7v10M9.5 9.5h3.2a1.8 1.8 0 0 1 0 3.6H9.5h3.4a1.8 1.8 0 0 1 0 3.6H9.5"/>',
    video: '<rect x="2" y="6" width="13" height="12" rx="2"/><path d="M15 11l7-4v10l-7-4z"/>',
    clipboard: '<rect x="7" y="3" width="10" height="4" rx="1"/><path d="M9 5H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-3"/><path d="M8 12h8M8 16h5"/>',
    bell: '<path d="M18 8a6 6 0 1 0-12 0c0 7-3 8-3 8h18s-3-1-3-8"/><path d="M13.7 21a2 2 0 0 1-3.4 0"/>',
    shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
    gear: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-2.7 1.1V21a2 2 0 1 1-4 0v-.1A1.6 1.6 0 0 0 7.5 19l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1A1.6 1.6 0 0 0 3 13.6H3a2 2 0 1 1 0-4h.1A1.6 1.6 0 0 0 4.7 7L4.6 7a2 2 0 1 1 2.8-2.8l.1.1A1.6 1.6 0 0 0 10 3.4V3a2 2 0 1 1 4 0v.1a1.6 1.6 0 0 0 2.6 1.1l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0 1.1 2.7H21a2 2 0 1 1 0 4h-.1a1.6 1.6 0 0 0-1.5 1.3z"/>',
    logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="M16 17l5-5-5-5M21 12H9"/>',
    user: '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
    search: '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>',
    menu: '<path d="M3 6h18M3 12h18M3 18h18"/>',
    chevron: '<path d="M9 18l6-6-6-6"/>',
    upload: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M7 10l5-5 5 5M12 5v12"/>',
    download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M7 10l5 5 5-5M12 15V3"/>',
    check: '<path d="M20 6L9 17l-5-5"/>',
    x: '<path d="M18 6L6 18M6 6l12 12"/>',
    eye: '<path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12z"/><circle cx="12" cy="12" r="3"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    alert: '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/>',
    inbox: '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.4 5.1 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.4-6.9A2 2 0 0 0 16.8 4H7.2a2 2 0 0 0-1.8 1.1z"/>',
    trash: '<path d="M3 6h18M8 6V4h8v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6M10 11v6M14 11v6"/>',
    calendar: '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
    tree: '<rect x="9" y="2" width="6" height="5" rx="1"/><rect x="2" y="17" width="6" height="5" rx="1"/><rect x="16" y="17" width="6" height="5" rx="1"/><path d="M12 7v5M5 17v-2a3 3 0 0 1 3-3h8a3 3 0 0 1 3 3v2"/>',
    grid: '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M3 15h18M9 3v18M15 3v18"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
    pulse: '<path d="M3 12h4l3-8 4 16 3-8h4"/>',
    flag: '<path d="M4 22V4M4 4h12l-2 4 2 4H4"/>',
    book: '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20V3H6.5A2.5 2.5 0 0 0 4 5.5z"/><path d="M4 19.5A2.5 2.5 0 0 0 6.5 22H20v-5"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    layers: '<path d="M12 2 2 7l10 5 10-5z"/><path d="M2 17l10 5 10-5M2 12l10 5 10-5"/>',
    bolt: '<path d="M13 2 3 14h9l-1 8 10-12h-9z"/>',
    message: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
    down: '<path d="M6 9l6 6 6-6"/>',
    arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>'
  };

  function icon(name, size) {
    var d = ICONS[name] || ICONS.doc;
    return '<svg width="' + (size || 18) + '" height="' + (size || 18) + '" viewBox="0 0 24 24" fill="none" ' +
      'stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + d + '</svg>';
  }

  /* Employee-side self-service pages shared by HR and Managers (they are
     employees too: check-in, tasks, hourly updates, reports, leave, salary). */
  var SELF = [
    { href: "my-work.html", key: "work", label: "My Tasks & Hourly", icon: "calendar", group: "My work" },
    { href: "my-reports.html", key: "my-reports", label: "My Daily Reports & Leave", icon: "clipboard", group: "My work" },
    { href: "my-documents.html", key: "my-documents", label: "My Documents", icon: "doc", group: "My work" },
    { href: "my-salary.html", key: "my-salary", label: "My Salary Slips", icon: "money", group: "My work" },
    { href: "my-monthly-report.html", key: "monthly-report", label: "My Monthly Report", icon: "dashboard", group: "My work" }
  ];

  /* Navigation is organised around how each role works. Every entry points at
     an existing page; keys are unchanged so pages still highlight themselves.
     Groups are only labels - nothing here grants or removes access (the API
     enforces permissions). */
  var NAV = {
    admin: [
      { href: "dashboard.html", key: "dashboard", label: "Command Center", icon: "dashboard", group: "Organisation" },
      { href: "organization.html", key: "organization", label: "Organisation & Hierarchy", icon: "tree", group: "Organisation" },
      { href: "departments.html", key: "departments", label: "Departments", icon: "grid", group: "Organisation" },
      { href: "employees.html", key: "employees", label: "People Directory", icon: "users", group: "People" },
      { href: "people.html?type=Manager", key: "people-Manager", label: "Manager Monitoring", icon: "users", group: "People" },
      { href: "people.html?type=Employee", key: "people-Employee", label: "Employee Monitoring", icon: "user", group: "People" },
      { href: "people.html?type=Intern", key: "people-Intern", label: "Intern Monitoring", icon: "user", group: "People" },
      { href: "hr-monitoring.html", key: "hr-monitoring", label: "HR Monitoring", icon: "shield", group: "HR Monitoring" },
      { href: "work-monitor.html", key: "work-monitor", label: "Attendance & Hourly", icon: "clock", group: "Workforce" },
      { href: "leave-requests.html", key: "leave-requests", label: "Leave", icon: "calendar", group: "Workforce" },
      { href: "tasks.html", key: "tasks", label: "Tasks", icon: "target", group: "Workforce" },
      { href: "meetings.html", key: "meetings", label: "Meetings", icon: "video", group: "Workforce" },
      { href: "salary.html", key: "salary", label: "Salary & Slips", icon: "money", group: "Payroll" },
      { href: "uan.html", key: "uan", label: "UAN", icon: "badge", group: "Payroll" },
      { href: "payslip-requests.html", key: "payslip-requests", label: "Payslip Requests", icon: "download", group: "Payroll" },
      { href: "documents.html", key: "documents", label: "Documents", icon: "doc", group: "Documents" },
      { href: "id-approvals.html", key: "id-approvals", label: "ID Approvals", icon: "badge", group: "Documents" },
      { href: "profile-requests.html", key: "profile-requests", label: "Profile Requests", icon: "user", group: "Documents" },
      { href: "work-reports.html", key: "reports", label: "Work Reports", icon: "clipboard", group: "Reports" },
      { href: "monthly-reports.html", key: "monthly-reports", label: "Monthly Reports", icon: "dashboard", group: "Reports" },
      { href: "excel.html", key: "excel", label: "Excel Import / Export", icon: "upload", group: "Reports" },
      { href: "notifications.html", key: "notifications", label: "Notifications", icon: "bell", group: "System" },
      { href: "audit-logs.html", key: "audit", label: "Audit Logs", icon: "shield", group: "System" },
      { href: "settings.html", key: "settings", label: "Settings", icon: "gear", group: "System" },
      { href: "profile.html", key: "profile", label: "Admin Profile", icon: "user", group: "System" }
    ],
    hr: [
      { href: "dashboard.html", key: "dashboard", label: "People Ops Hub", icon: "dashboard", group: "Today" },
      { href: "notifications.html", key: "notifications", label: "Notifications", icon: "bell", group: "Today" },
      { href: "employees.html", key: "employees", label: "Employees", icon: "users", group: "People" },
      { href: "hierarchy.html", key: "organization", label: "My Hierarchy", icon: "tree", group: "People" },
      { href: "work-monitor.html", key: "work-monitor", label: "Attendance & Work", icon: "clock", group: "Attendance & Leave" },
      { href: "leave-requests.html", key: "leave-requests", label: "Leave Requests", icon: "calendar", group: "Attendance & Leave" },
      { href: "tasks.html", key: "tasks", label: "Tasks", icon: "target", group: "Attendance & Leave" },
      { href: "documents.html", key: "documents", label: "Documents", icon: "doc", group: "Documents & Identity" },
      { href: "id-approvals.html", key: "id-approvals", label: "ID Approvals", icon: "badge", group: "Documents & Identity" },
      { href: "profile-requests.html", key: "profile-requests", label: "Profile Requests", icon: "user", group: "Documents & Identity" },
      { href: "uan.html", key: "uan", label: "UAN", icon: "badge", group: "Payroll" },
      { href: "salary.html", key: "salary", label: "Salary", icon: "money", group: "Payroll" },
      { href: "payslip-requests.html", key: "payslip-requests", label: "Payslip Requests", icon: "download", group: "Payroll" },
      { href: "work-reports.html", key: "reports", label: "Work Reports", icon: "clipboard", group: "Reports" },
      { href: "monthly-reports.html", key: "monthly-reports", label: "Monthly Reports", icon: "dashboard", group: "Reports" },
      { href: "meetings.html", key: "meetings", label: "Meetings", icon: "video", group: "Reports" },
      { href: "excel.html", key: "excel", label: "Excel Import / Export", icon: "upload", group: "HR Operations" },
      { href: "audit-logs.html", key: "audit", label: "Audit Logs", icon: "shield", group: "HR Operations" },
      { href: "settings.html", key: "settings", label: "Settings", icon: "gear", group: "HR Operations" },
      { href: "profile.html", key: "profile", label: "My Profile", icon: "user", group: "My work" }
    ].concat(SELF),
    manager: [
      { href: "dashboard.html", key: "dashboard", label: "Team Desk", icon: "dashboard" },
      { href: "team.html", key: "team", label: "My Team", icon: "users", group: "My Team" },
      { href: "team-monitor.html", key: "work-monitor", label: "Team Attendance & Work", icon: "clock", group: "My Team" },
      { href: "team-tasks.html", key: "tasks", label: "Team Tasks", icon: "target", group: "My Team" },
      { href: "team-reports.html", key: "team-reports", label: "Team Reports", icon: "clipboard", group: "My Team" },
      { href: "team-leave.html", key: "leave-requests", label: "Team Leave", icon: "calendar", group: "My Team" },
      { href: "team-monthly.html", key: "monthly-reports", label: "Team Analytics (Monthly)", icon: "dashboard", group: "My Team" },
      { href: "exports.html", key: "excel", label: "Team Export", icon: "download", group: "My Team" },
      { href: "work.html", key: "work", label: "My Tasks & Hourly", icon: "calendar", group: "My Work" },
      { href: "daily-reports.html", key: "reports", label: "My Reports & Leave", icon: "clipboard", group: "My Work" },
      { href: "monthly-report.html", key: "monthly-report", label: "My Monthly Report", icon: "dashboard", group: "My Work" },
      { href: "meetings.html", key: "meetings", label: "Meetings", icon: "video", group: "My Work" },
      { href: "profile.html", key: "profile", label: "My Profile", icon: "user", group: "My Records" },
      { href: "documents.html", key: "documents", label: "My Documents", icon: "doc", group: "My Records" },
      { href: "salary-slips.html", key: "salary", label: "Salary Slips", icon: "money", group: "My Records" },
      { href: "uan.html", key: "uan", label: "UAN", icon: "badge", group: "My Records" },
      { href: "notifications.html", key: "notifications", label: "Notifications", icon: "bell", group: "My Records" },
      { href: "settings.html", key: "settings", label: "Settings", icon: "gear", group: "My Records" }
    ],
    employee: [
      { href: "dashboard.html", key: "dashboard", label: "My Day", icon: "clock" },
      { href: "work.html", key: "work", label: "My Tasks", icon: "target" },
      { href: "daily-reports.html", key: "reports", label: "My Reports & Leave", icon: "clipboard" },
      { href: "monthly-report.html", key: "monthly-report", label: "My Month", icon: "calendar" },
      { href: "meetings.html", key: "meetings", label: "Meetings", icon: "video" },
      { href: "salary-slips.html", key: "salary", label: "My Salary", icon: "money" },
      { href: "documents.html", key: "documents", label: "My Documents", icon: "doc" },
      { href: "uan.html", key: "uan", label: "UAN", icon: "badge" },
      { href: "profile.html", key: "profile", label: "Profile", icon: "user" },
      { href: "notifications.html", key: "notifications", label: "Notifications", icon: "bell" },
      { href: "settings.html", key: "settings", label: "Settings", icon: "gear" }
    ],
    intern: [
      { href: "dashboard.html", key: "dashboard", label: "My Journey", icon: "target", group: "Journey" },
      { href: "work.html", key: "work", label: "My Tasks & Hourly", icon: "calendar", group: "Learning & work" },
      { href: "daily-reports.html", key: "reports", label: "My Reports & Leave", icon: "clipboard", group: "Learning & work" },
      { href: "monthly-report.html", key: "monthly-report", label: "My Attendance & Progress", icon: "dashboard", group: "Learning & work" },
      { href: "meetings.html", key: "meetings", label: "My Sessions", icon: "video", group: "Learning & work" },
      { href: "documents.html", key: "documents", label: "My Documents", icon: "doc", group: "Records" },
      { href: "salary-slips.html", key: "salary", label: "Salary Slips", icon: "money", group: "Records" },
      { href: "uan.html", key: "uan", label: "UAN", icon: "badge", group: "Records" },
      { href: "profile.html", key: "profile", label: "My Profile", icon: "user", group: "Records" },
      { href: "notifications.html", key: "notifications", label: "Notifications", icon: "bell", group: "Records" },
      { href: "settings.html", key: "settings", label: "Settings", icon: "gear", group: "Records" }
    ]
  };

  var SCOPE_LABEL = { admin: "ADMIN", hr: "HR", manager: "MANAGER", employee: "EMPLOYEE", intern: "INTERN" };
  /* Each portal names its own workspace in the shell. */
  var WORKSPACE = {
    admin: "Organisation Command Center", hr: "People Operations Hub", manager: "Team Operating Desk",
    employee: "My Workday", intern: "Learning & Growth"
  };
  var ROLE_LABEL = { admin: "Admin", hr: "HR", manager: "Manager", employee: "Employee", intern: "Intern" };

  /* Which portal an account belongs to. The API sends "portal"; older stored
     sessions only have role + department, so derive it the same way. */
  function portalOf(user) {
    user = user || {};
    if (user.portal) return user.portal;
    if (user.role === "ADMIN") return "admin";
    if (user.role === "HR_ADMIN") return "hr";
    if (user.role === "MANAGER") return "manager";
    return String(user.department || "") === "Internship" ? "intern" : "employee";
  }
  /* Shared page scripts render either a management view (HR / Admin queues,
     a Manager's team pages: data-view="team") or the person's own view
     (employees, interns, Managers, and HR's "My work" pages: data-view="self"). */
  function mgmtView() {
    var b = document.body.dataset;
    if (b.view === "self") return false;
    if (b.view === "team") return true;
    return b.scope === "hr" || b.scope === "admin";
  }
  function homeOf(user) { return APP_ROOT + "/" + portalOf(user) + "/dashboard.html"; }
  /* Employee-side portals use Check-In / Check-Out and hourly updates. */
  function isWorkerPortal(p) { return p === "hr" || p === "manager" || p === "employee" || p === "intern"; }

  /* ---------------- formatters ---------------- */
  var MONTHS = ["January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"];

  var inr0 = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
  var inr2 = new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  /* The API stores and returns UTC timestamps without a zone marker
     ("2026-10-05T07:35:00"). Read those as UTC so they display in the
     viewer's local time; values that already carry a zone are left alone. */
  function toDate(value) {
    if (value instanceof Date) return value;
    var v = String(value);
    if (v.length === 10) return new Date(v + "T00:00:00");
    if (/T\d{2}:\d{2}/.test(v) && !/(Z|[+-]\d{2}:?\d{2})$/.test(v)) v += "Z";
    return new Date(v);
  }

  var fmt = {
    money: function (value, decimals) {
      var n = Number(value || 0);
      return "\u20B9" + (decimals ? inr2.format(n) : inr0.format(Math.round(n)));
    },
    number: function (value) { return inr0.format(Number(value || 0)); },
    percent: function (value) { return (Math.round(Number(value || 0) * 10) / 10) + "%"; },
    date: function (value) {
      if (!value) return "\u2014";
      var d = toDate(value);
      if (isNaN(d)) return value;
      return d.getDate() + " " + MONTHS[d.getMonth()].slice(0, 3) + " " + d.getFullYear();
    },
    dateLong: function (value) {
      if (!value) return "\u2014";
      var d = toDate(value);
      return isNaN(d) ? value : d.getDate() + " " + MONTHS[d.getMonth()] + " " + d.getFullYear();
    },
    dateTime: function (value) {
      if (!value) return "\u2014";
      var d = toDate(value);
      if (isNaN(d)) return value;
      return fmt.date(d) + ", " + fmt.time(d.toTimeString().slice(0, 5));
    },
    time: function (value) {
      if (!value) return "\u2014";
      var parts = String(value).split(":");
      var h = parseInt(parts[0], 10);
      var m = parts[1] || "00";
      var suffix = h >= 12 ? "PM" : "AM";
      var h12 = h % 12 === 0 ? 12 : h % 12;
      return h12 + ":" + m + " " + suffix;
    },
    ago: function (value) {
      if (!value) return "";
      var then = toDate(value);
      if (isNaN(then)) return "";
      var secs = Math.floor((Date.now() - then.getTime()) / 1000);
      if (secs < 60) return "just now";
      if (secs < 3600) return Math.floor(secs / 60) + "m ago";
      if (secs < 86400) return Math.floor(secs / 3600) + "h ago";
      if (secs < 604800) return Math.floor(secs / 86400) + "d ago";
      return fmt.date(value);
    },
    initials: function (name) {
      if (!name) return "?";
      var bits = String(name).trim().split(/\s+/);
      return ((bits[0] || "")[0] + (bits.length > 1 ? bits[bits.length - 1][0] : "")).toUpperCase();
    },
    bytes: function (size) {
      var n = Number(size || 0);
      if (n < 1024) return n + " B";
      if (n < 1048576) return (n / 1024).toFixed(0) + " KB";
      return (n / 1048576).toFixed(1) + " MB";
    },
    period: function (year, month) { return MONTHS[(month || 1) - 1] + " " + year; }
  };

  function escapeHtml(value) {
    if (value === null || value === undefined) return "";
    return String(value).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  /* ---------------- status badges ---------------- */
  var TONE = {
    "Verified": "ok", "Credited": "ok", "Active": "ok", "Reviewed": "ok", "Completed": "ok",
    "Approved": "ok", "Granted": "ok", "Pending Approval": "warn", "Superseded": "",
    "Pending": "warn", "Processing": "warn", "Under Verification": "warn", "Draft": "warn",
    "On Leave": "warn", "Scheduled": "info", "Submitted": "info",
    "Rejected": "bad", "Cancelled": "bad", "Terminated": "bad", "Resigned": "bad",
    "Re-upload Requested": "bad", "Inactive": "",
    "Missing": "", "Not Submitted": "",
    "Required": "warn", "Not Required": "", "Paid": "ok", "Unpaid": "bad",
    "Full Day Leave": "info", "Morning Half Leave": "info", "Afternoon Half Leave": "info",
    "Absent": "bad", "No Attachment": "bad", "No Attendance": "", "Upcoming": "", "Weekly Off": "", "Full Day": "ok",
    "First Half": "info", "Second Half": "info", "Not Logged In": ""
  };
  function tone(status) { return TONE[status] !== undefined ? TONE[status] : "info"; }
  function badge(status, extraClass) {
    if (!status) return '<span class="badge">\u2014</span>';
    return '<span class="badge ' + tone(status) + " " + (extraClass || "") + '">' + escapeHtml(status) + "</span>";
  }

  function avatar(employee, size) {
    var cls = "avatar" + (size ? " " + size : "");
    var name = (employee && (employee.full_name || employee.name)) || "";
    var id = employee && (employee.id || employee.employee_id);
    if (employee && employee.photo_path && id) {
      return '<span class="' + cls + '"><img alt="" loading="lazy" data-photo="' + id + '"></span>';
    }
    return '<span class="' + cls + '">' + escapeHtml(fmt.initials(name)) + "</span>";
  }

  /* Photos sit behind an authorised endpoint, so they are fetched as blobs. */
  function hydratePhotos(root) {
    (root || document).querySelectorAll("img[data-photo]").forEach(function (img) {
      if (img.dataset.loaded) return;
      img.dataset.loaded = "1";
      global.API.blob("/employees/" + img.dataset.photo + "/photo")
        .then(function (file) { img.src = file.url; })
        .catch(function () { img.remove(); });
    });
  }

  /* ---------------- toasts ---------------- */
  function toastHost() {
    var host = document.getElementById("toasts");
    if (!host) {
      host = document.createElement("div");
      host.id = "toasts";
      document.body.appendChild(host);
    }
    return host;
  }
  function toast(message, kind, title) {
    var el = document.createElement("div");
    el.className = "toast " + (kind || "");
    el.setAttribute("role", kind === "bad" ? "alert" : "status");
    el.innerHTML = '<div><div class="t-title">' + escapeHtml(title || (kind === "bad" ? "Something went wrong" : "Done")) +
      '</div><div class="t-msg">' + escapeHtml(message) + "</div></div>" +
      '<button class="t-close" aria-label="Dismiss">\u00D7</button>';
    toastHost().appendChild(el);
    var kill = function () { el.remove(); };
    el.querySelector(".t-close").addEventListener("click", kill);
    setTimeout(kill, kind === "bad" ? 7000 : 4200);
  }
  function toastOk(m, t) { toast(m, "ok", t || "Done"); }
  function toastErr(e, t) {
    toast(e && e.message ? e.message : String(e), "bad", t || "Something went wrong");
  }

  /* ---------------- modals ---------------- */
  function openModal(options) {
    var backdrop = document.createElement("div");
    backdrop.className = "modal-backdrop";
    backdrop.innerHTML =
      '<div class="modal ' + (options.size || "") + '" role="dialog" aria-modal="true">' +
        '<div class="modal-head"><h3>' + escapeHtml(options.title || "") + "</h3>" +
          '<button class="icon-btn" data-close aria-label="Close">' + icon("x", 16) + "</button></div>" +
        '<div class="modal-body">' + (options.body || "") + "</div>" +
        (options.footer === null ? "" : '<div class="modal-foot">' + (options.footer || "") + "</div>") +
      "</div>";
    document.body.appendChild(backdrop);
    document.body.style.overflow = "hidden";

    function close() {
      backdrop.remove();
      document.body.style.overflow = "";
      document.removeEventListener("keydown", onKey);
      if (options.onClose) options.onClose();
    }
    function onKey(e) { if (e.key === "Escape") close(); }
    document.addEventListener("keydown", onKey);
    backdrop.addEventListener("click", function (e) {
      if (e.target === backdrop || e.target.closest("[data-close]")) close();
    });
    var api = { el: backdrop, root: backdrop.querySelector(".modal"), close: close,
      body: backdrop.querySelector(".modal-body"), foot: backdrop.querySelector(".modal-foot") };
    if (options.onOpen) options.onOpen(api);
    var focusable = backdrop.querySelector("input, textarea, select, button:not([data-close])");
    if (focusable) focusable.focus();
    return api;
  }

  function confirmAction(options) {
    return new Promise(function (resolve) {
      var decided = false;
      var modal = openModal({
        title: options.title || "Are you sure?",
        size: "sm",
        body: '<p class="mb-0">' + escapeHtml(options.message || "") + "</p>" +
          (options.note ? '<p class="small muted mt-2 mb-0">' + escapeHtml(options.note) + "</p>" : ""),
        footer: '<button class="btn" data-close>Cancel</button>' +
          '<button class="btn ' + (options.danger ? "btn-danger" : "btn-primary") + '" data-go>' +
          escapeHtml(options.confirmLabel || "Confirm") + "</button>",
        onClose: function () { if (!decided) resolve(false); }
      });
      modal.foot.querySelector("[data-go]").addEventListener("click", function () {
        decided = true; modal.close(); resolve(true);
      });
    });
  }

  /* ---------------- loading / empty / error ---------------- */
  function skeletonRows(count, cols) {
    var html = "";
    for (var i = 0; i < (count || 5); i++) html += '<div class="skeleton sk-row"></div>';
    return '<div class="card-body">' + html + "</div>";
  }
  function skeletonCards(count) {
    var html = "";
    for (var i = 0; i < (count || 3); i++) html += '<div class="skeleton sk-card"></div>';
    return '<div class="grid grid-3">' + html + "</div>";
  }
  function emptyState(title, message, actionHtml, iconName) {
    return '<div class="state"><div class="state-icon">' + icon(iconName || "inbox", 22) + "</div>" +
      "<h4>" + escapeHtml(title) + "</h4><p class=\"mb-0\">" + escapeHtml(message || "") + "</p>" +
      (actionHtml || "") + "</div>";
  }
  function errorState(message, retryId) {
    return '<div class="state error"><div class="state-icon">' + icon("alert", 22) + "</div>" +
      "<h4>Couldn't load this</h4><p class=\"mb-0\">" + escapeHtml(message || "Please try again.") + "</p>" +
      (retryId ? '<button class="btn btn-sm" id="' + retryId + '">Try again</button>' : "") + "</div>";
  }

  /* ---------------- pagination ---------------- */
  function renderPager(host, meta, onGo) {
    if (!host) return;
    if (!meta || !meta.total) { host.innerHTML = ""; return; }
    var from = (meta.page - 1) * meta.page_size + 1;
    var to = Math.min(meta.page * meta.page_size, meta.total);
    var buttons = "";
    var pages = meta.pages || 1;
    var start = Math.max(1, meta.page - 2);
    var end = Math.min(pages, start + 4);
    if (end - start < 4) start = Math.max(1, end - 4);
    buttons += '<button data-page="' + (meta.page - 1) + '"' + (meta.page <= 1 ? " disabled" : "") + '>Prev</button>';
    for (var p = start; p <= end; p++) {
      buttons += '<button data-page="' + p + '" class="' + (p === meta.page ? "current" : "") + '">' + p + "</button>";
    }
    buttons += '<button data-page="' + (meta.page + 1) + '"' + (meta.page >= pages ? " disabled" : "") + ">Next</button>";
    host.innerHTML = '<span class="info">Showing ' + from + "\u2013" + to + " of " + meta.total + "</span>" +
      '<span class="pages">' + buttons + "</span>";
    host.querySelectorAll("button[data-page]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var target = parseInt(btn.dataset.page, 10);
        if (target >= 1 && target <= pages && target !== meta.page) onGo(target);
      });
    });
  }

  /* ---------------- shell ---------------- */
  function renderShell(config) {
    var user = global.API.session.user() || {};
    var scope = config.scope;
    var items = NAV[scope];
    var base = APP_ROOT + "/" + scope + "/";

    var lastGroup = null;
    var navHtml = items.map(function (item) {
      var active = item.key === config.active ? " active" : "";
      var head = "";
      if (item.group && item.group !== lastGroup) {
        head = '<li class="nav-group" aria-hidden="true"><span class="label">' + escapeHtml(item.group) + "</span></li>";
      }
      lastGroup = item.group || lastGroup;
      return head + '<li><a href="' + base + item.href + '" class="' + active.trim() + '">' +
        icon(item.icon) + '<span class="label">' + item.label + "</span>" +
        (item.key === "notifications" ? '<span class="count hidden" data-unread></span>' : "") +
        "</a></li>";
    }).join("");

    // Dark shells (Admin console, Manager drawer) use the white-text logo;
    // the light shells use the dark-text one.
    var darkShell = scope === "admin" || scope === "manager";
    var logo = darkShell ? "rocket-genie-logo.png" : "rocket-genie-logo-dark.png";

    // Manager: a horizontal desk navigation on wide screens (the sidebar stays
    // as the drawer on tablets and phones, so nothing becomes unreachable).
    var topnav = "";
    if (scope === "manager") {
      var groups = [], byGroup = {};
      items.forEach(function (item) {
        var g = item.group || "";
        if (!byGroup[g]) { byGroup[g] = []; groups.push(g); }
        byGroup[g].push(item);
      });
      topnav = '<nav class="topnav" aria-label="Desk navigation"><ul>' + groups.map(function (g, gi) {
        var list = byGroup[g];
        if (!g) {
          return list.map(function (item) {
            return '<li><a class="tn-link' + (item.key === config.active ? " active" : "") + '" href="' + base + item.href + '"' +
              (item.key === config.active ? ' aria-current="page"' : "") + ">" + icon(item.icon, 16) + "<span>" + item.label + "</span></a></li>";
          }).join("");
        }
        var hasActive = list.some(function (i) { return i.key === config.active; });
        return '<li class="tn-group"><button type="button" class="tn-link' + (hasActive ? " active" : "") + '" aria-expanded="false" aria-haspopup="true" data-tn="' + gi + '">' +
            escapeHtml(g) + icon("down", 14) + "</button>" +
          '<ul class="tn-menu" role="menu" data-tn-menu="' + gi + '">' + list.map(function (item) {
            return '<li role="none"><a role="menuitem" href="' + base + item.href + '"' + (item.key === config.active ? ' class="active" aria-current="page"' : "") + ">" +
              icon(item.icon, 16) + "<span>" + item.label + "</span>" +
              (item.key === "notifications" ? '<span class="count hidden" data-unread></span>' : "") + "</a></li>";
          }).join("") + "</ul></li>";
      }).join("") + "</ul></nav>";
    }

    var shell =
      '<aside class="sidebar" aria-label="Main navigation">' +
        '<div class="sidebar-brand">' +
          '<img class="full" src="' + APP_ROOT + "/assets/logo/" + logo + '" alt="Rocket Genie">' +
          '<img class="mark" src="' + APP_ROOT + '/assets/logo/rocket-genie-mark.png" alt="Rocket Genie">' +
        "</div>" +
        '<div class="sidebar-scope"><span class="ws-role">' + (SCOPE_LABEL[scope] || "EMPLOYEE") + "</span>" +
          '<span class="ws-name">' + escapeHtml(WORKSPACE[scope] || "") + "</span></div>" +
        '<ul class="nav">' + navHtml + "</ul>" +
        '<div class="sidebar-foot">' +
          '<div class="sidebar-user">' + avatar({ full_name: user.full_name, photo_path: user.photo_path, id: user.employee_id }, "sm") +
            '<div class="who"><b class="truncate">' + escapeHtml(user.full_name || user.email || "") + "</b>" +
            "<span>" + escapeHtml(user.designation || ROLE_LABEL[scope] || "Employee") + "</span></div>" +
          "</div>" +
          '<button class="btn btn-sm logout-btn" data-logout>' + icon("logout", 16) +
            '<span class="label">Log out</span></button>' +
        "</div>" +
      "</aside>" +
      '<div class="sidebar-scrim" data-drawer-close></div>' +
      '<div class="workspace">' +
        '<header class="topbar">' +
          '<button class="icon-btn hamburger" data-drawer aria-label="Open menu">' + icon("menu", 18) + "</button>" +
          (scope === "manager"
            ? '<a class="tb-brand" href="' + base + 'dashboard.html"><img src="' + APP_ROOT + '/assets/logo/rocket-genie-logo.png" alt="Rocket Genie"></a>'
            : "") +
          '<div class="crumb">' + escapeHtml(config.title || "") +
            (config.subtitle ? "<small>" + escapeHtml(config.subtitle) + "</small>" : "") + "</div>" +
          topnav +
          '<div class="spacer"></div>' +
          '<button class="palette-btn" type="button" data-palette aria-label="Jump to (Ctrl+K)">' + icon("search", 15) +
            '<span>Jump to…</span><kbd>Ctrl K</kbd></button>' +
          (scope === "admin" || scope === "employee"
            ? '<span class="tb-clock" data-clock aria-live="off"></span>' : "") +
          '<button class="icon-btn" data-collapse aria-label="Collapse sidebar">' + icon("chevron", 16) + "</button>" +
          '<div class="notif-anchor">' +
            '<button class="icon-btn" data-bell aria-label="Notifications">' + icon("bell", 18) +
              '<span class="dot hidden" data-unread></span></button>' +
          "</div>" +
           (scope === "manager"

            ? '\<button class="manager-logout" type="button" data-manager-logout aria-label="Log out">' +

                icon("logout", 18) +

                '\<span>Log out\</span>' +

              '\</button>'

            : "") +
        "</header>" +
        '<main class="page" id="page"></main>' +
      "</div>";

    document.body.innerHTML = shell + '<div id="toasts"></div>';
    document.body.classList.add("role-" + scope);

    // Live clock (Admin console and the employee's workday).
    var clock = document.querySelector("[data-clock]");
    if (clock) {
      var tick = function () {
        var d = new Date();
        clock.textContent = d.toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" }) +
          "  ·  " + d.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" });
      };
      tick();
      setInterval(tick, 30000);
    }

    // Manager desk navigation: click / keyboard dropdowns.
    var tn = document.querySelector(".topnav");
    if (tn) {
      var closeAll = function (except) {
        tn.querySelectorAll("[data-tn]").forEach(function (b) {
          if (b === except) return;
          b.setAttribute("aria-expanded", "false");
          b.parentNode.classList.remove("open");
        });
      };
      tn.querySelectorAll("[data-tn]").forEach(function (btn) {
        btn.addEventListener("click", function (e) {
          e.stopPropagation();
          var open = btn.getAttribute("aria-expanded") === "true";
          closeAll(btn);
          btn.setAttribute("aria-expanded", open ? "false" : "true");
          btn.parentNode.classList.toggle("open", !open);
          if (!open) { var first = btn.parentNode.querySelector(".tn-menu a"); if (first) first.focus(); }
        });
      });
      tn.addEventListener("keydown", function (e) {
        if (e.key === "Escape") {
          var openBtn = tn.querySelector('[data-tn][aria-expanded="true"]');
          closeAll();
          if (openBtn) openBtn.focus();
        }
        if (e.key === "ArrowDown" || e.key === "ArrowUp") {
          var menu = e.target.closest(".tn-menu");
          if (!menu) return;
          e.preventDefault();
          var links = Array.prototype.slice.call(menu.querySelectorAll("a"));
          var i = links.indexOf(e.target);
          links[(i + (e.key === "ArrowDown" ? 1 : -1) + links.length) % links.length].focus();
        }
      });
      document.addEventListener("click", function (e) { if (!e.target.closest(".topnav")) closeAll(); });
    }

    // Sidebar collapse preference survives navigation.
    try {
      if (localStorage.getItem("rg_sidebar") === "collapsed") document.body.classList.add("sidebar-collapsed");
    } catch (e) { /* ignore */ }

    document.querySelector("[data-collapse]").addEventListener("click", function () {
      document.body.classList.toggle("sidebar-collapsed");
      try {
        localStorage.setItem("rg_sidebar",
          document.body.classList.contains("sidebar-collapsed") ? "collapsed" : "open");
      } catch (e) { /* ignore */ }
    });
    document.querySelector("[data-drawer]").addEventListener("click", function () {
      document.body.classList.toggle("drawer-open");
    });
    document.querySelector("[data-drawer-close]").addEventListener("click", function () {
      document.body.classList.remove("drawer-open");
    });
    // document.querySelector("[data-logout]").addEventListener("click", function () {
    //   startLogout(scope);
    // });
    var logoutButton = document.querySelector("[data-logout]");

    if (logoutButton) {

      logoutButton.addEventListener("click", function () {

        startLogout(scope);

      });

    }

    var managerLogoutButton = document.querySelector("[data-manager-logout]");

    if (managerLogoutButton) {

      managerLogoutButton.addEventListener("click", function () {

        startLogout(scope);

      });

    }



    document.querySelector("[data-bell]").addEventListener("click", toggleBell);
    document.querySelector("[data-palette]").addEventListener("click", function () { openPalette(); });

    // Full-bleed workspaces (Admin control room): the navigation becomes an
    // overlay drawer at every width, so the canvas can use the whole screen.
    if (config.shell === "overlay") document.body.classList.add("shell-overlay");

    PALETTE.base = items.map(function (item) {
      return { label: item.label, hint: item.group || WORKSPACE[scope] || "", href: base + item.href, icon: item.icon, kind: "Go to" };
    });
    document.addEventListener("keydown", function (e) {
      if ((e.ctrlKey || e.metaKey) && (e.key === "k" || e.key === "K")) { e.preventDefault(); openPalette(); }
    });

    hydratePhotos(document);
    refreshUnread();
    return user;
  }

  /* ---------------- command palette (Ctrl / Cmd + K) ----------------
     Jump to any page of the portal, or to records a page registers
     (people, departments). Navigation only - it performs no actions. */
  var PALETTE = { base: [], extra: [] };
  function registerCommands(list) { PALETTE.extra = PALETTE.extra.concat(list || []); }
  function openPalette(prefill) {
    if (document.querySelector(".palette-backdrop")) return;
    var opener = document.activeElement;
    var all = PALETTE.base.concat(PALETTE.extra);
    var wrap = document.createElement("div");
    wrap.className = "palette-backdrop";
    wrap.innerHTML = '<div class="palette" role="dialog" aria-modal="true" aria-label="Jump to">' +
      '<div class="pl-input">' + icon("search", 18) + '<input type="text" placeholder="Jump to a page, person or department…" aria-label="Search" autocomplete="off" role="combobox" aria-expanded="true" aria-controls="pl-list">' +
      "<kbd>Esc</kbd></div>" +
      '<ul class="pl-list" id="pl-list" role="listbox"></ul>' +
      '<div class="pl-foot"><span><kbd>↑</kbd><kbd>↓</kbd> move</span><span><kbd>Enter</kbd> open</span><span><kbd>Ctrl</kbd>+<kbd>K</kbd> anywhere</span></div></div>';
    document.body.appendChild(wrap);
    var input = wrap.querySelector("input"), list = wrap.querySelector(".pl-list"), sel = 0, shown = [];
    function render() {
      var q = input.value.trim().toLowerCase();
      shown = all.filter(function (c) { return !q || (c.label + " " + (c.hint || "") + " " + (c.kind || "")).toLowerCase().indexOf(q) >= 0; }).slice(0, 40);
      if (sel >= shown.length) sel = 0;
      list.innerHTML = shown.length ? shown.map(function (c, i) {
        return '<li role="option" id="pl-' + i + '" aria-selected="' + (i === sel) + '" data-i="' + i + '">' + icon(c.icon || "chevron", 16) +
          '<span class="pl-l">' + escapeHtml(c.label) + "</span>" + (c.hint ? '<span class="pl-h">' + escapeHtml(c.hint) + "</span>" : "") +
          '<span class="pl-k">' + escapeHtml(c.kind || "") + "</span></li>";
      }).join("") : '<li class="pl-empty">No matches</li>';
      input.setAttribute("aria-activedescendant", shown.length ? "pl-" + sel : "");
      var cur = list.querySelector('[aria-selected="true"]');
      if (cur && cur.scrollIntoView) cur.scrollIntoView({ block: "nearest" });
    }
    function close() { wrap.remove(); if (opener && opener.focus) opener.focus(); }
    function go(i) { var c = shown[i]; if (!c) return; close(); global.location.href = c.href; }
    input.addEventListener("input", function () { sel = 0; render(); });
    input.addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown") { e.preventDefault(); sel = Math.min(shown.length - 1, sel + 1); render(); }
      else if (e.key === "ArrowUp") { e.preventDefault(); sel = Math.max(0, sel - 1); render(); }
      else if (e.key === "Enter") { e.preventDefault(); go(sel); }
      else if (e.key === "Escape") { close(); }
    });
    list.addEventListener("click", function (e) { var li = e.target.closest("[data-i]"); if (li) go(Number(li.dataset.i)); });
    wrap.addEventListener("click", function (e) { if (e.target === wrap) close(); });
    if (prefill) input.value = prefill;
    render();
    input.focus();
  }

  /* ---------------- notifications bell ---------------- */
  function setUnread(count) {
    document.querySelectorAll("[data-unread]").forEach(function (el) {
      if (count > 0) {
        el.textContent = count > 99 ? "99+" : String(count);
        el.classList.remove("hidden");
      } else {
        el.classList.add("hidden");
      }
    });
  }
  function refreshUnread() {
    return global.API.get("/notifications/unread-count")
      .then(function (data) { setUnread(data.unread_count); return data.unread_count; })
      .catch(function () { /* the bell is not worth an error toast */ });
  }

  function toggleBell() {
    var open = document.querySelector(".notif-panel");
    if (open) { open.remove(); return; }
    var anchor = document.querySelector(".notif-anchor");
    var panel = document.createElement("div");
    panel.className = "notif-panel";
    panel.innerHTML = '<div class="np-head"><b>Notifications</b>' +
      '<button class="btn btn-sm btn-ghost" data-readall>Mark all read</button></div>' +
      '<div class="np-body"><div class="card-body">' +
      '<div class="skeleton sk-line"></div><div class="skeleton sk-line"></div></div></div>' +
      '<div class="np-foot"><a href="' + APP_ROOT + "/" + portalOf(global.API.session.user()) +
      '/notifications.html">Open notification centre</a></div>';
    anchor.appendChild(panel);

    function closeOutside(e) {
      if (!panel.contains(e.target) && !e.target.closest("[data-bell]")) {
        panel.remove();
        document.removeEventListener("click", closeOutside);
      }
    }
    setTimeout(function () { document.addEventListener("click", closeOutside); }, 0);

    panel.querySelector("[data-readall]").addEventListener("click", function () {
      global.API.post("/notifications/read-all", {})
        .then(function () { setUnread(0); toggleBell(); toggleBell(); })
        .catch(toastErr);
    });

    global.API.get("/notifications", { page: 1, page_size: 8 }).then(function (data) {
      var body = panel.querySelector(".np-body");
      if (!data.items.length) {
        body.innerHTML = emptyState("Nothing yet", "Notifications about documents, salary and meetings land here.");
        return;
      }
      body.innerHTML = '<ul class="notif-list">' + data.items.map(notificationRow).join("") + "</ul>";
      wireNotificationRows(body);
    }).catch(function (err) {
      panel.querySelector(".np-body").innerHTML = errorState(err.message);
    });
  }

  var NOTIF_TONE = {
    "Salary Credited": "ok", "Salary Slip Available": "ok", "Document Verified": "ok", "UAN Verified": "ok",
    "Document Rejected": "bad", "UAN Rejected": "bad", "Re-upload Requested": "warn",
    "Meeting Reminder": "info", "Daily Report Reminder": "warn", "HR Announcement": "info"
  };
  function notificationRow(item) {
    var t = NOTIF_TONE[item.type] || "info";
    var glyph = t === "ok" ? "check" : (t === "bad" ? "alert" : "bell");
    return '<li class="notif ' + (item.is_read ? "" : "unread") + '" data-id="' + item.id + '">' +
      '<span class="n-icon ' + t + '">' + icon(glyph, 16) + "</span>" +
      '<div class="n-main"><b>' + escapeHtml(item.title) + "</b><p>" + escapeHtml(item.message) + "</p></div>" +
      '<div class="col" style="align-items:flex-end;gap:4px">' +
        '<span class="n-when">' + fmt.ago(item.created_at) + "</span>" +
        (item.is_read
          ? '<button class="n-mark n-del" data-del="' + item.id + '" title="Delete notification">' + icon("trash", 13) + " Delete</button>"
          : '<button class="n-mark" data-read="' + item.id + '">Mark read</button>') +
      "</div></li>";
  }
  function deleteButton(id) {
    var b = document.createElement("button");
    b.className = "n-mark n-del";
    b.dataset.del = id;
    b.title = "Delete notification";
    b.innerHTML = icon("trash", 13) + " Delete";
    return b;
  }
  function wireDelete(btn, onChange) {
    btn.addEventListener("click", function () {
      btn.disabled = true;
      global.API.del("/notifications/" + btn.dataset.del).then(function () {
        var li = btn.closest(".notif");
        var list = li && li.parentNode;
        if (li) li.remove();
        if (list && !list.children.length && list.parentNode) {
          list.parentNode.innerHTML = emptyState("No notifications", "You're all caught up.", "", "bell");
        }
        refreshUnread();
        if (onChange) onChange("deleted");
      }).catch(function (err) { btn.disabled = false; toastErr(err); });
    });
  }
  function wireNotificationRows(root, onChange) {
    root.querySelectorAll("[data-read]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        global.API.post("/notifications/" + btn.dataset.read + "/read", {}).then(function () {
          var li = btn.closest(".notif");
          li.classList.remove("unread");
          var del = deleteButton(btn.dataset.read);
          btn.replaceWith(del);
          wireDelete(del, onChange);
          refreshUnread();
          if (onChange) onChange("read");
        }).catch(toastErr);
      });
    });
    root.querySelectorAll("[data-del]").forEach(function (btn) { wireDelete(btn, onChange); });
  }

  /* ---------------- logout ----------------
     Plain sign-out. The daily-report gate now applies to Check-Out (work.js). */
  function doLogout(scope) {
    return global.API.post("/auth/logout", {}).then(function () {
      global.API.session.clear();
      global.location.replace(global.API.loginUrl());
    }).catch(function (err) {
      global.API.session.clear();
      global.location.replace(global.API.loginUrl());
    });
  }

  function startLogout(scope) {
    if (!isWorkerPortal(scope)) {
      confirmAction({ title: "Log out?", message: "You'll need to sign in again.", confirmLabel: "Log out" })
        .then(function (ok) { if (ok) doLogout(scope); });
      return;
    }
    // Logging out only ends the portal session. Attendance is closed with
    // Check-Out on the dashboard, so remind the person if they are still in.
    global.API.get("/attendance/status").catch(function () { return null; }).then(function (st) {
      var still = st && st.state === "checked_in";
      confirmAction({
        title: "Log out?",
        message: still ? "You are still checked in. Logging out does not check you out — use Check-Out on your dashboard when your day ends."
                       : "You'll need to sign in again.",
        confirmLabel: "Log out"
      }).then(function (ok) { if (ok) doLogout(scope); });
    });
  }

  /* ---------------- leave (shared by employee, intern and HR pages) ---------------- */
  var LEAVE_TYPE_LABEL = { "Other": "Other Leave" };
  function leaveTypeLabel(value) { return LEAVE_TYPE_LABEL[value] || value; }
  function leaveDates(r) {
    return r.from_date === r.to_date ? fmt.date(r.from_date) : fmt.date(r.from_date) + " \u2013 " + fmt.date(r.to_date);
  }
  function leaveDuration(r) {
    var d = Number(r.duration_days || 0);
    return d === 0.5 ? "Half day" : (d + (d === 1 ? " day" : " days"));
  }
  function leaveTable(rows, opts) {
    opts = opts || {};
    if (!rows.length) return emptyState("No leave records", opts.emptyText || "Leave requests will appear here.", "", "calendar");
    return '<div class="table-scroll"><table class="data"><thead><tr>' +
      (opts.showEmployee ? "<th>Employee</th>" : "") +
      "<th>Leave type</th><th>Date</th><th>Period</th><th>Duration</th><th>Status</th><th>Paid</th><th>Reason</th><th>HR decision</th>" +
      "</tr></thead><tbody>" + rows.map(function (r) {
        return "<tr>" +
          (opts.showEmployee ? '<td data-label="Employee">' + escapeHtml(r.employee_name || "") + "</td>" : "") +
          '<td data-label="Leave type"><b>' + escapeHtml(r.leave_type_label || leaveTypeLabel(r.leave_type)) + "</b></td>" +
          '<td data-label="Date" class="nowrap">' + leaveDates(r) + "</td>" +
          '<td data-label="Period">' + escapeHtml(r.leave_period_label || r.leave_period || "Full Day") + "</td>" +
          '<td data-label="Duration">' + leaveDuration(r) + "</td>" +
          '<td data-label="Status">' + badge(r.status) + "</td>" +
          '<td data-label="Paid">' + (r.is_paid === false ? badge("Unpaid", "bad") : badge("Paid", "ok")) + "</td>" +
          '<td data-label="Reason"><div class="truncate" style="max-width:240px" title="' + escapeHtml(r.reason || "") + '">' + escapeHtml(r.reason || "\u2014") + "</div></td>" +
          '<td data-label="Decision">' + (r.reviewed_at
            ? '<span class="small">' + escapeHtml(r.status) + " on " + fmt.date(r.reviewed_at) +
              (r.reviewed_by_name ? " by " + escapeHtml(r.reviewed_by_name) : "") + "</span>" +
              (r.hr_remarks ? '<div class="small muted">' + escapeHtml(r.hr_remarks) + "</div>" : "")
            : '<span class="small muted">' + escapeHtml(stageText(r)) + "</span>") +
            (r.manager_status && r.manager_status !== r.status ? '<div class="small muted">Manager: ' + escapeHtml(r.manager_status) + "</div>" : "") +
          "</td>" +
          "</tr>";
      }).join("") + "</tbody></table></div>";
  }

  var STAGE_TEXT = { "Manager": "Awaiting reporting manager", "HR": "Awaiting HR", "Admin": "Awaiting Admin", "Closed": "Closed" };
  function stageText(r) { return STAGE_TEXT[r.approval_stage] || "Awaiting HR"; }

  function leaveModal(onDone, defaultDate) {
    var now = new Date();
    var today = defaultDate || (now.getFullYear() + "-" + String(now.getMonth() + 1).padStart(2, "0") + "-" + String(now.getDate()).padStart(2, "0"));
    var modal = openModal({
      title: "Request Leave", size: "md",
      body: '<form class="form-grid" id="leave-form" novalidate>' +
        '<div class="field full"><label for="leave-type">Leave type</label><select id="leave-type">' +
          ["Casual Leave", "Sick Leave", "Earned Leave", "Unpaid Leave", "Other", "Half Day Leave"].map(function (t) {
            return '<option value="' + t + '">' + leaveTypeLabel(t) + "</option>";
          }).join("") + "</select></div>" +
        '<div class="field full" data-period-wrap><label>Leave period</label>' +
          '<div class="period-pick">' +
            '<label class="period-opt"><input type="radio" name="leave-period" value="Full Day" checked><span><b>Full Day</b><small>10:00 AM \u2013 6:00 PM</small></span></label>' +
            '<label class="period-opt"><input type="radio" name="leave-period" value="Morning Half"><span><b>Morning Half</b><small>10:00 AM \u2013 1:00 PM \u00B7 EOD required</small></span></label>' +
            '<label class="period-opt"><input type="radio" name="leave-period" value="Afternoon Half"><span><b>Afternoon Half</b><small>1:00 PM \u2013 6:00 PM \u00B7 Noon required</small></span></label>' +
          "</div></div>" +
        '<div class="field"><label for="leave-from">From date</label><input id="leave-from" type="date" value="' + escapeHtml(today) + '"></div>' +
        '<div class="field" data-to-wrap><label for="leave-to">To date</label><input id="leave-to" type="date" value="' + escapeHtml(today) + '"></div>' +
        '<div class="field full"><label for="leave-reason">Reason</label><textarea id="leave-reason" rows="4" maxlength="3000"></textarea></div>' +
        '<p class="small muted full mb-0" data-leave-hint></p>' +
        "</form>",
      footer: '<button class="btn" data-close>Cancel</button><button class="btn btn-brand" data-submit-leave>Submit Request</button>'
    });
    var body = modal.body;
    var typeEl = body.querySelector("#leave-type");
    var fromEl = body.querySelector("#leave-from");
    var toEl = body.querySelector("#leave-to");
    var hint = body.querySelector("[data-leave-hint]");
    function period() { var c = body.querySelector("input[name=leave-period]:checked"); return c ? c.value : "Full Day"; }
    function sync() {
      var halfType = typeEl.value === "Half Day Leave";
      var fullOpt = body.querySelector("input[value='Full Day']");
      fullOpt.disabled = halfType;
      fullOpt.closest(".period-opt").classList.toggle("disabled", halfType);
      if (halfType && period() === "Full Day") body.querySelector("input[value='Morning Half']").checked = true;
      var half = period() !== "Full Day";
      body.querySelector("[data-to-wrap]").style.display = half ? "none" : "";
      if (half) toEl.value = fromEl.value;
      hint.textContent = {
        "Full Day": "Full Day leave: Noon and EOD reports are not required on approved dates.",
        "Morning Half": "Morning Half (10:00 AM \u2013 1:00 PM): you work 1:00 PM \u2013 6:00 PM. Noon Report not required, EOD Report required.",
        "Afternoon Half": "Afternoon Half (1:00 PM \u2013 6:00 PM): you work 10:00 AM \u2013 1:00 PM. Noon Report required, EOD Report not required."
      }[period()];
    }
    typeEl.addEventListener("change", sync);
    fromEl.addEventListener("change", sync);
    body.querySelectorAll("input[name=leave-period]").forEach(function (r) { r.addEventListener("change", sync); });
    sync();
    modal.foot.querySelector("[data-submit-leave]").addEventListener("click", function () {
      var from = fromEl.value, to = period() === "Full Day" ? toEl.value : fromEl.value;
      var reason = body.querySelector("#leave-reason").value.trim();
      if (!from || !to || reason.length < 3) { toastErr({ message: "Select the date(s) and enter a reason." }); return; }
      if (from > to) { toastErr({ message: "From date cannot be after To date." }); return; }
      var b = this;
      setBusy(b, true, "Submitting\u2026");
      global.API.post("/leave-requests", {
        leave_type: typeEl.value, leave_period: period(), from_date: from, to_date: to, reason: reason
      }).then(function () {
        modal.close();
        toastOk("Leave request sent for approval.");
        if (onDone) onDone();
      }).catch(function (err) { setBusy(b, false); toastErr(err); });
    });
    return modal;
  }

  /* ---------------- page boot ---------------- */
  function boot(config) {
    var session = global.API.session;
    if (!session.token()) {
      global.location.replace(global.API.loginUrl());
      return null;
    }
    var user = session.user() || {};
    var portal = portalOf(user);
    var bodyScope = document.body.dataset.scope || config.scope;
    config = Object.assign({}, config);
    // The folder a page lives in (body data-scope) decides the shell. Shared
    // scripts are reused across portals: HR screens in the Admin console and
    // the Manager team pages, employee screens for HR and Managers.
    config.scope = bodyScope;
    if (document.body.dataset.active) config.active = document.body.dataset.active;
    if (document.body.dataset.title) config.title = document.body.dataset.title;
    // Each portal is for exactly one kind of account; anyone else goes home.
    var wanted = config.scope;
    var allowed = wanted === portal;
    if (!allowed) {
      global.location.replace(homeOf(user));
      return null;
    }
    document.title = (config.title ? config.title + " \u00B7 " : "") + "Rocket Genie HRMS";
    renderShell(config);
    // Confirm the token against the server so a revoked account can't linger,
    // and move the person if their role changed since they signed in.
    global.API.get("/auth/me").then(function (me) {
      session.save(session.token(), me);
      if (portalOf(me) !== portal) global.location.replace(homeOf(me));
    }).catch(function () { /* api.js already handles 401 */ });
    return { user: user, page: document.getElementById("page"), scope: config.scope, portal: portal };
  }

  /* Small helpers page scripts lean on */
  function el(html) {
    var wrap = document.createElement("div");
    wrap.innerHTML = html.trim();
    return wrap.firstElementChild;
  }
  function on(root, selector, event, handler) {
    (root || document).addEventListener(event, function (e) {
      var hit = e.target.closest(selector);
      if (hit && (root || document).contains(hit)) handler(e, hit);
    });
  }
  function debounce(fn, wait) {
    var timer;
    return function () {
      var args = arguments, self = this;
      clearTimeout(timer);
      timer = setTimeout(function () { fn.apply(self, args); }, wait || 320);
    };
  }
  function param(name) {
    return new URLSearchParams(global.location.search).get(name);
  }
  function optionList(rows, valueKey, labelKey, selected) {
    return rows.map(function (row) {
      return '<option value="' + row[valueKey] + '"' +
        (String(selected) === String(row[valueKey]) ? " selected" : "") + ">" +
        escapeHtml(row[labelKey]) + "</option>";
    }).join("");
  }
  function setBusy(button, busy, busyLabel) {
    if (!button) return;
    if (busy) {
      button.dataset.label = button.innerHTML;
      button.disabled = true;
      button.classList.add("is-loading");
      button.innerHTML = escapeHtml(busyLabel || "Working\u2026");
    } else {
      button.disabled = false;
      button.classList.remove("is-loading");
      if (button.dataset.label) button.innerHTML = button.dataset.label;
    }
  }

  global.RG = {
    APP_ROOT: APP_ROOT, NAV: NAV, MONTHS: MONTHS,
    portalOf: portalOf, homeOf: homeOf, mgmtView: mgmtView, isWorkerPortal: isWorkerPortal, stageText: stageText,
    icon: icon, fmt: fmt, esc: escapeHtml, badge: badge, tone: tone, avatar: avatar,
    hydratePhotos: hydratePhotos,
    toast: toast, toastOk: toastOk, toastErr: toastErr,
    openModal: openModal, confirmAction: confirmAction,
    skeletonRows: skeletonRows, skeletonCards: skeletonCards,
    emptyState: emptyState, errorState: errorState,
    renderPager: renderPager, refreshUnread: refreshUnread,
    notificationRow: notificationRow, wireNotificationRows: wireNotificationRows,
    boot: boot, doLogout: doLogout, openPalette: openPalette, registerCommands: registerCommands,
    leaveModal: leaveModal, leaveTable: leaveTable, leaveTypeLabel: leaveTypeLabel,
    el: el, on: on, debounce: debounce, param: param, optionList: optionList, setBusy: setBusy
  };
})(window);
