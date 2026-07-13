# STATUS — GP-50 Converter MVP
updated: 2026-07-13 tick-6 | branch: mvp-converter | phase: 5 | acceptance: 2/7

## Now / next
- T1b DONE: a2a1/train_a1_070.py (0.13.0 new-schema WaveNet trainer) + engine dispatch (0.7.0→.venv/train_a1_070.py). REAL fast train verified: /tmp/t070/a1.nam = version 0.7.0, WaveNet (independently confirmed). 0.5.x path untouched. 0.7.0 toggle enabled in UI. Evidence: 31 tests pass. Committed. → Acceptance #3 MET (both formats load-valid: 0.5.x out/A2.nam + 0.7.0 verified).
- Next: T5 — install playwright+chromium; headless e2e that drives a REAL fast conversion via the UI + saves screenshots (convert progress/done + device page); verify batch+bad-file isolation. This produces the screenshots Drew reviews.

## Backlog (DAG)
- [x] T0  scaffold FastAPI app, .venv-app, pytest harness, run.sh        [done]  (2 passed)
- [x] T1  engine API: app/engine.py wrap 2-venv convert, progress_cb, 0.5.x path   [done]  (10 passed)
- [x] T2  backend: POST create-job + background exec + GET status/download/list   (deps: T1)  [done]  (18 passed)
- [x] T3  frontend: drag-drop, format toggle, epochs, live progress, download   (deps: T2)  [done]  (22 passed)
- [x] T4  device-stub screen: mocked SnapTone/IR→patch usage inspector + MOCK banner   (deps: T0)  [done]  (31 passed, #4 MET)
- [ ] T5  robustness + tests: failure isolation (have it), error surfacing in UI, unit + HEADLESS e2e (real fast-preset convert via API) + UI screenshot   (deps: T2,T3)  [todo]
- [ ] T6  acceptance sweep + run.sh + README; verify all 7 criteria   (deps: T3,T4,T5)  [todo]
- [x] T1b 0.7.0 export path (.venv 0.13.0 + a2a1/train_a1_070.py)   (deps: T1)  [done]  (real train → v0.7.0, #3 MET)

## Acceptance (MVP_REQUIREMENTS.md §Acceptance) — 0/7
1. [ ] UI: A2.nam → valid 0.5.x A1, format OK, progress shown
2. [ ] batch ≥2 + bad-file isolation   (engine supports; needs UI/e2e)
3. [x] both output formats load-valid  (0.5.x out/A2.nam + 0.7.0 /tmp verified)
4. [x] usage-inspector stub w/ MOCK banner  (T4: /device, 31 tests)
5. [ ] test suite green + headless e2e + UI screenshot
6. [ ] ESR under threshold (fast <0.05, full <0.015)
7. [ ] run.sh launches; README documents

## Blocked-on-Drew (hardware-gated — DO NOT ATTEMPT)
- Features 2-6 real device I/O: need spy capture of SnapTone upload + 2-byte checksum crack + patch-body decode. Stub = mocked data only.

## Follow-ups / tech-debt (address in noted task)
- T2 DONE this way (daemon thread). Still open: no job retention/cleanup (work/jobs grows); dup-named uploads in one job collide; subprocess still has no timeout (a hung train hangs that job only).
- T3: guard/disable the 0.7.0 toggle until T1b lands (0.7.0 currently fails async per-file with a clear error).
- Enhancement (T3/T5): live epoch progress by polling lightning checkpoint dir (currently coarse: rendering=0.2, training=0.5, done=1.0).
- Enhancement: port _copy_name_metadata (source→A1 name carryover) from a2a1/a2_to_a1.py.
- Edge: 0.7.0-format WaveNet A1 input currently rejected as unsupported; could re-distill to 0.5.x (render_a2 can load WaveNet). Low priority.

## Notes / decisions
- engine.py public API: FileState, ConvertJob, detect_architecture(), run_job(job, progress_cb). venv paths are ConvertJob fields (testability).
- Stack: FastAPI + minimal web frontend. Full-auto loop, notify on done/block.
