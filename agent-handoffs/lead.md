# Lead handoff, 2026-10-20 (session 2)
## State: awaiting director (Hunyuan in or out of the bake-off)

## Task
Lead of Asset Forge: local text/image -> game-ready 3D (clean mesh, skeleton, procedural
animations, .glb) and pixel-perfect Pokémon-style sprites. Read, in order: `CLAUDE.md`, this
file, the design `docs/superpowers/specs/2026-10-19-asset-forge-design.md` (in full),
`docs/STATUS.md`, `docs/DECISIONS.md`, `docs/LICENCES.md`. Then do STATUS "Assigned items".

## Branch and commit
- Phase 0 done: gate proved (`docs/audits/kickoff_gate.md`, PRs #1-#3 closed unmerged), licence
  register filled (D-009). Board PR `claude/phase0-board` carries both; check it merged.

## Next
Phase 1 item 3, the bake-off. Candidates that are CLEARED: TripoSG (swap RMBG for BiRefNet),
TripoSR, SF3D, Hi3DGen, Direct3D-S2, Step1X-3D geometry-only if it fits. Hunyuan 2.x only if the
director keeps it (HELD, D-009). Text-to-image front end: SDXL + `pixel-art-xl` are cleared, but
a non-pixel reference model for 3D input still needs a licence row.
Blocker to solve first: the Stability Matrix ComfyUI folder was not found (searched C:\Users\DANTE
and D:\ to depth 3; %APPDATA%\StabilityMatrix has no LibraryDir). Our own `.venv` per model is
allowed and may be simpler than ComfyUI for TripoSG/SF3D.

## Open decisions
- Director: keep Hunyuan in the bake-off despite the EU/UK/South Korea output ban?

## Running jobs
None.

## Findings for the lead
- Civitai returns "not available in your region" from this PC, so Civitai licence flags cannot
  be read here; treat Civitai models as unverifiable.
- Planted-defect PRs bind to the lead session's PR bar; auto_fix and auto_archive were off.
Playbook: nothing new.

## Rules learnt the hard way (under 10 lines)
- Southern Cross is Essentials Gen 9 Pack, not GBA; check the target game's files before
  assuming a sprite format.
- "MIT" on a 3D model is not enough: check its export path's dependencies (nvdiffrast,
  diffoctreerast are non-commercial).
