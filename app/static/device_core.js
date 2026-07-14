"use strict";
/*
 * DeviceCore — shared engine for the Device Inspector layouts.
 *
 * One data + workflow layer that every layout variant (registry-first / two-pane /
 * build-forward) consumes, so the correctness-critical parts — device reads, the
 * build-from-capture flow, and the device WRITE — live in exactly one place.
 *
 * Public surface: window.DeviceCore
 *   .state            {snaptones, userIrs, factoryCabs, patches, templates, loaded}
 *   .load()           fetch inventory + templates, classify assets
 *   .usagePatches(kind, slot) / .usageCount(kind, slot)   (kind = 'snaptone' | 'ir')
 *   .emptySlots() / .isEmpty(slot)      default "GP-50" presets = safe to overwrite
 *   .slotName(slot)
 *   .sync()           re-read SnapTone catalog from the pedal
 *   .createTemplate(name, sourceSlot) / .deleteTemplate(id)
 *   .openBuildModal({snaptoneSlot?, templateId?})   the shared build UI → device write
 *   .confirmDialog(msg, okLabel) / .toast(msg, kind)
 *   .on(evt, cb)      'change' fires after any mutation (sync/build/template CRUD)
 */
(() => {
  const API = "/api/device";
  const USER_IR_BASE = 0x100000;

  const listeners = {};
  function emit(evt) {
    (listeners[evt] || []).forEach((cb) => {
      try { cb(); } catch (e) { console.error(e); }
    });
  }

  const state = {
    snaptones: [], userIrs: [], factoryCabs: [], patches: [], templates: [],
    loaded: false, source: "",
  };

  const isUserIr = (it) => it.is_user_ir || it.slot >= USER_IR_BASE;

  async function jget(path) {
    const r = await fetch(API + path);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  }
  async function jpost(path, body) {
    const r = await fetch(API + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.detail || data.error || `HTTP ${r.status}`);
    return data;
  }

  async function load() {
    const inv = await jget("/inventory");
    state.snaptones = inv.snaptones || [];
    state.userIrs = (inv.irs || []).filter(isUserIr);
    state.factoryCabs = (inv.irs || []).filter((it) => !isUserIr(it));
    state.patches = inv.patches || [];
    state.source = inv.source || "";
    try {
      state.templates = (await jget("/templates")).templates || [];
    } catch { state.templates = []; }
    state.loaded = true;
    emit("change");
  }

  function usagePatches(kind, slot) {
    return state.patches.filter((p) =>
      kind === "ir"
        ? p.ir_slot === slot && !p.uses_snaptone
        : p.snaptone_slot === slot
    );
  }
  const usageCount = (kind, slot) => usagePatches(kind, slot).length;

  // Default factory presets are all named "GP-50" — treated as empty/safe targets.
  const isEmpty = (slot) => {
    const p = state.patches.find((x) => x.slot === slot);
    return !!p && (p.name || "").trim().toUpperCase() === "GP-50";
  };
  const emptySlots = () => state.patches.filter((p) => isEmpty(p.slot));
  const slotName = (slot) => {
    const p = state.patches.find((x) => x.slot === slot);
    return p ? p.name : `#${slot}`;
  };
  function irLabel(it) {
    return isUserIr(it) ? `User IR ${it.slot - USER_IR_BASE + 1}` : it.name;
  }

  async function sync() {
    const r = await jpost("/sync", {});
    if (r.ok) await load();
    return r;
  }
  async function createTemplate(name, sourceSlot) {
    const t = await jpost("/templates/from-patch", { name, source_slot: sourceSlot });
    await load();
    return t;
  }
  async function deleteTemplate(id) {
    const r = await fetch(`${API}/templates/${id}`, { method: "DELETE" });
    await load();
    return r.ok;
  }

  // Build + write to the device (confirm handled by the caller). Reloads on success.
  async function buildWrite(templateId, snaptoneSlot, targetSlot) {
    const r = await jpost("/build", {
      template_id: templateId,
      snaptone_slot: snaptoneSlot,
      target_slot: targetSlot,
      confirm: true,
    });
    if (r.ok) await load();
    return r;
  }

  // ---- shared UI: toast + confirm modal + build modal -----------------------
  let uiRoot;
  function ensureUi() {
    if (uiRoot) return;
    uiRoot = document.createElement("div");
    uiRoot.innerHTML = `
      <div id="dc-toast" class="dc-toast" hidden></div>
      <div id="dc-confirm" class="modal-overlay" hidden>
        <div class="modal-card">
          <p id="dc-confirm-msg" class="modal-msg"></p>
          <div class="modal-actions">
            <button type="button" id="dc-confirm-cancel" class="modal-btn">Cancel</button>
            <button type="button" id="dc-confirm-ok" class="modal-btn primary">Confirm</button>
          </div>
        </div>
      </div>
      <div id="dc-usage" class="modal-overlay" hidden>
        <div class="modal-card build-card">
          <h2 id="dc-usage-title" class="build-title"></h2>
          <p id="dc-usage-sub" class="build-sub"></p>
          <ul id="dc-usage-list" class="dep-list"></ul>
          <div class="modal-actions build-actions">
            <button type="button" id="dc-usage-close" class="modal-btn">Close</button>
            <button type="button" id="dc-usage-build" class="modal-btn primary" hidden>Build a patch from this capture</button>
          </div>
        </div>
      </div>
      <div id="dc-build" class="modal-overlay" hidden>
        <div class="modal-card build-card">
          <h2 class="build-title">Build a patch from a capture</h2>
          <p class="build-sub">Wrap a saved template's effects around a SnapTone, then write it to a preset slot on your pedal.</p>
          <label class="build-field"><span>Template <small>(the effects wrapper)</small></span>
            <select id="dc-build-template"></select></label>
          <label class="build-field"><span>SnapTone <small>(the captured tone)</small></span>
            <select id="dc-build-snaptone"></select></label>
          <label class="build-field"><span>Write to slot</span>
            <select id="dc-build-slot"></select></label>
          <p id="dc-build-warn" class="build-warn" hidden></p>
          <div class="modal-actions build-actions">
            <button type="button" id="dc-build-cancel" class="modal-btn">Cancel</button>
            <button type="button" id="dc-build-download" class="modal-btn">Download .prst</button>
            <button type="button" id="dc-build-write" class="modal-btn primary">Write to device</button>
          </div>
        </div>
      </div>`;
    document.body.appendChild(uiRoot);
  }

  let toastTimer;
  function toast(msg, kind) {
    ensureUi();
    const el = document.getElementById("dc-toast");
    el.textContent = msg;
    el.className = "dc-toast" + (kind ? ` dc-toast-${kind}` : "");
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { el.hidden = true; }, 4200);
  }

  function confirmDialog(message, okLabel = "Confirm") {
    ensureUi();
    return new Promise((resolve) => {
      const ov = document.getElementById("dc-confirm");
      const ok = document.getElementById("dc-confirm-ok");
      const cancel = document.getElementById("dc-confirm-cancel");
      document.getElementById("dc-confirm-msg").textContent = message;
      ok.textContent = okLabel;
      ov.hidden = false;
      ok.focus();
      const done = (v) => {
        ov.hidden = true;
        ok.removeEventListener("click", onOk);
        cancel.removeEventListener("click", onCancel);
        ov.removeEventListener("click", onBackdrop);
        resolve(v);
      };
      const onOk = () => done(true);
      const onCancel = () => done(false);
      const onBackdrop = (e) => { if (e.target === ov) done(false); };
      ok.addEventListener("click", onOk);
      cancel.addEventListener("click", onCancel);
      ov.addEventListener("click", onBackdrop);
    });
  }

  function templateChainText(t) {
    const chain = (t.summary && t.summary.chain) || [];
    return chain.map((b) => b.model || b.block).join(" · ") || "(no active blocks)";
  }

  function fillSlotPicker(sel) {
    sel.innerHTML = "";
    const opt = (slot, label) => {
      const o = document.createElement("option");
      o.value = String(slot);
      o.textContent = label;
      sel.appendChild(o);
    };
    const empties = emptySlots();
    if (empties.length) {
      const g = document.createElement("optgroup");
      g.label = `Empty slots (${empties.length})`;
      empties.forEach((p) => {
        const o = document.createElement("option");
        o.value = String(p.slot);
        o.textContent = `#${p.slot} — empty`;
        g.appendChild(o);
      });
      sel.appendChild(g);
    }
    const used = state.patches.filter((p) => !isEmpty(p.slot));
    const g2 = document.createElement("optgroup");
    g2.label = "Occupied slots (overwrite)";
    used.forEach((p) => {
      const o = document.createElement("option");
      o.value = String(p.slot);
      o.textContent = `#${p.slot} — ${p.name}`;
      g2.appendChild(o);
    });
    sel.appendChild(g2);
  }

  function chainText(p) {
    return p.uses_snaptone
      ? `N→S: ${p.snaptone_name}`
      : `${p.amp_name || "?"} · ${p.ir_name || "?"}`;
  }

  function openUsageModal(kind, slot) {
    ensureUi();
    const ov = document.getElementById("dc-usage");
    const list = document.getElementById("dc-usage-list");
    const buildBtn = document.getElementById("dc-usage-build");
    const closeBtn = document.getElementById("dc-usage-close");
    const asset = (kind === "ir" ? state.userIrs.concat(state.factoryCabs) : state.snaptones)
      .find((x) => x.slot === slot);
    const name = asset ? (kind === "ir" ? irLabel(asset) : asset.name) : `#${slot}`;
    const patches = usagePatches(kind, slot);
    document.getElementById("dc-usage-title").textContent = name;
    document.getElementById("dc-usage-sub").textContent = patches.length
      ? `Used by ${patches.length} patch${patches.length === 1 ? "" : "es"}:`
      : "Not used by any patch — safe to overwrite or remove.";
    list.innerHTML = "";
    patches.forEach((p) => {
      const li = document.createElement("li");
      li.className = "dep-row";
      li.innerHTML = `<span class="dep-slot">#${p.slot}</span><span>${p.name}</span>` +
        `<span class="dep-meta">${chainText(p)}</span>`;
      list.appendChild(li);
    });
    buildBtn.hidden = kind !== "snaptone";
    ov.hidden = false;
    const close = () => { ov.hidden = true; closeBtn.onclick = ov.onclick = buildBtn.onclick = null; };
    closeBtn.onclick = close;
    ov.onclick = (e) => { if (e.target === ov) close(); };
    buildBtn.onclick = () => { close(); openBuildModal({ snaptoneSlot: slot }); };
  }

  function openBuildModal(opts = {}) {
    ensureUi();
    const ov = document.getElementById("dc-build");
    const tSel = document.getElementById("dc-build-template");
    const sSel = document.getElementById("dc-build-snaptone");
    const slotSel = document.getElementById("dc-build-slot");
    const warn = document.getElementById("dc-build-warn");
    const btnWrite = document.getElementById("dc-build-write");
    const btnDl = document.getElementById("dc-build-download");
    const btnCancel = document.getElementById("dc-build-cancel");

    // templates
    tSel.innerHTML = "";
    if (!state.templates.length) {
      const o = document.createElement("option");
      o.textContent = "No templates yet — create one from a preset in Preset Explorer";
      o.value = "";
      tSel.appendChild(o);
    } else {
      state.templates.forEach((t) => {
        const o = document.createElement("option");
        o.value = t.id;
        o.textContent = `${t.name}  ·  ${templateChainText(t)}`;
        tSel.appendChild(o);
      });
    }
    if (opts.templateId) tSel.value = opts.templateId;

    // snaptones
    sSel.innerHTML = "";
    state.snaptones.forEach((s) => {
      const o = document.createElement("option");
      o.value = String(s.slot);
      o.textContent = `#${s.slot} — ${s.name}`;
      sSel.appendChild(o);
    });
    if (opts.snaptoneSlot != null) sSel.value = String(opts.snaptoneSlot);

    fillSlotPicker(slotSel);

    const haveTemplate = !!state.templates.length;
    btnWrite.disabled = !haveTemplate;
    btnDl.disabled = !haveTemplate;

    function refreshWarn() {
      const slot = Number(slotSel.value);
      if (isEmpty(slot)) { warn.hidden = true; return; }
      const n = usageCount("snaptone", slot) + usageCount("ir", slot);
      warn.hidden = false;
      warn.textContent = `⚠ Slot #${slot} "${slotName(slot)}" is not empty — writing replaces it` +
        (n ? ` (${n} patch${n === 1 ? "" : "es"} reference material here).` : ".");
    }
    slotSel.onchange = refreshWarn;
    refreshWarn();

    ov.hidden = false;

    const close = () => {
      ov.hidden = true;
      btnWrite.onclick = btnDl.onclick = btnCancel.onclick = ov.onclick = null;
    };
    btnCancel.onclick = close;
    ov.onclick = (e) => { if (e.target === ov) close(); };

    btnDl.onclick = async () => {
      try {
        const r = await fetch(API + "/build", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            template_id: tSel.value,
            snaptone_slot: Number(sSel.value),
            download: true,
          }),
        });
        if (!r.ok) throw new Error((await r.json()).detail || `HTTP ${r.status}`);
        const disp = r.headers.get("content-disposition") || "";
        const m = disp.match(/filename="(.+?)"/);
        const blob = await r.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url; a.download = m ? m[1] : "patch.prst"; a.click();
        URL.revokeObjectURL(url);
        toast(`Downloaded ${a.download} — import via Suite.`, "ok");
        close();
      } catch (e) { toast(`Build failed: ${e.message}`, "err"); }
    };

    btnWrite.onclick = async () => {
      const slot = Number(slotSel.value);
      const stName = state.snaptones.find((s) => s.slot === Number(sSel.value));
      const msg = isEmpty(slot)
        ? `Write a patch built from "${stName ? stName.name : sSel.value}" to empty slot #${slot}?`
        : `Overwrite slot #${slot} "${slotName(slot)}" with a patch built from "${stName ? stName.name : sSel.value}"? This writes to the pedal.`;
      if (!(await confirmDialog(msg, "Write to device"))) return;
      btnWrite.disabled = true;
      toast(`Writing to slot #${slot}…`);
      try {
        const r = await jpost("/build", {
          template_id: tSel.value,
          snaptone_slot: Number(sSel.value),
          target_slot: slot,
          confirm: true,
        });
        if (!r.ok) throw new Error(r.error || "write failed");
        toast(`✓ Wrote "${r.verified_name || ""}" to slot #${slot}.`, "ok");
        close();
        await load();
      } catch (e) {
        toast(`Write failed: ${e.message}`, "err");
        btnWrite.disabled = false;
      }
    };
  }

  window.DeviceCore = {
    state,
    load, usagePatches, usageCount, emptySlots, isEmpty, slotName, irLabel, isUserIr,
    sync, createTemplate, deleteTemplate, buildWrite,
    openBuildModal, openUsageModal, confirmDialog, toast,
    on: (evt, cb) => { (listeners[evt] = listeners[evt] || []).push(cb); },
  };
})();
