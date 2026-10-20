# Handoff: animation (anim-b2, Phase 4 first slice), updated 2026-10-20
State: back end + export done and proven on the six rigs; next API, page, blender tests, previews, PR.
Branch claude/animation (worktree ../asset-forge-wt/animation, own .venv), origin/main merged (037f86a).
Brief (lead): finish anim-b1's WIP; DONE = draft PR (do not merge): unit tests failing first, -m blender
tests, export gate + Godot check incl. loop modes on six rigs, Step 4 page with clip picker (API on the GPU
queue), game-speed GIF per clip per body type in the evidence folder, PR body per forge-pr.
Evidence folder: C:/Users/DANTE/AppData/Roaming/Claude/side-session-notes/32c9f533-fe4e-47ae-b55b-70ec62248734/animation/
Scratch: %TEMP%/claude/C--Users-DANTE-Documents-GitHub-asset-forge--claude-worktrees-asset-forge-status-0d338f/32c9f533-.../scratchpad
  (run6.py animates the six rigs -> anim6/, mutate.py = failing-first mutation runs, probe.py = gait table)

## Lead decisions applied
1. In place, speed in clips.json (+ froude, strides_per_s). 2. Loop sidecar <name>.glb.import (idle/walk/run
loop_mode 1); Godot honours it: proven by check_import (real `--import` in a scratch project): no sidecar ->
loop mode 0 (fails), with sidecar -> LOOP_CHECK_OK. 3. Floors dropped: v = sqrt(Fr g L), Fr walk 0.25 all,
run 1.5 humanoid / 2.0 four_legged trot / 1.5 bird; stride by Alexander (2.3 Fr^0.3 L), capped by reach;
cadence follows. Heel lift at push-off (pivot ball for humanoid, toes counter-rotated; paw tip for
animals) + per-leg reach window. Small bodies keyed at 60 fps (run stride < 12 keys at 30).

## Commits since WIP
cddf3b6 Froude gait, heel lift, tests/test_animate.py + tests/anim_factory.py
(stall check: duplicate seam frame only if motion keeps direction; turning sway is not a hitch)
29f14d2 export/animated.py export_animated (measure_glb gate: tris, materials, texture px, bones,
influences; budgets section 6), godot_check.loop_sidecar/write_loop_sidecar/check_import,
godot/import_check/check_import.gd, tests/test_export_animated.py

## Numbers (six rigs, exported glb checks; evidence export_godot_six.txt)
All six: Godot RIG_CHECK_OK + LOOP_CHECK_OK clips=6 looping=idle,walk,run; gate in budget.
worst planted slide 0.21 cm (triposg fox run). Seams exact.
bird L=0.06 m: walk 0.38 m/s 4.3 strides/s; run 0.94 m/s 6.0/s (60 fps)
fox L=0.165-0.193: walk 0.64-0.69 m/s 3.0/s; trot 1.80-1.95 m/s 4.3/s (60 fps)
humanoid L=0.84: walk 1.44 m/s 1.36/s (163 steps/min, brisk; real ~2 steps/s); run 3.52 m/s 1.67/s
Open for lead (no change made): human walk cadence is brisk because hip drop budget is 0.07 L;
0.10 L would give 1.16 strides/s but a deeper knee bend. Taste call.

## Left (in order)
4. API: POST /api/assets/{id}/animate (job on GPU queue, needs skeleton/rigged.blend; monster -> 400
   NOT_YET), POST /api/assets/{id}/export (export_animated). tests/test_animate_api.py, animate() mocked.
   Mirror the skeleton endpoint in src/asset_forge/api.py (line ~294).
5. Web: index.html panel-4 (clip picker Idle Walk Run Attack Hit Faint), viewer.js playClip(name)
   (AnimationMixer + mixer.update), app.js step 4 wiring in its own functions (keep diff small; #17
   Library touched app.js). Real-click proof (browser automation).
6. tests/test_animate_blender.py (-m blender): animate on fixture rig -> checks pass; Godot rig +
   import loop check; control without sidecar fails.
7. tools/animate/previews.py: gpu_lock(models/gpu.lock) -> animate --previews -> GIF per clip per body
   (PIL, 30 fps, durations [30,30,40]) into the evidence folder. Lock was clean-b5's at 13:17.
8. Full unit suite + ruff, PR body (forge-pr template), report to lead (<=8 lines). Delete scratch.
