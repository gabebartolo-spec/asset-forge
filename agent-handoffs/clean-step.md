# Handoff: clean-step (PR #9, builder clean-b9, cause fixes after D-027), 2026-10-20
Brief (lead): D-027 "Keep improving first". Fix CAUSES of the fails, never loosen a gate threshold.
Bar >= 8/10 on the same 10 (9a2ec52 gates) -> push into claude/clean-step (PR #9), five-view
sheets untextured + textured for all 10, plain-words gate messages (D-014: name the one click,
"Press Redo"; no "Decimate harder"), PR #9 body with Evidence and Not exercised, mark ready.
Also (lead, added): when the bar is met, make method B the app's DEFAULT Clean route
(steps.clean_command + the GPU queue, freeing ComfyUI VRAM before the bake) and settle
test_clean_fox_gates against that route. < 8/10 -> push nothing to PR #9, report numbers.

## State: stopped by the director's rule change (2026-10-20), mid-diagnosis, nothing running
Branch claude/clean-step-methodB-local, WIP commit 2b14d4d (b8's make_solid + outline warp).
No code changed after 2b14d4d. Last full run: S1 (b8, views reused from B3): 6/10-ish; fails
hi3dgen fox chest (hollow), triposg fox single_part=2 + chest_p90, hi3dgen humanoid greaves_back.
Scratch b9: C:/Users/DANTE/AppData/Local/Temp/claude/C--Users-DANTE-Documents-GitHub-asset-forge--claude-worktrees-session-context-optimization-b3f75f/f1b204c2-5c54-4f23-a732-130a57d70b7c/scratchpad/b9
 (vdump.py: Blender, remesh like main + voxel_solid + unseen-vertex share, dumps vd/*.npz;
  an1.py: numpy hollow measures; an2.py: detached-part gap.) b8 scratch is the sibling b8/.

## Measured (b9, all 10 raw meshes, 128-voxel solid after the 1/220 voxel remesh)
Why make_solid did nothing on the hi3dgen fox: its cavity is OPEN, so the seal trick fails
(hollow share by seal radius 3/5/8 voxels = 0.026/0.047/0.178). Escape-direction measure works:
a free voxel is "outside" if a straight line in >= 3 of the 26 grid directions reaches the border
without hitting solid; the rest is cavity. Cavity share (cavity / (solid+cavity)) with esc<3:
  hi3dgen fox 0.605, hi3dgen humanoid 0.313 (the two hollow shells)
  every other model <= 0.017 (triposg humanoid 0.017 crevices; birds, spiders, brutes, triposg fox ~0)
Unseen-vertex share (no escape ray in 26 dirs): hi3dgen fox 0.384, hi3dgen hum 0.225, but triposg
  hum 0.176 (crevices) -> vertex share overlaps, so trigger on the cavity share instead.
DECISION from data: SOLID_MIN_CAVITY = 0.10 on the esc<3 cavity share (gap 0.017 .. 0.31).
TripoSG fox detached piece: 314 voxels (0.3% of solid), a lower hind leg, bbox x92-106 y76-82
  z19-38; gap to the body ~5.8 voxels, roughly vertical (part pt [100,79,38] body pt [103,79,43]).
  The old bridge (intersection of the two dilations) is a thin lens (6 voxels) -> still 2 parts.

## Next (exact)
1. In blender/clean.py solid_filler: replace the seal/flood hollow with the escape count.
   Fast version (numpy only; no scipy in Blender or .venv): per direction d, sweep slices along a
   nonzero axis of d from the border side: e[i] = free[i] & shift2d(e[i - step], other comps of d),
   out-of-grid counts as escaped. 26 dirs x ~160 slices of 2D ops, well under 1 s. (an1.py's
   iterate-until-stable version takes ~15 s per model: too slow for the app.)
   outside = free & (cnt >= 3); cavity = free & ~outside; fill if share >= 0.10:
   filler |= dil(cavity,1) & ~dil(outside,1) (as before). SOLID_SEAL then goes.
2. Bridge: dilate the part until it touches the body (k steps), take one contact voxel, nearest
   part voxel and nearest body voxel to it, paint a cylinder radius 2.5 voxels between them,
   extended 2 voxels into each end; then re-check parts on the voxel grid (expect 1).
3. Blender run of make_solid alone on hi3dgen fox/humanoid + triposg fox (use vdump.py pattern):
   check cavity filled (slice image vs b8/slices.png), parts == 1 after the second remesh.
4. Regenerate MV views for every changed mesh (those 3): clean.py with --mv-python/--mv-src (see
   b8/measure.py and src/asset_forge/multiview.py --batch, ~63 s/model), others reuse B3 views
   via measure.py --views-from B3. gpu lock: tools/bakeoff/gpu_lock.py run <who> -- ...
5. Run all 10 (b8/measure.py, rename the lock owner), compare with gates; humanoid greaves_back
   only judged with fresh views. Then the bar branch above.
6. test_clean_fox_gates x2 fail on the non-MV route since 9a2ec52: settle against method B once
   it is the default route.
Gate wording: budgets.py says "Redo runs ..." (effb435); clean.py SystemExit texts (ambiguous head
"pass --turn DEG", multiview failed) are still developer words: rewrite in plain words.
