# Handoff: animation (anim-b1, Phase 4 first slice), updated 2026-10-20
State: back end works on the real hi3dgen humanoid (pure clips -> Blender keys -> NLA -> animated.glb with 6 clips;
glb checks pass: slide <=0.05 cm, seams exact). Committed WIP on claude/animation. Context handoff at ~200k.
Worktree ../asset-forge-wt/animation, own .venv (uv, py3.14; `uv venv .venv && uv pip install -e ".[dev]"`).
config.local.toml copied from ../clean-step (gitignored). Baseline unit suite 99 passed.
Inputs: main checkout models/skeleton_in (clean.glb x6), models/skeleton_out/<gen>/<animal>/rigged.blend (from #15).
Brief (lead): Step 4 for humanoid / four-legged / bird; clips idle, walk, run, attack, hit, faint in ONE .glb + .blend;
export gate + headless Godot check; Step 4 panel with clip picker; monsters/6+ legs plain-words "later" (NOT_YET).
DONE = draft PR: unit tests failing-first (foot-slide, clip names, loop seams), -m blender tests, Godot OK x6,
GIF per clip per body type in evidence folder, PR body per forge-pr. Do not merge. Clips go to the lead only.

## Built (src/asset_forge/animate/)
- kin.py: rot, rot_between, frame, about, two_bone_ik. Frame: Z up, faces -Y, +X left.
- body.py: Body (from_joints / from_skeleton_report / bones), Leg (template pole: humanoid knee fwd, quad front back,
  hind fwd, bird back), ground_z (raised paw -> ground; short_legs when bones cannot reach), Pose, solve()
  -> delta 4x4 per bone. Hips move rides on Root (Hips is connected to Root's tail; connected bones cannot translate).
- gait.py: Gait (duty, stroke, Hermite swing matching planted speed), BIPED/QUAD_WALK/QUAD_TROT, foot_slide metric.
- curves.py: pchip + Keys (shared key times). clips.py: Animator + Humanoid/FourLegged/Bird, six clips each,
  make_clips(body), ground_offsets() for the faint. Hip drop from the reach limit (REACH .97, _periodic_cover).
  Cycle frames Froude-scaled with floors (walk >=24, run >=16): bird walk 0.04 m/s, fox 0.23 (flag to lead).
- check.py: read_animations (glb), world_positions (node FK), seam_errors (pop + stall), check_animated_glb
  (names exact, loop pop/stall, foot slide on the exported file; faint excluded).
- __init__.py: animate(rigged_blend, out_dir, blender_exe, asset_type) -> AnimResult; AnimFailed; NOT_YET.
- blender/animate.py: opens rigged.blend, keys every frame (basis = rest^-1 Dp^-1 D rest), faint grounding from the
  skinned mesh (moves Root only), NLA track per clip, export NLA_TRACKS, clips.json; --previews DIR renders PNGs
  (workbench, checker floor running at clip speed, az 55 el 12). Takes ~1 s without previews.
- Probe: scratchpad/probe.py (pure) shows all six rigs: no IK shortfall, slide ~0 except faint (excluded).

## Left (in order)
1. Unit tests tests/test_animate.py: foot_slide fails on a sliding track (show failing first: e.g. Gait with wrong
   speed), clip-name check fails on a glb missing 'run', seam check fails on a pop and a stall (write a tiny glb
   with tests/glb_factory or skin_factory + animations), IK reaches, loop frame N == frame 0, knee bends forward.
   Use `from test_skeleton import stick_human, stick_fox, stick_bird` + fit.fit -> Body.from_joints.
2. tools/animate/previews.py: per model: gpu_lock(models/gpu.lock) -> animate --previews -> GIFs (PIL, durations
   [30,30,40] ms, label clip + speed) into evidence folder
   C:/Users/DANTE/AppData/Roaming/Claude/side-session-notes/<session>/animation/ (pick one, say it in the report).
   gpu.lock was held by clean-b5 at 13:15; wait in background, never poll.
3. Export: export_animated(asset_dir...) in src/asset_forge/export/: gate on the MEASURED final glb (tris, materials,
   texture px from PNG header, bones, influences via skeleton.glb.read_skin) using asset_forge.gates.check if present
   (PR #9, not on main) else a local table mirroring design section 6; + godot_check.check_rig (maybe print clip names
   in check_skeleton.gd). Refuse with the broken limit in plain words. Test with an over-budget glb (failing first).
4. API: POST /api/assets/{id}/animate (queue job, needs skeleton/rigged.blend; monster -> 400 NOT_YET),
   POST /api/assets/{id}/export. tests/test_animate_api.py with animate() mocked.
5. Web: index.html panel-4 (clip picker: Idle Walk Run Attack Hit Faint), viewer.js playClip(name) with
   AnimationMixer (+ mixer.update in loop), app.js step 4 wiring (Next on step 3 -> Animate). Real-click proof.
6. tests/test_animate_blender.py (-m blender): animate on tests/fixtures blockman/blockfox rig -> 6 clips, checks pass,
   Godot import OK. Then Godot check on all six skeleton_out rigs' animated.glb.
7. PR body (forge-pr template): Evidence, Not exercised, Board and log (D-TBD: in-place clips + speed in clips.json;
   loop flag must be ticked in Godot since names are fixed; cycle floors for tiny bodies).
Open questions for the lead: in-place vs root motion (chose in-place + speed); Godot loop mode not set by names.
