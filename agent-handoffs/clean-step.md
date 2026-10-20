# Handoff: clean-step (PR #9, builder clean-b7, method B + per-view colour matching), 2026-10-20
Task (lead brief): one bounded try. Match each MV-Adapter view to the picture's colour statistics
before projecting, measure all 10 against the 9a2ec52 gates, measure/cut the +88 s. Stop rule:
>= 8/10 -> build in, LICENCES rows, sheets, PR #9 body; < 8/10 -> push nothing, keep branch local.

## RESULT: 6/10 (< 8) -> nothing pushed. Branch claude/clean-step-methodB-local stays local.
Run M2 (scratch b7/runs/M2/summary.json, views reused from b5/runs/B3 so seed-7 views identical):
PASS hi3dgen spider, brute; triposg humanoid, spider, brute, bird.
FAIL hi3dgen humanoid greaves_back 0.122 (<= 0.12); hi3dgen fox chest p90 0.81 + chest pale
0.087 + front lower legs dark 0.718; hi3dgen bird beak dark 0.0 (registration, not colour);
triposg fox chest p90 0.838 + single_part (mesh fault, cap).
M1 (first form: vertex samples, 4x8 cells) gave 3/10: too few vertices per cell (~15).

## Method as built (uncommitted->committed on the local branch, see git log)
blender/clean.py: mv_sample_views (per-view colour + weight), mv_blend, srgb_to_lab/lab_to_srgb,
mv_match (per view, per cell of a 6x12 grid over the picture's outline box in the gates'
registration frame: Lab mean/spread of the view's texels -> picture pixels' mean/spread, cell
shrunk to whole-view stats with prior 200 samples, gain clip MV_GAIN), mv_apply (bilinear field).
Replaces the old global per-channel gain/offset.
src/asset_forge/multiview.py: run_batch(jobs) + --batch JOBS.json: loads the generator once.

## Seconds (B3 humanoid): subprocess 89.7 s = ~13 s python/torch import + 16.8 s weight load +
59.4 s denoise (50 steps) + decode; control maps 2 s; bake itself ~4 s.
Batch (--batch, one load, 3 models): wall 212 s = 91 s first + ~60 s each after; views pixel-
identical to the single runs (mean abs diff 0.0), so M2 gates hold. VRAM peak 9.29 GB alloc /
10.9 reserved (cap 11). Per model: ~89 s alone, ~63 s in a batch of 10. Not cut: steps (50).
Sheets: b7/runs/M2s/triposg/humanoid/after (best, pass), b7/runs/M2s/hi3dgen/fox/after (worst).
Tests: clean blender tests 15 pass; test_clean_fox_gates x2 fail = non-MV route, failing since 9a2ec52.

## Known caps
- triposg fox single_part (2 parts) -> max 9/10 for any colour method.
- hi3dgen bird beak: picture beak does not land on the model's beak (texel beak orange 0.77).
