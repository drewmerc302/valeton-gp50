# STATUS — GP-50 Converter MVP
updated: 2026-07-13 tick-1 | branch: mvp-converter | phase: 1 | acceptance: 0/7

## Now / next
- T0 DONE: FastAPI scaffold + .venv-app + pytest harness + run.sh. Evidence: `pytest app/tests` = 2 passed; import ok. Committed.
- Next: T1 engine API (wrap the 2-venv convert as a job with progress callbacks + 0.5.x|0.7.0 toggle).

## Backlog (DAG)
- [x] T0  scaffold FastAPI app, .venv-app, pytest harness, run.sh   (deps: —)        [done]  (evidence: 2 passed)
- [ ] T1  engine API: `app/engine.py` wrapping 2-venv convert as job w/ progress callbacks + 0.5.x|0.7.0 toggle   (deps: T0)  [doing]
- [ ] T2  backend endpoints: upload/start job, job status (SSE/poll), download result, list jobs   (deps: T1)   [todo]
- [ ] T3  frontend: drag-drop, file list, format toggle, DI/epochs config, live progress, download   (deps: T2)  [todo]
- [ ] T4  device-stub screen: mocked SnapTone/IR→patch usage inspector (fixture from decoded inventory) + MOCK banner   (deps: T0)  [todo]
- [ ] T5  robustness + tests: per-file failure isolation, error surfacing, unit + HEADLESS e2e (real fast-preset conversion via API) + UI screenshot   (deps: T2,T3)  [todo]
- [ ] T6  acceptance sweep + run.sh + README; verify all 7 criteria   (deps: T3,T4,T5)  [todo]

## Acceptance (MVP_REQUIREMENTS.md §Acceptance) — 0/7
1. [ ] UI: A2.nam → valid 0.5.x A1, format OK, progress shown
2. [ ] batch ≥2 + bad-file isolation
3. [ ] both output formats load-valid
4. [ ] usage-inspector stub w/ MOCK banner
5. [ ] test suite green + headless e2e + UI screenshot
6. [ ] ESR under threshold (fast <0.05, full <0.015)
7. [ ] run.sh launches; README documents

## Blocked-on-Drew (hardware-gated — DO NOT ATTEMPT)
- Features 2-6 real device I/O: need spy capture of SnapTone upload + 2-byte checksum crack
  + patch-body decode. Stub uses mocked data only.

## Notes / decisions
- Stack: FastAPI + minimal web frontend. Full-auto loop, notify on done/block.
- Engine reuses `.venv` (0.13.0 render) + `.venv-a1` (0.12.2 export 0.5.x); 0.7.0 export via 0.13.0.
- T0: app on port 8756; router pattern in main.py for future mounts. .claude/ gitignored.
- Tests use fast epoch preset for speed; sample teacher = refs/A2.nam; DI = refs/v3_0_0.wav.
