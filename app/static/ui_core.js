"use strict";
/*
 * UI — the page-agnostic core shared by every page (Preset Explorer, Device
 * Inspector). One implementation of the app's UI primitives and slot
 * semantics; explorer.js and device_a.js/device_core.js are its adapters.
 *
 *   .toast(msg, kind)                  transient notification ('ok' | 'err')
 *   .confirmDialog(msg, okLabel)       Promise<bool> modal (Enter/Esc aware)
 *   .promptDialog(msg, def, okLabel)   Promise<string|null> text-input modal
 *   .jget(url) / .jpost(url, body) / .jdel(url)   fetch + error unwrapping
 *   .downloadResponse(resp, fallback)  content-disposition -> browser download
 *   .USER_IR_BASE / .isUserIrSlot(slot)   User IR slot threshold (0x0A10xxxx)
 *   .isEmptyName(name)                 empty-slot sentinel (factory "GP-50")
 */
(() => {
  const USER_IR_BASE = 0x100000; // CAB fxlow >= this => a User IR slot

  const isUserIrSlot = (slot) => slot >= USER_IR_BASE;

  // Factory default presets are all named "GP-50" — treated as empty slots.
  const isEmptyName = (name) => (name || "").trim().toUpperCase() === "GP-50";

  // --- fetch helpers ---------------------------------------------------------
  async function _unwrap(r) {
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.detail || data.error || `HTTP ${r.status}`);
    return data;
  }
  const jget = (url) => fetch(url).then(_unwrap);
  const jpost = (url, body) =>
    fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    }).then(_unwrap);
  const jdel = (url) => fetch(url, { method: "DELETE" }).then(_unwrap);

  // Download a fetch Response as a file (content-disposition names it).
  async function downloadResponse(r, fallbackName) {
    const disp = r.headers.get("content-disposition") || "";
    const m = disp.match(/filename="(.+?)"/);
    const url = URL.createObjectURL(await r.blob());
    const a = document.createElement("a");
    a.href = url;
    a.download = m ? m[1] : fallbackName || "download";
    a.click();
    URL.revokeObjectURL(url);
    return a.download;
  }

  // --- toast + modals (elements created on first use) -------------------------
  let uiRoot;
  function ensureUi() {
    if (uiRoot) return;
    uiRoot = document.createElement("div");
    uiRoot.innerHTML = `
      <div id="ui-toast" class="dc-toast" hidden></div>
      <div id="ui-confirm" class="modal-overlay" hidden>
        <div class="modal-card">
          <p id="ui-confirm-msg" class="modal-msg"></p>
          <div class="modal-actions">
            <button type="button" id="ui-confirm-cancel" class="modal-btn">Cancel</button>
            <button type="button" id="ui-confirm-ok" class="modal-btn primary">Confirm</button>
          </div>
        </div>
      </div>`;
    document.body.appendChild(uiRoot);
  }

  let toastTimer;
  function toast(msg, kind) {
    ensureUi();
    const el = document.getElementById("ui-toast");
    el.textContent = msg;
    el.className = "dc-toast" + (kind ? ` dc-toast-${kind}` : "");
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      el.hidden = true;
    }, 4200);
  }

  // Shared machinery for the confirm/prompt modals: wires ok/cancel/backdrop/
  // Enter/Esc, resolves once, and tears its listeners down.
  function _modal({ message, okLabel, input }) {
    ensureUi();
    return new Promise((resolve) => {
      const ov = document.getElementById("ui-confirm");
      const ok = document.getElementById("ui-confirm-ok");
      const cancel = document.getElementById("ui-confirm-cancel");
      document.getElementById("ui-confirm-msg").textContent = message;
      ok.textContent = okLabel;
      if (input) {
        const card = ov.querySelector(".modal-card");
        card.insertBefore(input, card.querySelector(".modal-actions"));
      }
      ov.hidden = false;
      (input || ok).focus();
      if (input) input.select();
      const done = (v) => {
        ov.hidden = true;
        if (input) input.remove();
        ok.removeEventListener("click", onOk);
        cancel.removeEventListener("click", onCancel);
        ov.removeEventListener("click", onBackdrop);
        document.removeEventListener("keydown", onKey);
        resolve(v);
      };
      const confirmVal = () => (input ? input.value.trim() || null : true);
      const cancelVal = input ? null : false;
      const onOk = () => done(confirmVal());
      const onCancel = () => done(cancelVal);
      const onBackdrop = (e) => {
        if (e.target === ov) done(cancelVal);
      };
      const onKey = (e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          done(confirmVal());
        } else if (e.key === "Escape") {
          e.preventDefault();
          done(cancelVal);
        }
      };
      ok.addEventListener("click", onOk);
      cancel.addEventListener("click", onCancel);
      ov.addEventListener("click", onBackdrop);
      document.addEventListener("keydown", onKey);
    });
  }

  const confirmDialog = (message, okLabel = "Confirm") =>
    _modal({ message, okLabel });

  function promptDialog(message, defaultValue = "", okLabel = "Save") {
    const input = document.createElement("input");
    input.type = "text";
    input.className = "modal-input";
    input.value = defaultValue;
    return _modal({ message, okLabel, input });
  }

  window.UI = {
    USER_IR_BASE,
    isUserIrSlot,
    isEmptyName,
    jget,
    jpost,
    jdel,
    downloadResponse,
    toast,
    confirmDialog,
    promptDialog,
  };
})();
