# Handoff: monster-rig (Phase 3 monsters + Step 1 limb gate, STATUS item 13, D-026), 2026-10-20
State: done. Branch claude/monster-rig pushed (origin/main #22/#23 merged in). No PR (3-PR cap): the
lead opens it with the body below. Worktree C:/Users/DANTE/Documents/GitHub/asset-forge-wt/monster-rig
(own .venv with scipy, config.local.toml). Evidence in ../mr_evidence; rig outputs in ../mr_out.
Lead rulings: gate option A (Re-roll primary, "Use it anyway" quiet second; the warning says extra
legs STAY in the model); scipy OK with a LICENCES.md row (added).

## If the lead asks for changes
- Limb finder: src/asset_forge/skeleton/limbs.py (voxelise -> body middle -> core -> band tree ->
  4-joint chains; tunables at the top). Counts: hi3dgen spider 10 legs, triposg spider 8, both
  brutes 2 legs 2 arms. Humanoids/foxes are not reliable, so the gate uses only counts the words ask for.
- Bones: skeleton/monster.py; Blender: blender/rig.py --chain; API: api.py limb_check(),
  GET /api/assets/{id}/skeleton/limbs, POST skeleton {spine, limbs}; page: web/viewer.js markers,
  web/app.js Step 3 limb editor + Step 1 warning.
- Merge note: rig.py skeleton.json keeps main's foot_pivots for template rigs; monsters write {}.

## PR body (for the lead)
Title: rig: monster skeleton from the mesh, limb editor, Step 1 limb check

### What the director gets
Monsters get a skeleton proposed from their shape: Step 3 shows each limb as a row of dots he can
drag, remove, or add ("Add a limb"), then Build skeleton rigs it. Step 1 counts legs/arms when his
words name a number (or "spider", insects): a 10-legged spider gets a plain-words warning with
Re-roll as the main button and "Use it anyway" beside it.

### Changes
- skeleton/limbs.py (limb finder, count_limbs), skeleton/glb.py (read a .glb mesh), anatomy.py
  (counts from words, judge, plain message), skeleton/monster.py (bones from limb chains, test pose).
- blender/rig.py --chain; api.py limb check after Generate, limbs proposal/confirm endpoints.
- jobqueue.py: a job shows done only after its end state is on disk (fixed a race the library tests hit).
- web/: draggable markers, Step 3 limb editor, Step 1 warning. scipy dependency + LICENCES.md row.
- Tests: test_monster.py, test_monster_api.py, monster -m blender tests; 4 real-model fixtures
  (tests/fixtures/monsters/*.npz, made by tools/skeleton/monster_fixtures.py).

### Evidence (folder C:/Users/DANTE/Documents/GitHub/asset-forge-wt/mr_evidence)
- Unit: 219 passed (ruff clean). Blender: 11 passed (blender_suite.txt).
- Fail first (fail_first.txt): judge always ok -> 4 fail; GROUND=0 -> 8 fail; MIN_LIMB=0 -> 4 fail.
- Real rigs: hi3dgen spider 34 bones, triposg spider 28, both brutes 16; automatic weights, max 4
  influences, 0 unweighted. Five-view test-pose sheets *_pose_clay/colour.png.
- Godot 4.7.2 headless: rigged.glb and test_pose.glb of all four RIG_CHECK_OK, python gate pass
  (godot_rig_check.txt).
- Job race: done-but-not-settled 0 of 20 after the fix (race_after_fix.txt).
- Page, real clicks at 1366x768 and 1920x1080: 1 Step 1 warning, 2 limbs proposed, 3 marker dragged,
  4 limb removed and added, 5 skeleton built, 6 quick pose.

### Not exercised
Auto-skeleton on humanoid/animal-shaped monsters (counts unreliable there; words-only gate);
six-armed brutes came out of both generators with 2 arms, so a real 6-arm rig was not built from a
generated mesh. No critic or director review yet.

### Board and log
STATUS item 13 -> DONE (PR #?). No new decision.

## Cleanup left
Delete ../mr_out and ../mr_evidence after the lead has reviewed; remove this worktree after merge.
