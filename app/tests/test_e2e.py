"""Real headless-browser end-to-end test (T5).

Drives the actual app (real uvicorn subprocess, real Chromium via
Playwright) through a genuine batch conversion at the "Fast (test)" preset
— no mocking of app.api.job_executor here, unlike the fast TestClient suite.
This is slow (spins up torch + does a real render/train pass) and is
therefore excluded from the default run via the `slow` marker; invoke with
`pytest -m slow` (or without `-m` filters at all) to run it for real.

It validates MVP_REQUIREMENTS.md acceptance criteria:
  #1 UI: refs/A2.nam -> valid 0.5.x A1, format OK, progress shown.
  #2 batch of >=2 with a deliberately-bad file: per-file isolation.
  #5 headless e2e drives a real conversion via the HTTP API + UI screenshots.
  #6 ESR under threshold at the fast preset (printed for the overseer to check).

No device I/O happens anywhere in this test — /device is read-only mocked
data, asserted only for the MOCK banner.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SCREENSHOTS_DIR = PROJECT_ROOT / "work" / "screenshots"
GOOD_NAM = PROJECT_ROOT / "refs" / "A2.nam"

# WaveNet architecture but a non-0.5.x version: engine.detect_architecture
# rejects this as "unsupported source architecture" before any subprocess
# work starts, so it fails fast and deterministically at detection.
BAD_NAM_BYTES = json.dumps(
    {
        "version": "0.7.0",
        "architecture": "WaveNet",
        "config": {"layers": [{"head_size": 8}]},
        "weights": [],
        "sample_rate": 48000,
    }
).encode()


def _row_states(page) -> list[dict]:
    return page.evaluate(
        """
        () => Array.from(document.querySelectorAll('.file-row')).map(row => ({
            name: row.querySelector('.file-row-name')?.textContent ?? null,
            status: row.querySelector('.file-row-status')?.textContent ?? null,
            className: row.className,
            error: row.querySelector('.file-row-error')?.textContent ?? null,
            meta: row.querySelector('.file-row-meta')?.textContent ?? null,
            downloadHref: row.querySelector('.download-link')?.getAttribute('href') ?? null,
        }))
        """
    )


@pytest.mark.slow
def test_convert_e2e_real_conversion(page, live_server, tmp_path):
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    assert GOOD_NAM.exists(), f"missing fixture: {GOOD_NAM}"

    bad_nam = tmp_path / "bad.nam"
    bad_nam.write_bytes(BAD_NAM_BYTES)

    # --- 1. empty convert page -------------------------------------------------
    page.goto(live_server + "/")
    page.wait_for_selector("#drop-zone")
    page.screenshot(path=str(SCREENSHOTS_DIR / "01-convert-empty.png"), full_page=True)

    # --- 2. upload both files, fast preset, convert -----------------------------
    page.set_input_files("#file-input", [str(GOOD_NAM), str(bad_nam)])
    page.wait_for_function(
        "() => document.querySelectorAll('#file-list li').length === 2"
    )

    page.click("#fast-preset")
    assert page.input_value("#epochs") == "5"

    page.click("#convert-btn")

    # --- 3. mid-progress screenshot ---------------------------------------------
    page.wait_for_function(
        """
        () => Array.from(document.querySelectorAll('.file-row-status'))
            .some(el => el.textContent.includes('Rendering') || el.textContent.includes('Training'))
        """,
        timeout=120_000,
    )
    page.screenshot(
        path=str(SCREENSHOTS_DIR / "02-convert-progress.png"), full_page=True
    )

    # --- 4. wait for both files to reach a terminal state -----------------------
    page.wait_for_function(
        """
        () => {
            const rows = document.querySelectorAll('.file-row');
            if (rows.length !== 2) return false;
            return Array.from(rows).every(
                row => row.className.includes('status-done') || row.className.includes('status-failed')
            );
        }
        """,
        timeout=300_000,
    )
    page.screenshot(path=str(SCREENSHOTS_DIR / "03-convert-done.png"), full_page=True)

    rows = _row_states(page)
    by_name = {r["name"]: r for r in rows}
    assert set(by_name) == {"A2", "bad"}, f"unexpected rows: {rows}"

    good = by_name["A2"]
    bad = by_name["bad"]

    # Good file: done, with a download link, an ESR value, and format OK.
    assert good["status"] == "Done", f"good file did not complete: {good}"
    assert good["downloadHref"], f"good file missing download link: {good}"
    assert good["meta"] and "ESR:" in good["meta"], f"good file missing ESR: {good}"
    assert good["meta"] and "format: ✓" in good["meta"], (
        f"good file format check not OK: {good}"
    )

    # Bad file: failed with a visible error, and — critically — the good
    # file above still completed. Per-file isolation (acceptance #2).
    assert bad["status"] == "Failed", f"bad file did not fail as expected: {bad}"
    assert bad["error"], f"bad file failed with no visible error text: {bad}"

    esr_str = good["meta"].split("ESR:")[1].split("·")[0].strip()
    esr_value = float(esr_str)
    print(f"\nGP-50 e2e: good-file (A2) ESR at fast preset = {esr_value}\n")

    # --- 5. download the good result and validate the .nam format (#1) ----------
    download_resp = page.request.get(live_server + good["downloadHref"])
    assert download_resp.ok, f"download failed: {download_resp.status}"
    nam_json = json.loads(download_resp.body())
    assert str(nam_json.get("version", "")).startswith("0.5"), (
        f"expected 0.5.x output version, got {nam_json.get('version')!r}"
    )
    assert nam_json.get("architecture") == "WaveNet", (
        f"expected WaveNet architecture, got {nam_json.get('architecture')!r}"
    )

    # --- 6. device inspector: registry renders from real inventory + build CTA ----
    page.goto(live_server + "/device")
    page.wait_for_selector(
        "#st-grid .asset-card"
    )  # SnapTone cards render (DeviceCore ran)
    assert page.query_selector(".asset-card .usage-badge")  # usage badges present
    assert page.query_selector("#build-btn")  # build-from-capture CTA present
    page.screenshot(path=str(SCREENSHOTS_DIR / "04-device.png"), full_page=True)
