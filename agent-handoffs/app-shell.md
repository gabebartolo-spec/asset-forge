# App shell builder handoff (2026-10-20)
## State: fixing PR #8 screen-critic + walk-through findings (10 items), then live recapture

## Task
Draft PR #8 (branch claude/app-shell). Lead brief: fix 10 findings (card VRAM 5 GB, heading at 1366,
no control jump on result, VRAM wrap, Redo disabled style, text >= 13 px / 4.5:1, type buttons 44 px,
hint wording, queue state + mm:ss counter, selected-maker mark), recapture live to
side-session-notes local_d40f4221.../pr8_live2 (shots.md), update PR body Evidence, leave draft.

## Where things are
- Backend `src/asset_forge/` (jobqueue already had queued/waiting/running + elapsed_s; new API test
  `test_job_status_tells_waiting_for_the_gpu_from_running`). Page `web/` (app.js, style.css, index.html).
- Message moved: the "Happy with it?" / error note now lives in the footer (fixed min-height), not the panel.
- Live driver + server in scratchpad (live.py, serve.py, port 7872); library dir scratch.

## Left
Recapture, shots.md, push, CI, PR body. Then report to lead (head sha, CI run, contrast 5.63 min).
