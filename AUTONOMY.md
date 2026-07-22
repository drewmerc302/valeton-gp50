# Autonomous Build — Overseer Protocol

The overseer runs as a self-paced loop. It builds the converter MVP
(`MVP_REQUIREMENTS.md`) to acceptance, unattended, notifying Drew (mobile) only on
milestones / done / hard block. This file is the overseer's operating manual; it re-reads
it every iteration.

## Agent roster (models / effort)
- **Overseer** — the loop itself (Fable, high effort). Plans, dispatches, integrates,
  decides continue/stop, notifies. Does not write feature code directly.
- **Architect** — one-shot at start (Opus/Fable, high): blueprint + task DAG → seeds STATUS.
- **Implementer** — per task (Sonnet, medium). Worktree-isolated when tasks run in parallel.
- **Tester** — (Sonnet, medium): writes + RUNS tests, drives the app headless, returns
  evidence (command output, exit codes, screenshot paths). Never "looks good to me".
- **Reviewer** — (Opus/Fable, high): adversarial diff review before every merge.
- **Mechanical** — (Haiku, low): renames, formatting, trivial fixups.

## Loop iteration (one bounded increment per tick)
1. **Load state:** read `MVP_REQUIREMENTS.md`, `STATUS.md`, `git log`/diff, and any new
   Drew messages. Reconcile.
2. **Pick** the next unblocked task (respect the DAG; prefer unblocking the critical path).
3. **Implement:** spawn Implementer(s) for the task (parallel + worktree only if truly
   independent). Keep tasks small (≈1 module / endpoint / screen).
4. **Verify:** spawn Tester → run the suite + a targeted check for this task → capture
   evidence. No evidence ⇒ treat as failed.
5. **Review:** spawn Reviewer on the diff → must pass (correctness + no scope creep) before merge.
6. **Integrate:** on green, commit to the run's task branch with a clear message + evidence
   summary; update `STATUS.md` (task→done, notes, next). On red, file a fix task; loop.
7. **Decide:** if all acceptance criteria pass → **stop, push Drew a "MVP ready" summary
   with screenshots**. If hard-blocked → **stop, push the blocker + question**. Else
   schedule the next tick and continue.

## Guardrails (NON-NEGOTIABLE)
- **Never** send MIDI to / read / write the physical pedal. No device I/O whatsoever.
  Device features stay mocked. If a task implies real hardware, mark it blocked-on-Drew.
- Work only on a dedicated task branch cut from `master` at the start of the run.
  Commit only on green (tests + review). **Never** commit directly to, force-push,
  or reset `master`.
- Every iteration emits test evidence. Claims without run output are rejected.
- **3-strikes:** if one task fails 3 iterations, stop and push Drew the problem + options.
- Stay in MVP scope (`MVP_REQUIREMENTS.md`). No gold-plating. Defer nice-to-haves to a list.
- Keep `STATUS.md` current every tick — it's Drew's window + the loop's memory.
- Escalate via push notification on: MVP done, hard block, 3-strikes, or scope ambiguity.

## Mobile steering
Drew may send messages any time. Read them at step 1 and adapt (reprioritize, change scope,
answer a blocker). If he's silent, keep going under these rules.

## STATUS.md format
```
# STATUS — GP-50 Converter MVP
updated: <when> | branch: <task-branch> | phase: <n> | acceptance: X/7

## Now / next
- <one line: what this tick did, what's next>

## Backlog (DAG)
- [ ] id  desc            (deps: …)  [state: todo|doing|blocked|done]  (evidence: …)

## Acceptance (MVP_REQUIREMENTS.md §Acceptance)
1..7 with pass/fail + evidence link

## Blocked-on-Drew (hardware-gated, do not attempt)
- device features 2-6: need capture/checksum

## Notes / decisions
```

## The recurring loop prompt (what re-fires each tick)
> Autonomous overseer for the Valeton GP-50 converter MVP. Each iteration: read
> `/Users/drewmerc/workspace/valeton/AUTONOMY.md` (full protocol), `MVP_REQUIREMENTS.md`,
> `STATUS.md`, recent git state, and any new user messages; execute exactly ONE bounded
> increment (implement → test-with-evidence → adversarial review → commit-on-green → update
> STATUS) using the specified worker agents/models; then either stop+notify (MVP done / hard
> block / 3-strikes) or schedule the next tick. NEVER touch the physical pedal or send MIDI.
> Work only on a task branch cut from `master`; never commit directly to master.
