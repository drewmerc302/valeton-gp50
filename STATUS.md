# STATUS — GP-50 Converter MVP
updated: 2026-07-13 tick-3 | branch: mvp-converter | phase: 3 | acceptance: 0/7

## Now / next
- T2 DONE: app/api.py — POST /api/jobs (multipart upload + config, background daemon thread, swappable job_executor), GET status (poll), GET download (path-safe), GET list. In-memory job store w/ lock. Reviewed: upload/download path-safe, per-file + job-level isolation. Evidence: 18 tests pass (8 new hermetic). Committed.
- Next: T3 frontend (convert UI: drag-drop, format toggle, epochs, live progress poll, download).

## Backlog (DAG)
- [x] T0  scaffold FastAPI app, .venv-app, pytest harness, run.sh        [done]  (2 passed)
- [x] T1  engine API: app/engine.py wrap 2-venv convert, progress_cb, 0.5.x path   [done]  (10 passed)
- [x] T2  backend: POST create-job + background exec + GET status/download/list   (deps: T1)  [done]  (18 passed)
- [ ] T3  frontend: drag-drop, file list, format toggle, DI/epochs config, live progress, download   (deps: T2)  [doing]
- [ ] T4  device-stub screen: mocked SnapTone/IR→patch usage inspector + MOCK banner   (deps: T0)  [todo]
- [ ] T5  robustness + tests: failure isolation (have it), error surfacing in UI, unit + HEADLESS e2e (real fast-preset convert via API) + UI screenshot   (deps: T2,T3)  [todo]
- [ ] T6  acceptance sweep + run.sh + README; verify all 7 criteria   (deps: T3,T4,T5)  [todo]
- [ ] T1b 0.7.0 export path (train/export in .venv 0.13.0 with new-schema WaveNet config)   (deps: T1)  [todo]

## Acceptance (MVP_REQUIREMENTS.md §Acceptance) — 0/7
1. [ ] UI: A2.nam → valid 0.5.x A1, format OK, progress shown
2. [ ] batch ≥2 + bad-file isolation   (engine supports; needs UI/e2e)
3. [ ] both output formats load-valid   (needs T1b)
4. [ ] usage-inspector stub w/ MOCK banner
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
