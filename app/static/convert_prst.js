"use strict";

// Convert page: sub-tab switching + the GP-5 <-> GP-50 preset converter.
// Talks to /api/device/convert{,/inspect} (see app/api_device.py). File-only —
// no device I/O. The NAM (A2 -> A1) tab is handled by app.js.
(() => {
  // --- sub-tab switching -----------------------------------------------------
  const tabs = document.getElementById("convert-subtabs");
  const panels = {
    nam: document.getElementById("tab-nam"),
    preset: document.getElementById("tab-preset"),
  };
  tabs.querySelectorAll("button[data-tab]").forEach((btn) => {
    btn.addEventListener("click", () => {
      tabs.querySelectorAll("button").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      Object.entries(panels).forEach(([key, el]) => {
        el.hidden = key !== btn.dataset.tab;
      });
    });
  });

  // --- preset converter ------------------------------------------------------
  const drop = document.getElementById("prst-drop");
  const input = document.getElementById("prst-input");
  const pickBtn = document.getElementById("prst-pick-btn");
  const listEl = document.getElementById("prst-list");
  const convertBtn = document.getElementById("prst-convert-btn");
  const errEl = document.getElementById("prst-error");
  const forceRow = document.getElementById("prst-force-row");
  const forceCb = document.getElementById("prst-force");

  let files = []; // File[]
  let inspected = []; // per-file inspect result, index-aligned with `files`

  const DEV = { gp5: "GP-5", gp50: "GP-50" };

  function showError(msg) {
    errEl.textContent = msg;
    errEl.hidden = !msg;
  }

  function targetValue() {
    const el = document.querySelector('input[name="prst_target"]:checked');
    return el ? el.value : "auto";
  }

  function addFiles(fileList) {
    const rejected = [];
    for (const f of Array.from(fileList)) {
      if (!f.name.toLowerCase().endsWith(".prst")) {
        rejected.push(f.name);
        continue;
      }
      if (!files.some((x) => x.name === f.name && x.size === f.size)) files.push(f);
    }
    showError(rejected.length ? `Skipped non-.prst file(s): ${rejected.join(", ")}` : "");
    refresh();
  }

  async function refresh() {
    if (!files.length) {
      listEl.innerHTML = "";
      inspected = [];
      forceRow.hidden = true;
      convertBtn.disabled = true;
      return;
    }
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f, f.name));
    fd.append("target", targetValue());
    try {
      const r = await fetch("/api/device/convert/inspect", { method: "POST", body: fd });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || `HTTP ${r.status}`);
      inspected = data.files;
    } catch (e) {
      showError(`Could not inspect presets: ${e.message}`);
      return;
    }
    render();
  }

  function render() {
    listEl.innerHTML = "";
    let anyProblem = false;
    let anyConvertible = false;
    files.forEach((f, idx) => {
      const info = inspected[idx] || {};
      const li = document.createElement("li");
      li.className = "convert-row";

      const left = document.createElement("div");
      left.className = "convert-row-main";
      const name = document.createElement("span");
      name.className = "convert-row-name";
      name.textContent = f.name;
      left.appendChild(name);

      const flow = document.createElement("span");
      flow.className = "convert-flow";
      if (!info.ok) {
        flow.innerHTML = `<span class="badge warn">unrecognized</span>`;
      } else if (info.same_device) {
        flow.innerHTML = `<span class="badge">${DEV[info.source_key]}</span> <span class="hint">already this device</span>`;
      } else {
        anyConvertible = true;
        flow.innerHTML =
          `<span class="badge">${DEV[info.source_key]}</span> → ` +
          `<span class="badge ok">${DEV[info.target_key]}</span>`;
        if (info.problems && info.problems.length) {
          anyProblem = true;
          const models = info.problems.map((p) => p.model).join(", ");
          flow.innerHTML += ` <span class="badge warn" title="${models}">${info.problems.length} block(s) with no ${DEV[info.target_key]} equivalent</span>`;
        }
      }
      left.appendChild(flow);
      li.appendChild(left);

      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "remove-file";
      remove.textContent = "×";
      remove.setAttribute("aria-label", `Remove ${f.name}`);
      remove.addEventListener("click", () => {
        files.splice(idx, 1);
        refresh();
      });
      li.appendChild(remove);
      listEl.appendChild(li);
    });

    forceRow.hidden = !anyProblem;
    convertBtn.disabled = !anyConvertible;
  }

  async function convert() {
    if (!files.length) return;
    showError("");
    convertBtn.disabled = true;
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f, f.name));
    fd.append("target", targetValue());
    fd.append("force", forceCb.checked ? "true" : "false");
    try {
      const r = await fetch("/api/device/convert", { method: "POST", body: fd });
      if (!r.ok) {
        let detail = `HTTP ${r.status}`;
        try {
          detail = (await r.json()).detail || detail;
        } catch (_) {}
        throw new Error(detail);
      }
      const name = await window.UI.downloadResponse(r, "converted.prst");
      window.UI.toast(`Downloaded ${name}`, "ok");
    } catch (e) {
      showError(e.message);
      window.UI.toast("Conversion failed", "err");
    } finally {
      convertBtn.disabled = false;
    }
  }

  // wiring
  pickBtn.addEventListener("click", () => input.click());
  input.addEventListener("change", () => {
    addFiles(input.files);
    input.value = "";
  });
  ["dragenter", "dragover"].forEach((evt) =>
    drop.addEventListener(evt, (e) => {
      e.preventDefault();
      drop.classList.add("drag-over");
    })
  );
  ["dragleave", "dragend", "drop"].forEach((evt) =>
    drop.addEventListener(evt, (e) => {
      e.preventDefault();
      drop.classList.remove("drag-over");
    })
  );
  drop.addEventListener("drop", (e) => {
    if (e.dataTransfer && e.dataTransfer.files.length) addFiles(e.dataTransfer.files);
  });
  drop.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      input.click();
    }
  });
  document
    .getElementById("prst-target")
    .addEventListener("change", refresh);
  convertBtn.addEventListener("click", convert);
})();
