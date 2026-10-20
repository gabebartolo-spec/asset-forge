# Asset Forge lead handoff (2026-10-21, session 8)
## State: awaiting director (knight clips sent). Director: "spawn no helpers": the lead builds itself.
Lead registered for 500k (~/.claude/context-guard-leads/<CLI session id>); a successor registers itself.
Handoff lives on claude/lead-handoff-s8. Animation work: worktree asset-forge-wt/anim-fix, branch
claude/anim-look, pushed onto PR #20's branch (claude/animation, head 2f4fe61).

## Goal (director /goal): "functional build prototype with at least 80% critic pass rate"
Measure: run_e2e.py on claude/prototype, 5 prompts x 2 generators; critics: realism per clean sheet (10),
motion per clip set (6), screen per page (4); pass 16/20, every non-monster export Godot-green.
Critics not started (no helpers); the lead judges sheets, screens and clips itself.

## Animation fix (the active work; director 2026-10-20: all clips "kinda bad")
Knight walk waddle, floppy punch, slapstick faint = procedural humanoid clips. Director 2026-10-21: "lots of
free animations for humanoids online we can use" -> yes to download. DONE (2f4fe61, PR #20): humanoid clips
now come from Quaternius Universal Animation Library [Standard] v3.0 (CC0; walk, jog, punch jab, hit chest,
death, idle), baked by blender/bake_library.py to src/asset_forge/animate/data/ual_humanoid.json (260 KB, zip
not in git), re-targeted in animate/library.py (per-bone world turn + rest correction, pelvis scaled by hip
height, 24->30 fps), clips.make_clips(library=True) for humanoids only; walk/run speed fitted, planted feet
pinned by IK (PIN_TOL/PIN_RAMP); attack/hit exempt from slide gate (check.py "library" flag); ground_library in
animate.py. Knight: gates pass (walk 0.9 cm, run 0.1 cm), Godot import OK, 13 new tests, ruff clean. GIFs sent
to the director (out/big in anim-fix). Procedural humanoid kept: make_clips(library=False) or
AF_PROCEDURAL_HUMANOID=1. LICENCES.md row added. Dev loop: pure-python Body from skeleton.json (fast), then
blender -b blender/animate.py with ABSOLUTE paths (relative preview paths silently write nothing), then
tools/animate/sheet.py for contact sheets. Rigs: run rig_two.py (notes folder) -> out/rigs.
FOX: "3 legged" is a MODEL defect, not animation: the TripoSG fox has 3 proper legs + a small pale stub
(zoom sheet sent). Hind legs do move (7 cm stride). Fix = regenerate/reroll the fox; limb check (#27) must
reject it. Candidate for animals: Quaternius Ultimate Animated Animals (CC0, 12 animals, walk/gallop/attack/
death) retargeted like the humanoid; not started. Bird walk slide 0.7 > 0.5 cm still open.

## Merged s8
#9 #23-#33 all merged (clean 8/10, monster rig, GPU lock, cut-out back end #32 + page #33, docs #31).
Open: #20 only (needs the director's OK on the knight clips, then merge on green).

## Next
1. Director verdict on knight clips -> merge #20 (CI green first; check headRefOid = 2f4fe61 or newer).
2. Fox: reroll TripoSG fox, check limb count; then animals from library clips (see above) if he agrees.
3. Re-run e2e run3 on main + #20 (runner on claude/prototype, tools/e2e; free port; chromium
   --use-angle=d3d11 --enable-gpu); live-draw check of one_subject; score vs critics bar.
4. Research leads (2026-10-21, not adopted): Hunyuan-Motion text-to-motion (Tencent licence, Hunyuan banned
   D-010, so no); Pixal3D (6 GB image-to-3D, check licence); UAL2 (CC0, 130 anims, parkour/combat);
   cinevva 260 CC0 clips. Also: Marigold delighting, Z-Image-Turbo vs SDXL, wireframe toggle, real-height field.
   Phase 12 (all 3D asset types, D-032) only when STATUS lists it.
5. Board PR: STATUS agents table stale (all sessions archived); add the library-clips decision to DECISIONS.

## Director said
D-027 clean keep improving; D-028 clips fix first; D-029 no subagents, helpers = sessions in group
"Asset Forge" (cg-c0fac8a5-7dfb-46ec-a0fd-658fe73e9182); "spawn no helpers"; helpers 300k/450k, leads 500k/600k;
GPU: as many jobs as fit (#28); "if theyre stuck, unstick them"; "stop wasting my time"; clips must be real
clips at readable size (my 640 px "reads fine" was rejected before); "do some online research in general".

## Sessions
None running. Worktrees to remove: asset-forge-wt animation, clean-step, monster-rig, mr_* (old; monster-rig
.venv is still the one I use, keep until a new venv exists); keep context-trim (not ours). anim-fix is live.
Untracked out_clips/ in the lead worktree (GIF copies; do not commit).

## Gotchas
- Main .venv lacks fastapi: use asset-forge-wt/monster-rig/.venv python with PYTHONPATH=src (its editable
  install points at monster-rig, so tests in another worktree need PYTHONPATH=src or they import the wrong code).
- Bash cwd resets after each call: always cd to the worktree in the same command.
- Stall watchers must watch where helpers really write (notes folder), not just worktrees.
- Notes folder: C:/Users/DANTE/AppData/Local/Claude-Data/claude_pzs8sxrjxfjjc/side-session-notes/.
- Godot console exe: C:/Users/DANTE/Desktop/Godot_v4.7.2-stable_win64.exe/Godot_v4.7.2-stable_win64_console.exe
  (goes in config.local.toml [godot] exe).
