# Lead handoff, 2026-10-20 (written for the account switch)
## State: available (Phase 0 item 1 is next)

## Task
Lead of Asset Forge: local text/image -> game-ready 3D (clean mesh, skeleton, procedural
animations, .glb) and pixel-perfect Pokémon-style sprites. Read, in order: `CLAUDE.md`, this
file, the design `docs/superpowers/specs/2026-10-19-asset-forge-design.md` (in full),
`docs/STATUS.md`, `docs/DECISIONS.md`. Then do STATUS "Assigned items" in order.

## Branch and commit
- main: the first commit (scaffold + design), pushed to github.com/gabebartolo-spec/asset-forge
  (public). Branch protection on main: `test`, `doc-caps`, `gitleaks` required, squash only.
- No worktrees, no open PRs.

## Unfinished changes
None. Next: Phase 0 item 1 (gate-proving throwaway PRs), item 2 (licence rows), then Phase 1
bake-off. The bake-off result goes to the director as labelled five-view sheets before any app
code is written.

## Evidence so far
- Builder check run on the design (Sonnet subagent, 2026-10-19); its 8 questions are answered in
  design section 9 (1 by the director, 7 lead calls, D-007/D-008).
- Local: `pytest` 2 passed, `ruff check .` clean, at the first commit.

## Attempts (fix-loop record)
None.

## Open decisions
None waiting on the director. Lead calls in design section 9 may be overruled by him.

## Running jobs
None. A brainstorm mockup server may still run from the old session (localhost, auto-exits after
4 h idle); ignore it.

## Findings for the lead
- The project-kickoff scaffold is Godot-only. For a Python tool, the Godot harness (tests/*.gd,
  run_tests.sh, shard planner, gdlint, build.yml, godot-tests and sim-review skills) was removed
  and replaced with pytest + ruff (`tests.yml`, `forge-tests` skill). Not yet proved across
  projects, so not in the skill's learnings.
- The machine already has `hunyuan3d-dit-v2-mv_fp16` and SDXL pixel-art models in the Stability
  Matrix ComfyUI; never update or modify that install (shared-machine rule).
Playbook: nothing new.

## Rules learnt the hard way (under 10 lines)
- Southern Cross is Essentials Gen 9 Pack, not GBA; check the target game's files before
  assuming a sprite format.
