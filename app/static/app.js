"use strict";

// GP-50 Converter frontend (T3). Talks only to the local /api/jobs endpoints
// defined in app/api.py — no device I/O of any kind happens here.
(() => {
  const dropZone = document.getElementById("drop-zone");
  const fileInput = document.getElementById("file-input");
  const filePickerBtn = document.getElementById("file-picker-btn");
  const fileListEl = document.getElementById("file-list");
  const convertBtn = document.getElementById("convert-btn");
  const cancelBtn = document.getElementById("cancel-btn");
  const epochsInput = document.getElementById("epochs");
  const errorBanner = document.getElementById("error-banner");
  const resultsSection = document.getElementById("results-section");
  const resultsEl = document.getElementById("results");

  const DEFAULT_EPOCHS = 60;
  const POLL_INTERVAL_MS = 1500;
  const epochPresetBtns = Array.from(
    document.querySelectorAll(".epoch-preset")
  );

  let selectedFiles = [];
  let pollTimer = null;
  let jobInFlight = false;
  let currentJobId = null;

  function showError(message) {
    errorBanner.textContent = message;
    errorBanner.hidden = false;
  }

  function clearError() {
    errorBanner.hidden = true;
    errorBanner.textContent = "";
  }

  function updateConvertEnabled() {
    convertBtn.disabled = selectedFiles.length === 0 || jobInFlight;
    if (cancelBtn) {
      cancelBtn.hidden = !jobInFlight;
      cancelBtn.disabled = !jobInFlight;
    }
  }

  function renderFileList() {
    fileListEl.innerHTML = "";
    selectedFiles.forEach((file, idx) => {
      const li = document.createElement("li");

      const name = document.createElement("span");
      name.textContent = file.name;

      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "remove-file";
      remove.textContent = "×";
      remove.setAttribute("aria-label", `Remove ${file.name}`);
      remove.addEventListener("click", () => {
        selectedFiles.splice(idx, 1);
        renderFileList();
      });

      li.appendChild(name);
      li.appendChild(remove);
      fileListEl.appendChild(li);
    });
    updateConvertEnabled();
  }

  function addFiles(fileList) {
    const incoming = Array.from(fileList);
    const rejected = [];
    for (const f of incoming) {
      if (!f.name.toLowerCase().endsWith(".nam")) {
        rejected.push(f.name);
        continue;
      }
      const dup = selectedFiles.some(
        (sf) => sf.name === f.name && sf.size === f.size
      );
      if (!dup) selectedFiles.push(f);
    }
    if (rejected.length) {
      showError(`Skipped non-.nam file(s): ${rejected.join(", ")}`);
    } else {
      clearError();
    }
    renderFileList();
  }

  filePickerBtn.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", () => {
    addFiles(fileInput.files);
    fileInput.value = "";
  });

  ["dragenter", "dragover"].forEach((evt) =>
    dropZone.addEventListener(evt, (e) => {
      e.preventDefault();
      dropZone.classList.add("drag-over");
    })
  );
  ["dragleave", "dragend"].forEach((evt) =>
    dropZone.addEventListener(evt, (e) => {
      e.preventDefault();
      dropZone.classList.remove("drag-over");
    })
  );
  dropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropZone.classList.remove("drag-over");
    if (e.dataTransfer && e.dataTransfer.files.length) {
      addFiles(e.dataTransfer.files);
    }
  });
  dropZone.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      fileInput.click();
    }
  });

  function selectedOutputFormat() {
    const checked = document.querySelector(
      'input[name="output_format"]:checked'
    );
    return checked ? checked.value : "0.5x";
  }

  const STATUS_LABELS = {
    queued: "Queued",
    detecting: "Detecting",
    rendering: "Rendering",
    training: "Training",
    done: "Done",
    failed: "Failed",
    cancelled: "Cancelled",
  };

  function isTerminal(status) {
    return (
      status === "done" || status === "failed" || status === "cancelled"
    );
  }

  function formatEta(seconds) {
    if (seconds === null || seconds === undefined || !isFinite(seconds)) {
      return null;
    }
    const s = Math.max(0, Math.round(seconds));
    if (s < 60) return `~${s}s left`;
    const m = Math.floor(s / 60);
    const rem = s % 60;
    return rem ? `~${m}m ${rem}s left` : `~${m}m left`;
  }

  function renderResults(job) {
    resultsSection.hidden = false;
    resultsEl.innerHTML = "";

    job.files.forEach((f) => {
      const row = document.createElement("div");
      row.className = `file-row status-${f.status}`;

      const header = document.createElement("div");
      header.className = "file-row-header";

      const nameEl = document.createElement("span");
      nameEl.className = "file-row-name";
      nameEl.textContent = f.name;

      const statusEl = document.createElement("span");
      statusEl.className = "file-row-status";
      // Prefer the live detail ("Training 42/100") while running; fall back to
      // the coarse status label.
      const running = !isTerminal(f.status);
      statusEl.textContent =
        running && f.detail ? f.detail : STATUS_LABELS[f.status] || f.status;

      header.appendChild(nameEl);
      header.appendChild(statusEl);

      const bar = document.createElement("div");
      bar.className = "progress-bar";
      const fill = document.createElement("div");
      fill.className = "progress-fill";
      fill.style.width = `${Math.round((f.progress || 0) * 100)}%`;
      bar.appendChild(fill);

      row.appendChild(header);
      row.appendChild(bar);

      const eta = running ? formatEta(f.eta_seconds) : null;
      if (eta) {
        const etaEl = document.createElement("div");
        etaEl.className = "file-row-meta file-row-eta";
        etaEl.textContent = eta;
        row.appendChild(etaEl);
      }

      const metaParts = [];
      if (f.esr !== null && f.esr !== undefined) {
        metaParts.push(`ESR: ${f.esr.toFixed(5)}`);
      }
      if (f.format_ok !== null && f.format_ok !== undefined) {
        metaParts.push(`format: ${f.format_ok ? "✓" : "✗"}`);
      }
      if (metaParts.length) {
        const meta = document.createElement("div");
        meta.className = "file-row-meta";
        meta.textContent = metaParts.join("  ·  ");
        row.appendChild(meta);
      }

      if ((f.status === "failed" || f.status === "cancelled") && f.error) {
        const err = document.createElement("div");
        err.className = "file-row-error";
        err.textContent = f.error;
        row.appendChild(err);
      }

      if (f.status === "done" && f.output_available) {
        const link = document.createElement("a");
        link.className = "download-link";
        link.href = `/api/jobs/${job.job_id}/download/${encodeURIComponent(
          f.name
        )}`;
        link.textContent = "Download";
        link.setAttribute("download", `${f.name}.nam`);
        row.appendChild(link);
      }

      resultsEl.appendChild(row);
    });
  }

  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  async function pollJob(jobId) {
    try {
      const resp = await fetch(`/api/jobs/${jobId}`);
      if (!resp.ok) {
        throw new Error(`status check failed (HTTP ${resp.status})`);
      }
      const job = await resp.json();
      job.job_id = jobId;
      renderResults(job);
      if (job.files.every((f) => isTerminal(f.status))) {
        stopPolling();
        jobInFlight = false;
        updateConvertEnabled();
      }
    } catch (e) {
      // A single failed poll shouldn't nuke the last-known results; just
      // surface the network problem and stop trying.
      showError(`Lost contact with job status: ${e.message}`);
      stopPolling();
      jobInFlight = false;
      updateConvertEnabled();
    }
  }

  async function submitJob() {
    if (!selectedFiles.length || jobInFlight) return;
    clearError();
    stopPolling();
    jobInFlight = true;
    updateConvertEnabled();

    const formData = new FormData();
    selectedFiles.forEach((f) => formData.append("files", f, f.name));
    formData.append("epochs", epochsInput.value || String(DEFAULT_EPOCHS));
    formData.append("output_format", selectedOutputFormat());
    formData.append("di", "default");

    let resp;
    try {
      resp = await fetch("/api/jobs", { method: "POST", body: formData });
    } catch (e) {
      showError(`Network error submitting job: ${e.message}`);
      jobInFlight = false;
      updateConvertEnabled();
      return;
    }

    if (!resp.ok) {
      let detail = `HTTP ${resp.status}`;
      try {
        const body = await resp.json();
        if (body && body.detail) detail = body.detail;
      } catch (_parseErr) {
        // keep the generic HTTP-status detail
      }
      showError(`Could not start conversion: ${detail}`);
      jobInFlight = false;
      updateConvertEnabled();
      return;
    }

    const body = await resp.json();
    const jobId = body.job_id;
    currentJobId = jobId;
    resultsSection.hidden = false;
    resultsEl.innerHTML = "";
    pollJob(jobId);
    pollTimer = setInterval(() => pollJob(jobId), POLL_INTERVAL_MS);
  }

  async function cancelJob() {
    if (!jobInFlight || !currentJobId) return;
    if (cancelBtn) {
      cancelBtn.disabled = true;
      cancelBtn.textContent = "Cancelling…";
    }
    try {
      await fetch(`/api/jobs/${currentJobId}/cancel`, { method: "POST" });
      // The next poll reflects the cancelled state; the run loop tears down the
      // in-flight subprocess and marks the remaining files cancelled.
    } catch (e) {
      showError(`Could not cancel: ${e.message}`);
    } finally {
      if (cancelBtn) cancelBtn.textContent = "Cancel";
    }
  }

  function syncPresetActive() {
    const v = String(epochsInput.value).trim();
    epochPresetBtns.forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.epochs === v);
    });
  }

  epochPresetBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      epochsInput.value = btn.dataset.epochs;
      syncPresetActive();
    });
  });
  epochsInput.addEventListener("input", syncPresetActive);

  convertBtn.addEventListener("click", submitJob);
  if (cancelBtn) cancelBtn.addEventListener("click", cancelJob);

  syncPresetActive();
  renderFileList();
})();
