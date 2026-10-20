# Handoff: animation (anim-b3, Phase 4 first slice), updated 2026-10-20
State: back end, export, cadence fix, API, Step 4 page, previews tool and blender tests committed;
running: blender tests + six-rig previews/export (under models/gpu.lock); then UI real-click proof, PR.
Branch claude/animation (worktree ../asset-forge-wt/animation, own .venv), origin/main merged (f208bd0).
Brief (lead): DONE = draft PR (do not merge), CI green, PR body per forge-pr with Evidence, Not
exercised, Board and log. Clips go to the lead (motion critic), never the director.
Evidence folder: C:/Users/DANTE/AppData/Roaming/Claude/side-session-notes/32c9f533-fe4e-47ae-b55b-70ec62248734/animation/
Scratch: %TEMP%/claude/C--Users-DANTE-Documents-GitHub-asset-forge--claude-worktrees-asset-forge-status-0d338f/32c9f533-.../scratchpad
  (probe.py = gait table on the six rigs, locked_pytest.py = pytest under gpu.lock, reach*.py stroke probes)

## Lead decisions applied
1. In place, speed in clips.json. 2. Loop sidecar <name>.glb.import. 3. Froude speeds, no floors (D-026).
4. (anim-b3 brief) Human walk at real cadence 100-120 steps/min, natural stride, no deep crouch.

## Cadence fix (c761292)
- People: walk Fr 0.20 (L hip-ankle; Perry 1.37 m/s at L~0.83), stride HUMAN_STRIDE walk 1.65 L,
  run 3.0 L; animals/birds keep Alexander 1976 (2.3 Fr^0.3 L).
- Reach: heel strike (toes up 15 deg, rocks about a heel point 0.035 H behind the ankle) and
  push-off about the toe TIP (heel up 45 deg walk, 35 run); toes no longer counter-rotated.
  Reason: Step 3 fit puts the Toes (ball) joint straight under the ankle (fit.py line 107-108:
  Foot at y_heel-0.7 flen, Toes at y_toe+0.3 flen = same y), so a ball pivot adds no stride.
  Report to lead as a Step 3 finding (ankle should be ~0.25 flen from the heel).
- Walk bob_max 0.055 L (hip dip <= 7.5% L); quad walk duty 0.62 (was 0.70), trot 0.38 (was 0.42).
- Six rigs now: humanoid walk 32f 1.29 m/s 0.94 strides/s = 113 steps/min, stride 0.76 H;
  run 3.52 m/s 1.36/s = 163 steps/min. fox walk 2.5/s (rule 2.3-2.5), trot 4.29/s (rule 3.6-3.9,
  reach-capped). bird walk 4.29/s, run 6.0/s (rule 4.2 / 6.0).
- Failing first: old code gave walk 163.6 and run 200 steps/min (tests fail), new passes.

## API (commit 2)
POST /api/assets/{id}/animate (409 no rigged.blend, 400 monster NOT_YET, job step "animate"),
POST /api/assets/{id}/export (409 no animated.glb; job step "export"; exports to
library_dir.parent/exports; writes animate/export.json). jobqueue._plain passes AnimFailed and
ExportRefused words. tests/test_animate_api.py 8 tests.

## Web (commit 3)
index.html panel-4 + pill4; viewer.js playClip(name, speed) + tickClip (grid scrolls at clip speed);
app.js Step 4 functions in one block (renderPill4, renderStep4, buildClipPicker, showClip, goStep4,
runStep4Job, makeAnimations, exportModel). Step 3 "Next: Animate" now enabled.

## Left (in order)
1. Read evidence blender_tests.txt and previews_six.txt; GIFs in previews_v2/.
2. UI real-click proof: scratch server with a library asset seeded from models/skeleton_out
   (clean.glb + skeleton/rigged.blend + result.json), Playwright msedge headless, 1366x768 and
   1920x1080: pill 4 -> Make animations -> clip picker clicks -> Export. Shots to evidence/shots_step4.
3. PR body (forge-pr template), push, draft PR, CI watch, report to lead (<=8 lines).
4. Delete scratch servers; no scratch branches pushed.
