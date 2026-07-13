# STATUS — GP-50 Converter MVP
updated: 2026-07-13 tick-8 | branch: mvp-converter | phase: DONE | acceptance: 7/7 ✅ MVP COMPLETE

## MVP COMPLETE — all 7 acceptance criteria met, committed to branch mvp-converter.
- T6 DONE: README.md (setup + usage + scope); run.sh verified launching (/health,/,/device,/api all 200); final fast sweep 31 green. → Acceptance #7 MET.
- Handoff: screenshots sent to Drew, push notification sent, loop stopped.
- Remaining work is all post-MVP / hardware-gated (see below). Merge mvp-converter → master when Drew approves.

## Backlog (DAG)
- [x] T0  scaffold FastAPI app, .venv-app, pytest harness, run.sh        [done]
- [x] T1  engine API: run_job, progress_cb, 0.5.x path, per-file isolation   [done]
- [x] T1b 0.7.0 export path (.venv 0.13.0 + a2a1/train_a1_070.py)   [done]  (#3 MET)
- [x] T2  backend: POST create-job + background exec + GET status/download/list   [done]
- [x] T3  frontend: drag-drop, format toggle, epochs, live progress, download   [done]
- [x] T4  device-stub screen: mocked usage inspector + MOCK banner   [done]  (#4 MET)
- [x] T5  headless e2e (real fast convert via UI) + screenshots + isolation   [done]  (#1,#2,#5,#6 MET)
- [x] T6  README (setup+usage) + full acceptance sweep + mark #7   (deps: all)  [done]  (#7 MET)

## Acceptance (MVP_REQUIREMENTS.md §Acceptance) — 6/7
1. [x] UI: A2.nam → valid 0.5.x A1, format OK, progress shown  (e2e screenshot 03)
2. [x] batch ≥2 + bad-file isolation  (good Done, bad Failed w/ error)
3. [x] both output formats load-valid  (0.5.x + 0.7.0 verified)
4. [x] usage-inspector stub w/ MOCK banner  (/device, screenshot 04)
5. [x] test suite green + headless e2e + UI screenshot  (31 fast + e2e + 4 shots)
6. [x] ESR under threshold  (fast 0.5.x = 0.04403 < 0.05)
7. [x] run.sh launches; README documents  (verified: all routes 200; README.md)

## Blocked-on-Drew (hardware-gated — DO NOT ATTEMPT)
- Features 2-6 real device I/O: need spy capture of SnapTone upload + 2-byte checksum + patch-body decode. Stub = mocked data only.

## Follow-ups / tech-debt (post-MVP)
- No job retention/cleanup (work/jobs grows); dup-named uploads in one job collide; subprocess no timeout.
- Live epoch progress (poll lightning checkpoint dir) — currently coarse.
- Port _copy_name_metadata (source→A1 name carryover).
- 0.7.0-format WaveNet A1 input currently rejected as unsupported (could re-distill).

## Notes / decisions
- Stack: FastAPI + vanilla web frontend, .venv-app. Engine reuses .venv (0.13.0) + .venv-a1 (0.12.2).
- Screenshots: work/screenshots/{01-empty,02-progress,03-done,04-device}.png (gitignored artifacts).
- Full-auto loop, notify Drew on MVP-done (with screenshots) / block.
