# Asset Forge lead handoff (2026-10-20, session 5)
## State: available (bake-off done: D-019 Hi3DGen then TripoSG; D-020 logged; PR #6 waits on CI)

## Task
STATUS item 3, generator bake-off. Report docs/audits/bakeoff_2026-10-20.md is written: Hi3DGen
4/5 and TripoSG 4/5 pass the bar; Step1X-3D 2/5, TripoSR 1/5 fail (fresh realism-critic per board
+ lead check). Director question: which passing generators go on the Step 1 menu and in what
order (D-019), and what the prompt generator should do (D-020). Log both in DECISIONS when he answers.

## Where things are
- MAIN = C:/Users/DANTE/Documents/GitHub/asset-forge (main ecdf66c).
- Worktree MAIN/../asset-forge-wt/bakeoff, branch claude/bakeoff, PR: see `gh pr list`.
  Session 5 changes: render_views.py camera roll fix (to_track_quat("-Z","Y")), rotation_mode
  XYZ (glTF import leaves QUATERNION so turns were ignored), --pitch; sheets.py
  cand[:prompt]=yaw[,pitch] overrides; TripoSR adapter applies upstream to_gradio_3d_orientation;
  ruff clean-up of every adapter (builder); ROADMAP Phase 9 prompt generator; audit report;
  docs/audits/bakeoff/*.jpg + summary.json (personal paths stripped). uv.lock untracked: not ours.
- Saved TripoSR meshes were turned in place with the upstream step; originals in
  MAIN/models/bakeoff/out/triposr/raw/.
- Sheets command (facing so "front" = face; renders cached, delete sheets/renders to redo; never
  leave your shell cwd inside sheets/renders or rm fails "busy"):
  `uv run --with pillow python tools/bakeoff/sheets.py hi3dgen step1x3d triposg triposr
  hi3dgen:fox=-90 step1x3d:fox=90 triposg:fox=90 triposg:bird=90 triposr=180 triposr:fox=-90
  triposr:bird=-90`

## Measurements (gen per model / whole-GPU peak / raw tris)
Hi3DGen 12-14 s / 6.8 GB / 220k-592k; Step1X-3D 16-18 s / 5.8 / 200k; TripoSG 29-33 s / 6.3 /
674k-1.38M; TripoSR 1-1.5 s / 5.4 / 42k-116k. Only TripoSR has colour.

## Director said this session (2026-10-20)
- "roadmap item: add a prompt generator" -> ROADMAP Phase 9, meaning asked (D-020).
- "hid3gen seems great" (before QC finished).
- On TripoSR sheets: "weird patterns on all of these" = TripoSR's lumpy surface, a real defect.

## Next steps
1. DONE in PR #6: D-019 (menu Hi3DGen, then TripoSG), D-020 (prompt generator = "Expand my
   idea"), STATUS item 3 DONE, design 5.2, ROADMAP Phase 9. Merge #6 on green at the exact head
   (Auto-fix is on); then remove the bakeoff worktree.
2. Then wait for the next assigned item (Phase 2 needs a colour route for geometry-only models).

## Gotchas
- Generators disagree on which camera the reference faces; check facing per prompt.
- Critics share the scratchpad: give each its own subfolder (two overwrote each other's grids).
- glTF splits verts on seams: render_views welds before counting parts.
- No HF token on this PC; gated weights are out. Playbook: nothing new.
