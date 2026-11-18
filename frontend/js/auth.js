/* ==========================================================================
   auth.js - login, forgot password, reset password, change password.
   One file drives all four pages; each page marks itself with data-auth.
   ========================================================================== */
(function (global) {
  "use strict";

  var API = global.API;
  var page = document.body.getAttribute("data-auth");

  function appRoot() {
    var path = global.location.pathname;
    var marker = path.indexOf("/app/");
    return marker >= 0 ? path.slice(0, marker) + "/app" : path.replace(/\/[^/]*$/, "");
  }

  /* One login for every role; the API says which portal the account uses. */
  function portalOf(user) {
    user = user || {};
    if (user.portal) return user.portal;
    if (user.role === "ADMIN") return "admin";
    if (user.role === "HR_ADMIN") return "hr";
    if (user.role === "MANAGER") return "manager";
    return user.department === "Internship" ? "intern" : "employee";
  }
  function homeOf(user) { return "/" + portalOf(user) + "/dashboard.html"; }

  function alertBox(message, kind) {
    var box = document.getElementById("auth-alert");
    if (!box) return;
    box.textContent = message;
    box.className = "auth-alert show" + (kind === "ok" ? " ok" : "");
  }
  function clearAlert() {
    var box = document.getElementById("auth-alert");
    if (box) box.className = "auth-alert";
  }
  function busy(button, isBusy, label) {
    if (!button) return;
    if (isBusy) {
      button.dataset.text = button.textContent;
      button.disabled = true;
      button.textContent = label || "Please wait\u2026";
    } else {
      button.disabled = false;
      if (button.dataset.text) button.textContent = button.dataset.text;
    }
  }

  function strengthMeter(input, meter) {
    if (!input || !meter) return;
    input.addEventListener("input", function () {
      var value = input.value;
      var score = 0;
      if (value.length >= 8) score++;
      if (/[A-Z]/.test(value) && /[a-z]/.test(value)) score++;
      if (/\d/.test(value)) score++;
      if (/[^A-Za-z0-9]/.test(value) && value.length >= 12) score++;
      meter.querySelectorAll("i").forEach(function (bar, index) {
        bar.className = index < score ? (score <= 2 ? "mid" : "on") : "";
      });
    });
  }

  /* ---------------- login ---------------- */
  function initLogin() {
    if (API.session.token()) {
      // Already signed in - send them straight to the right dashboard.
      var user = API.session.user() || {};
      global.location.replace(appRoot() + homeOf(user));
      return;
    }
    if (new URLSearchParams(global.location.search).get("expired")) {
      alertBox("Your session expired. Please sign in again.");
    }
    var form = document.getElementById("login-form");
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      clearAlert();
      var button = form.querySelector('button[type="submit"]');
      var email = document.getElementById("email").value.trim();
      var password = document.getElementById("password").value;
      if (!email || !password) { alertBox("Enter your email and password."); return; }

      // Normal sign-in for every role. Attendance (late-login reason, live
      // selfie and location) is recorded later by Check-In on the dashboard.
      busy(button, true, "Signing in\u2026");
      API.postAnon("/auth/login", { email: email, password: password }).then(function (data) {
        API.session.save(data.access_token, data.user);
        if (data.must_change_password) {
          global.location.replace(appRoot() + "/change-password.html?first=1");
          return;
        }
        var portal = portalOf(data.user);
        if (data.onboarding_required && (portal === "employee" || portal === "intern" || portal === "manager")) {
          global.location.replace(appRoot() + "/" + portal + "/documents.html");
          return;
        }
        global.location.replace(appRoot() + data.home);
      }).catch(function (err) {
        busy(button, false);
        alertBox(err.status === 401 ? "That email and password don't match an account." : (err.message || "Sign in failed."));
      });
    });

    document.querySelectorAll("[data-fill]").forEach(function (chip) {
      chip.addEventListener("click", function () {
        document.getElementById("email").value = chip.dataset.fill;
        document.getElementById("password").value = chip.dataset.pw || "";
        document.getElementById("password").focus();
      });
    });
  }

  /* ---------------- forgot password ---------------- */
  function initForgot() {
    var form = document.getElementById("forgot-form");
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      clearAlert();
      var button = form.querySelector('button[type="submit"]');
      busy(button, true, "Sending\u2026");
      API.postAnon("/auth/forgot-password", { email: document.getElementById("email").value.trim() })
        .then(function (data) {
          busy(button, false);
          form.reset();
          alertBox(data && data.message
            ? data.message
            : "If that email belongs to an account, a reset link is on its way.", "ok");
        })
        .catch(function (err) { busy(button, false); alertBox(err.message); });
    });
  }

  /* ---------------- reset password ---------------- */
  function initReset() {
    var token = new URLSearchParams(global.location.search).get("token") || "";
    var form = document.getElementById("reset-form");
    var tokenField = document.getElementById("token");
    if (token) {
      tokenField.value = token;
      tokenField.closest(".field").classList.add("hidden");
    }
    strengthMeter(document.getElementById("new_password"), document.getElementById("pw-meter"));

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      clearAlert();
      var button = form.querySelector('button[type="submit"]');
      var password = document.getElementById("new_password").value;
      if (password !== document.getElementById("confirm_password").value) {
        alertBox("The two passwords don't match."); return;
      }
      busy(button, true, "Updating\u2026");
      API.postAnon("/auth/reset-password", { token: tokenField.value.trim(), new_password: password })
        .then(function () {
          alertBox("Password updated. Redirecting to sign in\u2026", "ok");
          setTimeout(function () { global.location.replace(appRoot() + "/login.html"); }, 1400);
        })
        .catch(function (err) { busy(button, false); alertBox(err.message); });
    });
  }

  /* ---------------- change password ---------------- */
  function initChange() {
    if (!API.session.token()) { global.location.replace(appRoot() + "/login.html"); return; }
    var first = new URLSearchParams(global.location.search).get("first");
    if (first) {
      alertBox("This is a temporary password. Choose your own to continue.", "ok");
    }
    var user = API.session.user() || {};
    var back = document.getElementById("back-link");
    if (back) {
      back.href = appRoot() + "/" + portalOf(user) + "/settings.html";
      if (first) back.classList.add("hidden");
    }
    strengthMeter(document.getElementById("new_password"), document.getElementById("pw-meter"));

    var form = document.getElementById("change-form");
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      clearAlert();
      var button = form.querySelector('button[type="submit"]');
      var next = document.getElementById("new_password").value;
      if (next !== document.getElementById("confirm_password").value) {
        alertBox("The two new passwords don't match."); return;
      }
      busy(button, true, "Updating\u2026");
      API.post("/auth/change-password", {
        current_password: document.getElementById("current_password").value,
        new_password: next
      }).then(function () {
        alertBox("Password changed. Taking you to your dashboard\u2026", "ok");
        setTimeout(function () {
          global.location.replace(appRoot() + homeOf(user));
        }, 1200);
      }).catch(function (err) { busy(button, false); alertBox(err.message); });
    });
  }

  var routes = { login: initLogin, forgot: initForgot, reset: initReset, change: initChange };
  if (routes[page]) routes[page]();
})(window);
