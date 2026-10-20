# Asset Forge lead handoff (2026-10-20, session 6)
## State: working (4 builders; board PR claude/board-2 merges on green)

## Director said this session (2026-10-20)
- "eta til usable build?" -> ~1.5-2 working days (Clean round 4 failed 1/10).
- "work on multiple phases at once" (D-025); "if theres anything you can work on in parrelal
  then do it" (D-026).

## Live (verify with gh pr list / ListAgents; in-process agents die with this session)
- main: #15, #16, #11, #17, #19 merged this session.
- D-027 TO LOG (director 2026-10-20): Clean colour "Keep improving first" (asked: ship 6/10
  multi-view, keep improving, or shape only; board clean_choice.png in lead scratchpad).
- PR #9 clean (head effb435: plain-words gate messages). Best method = B (MV-Adapter, fp8, 9.3 GB,
  ~60 s/model batched) + per-view Lab grid colour match: 6/10, local branch
  claude/clean-step-methodB-local a57382f (NOT pushed). Fails: hi3dgen humanoid greaves_back
  0.122/0.12; hi3dgen fox chest + front lower legs; hi3dgen bird beak (picture-to-mesh
  registration); triposg fox chest + 2-part mesh. Clean session started from this (see sessions).
- PR #20 animation: READY (350dcf2), motion critic r2 13/14; needs DIRECTOR LOOK at clips
  (previews_v3 in side-session-notes/32c9f533.../animation/) before merge. Known: triposg fox
  walk hind legs fold (Step 3 forward fit ~18 deg yaw); rigid forefoot (foot-joint card).
- claude/step2-page 1d474f3: done, PR after #9; fix "It broke 2 limits" count first. The jobqueue
  race fix lives on claude/monster-rig (GpuQueue._settle) and PR #20 also touched jobqueue.py:
  merge carefully.
- monster-b2 (subagent, opus): claude/monster-rig, page editor + Step 1 warning + sheets; no PR.
- Proposed card: Step 3 foot joint fix (task_043885cd). Also log: Step 3 fox yaw ~18 deg.

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
