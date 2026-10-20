# Asset Forge lead handoff (2026-10-20, session 8)
## State: working. Five lane sessions + one rule sweep running; lead waits on their notes.
Lead session registered for 500k (~/.claude/context-guard-leads/<CLI session id>); successor must
register itself at boot.

## Session goal (director /goal 2026-10-20): "functional build prototype with at least 80% critic pass rate"
Measure: tools/e2e/run_e2e.py on claude/prototype (main + clean-step-methodB-local + step2-page +
animation + ref-drawer + monster-rig), 5 bake-off prompts x 2 generators. Fresh critic SESSIONS,
one verdict per item (briefs: notes local_7fdc3e78.../critic_briefs_e2e.md): realism per clean
five-view sheet (10), motion per animated rig clip set (6), screen per step page (4). Pass = 16 of 20,
every non-monster export Godot-green. Output: notes folder e2e/run<N>/.

## Director said (2026-10-20)
- D-027 Clean "Keep improving first"; D-028 #20 clips "Fix first" (logged, #24 merged).
- D-029 no subagents; helpers are fresh sessions filed in sidebar group "Asset Forge"
  (cg-c0fac8a5-7dfb-46ec-a0fd-658fe73e9182). Start them yourself ("stop making me approve things").
- "change lead context limit to 500k" and "increase to 300k (450k hard cutoff) for all helpers":
  hook + RULEBOOK line 99 + ~/.claude/CLAUDE.md done; sweep of other files = rule-ctx-sweep.
- "hurry the fk up": fill every lane at once, no idle slots.

## Merged this session
#23 (CLAUDE.md no-subagents line), #24 (board s8: D-028, D-029, agents table).

## Lanes (sessions; each reports via turn-end note)
- af-clean local_9e53e68c: item 5, method B to 8/10, pushes into claude/clean-step, PR #9 ready.
  Then: fresh realism-critic session on the 10 sheets -> merge #9 -> open step2-page PR.
- af-anim local_5de871d0: item 10, re-rig on #22 joints, 9 unit fails, previews_v4, PR #20.
  Then: fresh motion-critic session -> director clips (send GIFs from a session folder).
- af-refdraw local_8ba42145: SDXL text-only reference drawer; PR only if < 3 open.
- af-monster local_863debb1: item 13 monster skeleton + limb editor; no PR yet (cap).
- af-proto local_bbbdbf10: re-merge lanes into claude/prototype, five-view file-route gap, e2e run2.
- rule-ctx-sweep local_38465d31: context-limit wording sweep + forge-handoff skill PR.
Old s7 builders (anim-b4, ref-drawer, proto) may still push to their branches; new lanes reset onto them.

## Next steps
1. On each note: verify files exist; start a fresh critic session; filter findings.
2. Merge order: #9 -> step2-page PR -> #20 (after director yes on v4) -> ref-drawer -> monster-rig.
   Max 3 open PRs. Board PR after merges.
3. When run2 is in: start realism/motion/screen critic sessions (own scratch subfolders); score.
4. Mocap side-by-side (notes mocap_cmp/) only after v4 passes; D-005 change is his call.

## Worktrees
asset-forge-wt: animation, clean-step, monster-rig, ref-drawer (old s7 lanes; remove as each
lane merges), context-trim (not ours). skeleton-fit removed (merged #22).

## Gotchas
- Generators disagree on which camera the reference faces; check facing per prompt.
- Critics share the scratchpad: give each its own subfolder. No HF token; gated weights out.
- Background `sleep` loops may exit early here; check PR state directly after a watcher ends.
- Playbook: nothing new.
