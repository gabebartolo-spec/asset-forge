# App shell builder handoff (2026-10-20)
## State: done, draft PR open; waiting for lead

## Task
Phase 2 item: app shell + Step 1 (Generate) + generator menu (director 2026-10-20). Worktree
`asset-forge-wt/app-shell`, branch `claude/app-shell` (cut from claude/bakeoff; merge origin/main
once PR #6 lands, never rebase).

## Where things are
- Backend `src/asset_forge/`: config, gpu_lock (same mkdir lock as tools/bakeoff), store (library
  layout), jobqueue (one worker, holds models/gpu.lock), generators (Hi3DGen, TripoSG run the
  bake-off adapters in `models/envs/<id>`), matte (plain-background cut-out), steps (clean_command
  hook for Step 2), api (FastAPI, 127.0.0.1).
- Page `web/` (plain JS, vendored three.js r186 in `web/vendor/three`), `AssetForge.bat`.
- Tests `tests/test_app_*.py` (36 pass), ruff clean. App venv `.venv` (uv, py3.12, gitignored).
- Evidence driver (scratchpad `run/serve.py`, `run/drive.py`): Edge headless via Playwright,
  real clicks, Hi3DGen on fox.png through the queue; shots in `scratchpad/run/shots`.

## Left
Nothing for me. Evidence: real Hi3DGen run on fox.png through the queue, 70 s and 73 s, 6.15 GB VRAM peak.
