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

  const activeBlocks = (p) => p.blocks.filter((b) => b.active);

  function filterLabel(f) {
    return [f.block, f.type, f.model].filter(Boolean).join(" · ");
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
    const blockSel = mkSelect(["— block —", ...facets.blocks.map((b) => b.block)]);
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
      fill(modelSel, ["any model", ...(fb ? fb.models : [])]);
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

  function chip(b) {
    const c = document.createElement("button");
    c.type = "button";
    c.className = `chip blk-${b.block.replace(/[^a-z]/gi, "").toLowerCase()}`;
    c.textContent = b.label;
    c.title = "Filter by this block · type · model";
    c.addEventListener("click", () =>
      addFilter({ block: b.block, type: b.type, model: b.model })
    );
    return c;
  }

  function renderPresets() {
    const shown = patches.filter((p) => matchesFilters(p) && matchesSearch(p));
    listEl.innerHTML = "";
    emptyEl.hidden = shown.length > 0;
    countEl.textContent = `${shown.length} of ${patches.length} presets`;
    shown.forEach((p) => {
      const li = document.createElement("li");
      li.className = "preset-row";
      const head = document.createElement("div");
      head.className = "preset-head";
      head.innerHTML = `<span class="preset-num">#${p.slot}</span> <span class="preset-name">${p.name}</span>` +
        (p.uses_snaptone ? ' <span class="badge st">SnapTone</span>' : "");
      const chips = document.createElement("div");
      chips.className = "chip-row";
      activeBlocks(p).forEach((b) => chips.appendChild(chip(b)));
      if (!activeBlocks(p).length)
        chips.innerHTML = '<span class="subtitle">empty preset</span>';
      li.appendChild(head);
      li.appendChild(chips);
      listEl.appendChild(li);
    });
  }

  function render() {
    renderActiveFilters();
    renderPresets();
  }

  searchEl.addEventListener("input", renderPresets);

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
    render();
  }

  init();
})();
