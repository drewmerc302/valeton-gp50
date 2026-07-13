"use strict";

// GP-50 Device Inspector. Reads real data parsed from the exported patch set
// via /api/device (see app/api_device.py + app/patchlib.py). The /clone POST
// returns an edited .prst (or a .zip for multiple) to re-import through Suite.
(() => {
  const $ = (id) => document.getElementById(id);
  const kindSnaptone = $("kind-snaptone");
  const kindIr = $("kind-ir");
  const libSearch = $("lib-search");
  const libList = $("lib-list");
  const usageTitle = $("usage-title");
  const usageList = $("usage-list");
  const usageEmpty = $("usage-empty");
  const cloneOnto = $("clone-onto");
  const cloneSource = $("clone-source");
  const cloneTargets = $("clone-targets");
  const cloneGo = $("clone-go");
  const cloneStatus = $("clone-status");
  const patchSearch = $("patch-search");
  const patchList = $("patch-list");

  let inv = { snaptones: [], irs: [], patches: [] };
  let selected = null; // {kind, slot}

  const kind = () => (kindIr.checked ? "ir" : "snaptone");
  const items = (k) => (k === "ir" ? inv.irs : inv.snaptones);
  const usageCount = (k, slot) =>
    inv.patches.filter((p) =>
      k === "ir" ? p.ir_slot === slot && !p.uses_snaptone : p.snaptone_slot === slot
    ).length;

  function chainText(p) {
    return p.uses_snaptone
      ? `N→S: ${p.snaptone_name} (#${p.snaptone_slot})`
      : `${p.amp_name} · ${p.ir_name}`;
  }

  const USER_IR_BASE = 0x100000;
  function slotLabel(it) {
    // User IR slots use a big fxid-derived index; show "User IR N" instead
    if (it.is_user_ir || it.slot >= USER_IR_BASE)
      return `User IR ${it.slot - USER_IR_BASE + 1}`;
    return `#${it.slot}`;
  }

  function renderLib() {
    const k = kind();
    const q = libSearch.value.trim().toLowerCase();
    libList.innerHTML = "";
    items(k)
      .filter((it) => !q || `${slotLabel(it)} ${it.name}`.toLowerCase().includes(q))
      .forEach((it) => {
        const li = document.createElement("li");
        li.className = "lib-item";
        if (selected && selected.kind === k && selected.slot === it.slot)
          li.classList.add("sel");
        const n = usageCount(k, it.slot);
        li.innerHTML = `<span class="lib-name">${slotLabel(it)} ${it.name}</span>` +
          `<span class="badge">${n} patch${n === 1 ? "" : "es"}</span>`;
        li.addEventListener("click", () => selectItem(k, it.slot));
        libList.appendChild(li);
      });
  }

  async function selectItem(k, slot) {
    selected = { kind: k, slot };
    renderLib();
    const it = items(k).find((x) => x.slot === slot);
    usageTitle.textContent = `Patches using ${it ? it.name : "#" + slot}`;
    cloneOnto.hidden = k !== "snaptone";
    try {
      const r = await fetch(`/api/device/usage/${k}/${slot}`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      renderUsage((await r.json()).patches || []);
    } catch (e) {
      usageList.innerHTML = "";
      usageEmpty.hidden = false;
      usageEmpty.textContent = `Could not load usage: ${e.message}`;
    }
  }

  function renderUsage(patches) {
    usageList.innerHTML = "";
    if (!patches.length) {
      usageEmpty.hidden = false;
      usageEmpty.textContent = "No patches reference this.";
      return;
    }
    usageEmpty.hidden = true;
    patches.forEach((p) => {
      const li = document.createElement("li");
      li.className = "file-row";
      li.innerHTML = `<span class="file-row-name">#${p.slot} ${p.name}</span>` +
        `<span class="file-row-meta">${chainText(p)}</span>`;
      usageList.appendChild(li);
    });
  }

  function renderPatches() {
    const q = patchSearch.value.trim().toLowerCase();
    patchList.innerHTML = "";
    inv.patches
      .filter((p) => !q || `${p.slot} ${p.name} ${chainText(p)}`.toLowerCase().includes(q))
      .forEach((p) => {
        const li = document.createElement("li");
        li.className = "file-row";
        const tag = p.uses_snaptone ? '<span class="badge st">SnapTone</span>' : "";
        li.innerHTML = `<span class="file-row-name">#${p.slot} ${p.name} ${tag}</span>` +
          `<span class="file-row-meta">${chainText(p)}</span>`;
        patchList.appendChild(li);
      });
  }

  function fillClone() {
    cloneSource.innerHTML = "";
    inv.patches.forEach((p) => {
      const o = document.createElement("option");
      o.value = String(p.slot);
      o.textContent = `#${p.slot} ${p.name}${p.uses_snaptone ? "" : "  (amp+cab — no SnapTone block)"}`;
      cloneSource.appendChild(o);
    });
    cloneTargets.innerHTML = "";
    inv.snaptones.forEach((s) => {
      const lbl = document.createElement("label");
      lbl.className = "radio-pill";
      lbl.innerHTML = `<input type="checkbox" value="${s.slot}" /> #${s.slot} ${s.name}`;
      cloneTargets.appendChild(lbl);
    });
    cloneTargets.addEventListener("change", updateCloneBtn);
    updateCloneBtn();
  }

  const chosenTargets = () =>
    [...cloneTargets.querySelectorAll("input:checked")].map((c) => Number(c.value));

  function updateCloneBtn() {
    const n = chosenTargets().length;
    cloneGo.disabled = n === 0;
    cloneGo.textContent = n > 1 ? `Generate & download (${n} clones .zip)` : "Generate & download";
  }

  async function doClone() {
    const patch_slot = Number(cloneSource.value);
    const snaptone_slots = chosenTargets();
    cloneStatus.textContent = "Generating…";
    cloneGo.disabled = true;
    try {
      const r = await fetch("/api/device/clone", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ patch_slot, snaptone_slots }),
      });
      if (!r.ok) throw new Error((await r.json()).detail || `HTTP ${r.status}`);
      const disp = r.headers.get("content-disposition") || "";
      const m = disp.match(/filename="(.+?)"/);
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = m ? m[1] : "clone.prst";
      a.click();
      URL.revokeObjectURL(url);
      cloneStatus.textContent = `Downloaded ${a.download} — re-import via Suite.`;
    } catch (e) {
      cloneStatus.textContent = `Failed: ${e.message}`;
    } finally {
      updateCloneBtn();
    }
  }

  cloneOnto.addEventListener("click", () => {
    if (selected && selected.kind === "snaptone") {
      cloneTargets.querySelectorAll("input").forEach((c) => {
        c.checked = Number(c.value) === selected.slot;
      });
      updateCloneBtn();
      $("clone-card").scrollIntoView({ behavior: "smooth" });
    }
  });
  kindSnaptone.addEventListener("change", () => { selected = null; renderLib(); usageTitle.textContent = "Select an item"; usageList.innerHTML = ""; usageEmpty.hidden = true; cloneOnto.hidden = true; });
  kindIr.addEventListener("change", () => { selected = null; renderLib(); usageTitle.textContent = "Select an item"; usageList.innerHTML = ""; usageEmpty.hidden = true; cloneOnto.hidden = true; });
  libSearch.addEventListener("input", renderLib);
  patchSearch.addEventListener("input", renderPatches);
  cloneGo.addEventListener("click", doClone);
  $("clone-all").addEventListener("click", () => {
    cloneTargets.querySelectorAll("input").forEach((c) => (c.checked = true));
    updateCloneBtn();
  });
  $("clone-none").addEventListener("click", () => {
    cloneTargets.querySelectorAll("input").forEach((c) => (c.checked = false));
    updateCloneBtn();
  });

  async function loadInventory() {
    const r = await fetch("/api/device/inventory");
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    inv = await r.json();
    if (inv.source) $("source-note").textContent = inv.source;
  }

  async function syncDevice() {
    const btn = $("sync-btn");
    const status = $("sync-status");
    btn.disabled = true;
    status.textContent = "Reading pedal… (connect it, close Valeton Suite)";
    try {
      const r = await fetch("/api/device/sync", { method: "POST" });
      const body = await r.json();
      if (!body.ok) throw new Error(body.error || "sync failed");
      status.textContent = `Synced ${body.count} SnapTones and ${body.ir_count ?? 0} User IRs from device.`;
      await loadInventory();
      $("ct-snaptone").textContent = `(${inv.snaptones.length})`;
      $("ct-ir").textContent = `(${inv.irs.length})`;
      selected = null;
      renderLib();
      renderPatches();
      fillClone();
    } catch (e) {
      status.textContent = `Sync failed: ${e.message}`;
    } finally {
      btn.disabled = false;
    }
  }

  $("sync-btn").addEventListener("click", syncDevice);

  async function init() {
    try {
      await loadInventory();
    } catch (e) {
      $("source-note").textContent = `Could not load inventory: ${e.message}`;
      return;
    }
    $("ct-snaptone").textContent = `(${inv.snaptones.length})`;
    $("ct-ir").textContent = `(${inv.irs.length})`;
    renderLib();
    renderPatches();
    fillClone();
  }

  init();
})();
