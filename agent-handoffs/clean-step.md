# Handoff: clean-step (PR #9, builder clean-b5, round 5 spike), 2026-10-20
State: stopped at 202k context. Gates-failing-first commit 9a2ec52 pushed; spike B and C in progress.
Task (lead brief): spike (B) multi-view and (C) part-wise wrap, pick the one passing more of the 10
bake-off models on region gates + new fix-list gates, build it into blender/clean.py, tests, audit
sheets (docs/audits/clean/), PR body Evidence (pass count per method, seconds added), Not exercised,
Board and log. Do not mark ready; lead runs a fresh critic. Front-only projection tuning NOT allowed.

## Done
- New gates in clean.py (REGION_GATES + region_gate_checks(name) + model_side_measures + report
  single_part). Round-4 bake measured with them: PASS 2/10 (only the spiders, which have no colour
  gates). Fails: brute x2 shorts_back_colour_distance 0.137/0.141 (<=0.10); hi3dgen humanoid
  torso_back_contrast_ratio 0.11 (>=0.40), boots_minus_greaves_warmth_back 0.008 (>=0.03); triposg
  humanoid also greaves/boots back distance, greaves_back_warmth; foxes lower legs dark (hi3dgen
  front 0.32, hind 0.69; triposg front 0.736 vs >=0.75); triposg fox far_minus_near_neck_pale 0.145
  (<=0.10), tail_end_on_pale 0.206 (<=0.17), single_part parts=2; birds beak_dark_fraction 0.0.
- NOT gated: triposg humanoid breastplate "white streak" = the picture's own specular highlight
  (front white fraction 0.19 vs picture 0.23); ask the lead whether de-lighting is in scope.
- tests/test_clean_fox_gates.py now FAILS on 9a2ec52 by design (failing-first). Needs a new
  test over all 10 models (local, blender marker) once a method passes.

## Method C (part-wise wrap) so far: best PASS 3/10 (scratch b5/patch_wrap.py -> clean_C.py)
- Pieces = connected components of horizontal slabs (WRAP_BAND 0.06 x height, edges inside a
  slab only; first try joined all slabs into one piece - bug). Hidden vertex (a0<0.5) takes its
  piece's visible colour weighted along camera-right (animals: y). Visible weight must INCLUDE
  shadow-dark pixels (shadow rule was dropping dark grey shorts: that is the brute's root cause).
- Result: brute hi3dgen passes; triposg brute 0.117; humanoids improve (triposg only boots 0.147,
  contrast 0.35); animals get WORSE (chest pale drops) - wrap fights the neutral fill.
- Root causes found that C does not fix: bird beak = registration (model beak lands at tv
  0.105-0.127, the thin black beak at ~0.09-0.11; bleed fills orange); hi3dgen fox front leg =
  model leg pose differs, the picture's chest lands on it. Both are visible-side registration.
  Tried opts (WRAP_OPT early,beak,tail,thin): no change on beak; specks were not the cause.

## Method B (multi-view) setup
- Licences (primary sources, 2026-10-20): Zero123++ v1.2 weights CC-BY-NC 4.0 = BANNED; Era3D repo
  README says AGPL-3.0 for code and model while HF card says apache-2.0 = unclear, BANNED;
  MV-Adapter (huanngzh/MV-Adapter) code Apache-2.0, weights huanngzh/mv-adapter apache-2.0, base
  SDXL 1.0 OpenRAIL++ (already CLEARED), VAE madebyollin/sdxl-vae-fp16-fix MIT. Its mesh render
  utils use nvdiffrast (BANNED) - render control maps ourselves, never call mvadapter.utils.mesh_utils.render.
- Chosen: ig2mv SDXL (image + GEOMETRY conditioned: views come out aligned to OUR mesh, which also
  removes the registration problem). README: ~14 GB for i2mv; may need cpu offload on 12 GB.
- Source: models/src/mv_adapter (clone, commit 4277e00). Imports work in models/envs/sdxl
  (torch 2.14 cu130, diffusers 0.41) with PYTHONPATH=models/src/mv_adapter; do not pip into that env
  (shared); extras, if needed, go to a --target folder.
- Download (background, HF_HOME=models/hf): mvadapter_ig2mv_sdxl.safetensors 3.6 GB + VAE.
  Log models/hf_mvadapter_dl_log/dl.log. SDXL base already in models/hf/hub.
- Conventions (read from their code): control = 6 views 768 px, ortho box +-0.55, mesh scaled so
  max |coord| = 0.5 (centre it by bbox first); std frame == Blender frame (x, y, z up); cameras at
  az [-90, 0, 90, 180] el 0 then top (el 89.99, az 90) and bottom (el -89.99, az 90), distance 1.8,
  position (cos el cos az, cos el sin az, sin el); view 0 = camera at -Y = model front (D-021);
  right = lookat x up(z); row 0 = top. Control image = cat(pos+0.5, normal/2+0.5) (6 channels),
  background 0.5 for both. Pipeline call: see scripts/inference_ig2mv_sdxl.py run_pipeline
  (ShiftSNRScheduler interpolated 8.0, DecoupledMVRowColSelfAttnProcessor2_0, 50 steps, cfg 3.0,
  reference_image preprocess to 768 grey bg).
- Plan: clean.py pass 1 --mv-export DIR (numpy raster of pos/normal/depth per view after UV), GPU
  job (gpu.lock) runs ig2mv, pass 2 --mv-views DIR projects views onto texels with z-test,
  weight facing^4; the picture wins only where it directly sees (no mirror); fill elsewhere.

## Scratch (session scratchpad b5/)
measure.py CLEAN TAG [cand/prompt..] [--sheets] [-- args] (runs under gpu_lock, prints gates,
PASS n/10); mkdump.py (GATE_DUMP npz); uvmap.py / sidemap.py / boxstat*.py (diagnostic maps);
runs/<tag>/ outputs; clean_r4gates.py = round-4 bake + new gates.
Bash heredocs containing ''' break in this tool: write patch scripts with Write instead.
