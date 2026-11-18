/* ==========================================================================
   api.js - the only place that talks to FastAPI.
   Every request carries the JWT; a 401 sends the person back to the login page.
   ========================================================================== */
(function (global) {
  "use strict";

  // The frontend is normally served by FastAPI itself at /app/. When it is
  // hosted separately (Live Server, nginx) set RG_API_BASE in localStorage.
  function resolveBase() {
    var override = null;
    try { override = localStorage.getItem("rg_api_base"); } catch (e) { /* private mode */ }
    if (override) return override.replace(/\/$/, "");
    var path = global.location.pathname;
    var marker = path.indexOf("/app/");
    if (marker >= 0) return global.location.origin + path.slice(0, marker) + "/api";
    if (global.location.protocol === "file:") return "http://localhost:8000/api";
    return global.location.origin + "/api";
  }

  var TOKEN_KEY = "rg_token";
  var USER_KEY = "rg_user";

  var store = {
    get: function (k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set: function (k, v) { try { localStorage.setItem(k, v); } catch (e) { /* ignore */ } },
    del: function (k) { try { localStorage.removeItem(k); } catch (e) { /* ignore */ } }
  };

  var session = {
    token: function () { return store.get(TOKEN_KEY); },
    user: function () {
      var raw = store.get(USER_KEY);
      if (!raw) return null;
      try { return JSON.parse(raw); } catch (e) { return null; }
    },
    save: function (token, user) {
      store.set(TOKEN_KEY, token);
      store.set(USER_KEY, JSON.stringify(user || {}));
    },
    clear: function () { store.del(TOKEN_KEY); store.del(USER_KEY); },
    isHr: function () { var u = session.user(); return !!u && (u.role === "HR_ADMIN" || u.role === "ADMIN"); },
    isAdmin: function () { var u = session.user(); return !!u && u.role === "ADMIN"; }
  };

  function ApiError(message, status, body) {
    this.name = "ApiError";
    this.message = message;
    this.status = status;
    this.body = body || null;
  }
  ApiError.prototype = Object.create(Error.prototype);

  function qs(params) {
    if (!params) return "";
    var parts = [];
    Object.keys(params).forEach(function (k) {
      var v = params[k];
      if (v === null || v === undefined || v === "" || v === "all") return;
      parts.push(encodeURIComponent(k) + "=" + encodeURIComponent(v));
    });
    return parts.length ? "?" + parts.join("&") : "";
  }

  function loginUrl() {
    var path = global.location.pathname;
    var marker = path.indexOf("/app/");
    var root = marker >= 0 ? path.slice(0, marker) + "/app" : "";
    return root + "/login.html";
  }

  function onUnauthorised() {
    session.clear();
    var here = global.location.pathname;
    if (here.indexOf("login.html") === -1) {
      global.location.replace(loginUrl() + "?expired=1");
    }
  }

  function readError(res, payload) {
    if (payload && typeof payload === "object") {
      if (typeof payload.detail === "string") return payload.detail;
      if (Array.isArray(payload.detail) && payload.detail.length) {
        return payload.detail[0].msg || "That request wasn't valid.";
      }
    }
    if (res.status === 403) return "You don't have access to this.";
    if (res.status === 404) return "That wasn't found.";
    if (res.status === 413) return "That file is too large.";
    if (res.status >= 500) return "The server hit an error. Try again.";
    return "Request failed (" + res.status + ").";
  }

  function request(method, path, options) {
    options = options || {};
    var headers = {};
    var token = session.token();
    if (token && !options.anonymous) headers.Authorization = "Bearer " + token;

    var body;
    if (options.form) {
      body = options.form;               // FormData - browser sets the boundary
    } else if (options.json !== undefined) {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(options.json);
    }

    var url = resolveBase() + path + qs(options.query);

    return fetch(url, { method: method, headers: headers, body: body })
      .then(function (res) {
        if (res.status === 401 && !options.anonymous) {
          onUnauthorised();
          throw new ApiError("Your session has expired. Sign in again.", 401, null);
        }
        if (res.status === 204) return null;
        var type = res.headers.get("content-type") || "";
        var parse = type.indexOf("application/json") >= 0 ? res.json() : res.text();
        return parse.then(function (payload) {
          if (!res.ok) throw new ApiError(readError(res, payload), res.status, payload);
          return payload;
        });
      }, function (networkError) {
        throw new ApiError("Can't reach the server. Check your connection.", 0, String(networkError));
      });
  }

  /* Authenticated file fetch. Uploaded documents and payslips are never public
     URLs, so they are pulled with the token and turned into a blob URL. */
  function fetchBlob(path) {
    var headers = {};
    var token = session.token();
    if (token) headers.Authorization = "Bearer " + token;
    return fetch(resolveBase() + path, { headers: headers }).then(function (res) {
      if (res.status === 401) { onUnauthorised(); throw new ApiError("Session expired.", 401); }
      if (!res.ok) {
        return res.json().catch(function () { return null; }).then(function (payload) {
          throw new ApiError(readError(res, payload), res.status, payload);
        });
      }
      var name = "download";
      var disp = res.headers.get("content-disposition") || "";
      var match = /filename="?([^";]+)"?/.exec(disp);
      if (match) name = match[1];
      return res.blob().then(function (blob) {
        return { blob: blob, url: URL.createObjectURL(blob), filename: name, type: blob.type };
      });
    });
  }

  function download(path, fallbackName) {
    return fetchBlob(path).then(function (file) {
      var a = document.createElement("a");
      a.href = file.url;
      a.download = file.filename || fallbackName || "download";
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(function () { URL.revokeObjectURL(file.url); }, 4000);
      return file;
    });
  }

  global.API = {
    base: resolveBase,
    session: session,
    ApiError: ApiError,
    get: function (p, query) { return request("GET", p, { query: query }); },
    post: function (p, json, query) { return request("POST", p, { json: json, query: query }); },
    put: function (p, json) { return request("PUT", p, { json: json }); },
    patch: function (p, json) { return request("PATCH", p, { json: json }); },
    del: function (p) { return request("DELETE", p); },
    postAnon: function (p, json) { return request("POST", p, { json: json, anonymous: true }); },
    upload: function (p, formData) { return request("POST", p, { form: formData }); },
    blob: fetchBlob,
    download: download,
    loginUrl: loginUrl
  };
})(window);
