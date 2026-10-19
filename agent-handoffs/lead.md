# Asset Forge lead handoff (2026-10-20, session 3, handing off at 203k)
## State: available (all env builders reported; successor runs the candidates)

## Task
STATUS item 3, generator bake-off (design 5.2 + section 9 bar: fits 12 GB, commercial licence,
<=3 min/model, five-view pass on >=3 of 5). Done = script + report (time, peak VRAM, licence,
labelled five-view sheets per candidate), lead QC (art-qa-critic, fresh realism-critic per board),
one AskUserQuestion to the director to pick, decision logged.

## Where things are
- Repo C:\Users\DANTE\Documents\GitHub\asset-forge (MAIN), main ecdf66c, no open PRs.
- Worktree MAIN/../asset-forge-wt/bakeoff, branch claude/bakeoff, NOTHING COMMITTED YET:
  tools/bakeoff/{prompts.toml, gpu_lock.py, run_candidate.py (adapter contract in docstring),
  render_views.py (Blender 6 views clay+colour + stats, tested), sheets.py (labelled sheets +
  per-prompt boards, tested), make_refs.py (refs builder), adapters/<name>.py (builders)}.
  Docs edits (LF endings; write files with bytes, Python write_text makes CRLF on Windows):
  DECISIONS D-011 SF3D skipped (director), D-012 per-model envs (lead), D-013 UI clean+intuitive,
  D-014 non-technical users / only on his PC / VRAM shown, D-015 optional local-AI QA (Phase 7,
  design 5.6), D-016 Claude MCP server (Phase 8, design 5.7); design section 6 UI gate; ROADMAP 7-8.
- Envs MAIN/models/envs/<name>, src MAIN/models/src/<name>, weights MAIN/models/hf (gitignored).
  Torch standard: 2.14.1+cu130 (download.pytorch.org/whl/cu130); PyPI torch on Windows is CPU-only.
- Builder rules: C:\Users\DANTE\AppData\Roaming\Claude\side-session-notes\local_b118c49f-c304-49df-91fd-c598a7a48c30\bakeoff_builder_rules.md
- Builder reports land in that notes folder as builder_reports.md (old session relays them).

## Refs (MAIN/models/bakeoff/refs, picked by lead from ref_candidates/*_sheet.png)
humanoid s5 (closest to A-pose, front, no sword), spider s7 (8 legs; s1 has ~12, rejected),
fox s1 (side, facing left), bird s5 (side, facing left). BRUTE MISSING: SDXL drew two arms on all
8 seeds (six-arm prompt fails; s4/s5 greyscale, s0 turnaround). Next: rerun
`models/envs/sdxl/Scripts/python tools/bakeoff/make_refs.py --only brute --seeds 8-23` with a
stronger prompt; if still no six arms, report it as a front-end finding and ask the director
(supply an image, or test with the best 2-arm brute). SDXL: ~9.3 s/image, 10.9 GB torch peak.

## Builders: all reported - read notes builder_reports.md (D3D-S2 20 GB / 833 s and Hi3DGen 13 GB need one low-VRAM try each).
triposg (had CPU torch; told to fix), triposr, hi3dgen, direct3d_s2, step1x3d. sf3d + refs done.

## Next steps
1. Read builder_reports.md; fix/finish any candidate that is not runnable (fresh builder per fix).
2. Brute ref (above). 3. Run each: `python tools/bakeoff/run_candidate.py <name>` (serial, lock).
4. `uv run --with pillow python tools/bakeoff/sheets.py [name=yawdeg]` -> models/bakeoff/sheets.
5. QC each board (fresh realism-critic), write docs/audits/bakeoff_2026-10-20.md (+ sheets copied
   to docs/audits/bakeoff/), PR per forge-pr, ask the director, log D-017 pick.
6. Note for report: geometry-only winners need a colour route (project the ref in Blender).

## Open questions for the director
None pending (answered: SF3D skip; only his PC; local-AI QA later; MCP on roadmap).

## Gotchas
- glTF splits verts on seams: render_views welds before counting parts.
- No HF token on this PC; gated weights are out.
- Playbook: nothing new.
