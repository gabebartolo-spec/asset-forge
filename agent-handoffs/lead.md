# Asset Forge lead handoff (2026-10-20, session 4)
## State: available (candidates all run; successor does sheets, QC, report, PR, director question)

## Task
STATUS item 3, generator bake-off (design 5.2 + section 9 bar: fits 12 GB, commercial licence,
<=3 min/model, five-view pass on >=3 of 5). Done = report docs/audits/bakeoff_2026-10-20.md (time,
peak VRAM, licence, labelled sheets), lead QC (art-qa-critic + fresh realism-critic per board), PR
per forge-pr, ONE AskUserQuestion: which passing models go on the generator menu and in what order
(top = preselected) -> log D-019 (D-018 menu ruling already logged).

## Where things are
- MAIN = C:/Users/DANTE/Documents/GitHub/asset-forge (main ecdf66c, no open PRs).
- Worktree MAIN/../asset-forge-wt/bakeoff, branch claude/bakeoff, HEAD 91fad14 (D-017). Committed in session 4:
  LICENCES rows (diso BANNED, CUDA runtime, torchmcubes MPL, DINOv2/DINO v1, HF cards confirmed,
  Hi3DGen + Direct3D-S2 now CLEARED, BiRefNet pinned), D-018 in DECISIONS + design 5.2 + ROADMAP,
  make_refs.py (--seed-start/--text/--tag, BiRefNet pinned), adapters/. uv.lock left untracked (from uv run; not ours to add).
- Candidates: triposr, step1x3d, hi3dgen, triposg (Direct3D-S2 OUT, D-017; SF3D OUT, D-011).
  Run log MAIN/models/bakeoff/run_all.log; outputs MAIN/models/bakeoff/out/<name>/run.json.
- Hi3DGen low-VRAM fix (builder, adapter only): StableNormal first then freed, Hi3DGen sub-models
  on GPU one stage at a time: torch peak 13.15 -> 5.22 GB, gen 14.2 s, same quality settings.
- Brute ref: SDXL cannot draw six arms (24 seeds, 2 prompts). Director chose A = two-armed colour
  brute (ref_candidates/brute_s6_rgba.png -> refs/brute.png), 2026-10-20. Record in report.

## Next steps
1. DONE: all 4 ran rc 0, no item errors, 5 refs each. Per model gen s / torch GB / GPU GB:
   TripoSR 1.1-1.5 / 4.14 / 5.39 (load 10 s); Step1X-3D 16-18 / 4.8 / 5.8 (wall 128 s for 5);
   Hi3DGen 12-14 / 5.22 / 4.5-6.8 (load 26 s); TripoSG 29-33 / 5.3 / 5.8-6.3 (wall 185 s for 5).
   All fit 12 GB and 3 min; the five-view pass decides the bar.
2. `uv run --with pillow python tools/bakeoff/sheets.py` (fix facing with name=yawdeg).
3. QC boards (art-qa-critic; fresh realism-critic per prompt board); write report + copy sheets to
   docs/audits/bakeoff/; note Step1X-3D adapter cleanup, Hi3DGen offload, colour route for
   geometry-only models (only TripoSR has vertex colour).
4. Commit by name, PR per forge-pr, ask director (menu + order), log D-019.

## Open questions for the director
None pending.

## Gotchas
- glTF splits verts on seams: render_views welds before counting parts.
- No HF token on this PC; gated weights are out.
- Playbook: nothing new.
