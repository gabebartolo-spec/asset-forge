# Asset Forge lead handoff (2026-10-21, session 8)
## State: handing off. #20 MERGED 2026-10-20 (8c8c724) on the director's OK; fox reroll is next. Director: "spawn no helpers": the lead builds itself.
Lead registered for 500k (~/.claude/context-guard-leads/<CLI session id>); a successor registers itself.
Handoff lives on claude/lead-handoff-s8. Animation work merged; worktree asset-forge-wt/anim-fix (branch
claude/anim-look) can be removed.

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
#9 #20 #23-#33 all merged (#20 = library humanoid clips + animation, squash 8c8c724). No open PRs.

## Next (director 2026-10-21: "Knight clips are good, merge #20 once CI is green, then reroll the fox")
1. REROLL THE FOX (in progress, not started): run the real app with the new main. Ready environment:
   worktree .claude/worktrees/priceless-kilby-4abc26 (detached eadbfe4 = claude/prototype, own .venv,
   config.local.toml port 7872, FORGE_MODELS_DIR=C:/Users/DANTE/Documents/GitHub/asset-forge/models).
   `git fetch; git merge origin/main` there, then `python tools/e2e/run_e2e.py OUT --only fox --generators triposg`
   (SEED pinned 1234 in run_e2e.py: add a --seed option or change it for the reroll). The Step 1 limb check must
   reject a fox with a missing leg (run2 flagged every fox). Pass = 4 proper legs in the five-view sheet, limb
   check green, clean + rig + animate + Godot green; then send the fox walk clip at readable size to the director.
   If the stub-leg persists across seeds, fix the reference (a side-on fox shows only 2 legs per side).
2. Then run3 for all 10 (5 prompts x 2 generators), score vs the critics bar (16/20), one_subject live-draw check.
3. Animals from library clips: Quaternius Ultimate Animated Animals (CC0) retargeted like the humanoid; propose
   to the director after the fox. Bird walk slide 0.7 > 0.5 cm open.
4. Research leads (2026-10-21, not adopted): Hunyuan-Motion (Hunyuan banned D-010, no); Pixal3D (6 GB
   image-to-3D, check licence); UAL2 (CC0); Marigold delighting, Z-Image-Turbo vs SDXL, wireframe toggle,
   real-height field. Phase 12 only when STATUS lists it.
5. Board PR: STATUS agents table stale (all sessions archived); log the library-clips decision in DECISIONS.

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
