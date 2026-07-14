"use strict";
// Variant B — Two-pane manager. Left rail lists every asset (SnapTones / user IRs
// / factory cabs); the right pane shows the selected asset's dependencies + build.
(() => {
  const DC = window.DeviceCore;
  const $ = (id) => document.getElementById(id);
  let sel = null; // {kind, slot}

  function badge(kind, slot) {
    const n = DC.usageCount(kind, slot);
    return `<span class="usage-badge ri-badge${n ? "" : " unused"}">${n || "0"}</span>`;
  }

  function railItem(kind, it) {
    const name = kind === "snaptone" ? it.name : DC.irLabel(it);
    const li = document.createElement("li");
    li.className = "dc-rail-item";
    if (sel && sel.kind === kind && sel.slot === it.slot) li.classList.add("sel");
    li.innerHTML = `<span class="ri-slot">#${it.slot > 0xfffff ? "IR" : it.slot}</span>` +
      `<span>${name}</span>${badge(kind, it.slot)}`;
    li.addEventListener("click", () => { sel = { kind, slot: it.slot }; render(); });
    return li;
  }

  function fillList(el, kind, items) {
    el.innerHTML = "";
    items.forEach((it) => el.appendChild(railItem(kind, it)));
  }

  function renderDetail() {
    const box = $("detail");
    if (!sel) {
      box.innerHTML = `<div class="dc-detail-empty" id="detail-empty">Select a capture or cab on the left to see what uses it.</div>`;
      return;
    }
    const asset = (sel.kind === "ir" ? DC.state.userIrs.concat(DC.state.factoryCabs) : DC.state.snaptones)
      .find((x) => x.slot === sel.slot);
    const name = asset ? (sel.kind === "ir" ? DC.irLabel(asset) : asset.name) : `#${sel.slot}`;
    const patches = DC.usagePatches(sel.kind, sel.slot);
    const head = document.createElement("div");
    head.className = "dc-section-head";
    head.innerHTML = `<h2>${name}</h2><span class="count">${sel.kind === "snaptone" ? "SnapTone" : "IR / cab"}</span><span class="spacer"></span>`;
    if (sel.kind === "snaptone") {
      const b = document.createElement("button");
      b.type = "button"; b.className = "scan-btn primary"; b.textContent = "Build a patch from this →";
      b.addEventListener("click", () => DC.openBuildModal({ snaptoneSlot: sel.slot }));
      head.appendChild(b);
    }
    box.innerHTML = "";
    box.appendChild(head);
    const sub = document.createElement("p");
    sub.className = "subtitle";
    sub.textContent = patches.length
      ? `Used by ${patches.length} patch${patches.length === 1 ? "" : "es"}:`
      : "Not used by any patch — safe to overwrite or remove.";
    box.appendChild(sub);
    const ul = document.createElement("ul");
    ul.className = "dep-list";
    patches.forEach((p) => {
      const li = document.createElement("li");
      li.className = "dep-row";
      const chain = p.uses_snaptone ? `N→S: ${p.snaptone_name}` : `${p.amp_name || "?"} · ${p.ir_name || "?"}`;
      li.innerHTML = `<span class="dep-slot">#${p.slot}</span><span>${p.name}</span><span class="dep-meta">${chain}</span>`;
      ul.appendChild(li);
    });
    box.appendChild(ul);
  }

  function renderTemplates() {
    const list = $("tmpl-list"), empty = $("tmpl-empty");
    list.innerHTML = "";
    $("tmpl-count").textContent = `(${DC.state.templates.length})`;
    if (!DC.state.templates.length) { empty.hidden = false; return; }
    empty.hidden = true;
    DC.state.templates.forEach((t) => {
      const chain = ((t.summary && t.summary.chain) || []).map((b) => b.model || b.block).join(" · ");
      const li = document.createElement("li");
      li.className = "tmpl-row";
      li.innerHTML = `<span class="tr-name">${t.name}</span><span class="tr-chain">${chain || "(no active blocks)"}</span>`;
      const del = document.createElement("button");
      del.type = "button"; del.className = "tr-del"; del.textContent = "✕";
      del.addEventListener("click", async () => {
        if (!(await DC.confirmDialog(`Delete template "${t.name}"?`, "Delete"))) return;
        await DC.deleteTemplate(t.id); DC.toast("Template deleted.");
      });
      li.appendChild(del);
      list.appendChild(li);
    });
  }

  function render() {
    const s = DC.state;
    $("st-count").textContent = `(${s.snaptones.length})`;
    $("ir-count").textContent = `(${s.userIrs.length})`;
    $("cab-count").textContent = `(${s.factoryCabs.length})`;
    fillList($("st-list"), "snaptone", s.snaptones);
    fillList($("ir-list"), "ir", s.userIrs);
    fillList($("cab-list"), "ir", s.factoryCabs);
    renderDetail();
    renderTemplates();
  }

  $("build-btn").addEventListener("click", () => DC.openBuildModal({}));
  $("sync-btn").addEventListener("click", async () => {
    const btn = $("sync-btn"), status = $("sync-status");
    btn.disabled = true;
    status.textContent = "Reading pedal…";
    try {
      const r = await DC.sync();
      status.textContent = `Synced ${r.count} SnapTones${r.ir_count != null ? `, ${r.ir_count} user IRs` : ""}.`;
    } catch (e) { status.textContent = `Sync failed: ${e.message}`; }
    finally { btn.disabled = false; }
  });

  DC.on("change", render);
  DC.load().catch((e) => DC.toast(`Could not load device inventory: ${e.message}`, "err"));
})();
