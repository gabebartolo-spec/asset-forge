# Asset Forge lead handoff (2026-10-20, session 8)
## State: working. Director: "spawn no helpers" (this turn): the lead builds itself, no sessions.
Lead registered for 500k (~/.claude/context-guard-leads/<CLI session id>); a successor registers itself.
Branch for my own work: claude/clean-fox-turn (PR #30). Handoff lives on claude/lead-handoff-s8.

## Goal (director /goal): "functional build prototype with at least 80% critic pass rate"
Measure: run_e2e.py on claude/prototype, 5 prompts x 2 generators; critics: realism per clean sheet (10),
motion per clip set (6), screen per page (4); pass 16/20, every non-monster export Godot-green.
Critics were not started (no helpers). I judged #9 sheets and #27 screens myself as lead.

## Root cause of run2 (found this turn)
Run2 drew its references from words with SDXL: humanoid = front+side in one picture, fox = nine tiled
foxes, bird/brute same. Run1 references were single. That caused: fox "head direction ambiguous", humanoid
top-outline fail (two subjects), and likely the limb-check false positives. Fix = PR #30 (open, CI running):
matte.one_subject() rejects multi-subject/cut-off pictures (rejects 7 of 8 bad run2 refs, passes run1 + the
good run2 ones), draw job retries seed+1 up to 3, negative prompt adds multiple views/collage/tiled.
Fixture tests/fixtures/multi_fox_ref.png. Suite 262 pass. Not exercised: live SDXL draw.

## Merged s8
#23 #24 #25 #26 #28 #29 #9 (clean 8/10, lead-reviewed sheets) #27 (monster rig, lead-reviewed round-2 screens).
#30 merged (one-subject redraw). Open: #20 animation green 3c32535 (needs motion check; GIFs in notes local_68d3bafb.../previews_v4), #31 docs (roadmap phases 10-12, D-030/31/32, design scope + hard-surface budgets; a watcher merges it on green).

## Next
1. (#30 merged; confirm #31 merged.) 2. Re-run e2e run3 on main + #20 + #30 (runner on
claude/prototype, tools/e2e; app on a free port; chromium with --use-angle=d3d11 --enable-gpu).
3. Director asked (2026-10-20): "our forge also needs the ability to remove backgrounds/cut the subject out":
build BiRefNet cutout (MIT; GitHub code + HF weights in its own env, no trust_remote_code; step "Cut out
the subject" with before/after + Cut again; one_subject gate after; LICENCES.md row; board entry).
4. Test Marigold-IID delighting (RAIL++-M, read licence) on the 10 refs; Z-Image-Turbo (Apache 2.0) vs SDXL
in the bake-off; wireframe toggle + real-height field; optional side/back reference slots; KTX2 only if Godot
import check shows a gain. Skip TRELLIS.2 (nvdiffrast banned, 24 GB), LLM/CSG modelling, tree cards.
5. #20: motion check of the 36 clips (as lead), then director clips. Bird walk slide 0.7>0.5 cm still open.
6. Director 2026-10-20 (D-032): scope = every 3D asset (gear, props, vehicles, buildings) + Godot-direct modelling kept: ROADMAP Phase 12 (types, hard-surface bake-off, "Build in code" via Claude MCP, rebuild-from-generated, building kits). Not assigned yet: starts only when STATUS lists it. STATUS item 14 (cut-out) is assigned.
7. Board PR after #20/cut-out merges: agents table is stale (all sessions archived).

## Director said (2026-10-20)
D-027 clean keep improving; D-028 clips fix first; D-029 no subagents, helpers = sessions in group
"Asset Forge" (cg-c0fac8a5-7dfb-46ec-a0fd-658fe73e9182); this turn "spawn no helpers"; context limits
helpers 300k/450k, leads 500k/600k; GPU: as many jobs as fit (#28); "if theyre stuck, unstick them";
"archive helpers no longer in use". He shared Reddit posts to mine for ideas (assessed above).

## Sessions
None running. All lane sessions archived (monster/clean/anim/proto/ref/gpu/ci). Worktrees: asset-forge-wt
animation, clean-step, monster-rig, mr_* (old; remove), context-trim (not ours).

## Gotchas
- Main .venv lacks fastapi: use asset-forge-wt/monster-rig/.venv with PYTHONPATH=src.
- Stall watchers must watch where helpers really write (notes folder, mr_evidence), not just worktrees.
- Notes folder moved: C:/Users/DANTE/AppData/Local/Claude-Data/claude_pzs8sxrjxfjjc/side-session-notes/.
- Playbook: nothing proved yet (one_subject check pending #30 merge + run3).
