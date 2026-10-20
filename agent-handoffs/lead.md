# Asset Forge lead handoff (2026-10-20, session 8)
## State: working. Run2 done (2 of 10 export); critics + fix lanes start on the director's next message.
Lead registered for 500k (~/.claude/context-guard-leads/<CLI session id>); a successor registers itself.
Start sessions only on a director turn (the app refuses starts on peer/automated turns).

## Session goal (director /goal): "functional build prototype with at least 80% critic pass rate"
Measure: run_e2e.py on claude/prototype, 5 bake-off prompts x 2 generators; fresh critic sessions:
realism per clean sheet (10), motion per clip set (6), screen per step page (4); pass 16/20 and every
non-monster export Godot-green. Run2 (notes local_7fdc3e78.../e2e/run2/manifest.md, prototype
eadbfe4): only hi3dgen_bird + pageshots humanoid exported. Bar not measurable yet.

## Run2 blockers (each needs a fix lane)
1. Clean in the APP fails both humanoids on top outline (0.084, 0.129 > 0.08) though the R1 script
   run passed outline 10/10: find what the app path does differently (params, views, scale).
2. Foxes: clean.py exits "animal head direction is ambiguous ... pass --turn DEG"; the app passes no
   --turn and shows a generic error (log hi3dgen_fox_clean_blender.log). Auto-resolve or ask in plain words.
3. Step 1 limb check fails every monster and fox (false positives; from monster-rig).
4. triposg_bird walk foot slide 0.7 cm > 0.5 cm.
5. Monsters: animate refused (6+ legs is a later slice; not a defect for this measure).
6. App throws away Blender logs: errors must name the cause in plain words (D-014).

## Director said (2026-10-20)
- D-027 Clean "Keep improving first"; D-028 #20 "Fix first"; D-029 no subagents, sidebar group
  "Asset Forge" (cg-c0fac8a5-7dfb-46ec-a0fd-658fe73e9182); start helpers yourself.
- Context: helpers 300k/450k, leads 500k/600k (hook + RULEBOOK).
- "why is there only 1 gpu queue? open as many as you can" -> #28 VRAM-budget lock merged; RULEBOOK.
- "its your job to lead ... if theyre stuck, unstick them": stall watcher ($TEMP/stall.py <dirs>;
  watch the dirs helpers really write to), restart stuck helpers unasked, no long digging.
- "archive helpers no longer in use": archive as soon as a helper's PR merges or it reports done.

## PRs
- #9 clean, ready 3561d2c, 8/10 colour (fails: hi3dgen humanoid greaves_back 0.127/0.12, triposg
  fox chest_p90 0.838/0.85; next idea: calibrate each view on texels the picture also sees).
  Sheets docs/audits/clean/*.jpg. Needs fresh realism critic, then merge.
- #20 animation green 3c32535 (round 4, paw-tip fix). GIFs copied to notes local_68d3bafb.../previews_v4
  (36). Needs fresh motion critic, then director clips.
- #27 monster rig green e9b0c4f (lead merged main; #28 settle order kept). Round-2 evidence in
  asset-forge-wt/mr_evidence/round2 (af-monster at 300k, finishing). Needs fresh screen critic.
- Merged s8: #23 #24 #25 #26 #28 #29.

## Live sessions
af-monster local_863debb1 (300k, finishing evidence), af-proto local_bbbdbf10 (run2 done; idle).
af-clean and af-anim archived by the director.

## Next (on the director's next message, same turn)
Start: realism critic (#9 sheets), motion critic (#20 GIFs), screen critic (#27 round2 when pushed),
clean-app fix lane (blockers 1, 2, 6), limb-check fix lane (3), anim slide fix (4). Then run3.

## Gotchas
- Main checkout .venv lacks fastapi; use asset-forge-wt/monster-rig/.venv with PYTHONPATH=src.
- Headless chromium renders WebGL on CPU (56% CPU): launch with --use-angle=d3d11 --enable-gpu.
- Playbook: nothing new yet.
