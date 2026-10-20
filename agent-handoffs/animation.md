# Handoff: animation (round 4: "Fix first" on #22's joints), updated 2026-10-20
State: round 4 done and pushed: origin/claude/animation = 43450d7 (PR #20 ready, body has
rounds 3 and 4). CI watcher was running at hand-off; if not green at head, read the failing
shard (jobs/annotations API) and fix. Do not merge (the lead merges). Context hit 300k:
stood down; a fresh session continues only if CI is red or the lead's critic returns fixes.
Lead (director 2026-10-20): GPU lock only for GPU jobs; re-rig, -m blender and Workbench
previews run without it (previews use --lock out/own.lock).
Worktree: C:/Users/DANTE/Documents/GitHub/asset-forge/.claude/worktrees/magical-booth-c546dd
(no .venv: run C:/Users/DANTE/Documents/GitHub/asset-forge-wt/animation/.venv/Scripts/python.exe
with PYTHONPATH=src; never edit that old worktree). config.local.toml copied in (gitignored).
gpu.lock: C:/Users/DANTE/Documents/GitHub/asset-forge/models/gpu.lock (shared; remove only a
lock whose owner pid is dead).
Inputs: models/skeleton_in/<gen>/<body>/clean.glb re-rigged on merged main (#22) into
out/rigs_v4 (gitignored). GIFs: out/previews_v4/, log out/previews_v4.txt, job log out/run_v4.log.
Scratch: %TEMP%/afsp (run_v4.py = re-rig + pytest -m blender under the lock, then previews;
oldsrc/ = pre-round-4 src for failing-first runs; failing_first.txt).

## Brief (lead, 2026-10-20)
STATUS item 10, PR #20. Director "Fix first" (D-028) on person walk, fox walk, bird walk,
attack/faint. Merge origin/main (#22 foot ball joint, hock, fox yaw 0), re-rig on #22's joints,
unit + ruff + -m blender green, previews_v4 GIFs at game speed in the worktree, PR #20 body,
push once. No critics (the lead starts a fresh motion critic). Report 6 lines max.

## Done (round 4)
- Merged origin/main (clean). 3 unit tests broke on #22's joints; root causes, all fixed:
  - Heel lift pivoted on the toe tip (now 22 cm ahead of the ankle): person heel now turns
    about the ball joint (Leg.ball = Toes head) with the toes kept flat (Animator.toe_bend),
    walk and attack back foot. Bob back to 0.034 L.
  - Faint lay 22 cm above the floor (toppling about the toe tips) and the feet never pointed
    (sign bug in the old slope, hidden: max(0, 80 - 138)). Now it sinks to 0.06 H with the
    fall (sin^4 of the fall angle), feet point so the tip reaches the floor, toes bend back
    at the ball if they would dip (_toes_off_floor), head lags back (not into the floor),
    arms at the sides by landing. Nothing below the floor on any frame (Root bone excepted).
  - Fox hind ankle "slid" 4.8 mm: the ankle above a flat paw swings forward as the pad peels;
    the slide check (unit and .glb) now follows the paw/toe tip ("<leg>Foot.tail"; clips.json
    "foot_tips" in glTF axes; files without it fall back to the ankle node).
  - That exposed a real defect: curled toes/paws dipped through the floor mid-swing (bird
    toes ~1 cm). Animator.swing_turn cuts the curl back to keep the tip clear (now >= 3/4 of the lift, 0d077f6).
- Previews framed on all clips together (union box centre, smallest scale), constant per rig.
- 4 new tests, failing first on the old src (scratch failing_first.txt): paw tip check,
  tips never dip in the swing [bird fails old], heel about the ball, faint on the floor.
- Unit: animate + api + export_animated 103 passed; full suite 288 passed, 3 failed
  (test_app_queue gpu-lock wait and 2 test_library: timing flakes, they also fail on the old
  src under load, untouched files). ruff clean.
- Real rigs (skeleton_out_fit joints, pure numpy): slide <= 1.6% of leg (limit 2%) on all six.
- Fresh worktree had LFS pointers for test fixtures: ran git lfs pull (first -m blender run
  failed on that, not on code).
- -m blender then: blockfox hind paw tip "slid" 0.3 cm at touchdown (tip came in 1% L up,
  still moving). Fix 0d077f6: swing curl sin^1.5 (flat on landing) and swing_turn keeps the
  tip >= 3/4 of the lift. Real rigs fox walk now 0.1% (was 1.5%). Unit 103 passed, ruff clean.
- Re-rig of six on merged fit: out/rigs_v4, all RIG OK, 4 influences. First previews run
  (before 0d077f6): all six OK, export OK, RIG_CHECK_OK, LOOP_CHECK_OK; re-rendering now.

- Final: -m blender (animate + skeleton) 13 passed; previews_v4 re-rendered after 0d077f6:
  six OK, export OK, RIG/LOOP_CHECK_OK; slide cm person walk 0.05-0.13, fox walk 0.02.
  Own look at strips (out/check_v4.png): faint flat on floor, size constant; figure sits ~1/3
  frame height (union framing includes the lying faint), the critic may flag it.

## Next steps
1. CI green at 43450d7 (gh pr checks 20).
2. Lead runs a fresh motion critic on out/previews_v4/ (36 GIFs); apply its FIX list.
3. Finding for the lead's learnings (workers don't write them): tracking the paw/toe tip
   instead of the ankle caught toes clipping through the floor mid-swing (test failed first).
