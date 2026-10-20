# Handoff: animation (anim-b4, motion fix round on draft PR #20), updated 2026-10-20
State: fixes 1-5 committed locally (3e223da, NOT pushed); -m blender run was in progress at handoff.
Branch claude/animation (worktree ../asset-forge-wt/animation, own .venv).
Evidence folder: C:/Users/DANTE/AppData/Roaming/Claude/side-session-notes/32c9f533-fe4e-47ae-b55b-70ec62248734/animation/
Scratch (S): %TEMP%/claude/C--Users-DANTE-Documents-GitHub-asset-forge--claude-worktrees-asset-forge-status-0d338f/32c9f533-.../scratchpad
  probe.py (gait table, six rigs), lean.py (fox hind lean), faint_probe.py, locked_pytest.py (gpu.lock),
  headsrc/ (HEAD src for failing-first runs: PYTHONPATH=$(cygpath -w S/headsrc/src)), bl_tests.log.

## Brief (lead, anim-b4)
Fix list: 1 animal cadence cap, 2 triposg fox hind leg drag, 3 human attack swipe, 4 human hit
torso/head recoil, 5 human faint ends lying flat, 6 check loop wrap in the real clip and note it.
DONE = pushed, unit + -m blender + ruff green, Godot OK on all six rigs, 36 previews re-rendered to
previews_v3/ in the evidence folder, PR #20 body updated. Do not mark ready, do not merge.
gpu.lock for every Blender run (shared with clean-b6, monster-b2). Do not touch jobqueue.py.

## What 3e223da does
1. clips.MAX_STRIDES_PER_S = {walk 2.0, run 3.0} (lead decision); plan() returns (n, stroke, capped):
   capped gait keeps the reach-limited stroke and lengthens the cycle; Clip.capped,
   clips.json "cadence_capped". Six rigs now: bird walk 2.0/s 0.18 m/s, run 3.0/s ~0.46 m/s;
   fox walk 1.88/s ~0.33-0.44 m/s, run 3.0/s ~0.7-0.87 m/s; humans unchanged (113 / 163 steps/min).
2. Hind drag cause: hind leg = 2 bones (stifle to paw in one), knee forward; foot far behind the hip
   plus hip drop leaned the lower bone 52 (walk) / 61 (run) deg near the ground (HEAD code, triposg
   fixture). Fix: HIND_SHIN_MAX_DEG 45 on frames where the paw is below half the swing lift;
   gait_clip loops shortening the hind back reach (0.88^k); Gait.early = hind paws lift early
   (peak 30% of swing); four-legged crouch 0 and no mid-stance compress. Fixture
   tests/fixtures/triposg_fox_skeleton.json. Also seen: triposg fox body is yawed ~18 deg off -Y
   (Step 3 forward fit) - report to lead as a finding, not fixed here.
3. Attack: upper-arm direction keyed as el/az angles (wind-up up-back, strike level forward-right,
   follow-through across left-low, recoil), keys 0/.26/.33/.40/.52/.90, lunge step kept.
4. Hit: Hips/Spine/Chest/UpperChest pitch back 24 deg total, neck+head lag then whip, settle.
5. Faint: ends prone: legs straight (ankles move to hip - UP*0.995 L), feet pointed (toes 80 deg
   below forward), arms by the sides, head on cheek; land frame 0.85 s. Blender ground_faint now
   reports end_lowest_mm and end_torso_gap_mm (trunk-weighted vertices vs floor).
Tests: test_animate.py 56 pass (new: cap pinned, small animals capped, hind lean on stick + triposg
fixture, swipe arc, hit recoil, faint flat); new tests shown failing on HEAD code (scratch ff/).
New blender test: faint lowest ~0 mm and torso gap <= 5% H. Unit suite 255 passed, ruff clean.

## Left
- Read S/bl_tests.log (blender tests); fix if red.
- Push; re-render 36 previews: python tools/animate/previews.py <models/skeleton_out> <evidence>/previews_v3 --export
  (uses gpu.lock; gives Godot checks on six rigs + gait lines). Look at fox walk/run hind legs,
  human attack/hit/faint frames (crops) before reporting.
- Item 6: loop wrap: read seams in each rig's check report (rotation, position_mm, stalls) from the
  real .glb (check_animated_glb), not the preview floor; note it in the PR body.
- Update PR #20 body (Evidence, Not exercised, Board and log), report to lead (<=8 lines).
