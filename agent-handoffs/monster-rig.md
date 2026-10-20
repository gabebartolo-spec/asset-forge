# Handoff: monster-rig (Phase 3 monsters + Step 1 limb gate), 2026-10-20
State: back end built and committed on claude/monster-rig (not pushed yet). Context hit 200k; restart here.
Worktree C:/Users/DANTE/Documents/GitHub/asset-forge-wt/monster-rig, own venv .venv (uv, py3.12, +scipy),
config.local.toml copied from ../animation. Lead rulings: gate option A (Re-roll main button, "Use it anyway"
quiet second; warning says extra legs STAY in the model); scipy OK with a LICENCES.md row (row NOT added yet).

## Done (files)
- src/asset_forge/skeleton/limbs.py: voxelise (RES 160) -> body middle (_centre: deepest voxel on the
  geodesic bisector of the two farthest points) -> core (union of balls, CORE_DEPTH .5, GROW 1.1, MARGIN .3)
  -> pieces -> band tree (_branches) -> 4-joint chains; _classify leg/arm/head/tail; propose(), count_limbs().
  Results (clean + raw): hi3dgen spider 10 legs, triposg spider 8, both brutes 2 legs 2 arms. Humanoids/
  foxes are NOT reliable (arms glued, tails) -> gate sets no type-implied counts, words only.
- src/asset_forge/skeleton/glb.py: read_mesh() (vectorised, node transforms, to Blender Z-up frame).
- src/asset_forge/anatomy.py: expected_counts(words) (numbers + "spider"=8, insects=6, snake=0), judge(),
  check_mesh(). Message ends "...extra ones stay in the model ... Press Re-roll for a new try."
- src/asset_forge/skeleton/monster.py: monster_bones(chain) -> BoneDef/joints/limb info (Root, Spine1-3,
  <Kind><L|R|><n>_1..3); ChainError plain words; MAX_LIMBS 20; monster_pose().
- blender/rig.py: --chain FILE for monsters (bones from chain, monster_pose); skeleton.json gets "limbs".
- skeleton/__init__.py rig(..., chain=) ; api.py: limb_check() after generate (result["anatomy"]),
  GET /api/assets/{id}/skeleton/limbs (proposal kept in skeleton/proposal.json, chain.json once confirmed),
  confirmed_chain(), POST skeleton takes {spine, limbs} for monsters.
- tests/test_monster.py (25 pass), tests/test_monster_api.py (new, not yet run green), fixtures
  tests/fixtures/monsters/*.npz (tools/skeleton/monster_fixtures.py), glb_factory.write_mesh_glb.

## Open problem (first thing next session)
tests/test_library.py: 3-4 tests fail with my api.py (KeyError 'timings', 409 on duplicate/trash), pass
alone and pass on pristine origin/main. Not the progress() line. Suspect: something in my generate_now /
api import changes the job-done vs persist ordering (jobqueue flips DONE before save; library waits on
`settled`). Find the cause; do not just loosen the tests.

## Left
1. Fix the library-test failure; run test_monster_api.py; full unit suite; ruff.
2. Show tests failing first: mutation (e.g. GROUND=0 / judge always ok) + log output to evidence.
3. Blender DONE once by hand: all 4 monsters RIG_OK (hi3dgen spider 34 bones, triposg spider 28, brutes 16;
   blender_automatic weights, max 4 influences, 0 unweighted; sheets in ../mr_out/<gen>/<name>/pose_*.png). Was:
   ../mr_out/*_chain.json into ../mr_out/<gen>/<name>; check logs ../mr_out/*.log for RIG_OK.
   Add -m blender tests (monster chain rig on a fixture) + Godot check_rig on rigged/test_pose.glb.
4. Page: web/viewer.js draggable markers (child of gltf root, glTF coords = (x, z, -y)), web/app.js Step 3
   limb editor in its own functions (list limbs + kind, Remove, "Add a limb: click where its tip is",
   Build skeleton sends {spine, limbs}); Step 1 warning (Redo->"Re-roll" primary, Next->"Use it anyway").
5. LICENCES.md scipy row; pyproject dependency scipy>=1.13.
6. Evidence: five-view test-pose sheets (tools/skeleton/contact_sheet.py) for hi3dgen/triposg spider and
   brute; real-click screenshots 1366x768 + 1920x1080 of the marker editor; to the lead only.
7. Push branch, PR body here (no PR; lead opens). Delete scratch dirs ../mr_out, ../scratch_*.py.
