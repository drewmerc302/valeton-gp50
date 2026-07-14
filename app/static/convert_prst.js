"use strict";

// Convert page: the GP-5 <-> GP-50 preset converter (the lower section). Runs
// fully client-side via window.PRST (app/static/prst.js) — a byte-for-byte port
// of patch/convert.py, verified over the whole corpus (app/tests/test_prst_js.mjs).
// No backend call, so this page works as a static host (the beta-2 target). The
// NAM (A2 -> A1) section above is handled by app.js.
(() => {
  const PRST = window.PRST;

  // Mirror of api_device._target_for: auto -> the opposite device.
  const targetFor = (srcKey, target) =>
    target === "auto" ? (srcKey === "gp50" ? "gp5" : "gp50") : target;

  const readBytes = (file) =>
    file.arrayBuffer().then((buf) => new Uint8Array(buf));

  function downloadBytes(name, u8) {
    const url = URL.createObjectURL(new Blob([u8], { type: "application/octet-stream" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 4000);
  }

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
    const target = targetValue();
    try {
      inspected = await Promise.all(
        files.map(async (f) => {
          const data = await readBytes(f);
          let src;
          try {
            src = PRST.detect(data);
          } catch (e) {
            return { name: f.name, ok: false, error: e.message };
          }
          const tgtKey = targetFor(src.key, target);
          const problems = PRST.checkConvertible(data, tgtKey);
          return {
            name: f.name,
            ok: true,
            source_key: src.key,
            target_key: tgtKey,
            same_device: src.key === tgtKey,
            problems: problems.map((p) => ({ block_index: p.blockIndex, model: p.model })),
          };
        })
      );
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
    const target = targetValue();
    const force = forceCb.checked;
    try {
      // Only the cross-device files are convertible; same-device files are skipped
      // (the button is gated on there being at least one convertible file).
      const jobs = [];
      for (const f of files) {
        const data = await readBytes(f);
        const src = PRST.detect(data);
        const tgtKey = targetFor(src.key, target);
        if (src.key === tgtKey) continue;
        const out = PRST.convert(data, tgtKey, { force });
        const stem = f.name.toLowerCase().endsWith(".prst") ? f.name.slice(0, -5) : f.name;
        jobs.push({ name: `${stem}__${PRST.profileFor(tgtKey).name}.prst`, bytes: out });
      }
      if (!jobs.length) throw new Error("nothing to convert");
      jobs.forEach((j) => downloadBytes(j.name, j.bytes));
      const label = jobs.length === 1 ? jobs[0].name : `${jobs.length} presets`;
      window.UI.toast(`Downloaded ${label}`, "ok");
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
