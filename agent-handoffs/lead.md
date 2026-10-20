# Asset Forge lead handoff (2026-10-20, session 7, at the 200k guard)
## State: working; no new work in s7. Six in-process builders finish here, then s8 takes over.
s7's builders live only inside s7 (they die if s7 is archived). s8: check list_sessions / ListAgents;
any builder below with no report = respawn fresh from its lane handoff file.

## Session goal (director /goal 2026-10-20): "functional build prototype with at least 80% critic pass rate"
Measure (lead's call): tools/e2e/run_e2e.py on claude/prototype (main + #9 + step2-page + #20 +
skeleton-fit + ref-drawer), 5 bake-off prompts x 2 generators. Fresh critics, one verdict per item
(briefs: notes folder critic_briefs_e2e.md): realism per clean five-view sheet (10), motion per
animated rig clip set (6), screen per step page (4). Pass = SHIP/judged >= 80% (16 of 20), and every
non-monster model exports with the Godot check green. Output: notes folder e2e/run<N>/.

## Director said (2026-10-20)
- "eta til usable build?" -> ~1.5-2 working days. D-025/D-026: run phases in parallel.
- Clean colour "Keep improving first" (D-027, merged #21).
- PR #20 clips: "Fix first", all of person walk, fox walk, bird walk, attack/faint. TO LOG D-028.
- "spawn another helper, stop making me ask, be productive": fill free slots unasked.
- Asked "video to animation?": answered not now; people-only custom moves later if mocap wins;
  roadmap only on his say-so.

## Lanes (notes folder = C:/Users/DANTE/AppData/Roaming/Claude/side-session-notes/local_7fdc3e78-46c6-48b7-9439-a48ba40b7296)
- clean-b8 (opus): worktree asset-forge-wt/clean-step, local claude/clean-step-methodB-local
  (a57382f base, 6/10). Causes: bird beak registration, triposg fox 2 parts, hi3dgen fox
  chest/legs, humanoid greaves. Bar 8/10 -> pushes into claude/clean-step + PR #9 body.
  Next: fresh realism-critic on the 10 sheets, merge #9. Handoff agent-handoffs/clean-step.md.
  clean-b8 hit its guard: stops after the S1 run (make_solid on hi3dgen fox, triposg fox, hi3dgen
  humanoid). s8 respawns clean-b9 from agent-handoffs/clean-step.md.
- anim-b4 life 2 (opus): asset-forge-wt/animation, local WIP 5a87bdd (not pushed; #20 at
  350dcf2). Critic list notes motion_critic_s7.md. 9 of 79 unit fail (diagnosed in
  agent-handoffs/animation.md). Lead confirmed fox walk 1.3 strides/s, birds <=0.3 m hop. Left:
  unit green, framing, -m blender, previews_v4, PR body, push. Next: fresh motion-critic -> director.
- skel-fit (opus): asset-forge-wt/skeleton-fit, claude/skeleton-fit 4ca50ca+ (foot ball joint,
  fox yaw 18->0 deg, plus the hock joint asked by lead). Out models/skeleton_out_fit/. Pushes, no PR.
- ref-drawer (sonnet): asset-forge-wt/ref-drawer, claude/ref-drawer: SDXL base reference drawer
  (text-only input was never wired: UnavailableDrawer). Evidence notes ref_drawer/. Pushes, no PR.
- proto (opus): THIS worktree, branch claude/prototype (1dacaad merge + e2e runner 1f9d63f,
  shots 49eec7e). App on 127.0.0.1:7871 (proto's PID). Run1 (bake-off ref pictures) -> notes
  e2e/run1/. Conflicts recorded in agent-handoffs/prototype.md. Gap: five-view sheets in
  clean/before|after not served by the file route (design 5.7) -> fix in step2-page PR.
- mocap-cmp (opus): scratch only, notes mocap_cmp/: procedural vs CC0/CMU mocap side by side for
  the person (licences: notes mocap_licences_2026-10-20.md). Evidence for a D-005 question.
- monster-b2 lives in the OLD lead session (claude/monster-rig); old lead forwards.
- claude/step2-page a131c49 pushed (count fix + _settle); its worktree was removed. PR after #9.
- context-trim worktree (claude/context-trim, uncommitted CLAUDE.md + settings) is not ours.

## Next steps (s8)
1. On each report: verify files exist, fresh critic, filter findings.
2. Re-merge moved branches into claude/prototype; run e2e run2; run the three critics; score.
3. Merge order: #9 -> step2-page PR (open at once) -> #20 (after director yes on v4 clips) ->
   skeleton-fit PR -> ref-drawer PR. Max 3 open PRs. Board PR after merges (log D-028).
4. Director: v4 clips (send GIFs from inside a session folder; notes-folder files did not show),
   then mocap side-by-side if the person still reads mechanical (D-005 change, his call).

## Gotchas
- Generators disagree on which camera the reference faces; check facing per prompt.
- Critics share the scratchpad: give each its own subfolder. No HF token; gated weights out.
- Playbook: nothing new yet (candidate: strict motion bar caught what foot-slide checks missed;
  file once v4 passes his look).
