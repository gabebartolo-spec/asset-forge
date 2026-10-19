# Sprites handoff, 2026-10-20
## State: running a check (real GPU proof pending)
## Task
Phase 5 sprite mode A back end: src/asset_forge/sprites (presets, SDXL+pixel-art-xl draw, grid detect,
post-process, QA, export, CLI). No UI, no web/, no api.py.
## Branch and commit
claude/sprites, draft PR. See `git log`.
## Unfinished changes
Real GPU proof (Southern Cross + GBA pair) and notes.md in
C:\Users\DANTE\AppData\Roaming\Claude\side-session-notes\local_d40f4221-0337-4df7-aee9-69379fac41e2\sprites\
## Evidence so far
36 unit tests pass (PYTHONPATH=src python -m pytest), ruff clean.
## Attempts (fix-loop record)
Grid detect v1 (smallest pitch) picked 4 not 8 (divisors also hold every edge); v2 largest pitch with
>=80% of strong-edge energy, weak steps (<60 summed RGB) ignored.
## Open decisions
Southern Cross file layout assumed Graphics/Pokemon/Front|Back/<Name>.png (not verified against the pack).
## Running jobs
CLI run holds models/gpu.lock as owner "sprites". It first downloaded SDXL into the worktree's own
models/ folder (path bug, fixed since); delete worktree models/ after the run.
## Findings for the lead
none yet
## Rules learnt the hard way
- Long heredocs in this Bash tool can fail on quoting; use the Write tool for source files.
