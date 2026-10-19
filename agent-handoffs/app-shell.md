# App shell builder handoff (2026-10-20)
## State: round-3 done, live shots in pr8_live3; push + CI + PR body in progress

## Task
Draft PR #8 (branch claude/app-shell). Round-2 critic findings: dark scrim while working, footer shows
"Making your model..." during a run, one VRAM wording per maker (menu text is the single source;
TripoSG "about 5 to 6 GB"), waiting line "It starts by itself when the graphics card is free. You can
leave this open.", empty text "press Make 3D model, bottom right", step 2 hint line. Generators NOT renamed.

## Where things are
- Backend `src/asset_forge/` (generators.py holds vram text). Page `web/` (app.js, style.css, index.html).
- Live driver `live3.py` + `serve3.py` (port 7873) in the session scratchpad; shots go to
  side-session-notes local_d40f4221.../pr8_live3 (not committed).
- Run python with the worktree `.venv` (has fastapi, PIL, playwright). pytest: PYTHONPATH=src.

## Left
shots.md, push, CI at pushed head, PR body Evidence + Not exercised, report to lead.
