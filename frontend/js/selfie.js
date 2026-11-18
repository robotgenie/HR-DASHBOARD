/* Live camera selfie capture used by employee/intern login and logout. */
(function (global) {
  "use strict";

  function capture(action) {
    return new Promise(function (resolve, reject) {
      var settled = false;
      var stream = null;
      var backdrop = document.createElement("div");
      backdrop.className = "selfie-backdrop";
      backdrop.innerHTML =
        '<div class="selfie-card" role="dialog" aria-modal="true" aria-labelledby="selfie-title">' +
          '<div class="selfie-head"><div><h3 id="selfie-title">Live selfie required</h3>' +
          '<p>Allow camera access and capture a fresh selfie to ' + (action === "logout" ? "sign out" : "sign in") + '.</p></div>' +
          '<button type="button" class="selfie-close" data-selfie-cancel aria-label="Cancel">&times;</button></div>' +
          '<div class="selfie-stage"><video autoplay playsinline muted></video><canvas hidden></canvas>' +
          '<div class="selfie-hint">Keep your face inside the frame</div></div>' +
          '<div class="selfie-error" data-selfie-error></div>' +
          '<div class="selfie-actions"><button type="button" class="btn" data-selfie-cancel>Cancel</button>' +
          '<button type="button" class="btn btn-brand" data-selfie-capture disabled>Capture Selfie</button></div>' +
        '</div>';
      document.body.appendChild(backdrop);
      document.body.style.overflow = "hidden";

      var video = backdrop.querySelector("video");
      var canvas = backdrop.querySelector("canvas");
      var captureButton = backdrop.querySelector("[data-selfie-capture]");
      var errorBox = backdrop.querySelector("[data-selfie-error]");

      function cleanup() {
        if (stream) stream.getTracks().forEach(function (track) { track.stop(); });
        backdrop.remove();
        document.body.style.overflow = "";
        document.removeEventListener("keydown", onKey);
      }
      function finish(value, error) {
        if (settled) return;
        settled = true;
        cleanup();
        if (error) reject(error); else resolve(value);
      }
      function showError(message) {
        errorBox.textContent = message || "Camera access is required.";
        errorBox.classList.add("show");
      }
      function onKey(e) { if (e.key === "Escape") finish(null, new Error("Selfie capture cancelled.")); }

      backdrop.querySelectorAll("[data-selfie-cancel]").forEach(function (button) {
        button.addEventListener("click", function () {
          finish(null, new Error("Selfie capture cancelled."));
        });
      });

      captureButton.addEventListener("click", function () {
        if (!video.videoWidth || !video.videoHeight) {
          showError("Camera is not ready yet. Please wait a moment.");
          return;
        }
        var max = 720;
        var scale = Math.min(1, max / video.videoWidth);
        canvas.width = Math.round(video.videoWidth * scale);
        canvas.height = Math.round(video.videoHeight * scale);
        var ctx = canvas.getContext("2d");
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        finish(canvas.toDataURL("image/jpeg", 0.86), null);
      });

      document.addEventListener("keydown", onKey);

      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        showError("This browser does not support camera capture. Please use a modern browser over HTTPS.");
        return;
      }

      navigator.mediaDevices.getUserMedia({
        video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false
      }).then(function (value) {
        stream = value;
        video.srcObject = stream;
        video.onloadedmetadata = function () {
          captureButton.disabled = false;
        };
      }).catch(function () {
        showError("Camera permission is required. Please allow camera access and try again.");
      });
    });
  }

  /* ------------------------------------------------------------------
     Check-In / Check-Out capture: location + live selfie, with preview,
     Retake and Confirm. Resolves { selfie_data, latitude, longitude,
     accuracy }. Nothing is sent until the person confirms.
     ------------------------------------------------------------------ */
  function esc(v) {
    return String(v == null ? "" : v).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function attendance(action, info) {
    info = info || {};
    var label = action === "check-out" ? "Check-Out" : "Check-In";
    return new Promise(function (resolve, reject) {
      var settled = false, stream = null, shot = null, loc = null, watchId = null;
      var backdrop = document.createElement("div");
      backdrop.className = "selfie-backdrop";
      backdrop.innerHTML =
        '<div class="selfie-card att-card" role="dialog" aria-modal="true" aria-labelledby="att-title">' +
          '<div class="selfie-head"><div><h3 id="att-title">' + label + ": live selfie &amp; location</h3>" +
          "<p>Your photo and location are saved with today's attendance record" +
            (info.subtitle ? " \u00B7 " + esc(info.subtitle) : "") + ".</p></div>" +
          '<button type="button" class="selfie-close" data-cancel aria-label="Cancel">&times;</button></div>' +
          '<div class="att-steps">' +
            '<div class="att-step" data-step-loc><span class="att-dot"></span><div><b>Location</b><small data-loc-text>Requesting location permission\u2026</small></div>' +
              '<button type="button" class="btn btn-sm hidden" data-loc-retry>Try again</button></div>' +
            '<div class="att-step" data-step-cam><span class="att-dot"></span><div><b>Camera</b><small data-cam-text>Starting camera\u2026</small></div></div>' +
          "</div>" +
          '<div class="selfie-stage"><video autoplay playsinline muted></video><img alt="Captured selfie" class="att-preview hidden"><canvas hidden></canvas>' +
          '<div class="selfie-hint" data-hint>Look at the camera and keep your face inside the frame</div></div>' +
          '<div class="selfie-error" data-error></div>' +
          '<div class="selfie-actions">' +
            '<button type="button" class="btn" data-cancel>Cancel</button>' +
            '<button type="button" class="btn hidden" data-retake>Retake</button>' +
            '<button type="button" class="btn btn-brand" data-capture disabled>Capture selfie</button>' +
            '<button type="button" class="btn btn-brand hidden" data-confirm disabled>Confirm ' + label + "</button>" +
          "</div>" +
        "</div>";
      document.body.appendChild(backdrop);
      document.body.style.overflow = "hidden";
      var q = function (sel) { return backdrop.querySelector(sel); };
      var video = q("video"), canvas = q("canvas"), preview = q(".att-preview");
      var errorBox = q("[data-error]");

      function showError(m) { errorBox.textContent = m; errorBox.classList.add("show"); }
      function clearError() { errorBox.classList.remove("show"); }
      function setStep(name, state, text) {
        var el = q("[data-step-" + name + "]");
        el.className = "att-step is-" + state;
        el.querySelector("small").textContent = text;
      }
      function syncConfirm() { q("[data-confirm]").disabled = !(shot && loc); }
      function cleanup() {
        if (stream) stream.getTracks().forEach(function (t) { t.stop(); });
        if (watchId !== null && navigator.geolocation) navigator.geolocation.clearWatch(watchId);
        backdrop.remove();
        document.body.style.overflow = "";
        document.removeEventListener("keydown", onKey);
      }
      function finish(value, err) {
        if (settled) return;
        settled = true; cleanup();
        if (err) reject(err); else resolve(value);
      }
      function onKey(e) { if (e.key === "Escape") finish(null, new Error("Selfie capture cancelled.")); }
      document.addEventListener("keydown", onKey);
      backdrop.querySelectorAll("[data-cancel]").forEach(function (b) {
        b.addEventListener("click", function () { finish(null, new Error("Selfie capture cancelled.")); });
      });

      /* ---- location ---- */
      function locate() {
        q("[data-loc-retry]").classList.add("hidden");
        if (!navigator.geolocation) {
          setStep("loc", "bad", "This browser can't share location. Use a phone or a browser with location support.");
          return;
        }
        setStep("loc", "wait", "Requesting location permission\u2026");
        navigator.geolocation.getCurrentPosition(function (pos) {
          loc = { latitude: pos.coords.latitude, longitude: pos.coords.longitude, accuracy: pos.coords.accuracy };
          setStep("loc", "ok", "Captured \u00B7 " + loc.latitude.toFixed(5) + ", " + loc.longitude.toFixed(5) +
            (loc.accuracy ? " (\u00B1" + Math.round(loc.accuracy) + " m)" : ""));
          syncConfirm();
        }, function (err) {
          loc = null; syncConfirm();
          var msg = err && err.code === 1
            ? "Location permission was denied. Allow location for this site in your browser settings, then tap Try again."
            : "Couldn't get your location (" + ((err && err.message) || "timeout") + "). Check that location/GPS is on, then tap Try again.";
          setStep("loc", "bad", msg);
          q("[data-loc-retry]").classList.remove("hidden");
        }, { enableHighAccuracy: true, timeout: 15000, maximumAge: 30000 });
      }
      q("[data-loc-retry]").addEventListener("click", locate);
      locate();

      /* ---- camera ---- */
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        setStep("cam", "bad", "Camera capture needs a modern browser over HTTPS (or localhost).");
      } else {
        navigator.mediaDevices.getUserMedia({ video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false })
          .then(function (value) {
            stream = value; video.srcObject = stream;
            video.onloadedmetadata = function () {
              q("[data-capture]").disabled = false;
              setStep("cam", "ok", "Camera ready");
            };
          }).catch(function (err) {
            var denied = err && (err.name === "NotAllowedError" || err.name === "SecurityError");
            setStep("cam", "bad", denied
              ? "Camera permission was denied. Allow camera access for this site in your browser settings and reopen " + label + "."
              : "No camera could be started (" + ((err && err.name) || "error") + ").");
          });
      }

      q("[data-capture]").addEventListener("click", function () {
        if (!video.videoWidth) { showError("Camera is not ready yet. Please wait a moment."); return; }
        clearError();
        var scale = Math.min(1, 720 / video.videoWidth);
        canvas.width = Math.round(video.videoWidth * scale);
        canvas.height = Math.round(video.videoHeight * scale);
        var ctx = canvas.getContext("2d");
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        shot = canvas.toDataURL("image/jpeg", 0.86);
        preview.src = shot;
        preview.classList.remove("hidden"); video.classList.add("hidden");
        q("[data-hint]").textContent = "Check the photo, then confirm or retake";
        q("[data-capture]").classList.add("hidden");
        q("[data-retake]").classList.remove("hidden");
        q("[data-confirm]").classList.remove("hidden");
        syncConfirm();
        if (!loc) showError("Waiting for your location before you can confirm.");
      });
      q("[data-retake]").addEventListener("click", function () {
        shot = null; clearError();
        preview.classList.add("hidden"); video.classList.remove("hidden");
        q("[data-hint]").textContent = "Look at the camera and keep your face inside the frame";
        q("[data-capture]").classList.remove("hidden");
        q("[data-retake]").classList.add("hidden");
        q("[data-confirm]").classList.add("hidden");
      });
      q("[data-confirm]").addEventListener("click", function () {
        if (!shot) { showError("Capture your selfie first."); return; }
        if (!loc) { showError("Your location is required. Allow location access and tap Try again."); return; }
        finish({ selfie_data: shot, latitude: loc.latitude, longitude: loc.longitude, accuracy: loc.accuracy });
      });
    });
  }

  global.RGSelfie = { capture: capture, attendance: attendance };
})(window);
