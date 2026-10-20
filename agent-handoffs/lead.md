# Asset Forge lead handoff (2026-10-20, session 6)
## State: working (4 builders; board PR claude/board-2 merges on green)

## Director said this session (2026-10-20)
- "eta til usable build?" -> ~1.5-2 working days (Clean round 4 failed 1/10).
- "work on multiple phases at once" (D-025); "if theres anything you can work on in parrelal
  then do it" (D-026).

## Live (verify with gh pr list / ListAgents; in-process agents die with this session)
- main: #15, #16, #11, #17, #19 merged this session. Open PRs: #9 only (ours).
- PR #9 clean: clean-b6 (opus) running method B = MV-Adapter ig2mv SDXL (Apache-2.0; weights in
  models/hf/hub). C (part-wise) = 3/10. Stop rule: neither >= 8/10 -> report, director decision.
  Also asked: gate messages in plain words. Lighting removal out of scope (lead).
- anim-b3 (opus): claude/animation; cadence fix (100-120 steps/min, real gait data), API,
  Step 4 page, GIFs, draft PR. Clips -> fresh motion-critic.
- claude/step2-page 1d474f3: done + critic round fixed, NO PR until #9 merges. Open it then and
  fix two things first: "It broke 2 limits" lists 1 bullet (count the row too or reword); flaky
  KeyError 'timings' in test_clean_api/test_library (race: settle, not rerun).
- monster-rig (opus): claude/monster-rig, no PR (cap); Step 1 limb gate = option A (Re-roll main,
  "Use it anyway" quiet; extra legs stay in the mesh). scipy allowed (licence row).
- Waiting: sprite backs by multi-view (if B wins), sprite mode B (needs a worktree slot).
- Not ours: asset-forge-wt/context-trim (another session). Lead worktree: .claude/worktrees/lead-s6.

## Next steps
1. On each report: check evidence, spawn the right fresh critic, filter findings.
2. #9 merges -> open step2-page PR at once (usable build), then monster-rig PR when a slot frees.
3. Board PR after each merge: D-023 from #11; item states.
4. First usable build = item 12 merged (text/image -> clean -> rig -> export). Then show the
   director one end-to-end model (five views + Godot check) as a decision.

## Restart kit
Briefs are in this session's transcript; respawn from each lane's handoff file above with the
team-kit template (~/.claude/skills/game-studio-lead/references/team-kit.md). GPU: models/gpu.lock.
Worktrees in asset-forge-wt (ours): clean-step, animation, step2-page, monster-rig (4 = cap).

## Gotchas
- Generators disagree on which camera the reference faces; check facing per prompt.
- Critics share the scratchpad: give each its own subfolder.
- No HF token on this PC; gated weights are out. Playbook: nothing new.
