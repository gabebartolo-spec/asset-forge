# Asset Forge lead handoff (2026-10-20, session 6)
## State: working (4 agents running; board PR #16 merges on green)

## Director said this session (2026-10-20)
- "status check ... eta til usable build?" -> answered: ~1 working day if #9 round 4 passes, 2-3 if not.
- "get to work / work on multiple phases at once, get more efficient" -> D-025: Phase 4 Animation
  and Phase 6 Library start now beside the Phase 2 and 5 finishes.

## Live (verify with gh pr list / ListAgents; in-process agents die with this session)
- main 1562679 (#15 Skeleton merged this session; skeleton worktree removed).
- PR #16 board (this branch claude/asset-forge-status-0d338f): D-024, D-025, STATUS rewrite.
- PR #9 clean (draft, green): round 4 = measured colour region gates. clean-critic-r4
  (realism-critic) checks docs/audits/clean/*.jpg in asset-forge-wt/clean-step. PASS -> lead
  marks ready, merges on green, then brief item 12. FIX -> fresh builder life from
  asset-forge-wt/clean-step/agent-handoffs/clean-step.md with the filtered FIX list.
- PR #11 sprites (draft): sprites-b4 (builder, sonnet) finishing spurs, real runs, PR body.
  Handoff asset-forge-wt/sprites/agent-handoffs/sprites.md. Yield 1/18 sheets: report, no tuning.
- anim-b1 (builder, opus): Phase 4 first slice in asset-forge-wt/animation, claude/animation,
  draft PR when ready. Clips -> fresh motion-critic before the director.
- library-b1 (builder, sonnet): Phase 6 in asset-forge-wt/library, claude/library, NO PR until a
  slot frees (cap 3 open). Screens -> fresh screen-critic.

## Next steps
1. On each report: check evidence, spawn the right fresh critic, filter findings.
2. #9 merges -> item 12 builder: Step 2 page + Step 2 -> Step 3 hand-over (TODO(PR #9) in #15).
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
