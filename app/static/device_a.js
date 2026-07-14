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
    const list = document.createElement("button");
    list.type = "button";
    list.className = "ac-list";
    list.textContent = "List Presets";
    list.addEventListener("click", () => DC.openUsageModal(kind, it.slot));
    foot.appendChild(list);
    if (kind === "snaptone") {
      const build = document.createElement("button");
      build.type = "button";
      build.className = "ac-build";
      build.textContent = "Build →";
      build.addEventListener("click", () => DC.openBuildModal({ snaptoneSlot: it.slot }));
      foot.appendChild(build);
    }
    card.append(top, foot);
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
    renderGrid($("st-grid"), "snaptone", s.snaptones, $("st-empty"));
    renderGrid($("ir-grid"), "ir", s.userIrs, $("ir-empty"));
    renderTemplates();
  }

  // "Make a template from a preset" — save any preset's effects chain as a
  // named template without a round-trip through the Preset Explorer.
  function openTemplateModal() {
    const ov = $("tmpl-modal");
    const src = $("tmpl-src");
    const name = $("tmpl-name");
    const create = $("tmpl-create");
    const cancel = $("tmpl-cancel");
    src.innerHTML = "";
    const named = DC.state.patches.filter((p) => !DC.isEmpty(p.slot));
    (named.length ? named : DC.state.patches).forEach((p) => {
      const o = document.createElement("option");
      o.value = String(p.slot);
      o.textContent = `#${p.slot} — ${p.name}`;
      src.appendChild(o);
    });
    name.value = "";
    ov.hidden = false;
    name.focus();
    const close = () => {
      ov.hidden = true;
      create.onclick = cancel.onclick = ov.onclick = null;
    };
    cancel.onclick = close;
    ov.onclick = (e) => { if (e.target === ov) close(); };
    create.onclick = async () => {
      const n = name.value.trim() || (src.selectedOptions[0]?.textContent.split("— ")[1] ?? "");
      if (!n) { DC.toast("Give the template a name.", "err"); return; }
      create.disabled = true;
      try {
        await DC.createTemplate(n, Number(src.value));
        DC.toast(`✓ Saved template "${n}".`, "ok");
        close();
      } catch (e) {
        DC.toast(`Could not save template: ${e.message}`, "err");
      } finally { create.disabled = false; }
    };
  }
  $("tmpl-new-btn").addEventListener("click", openTemplateModal);

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
