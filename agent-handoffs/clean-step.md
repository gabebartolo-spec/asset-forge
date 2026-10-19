# Handoff: clean-step (PR #9, builder), rewritten 2026-10-20 (second colour-fix round)
State: second colour-fix round pushed; waiting on CI and the lead's fresh fidelity check.
Branch claude/clean-step, worktree asset-forge-wt/clean-step. PR body Evidence updated (A to E).
Done in blender/clean.py (bake_colour rewritten):
- A: Registration class (bbox scale per axis + smoothed per-row shift of outline centres); head-band
  width-ratio gate HEAD_WIDTH_RATIO (0.4, 2.0): outside it the head is low-frequency, no face.
- B: fill = normalised diffusion over the mesh edge graph, per vertex, interpolated over triangles;
  seam feather 5% of height by graph diffusion (alpha 0 at the seam).
- C: fill sources skip cos < 0.34 (70 deg) and pixels < 0.55 x band median (8 bands); in report.json.
- D: side views (camera +X) mirror left-right only (x -> 2cx - x, snapped to nearest surface).
- E: albedo was true; lit sheet fixed with Standard view transform, no specular, SHEET_EXPOSURE 1.1 EV.
  albedo_vs_reference per height band in report.json; run_all.py adds lit_vs_reference to summary.json.
- Tests: tests/test_clean_colour.py + tests/fixtures/colour_probe.py (5), all failed first on the old
  script except the luma assert of the albedo test (only its missing key failed).
- Godot headless check: 4 of 10 clean.glb IMPORT_CHECK_OK (hi3dgen humanoid/fox/bird, triposg brute).
  config.local.toml (gitignored) in the worktree holds the Godot and Blender paths.
Left / open: lead's fresh fidelity check of the 10 sheets; humanoid albedo saturation 0.65-0.87;
 fox chest grey-brown; head gate lower bound 0.4 is my call (0.5 lost the hi3dgen spider face).
Scratch: C:/Users/DANTE/AppData/Local/Temp/claude/.../scratchpad (one.py runs one model).
