"use strict";

// GP-50 Preset Explorer. Renders every preset's ACTIVE chain at
// Block · Type · Model granularity and filters over it. Reads real parsed data
// from /api/device/inventory (patches carry a `blocks` array) + /api/device/facets.
(() => {
  const UI = window.UI; // shared core: toast/confirm/prompt, fetch helpers, downloads
  const $ = (id) => document.getElementById(id);
  const searchEl = $("preset-search");
  const filterBar = $("filter-bar");
  const activeFiltersEl = $("active-filters");
  const listEl = $("preset-list");
  const emptyEl = $("preset-empty");
  const countEl = $("result-count");

  let patches = [];
  let facets = { blocks: [] };
  let inventoryDevice = null; // {key,name} the loaded presets belong to
  let filters = []; // {block, type|null, model|null}

  // N->S is the pedal's block name for the SnapTone slot; label it plainly.
  const BLOCK_DISPLAY = { "N->S": "SnapTone" };
  const blockDisplay = (b) => BLOCK_DISPLAY[b] || b;

  const SAVED_KEY = "gp50_savedFilters";
  const loadSaved = () => { try { return JSON.parse(localStorage.getItem(SAVED_KEY)) || []; } catch { return []; } };
  const persistSaved = (list) => localStorage.setItem(SAVED_KEY, JSON.stringify(list));

  const activeBlocks = (p) => p.blocks.filter((b) => b.active);

  function filterLabel(f) {
    return [blockDisplay(f.block), f.type, f.model].filter(Boolean).join(" · ");
  }

  function sameFilter(a, b) {
    return a.block === b.block && a.type === b.type && a.model === b.model;
  }

  function addFilter(f) {
    if (reorderMode) return; // list is a reorder surface right now, not a filter surface
    if (!filters.some((x) => sameFilter(x, f))) filters.push(f);
    render();
  }

  // clicking a block chip toggles its filter: add if absent, remove if already
  // applied (so a second click on the same block clears it).
  function toggleFilter(f) {
    if (reorderMode) return;
    const before = filters.length;
    filters = filters.filter((x) => !sameFilter(x, f));
    if (filters.length === before) filters.push(f);
    render();
  }

  function matchesFilters(p) {
    const blocks = activeBlocks(p);
    return filters.every((f) =>
      blocks.some(
        (b) =>
          b.block === f.block &&
          (!f.type || b.type === f.type) &&
          (!f.model || b.model === f.model)
      )
    );
  }

  function matchesSearch(p) {
    const q = searchEl.value.trim().toLowerCase();
    if (!q) return true;
    // search device labels AND real-hardware names (Fender, JCM800, TS808, …)
    const hay = `${p.slot} ${p.name} ` +
      p.blocks.map((b) => `${b.label} ${b.label_official || ""} ${b.official || ""}`).join(" ");
    return hay.toLowerCase().includes(q);
  }

  // --- filter builder: Block -> Type(optional) -> Model(optional) -----------
  function buildFilterBar() {
    filterBar.innerHTML = "";
    const blockSel = document.createElement("select");
    fill(blockSel, ["— block —"]);
    facets.blocks.forEach((b) => {
      const o = document.createElement("option");
      o.value = b.block;
      o.textContent = blockDisplay(b.block);
      blockSel.appendChild(o);
    });
    const typeSel = mkSelect(["any type"]);
    const modelSel = mkSelect(["any model"]);
    const addBtn = document.createElement("button");
    addBtn.type = "button";
    addBtn.textContent = "Add filter";
    addBtn.disabled = true;

    // (re)build the model dropdown, narrowed to the selected type ("any type"
    // shows all). Called on both block change and type change.
    function fillModels() {
      const fb = facets.blocks.find((b) => b.block === blockSel.value);
      const wantType = typeSel.selectedIndex > 0 ? typeSel.value : null;
      modelSel.innerHTML = "";
      const anyOpt = document.createElement("option");
      anyOpt.textContent = "any model";
      anyOpt.value = "";
      modelSel.appendChild(anyOpt);
      (fb ? fb.models : [])
        .filter((m) => !wantType || m.type === wantType)
        .forEach((m) => {
          const opt = document.createElement("option");
          opt.value = m.model;
          // models carry an optional official name -> show "Device / Official"
          opt.textContent = m.official ? `${m.model} / ${m.official}` : m.model;
          modelSel.appendChild(opt);
        });
    }

    function refresh() {
      const fb = facets.blocks.find((b) => b.block === blockSel.value);
      typeSel.innerHTML = "";
      fill(typeSel, ["any type", ...(fb ? fb.types : [])]);
      fillModels();
      addBtn.disabled = !fb;
    }
    blockSel.addEventListener("change", refresh);
    typeSel.addEventListener("change", fillModels);
    addBtn.addEventListener("click", () => {
      if (!blockSel.value || blockSel.selectedIndex === 0) return;
      addFilter({
        block: blockSel.value,
        type: typeSel.selectedIndex > 0 ? typeSel.value : null,
        model: modelSel.selectedIndex > 0 ? modelSel.value : null,
      });
    });

    [labelWrap("Block", blockSel), labelWrap("Type", typeSel),
     labelWrap("Model", modelSel), addBtn].forEach((el) => filterBar.appendChild(el));
  }

  function mkSelect(opts) {
    const s = document.createElement("select");
    fill(s, opts);
    return s;
  }
  function fill(sel, opts) {
    opts.forEach((o) => {
      const opt = document.createElement("option");
      opt.textContent = o;
      opt.value = o;
      sel.appendChild(opt);
    });
  }
  function labelWrap(text, el) {
    const w = document.createElement("label");
    w.className = "field inline";
    w.innerHTML = `<span class="hint">${text}</span>`;
    w.appendChild(el);
    return w;
  }

  function renderActiveFilters() {
    activeFiltersEl.innerHTML = "";
    filters.forEach((f, i) => {
      const pill = document.createElement("button");
      pill.type = "button";
      pill.className = "filter-pill";
      pill.innerHTML = `${filterLabel(f)} <span class="x">✕</span>`;
      pill.addEventListener("click", () => {
        filters.splice(i, 1);
        render();
      });
      activeFiltersEl.appendChild(pill);
    });
    if (filters.length > 1) {
      const clear = document.createElement("button");
      clear.type = "button";
      clear.className = "linkish";
      clear.textContent = "clear all";
      clear.addEventListener("click", () => { filters = []; render(); });
      activeFiltersEl.appendChild(clear);
    }
  }

  const officialOn = () => $("official-toggle").checked;

  function chip(b) {
    const c = document.createElement("button");
    c.type = "button";
    c.className = `chip blk-${b.block.replace(/[^a-z]/gi, "").toLowerCase()}`;
    if (!b.active) c.classList.add("bypassed-chip"); // dim bypassed blocks in the chain
    const useOfficial = officialOn() && b.official;
    c.textContent = useOfficial ? b.label_official : b.label;
    if (useOfficial) c.classList.add("official");
    const f = { block: b.block, type: b.type, model: b.model };
    const active = filters.some((x) => sameFilter(x, f));
    if (active) c.classList.add("chip-filtered"); // show it's an applied filter
    c.title = active
      ? "Click to remove this filter"
      : b.official
        ? `Device: ${b.label}\nOfficial: ${b.label_official}`
        : "Filter by this block · type · model";
    c.addEventListener("click", (ev) => {
      ev.stopPropagation();
      toggleFilter(f);
    });
    return c;
  }

  const expanded = new Set(); // preset slots currently expanded
  let activeSlot = null; // the preset currently SELECTED on the connected pedal
  let deviceLive = { connected: false, device: null }; // /api/device/status
  const blockToggled = new Set(); // `${slot}:${blkIdx}` blocks flipped from their default expand state (active=open)
  const edits = new Map(); // slot -> {params:{blk:{alg:val}}, bypass:{blk:bool}, settings:{}, models:{blk:fxid}, override:{blk:{...}}}
  let allModels = {}; // block -> [selectable models w/ param defs] (for the model picker)
  let libEntries = []; // all block-library entries (grouped client-side by block)
  let pickerKey = null; // `${slot}:${blkIdx}` of the open model picker, or null

  // live edit: mirror edits to the pedal over WebMIDI (Chrome/Edge) via DeviceBridge
  let liveSlot = null; // slot currently in live-edit mode, or null
  let liveBase = null; // that slot's base .prst (Uint8Array) read from the pedal
  let liveTimer = null; // debounce handle
  let liveBusy = false; // a write is in flight
  let livePending = false; // an edit arrived during a write -> flush after

  function blockLabel(b) {
    return officialOn() && b.official ? b.label_official : b.label;
  }

  function getEdit(slot) {
    if (!edits.has(slot))
      edits.set(slot, { params: {}, bypass: {}, settings: {}, footswitches: null, models: {}, override: {}, name: null, order: null });
    return edits.get(slot);
  }
  function isDirty(slot) {
    const e = edits.get(slot);
    return e && (Object.keys(e.params).length || Object.keys(e.bypass).length ||
      Object.keys(e.settings).length || Object.keys(e.models).length || e.footswitches || e.name != null || e.order != null);
  }
  // Current name for a preset — a pending rename wins over the stored name.
  function curName(p) {
    const e = edits.get(p.slot);
    return e && e.name != null ? e.name : p.name;
  }
  // Current chain order (chain position -> model-record index). Pending reorder wins;
  // falls back to the decoded order, then canonical identity.
  function curOrder(p) {
    const e = edits.get(p.slot);
    if (e && e.order != null) return e.order;
    return (p.order && p.order.length === 10) ? p.order : Array.from({ length: 10 }, (_, i) => i);
  }

  // Effective block view: if the user swapped the model, render the NEW model's
  // label + param defs (values = saved/default) instead of the on-device block.
  function effBlock(slot, blkIdx, b) {
    const e = edits.get(slot);
    const ov = e && e.override && e.override[blkIdx];
    if (!ov) return b;
    const pvals = (e.params && e.params[blkIdx]) || {};
    const params = (ov.params || []).map((pd) => {
      const value = pvals[pd.algId] !== undefined ? pvals[pd.algId] : resolveDefault(pd);
      return {
        name: pd.name, algId: pd.algId, toggle: !!pd.toggle, unit: pd.unit || "",
        min: pd.min, max: pd.max, step: pd.step, value,
        display: fmtParam({ toggle: !!pd.toggle, unit: pd.unit || "" }, value),
      };
    });
    return {
      block: b.block, active: b.active, type: ov.type, model: ov.name,
      official: ov.official, fxid: ov.fxid, label: ov.label,
      label_official: ov.label_official, params, _override: true,
    };
  }
  // current footswitch assignment {fs1:[...], fs2:[...]} (pending edit wins)
  function curFS(p) {
    const e = getEdit(p.slot);
    if (e.footswitches) return e.footswitches;
    const s = p.settings || {};
    return { fs1: (s.fs1 || []).slice(), fs2: (s.fs2 || []).slice() };
  }
  function toggleFS(p, blkIdx, fsKey) {
    const e = getEdit(p.slot);
    if (!e.footswitches) e.footswitches = curFS(p);  // materialize on first edit
    const arr = e.footswitches[fsKey];
    const at = arr.indexOf(blkIdx);
    if (at >= 0) arr.splice(at, 1);
    else if (arr.length < 2) arr.push(blkIdx);  // device cap: 2 blocks per FS
    renderPresets();
    liveKick(p.slot);
  }
  // current value for a param (pending edit wins over stored value)
  function curVal(slot, blkIdx, pr) {
    const e = edits.get(slot);
    const v = e && e.params[blkIdx] && e.params[blkIdx][pr.algId];
    return v !== undefined ? v : pr.value;
  }
  function fmtParam(pr, value) {
    if (pr.toggle) return Math.round(value) ? "On" : "Off";
    const v = Math.abs(value - Math.round(value)) < 1e-4 ? String(Math.round(value)) : value.toFixed(2);
    return pr.unit ? `${v} ${pr.unit}` : v;
  }

  // A param's default value. Trust the model data when it has one (the Valeton
  // Suite catalog carries real per-model defaults — e.g. cab VOL 50, and EQ bands
  // legitimately 0 = flat). Only SYNTHESIZE when a default is genuinely missing,
  // so a swapped model never lands on a silent/extreme value: unknown toggle=off,
  // unknown time(ms)=500ms, unknown bipolar(EQ-like)=0 (center), else the 0..100
  // midpoint (=50). Never overrides a real default.
  function resolveDefault(pd) {
    const d = Number(pd.default);
    if (Number.isFinite(d)) return d;
    if (pd.toggle) return 0;
    const min = Number(pd.min ?? 0);
    const max = Number(pd.max ?? 100);
    if ((pd.unit || "") === "ms") return Math.min(Math.max(500, min), max);
    if (min < 0) return 0;
    return Math.round((min + max) / 2);
  }

  // --- model swap + block library ------------------------------------------
  // Set a block's (model, params): the shared core of "change model" and
  // "apply library block". savedParams (algId->value) win over model defaults.
  function applyModel(p, blkIdx, model, savedParams) {
    const e = getEdit(p.slot);
    e.models[blkIdx] = model.fxid;
    e.override[blkIdx] = {
      fxid: model.fxid, name: model.name, official: model.official || null,
      type: model.type || "", label: model.label, label_official: model.label_official,
      params: model.params || [],
    };
    const pv = {};
    (model.params || []).forEach((pd) => {
      // sv is undefined for a fresh pick (no savedParams) OR when the saved set
      // omits this algId; a real saved value (incl. 0) is kept. NOTE: this MUST be
      // `savedParams ? ... : undefined`, not `savedParams && savedParams[algId]` —
      // the latter yields null when savedParams is null, and `null !== undefined`
      // is true, so every fresh-pick param got Number(null)=0 (silent cabs/amps).
      const sv = savedParams ? savedParams[pd.algId] : undefined;
      pv[pd.algId] = sv !== undefined ? Number(sv) : resolveDefault(pd);
    });
    e.params[blkIdx] = pv;
    pickerKey = null;
    renderPresets();
    liveKick(p.slot);
  }

  function applyLibEntry(p, blkIdx, entry) {
    const model = (allModels[entry.block] || []).find((m) => m.fxid === entry.fxid);
    if (!model) { UI.toast(`Model for "${entry.name}" is no longer available on this device.`, "err"); return; }
    applyModel(p, blkIdx, model, entry.params);
  }

  function revertModel(p, blkIdx) {
    const e = getEdit(p.slot);
    delete e.models[blkIdx];
    delete e.override[blkIdx];
    delete e.params[blkIdx]; // drop the seeded defaults so the on-device values show
    pickerKey = null;
    renderPresets();
    liveKick(p.slot);
  }

  async function saveToLib(p, blkIdx, b) {
    const name = await UI.promptDialog(
      `Save this ${blockDisplay(b.block)} block to your library as:`, b.model || b.block, "Save");
    if (!name) return;
    const params = {};
    (b.params || []).forEach((pr) => { params[pr.algId] = curVal(p.slot, blkIdx, pr); });
    try {
      await UI.jpost("/api/device/blocklib",
        { name, block: b.block, fxid: b.fxid, model_name: b.model || "", params });
      await refreshLib();
      renderPresets();
    } catch (err) { UI.toast(`Save failed: ${err.message}`, "err"); }
  }

  async function deleteLibEntry(id) {
    try {
      await UI.jdel(`/api/device/blocklib/${id}`);
      await refreshLib();
      renderPresets();
    } catch { /* ignore */ }
  }

  async function refreshLib() {
    libEntries = (await UI.jget("/api/device/blocklib")).entries || [];
  }

  // Preload the model catalog per block type + the block library so the picker
  // renders synchronously. Model lists are static; the library refreshes on edit.
  async function loadModelsAndLib() {
    const blocks = [...new Set(patches.flatMap((p) => p.blocks.map((b) => b.block)))];
    const pairs = await Promise.all(
      blocks.map(async (blk) => {
        try {
          const j = await UI.jget(`/api/device/models/${encodeURIComponent(blk)}`);
          return [blk, j.models || []];
        } catch { return [blk, []]; }
      })
    );
    allModels = Object.fromEntries(pairs);
    await refreshLib();
  }

  // The model/library picker panel shown under a block header when clicked.
  function buildPicker(p, blkIdx, b) {
    const panel = document.createElement("div");
    panel.className = "model-picker";

    const models = allModels[b.block] || [];
    const lib = libEntries.filter((en) => en.block === b.block);

    const search = document.createElement("input");
    search.type = "search";
    search.className = "picker-search";
    search.placeholder = `Filter ${models.length} ${blockDisplay(b.block)} models…`;
    panel.appendChild(search);

    // library section (if any saved for this block type)
    if (lib.length) {
      const lh = document.createElement("div");
      lh.className = "picker-section-head";
      lh.textContent = "Your library";
      panel.appendChild(lh);
      const llist = document.createElement("div");
      llist.className = "picker-list lib";
      lib.forEach((en) => {
        const row = document.createElement("div");
        row.className = "picker-item lib";
        const pick = document.createElement("button");
        pick.type = "button"; pick.className = "picker-pick";
        pick.innerHTML = `<b>${en.name}</b> <span class="subtitle">${en.model_name || ""}</span>`;
        pick.addEventListener("click", () => applyLibEntry(p, blkIdx, en));
        const del = document.createElement("button");
        del.type = "button"; del.className = "picker-del"; del.textContent = "✕";
        del.title = "Delete library entry";
        del.addEventListener("click", (ev) => { ev.stopPropagation(); deleteLibEntry(en.id); });
        row.appendChild(pick); row.appendChild(del);
        llist.appendChild(row);
      });
      panel.appendChild(llist);
    }

    const mh = document.createElement("div");
    mh.className = "picker-section-head";
    mh.textContent = "Models";
    panel.appendChild(mh);
    const mlist = document.createElement("div");
    mlist.className = "picker-list";
    panel.appendChild(mlist);

    function renderModels(q) {
      mlist.innerHTML = "";
      const ql = q.trim().toLowerCase();
      models
        .filter((m) => !ql || `${m.name} ${m.official || ""} ${m.type || ""}`.toLowerCase().includes(ql))
        .forEach((m) => {
          const btn = document.createElement("button");
          btn.type = "button";
          btn.className = "picker-pick model" + (m.fxid === b.fxid ? " current" : "");
          btn.innerHTML =
            `<span>${m.name}</span>` +
            (m.type ? ` <span class="picker-type">${m.type}</span>` : "") +
            (m.official ? ` <span class="subtitle">${m.official}</span>` : "");
          btn.addEventListener("click", () => applyModel(p, blkIdx, m, null));
          mlist.appendChild(btn);
        });
    }
    renderModels("");
    search.addEventListener("input", () => renderModels(search.value));

    // footer: save current to library + (if overridden) revert
    const foot = document.createElement("div");
    foot.className = "picker-foot";
    const save = document.createElement("button");
    save.type = "button"; save.className = "picker-save"; save.textContent = "★ Save current to library";
    save.addEventListener("click", () => saveToLib(p, blkIdx, b));
    foot.appendChild(save);
    if (getEdit(p.slot).override[blkIdx]) {
      const rev = document.createElement("button");
      rev.type = "button"; rev.className = "linkish"; rev.textContent = "revert model";
      rev.addEventListener("click", () => revertModel(p, blkIdx));
      foot.appendChild(rev);
    }
    panel.appendChild(foot);
    return panel;
  }

  // The action bar (download / write / live-edit / reset + status notes). Rendered
  // at the TOP of the expanded detail so it stays visible without scrolling past a
  // long block chain — otherwise Live edit gets lost below the fold.
  function buildSaveBar(p) {
    const bar = document.createElement("div");
    bar.className = "save-bar";
    if (isDirty(p.slot)) bar.classList.add("dirty"); // survive full re-renders (e.g. block reorder)
    bar.dataset.slot = p.slot;
    const dl = document.createElement("button");
    dl.type = "button"; dl.className = "save-edit"; dl.textContent = "⬇ Download edited .prst";
    dl.addEventListener("click", () => downloadEdit(p));
    const wr = document.createElement("button");
    wr.type = "button"; wr.className = "write-dev"; wr.textContent = "⚡ Write edits to device";
    wr.title = "Write this patch directly to the pedal (overwrites a slot)";
    wr.addEventListener("click", () => writeToDevice(p));
    const rst = document.createElement("button");
    rst.type = "button"; rst.className = "linkish"; rst.textContent = "reset";
    rst.addEventListener("click", () => { edits.delete(p.slot); renderPresets(); });
    bar.appendChild(dl); bar.appendChild(wr);
    // live edit (WebMIDI only): mirror changes to the pedal in real time
    if (window.DeviceBridge && DeviceBridge.webmidiAvailable()) {
      if (liveSlot === p.slot) {
        // live is ON for this slot → commit / restore controls
        const status = document.createElement("span");
        status.className = "live-status"; status.textContent = "● Live";
        const keep = document.createElement("button");
        keep.type = "button"; keep.className = "live-keep"; keep.textContent = "✓ Keep changes";
        keep.title = "Commit the current live edits to the pedal and stop live editing";
        keep.addEventListener("click", () => keepLive(p.slot));
        const restore = document.createElement("button");
        restore.type = "button"; restore.className = "live-restore"; restore.textContent = "↺ Restore original";
        restore.title = "Undo all live changes — write the pre-live settings back to the pedal";
        restore.addEventListener("click", () => restoreLive(p.slot));
        bar.appendChild(status); bar.appendChild(keep); bar.appendChild(restore);
      } else {
        const live = document.createElement("button");
        live.type = "button"; live.className = "live-toggle";
        live.textContent = "⚡ Live edit";
        live.title = "Mirror edits to the pedal in real time over WebMIDI (writes slot " + p.slot + " on each change)";
        live.addEventListener("click", () => toggleLiveEdit(p));
        bar.appendChild(live);
      }
    }
    bar.appendChild(rst);
    const note = document.createElement("span");
    note.className = "subtitle save-note";
    const liveNoteEl = document.createElement("span");
    liveNoteEl.className = "subtitle live-note";
    bar.appendChild(note); bar.appendChild(liveNoteEl);
    // Clear Preset (far right): wipe this slot back to the factory "GP-50" blank.
    // WebMIDI-only (writes the pedal directly), like Live edit.
    if (window.DeviceBridge && DeviceBridge.webmidiAvailable()) {
      const clr = document.createElement("button");
      clr.type = "button"; clr.className = "clear-preset"; clr.textContent = "🗑 Clear preset";
      clr.title = `Overwrite slot ${p.slot} with a blank "GP-50" preset (writes the pedal)`;
      clr.addEventListener("click", () => clearPreset(p));
      bar.appendChild(clr);
    }
    return bar;
  }

  // Clear Preset: overwrite the slot with the factory-default "GP-50" blank. Writes
  // the pedal directly over WebMIDI (like Live edit); confirmed first. Drops any
  // pending edits and exits live mode for the slot, then syncs the cache to blank.
  async function clearPreset(p) {
    if (!(window.DeviceBridge && DeviceBridge.webmidiAvailable())) {
      UI.toast("Clear needs Chrome or Edge (WebMIDI).", "err");
      return;
    }
    const ok = await UI.confirmDialog(
      `Clear slot ${p.slot} "${curName(p)}" back to a blank "GP-50" preset? This overwrites the slot on the pedal and can't be undone from here. Make sure Valeton Suite is closed.`,
      "Clear preset");
    if (!ok) return;
    const note = listEl.querySelector(`.save-bar[data-slot="${p.slot}"] .save-note`);
    try {
      if (!DeviceBridge.connected()) { if (note) note.textContent = "Connecting to pedal…"; await DeviceBridge.connect(); }
      const blank = window.PRST.blankPrst((inventoryDevice && inventoryDevice.key) || "gp50");
      if (note) note.textContent = `Clearing slot ${p.slot}…`;
      await withTimeout(
        DeviceBridge.writeSlot(p.slot, blank), 15000,
        "clear timed out — is this tab in the background? (bring it to the front)");
      edits.delete(p.slot);
      if (liveSlot === p.slot) { liveSlot = null; liveBase = null; }
      await syncSlotCache(p.slot, blank);
      renderPresets();
      UI.toast(`Cleared slot ${p.slot} to a blank preset.`, "ok");
    } catch (err) {
      if (note) note.textContent = `Clear failed: ${err.message}`;
      UI.toast(`Clear failed: ${err.message}`, "err");
    }
  }

  // --- block (signal-chain) reordering --------------------------------------
  // A compact draggable strip of the 10 blocks in chain order. The 5 movable
  // blocks (NR·PRE·MOD·DLY·RVB) drag freely; the 5-block amp core
  // (DST·N→S·AMP·CAB·EQ) is one locked, atomic group they arrange around — so the
  // core can never be split, matching the device/app rule. See re/DEVICE_BLOCKORDER.md.
  function chainChip(p, b, recIdx, locked) {
    const c = document.createElement("div");
    c.className = "chain-chip blk-" + b.block.replace(/[^a-z]/gi, "").toLowerCase() + (locked ? " locked" : " movable");
    c.dataset.rec = recIdx;
    if (!locked) c.draggable = true;
    const e = getEdit(p.slot);
    const active = e.bypass[recIdx] !== undefined ? e.bypass[recIdx] : b.active;
    if (!active) c.classList.add("bypassed-chip");
    const name = blockDisplay(b.block);
    c.innerHTML = (locked ? "" : `<span class="chain-grip" aria-hidden="true">⠿</span>`) + `<span class="chain-name">${name}</span>`;
    c.title = locked ? "Fixed core block — can't be reordered" : `Drag to move ${name} in the chain`;
    return c;
  }

  function buildChainStrip(p) {
    const wrap = document.createElement("div");
    wrap.className = "chain-strip-wrap";
    const lbl = document.createElement("div");
    lbl.className = "chain-strip-label";
    lbl.innerHTML = `Signal chain <span class="hint">— drag NR · PRE · MOD · DLY · RVB around the fixed amp core</span>`;
    wrap.appendChild(lbl);
    const strip = document.createElement("div");
    strip.className = "chain-strip";
    const order = curOrder(p);
    let coreDone = false;
    order.forEach((recIdx) => {
      const b = p.blocks[recIdx];
      if (!b) return;
      if (b.movable) {
        strip.appendChild(chainChip(p, b, recIdx, false));
      } else if (!coreDone) {
        coreDone = true; // emit the whole contiguous core as one non-draggable unit
        const core = document.createElement("div");
        core.className = "chain-core";
        core.title = "Fixed core — DST · N→S · AMP · CAB · EQ stay together, in order";
        order.forEach((ri) => { const cb = p.blocks[ri]; if (cb && !cb.movable) core.appendChild(chainChip(p, cb, ri, true)); });
        strip.appendChild(core);
      }
    });
    wireChainDrag(p, strip);
    wrap.appendChild(strip);
    return wrap;
  }

  function chainDragAfter(strip, x) {
    let best = { off: -Infinity, el: null };
    for (const el of strip.children) {
      if (el.classList.contains("dragging")) continue;
      const box = el.getBoundingClientRect();
      const off = x - box.left - box.width / 2;
      if (off < 0 && off > best.off) best = { off, el };
    }
    return best.el;
  }

  // Read the chain order back from the strip DOM: movable chips contribute their
  // record index; the core group expands to its blocks (kept contiguous + in order).
  function chainOrderFromDom(strip) {
    const order = [];
    for (const el of strip.children) {
      if (el.classList.contains("chain-core")) {
        for (const cc of el.children) order.push(Number(cc.dataset.rec));
      } else if (el.classList.contains("chain-chip")) {
        order.push(Number(el.dataset.rec));
      }
    }
    return order;
  }

  function setChainOrder(p, order) {
    if (order.length !== 10 || new Set(order).size !== 10) return; // guard: keep it a permutation
    const e = getEdit(p.slot);
    const base = (p.order && p.order.length === 10) ? p.order : Array.from({ length: 10 }, (_, i) => i);
    e.order = order.every((v, i) => v === base[i]) ? null : order;
    refreshSaveBar(p);
    renderPresets(); // re-render so the strip + block cards reflect the new chain order
    liveKick(p.slot);
  }

  function wireChainDrag(p, strip) {
    strip.addEventListener("dragstart", (ev) => {
      const chip = ev.target.closest(".chain-chip.movable");
      if (!chip || !strip.contains(chip)) { ev.preventDefault(); return; }
      chip.classList.add("dragging");
      ev.dataTransfer.effectAllowed = "move";
      try { ev.dataTransfer.setData("text/plain", chip.dataset.rec); } catch { /* Safari */ }
    });
    strip.addEventListener("dragover", (ev) => {
      const dragging = strip.querySelector(".dragging");
      if (!dragging) return;
      ev.preventDefault();
      ev.dataTransfer.dropEffect = "move";
      const after = chainDragAfter(strip, ev.clientX);
      if (after == null) strip.appendChild(dragging);
      else strip.insertBefore(dragging, after);
    });
    strip.addEventListener("dragend", () => {
      const chip = strip.querySelector(".dragging");
      if (chip) chip.classList.remove("dragging");
      setChainOrder(p, chainOrderFromDom(strip));
    });
  }

  function renderDetail(p) {
    const d = document.createElement("div");
    d.className = "preset-detail";
    d.appendChild(buildSaveBar(p)); // actions first — visible without scrolling

    // editable preset name (16-char device limit) — writes with the other edits
    const nameRow = document.createElement("div");
    nameRow.className = "name-row";
    const nameLbl = document.createElement("label");
    nameLbl.textContent = "Preset name";
    const nameInput = document.createElement("input");
    // the device caps patch names at 10 chars (factory names top out at 10)
    nameInput.type = "text"; nameInput.className = "name-input"; nameInput.maxLength = 10;
    nameInput.title = "Up to 10 characters (device limit)";
    nameInput.value = curName(p);
    nameInput.setAttribute("aria-label", "Preset name");
    nameInput.addEventListener("input", () => {
      const e = getEdit(p.slot);
      const v = nameInput.value;
      e.name = v === p.name ? null : v; // unchanged = no edit
      refreshSaveBar(p);
      const hdr = nameInput.closest(".preset-row") && nameInput.closest(".preset-row").querySelector(".preset-name");
      if (hdr) hdr.textContent = v || p.name; // live-update the header without a re-render
    });
    nameInput.addEventListener("change", () => liveKick(p.slot)); // commit on blur/enter
    nameRow.appendChild(nameLbl); nameRow.appendChild(nameInput);
    d.appendChild(nameRow);

    // patch settings (editable VOL + BPM)
    const s = p.settings || {};
    const e = getEdit(p.slot);
    if (s.patch_vol !== undefined || s.bpm !== undefined) {
      const ps = document.createElement("div");
      ps.className = "patch-settings";
      const mk = (label, key, min, max, cur) => {
        const wrap = document.createElement("label");
        wrap.className = "patch-set";
        const val = e.settings[key] !== undefined ? e.settings[key] : cur;
        wrap.innerHTML = `<span>${label}</span>`;
        const inp = document.createElement("input");
        inp.type = "range"; inp.min = min; inp.max = max; inp.step = 1; inp.value = val;
        const out = document.createElement("b"); out.textContent = val;
        inp.addEventListener("input", () => {
          out.textContent = inp.value;
          e.settings[key] = Number(inp.value);
          refreshSaveBar(p);
        });
        inp.addEventListener("change", () => liveKick(p.slot)); // write on release
        wrap.appendChild(inp); wrap.appendChild(out);
        return wrap;
      };
      if (s.patch_vol !== undefined) ps.appendChild(mk("Patch VOL", "patch_vol", 0, 100, s.patch_vol));
      if (s.bpm !== undefined) ps.appendChild(mk("BPM", "bpm", 40, 300, s.bpm));
      d.appendChild(ps);
    }

    // draggable signal-chain strip (block reordering)
    d.appendChild(buildChainStrip(p));

    // per-block: bypass toggle + editable params, rendered in CHAIN order (blkIdx
    // stays the model-record index, so all edits keep keying by record index).
    curOrder(p).forEach((blkIdx) => {
      const b0 = p.blocks[blkIdx];
      if (!b0) return;
      const b = effBlock(p.slot, blkIdx, b0);
      if (!b.model && !b.params.length && !b0.model) return;
      const bd = document.createElement("div");
      bd.className = `block-detail blk-${b.block.replace(/[^a-z]/gi, "").toLowerCase()}`;
      const active = e.bypass[blkIdx] !== undefined ? e.bypass[blkIdx] : b.active;
      if (!active) bd.classList.add("bypassed");
      // active blocks open by default, bypassed collapsed; caret flips it (XOR)
      const bkey = `${p.slot}:${blkIdx}`;
      const showParams = active !== blockToggled.has(bkey);
      if (!showParams) bd.classList.add("collapsed");

      const head = document.createElement("div");
      head.className = "block-detail-head";
      // clicking anywhere on the header (except its controls) expands/collapses
      const toggleBlock = () => {
        if (blockToggled.has(bkey)) blockToggled.delete(bkey);
        else blockToggled.add(bkey);
        renderPresets();
      };
      head.addEventListener("click", toggleBlock);
      const caret = document.createElement("span");
      caret.className = "block-caret";
      caret.textContent = showParams ? "▾" : "▸";
      head.appendChild(caret);
      // plain "BLOCK · Type" label + a separate lighter model dropdown chip
      const bd_ = blockDisplay(b.block);
      const labelText = b.type && b.type !== bd_ ? `${bd_} · ${b.type}` : bd_;
      const modelText = officialOn() && b.official ? b.official : b.model || "—";
      const lbl = document.createElement("span");
      lbl.className = "block-label";
      lbl.textContent = labelText;
      head.appendChild(lbl);
      const pkey = `${p.slot}:${blkIdx}`;
      const chipBtn = document.createElement("button");
      chipBtn.type = "button";
      chipBtn.className =
        "model-chip" + (e.override[blkIdx] ? " changed" : "") + (pickerKey === pkey ? " open" : "");
      chipBtn.innerHTML = `${modelText} <span class="chip-caret">▾</span>`;
      chipBtn.title = "Change model / apply a library block";
      chipBtn.addEventListener("click", (ev) => {
        ev.stopPropagation();
        pickerKey = pickerKey === pkey ? null : pkey;
        renderPresets();
      });
      head.appendChild(chipBtn);
      const sw = document.createElement("button");
      sw.type = "button";
      sw.className = "state-toggle " + (active ? "on" : "off");
      sw.textContent = active ? "on" : "off";
      sw.title = "Toggle block on/off";
      sw.addEventListener("click", (ev) => {
        ev.stopPropagation();
        const next = !(e.bypass[blkIdx] !== undefined ? e.bypass[blkIdx] : b.active);
        e.bypass[blkIdx] = next;
        renderPresets();
        liveKick(p.slot);
      });
      head.appendChild(sw);

      // FS1 / FS2 assignment toggles (max 2 blocks per footswitch)
      const fs = curFS(p);
      ["fs1", "fs2"].forEach((fsKey) => {
        const on = fs[fsKey].includes(blkIdx);
        const full = fs[fsKey].length >= 2 && !on;
        const fb = document.createElement("button");
        fb.type = "button";
        fb.className = "fs-toggle" + (on ? " on" : "") + (full ? " full" : "");
        fb.textContent = fsKey.toUpperCase();
        fb.setAttribute("aria-pressed", on ? "true" : "false");
        fb.title = on
          ? `Remove this block from ${fsKey.toUpperCase()}`
          : full
            ? `${fsKey.toUpperCase()} already has its 2 blocks (device max)`
            : `Assign this block to ${fsKey.toUpperCase()}`;
        // always handle the click so it never falls through to the row toggle;
        // a full FS just warns instead of assigning (was: disabled + pointer-events
        // none let the click hit the header and collapse/expand the row).
        fb.addEventListener("click", (ev) => {
          ev.stopPropagation();
          if (full) {
            UI.toast(`${fsKey.toUpperCase()} already has its 2 blocks.`, "err");
            return;
          }
          toggleFS(p, blkIdx, fsKey);
        });
        head.appendChild(fb);
      });
      bd.appendChild(head);

      if (pickerKey === `${p.slot}:${blkIdx}`) bd.appendChild(buildPicker(p, blkIdx, b));

      if (b.params.length && showParams) {
        const grid = document.createElement("div");
        grid.className = "param-grid";
        b.params.forEach((pr) => {
          const cell = document.createElement("div");
          cell.className = "param editable" + (pr.toggle ? " toggle" : "");
          const value = curVal(p.slot, blkIdx, pr);
          const out = document.createElement("span");
          out.className = "pval";
          out.textContent = fmtParam(pr, value);
          cell.innerHTML = `<span class="pname">${pr.name}</span>`;
          cell.appendChild(out);
          if (pr.toggle) {
            // blue iOS-style pill switch (no checkbox, no "Off" text control)
            const sw = document.createElement("button");
            sw.type = "button";
            sw.className = "pswitch" + (Math.round(value) !== 0 ? " on" : "");
            sw.setAttribute("role", "switch");
            sw.setAttribute("aria-checked", Math.round(value) !== 0);
            sw.addEventListener("click", () => {
              const v = sw.classList.contains("on") ? 0 : 1;
              (e.params[blkIdx] ||= {})[pr.algId] = v;
              sw.classList.toggle("on", v === 1);
              sw.setAttribute("aria-checked", v === 1);
              out.textContent = fmtParam(pr, v);
              refreshSaveBar(p);
              liveKick(p.slot);
            });
            cell.appendChild(sw);
          } else {
            const inp = document.createElement("input");
            inp.type = "range"; inp.min = pr.min; inp.max = pr.max; inp.step = pr.step; inp.value = value;
            inp.addEventListener("input", () => {
              const v = Number(inp.value);
              (e.params[blkIdx] ||= {})[pr.algId] = v;
              out.textContent = fmtParam(pr, v);
              refreshSaveBar(p);
            });
            inp.addEventListener("change", () => liveKick(p.slot)); // write on release
            cell.appendChild(inp);
          }
          grid.appendChild(cell);
        });
        bd.appendChild(grid);
      }
      d.appendChild(bd);
    });

    return d;
  }

  function refreshSaveBar(p) {
    const bar = listEl.querySelector(`.save-bar[data-slot="${p.slot}"]`);
    if (bar) bar.classList.toggle("dirty", !!isDirty(p.slot));
  }

  async function downloadEdit(p) {
    const e = getEdit(p.slot);
    const note = listEl.querySelector(`.save-bar[data-slot="${p.slot}"] .save-note`);
    try {
      const r = await fetch("/api/device/edit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          patch_slot: p.slot, params: e.params, bypass: e.bypass,
          settings: e.settings, footswitches: e.footswitches || {}, models: e.models || {},
          name: e.name, order: e.order,
        }),
      });
      if (!r.ok) throw new Error((await r.json()).detail || `HTTP ${r.status}`);
      const fname = await UI.downloadResponse(r, "edited.prst");
      if (note) note.textContent = `Saved ${fname} — import via Suite (device is not written directly).`;
    } catch (err) {
      if (note) note.textContent = `Failed: ${err.message}`;
    }
  }

  // --- slot management: copy/paste + swap (device writes) --------------------
  let clipboard = null; // {slot, name} of a copied preset

  function slotName(slot) {
    const p = patches.find((x) => x.slot === slot);
    return p ? p.name : "(empty)";
  }

  async function refreshAfterSlotOp() {
    await loadInventory();
    render();
  }

  function copyPreset(p) {
    clipboard = { slot: p.slot, name: p.name };
    renderPresets(); // paste buttons appear on other slots
  }

  async function pastePreset(target) {
    if (!clipboard) return;
    if (clipboard.slot === target.slot) return;
    if (!(await UI.confirmDialog(`Overwrite slot ${target.slot} "${target.name}" with "${clipboard.name}" (from slot ${clipboard.slot})? Writes to the pedal. Close Valeton Suite first.`, "Paste"))) return;
    try {
      const j = await UI.jpost("/api/device/write",
        { patch_slot: clipboard.slot, target_slot: target.slot, confirm: true });
      if (!j.ok) throw new Error(j.error || "write failed");
      await refreshAfterSlotOp();
    } catch (e) {
      UI.toast(`Paste failed: ${e.message}`, "err");
    }
  }

  async function swapPreset(p, otherSlot) {
    if (otherSlot === p.slot) return;
    if (!(await UI.confirmDialog(`Swap slot ${p.slot} "${p.name}" ⇄ slot ${otherSlot} "${slotName(otherSlot)}"? Non-destructive, but writes both to the pedal. Close Valeton Suite first.`, "Swap"))) return;
    try {
      const j = await UI.jpost("/api/device/swap",
        { slot_a: p.slot, slot_b: otherSlot, confirm: true });
      if (!j.ok) throw new Error(j.error || "swap failed");
      await refreshAfterSlotOp();
    } catch (e) {
      UI.toast(`Swap failed: ${e.message}`, "err");
    }
  }

  function slotActions(p) {
    const row = document.createElement("div");
    row.className = "slot-actions";
    const stop = (fn) => (ev) => { ev.stopPropagation(); fn(); };

    const copy = document.createElement("button");
    copy.type = "button"; copy.className = "slot-act";
    copy.textContent = clipboard && clipboard.slot === p.slot ? "⧉ Copied" : "⧉ Copy";
    copy.title = "Copy this preset to the clipboard";
    copy.addEventListener("click", stop(() => copyPreset(p)));
    row.appendChild(copy);

    if (clipboard && clipboard.slot !== p.slot) {
      const paste = document.createElement("button");
      paste.type = "button"; paste.className = "slot-act paste";
      paste.textContent = `📋 Paste "${clipboard.name}"`;
      paste.title = `Overwrite slot ${p.slot} with the copied preset`;
      paste.addEventListener("click", stop(() => pastePreset(p)));
      row.appendChild(paste);
    }

    const sw = document.createElement("select");
    sw.className = "slot-act swap-sel";
    sw.innerHTML = `<option value="">⇄ Swap with…</option>` +
      patches.filter((x) => x.slot !== p.slot)
        .map((x) => `<option value="${x.slot}">#${x.slot} ${x.name}</option>`).join("");
    sw.addEventListener("click", (ev) => ev.stopPropagation());
    sw.addEventListener("change", () => {
      const other = Number(sw.value);
      sw.value = "";
      if (!Number.isNaN(other)) swapPreset(p, other);
    });
    row.appendChild(sw);

    const tmpl = document.createElement("button");
    tmpl.type = "button"; tmpl.className = "slot-act";
    tmpl.textContent = "★ Create template from";
    tmpl.title = "Save this preset's effects chain as a reusable template (build patches from it in Device Inspector)";
    tmpl.addEventListener("click", stop(() => createTemplateFrom(p)));
    row.appendChild(tmpl);
    return row;
  }

  async function writeToDevice(p) {
    const e = getEdit(p.slot);
    const note = listEl.querySelector(`.save-bar[data-slot="${p.slot}"] .save-note`);
    const ans = await UI.promptDialog(
      `Write "${p.name}" directly to the pedal. Enter the target slot (0–99) to OVERWRITE. Make sure Valeton Suite is closed.`,
      String(p.slot), "Next"
    );
    if (ans === null) return;
    const target = Number(ans);
    if (!Number.isInteger(target) || target < 0 || target > 99) {
      if (note) note.textContent = "Write cancelled: slot must be 0–99.";
      return;
    }
    if (!(await UI.confirmDialog(`Overwrite device slot ${target} with "${p.name}"? This writes to the pedal.`, "Overwrite"))) return;
    if (note) note.textContent = `Writing to slot ${target}…`;
    try {
      const j = await UI.jpost("/api/device/write", {
        patch_slot: p.slot, params: e.params, bypass: e.bypass,
        settings: e.settings, footswitches: e.footswitches || {}, models: e.models || {},
        name: e.name, order: e.order, target_slot: target, confirm: true,
      });
      if (!j.ok) throw new Error(j.error || "write failed");
      const vn = j.verified_name ? ` — slot now reads "${j.verified_name}"` : "";
      if (note) note.textContent = `✓ Written to slot ${target}${vn}.`;
    } catch (err) {
      if (note) note.textContent = `Write failed: ${err.message}`;
    }
  }

  // --- live edit (WebMIDI) ---------------------------------------------------
  function liveNote(slot, msg, cls) {
    const el = listEl.querySelector(`.save-bar[data-slot="${slot}"] .live-note`);
    if (el) { el.textContent = msg || ""; el.className = "subtitle live-note" + (cls ? " " + cls : ""); }
  }

  async function toggleLiveEdit(p) {
    if (liveSlot === p.slot) { // turn off
      liveSlot = null; liveBase = null;
      renderPresets();
      return;
    }
    if (!window.DeviceBridge || !DeviceBridge.webmidiAvailable()) {
      UI.toast("Live edit needs Chrome or Edge (WebMIDI).", "err");
      return;
    }
    const dev = DeviceBridge.device();
    if (dev && inventoryDevice && dev.key !== inventoryDevice.key) {
      UI.toast(`Pedal is a ${dev.name} but these presets are ${inventoryDevice.name}.`, "err");
    }
    try {
      if (!DeviceBridge.connected()) { liveNote(p.slot, "Connecting to pedal…"); await DeviceBridge.connect(); }
      liveNote(p.slot, `Reading slot ${p.slot} from the pedal…`);
      liveBase = await DeviceBridge.readSlotPrst(p.slot);
      liveSlot = p.slot;
      activeSlot = p.slot;
      renderPresets();
      liveNote(p.slot, "Live — changes write to the pedal on release.", "ok");
    } catch (e) {
      liveSlot = null; liveBase = null;
      liveNote(p.slot, `Live edit failed: ${e.message}`, "err");
    }
  }

  // The edit spec (params/bypass/settings/footswitches/models/name) for applyEdits.
  function editsSpec(slot) {
    const e = getEdit(slot);
    const spec = { params: e.params, bypass: e.bypass, settings: e.settings, footswitches: e.footswitches || {}, models: e.models || {} };
    if (e.name != null) spec.name = e.name;
    if (e.order != null) spec.order = e.order;
    return spec;
  }

  function liveKick(slot) {
    if (liveSlot !== slot || !liveBase) return;
    livePending = true;
    if (liveTimer) clearTimeout(liveTimer);
    liveTimer = setTimeout(() => liveWrite(slot), 200);
  }

  // Reject if `promise` doesn't settle in `ms`, so a stuck/throttled write can't
  // pin the UI on "Writing…" forever (e.g. a backgrounded tab throttles the send
  // pacing). The underlying send stays serialized, so no overlap on retry.
  function withTimeout(promise, ms, msg) {
    return Promise.race([
      promise,
      new Promise((_, rej) => setTimeout(() => rej(new Error(msg)), ms)),
    ]);
  }

  async function liveWrite(slot) {
    if (liveSlot !== slot || !liveBase || liveBusy) return; // busy: re-kicked when it finishes
    liveBusy = true;
    livePending = false;
    try {
      const edited = window.PRST.applyEdits(liveBase, editsSpec(slot));
      liveNote(slot, "Writing to the pedal…");
      await withTimeout(
        DeviceBridge.writeSlot(slot, edited), 15000,
        "write timed out — is this tab in the background? (bring it to the front)"
      );
      liveNote(slot, `✓ Live: slot ${slot} written`, "ok");
    } catch (err) {
      liveNote(slot, `Live write failed: ${err.message}`, "err");
    } finally {
      liveBusy = false;
      if (livePending) liveKick(slot); // edits arrived mid-write -> flush the latest
    }
  }

  // Re-pull a slot's live state from the pedal into the cache (so the row shows
  // what's actually on the device after a commit).
  async function refreshSlotFromDevice(slot) {
    const r = await UI.jpost("/api/device/select", { slot });
    if (r && r.ok && r.cache_updated) await loadInventory();
  }

  // Sync a slot's cache to bytes we already have. Static shim: push them in — instant,
  // and keeps the new NAME (a 0x41 body re-read can't recover a renamed patch's name).
  // Backend: fall back to a device re-read.
  async function syncSlotCache(slot, prstBytes) {
    if (window.__staticApi && window.__staticApi.setSlotBytes) {
      window.__staticApi.setSlotBytes(slot, prstBytes);
      await loadInventory().catch(() => {});
    } else {
      await refreshSlotFromDevice(slot).catch(() => {});
    }
  }

  // Restore original: write the pre-live snapshot back to the pedal, undoing every
  // live change, then exit live mode. This is the safety net for live editing.
  async function restoreLive(slot) {
    if (liveBase == null || liveSlot !== slot) return;
    if (liveTimer) { clearTimeout(liveTimer); liveTimer = null; }
    livePending = false;
    const base = liveBase;
    liveNote(slot, "Restoring original settings to the pedal…");
    try {
      await withTimeout(DeviceBridge.writeSlot(slot, base), 15000, "restore timed out (foreground the tab)");
    } catch (e) {
      liveNote(slot, `Restore failed: ${e.message}`, "err");
      return;
    }
    edits.delete(slot);
    liveSlot = null; liveBase = null;
    await syncSlotCache(slot, base);
    renderPresets();
    UI.toast(`Restored slot ${slot} to its original settings.`, "ok");
  }

  // Keep changes: the live edits are already on the pedal (each change wrote); flush
  // the latest, refresh the cache, and exit live mode with the edits committed.
  async function keepLive(slot) {
    if (liveSlot !== slot) return;
    if (liveTimer) { clearTimeout(liveTimer); liveTimer = null; }
    livePending = false;
    liveNote(slot, "Committing changes to the pedal…");
    const edited = window.PRST.applyEdits(liveBase, editsSpec(slot)); // ensure the very latest is written
    try {
      await withTimeout(DeviceBridge.writeSlot(slot, edited), 15000, "keep timed out (foreground the tab)");
    } catch (e) {
      liveNote(slot, `Keep failed: ${e.message}`, "err");
      return;
    }
    edits.delete(slot);
    liveSlot = null; liveBase = null;
    await syncSlotCache(slot, edited);
    renderPresets();
    UI.toast(`Kept your changes on slot ${slot}.`, "ok");
  }

  // 3-way modal for leaving a live-edited preset: keep / restore / cancel.
  function liveExitDialog(name, slot) {
    return new Promise((resolve) => {
      const ov = document.createElement("div");
      ov.className = "modal-overlay";
      ov.innerHTML = `
        <div class="modal-card">
          <h2>Live edits on "${name}"</h2>
          <p>You changed slot ${slot} live on the pedal. Keep those changes, or restore the original settings?</p>
          <div class="modal-actions">
            <button type="button" class="modal-btn" data-c="cancel">Cancel</button>
            <button type="button" class="modal-btn" data-c="restore">↺ Restore original</button>
            <button type="button" class="modal-btn primary" data-c="keep">✓ Keep changes</button>
          </div>
        </div>`;
      document.body.appendChild(ov);
      ov.addEventListener("click", (e) => {
        const c = e.target && e.target.getAttribute && e.target.getAttribute("data-c");
        if (c) { ov.remove(); resolve(c); }
        else if (e.target === ov) { ov.remove(); resolve("cancel"); }
      });
    });
  }

  // --- preset reordering (batched, minimal-write) ----------------------------
  // Rearrange presets across slots in memory, then commit as ONE finalize that
  // writes ONLY the slots whose content changed (writes = displaced presets, the
  // provable minimum). Because every write comes from an immutable pre-reorder
  // snapshot, there's no temp-slot juggling and the write order doesn't matter.
  // Requires a fresh full-bank snapshot first (so each preset moves with its
  // current on-device settings) and the static WebMIDI app.

  let reorderSnapshot = null; // { bytes: {slot->Uint8Array}, names: {slot->str}, takenAt }
  // TRUE only after a real device scan THIS page load. The snapshot lives in memory
  // (the shim's store.bytes) and resets to the factory bundle on reload, while the
  // LAST_SCAN_KEY timestamp persists in localStorage — so the "reuse recent snapshot"
  // fast path must gate on this, never on the timestamp alone, or a post-reload
  // reorder would rearrange BUNDLE bytes and overwrite the user's real presets.
  let bankScanned = false;
  const REORDER_WRITE_MS = 600; // measured per-slot write (~0.5–0.6s) — for time estimates
  const RECENT_SNAP_MS = 2 * 60 * 1000; // a scan this fresh can be reused without rescanning

  const bytesToB64 = (u) => btoa(String.fromCharCode.apply(null, u));
  const mkBtn = (text, cls) => { const b = document.createElement("button"); b.type = "button"; b.className = cls; b.textContent = text; return b; };
  const fmtDur = (ms) => { const s = Math.round(ms / 1000); if (s < 60) return `${s}s`; return `${Math.floor(s / 60)}m ${s % 60}s`; };
  function eqBytes(a, z) { if (!a || !z || a.length !== z.length) return false; for (let i = 0; i < a.length; i++) if (a[i] !== z[i]) return false; return true; }

  // Pure minimal-write plan: order[dest] = the ORIGIN slot whose preset should end
  // up at `dest`. Returns [{slot, from, bytes}] for only the destinations whose
  // assigned preset differs (by bytes) from what's there now. Two byte-identical
  // presets (e.g. blanks) swapping positions correctly produce no write.
  function planReorder(snapBytes, order) {
    const writes = [];
    for (let dest = 0; dest < order.length; dest++) {
      const bytes = snapBytes[order[dest]];
      if (!eqBytes(bytes, snapBytes[dest])) writes.push({ slot: dest, from: order[dest], bytes });
    }
    return writes;
  }

  // --- inline reorder mode (main list) ---------------------------------------
  // Presets are dragged by their ☰ grip directly in the main list. The first
  // grip-drag (or a grip click / the ⇅ button) enters reorder mode: rows render
  // collapsed, selection/filters/live-edit are locked out, and a sticky bar shows
  // pending moves + Finalize. The device snapshot is taken at Finalize time (the
  // snapshot dialog stays), so arranging costs nothing until the user commits.
  let reorderMode = null; // { order: [origin slot per destination index] } while active

  function reorderBlockReason() {
    if (!(window.DeviceBridge && DeviceBridge.webmidiAvailable())) return "Reorder needs Chrome or Edge (WebMIDI).";
    if (!window.__staticApi || !window.__staticApi.getAllSlotBytes) return "Reorder needs the static WebMIDI app.";
    if (filters.length || searchEl.value.trim()) return "Clear the search and filters first — reordering needs all 100 slots visible.";
    const slots = patches.map((p) => p.slot).sort((a, z) => a - z);
    if (slots.length !== 100 || slots[0] !== 0 || slots[99] !== 99) return "Reorder needs the full 100-preset inventory — rescan the device.";
    if (liveSlot != null) return "Finish the live edit first (keep or restore it), then reorder.";
    return null;
  }

  function enterReorderMode(rerender) {
    if (reorderMode) return;
    reorderMode = { order: patches.map((p) => p.slot).sort((a, z) => a - z) };
    expanded.clear();
    searchEl.disabled = true;
    ensureReorderBar();
    updateReorderBar();
    if (rerender) renderPresets();
  }

  // Teardown only — callers re-render (or commitReorderCache already did).
  function finishReorder() {
    reorderMode = null;
    reorderSnapshot = null;
    searchEl.disabled = false;
    const bar = $("reorder-inline-bar");
    if (bar) bar.remove();
    listEl.classList.remove("reordering");
  }

  function ensureReorderBar() {
    if ($("reorder-inline-bar")) return;
    const bar = document.createElement("div");
    bar.id = "reorder-inline-bar";
    bar.className = "reorder-inline-bar";
    const status = document.createElement("span");
    status.className = "reorder-inline-status subtitle";
    const spacer = document.createElement("div");
    spacer.className = "nav-spacer";
    const backup = mkBtn("⬇ Bank backup", "reorder-backup");
    backup.title = "Save a snapshot of all presets to a file before writing";
    backup.onclick = async () => { if (reorderSnapshot || (await acquireSnapshot())) downloadBankBackup(); };
    const cancel = mkBtn("Cancel", "modal-btn");
    cancel.onclick = () => { finishReorder(); render(); };
    const finalize = mkBtn("Finalize", "modal-btn primary reorder-finalize");
    finalize.disabled = true;
    finalize.onclick = finalizeInlineReorder;
    bar.append(status, spacer, backup, cancel, finalize);
    const listSection = listEl.closest("section.card");
    listSection.parentNode.insertBefore(bar, listSection);
  }

  function updateReorderBar() {
    const bar = $("reorder-inline-bar");
    if (!bar || !reorderMode) return;
    const moved = reorderMode.order.filter((slot, dest) => slot !== dest).length;
    bar.querySelector(".reorder-inline-status").textContent = moved
      ? `${moved} slot${moved > 1 ? "s" : ""} will change — up to ≈ ${fmtDur(moved * REORDER_WRITE_MS)} to write`
      : "Drag presets by the ☰ grip. Slot numbers stay put — presets move into them.";
    const finalize = bar.querySelector(".reorder-finalize");
    finalize.disabled = !moved;
    finalize.textContent = moved ? `Finalize — write ${moved}` : "Finalize";
  }

  // Gate → snapshot dialog → (scan) → reorderSnapshot ready. Shared by Finalize
  // and the pre-write bank backup.
  async function acquireSnapshot() {
    if (!(window.DeviceBridge && DeviceBridge.webmidiAvailable())) { UI.toast("Reorder needs Chrome or Edge (WebMIDI).", "err"); return false; }
    if (!window.__staticApi || !window.__staticApi.getAllSlotBytes) { UI.toast("Reorder needs the static WebMIDI app.", "err"); return false; }
    try { if (!DeviceBridge.connected()) await DeviceBridge.connect(); }
    catch (e) { UI.toast(`Connect the pedal first: ${e.message}`, "err"); return false; }

    const choice = await reorderSnapshotDialog();
    if (choice === "cancel") return false;
    if (choice === "fresh") { if (!(await runReorderScan())) return false; }

    const all = window.__staticApi.getAllSlotBytes();
    const slots = all ? Object.keys(all).map(Number).sort((a, z) => a - z) : [];
    if (slots.length !== 100 || slots[0] !== 0 || slots[99] !== 99) {
      UI.toast("Snapshot is incomplete — take a fresh snapshot and try again.", "err");
      return false;
    }
    reorderSnapshot = { bytes: all, names: {}, takenAt: Date.now() };
    for (const slot of slots) reorderSnapshot.names[slot] = window.PRST.readName(all[slot]);
    return true;
  }

  // Explain the up-front snapshot (the user's decision: force a fresh scan, but ask
  // first). Offers reuse only when a real device scan is very recent.
  function reorderSnapshotDialog() {
    return new Promise((resolve) => {
      const last = Number(localStorage.getItem(LAST_SCAN_KEY));
      const fresh = bankScanned && last && (Date.now() - last) < RECENT_SNAP_MS;
      const ov = document.createElement("div");
      ov.className = "modal-overlay";
      ov.innerHTML = `
        <div class="modal-card" style="text-align:left;max-width:440px">
          <h2 style="margin:0 0 .6rem">Reorder presets</h2>
          <p class="modal-msg" style="margin:0 0 1.2rem">
            Preset reordering is fully supported. First we take a clean snapshot of all
            100 presets so every one moves with its current settings. It reads one preset
            at a time and takes about 90 seconds.
          </p>
          <div class="modal-actions" style="justify-content:flex-end;gap:.6rem">
            <button type="button" class="modal-btn" data-c="cancel">Cancel</button>
            ${fresh ? `<button type="button" class="modal-btn" data-c="recent">Use snapshot from ${relTime(last)}</button>` : ""}
            <button type="button" class="modal-btn primary" data-c="fresh">Take snapshot &amp; reorder</button>
          </div>
        </div>`;
      document.body.appendChild(ov);
      ov.addEventListener("click", (e) => {
        const c = e.target && e.target.getAttribute && e.target.getAttribute("data-c");
        if (c) { ov.remove(); resolve(c); }
        else if (e.target === ov) { ov.remove(); resolve("cancel"); }
      });
    });
  }

  // Awaitable full-bank scan that drives the shared scan-progress UI. Resolves
  // true on success (snapshot in the cache), false on failure.
  async function runReorderScan() {
    $("scan-progress").hidden = false;
    $("scan-fill").style.width = "0%";
    $("scan-status").textContent = "Starting snapshot…";
    try {
      const r = await UI.jpost("/api/device/scan", {});
      if (!r.ok) throw new Error(r.error || "could not start scan");
    } catch (e) { $("scan-status").textContent = `Snapshot failed: ${e.message}`; return false; }
    for (;;) {
      await sleep(700);
      let st;
      try { st = await UI.jget("/api/device/scan/status"); } catch { continue; }
      const pct = st.total ? Math.round((st.done / st.total) * 100) : 0;
      $("scan-fill").style.width = `${pct}%`;
      $("scan-status").textContent = st.error
        ? `Snapshot failed: ${st.error}`
        : `Snapshot ${st.done}/${st.total}${st.current ? ` — ${st.current}` : ""}${st.errors ? ` (${st.errors} skipped)` : ""}`;
      if (!st.running) {
        if (st.error) return false;
        localStorage.setItem(LAST_SCAN_KEY, String(Date.now()));
        bankScanned = true;
        await loadInventory();
        updateDeviceHeader();
        render();
        $("scan-status").textContent = `✓ Snapshot ready (${st.written || st.done} presets).`;
        setTimeout(() => { $("scan-progress").hidden = true; }, 2000);
        return true;
      }
    }
  }

  function dragAfter(list, y) {
    const rows = [...list.querySelectorAll(".preset-row:not(.dragging)")];
    let best = { offset: -Infinity, el: null };
    for (const row of rows) {
      const box = row.getBoundingClientRect();
      const offset = y - box.top - box.height / 2;
      if (offset < 0 && offset > best.offset) best = { offset, el: row };
    }
    return best.el;
  }
  // the main list scrolls with the page, not inside a box — nudge the window
  function autoscroll(y) {
    const M = 70;
    if (y < M) window.scrollBy(0, -14);
    else if (window.innerHeight - y < M) window.scrollBy(0, 14);
  }

  function wireInlineReorder() {
    // a drag may only start from a grip: arm the row on grip pointerdown,
    // disarm on dragend — row clicks and text selection stay unaffected
    listEl.addEventListener("pointerdown", (e) => {
      const grip = e.target.closest(".reorder-grip");
      if (!grip || grip.classList.contains("disabled")) return;
      const row = grip.closest(".preset-row");
      if (row) row.draggable = true;
    });
    listEl.addEventListener("dragstart", (e) => {
      const row = e.target.closest(".preset-row");
      if (!row || !row.draggable) return;
      if (!reorderMode) {
        const reason = reorderBlockReason();
        if (reason) { e.preventDefault(); row.draggable = false; UI.toast(reason, "err"); return; }
        enterReorderMode(false); // no re-render mid-gesture — it would kill the drag
      }
      row.classList.add("dragging");
      e.dataTransfer.effectAllowed = "move";
      try { e.dataTransfer.setData("text/plain", String(row.__slot)); } catch { /* Safari */ }
    });
    listEl.addEventListener("dragend", (e) => {
      const row = e.target.closest(".preset-row");
      if (row) { row.classList.remove("dragging"); row.draggable = false; }
      if (!reorderMode) return;
      reorderMode.order = [...listEl.querySelectorAll(".preset-row")].map((r) => r.__slot);
      renderPresets(); // renumber + moved-highlight + collapse any stale detail
      updateReorderBar();
    });
    listEl.addEventListener("dragover", (e) => {
      if (!reorderMode) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      const dragging = listEl.querySelector(".preset-row.dragging");
      if (!dragging) return;
      const after = dragAfter(listEl, e.clientY);
      if (after == null) listEl.appendChild(dragging);
      else listEl.insertBefore(dragging, after);
      autoscroll(e.clientY);
    });
  }

  function downloadBankBackup() {
    if (!reorderSnapshot) return;
    const presets = Object.keys(reorderSnapshot.bytes).map(Number).sort((a, z) => a - z)
      .map((slot) => ({ slot, name: reorderSnapshot.names[slot], b64: bytesToB64(reorderSnapshot.bytes[slot]) }));
    const doc = { device: (inventoryDevice && inventoryDevice.key) || "gp50", takenAt: reorderSnapshot.takenAt, presets };
    const blob = new Blob([JSON.stringify(doc)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `${(inventoryDevice && inventoryDevice.key) || "gp50"}_bank_backup.json`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 4000);
    UI.toast("Saved a bank backup (all 100 presets).", "ok");
  }

  async function finalizeInlineReorder() {
    if (!reorderMode) return;
    const order = reorderMode.order;
    if (new Set(order).size !== order.length) { UI.toast("Internal error: the new order lost a preset — aborting.", "err"); return; }
    if (!(await acquireSnapshot())) return;
    const writes = planReorder(reorderSnapshot.bytes, order);
    if (!writes.length) { UI.toast("No changes to write — the pedal already matches this order.", "ok"); finishReorder(); render(); return; }
    const est = fmtDur(writes.length * REORDER_WRITE_MS);
    const ok = await UI.confirmDialog(
      `Write ${writes.length} preset${writes.length > 1 ? "s" : ""} to the pedal to apply the new order? This takes about ${est}. Keep this tab in the foreground and don't unplug the pedal until it finishes. Make sure Valeton Suite is closed.`,
      `Write ${writes.length} presets`);
    if (!ok) return;
    await runReorderWrites(writes);
  }

  async function commitReorderCache(writes) {
    if (window.__staticApi && window.__staticApi.setSlotBytes) {
      for (const w of writes) window.__staticApi.setSlotBytes(w.slot, w.bytes);
      await loadInventory().catch(() => {});
    } else {
      for (const w of writes) await refreshSlotFromDevice(w.slot).catch(() => {});
    }
    updateDeviceHeader();
    render();
  }

  // Swap the modal footer for a progress bar and drive the writes. On any failure
  // we stop and surface retry / rollback rather than pressing on blindly.
  function reorderProgressUI(foot) {
    foot.innerHTML = "";
    const wrap = document.createElement("div");
    wrap.className = "reorder-progress";
    wrap.innerHTML = `<div class="scan-bar"><div class="reorder-fill" style="width:0%"></div></div><span class="reorder-prog-text subtitle"></span>`;
    foot.appendChild(wrap);
    return { fill: wrap.querySelector(".reorder-fill"), txt: wrap.querySelector(".reorder-prog-text") };
  }

  async function runReorderWrites(writes) {
    const bar = $("reorder-inline-bar");
    const { fill, txt } = reorderProgressUI(bar);
    const done = [];
    for (let i = 0; i < writes.length; i++) {
      const w = writes[i];
      txt.textContent = `Writing ${i + 1}/${writes.length} — slot ${w.slot} (was #${w.from})…`;
      try {
        await withTimeout(DeviceBridge.writeSlot(w.slot, w.bytes), 15000, "write timed out — is this tab in the background? (bring it to the front)");
        done.push(w);
        fill.style.width = `${Math.round(((i + 1) / writes.length) * 100)}%`;
      } catch (e) {
        await reorderFailure(writes, done, { w, i, error: e.message });
        return;
      }
    }
    txt.textContent = "Updating…";
    reorderMode = null; // the refresh below renders the normal list again
    await commitReorderCache(writes);
    UI.toast(`Reordered — wrote ${writes.length} preset${writes.length > 1 ? "s" : ""} to the pedal.`, "ok");
    finishReorder();
  }

  async function reorderFailure(writes, done, failed) {
    reorderMode = null;
    await commitReorderCache(done); // the list below reflects what actually got written
    const bar = $("reorder-inline-bar");
    bar.innerHTML = "";
    const msg = document.createElement("p");
    msg.className = "reorder-fail-msg";
    msg.textContent = `Write failed at slot ${failed.w.slot} (${failed.error}). ${done.length} of ${writes.length} presets were written — your bank is partly reordered.`;
    const leave = mkBtn("Leave as-is", "modal-btn");
    leave.onclick = () => { finishReorder(); render(); };
    const rollback = mkBtn("↺ Roll back written slots", "modal-btn");
    rollback.onclick = () => rollbackReorder(done);
    const retry = mkBtn(`Retry remaining (${writes.length - failed.i})`, "modal-btn primary");
    retry.onclick = () => runReorderWrites(writes.slice(failed.i));
    const row = document.createElement("div");
    row.className = "reorder-foot-btns";
    row.append(leave, rollback, retry);
    bar.append(msg, row);
  }

  // Rewrite the ORIGINAL bytes back to every slot we changed, undoing the partial
  // reorder. Originals come from the immutable snapshot.
  async function rollbackReorder(done) {
    const bar = $("reorder-inline-bar");
    const { fill, txt } = reorderProgressUI(bar);
    const rolled = [];
    for (let i = 0; i < done.length; i++) {
      const dest = done[i].slot;
      txt.textContent = `Rolling back ${i + 1}/${done.length} — slot ${dest}…`;
      try {
        await withTimeout(DeviceBridge.writeSlot(dest, reorderSnapshot.bytes[dest]), 15000, "rollback timed out (foreground the tab)");
        rolled.push({ slot: dest, bytes: reorderSnapshot.bytes[dest] });
        fill.style.width = `${Math.round(((i + 1) / done.length) * 100)}%`;
      } catch (e) { UI.toast(`Rollback stopped at slot ${dest}: ${e.message}`, "err"); break; }
    }
    await commitReorderCache(rolled);
    UI.toast(`Rolled back ${rolled.length} slot${rolled.length === 1 ? "" : "s"} to the original presets.`, rolled.length === done.length ? "ok" : "err");
    finishReorder();
    render();
  }

  function renderPresets() {
    listEl.classList.toggle("reordering", !!reorderMode);
    if (reorderMode) { renderReorderList(); return; }
    const shown = patches.filter((p) => matchesFilters(p) && matchesSearch(p));
    listEl.innerHTML = "";
    emptyEl.hidden = shown.length > 0;
    countEl.textContent = `${shown.length} of ${patches.length} presets`;
    shown.forEach((p) => {
      const li = document.createElement("li");
      li.className = "preset-row";
      li.__slot = p.slot;
      const isOpen = expanded.has(p.slot);
      const isActive = p.slot === activeSlot;
      if (isActive) li.classList.add("preset-active");
      const head = document.createElement("div");
      head.className = "preset-head";
      head.innerHTML =
        `<span class="preset-num">#${p.slot}</span> <span class="preset-name">${curName(p).replace(/</g, "&lt;")}</span>` +
        (isActive ? ' <span class="badge active-badge">● Active on pedal</span>' : "") +
        (p.uses_snaptone ? ' <span class="badge st">SnapTone</span>' : "");
      // reorder grip (left of the slot number) → drag the row to a new slot
      if (window.DeviceBridge && DeviceBridge.webmidiAvailable()) {
        const grip = document.createElement("button");
        grip.type = "button"; grip.className = "reorder-grip"; grip.textContent = "☰";
        const reason = reorderBlockReason();
        if (reason) { grip.classList.add("disabled"); grip.title = reason; }
        else grip.title = "Drag to move this preset to a new slot (click to enter reorder mode)";
        grip.addEventListener("click", (ev) => {
          ev.stopPropagation();
          if (reorderMode) return;
          const r = reorderBlockReason();
          if (r) { UI.toast(r, "err"); return; }
          enterReorderMode(true);
        });
        head.insertBefore(grip, head.firstChild);
      }
      // full block chain, right-aligned; bypassed blocks are hidden here (not dimmed)
      // to keep the collapsed header uncluttered — the expanded detail below still
      // shows every block, active or not.
      const chips = document.createElement("div");
      chips.className = "chip-row";
      const chain = p.blocks.filter((b) => b.model);
      const engaged = chain.filter((b) => b.active);
      engaged.forEach((b) => chips.appendChild(chip(b)));
      if (!chain.length)
        chips.innerHTML = '<span class="subtitle">empty preset</span>';
      else if (!engaged.length)
        chips.innerHTML = '<span class="subtitle">all blocks off</span>';
      head.appendChild(chips);
      const caret = document.createElement("span");
      caret.className = "caret";
      caret.textContent = isOpen ? "▾" : "▸";
      head.appendChild(caret);
      head.addEventListener("click", () => selectPreset(p));
      li.appendChild(head);
      if (isOpen) {
        li.appendChild(renderDetail(p));
        li.appendChild(slotActions(p));
      }
      listEl.appendChild(li);
    });
  }

  // reorder-mode rows: compact, collapsed, numbered by DESTINATION slot
  function renderReorderList() {
    const bySlot = new Map(patches.map((p) => [p.slot, p]));
    listEl.innerHTML = "";
    emptyEl.hidden = true;
    countEl.textContent = `reordering ${patches.length} presets`;
    reorderMode.order.forEach((slot, dest) => {
      const p = bySlot.get(slot);
      if (!p) return;
      const li = document.createElement("li");
      li.className = "preset-row";
      li.__slot = slot;
      if (slot !== dest) li.classList.add("moved");
      const head = document.createElement("div");
      head.className = "preset-head";
      const grip = document.createElement("button");
      grip.type = "button"; grip.className = "reorder-grip"; grip.textContent = "☰";
      grip.title = "Drag to a new slot";
      head.appendChild(grip);
      head.insertAdjacentHTML("beforeend",
        `<span class="preset-num">#${dest}</span> <span class="preset-name">${curName(p).replace(/</g, "&lt;")}</span>` +
        (slot !== dest ? ` <span class="reorder-orig">was #${slot}</span>` : ""));
      const chips = document.createElement("div");
      chips.className = "chip-row";
      const chain = p.blocks.filter((b) => b.model);
      chain.forEach((b) => chips.appendChild(chip(b)));
      if (!chain.length) chips.innerHTML = '<span class="subtitle">empty preset</span>';
      head.appendChild(chips);
      li.appendChild(head);
      listEl.appendChild(li);
    });
  }

  // --- saved filter sets (localStorage) -------------------------------------
  function renderSaved() {
    const box = $("saved-filters");
    box.innerHTML = "";
    loadSaved().forEach((entry, i) => {
      const pill = document.createElement("span");
      pill.className = "saved-pill";
      const apply = document.createElement("button");
      apply.type = "button";
      apply.className = "saved-apply";
      apply.textContent = entry.name;
      apply.title = entry.filters.map(filterLabel).join(" AND ") + (entry.search ? ` · "${entry.search}"` : "");
      apply.addEventListener("click", () => {
        filters = entry.filters.map((f) => ({ ...f }));
        searchEl.value = entry.search || "";
        render();
      });
      const del = document.createElement("button");
      del.type = "button";
      del.className = "saved-del";
      del.textContent = "✕";
      del.title = "Delete saved filter";
      del.addEventListener("click", () => {
        const list = loadSaved();
        list.splice(i, 1);
        persistSaved(list);
        renderSaved();
      });
      pill.appendChild(apply);
      pill.appendChild(del);
      box.appendChild(pill);
    });
  }

  async function saveCurrent() {
    if (!filters.length && !searchEl.value.trim()) return;
    const suggested = filters.map(filterLabel).join(", ") || searchEl.value.trim();
    const name = await UI.promptDialog("Name this filter set:", suggested, "Save");
    if (!name) return;
    const list = loadSaved();
    list.push({ name, filters: filters.map((f) => ({ ...f })), search: searchEl.value.trim() });
    persistSaved(list);
    renderSaved();
  }

  function render() {
    renderActiveFilters();
    renderPresets();
    $("save-filter").disabled = !filters.length && !searchEl.value.trim();
  }

  $("save-filter").addEventListener("click", saveCurrent);
  $("official-toggle").addEventListener("change", renderPresets);
  searchEl.addEventListener("input", render);

  async function loadInventory() {
    const [inv, fac] = await Promise.all([
      UI.jget("/api/device/inventory"),
      UI.jget("/api/device/facets"),
    ]);
    patches = inv.patches || [];
    facets = fac;
    inventoryDevice = inv.device || null;
    UI.setDeviceBadge(inv.device);
  }

  // --- live device: connection status + click-to-select ----------------------

  async function refreshDeviceStatus() {
    const btn = $("device-conn");
    try {
      const st = await UI.jget("/api/device/status");
      deviceLive = { connected: !!st.connected, device: st.device || null };
    } catch {
      deviceLive = { connected: false, device: null };
    }
    if (btn) {
      const on = deviceLive.connected;
      const name = deviceLive.device ? deviceLive.device.name : "device";
      btn.textContent = on ? `● ${name} connected` : "○ No device";
      btn.classList.toggle("connected", on);
      btn.title = on
        ? "Connected — click a preset to switch the pedal to it. Click here to re-check."
        : "No device found. Connect via USB with Suite closed, then click to re-check.";
    }
    renderPresets();
  }

  async function selectPreset(p) {
    if (reorderMode) return; // rows aren't selectable while arranging
    // leaving a live-edited preset for another one? decide what to do with the edits
    if (liveSlot != null && liveSlot !== p.slot) {
      if (isDirty(liveSlot)) {
        const choice = await liveExitDialog(slotName(liveSlot), liveSlot);
        if (choice === "cancel") return;
        if (choice === "restore") await restoreLive(liveSlot);
        else await keepLive(liveSlot);
        if (liveSlot != null) return; // exit didn't complete (e.g. write failed) — stay put
      } else {
        liveSlot = null; liveBase = null; // live on but nothing changed — just drop it
      }
    }
    if (!deviceLive.connected) {
      // browse mode (no pedal): multi-open toggle, unchanged
      if (expanded.has(p.slot)) expanded.delete(p.slot);
      else expanded.add(p.slot);
      renderPresets();
      return;
    }
    // active-preset mode: solo-expand (collapse others), then select on the pedal
    const already = expanded.has(p.slot);
    expanded.clear();
    if (!already) expanded.add(p.slot);
    renderPresets();
    if (already) return; // re-clicking the open one just collapses it; don't re-select
    if (
      deviceLive.device &&
      inventoryDevice &&
      deviceLive.device.key !== inventoryDevice.key
    ) {
      UI.toast(
        `Pedal is a ${deviceLive.device.name} but these presets are ${inventoryDevice.name} — slot #${p.slot} may differ on the pedal.`,
        "err"
      );
    }
    try {
      const r = await UI.jpost("/api/device/select", { slot: p.slot });
      if (r.ok) {
        activeSlot = p.slot;
        // the pedal's live state for this slot was just pulled into the cache —
        // re-fetch so the expanded detail shows current settings, not a stale scan
        if (r.cache_updated) {
          try {
            await loadInventory();
          } catch {
            /* keep showing cached values if the refresh re-fetch fails */
          }
        }
        renderPresets();
        UI.toast(
          `Pedal switched to #${p.slot} ${p.name}` +
            (r.cache_updated ? " · pulled live settings" : ""),
          "ok"
        );
      } else {
        UI.toast(r.error || "could not select preset", "err");
      }
    } catch (e) {
      UI.toast(`Select failed: ${e.message}`, "err");
    }
  }

  // --- device header: empty-state hero (no data) vs "last scan · rescan" bar ----
  const LAST_SCAN_KEY = "gp50_lastScan";
  function relTime(ts) {
    if (!ts) return null;
    const s = Math.floor((Date.now() - ts) / 1000);
    if (s < 60) return "just now";
    const m = Math.floor(s / 60);
    if (m < 60) return `${m} min ago`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h} hr ago`;
    return `${Math.floor(h / 24)} days ago`;
  }
  function updateDeviceHeader() {
    const has = patches.length > 0;
    $("device-bar").hidden = !has;
    $("empty-hero").hidden = has;
    const filterCard = document.querySelector(".filter-card");
    const listSection = listEl.closest("section");
    if (filterCard) filterCard.hidden = !has;
    if (listSection) listSection.hidden = !has;
    if (has) {
      const t = relTime(Number(localStorage.getItem(LAST_SCAN_KEY)));
      $("device-status-text").innerHTML =
        `<b>${patches.length} presets</b>` +
        (t ? ` · scanned from your device ${t}` : ` from your device`) +
        ` &nbsp;<span class="rescan-hint">— changed presets on the pedal? Rescan to sync.</span>`;
    }
  }

  // confirm/prompt modals live in the shared core (ui_core.js, window.UI)

  async function createTemplateFrom(p) {
    const name = await UI.promptDialog(
      `Save preset #${p.slot} "${p.name}" as a reusable template. Name it (e.g. "Metal", "80s Clean"):`,
      "", "Create template");
    if (!name) return;
    try {
      await UI.jpost("/api/device/templates/from-patch", { name, source_slot: p.slot });
      const note = listEl.querySelector(`.save-bar[data-slot="${p.slot}"] .save-note`);
      if (note) { note.textContent = `★ Saved template "${name}" — use it in Device Inspector.`; }
      UI.toast(`★ Saved template "${name}".`, "ok");
    } catch (e) {
      UI.toast(`Could not save template: ${e.message}`, "err");
    }
  }

  // --- scan all presets from the device (one at a time; no bulk read exists) -----
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  async function pollScan() {
    const fill = $("scan-fill");
    const status = $("scan-status");
    for (;;) {
      let st;
      try {
        st = await UI.jget("/api/device/scan/status");
      } catch {
        await sleep(1000);
        continue;
      }
      const pct = st.total ? Math.round((st.done / st.total) * 100) : 0;
      fill.style.width = `${pct}%`;
      status.textContent = st.error
        ? `Scan failed: ${st.error}`
        : `Scanning ${st.done}/${st.total}${st.current ? ` — ${st.current}` : ""}${st.errors ? ` (${st.errors} skipped)` : ""}`;
      if (!st.running) {
        if (!st.error) {
          status.textContent = `Scanned ${st.written || st.done} presets${st.errors ? `, ${st.errors} skipped` : ""}. Loading…`;
          localStorage.setItem(LAST_SCAN_KEY, String(Date.now()));
          bankScanned = true;
          await loadInventory();
          await loadModelsAndLib();
          buildFilterBar();
          updateDeviceHeader();
          render();
          status.textContent = `✓ Loaded ${patches.length} presets from the device.`;
          setTimeout(() => { $("scan-progress").hidden = true; }, 3000); // tidy up when done
        }
        scanButtons().forEach((b) => (b.disabled = false));
        return;
      }
      await sleep(700);
    }
  }

  const scanButtons = () => [$("scan-btn"), $("scan-btn-hero")].filter(Boolean);

  async function startScan() {
    if (!(await UI.confirmDialog("Begin scan of all 100 presets?\n\nPlease ensure your device is connected to your computer via USB cable.", "Begin scan"))) return;
    scanButtons().forEach((b) => (b.disabled = true));
    $("scan-progress").hidden = false;
    $("scan-fill").style.width = "0%";
    $("scan-status").textContent = "Starting…";
    try {
      const r = await UI.jpost("/api/device/scan", {});
      if (!r.ok) throw new Error(r.error || "could not start scan");
      pollScan();
    } catch (e) {
      $("scan-status").textContent = `Failed: ${e.message}`;
      scanButtons().forEach((b) => (b.disabled = false));
    }
  }

  scanButtons().forEach((b) => b.addEventListener("click", startScan));

  async function init() {
    try {
      await loadInventory();
    } catch (e) {
      $("scan-status").textContent = `Could not load presets: ${e.message}`;
      $("empty-hero").hidden = false;
      return;
    }
    await loadModelsAndLib();
    buildFilterBar();
    renderSaved();
    updateDeviceHeader();
    render();
    wireInlineReorder(); // grip-drag reordering on the main list
    refreshDeviceStatus(); // non-blocking: light up click-to-select if a pedal is present
  }

  const connBtn = $("device-conn");
  if (connBtn) connBtn.addEventListener("click", refreshDeviceStatus);

  // test/debug surface for the reorder planner (pure) — mirrors nothing else
  window.__reorderTest = { planReorder, eqBytes };
  window.__editTest = { editsSpec, isDirty, curOrder }; // block-reorder wiring checks

  init();
})();
