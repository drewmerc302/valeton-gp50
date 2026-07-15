"use strict";
/*
 * env_check.js — warn when the browser can't run the app's device features.
 *
 * WebMIDI needs Chrome/Edge AND a secure context (https or localhost). On Safari/
 * Firefox, or an http:// URL, connecting to the pedal silently fails — so show a
 * clear, dismissible modal instead of a broken-looking page. Browsing/converting
 * still work, so the modal never blocks; it just sets expectations.
 *
 * Self-contained (no deps), theme-aware via the app's CSS vars with fallbacks.
 * Test the modal without a second browser: ?envtest=browser or ?envtest=insecure.
 */
(function () {
  const q = (() => { try { return new URLSearchParams(location.search); } catch { return new Map(); } })();
  const forced = q.get && q.get("envtest");

  const hasMIDI = typeof navigator.requestMIDIAccess === "function" && forced !== "browser";
  const isLocal = ["localhost", "127.0.0.1", "[::1]", "::1"].includes(location.hostname);
  const insecure = (!window.isSecureContext && !isLocal) || forced === "insecure";

  if (hasMIDI && !insecure) return; // supported + secure — nothing to warn

  const CSS = `
    #env-check .ec-backdrop { position: fixed; inset: 0; background: rgba(0,0,0,.55); z-index: 9998; }
    #env-check .ec-card { position: fixed; z-index: 9999; left: 50%; top: 50%; transform: translate(-50%,-50%);
      width: min(92vw, 30rem); background: var(--card, #fff); color: var(--text, #16181d);
      border: 1px solid var(--border, #e2e4e8); border-radius: 14px; padding: 1.4rem 1.5rem;
      box-shadow: 0 18px 50px rgba(0,0,0,.35); font: 15px/1.5 system-ui, sans-serif; }
    #env-check h2 { font-size: 1.15rem; margin: 0 0 .5rem; }
    #env-check p { margin: .4rem 0; }
    #env-check .ec-sub { color: var(--muted, #6b7280); font-size: .9rem; }
    #env-check code { background: var(--code-bg, #eef); padding: 0 .3em; border-radius: 3px; }
    #env-check .ec-actions { display: flex; gap: .6rem; justify-content: flex-end; margin-top: 1.1rem; flex-wrap: wrap; }
    #env-check .ec-btn { font: inherit; font-weight: 600; padding: .5rem 1rem; border-radius: 8px;
      border: 1px solid var(--border, #cbd0d6); background: transparent; color: var(--text, #16181d); cursor: pointer; }
    #env-check .ec-primary { background: var(--accent, #2f9e8f); border-color: var(--accent, #2f9e8f); color: #fff; }`;

  const insecureBody = `
    <h2>Open the secure (https) link</h2>
    <p>This page is on <code>http://</code>, where browsers block WebMIDI — so it can't talk to your pedal.</p>
    <p>Use the <b>https://</b> address instead.</p>`;
  const browserBody = `
    <h2>Chrome or Edge needed to connect</h2>
    <p>This browser doesn't support <b>WebMIDI</b>, so connecting to the pedal — <b>Connect</b>, <b>Live edit</b>, <b>Write</b> — won't work here.</p>
    <p>Use desktop <b>Google Chrome</b> or <b>Microsoft Edge</b>.</p>
    <p class="ec-sub">You can still browse and convert presets in this browser.</p>`;

  function show() {
    if (document.getElementById("env-check")) return;
    const style = document.createElement("style");
    style.textContent = CSS;
    document.head.appendChild(style);
    const wrap = document.createElement("div");
    wrap.id = "env-check";
    wrap.innerHTML = `
      <div class="ec-backdrop"></div>
      <div class="ec-card" role="dialog" aria-modal="true" aria-label="Compatibility notice">
        ${insecure ? insecureBody : browserBody}
        <div class="ec-actions">
          ${insecure ? '<button class="ec-btn ec-primary" data-act="https">Switch to https</button>' : ""}
          <button class="ec-btn" data-act="dismiss">${insecure ? "Stay on http" : "Continue anyway"}</button>
        </div>
      </div>`;
    document.body.appendChild(wrap);
    const close = () => wrap.remove();
    wrap.querySelector('[data-act="dismiss"]').addEventListener("click", close);
    wrap.querySelector(".ec-backdrop").addEventListener("click", close);
    const https = wrap.querySelector('[data-act="https"]');
    if (https) https.addEventListener("click", () => { location.protocol = "https:"; });
  }

  if (document.body) show();
  else document.addEventListener("DOMContentLoaded", show);
})();
