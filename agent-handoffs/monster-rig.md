# Handoff: monster-rig (Phase 3 monsters + Step 1 limb gate, STATUS item 13, D-026), 2026-10-20
State: screen-critic round 1 on PR #27 (10 defects, side-session-notes/local_68d3bafb-.../
critic_monster_screen.md) fixed and pushed (9a83146, 8513381 local until the evidence push). Context guard
at 300k: the lead restarts this role after the evidence step below.
Worktree C:/Users/DANTE/Documents/GitHub/asset-forge-wt/monster-rig (own .venv with scipy + playwright,
config.local.toml). Lead rulings: gate option A (Re-roll primary, "Use it anyway" quiet second); scipy OK
(LICENCES row added). Round 2 replaced the "extra legs stay in the model" wording with the critic's
"The skeleton step can only move bones, not change the model's shape" (lead said fix all 10).

## Next session: finish the evidence, then report
1. Evidence reruns (real clicks, headless Playwright, true 1366x768 and 1920x1080) write to
   ../mr_evidence/round2/<W>_<n>_*.png + <W>_log.txt (each shot logs the note and hint text).
   Scripts (copy them into ../mr_tools/ if the scratchpad is gone; the old session's scratchpad is
   C:/Users/DANTE/AppData/Local/Temp/claude/C--Users-DANTE-...-strange-euler-d75020/9210a97b-.../scratchpad):
   shots_server.py REPO LIB (real app on :7871, library ../mr_shots2, Step 1 generator stubbed to return the
   real Hi3DGen spider mesh after 3 s; everything else real, incl. headless Blender rig through the GPU lock),
   shots.py OUT W H S1 S3 (S1 = picture-only spider asset, S3 = asset with clean.glb). Assets used:
   1366: a-20261020-170005-51cc / 170007-53cc; 1920: 170006-51dd / 170008-53dd. Fresh copies are made
   from a-20261020-153625-afab (S1) and 153628-7108 (S3, triposg spider) with a new hex id.
   Builds wait on models/gpu.lock (other sessions held it 10+ min); timeouts are 30 min.
2. Check every shot (2x crop): 1 Step 1 warning; 2/2b all 8 rows (panel scrolls as a whole); 3 row lit
   while dragging; 4 hovered row's dots orange; 5/5b bones removed + new leg beside the body; 6 build ->
   warning naming the new leg's foot + red dots; 7 pose; 8 Change the limbs shows red dots; 9 Start the
   limbs again asks; 10 back to found limbs; 11 clean build: tips drawn, white lines, no floor dot; 12 pose.
3. ../mr_evidence/round2/rig_all.txt: four real monsters re-rigged (chains regenerated with the snapped
   body line, all markers inside). Sheets ../mr_out/<gen>/<name>/pose_*.png -> copy to round2 as
   <gen>_<name>_pose_clay/colour.png; check RIG_OK in ../mr_out/*.log.
4. Push (git push origin claude/monster-rig), report to the lead (6 lines: sha, folder, tests, defects).

## Round 2 fixes (critic 1-10) and what else changed
outside_joints() in limbs.py (voxel gap > 2% of longest side) + skeleton result["outside"] -> plain warning
("Leg 8's foot is outside the body...") + red dots, built view and editor; body line snapped onto the core
(the triposg brute's started 7 cm outside: the new check caught it); limb list unscrolled; Step 1 wording;
"Add its bones" / "Remove bones" + note that the shape stays; new limb beside the body pointing out, hint
says drag first dot to where it meets the body and last to its foot; tip dots after Build (rig limbs carry
"tip"); white bone lines; drag lights the row, hover lights the dots; pose ~30 deg per joint, "Bends each
limb once"; Skeleton "soon" badge gone; draw-note hidden once a model exists; Step 3 Redo = "Start the
limbs again" (asks first; GET limbs?fresh=1); no dot for the floor-level Root bone (the critic's floating
dot at 513,516); limbWarningButtons used className and wiped "hidden" (Redo showed on Step 3).
Tests: touched suites 69 passed + ruff clean (../mr_evidence/unit_touched.txt); new tests: every proposed
marker inside (4 real models), dragged-off marker found, result["outside"] via the API, fresh proposal,
pose >= 30 deg per joint, Step 1 wording.

## PR body additions for #27 (lead pastes)
Evidence round 2: ../mr_evidence/round2 (real clicks at 1366 and 1920; Step 1 generator stubbed with the real
Hi3DGen spider mesh). Not exercised: the six-armed rig from a generated mesh (both generators gave 2 arms);
drag precision on a touch screen.

## Cleanup left
After merge: delete ../mr_out, ../mr_evidence, ../mr_shots_lib, ../mr_shots2; remove this worktree.
