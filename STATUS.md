# STATUS — GP-50 Converter MVP
updated: 2026-07-13 tick-2 | branch: mvp-converter | phase: 2 | acceptance: 0/7

## Now / next
- T1 DONE: app/engine.py (job model + run_job + progress_cb + 0.5.x path + per-file isolation + arch detect). Reviewed vs real script interfaces — correct. Evidence: 10 tests pass (8 new hermetic). Committed.
- Next: T2 backend endpoints. CRITICAL: run conversions OFF the request thread (they take minutes) — background worker + in-memory job store.

## Backlog (DAG)
- [x] T0  scaffold FastAPI app, .venv-app, pytest harness, run.sh        [done]  (2 passed)
- [x] T1  engine API: app/engine.py wrap 2-venv convert, progress_cb, 0.5.x path   [done]  (10 passed)
- [ ] T2  backend: POST create-job (multipart upload + config), background exec, GET job status (poll), GET download   (deps: T1)  [doing]
- [ ] T3  frontend: drag-drop, file list, format toggle, DI/epochs config, live progress, download   (deps: T2)  [todo]
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
- T2: conversions MUST run in a background thread/worker (subprocess has no timeout; ~10-20 min each) — never block the HTTP request.
- Enhancement (T3/T5): live epoch progress by polling lightning checkpoint dir (currently coarse: rendering=0.2, training=0.5, done=1.0).
- Enhancement: port _copy_name_metadata (source→A1 name carryover) from a2a1/a2_to_a1.py.
- Edge: 0.7.0-format WaveNet A1 input currently rejected as unsupported; could re-distill to 0.5.x (render_a2 can load WaveNet). Low priority.

## Notes / decisions
- engine.py public API: FileState, ConvertJob, detect_architecture(), run_job(job, progress_cb). venv paths are ConvertJob fields (testability).
- Stack: FastAPI + minimal web frontend. Full-auto loop, notify on done/block.
