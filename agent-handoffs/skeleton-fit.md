# Handoff: skel-fit (Step 3 fit fixes found by the PR #20 animation review), 2026-10-20

State: done incl. the hock fix; branch claude/skeleton-fit pushed; no PR (lead opens it, body below).
Worktree asset-forge-wt/skeleton-fit, venv borrowed from asset-forge-wt/monster-rig (run with PYTHONPATH=src,
its editable install points at monster-rig/src). Inputs: main checkout models/skeleton_in/<gen>/<kind>/clean.glb.
Outputs: models/skeleton_out_fit/<gen>/<kind>/ (rig, sheets, skeleton.json with foot_pivots),
models/skeleton_out_fit/_feet/{before,after}/<gen>/<kind>/foot_<chain>.png and _feet/board_<gen>_<kind>.png.
models/skeleton_out was not touched (the animation builder reads it).

## PR body draft

Title: rig: real foot joints and a body axis that ignores a turned head (Step 3 fit)

### What
- Humanoid foot: the ball of the foot (Toes) sat straight under the ankle, so a step pivoted on the toe tip
  with a rigid forefoot. Now heel, ankle, ball and toe tip come from the foot's own sole: heel = back end,
  toe tip = front end, ankle 25% and ball 72% of the foot length from the heel; each joint takes the foot's
  sideways position at its own length (turned-out feet keep their line); the ball height follows the mesh.
- Animal body axis: the frame came from the whole mesh's spread, which a turned head or curled tail tilts
  (triposg fox: 18.4 deg off -Y; its legs were even mislabelled, front-left was a hind leg). Now the axis is
  the torso's mirror line (middle 60% of the length, top-view symmetry search), and since Clean turns every
  model to face -Y, an axis within 15 deg of Y snaps to -Y exactly. A truly turned model still gets
  followed (stick fox turned 23-29 deg: within 1 deg; turned-head fox turned 29 deg: within 5 deg).
- Four-legged paw: the Foot joint sat at the middle of the low vertices and the tip a fixed 3% of body
  length ahead (hind tip right under the hock). Now the paw bone runs from above the back quarter of the
  ground pad to the pad's front end.
- Bird foot: the ankle sat over the mean of leg-plus-toes (pulled forward onto the toes) and its height was
  fixed, so the raised right foot of the triposg bird had all joints below the mesh. Now the ankle is over
  the shin column (median), the toes are the leg vertices reaching away from it, and the joints sit at the
  toes' own height.
- Hind leg middle joint (lead, 2026-10-20: "Fix the hind LowerLeg/hock finding too"): it sat ahead of the
  leg, in the air, where the leg really bends back at the hock. Now the fit follows the hind leg's own
  column up from the ankle (slice by slice, only vertices next to the last centre) and puts the joint at
  the slice furthest back: the hock, inside the leg. A straight leg keeps the old proportional joint.
- New fit.foot_pivots(v, template): a ground point behind each foot (<foot>Heel), written to skeleton.json
  as "foot_pivots" (not bones; the template and bone count are unchanged).

### Evidence
- 8 new unit tests (tests/test_skeleton.py), each shown failing on the old code first (7 fail on
  origin/main's fit.py; the hock test also fails on 4ca50ca), 30/30 pass now (humanoid foot, turned-head
  axis at 0 and 29 deg, paw, bird ankle over the shin, bird lifted foot, hind joint in the hock).
- Six real models (hi3dgen + triposg x humanoid, fox, bird), joints printed before/after
  (scratch joints_old.txt / joints_new.txt, summary below); body yaw (Chest - Hips vs -Y):
  hi3dgen fox -0.4 -> 0.0, hi3dgen bird +0.1 -> 0.0, triposg fox +18.4 -> 0.0, triposg bird -3.9 -> 0.0.
- Side view of every foot, before | after, x-ray mesh, joints as balls (white knee, red ankle, yellow ball,
  green toe tip, blue heel): models/skeleton_out_fit/_feet/board_<gen>_<kind>.png (16 feet).
- Rig re-run on all six into models/skeleton_out_fit: RIG_OK, 4 influences max, 0 unweighted vertices.
- ruff clean; unit suite 188 passed (an earlier run under Blender load had timing flakes in untouched files; clean on rerun);
  pytest -m blender tests/test_skeleton_blender.py: 6 passed (fixture rigs, Godot import included).
- Hock: hind LowerLeg on both foxes moved from ahead of the leg (in the air) to inside the leg at the
  back bend; boards models/skeleton_out_fit/_feet/board_<gen>_fox.png, hind rows first.

### Not exercised
- Animation on the new joints (PR #20 consumes them); Godot import of the new rigs beyond the blender tests.
- Front-leg middle joint left as it was (the brief named the hind bend only).
- hi3dgen fox front-left leg ends in the air (a generation defect, not the fit).
- Humanoid feet only in T/A-pose standing; a lifted humanoid foot keeps the fixed ankle height.

### Board and log
- Board: item 9 follow-up (Step 3 fit fixes) done; no DECISIONS entry (builder's call within design 8).

### MERGE NOTE
PR #20 consumes these joints: after this merges, re-rig its inputs (Toes/Foot/FootTip moved, fox frame now
-Y) and re-run its clips; skeleton.json gains "foot_pivots" (<foot>Heel ground points) for heel-toe roll.
