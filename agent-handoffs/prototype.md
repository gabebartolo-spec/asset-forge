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

## Merged into prototype (s2, 2026-10-20) - tip 7eb6387
| Branch | sha merged |
|---|---|
| main | aefe9be (#28 VRAM-budget lock, #26 drawer, #29) |
| claude/clean-step-methodB-local | e34508d (includes WIP 2b14d4d make_solid) |
| claude/step2-page | b655f4b (my file-route fix) |
| claude/animation | b80830c (main merged, gait reds fixed) |
| claude/ref-drawer | 7a3e8bc |
| claude/monster-rig | 23678e8 |

Monster-rig conflicts (a952cf3): api.py docstring/imports (union), skeleton signature
(monster-rig's `body` param); app.js state + viewer.js ctor (both); blender/rig.py
foot_pivots is `{}` for monsters (fit.foot_pivots KeyErrors on "monster").
Main #28 conflicts (277e32b): jobqueue end state keeps step2-page's `_settle` (save a copy,
then flip) with #28's admit order; steps.clean_command takes generator + gpu_lock_dir;
test_app_queue keeps both tests. Clean submits need="clean:multiview" (whole card) in the
page and batch, because method B's clean.py does not take --gpu-lock yet. 375 unit passed.

## step2-page fix (b655f4b, pushed)
File route `/api/assets/{id}/files/{step}/{name:path}` serves one sub-folder
(clean/after/front_clay.png); Store.file_path refuses 2+ levels, dot parts, backslashes,
empty parts. Tests: test_file_path_serves_one_sub_folder + an API traversal case. 193 passed.

## Runner changes (ca6fc28)
Monster: GET /skeleton/limbs, POST the proposal unedited; records limbs_proposed. Step 1
anatomy (limb check) recorded under steps.generate.anatomy. Sheets fetched via the file route,
disk fallback; `views_via` records which. test_e2e_runner 7 passed.

## Environment
- Own `.venv` here (uv-managed cpython 3.12, `--python-preference only-managed`; uv first found
  the Stability Matrix python). `config.local.toml` port 7872.
  `FORGE_MODELS_DIR=C:/Users/DANTE/Documents/GitHub/asset-forge/models`. The lead's old app may
  hold 7871: never kill it.
- Scratchpad helpers: rerun_animate.py (animate + export only), manifest.py, run_vramgate.py,
  app_ownlock.py (private lock; dropped after #28).

## Run2 result (e2e/run2/manifest.md, index.md)
2 of 10 prompts exported (hi3dgen_bird; plus pageshots_hi3dgen_humanoid, the page-shots model).
Clean FAIL: both humanoids (top outline 0.084 / 0.129 > 0.08); both foxes (clean.py: "animal
head direction is ambiguous ... pass --turn DEG"; the app passes no --turn and shows a generic
error). Monsters: skeleton pass, animate refused (later version). triposg_bird: walk foot slide
0.7 > 0.5 cm. Step 1 limb check fails on every monster and fox.

## State
Done: run2 delivered, app stopped, report sent to the lead. Next only on the lead's word.
