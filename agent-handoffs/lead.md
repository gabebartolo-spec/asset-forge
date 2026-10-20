# Asset Forge lead handoff (2026-10-20, session 6)
## State: working (4 builders; board PR claude/board-2 merges on green)

## Director said this session (2026-10-20)
- "eta til usable build?" -> ~1.5-2 working days (Clean round 4 failed 1/10).
- "work on multiple phases at once" (D-025); "if theres anything you can work on in parrelal
  then do it" (D-026).

## Live (verify with gh pr list / ListAgents; in-process agents die with this session)
- main: #15 Skeleton, #16 board, #11 Sprites back end, #17 Library merged this session.
- PR #9 clean: clean-b5 (opus) testing multi-view vs part-wise colour on 10 models, new fix-list
  gates (9a2ec52). Then fresh realism-critic (own scratch subfolder) -> merge or one more life.
- anim-b2 (opus): asset-forge-wt/animation, claude/animation; lead calls in D-026. Clips ->
  fresh motion-critic.
- step2-page (sonnet): asset-forge-wt/step2-page, no PR until #9 merges; body in its handoff.
- monster-rig (opus): asset-forge-wt/monster-rig, no PR (cap 3); sheets -> realism-critic.
- Waiting: sprite backs by multi-view (after item 5 proves the model).

## Next steps
1. On each report: check evidence, spawn the right fresh critic, filter findings.
2. #9 merges -> open step2-page PR at once (usable build), then monster-rig PR when a slot frees.
3. Board PR after each merge: D-023 from #11; item states.
4. First usable build = item 12 merged (text/image -> clean -> rig -> export). Then show the
   director one end-to-end model (five views + Godot check) as a decision.

## Restart kit
Briefs are in this session's transcript; respawn from each lane's handoff file above with the
team-kit template (~/.claude/skills/game-studio-lead/references/team-kit.md). GPU: models/gpu.lock.
Worktrees in asset-forge-wt: clean-step, sprites, animation, library (4 = cap).

## Gotchas
- Generators disagree on which camera the reference faces; check facing per prompt.
- Critics share the scratchpad: give each its own subfolder.
- No HF token on this PC; gated weights are out. Playbook: nothing new.
