"use strict";

// GP-50 Preset Explorer. Renders every preset's ACTIVE chain at
// Block · Type · Model granularity and filters over it. Reads real parsed data
// from /api/device/inventory (patches carry a `blocks` array) + /api/device/facets.
(() => {
  const $ = (id) => document.getElementById(id);
  const searchEl = $("preset-search");
  const filterBar = $("filter-bar");
  const activeFiltersEl = $("active-filters");
  const listEl = $("preset-list");
  const emptyEl = $("preset-empty");
  const countEl = $("result-count");

  let patches = [];
  let facets = { blocks: [] };
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
    if (!filters.some((x) => sameFilter(x, f))) filters.push(f);
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
    const hay = `${p.slot} ${p.name} ` + activeBlocks(p).map((b) => b.label).join(" ");
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

    function refresh() {
      const fb = facets.blocks.find((b) => b.block === blockSel.value);
      typeSel.innerHTML = "";
      modelSel.innerHTML = "";
      fill(typeSel, ["any type", ...(fb ? fb.types : [])]);
      // models carry an optional official name -> show "Device / Official"
      const anyOpt = document.createElement("option");
      anyOpt.textContent = "any model";
      anyOpt.value = "";
      modelSel.appendChild(anyOpt);
      (fb ? fb.models : []).forEach((m) => {
        const opt = document.createElement("option");
        opt.value = m.model;
        opt.textContent = m.official ? `${m.model} / ${m.official}` : m.model;
        modelSel.appendChild(opt);
      });
      addBtn.disabled = !fb;
    }
    blockSel.addEventListener("change", refresh);
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
    const useOfficial = officialOn() && b.official;
    c.textContent = useOfficial ? b.label_official : b.label;
    if (useOfficial) c.classList.add("official");
    c.title = b.official
      ? `Device: ${b.label}\nOfficial: ${b.label_official}`
      : "Filter by this block · type · model";
    c.addEventListener("click", () =>
      addFilter({ block: b.block, type: b.type, model: b.model })
    );
    return c;
  }

  const expanded = new Set(); // preset slots currently expanded

  function blockLabel(b) {
    return officialOn() && b.official ? b.label_official : b.label;
  }

  function renderDetail(p) {
    const d = document.createElement("div");
    d.className = "preset-detail";
    // patch settings
    const s = p.settings || {};
    const settingBits = [];
    if (s.patch_vol !== undefined) settingBits.push(`Patch VOL <b>${s.patch_vol}</b>`);
    if (s.bpm !== undefined) settingBits.push(`BPM <b>${s.bpm}</b>`);
    if (settingBits.length) {
      const ps = document.createElement("div");
      ps.className = "patch-settings";
      ps.innerHTML = settingBits.join(" &nbsp;·&nbsp; ");
      d.appendChild(ps);
    }
    // every block, active first-class + bypassed dimmed
    p.blocks.forEach((b) => {
      if (!b.model && !b.params.length) return; // skip truly empty slots
      const bd = document.createElement("div");
      bd.className = "block-detail" + (b.active ? "" : " bypassed");
      const state = b.active ? "on" : "off";
      const chipCls = `chip blk-${b.block.replace(/[^a-z]/gi, "").toLowerCase()}`;
      bd.innerHTML =
        `<div class="block-detail-head"><span class="${chipCls}">${blockLabel(b)}</span>` +
        `<span class="state ${state}">${state}</span></div>`;
      if (b.params.length) {
        const grid = document.createElement("div");
        grid.className = "param-grid";
        b.params.forEach((pr) => {
          const cell = document.createElement("div");
          cell.className = "param" + (pr.toggle ? " toggle" : "");
          cell.innerHTML = `<span class="pname">${pr.name}</span><span class="pval">${pr.display}</span>`;
          grid.appendChild(cell);
        });
        bd.appendChild(grid);
      }
      d.appendChild(bd);
    });
    return d;
  }

  function renderPresets() {
    const shown = patches.filter((p) => matchesFilters(p) && matchesSearch(p));
    listEl.innerHTML = "";
    emptyEl.hidden = shown.length > 0;
    countEl.textContent = `${shown.length} of ${patches.length} presets`;
    shown.forEach((p) => {
      const li = document.createElement("li");
      li.className = "preset-row";
      const isOpen = expanded.has(p.slot);
      const head = document.createElement("div");
      head.className = "preset-head";
      head.innerHTML =
        `<span class="caret">${isOpen ? "▾" : "▸"}</span>` +
        `<span class="preset-num">#${p.slot}</span> <span class="preset-name">${p.name}</span>` +
        (p.uses_snaptone ? ' <span class="badge st">SnapTone</span>' : "");
      head.addEventListener("click", () => {
        if (expanded.has(p.slot)) expanded.delete(p.slot);
        else expanded.add(p.slot);
        renderPresets();
      });
      const chips = document.createElement("div");
      chips.className = "chip-row";
      activeBlocks(p).forEach((b) => chips.appendChild(chip(b)));
      if (!activeBlocks(p).length)
        chips.innerHTML = '<span class="subtitle">empty preset</span>';
      li.appendChild(head);
      li.appendChild(chips);
      if (isOpen) li.appendChild(renderDetail(p));
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

  function saveCurrent() {
    if (!filters.length && !searchEl.value.trim()) return;
    const suggested = filters.map(filterLabel).join(", ") || searchEl.value.trim();
    const name = prompt("Name this filter set:", suggested);
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

  async function init() {
    try {
      const [inv, fac] = await Promise.all([
        fetch("/api/device/inventory").then((r) => r.json()),
        fetch("/api/device/facets").then((r) => r.json()),
      ]);
      patches = inv.patches || [];
      facets = fac;
      if (inv.source) $("source-note").textContent = inv.source;
    } catch (e) {
      $("source-note").textContent = `Could not load presets: ${e.message}`;
      return;
    }
    buildFilterBar();
    renderSaved();
    render();
  }

  init();
})();
