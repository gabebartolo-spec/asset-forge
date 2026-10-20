# Handoff: clean-step (PR #9, builder clean-b8, cause fixes after D-027), 2026-10-20
Brief (lead): D-027 "Keep improving first". Fix CAUSES of the 4 fails of run M2 (6/10), never a
threshold. Bar >= 8/10 on the same 10 -> commit, push into claude/clean-step, LICENCES, sheets,
PR #9 body, plain-word gate messages, test_clean_fox_gates. < 8/10 -> push nothing, report.

## State: stopped at 200k (uncommitted edits in blender/clean.py on claude/clean-step-methodB-local)
Scratch: C:/Users/DANTE/AppData/Local/Temp/claude/C--Users-DANTE-Documents-GitHub-asset-forge--claude-worktrees-session-context-optimization-b3f75f/f1b204c2-5c54-4f23-a732-130a57d70b7c/scratchpad/b8
(measure.py = b7's with the gpu lock always, stale report removed, --python-exit-code;
 mkdump.py + dbg2.py make clean_dump.py that writes GATE_DUMP npz; overlay.py, src_an.py.)
Views reused from b5/runs/B3 (seed 7) via --views-from B3.

## Causes found (evidence)
1. Bird beak (registration): per-row sideways shift cannot move the picture's beak DOWN onto the
   model's beak (overlay b8/bird_ov_small.png: model beak below the picture's). Fix built:
   fit_outline_warp (2D smooth displacement, non-rigid ICP on both outlines, 16x16 nodes,
   smoothness annealed 30 -> 1), animals only (side view). Outline IoU hi3dgen bird 0.786 -> 0.885,
   fox 0.828 -> 0.928. Beak dark 0.0 -> 0.435 (hi3dgen), triposg bird 0.275: both PASS (run W1).
   Proof crop: b8/w_bird_head.png. Cost ~+3 s per animal bake.
2. Hi3DGen fox (and Hi3DGen humanoid torso) is a HOLLOW thin shell: cross-sections b8/slices.png,
   slices_hum.png. 44% of the fox's texels (31% humanoid) sit on the inside wall, seen by no view
   (Blender ray test: 0.6% of them reach their best camera), so they get fill colour and half the
   triangle budget is wasted. Chest box on hi3dgen fox: 0 texels painted by the picture, half fill.
3. TripoSG fox 2 parts: a hind-leg piece (2% of faces) detached in the raw mesh already.
Fix for 2+3 BUILT, NOT WORKING YET (run S1, b8/runs/S1; uncommitted make_solid in clean.py):
make_solid() after the voxel remesh: ray-parity voxel copy (128 on the long side), seal openings
<= 6 voxels, fill the hollow (overlap the wall by 1 voxel), bridge detached parts, second remesh.
S1 (views still B3): hi3dgen fox hollow_share 0.026 < SOLID_MIN_CAVITY 0.03 -> nothing filled
  (no-view still 0.438): the opening is likely wider than the seal, or the parity voxels are wrong;
  check a voxel slice of `solid`/`hollow` against b8/slices.png first.
  triposg fox: bridge found (gap 8 voxels) but only 6 filler voxels -> still 2 parts after the
  second remesh. Make the bridge thicker (grow it 1-2 voxels inside filled) and re-check parts.
  hi3dgen humanoid: hollow 0.31 filled, no-view 0.314 -> 0.089, but greaves_back 0.122 -> 0.129
  with REUSED views (the mesh changed, so the views must be regenerated before judging).
Gate wording: budgets.py already says "Redo runs ..." (effb435). The clean.py SystemExit texts
  (ambiguous head "pass --turn DEG", multiview failed) are still developer words.
test_clean_fox_gates runs the non-MV default route (steps.clean_command has no --mv flags).

## Next
- Fix make_solid (above); then regenerate views for changed meshes; then humanoid greaves_back
  (b8/dbg2.py now also dumps raw per-view colours tc + plane uv for the per-cell match check).
- Then all 10 with fresh views if meshes changed (MV-Adapter batch: src/asset_forge/multiview.py
  --batch, ~63 s/model), sheets, commit, push, PR body.
- test_clean_fox_gates x2 fail on the non-MV route (since 9a2ec52): still to examine.
