# library builder handoff (2026-10-20)
## State: branch claude/library pushed, PR NOT opened (3-PR cap); lead opens it. Screens go to the screen critic.

Task: Phase 6 Library and batch (Library tab, batch queue, step timings). No GPU; generation mocked.
Worktree asset-forge-wt/library (own .venv, gitignored). Run: PYTHONPATH=src .venv/Scripts/python.exe -m pytest.

## Done
Backend: store.py (trash/restore/duplicate/cards, record_timing, lock on asset.json), library.py (routes,
batch), api.py (draw_now/generate_now pulled out of the two job bodies, timing hook in persist,
register_library call), jobqueue.py (+Job.settled). Web: web/library.js (new), small hooks in app.js
(showTab, openAsset, init), index.html (Library tab + section), style.css (appended).
Tests: tests/test_library.py (16). Full suite 115 pass x3, ruff clean, test_app_queue unchanged and green 8x.
Screenshots (scratch, not in git): scratchpad/shots/lib_{1366,1920}_{1_library,2_batch_filled,3_batch_running,
4_batch_done,5_removed,6_opened}.png, real clicks/typing via playwright on Edge (shots.py, serve.py beside them).

## Judgement calls (tell lead if wrong)
- Batch = one queue job per prompt: draw picture, then 3D model. Clean up is not wired yet (501), so it stops
  at Generate; add Clean to `run` in library.py when it lands. Needs a drawer: with none (today: PR #11 not in)
  the button is off and the page says so in plain words.
- Batch uses the generator selected on the 3D tab (default first in menu). No other setting.
- Thumbnail = the reference picture (generate/input.png). Text assets without a picture show "No picture yet".
- Open = resume at last finished step (Skeleton page if clean.glb exists); "Open at Make" extra button when
  skeleton is reached. Clean up / Animate are not built, so no chip for them yet.
- Copy copies every step folder; Remove/Copy refused (409) while a job is queued or running.
- No delete endpoint at all: trash only, "Put back" restores.

## PR body (ready to paste)
## What the director gets, and why
The Library tab works: every model with its picture, type, date, last finished step and how long each step
took; Open resumes where it left off; Copy duplicates; Remove moves to a Removed list with Put back (never
erased). "Make several at once": type up to 20 descriptions with types, press once, they run one after
another on the one GPU queue with live progress ("Model 2 of 3", who is ahead). Fast to get: no waiting
at the screen for each one.

## Assigned in
STATUS.md Phase 6 (ROADMAP: Library, batch queue, step timings); design 5.4, 5.5.

## What changes
- store.py: library/_trash/<id> (move, never delete), duplicate, cards, per-step seconds in asset.json
  "timings" (draw, generate, skeleton...), lock around asset.json writes.
- library.py: GET /api/library[?trash=1], POST /api/assets/{id}/duplicate|trash|restore, POST /api/batch,
  GET /api/batch/{id}. api.py: draw and generate bodies moved into draw_now/generate_now (same code, shared
  with the batch); persist records timings when a job ends. jobqueue.py: Job.settled (end state on disk)
  so Remove/Copy cannot race a finishing job.
- web: library.js, Library tab on, openAsset in app.js; /?asset=ID now goes through the same openAsset.

## Evidence
- Suites: full unit 115 passed (16 new in tests/test_library.py), ruff clean; test_app_queue/test_skeleton_api
  unchanged and green (8 repeated runs of library+queue).
- Capture: real clicks and typing at 1366x768 and 1920x1080, fake makers + mock drawer, batch of 3:
  scratchpad/shots/lib_*.png (library, rows filled, batch running, batch done, removed + Put back, Open).
- Race found and fixed: "done" showed before status.json was written, so Remove right after a job could
  hit 409 (or move the folder under the final write): guarded by Job.settled, test polls for it.

## Not exercised
Real GPU generation and the speed targets of design section 6 (no real timings measured, only recorded);
Clean step in batch (not wired); the real drawer (PR #11); Library with hundreds of assets (thumbnails load
lazily, no paging); Windows-only paths for trash move tested on Windows only; screen-critic and first-use
walk-through not done.

## Board and log
Row: Phase 6 Library/batch/timings built, PR pending. D-TBD-batch-stops-at-generate: batch runs draw + 3D
only until Clean is wired; then Clean is added and it stops at Skeleton per design 5.5.

## [MERGE NOTE]
- Hot files touched: api.py (two bodies extracted, one call added), web/app.js (hooks at end + init), jobqueue.py (+1 field)
- Review needed: lead + screen critic
- Director gate: none (look approval after critic)
- Ordering with other PRs: app.js/index.html header tabs conflict possible with sprites (Sprite tab line)
