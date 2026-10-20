# Handoff: skeleton (board item 9, D-024), updated 2026-10-20
State: everything built, evidence done, PR opened as draft from claude/skeleton. Left: wait for CI, mark ready.
Worktree asset-forge-wt/skeleton, own venv .venv. Inputs: main checkout models/skeleton_in, outputs models/skeleton_out.
Evidence folder: C:/Users/DANTE/AppData/Roaming/Claude/side-session-notes/local_f6b2f763-b2e4-47af-990a-44f6a54cc5ed/skeleton/
 (sheets/ 12 five-view-style sheets, screens/ hi3dgen humanoid at 1366 and 1920, godot_check.log 12/12 OK, mutation.txt).
Done: back end, Godot check, mutation proof, bird wing angles lowered, Step 3 page (viewer.js markers, panel-3, app.js),
 merged origin/main (#14), fixed jobqueue error-before-state flake.
Left: CI green -> gh pr ready; fix anything CI finds. TODO(PR #9): Step 2 -> Step 3 hand-over (dev: /?asset=ID).
Not exercised: monsters, hand-over, fingers/eyes/jaw, A-pose retarget quality, page shots of animals.
Notes: bash tool breaks on heredocs with apostrophes; Write tool for files; the app GPU queue waits on models/gpu.lock
 held by other agents (screenshots may wait minutes).
