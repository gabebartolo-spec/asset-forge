# Handoff: proto (prototype-integration builder)

Branch `claude/prototype` in the lead's worktree (`.claude/worktrees/session-context-optimization-b3f75f`).
Test bed, not a PR. The lead edits only `agent-handoffs/lead.md` here; never stage it.

## Task
Director goal (2026-10-20): "functional build prototype with at least 80% critic pass rate".
1. Integrate #9 (clean-step), step2-page, #20 (animation) into claude/prototype.
2. `tools/e2e/run_e2e.py`: drive the running app over HTTP for 5 bake-off prompts x {hi3dgen, triposg}.
3. Run it once for real; Playwright shots of each step for one humanoid (1920x1080).
Output: `C:/Users/DANTE/AppData/Roaming/Claude/side-session-notes/local_7fdc3e78-46c6-48b7-9439-a48ba40b7296/e2e/run1/`.

## Merge log (for the PR owners)
1. `origin/claude/clean-step` (effb435, PR #9): clean merge, no conflicts.
2. `origin/claude/step2-page` (a131c49): one conflict, `src/asset_forge/gates/budgets.py` (add/add).
   The only difference was the wording of the problem sentences (#9 has the longer plain-words
   "Redo runs ..." lines; step2-page an older terse copy). Took #9's file whole (`--ours`).
   Everything else auto-merged (api.py clean endpoint, jobqueue `_settle`, web/*).
3. `origin/claude/animation` (350dcf2, PR #20): two conflicts.
   - `src/asset_forge/api.py` imports: kept both (`from .animate import NOT_YET, animate` and
     `from .clean_step import ...`). `register_library(..., clean_now)` from step2-page kept, and
     `register_animate(...)` from #20 added after it.
   - `web/app.js` (3 hunks). #20 tracked Step 2 as `state.cleanReady` (a hand-placed clean.glb);
     step2-page tracks `state.clean` (the verdict). Resolution: step2-page's `state.clean`
     everywhere (no `cleanReady` left), plus #20's additions:
     render(): step2-page pill2/pill3 block + `renderPill4()`;
     Next: step 4 -> export/animate, step 3 -> `state.rig ? goStep4() : buildSkeleton()`,
     step 2 -> `state.clean ? goStep3() : runClean()`, else `goStep2()`/`start()`;
     resume: `state.clean && state.rig && animate.result` -> goStep4, else step2-page's
     `state.clean ? (rig ? goStep3 : goStep2)`.
   - `jobqueue.py` auto-merged: `_plain` (#20, knows AnimFailed/ExportRefused) and `_settle`
     (step2-page) both present. CleanFailed subclasses GeneratorError, so `_plain` shows it.
   Result: 279 unit tests pass, ruff clean (merge commit 1dacaad).

## Environment notes
- This worktree has its own `.venv` (uv, py3.12, `pip install -e .[dev]`); the main checkout's
  .venv lacks fastapi. Run tests with `.venv/Scripts/python.exe -m pytest -q`.
- `config.local.toml` (gitignored) here: blender + godot exe. Set `FORGE_MODELS_DIR` to the main
  checkout's `models/` (config's fallback path is wrong for `.claude/worktrees/*`).
- The text drawer is `UnavailableDrawer` (draw/from-text return 501), so the runner uploads the
  bake-off reference `models/bakeoff/refs/<id>.png` instead and records that.
- Five-view sheets (clean/before, clean/after subfolders) are not served by the API (file route
  refuses subpaths): the runner copies them from the library folder on disk. Gap for design 5.7.

## State
Step 1 done. Next: write runner + unit test, run it.
