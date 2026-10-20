# Asset Forge lead handoff (2026-10-20, session 7)
## State: working (clean-b8 and anim-b4 builders running)

## Director said (2026-10-20)
- "eta til usable build?" -> ~1.5-2 working days.
- "work on multiple phases at once" (D-025); "if theres anything you can work on in parrelal
  then do it" (D-026); Clean colour "Keep improving first" (D-027, merged #21).
- PR #20 clips A-E (review_pr20/ in the s7 worktree, untracked): "Fix first"; marked ALL of person
  walk, fox walk, bird walk, attack/faint wrong, no notes. TO LOG as D-028 in the next board PR.

## Live (verify with gh pr list / ListAgents; in-process agents die with this session)
- main: #15, #16, #11, #17, #19, #21 merged. Next board PR: claude/board-4 (local).
- PR #9 clean (draft, head effb435). Method B best: 6/10 on local claude/clean-step-methodB-local
  a57382f. clean-b8 (opus subagent, this session) targets causes: bird beak registration, triposg
  fox 2 parts, hi3dgen fox chest/front legs, humanoid greaves_back 0.122/0.12. Bar 8/10 -> pushes
  into claude/clean-step, PR #9 body. Then lead: fresh realism-critic on the sheets, merge #9.
- claude/step2-page a131c49 pushed (count fix + 0fb46ea _settle cherry-pick; 192 unit pass). NO PR
  until #9 merges. Not re-checked vs #20's jobqueue `_plain`.
- PR #20 animation (350dcf2): DO NOT MERGE, director "Fix first" on every clip. Strict critic: all 5
  FIX (weight, secondary motion, timing; notes folder motion_critic_s7.md). anim-b4 (opus) applies it
  all + bird hop + kinetic chain + gravity faint -> previews_v4/. Then fresh motion-critic, then the
  director. Mocap option (notes mocap_licences_2026-10-20.md: Quaternius UAL CC0, CMU) only if the
  tuned person walk still reads mechanical: ask him (D-005 change; downloading needs his yes).
- monster-b2 lives in the OLD lead session (claude/monster-rig, head d66d38b); old lead forwards.
- Proposed card: Step 3 foot joint fix (task_043885cd).
- asset-forge-wt has 5 worktrees: context-trim (claude/context-trim, uncommitted CLAUDE.md +
  settings.json) is not a lead lane; owner unknown. Do not touch; remove when its owner is done.

## Next steps
1. #20: anim-b4 report -> fresh motion-critic on previews_v4 -> clips to director (render from
   the worktree path; notes-folder files did not show for him).
2. clean-b8 report -> check evidence, fresh realism-critic (own scratch subfolder), merge #9.
3. #9 merged -> open step2-page PR (sync main first; gates/ add/add take #9's), merge on green.
4. Board PR after each merge. Then monster-rig PR when a slot frees.
5. First usable build = item 12 merged. Show director one end-to-end model (five views + Godot).

## Restart kit
Respawn from each lane's handoff with ~/.claude/skills/game-studio-lead/references/team-kit.md.
GPU: models/gpu.lock. Lanes: asset-forge-wt/{clean-step, animation, step2-page, monster-rig}.

## Gotchas
- Generators disagree on which camera the reference faces; check facing per prompt.
- Critics share the scratchpad: give each its own subfolder.
- No HF token on this PC; gated weights are out. Playbook: nothing new.
