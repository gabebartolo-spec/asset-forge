# Handoff: clean-step (PR #9, builder clean-b10), 2026-10-20
Brief (lead s8, local_1a944552): D-027 "Keep improving first". Fix CAUSES, never loosen a gate.
Bar >= 8/10 five-view sheets -> push into claude/clean-step (PR #9), body, mark ready; method B
the app default (steps.clean_command). Critics are the lead's (fresh realism critic next).

## State: done (bar met, PR #9 ready); waiting on CI and the lead's critic
PR #9 https://github.com/gabebartolo-spec/asset-forge/pull/9, branch claude/clean-step, head
b09e91a + this handoff commit (pushed after marking ready so CI runs). Body has Evidence, Not
exercised, Board and log. Local branch claude/intelligent-vaughan-d9a6e6 in worktree
.claude/worktrees/reverent-liskov-c185ff tracks the same commits.

## Result (R1: this code, fresh MV views)
8/10 region gates; budget gates 10/10; all 10 one part. Sheets: docs/audits/clean/*.jpg.
Run folder (clean.glb, report.json, multiview views):
C:/Users/DANTE/AppData/Local/Temp/claude/C--Users-DANTE-Documents-GitHub-asset-forge--claude-worktrees-reverent-liskov-c185ff/a11a6bd7-8e35-448a-8b13-6cc12dc53b2b/scratchpad/runs/R1
Fails:
- hi3dgen humanoid greaves_back_colour_distance 0.127 (<= 0.12): back greaves 0.28 vs picture 0.20.
- triposg fox chest_p90_luma_ratio 0.838 (0.85..1.25): chest view p90 0.56 vs picture 0.70.
Cause (texel source dump, scratch an_src.py + clean_dbg.py with GATE_DUMP): per-cell mv_match
compares a side-on picture cell (orange flank / bright knee cops) with the same cell's 3D texels
(whole white chest front / back greaves). Failed fixes (2 -> method change): re-match the blend
(fox 0.841, hum 0.14); grid 12x24 (fox 0.850 at limit, hum boots_back 0.121), 9x18 worse.
Proposed next (not built): calibrate each view on PAIRED texels the picture also sees (view vs
picture colour at the same 3D point), back view chained through calibrated side views.
test_clean_fox_gates[triposg] is xfail(strict) with that reason.

## What this session built
- clean.py: escape_count hollow fill (SOLID_ESCAPE 3, SOLID_MIN_CAVITY 0.10, SOLID_FILL_PASSES 4),
  cylinder bridge (r 2.5, +2), union-find _label_big; --gpu-lock DIR around the generator only
  (vram_need("clean:multiview")); plain-words errors.
- steps.clean_command(..., gpu_lock_dir, generator, models_dir): method B flags + lock default
  models_dir/gpu.lock. Main's gpu_lock_dir kept (test_gpu_budget).
- tests: test_clean_solid.py (new, fails on e34508d), clean_fox_gates on clean_command,
  app_matte_steps method B test. tools/clean/run_all.py on clean_command, --from DIR.
- Suites: unit 224 passed (post-merge); -m blender 17 passed, 9 skipped, 1 xfailed (pre-merge);
  post-merge clean_solid/step/forward 10 passed; ruff clean.

## Environment gotchas
- Main .venv lacks fastapi; use session-context-optimization-b3f75f/.venv python with
  PYTHONPATH=<worktree>/src. Set FORGE_MODELS_DIR to the main models/ when in doubt.
- 5 parallel generator starts once crashed torch DLL loading (access violation); rerun passed.
- Times inflated by parallel runs and lock waits; one model alone 3.5-7 min.

## Next
1. Lead: CI on PR #9, fresh realism critic on docs/audits/clean, merge.
2. If assigned: paired view calibration (above); then rerun the 10 with R1 views (--mv-views,
   CPU only, parallel) and remove the xfail.
