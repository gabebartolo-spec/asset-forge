# Handoff: monster-rig (Phase 3 monsters + Step 1 limb gate, STATUS item 13, D-026), 2026-10-20
State: screen-critic round 1 on PR #27 (10 defects, side-session-notes/local_68d3bafb-.../
critic_monster_screen.md) fixed, evidence re-shot, pushed. Stood down at the 300k guard; the lead restarts
this role for critic round 2.
Worktree C:/Users/DANTE/Documents/GitHub/asset-forge-wt/monster-rig (own .venv with scipy + playwright,
config.local.toml). Lead rulings: gate option A (Re-roll primary, "Use it anyway" quiet second); scipy OK
(LICENCES row added). Round 2 replaced the "extra legs stay in the model" wording with the critic's
"The skeleton step can only move bones, not change the model's shape" (lead said fix all 10).

## Next session
Round 2 is done and pushed (round2 evidence complete). Wait for the lead's fresh screen critic on PR #27;
fix what it sends. Re-shoot with ../mr_tools (shots_server.py REPO LIB on :7871 with a private lock dir,
no GPU lock for CPU work; shots.py OUT W H S1 S3, Chromium on hardware WebGL via d3d11; fresh asset
copies with a new hex id from mr_shots2 a-20261020-153625-afab (S1) and 153628-7108 (S3)).
Evidence: ../mr_evidence/round2/<W>_<n>_*.png + <W>_log.txt (note/hint text per shot), sheets/ (4 real
monsters re-rigged, all RIG_OK), rig_all.txt, webgl_renderer.txt. Open item for the critic: the brute's
quick pose is still subtle (arms hang down, so "lift" is small); spiders bend clearly.

## Round 2 fixes (critic 1-10) and what else changed
outside_joints() in limbs.py (voxel gap > 2% of longest side) + skeleton result["outside"] -> plain warning
("Leg 8's foot is outside the body...") + red dots, built view and editor; body line snapped onto the core
(the triposg brute's started 7 cm outside: the new check caught it); limb list unscrolled; Step 1 wording;
"Add its bones" / "Remove bones" + note that the shape stays; new limb beside the body pointing out, hint
says drag first dot to where it meets the body and last to its foot; tip dots after Build (rig limbs carry
"tip"); white bone lines; drag lights the row, hover lights the dots; pose ~30 deg per joint, "Bends each
limb once"; Skeleton "soon" badge gone; draw-note hidden once a model exists; Step 3 Redo = "Start the
limbs again" (asks first; GET limbs?fresh=1); no dot for the floor-level Root bone (the critic's floating
dot at 513,516); confirmed limbs keep the model height (marker size); limbWarningButtons used className and wiped "hidden" (Redo showed on Step 3).
Tests: touched suites 69 passed + ruff clean (../mr_evidence/unit_touched.txt); new tests: every proposed
marker inside (4 real models), dragged-off marker found, result["outside"] via the API, fresh proposal,
pose >= 30 deg per joint, Step 1 wording.

## PR body additions for #27 (lead pastes)
Evidence round 2: ../mr_evidence/round2 (real clicks at 1366 and 1920; Step 1 generator stubbed with the real
Hi3DGen spider mesh). Not exercised: the six-armed rig from a generated mesh (both generators gave 2 arms);
drag precision on a touch screen.

## Cleanup left
After merge: delete ../mr_out, ../mr_evidence, ../mr_shots_lib, ../mr_shots2; remove this worktree.
