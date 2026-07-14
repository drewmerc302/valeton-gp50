"use strict";
// Variant C — Build-forward. The Template → SnapTone → Slot build strip is the
// hero; the registry sits below for reference.
(() => {
  const DC = window.DeviceCore;
  const $ = (id) => document.getElementById(id);
  const tSel = $("c-template"), sSel = $("c-snaptone"), slotSel = $("c-slot");

  function fillStrip() {
    const s = DC.state;
    tSel.innerHTML = "";
    if (!s.templates.length) {
      $("c-hint").hidden = false;
      $("c-go").disabled = true;
      const o = document.createElement("option");
      o.textContent = "— no templates —"; o.value = ""; tSel.appendChild(o);
    } else {
      $("c-hint").hidden = true;
      $("c-go").disabled = false;
      s.templates.forEach((t) => {
        const o = document.createElement("option");
        o.value = t.id;
        o.textContent = `${t.name} · ${((t.summary && t.summary.chain) || []).map((b) => b.model || b.block).join(" · ") || "—"}`;
        tSel.appendChild(o);
      });
    }
    sSel.innerHTML = "";
    s.snaptones.forEach((st) => {
      const o = document.createElement("option");
      o.value = String(st.slot);
      o.textContent = `#${st.slot} — ${st.name}`;
      sSel.appendChild(o);
    });
    slotSel.innerHTML = "";
    const empties = DC.emptySlots();
    if (empties.length) {
      const g = document.createElement("optgroup"); g.label = `Empty slots (${empties.length})`;
      empties.forEach((p) => { const o = document.createElement("option"); o.value = String(p.slot); o.textContent = `#${p.slot} — empty`; g.appendChild(o); });
      slotSel.appendChild(g);
    }
    const g2 = document.createElement("optgroup"); g2.label = "Occupied (overwrite)";
    DC.state.patches.filter((p) => !DC.isEmpty(p.slot)).forEach((p) => {
      const o = document.createElement("option"); o.value = String(p.slot); o.textContent = `#${p.slot} — ${p.name}`; g2.appendChild(o);
    });
    slotSel.appendChild(g2);
    refreshWarn();
  }

  function refreshWarn() {
    const slot = Number(slotSel.value);
    const w = $("c-warn");
    if (DC.isEmpty(slot)) { w.hidden = true; return; }
    const n = DC.usageCount("snaptone", slot) + DC.usageCount("ir", slot);
    w.hidden = false;
    w.textContent = `⚠ Slot #${slot} "${DC.slotName(slot)}" is not empty — writing replaces it` +
      (n ? ` (${n} patch${n === 1 ? "" : "es"} reference material here).` : ".");
  }
  slotSel.addEventListener("change", refreshWarn);

  $("c-go").addEventListener("click", async () => {
    if (!tSel.value) return;
    const slot = Number(slotSel.value);
    const st = DC.state.snaptones.find((x) => x.slot === Number(sSel.value));
    const msg = DC.isEmpty(slot)
      ? `Write a patch built from "${st ? st.name : sSel.value}" to empty slot #${slot}?`
      : `Overwrite slot #${slot} "${DC.slotName(slot)}" with a patch built from "${st ? st.name : sSel.value}"?`;
    if (!(await DC.confirmDialog(msg, "Write to device"))) return;
    $("c-go").disabled = true;
    DC.toast(`Writing to slot #${slot}…`);
    try {
      const r = await DC.buildWrite(tSel.value, Number(sSel.value), slot);
      if (!r.ok) throw new Error(r.error || "write failed");
      DC.toast(`✓ Wrote "${r.verified_name || ""}" to slot #${slot}.`, "ok");
    } catch (e) { DC.toast(`Write failed: ${e.message}`, "err"); }
    finally { $("c-go").disabled = false; }
  });

  function card(kind, it) {
    const name = kind === "snaptone" ? it.name : DC.irLabel(it);
    const n = DC.usageCount(kind, it.slot);
    const el = document.createElement("div");
    el.className = `asset-card ${kind === "snaptone" ? "st" : "ir"}`;
    el.innerHTML = `<div class="ac-top"><span class="ac-slot">#${it.slot > 0xfffff ? "IR" : it.slot}</span><span class="ac-name">${name}</span></div>` +
      `<div class="ac-foot"><span class="usage-badge${n ? "" : " unused"}">${n ? n + " patch" + (n === 1 ? "" : "es") : "unused"}</span></div>`;
    el.addEventListener("click", () => DC.openUsageModal(kind, it.slot));
    return el;
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
    $("st-grid").innerHTML = ""; s.snaptones.forEach((it) => $("st-grid").appendChild(card("snaptone", it)));
    $("ir-grid").innerHTML = ""; s.userIrs.forEach((it) => $("ir-grid").appendChild(card("ir", it)));
    $("ir-empty").hidden = s.userIrs.length > 0;
    fillStrip();
    renderTemplates();
  }

  $("sync-btn").addEventListener("click", async () => {
    const btn = $("sync-btn");
    btn.disabled = true;
    try { const r = await DC.sync(); DC.toast(`Synced ${r.count} SnapTones.`, "ok"); }
    catch (e) { DC.toast(`Sync failed: ${e.message}`, "err"); }
    finally { btn.disabled = false; }
  });

  DC.on("change", render);
  DC.load().catch((e) => DC.toast(`Could not load device inventory: ${e.message}`, "err"));
})();
