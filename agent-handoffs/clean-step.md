# Handoff: clean-step (PR #9, builder clean-b10, cause fixes after D-027), 2026-10-20
Brief (lead s8, local_95e771b1): D-027 "Keep improving first". Fix CAUSES, never loosen a gate.
Bar >= 8/10 five-view sheets (5 prompts x Hi3DGen, TripoSG) -> push into claude/clean-step (PR #9),
update PR #9 body (Evidence, Not exercised, Board and log), mark ready. Method B is the app default
(steps.clean_command). Do NOT run critics; the lead starts a fresh realism critic.
Report to the lead in <= 6 lines: sha, score, sheet folder path.

## State: running a check (pytest -m blender), then merge main, push, PR #9 body
Worktree .claude/worktrees/reverent-liskov-c185ff, branch claude/intelligent-vaughan-d9a6e6
(contains origin/claude/clean-step effb435). Head 7da7ce8 (+ this handoff). Not pushed.
origin/main merges clean (checked with merge-tree); merge after the suite, rerun unit + ruff.
Director 2026-10-20 (via lead): gpu.lock only for VRAM-heavy work. clean.py `--gpu-lock DIR`
holds it only around the multiview generator; clean_command does not pass it yet (jobqueue
wraps the whole job; the lead's VRAM-budget lock PR changes that).

## Done this session (17e7800)
- blender/clean.py solid rebuild: `escape_count` (26 directions, one 2D-slice sweep each, 0.1-0.9 s,
  identical to b9's slow an1.py); hollow = free voxels with < 3 escapes; fill if share >= 0.10;
  SOLID_FILL_PASSES = 4 re-counts after each fill so an open mouth closes (old ~dil(outside)
  guard dropped 2/3 of the open fox cavity). Bridge = cylinder r 2.5 voxels, +2 into each end.
  `_label_big` is now a vectorised union-find (was 40 s on the hollow fox, now < 1 s). SOLID_SEAL,
  _flood, _ero gone. Offline on b9 dumps: hi3dgen fox hollow 0.605 -> resid 0.0004, humanoid 0.313
  -> 0.0005, triposg fox parts 2 -> 1 (gap 5.8), triposg humanoid 3 -> 1 (gaps 1.4, 2.0); others
  untouched. Slice check: fill stays inside the outline (scratch slices_fill.png).
- steps.clean_command(..., generator, models_dir) adds --generator and the method B flags
  (models/envs/sdxl python, models/src/mv_adapter, models/hf); unit test added.
- Plain-words SystemExit for unclear head direction and failed side painting.
- tests/test_clean_solid.py (blender): open shell, leg 6 voxels off, dented block. Old filler
  (e34508d) fails it: shell filled 0.0, leg still 3 parts. New: passes.
- tests/test_clean_fox_gates.py now runs the app command (method B) under the GPU lock, markers
  blender+gpu, also asserts single_part.
- Unit: 113 passed; ruff clean.

## Results (R1 = pushed code, fresh MV views; scratch runs/R1, sheets in docs/audits/clean)
Scratch: C:/Users/DANTE/AppData/Local/Temp/claude/C--Users-DANTE-Documents-GitHub-asset-forge--claude-worktrees-reverent-liskov-c185ff/a11a6bd7-8e35-448a-8b13-6cc12dc53b2b/scratchpad
8/10 region gates PASS; budget gates 10/10. Fails:
- hi3dgen humanoid greaves_back_colour_distance 0.127 (<= 0.12): back greaves 0.28 vs picture 0.20.
- triposg fox chest_p90_luma_ratio 0.838 (0.85..1.25): chest views p90 0.56 vs picture 0.70.
Cause (dump an_src.py on clean_dbg.py, GATE_DUMP): per-cell mv_match compares a picture cell
(side-on: mostly orange flank / bright knee cops) with the same cell's 3D texels (whole white chest
front / back greaves): population mismatch. 86% of fox chest texels come from the views.
Failed fixes (2, so change method): MV_REMATCH (match the blend again): fox 0.841, humanoid 0.14;
grid 12x24: fox 0.850 at the limit, humanoid greaves pass but boots_back 0.121; 9x18 worse.
Proposed method: calibrate each view on PAIRED texels the picture also sees (view colour vs
picture colour at the same 3D point); back view chained through the calibrated side views.
test_clean_fox_gates[triposg] is xfail(strict) with that reason; hi3dgen passes.
Transient: torch DLL access violation when 5 generator envs start at once (bird); rerun passed.

## Environment gotchas
- Set FORGE_MODELS_DIR=C:/Users/DANTE/Documents/GitHub/asset-forge/models (gpu_lock path guess
  fails in .claude/worktrees).
- Main .venv lacks fastapi; use session-context-optimization-b3f75f/.venv python with
  PYTHONPATH=<this worktree>/src for pytest.

## Next (exact)
1. Blender suite result (scratch blender_suite.log): expect all pass, 1 xfailed.
2. git merge origin/main; unit + ruff; push HEAD:claude/clean-step; PR #9 body (Evidence, Not
   exercised, Board and log: STATUS item 5 -> 8/10 met, follow-up "paired view calibration");
   gh pr ready 9.
3. Report to the lead (<= 6 lines: sha, 8/10, docs/audits/clean + scratch runs/R1); rewrite this.
