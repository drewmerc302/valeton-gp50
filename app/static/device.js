"use strict";

// GP-50 Device Usage Inspector frontend (T4). Talks only to the read-only
// /api/device endpoints defined in app/api_device.py, which serve the MOCK
// fixture in app/device_stub.py. No device I/O of any kind happens here.
(() => {
  const kindSnaptone = document.getElementById("kind-snaptone");
  const kindIr = document.getElementById("kind-ir");
  const itemSelect = document.getElementById("item-select");
  const usageList = document.getElementById("usage-list");
  const usageEmpty = document.getElementById("usage-empty");

  let inventory = { snaptones: [], irs: [], patches: [] };

  function selectedKind() {
    return kindIr.checked ? "ir" : "snaptone";
  }

  function itemsForKind(kind) {
    return kind === "ir" ? inventory.irs : inventory.snaptones;
  }

  function renderItemOptions() {
    const kind = selectedKind();
    itemSelect.innerHTML = "";
    itemsForKind(kind).forEach((item) => {
      const opt = document.createElement("option");
      opt.value = String(item.slot);
      opt.textContent = `${item.slot}: ${item.name}`;
      itemSelect.appendChild(opt);
    });
  }

  function renderUsage(patches) {
    usageList.innerHTML = "";
    if (!patches.length) {
      usageEmpty.hidden = false;
      return;
    }
    usageEmpty.hidden = true;
    patches.forEach((patch) => {
      const li = document.createElement("li");
      const name = document.createElement("span");
      name.textContent = `${patch.slot}: ${patch.name}`;
      li.appendChild(name);
      usageList.appendChild(li);
    });
  }

  async function loadUsage() {
    if (!itemSelect.value) {
      renderUsage([]);
      return;
    }
    const kind = selectedKind();
    const slot = itemSelect.value;
    try {
      const resp = await fetch(`/api/device/usage/${kind}/${slot}`);
      if (!resp.ok) {
        throw new Error(`usage lookup failed (HTTP ${resp.status})`);
      }
      const body = await resp.json();
      renderUsage(body.patches || []);
    } catch (e) {
      usageList.innerHTML = "";
      usageEmpty.hidden = false;
      usageEmpty.textContent = `Could not load usage: ${e.message}`;
    }
  }

  function onKindChange() {
    renderItemOptions();
    loadUsage();
  }

  kindSnaptone.addEventListener("change", onKindChange);
  kindIr.addEventListener("change", onKindChange);
  itemSelect.addEventListener("change", loadUsage);

  async function init() {
    try {
      const resp = await fetch("/api/device/inventory");
      if (!resp.ok) {
        throw new Error(`inventory load failed (HTTP ${resp.status})`);
      }
      inventory = await resp.json();
    } catch (e) {
      usageEmpty.hidden = false;
      usageEmpty.textContent = `Could not load device inventory: ${e.message}`;
      return;
    }
    renderItemOptions();
    loadUsage();
  }

  init();
})();
