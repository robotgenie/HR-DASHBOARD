/* admin-profile.js - the Admin's own profile (not an employee profile: no
   attendance, documents or salary) and the list of Admin accounts. */
(function () {
  "use strict";
  var ctx = RG.boot({ scope: "admin", active: "profile", title: "Admin Profile", subtitle: "Your account" });
  if (!ctx) return;

  ctx.page.innerHTML = '<div class="page-head"><div><h1>Admin Profile</h1><p class="sub">The Admin is not an employee: no check-in, attendance, documents or salary. This profile is your account only.</p></div>' +
    '<div class="page-actions"><a class="btn" href="../change-password.html">Change password</a></div></div>' +
    '<div class="grid grid-2"><div class="card"><div class="card-head"><h3>Your details</h3></div><div class="card-body" id="ap-form">' + RG.skeletonRows(3) + "</div></div>" +
    '<div class="card"><div class="card-head"><h3>Admin accounts</h3><button class="btn btn-sm" data-new-admin>' + RG.icon("plus", 14) + " Add admin</button></div><div id=\"ap-admins\">" + RG.skeletonRows(2) + "</div></div></div>";

  function loadProfile() {
    API.get("/admin/profile").then(function (p) {
      document.getElementById("ap-form").innerHTML = '<div class="person-hero mb-4">' + RG.avatar({ full_name: p.full_name }, "lg") +
        '<div class="who"><h2>' + RG.esc(p.full_name) + '</h2><div class="small muted">' + RG.esc(p.title) + " · " + RG.esc(p.email) + "</div>" +
        '<div class="small muted">Last sign-in ' + RG.fmt.dateTime(p.last_login_at) + "</div></div></div>" +
        '<form class="form-grid" id="ap-edit" novalidate>' +
          '<div class="field full"><label for="ap-name">Full name</label><input id="ap-name" maxlength="160" value="' + RG.esc(p.full_name) + '"></div>' +
          '<div class="field"><label for="ap-title">Title</label><input id="ap-title" maxlength="120" value="' + RG.esc(p.title || "") + '"></div>' +
          '<div class="field"><label for="ap-phone">Phone</label><input id="ap-phone" maxlength="20" value="' + RG.esc(p.phone || "") + '"></div>' +
          '<div class="field full"><label>Email (sign-in)</label><input value="' + RG.esc(p.email) + '" disabled></div>' +
          '<div class="full"><button class="btn btn-brand" type="submit">Save</button></div></form>';
      document.getElementById("ap-edit").addEventListener("submit", function (e) {
        e.preventDefault();
        var btn = this.querySelector("button");
        RG.setBusy(btn, true, "Saving…");
        API.put("/admin/profile", { full_name: document.getElementById("ap-name").value.trim(), title: document.getElementById("ap-title").value.trim(),
          phone: document.getElementById("ap-phone").value.trim() }).then(function (p2) {
          var u = API.session.user() || {}; u.full_name = p2.full_name; u.designation = p2.title;
          API.session.save(API.session.token(), u);
          RG.toastOk("Profile saved."); loadProfile();
        }).catch(function (err) { RG.setBusy(btn, false); RG.toastErr(err); });
      });
    }).catch(function (err) { document.getElementById("ap-form").innerHTML = RG.errorState(err.message); });
  }

  function loadAdmins() {
    API.get("/admin/admins").then(function (d) {
      document.getElementById("ap-admins").innerHTML = '<ul class="mini-list">' + d.items.map(function (a) {
        return "<li>" + RG.avatar({ full_name: a.full_name }, "sm") + '<div style="min-width:0"><div class="truncate" style="font-weight:600">' + RG.esc(a.full_name) +
          '</div><div class="small muted truncate">' + RG.esc(a.email) + "</div></div><span class=\"when\">" + RG.esc(a.title) + "</span></li>";
      }).join("") + "</ul>";
    }).catch(function (err) { document.getElementById("ap-admins").innerHTML = RG.errorState(err.message); });
  }

  RG.on(ctx.page, "[data-new-admin]", "click", function () {
    var m = RG.openModal({ title: "Add an Admin", size: "md",
      body: '<p class="small muted">Admins monitor the whole organisation and do not check in. A temporary password is shown once.</p><form class="form-grid" novalidate>' +
        '<div class="field full"><label for="na-name">Full name</label><input id="na-name" maxlength="160"></div>' +
        '<div class="field full"><label for="na-email">Email</label><input id="na-email" type="email"></div>' +
        '<div class="field"><label for="na-title">Title</label><input id="na-title" value="Administrator"></div>' +
        '<div class="field"><label for="na-phone">Phone</label><input id="na-phone"></div></form>',
      footer: '<button class="btn" data-close>Cancel</button><button class="btn btn-brand" data-go>Create</button>' });
    m.foot.querySelector("[data-go]").addEventListener("click", function () {
      var btn = this; RG.setBusy(btn, true, "Creating…");
      API.post("/admin/admins", { full_name: m.body.querySelector("#na-name").value.trim(), email: m.body.querySelector("#na-email").value.trim(),
        title: m.body.querySelector("#na-title").value.trim() || null, phone: m.body.querySelector("#na-phone").value.trim() || null })
        .then(function (r) {
          m.close();
          RG.openModal({ title: "Admin created", size: "sm", body: "<p><b>" + RG.esc(r.admin.email) + "</b></p><p>Temporary password: <code>" + RG.esc(r.initial_password) +
            '</code></p><p class="small muted">Share it privately. It must be changed at first sign-in.</p>', footer: '<button class="btn" data-close>Done</button>' });
          loadAdmins();
        }).catch(function (err) { RG.setBusy(btn, false); RG.toastErr(err); });
    });
  });

  loadProfile();
  loadAdmins();
})();
