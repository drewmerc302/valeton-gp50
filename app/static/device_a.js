"use strict";
// Variant A — Registry-first. Loaded captures + IRs as cards with usage badges;
// click a card to see its dependencies; build a patch from any SnapTone.
// All device logic lives in DeviceCore (device_core.js).
(() => {
  const DC = window.DeviceCore;
  const $ = (id) => document.getElementById(id);

  function usageBadge(kind, slot) {
    const n = DC.usageCount(kind, slot);
    const b = document.createElement("span");
    b.className = "usage-badge" + (n ? "" : " unused");
    b.textContent = n ? `${n} patch${n === 1 ? "" : "es"}` : "unused";
    return b;
  }

  function assetCard(kind, it) {
    const card = document.createElement("div");
    card.className = `asset-card ${kind === "snaptone" ? "st" : "ir"}`;
    const name = kind === "snaptone" ? it.name : DC.irLabel(it);
    const top = document.createElement("div");
    top.className = "ac-top";
    top.innerHTML =
      `<span class="ac-slot">#${it.slot > 0xfffff ? "IR" : it.slot}</span>` +
      `<span class="ac-name">${name}</span>`;
    const foot = document.createElement("div");
    foot.className = "ac-foot";
    foot.appendChild(usageBadge(kind, it.slot));
    if (kind === "snaptone") {
      const build = document.createElement("button");
      build.type = "button";
      build.className = "ac-build";
      build.textContent = "Build →";
      build.addEventListener("click", (e) => {
        e.stopPropagation();
        DC.openBuildModal({ snaptoneSlot: it.slot });
      });
      foot.appendChild(build);
    }
    card.append(top, foot);
    card.addEventListener("click", () => DC.openUsageModal(kind, it.slot));
    return card;
  }

  function renderGrid(el, kind, items, emptyEl) {
    el.innerHTML = "";
    if (!items.length) { if (emptyEl) emptyEl.hidden = false; return; }
    if (emptyEl) emptyEl.hidden = true;
    items.forEach((it) => el.appendChild(assetCard(kind, it)));
  }

  function renderTemplates() {
    const list = $("tmpl-list");
    const empty = $("tmpl-empty");
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
      del.type = "button"; del.className = "tr-del"; del.title = "Delete template"; del.textContent = "✕";
      del.addEventListener("click", async () => {
        if (!(await DC.confirmDialog(`Delete template "${t.name}"?`, "Delete"))) return;
        await DC.deleteTemplate(t.id);
        DC.toast("Template deleted.");
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
    renderGrid($("st-grid"), "snaptone", s.snaptones, $("st-empty"));
    renderGrid($("ir-grid"), "ir", s.userIrs, $("ir-empty"));
    renderGrid($("cab-grid"), "ir", s.factoryCabs, null);
    renderTemplates();
  }

  $("build-btn").addEventListener("click", () => DC.openBuildModal({}));
  $("sync-btn").addEventListener("click", async () => {
    const btn = $("sync-btn"), status = $("sync-status");
    btn.disabled = true;
    status.textContent = "Reading pedal… (connect it, close Valeton Suite)";
    try {
      const r = await DC.sync();
      status.textContent = `Synced ${r.count} SnapTones${r.ir_count != null ? `, ${r.ir_count} user IRs` : ""}.`;
    } catch (e) {
      status.textContent = `Sync failed: ${e.message}`;
    } finally { btn.disabled = false; }
  });

  DC.on("change", render);
  DC.load().catch((e) => DC.toast(`Could not load device inventory: ${e.message}`, "err"));
})();
