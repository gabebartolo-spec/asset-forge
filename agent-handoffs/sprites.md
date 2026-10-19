# Sprites handoff, 2026-10-20
## State: awaiting lead (PR open, CI running)
## Task
Phase 5 sprite mode A back end: src/asset_forge/sprites (presets, SDXL+pixel-art-xl draw, grid detect,
post-process, QA, export, CLI). No UI, no web/, no api.py.
## Branch and commit
claude/sprites, draft PR. See `git log`.
## Unfinished changes
Nothing; proof done (see notes.md in the shots folder).
C:\Users\DANTE\AppData\Roaming\Claude\side-session-notes\local_d40f4221-0337-4df7-aee9-69379fac41e2\sprites\
## Evidence so far
40 unit tests pass, ruff clean; real SC + GBA pairs run (95 s per pair, 10.9 GB peak).
## Attempts (fix-loop record)
Grid detect v1 (smallest pitch) picked 4 not 8 (divisors also hold every edge); v2 largest pitch with
>=80% of strong-edge energy, weak steps (<60 summed RGB) ignored.
## Open decisions
Southern Cross file layout assumed Graphics/Pokemon/Front|Back/<Name>.png (not verified against the pack).
## Running jobs
None. Worktree models/ removed.
## Findings for the lead
none yet
## Rules learnt the hard way
- Long heredocs in this Bash tool can fail on quoting; use the Write tool for source files.
