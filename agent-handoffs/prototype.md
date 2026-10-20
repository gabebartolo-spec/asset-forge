# Handoff: prototype (prototype-integration builder)

Branch `claude/prototype` (test bed, not a PR). This session works in worktree
`.claude/worktrees/priceless-kilby-4abc26` on local branch `claude/priceless-kilby-4abc26` and
pushes with `git push origin HEAD:claude/prototype`. The lead's worktree
`session-context-optimization-b3f75f` also has `claude/prototype` checked out (stale local copy);
never edit there. Never stage `agent-handoffs/lead.md`.

## Task
Director goal (2026-10-20): "functional build prototype with at least 80% critic pass rate".
claude/prototype = main + clean-step-methodB-local + step2-page + animation + ref-drawer +
monster-rig; re-merge each as it moves. Run `tools/e2e/run_e2e.py` (5 bake-off prompts x
{hi3dgen, triposg}) + `tools/e2e/shots.py` through the real app; outputs to
`C:/Users/DANTE/AppData/Roaming/Claude/side-session-notes/local_7fdc3e78-46c6-48b7-9439-a48ba40b7296/e2e/run<N>/`.
The lead runs the critics (realism 10 sheets, motion 6 clip sets, screen 4 pages; bar 16/20).

## Merged into prototype (s2, 2026-10-20)
| Branch | sha merged |
|---|---|
| main | 77558d2 (#22 skeleton-fit, #23) |
| claude/clean-step-methodB-local | e34508d (includes WIP 2b14d4d make_solid) |
| claude/step2-page | b655f4b (my file-route fix) |
| claude/animation | e3bae65 |
| claude/ref-drawer | 7a3e8bc |
| claude/monster-rig | 23678e8 |
Prototype tip: ca6fc28 (merge a952cf3 + runner commit).

Monster-rig conflicts (a952cf3): api.py docstring/imports (union), skeleton signature
(monster-rig's `body` param, TODO dropped); app.js state + viewer.js ctor (kept both);
blender/rig.py report: kept foot_pivots and limbs, and foot_pivots is `{}` for monsters
(fit.foot_pivots KeyErrors on template "monster").

Known red on prototype: 3 tests in tests/test_animate.py (four_legged foot slide, faint lying
flat, person bob) come from claude/animation x main #22 (proved: animation alone 79/79,
animation+main 3 red). Logic conflict, the animation lane's (told local_5de871d0).

## step2-page fix (b655f4b, pushed)
File route `/api/assets/{id}/files/{step}/{name:path}` serves one sub-folder
(clean/after/front_clay.png); Store.file_path refuses 2+ levels, dot parts, backslashes,
empty parts. Tests: test_file_path_serves_one_sub_folder + an API traversal case. 193 passed.

## Runner changes (ca6fc28)
Monster: GET /skeleton/limbs, POST the proposal unedited; records limbs_proposed. Step 1
anatomy (limb check) recorded under steps.generate.anatomy. Sheets fetched via the file route,
disk fallback; `views_via` records which. test_e2e_runner 7 passed.

## Environment
- Own `.venv` here (uv-managed cpython 3.12; NOT the Stability Matrix python uv found first:
  use `--python-preference only-managed`). `config.local.toml` copied from the lead's worktree,
  port 7872. `FORGE_MODELS_DIR=C:/Users/DANTE/Documents/GitHub/asset-forge/models`.
- Text drawer is available now (ref-drawer), so references are drawn from the words.
- GPU lock `models/gpu.lock` is shared with other lanes (clean-b10 held it at run2 start).

## State
Run 2 in progress: app PID in e2e/run2/app.pid (msys pid), runner then shots chained in the
background; logs run2/run.log, shots.log, app.log. After: write run2/manifest.md (artefacts +
branch shas), kill only the app PID, report to the lead (6 lines).
