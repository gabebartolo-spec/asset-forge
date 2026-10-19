# Handoff: skeleton (board item 9, D-024), written 2026-10-20 at ~202k context
State: back end done and tested locally; PAGE + EVIDENCE + PR left. Branch claude/skeleton, worktree
asset-forge-wt/skeleton (uncommitted until the commit below; check git log). Own venv: .venv (uv sync --extra dev).
Inputs copied to main checkout models/skeleton_in/{hi3dgen,triposg}/{humanoid,fox,bird}/clean.glb (use only these).
Rig outputs: main checkout models/skeleton_out/<gen>/<name>/ (rigged.glb, test_pose.glb, rigged.blend,
skeleton.json, pose_<view>_<clay|colour>.png). Regenerate: scratchpad rig1.sh (gen name type) under tools/bakeoff/gpu_lock.py run.
Decisions (lead confirmed): humanoid = 23 bones, required Godot SkeletonProfileHumanoid only (no fingers/eyes/jaw);
bird = animal template variant (2 legs + wings, auto picked by count_leg_columns <= 2).
Built: src/asset_forge/skeleton/{__init__ (rig, check_rig_glb, RigFailed), templates, fit, weights, glb, pose}.py;
blender/rig.py (welded-copy auto weights, distance fallback, limit 4, test pose via world-axis rotations);
api POST /api/assets/{id}/skeleton (TODO PR #9 for clean hand-over); godot/import_check/check_skeleton.gd +
godot_check.check_rig; tools/skeleton/{contact_sheet,make_fixtures}.py; tests/fixtures/block{man,fox}.glb;
tests: test_skeleton.py (23), test_skeleton_api.py (4), test_skeleton_blender.py (6, marker blender). Unit suite 86 pass, ruff clean.
Evidence so far: all 6 models auto-weighted (max 7-12 influences before the limit, 4 after); Godot rig check OK on
hi3dgen humanoid (23 of 56 profile bones, required_missing=[]) and fox test_pose.
Left, in order:
1. Godot check all 12 glbs (rigged + test_pose, 6 models) with godot_rig.sh (scratchpad) -> save output text.
2. Mutation proof: set MAX_INFLUENCES=8 in templates.py (or drop limit_influences) -> tests fail; paste failing names; revert.
3. Page Step 3: web/viewer.js markers (spheres+lines from SkinnedMesh bones, depthTest off) + toggle rigged.glb/test_pose.glb
   (AnimationMixer clip at t=0); web/index.html panel-3; app.js step 3, pill enabled when asset has clean.glb; ?asset=<id> loads
   an existing library asset (dev hand-over until #9). Plain words (D-014). Real-click screenshots with playwright
   (browser not yet installed? check `playwright install chromium` is allowed) of markers and test pose.
4. Copy 3 sheets per model (contact_sheet.py --shade clay and colour) + screenshots + godot log to
   C:/Users/DANTE/AppData/Roaming/Claude/side-session-notes/local_f6b2f763-b2e4-47af-990a-44f6a54cc5ed/skeleton/ .
   Known look issues to look at: triposg bird right wing spiky/looped in test pose (maybe lower wing angles in pose.py).
5. Draft PR (template in .github/PULL_REQUEST_TEMPLATE.md; Board and log: "D-024 to log"; Not exercised: monsters,
   Step2->3 hand-over, fingers/eyes/jaw, retarget quality of an A-pose rest). Ready after evidence; report to main (8 lines max).
Notes: bash tool breaks on heredocs containing apostrophes: use the Write tool for files. Scratch branches: none pushed.
