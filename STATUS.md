# STATUS — GP-50 Converter MVP
updated: 2026-07-13 tick-7 | branch: mvp-converter | phase: 6 | acceptance: 6/7

## Now / next
- T5 DONE: real headless e2e (playwright+chromium). Live fast conversion of refs/A2.nam through the UI: A2→0.5.4 A1, ESR **0.04403** (<0.05), Download works; bad file isolated to Failed while good completed; /device MOCK banner shown. 4 screenshots in work/screenshots/ (viewed — real content). Fast suite still 31 green (-m "not slow"); slow e2e passes in ~79s. Committed. → Acceptance #1, #2, #5, #6 MET.
- Next: T6 — run.sh already exists (T0); write README (setup + usage), run the full acceptance sweep, mark #7. Then MVP done → notify Drew with screenshots.

## Backlog (DAG)
- [x] T0  scaffold FastAPI app, .venv-app, pytest harness, run.sh        [done]
- [x] T1  engine API: run_job, progress_cb, 0.5.x path, per-file isolation   [done]
- [x] T1b 0.7.0 export path (.venv 0.13.0 + a2a1/train_a1_070.py)   [done]  (#3 MET)
- [x] T2  backend: POST create-job + background exec + GET status/download/list   [done]
- [x] T3  frontend: drag-drop, format toggle, epochs, live progress, download   [done]
- [x] T4  device-stub screen: mocked usage inspector + MOCK banner   [done]  (#4 MET)
- [x] T5  headless e2e (real fast convert via UI) + screenshots + isolation   [done]  (#1,#2,#5,#6 MET)
- [ ] T6  README (setup+usage) + full acceptance sweep + mark #7   (deps: all)  [doing]

## Acceptance (MVP_REQUIREMENTS.md §Acceptance) — 6/7
1. [x] UI: A2.nam → valid 0.5.x A1, format OK, progress shown  (e2e screenshot 03)
2. [x] batch ≥2 + bad-file isolation  (good Done, bad Failed w/ error)
3. [x] both output formats load-valid  (0.5.x + 0.7.0 verified)
4. [x] usage-inspector stub w/ MOCK banner  (/device, screenshot 04)
5. [x] test suite green + headless e2e + UI screenshot  (31 fast + e2e + 4 shots)
6. [x] ESR under threshold  (fast 0.5.x = 0.04403 < 0.05)
7. [ ] run.sh launches; README documents  (T6)

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
