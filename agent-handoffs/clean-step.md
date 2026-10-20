# Handoff: clean-step (PR #9, builder clean-b6, round 5 method B), 2026-10-20
Task (lead brief): run method B (MV-Adapter ig2mv SDXL) on all 10 bake-off models against the
gates of 9a2ec52 (round 4: 2/10; method C best 3/10). If B beats C, build it into clean.py; if
neither reaches 8/10, stop and report numbers (no further tuning). Do not mark ready.
Lead decisions: de-lighting the picture OUT of scope (triposg breastplate streak = picture's own
highlight -> Not exercised). Zero123++ / Era3D banned. If B wins: LICENCES rows for MV-Adapter,
SDXL base, fp16-fix VAE. Extra: gate messages in src/asset_forge/gates reworded plain (DONE,
uncommitted; tests/test_gates_budgets.py passes with PYTHONPATH=src).

## State (uncommitted in worktree)
- blender/clean.py: MV block (mv_frame, mv_cameras, mv_pixel, mv_control numpy z-buffer raster,
  mv_write_control, mv_load_views, mv_sample z-test + facing^4, mv_generate subprocess). bake_colour
  takes mv=; under MV the mirror is off (use_mirror), fill sources = picture's sunlit vertices
  else view colours, texel base = views blended over fill by summed weight / MV_FULL_WEIGHT;
  MV_PICTURE=True keeps the picture on directly-seen texels (variant False = views everywhere).
  Args: --mv-python EXE --mv-src DIR --hf-home DIR, or --mv-views DIR (reuse generated views).
- src/asset_forge/multiview.py: runs in models/envs/sdxl (python -I, by path), cpu offload,
  writes view_k.png + multiview.json (seconds, VRAM peak).
- Weights: models/hf/hub mv-adapter snapshot 6de4033, VAE 207b116, SDXL base present.

## Measure
scratch b5/measure.py CLEAN TAG [jobs] -- --mv-python M/envs/sdxl/Scripts/python.exe
  --mv-src M/src/mv_adapter --hf-home M/hf   (M = main repo models/). Runs under gpu_lock.
Runs: B1 fp16 full GPU = 15 GB peak, spilled, 1409 s (unusable). Fixes in multiview.py: text
encoders encode then leave the GPU; UNet stored fp8 (layerwise casting); duplicate reference cache
dropped by a pre-hook; views decoded one by one -> peak 7.56 GB, 76 s per model (fp8 views look
the same as fp16, compared front/back). Picture is 2% of texels on triposg humanoid anyway.
B2v: global per-channel calibration of views to picture added (MV_GAIN). Humanoid still fails
greaves/boots back: the generator lights the back brighter (view 2 greaves luma 0.55 vs front 0.23).
B3 = all 10 models, current code (scratch runs/B3).

## Known caps
- triposg fox fails single_part (mesh has 2 parts): no colour method fixes it -> max 9/10.

## Method C (clean-b5): best 3/10 (scratch b5/clean_C.py, part-wise wrap of horizontal slabs).
Round-4 fails (9a2ec52 gates): brute shorts back x2, humanoid torso/greaves/boots back, fox lower
legs + far neck + tail end-on, bird beak (registration), triposg fox single_part.
