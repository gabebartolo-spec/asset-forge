# Handoff: clean-step (PR #9, builder clean-b10, cause fixes after D-027), 2026-10-20
Brief (lead s8, local_95e771b1): D-027 "Keep improving first". Fix CAUSES, never loosen a gate.
Bar >= 8/10 five-view sheets (5 prompts x Hi3DGen, TripoSG) -> push into claude/clean-step (PR #9),
update PR #9 body (Evidence, Not exercised, Board and log), mark ready. Method B is the app default
(steps.clean_command). Do NOT run critics; the lead starts a fresh realism critic.
Report to the lead in <= 6 lines: sha, score, sheet folder path.

## State: running a check (R1 TripoSG x5 in parallel), nothing pushed yet
Worktree .claude/worktrees/reverent-liskov-c185ff, branch claude/intelligent-vaughan-d9a6e6
(contains origin/claude/clean-step effb435 + methodB-local e34508d). Commits 17e7800, a75cd87,
then the --gpu-lock commit with this handoff.
Director 2026-10-20 (via lead): gpu.lock only for VRAM-heavy work; CPU Blender runs unlocked in
parallel. clean.py `--gpu-lock DIR` holds the lock only around the multiview generator.
clean_command does NOT pass it yet (jobqueue wraps the whole job; the lead's VRAM-budget lock PR
changes that).

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

## Running jobs
R1 results: scratch runs/R1/<cand>/<prompt>; hi3dgen in R1.log, TripoSG in R1_t_<prompt>.log
(scratch measure2.py = measure.py without the outer lock; started 17:32, ~5-8 min each).
Scratch: C:/Users/DANTE/AppData/Local/Temp/claude/C--Users-DANTE-Documents-GitHub-asset-forge--claude-worktrees-reverent-liskov-c185ff/a11a6bd7-8e35-448a-8b13-6cc12dc53b2b/scratchpad
hi3dgen: spider, brute, fox, bird PASS; humanoid FAIL greaves_back_colour_distance 0.127 (<= 0.12):
back greaves albedo mean 0.28 vs picture 0.20; crop greaves_crop.png: same steel, but polished
and brighter than the picture's dark steel (the MV views light steel brighter; mv_match cells
6x12 + prior 200 + bilinear leave it light). Front greaves 0.24.

## Environment gotchas
- Set FORGE_MODELS_DIR=C:/Users/DANTE/Documents/GitHub/asset-forge/models (gpu_lock path guess
  fails in .claude/worktrees).
- Main .venv lacks fastapi; use session-context-optimization-b3f75f/.venv python with
  PYTHONPATH=<this worktree>/src for pytest.

## Next (exact)
1. Read R1.log when done; count passes. If < 8, fix causes (greaves_back first: check the back
   view's matching in rows 8-10 of the grid), rerun only changed models.
2. `python tools/clean/run_all.py --from <scratch>/runs/R1` -> docs/audits/clean sheets/table.
3. pytest -m blender (incl. fox gates, GPU) green; ruff; unit.
4. Push to claude/clean-step (fast-forward from effb435; check main merge needs), update PR #9
   body, mark ready. Board and log: STATUS item 5 row; D-TBD none unless the lead wants
   SOLID_MIN_CAVITY recorded.
5. Report to the lead; rewrite this handoff.
