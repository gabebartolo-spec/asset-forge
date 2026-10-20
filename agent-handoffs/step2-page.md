# step2-page handoff, 2026-10-20
## State: available (done, waiting for the lead to open the PR)
## Task
STATUS item 12: Step 2 Clean page, Step 2 -> Step 3 hand-over, Clean in the Library batch.
## Branch and commit
claude/step2-page (worktree ../asset-forge-wt/step2-page). Merge AFTER #9. No PR opened (lead opens it).
## Unfinished changes
none. One thing to settle at merge: `src/asset_forge/gates/` is copied byte-for-byte from claude/clean-step
(#9) because `clean_step.py` imports it and main does not have it yet. Identical add/add merges clean; if #9
changed it since, take #9's version.

## PR body (paste as is)
### What
- `POST /api/assets/{id}/clean` (was 501) is a job on the one GPU queue: runs `blender -b --python
  blender/clean.py` (steps.clean_command, now with `--generator` of the maker used), reads report.json,
  and returns a verdict: `passed`, `problems` (plain-words broken limits from `gates.check` plus failed
  animal colour regions), triangles / budget / raw triangles, texture size, height. Result stored in
  `clean/result.json`; only a passing model sets `reached = clean`. Old outputs are removed before a redo.
  A Blender crash or no report = failed job "Press Redo".
- `/skeleton` now also refuses (409) a model whose clean result says `passed: false`.
- Page, panel 2: Clean up button, then Before (rough, clay) / After (cleaned, own colour) switch in the
  viewer, verdict in plain words, broken limits as a list, triangles of allowed, colour picture size, height.
  Failed gate: Next greyed and says why, Redo re-runs. Passed: Next: Skeleton opens Step 3 on clean.glb.
  Pill "2 Clean up" is clickable from Step 3. Library Open on a cleaned model lands on Step 2 (Step 3 if rigged).
  Replaces the TODO(PR #9) hand-over from #15; `/?asset=ID` still works (a clean.glb with no result = passed).
- Library batch (#17): each item is draw, 3D, Clean up, then stops; no skeleton is ever queued (design 5.5).
  A gate failure in a batch fails that item with the broken limit named; the made model stays (card: Make).
### Evidence
- Unit: `pytest` 190 passed (9 deselected), `ruff check .` clean. New tests/test_clean_api.py (9 cases: 409 before
  Make, pass and serve files, each limit named (triangles, texture, side outline) + Skeleton 409, failed colour
  gate, Blender crash + stale files gone, batch stops at Clean and reports a failed gate); test_library batch
  now expects reached=clean and timings draw/generate/clean. The Blender run is the `cleaner=` fake (as CI).
- Real clicks (playwright, Edge, 1366x768 and 1920x1080, mocked clean result on a block model, no page errors):
  scratchpad s2/shots/{1366,1920}_{2a_before_press,2b_busy,2c_pass_after,2d_pass_before,2e_fail,2f_after_redo,
  3_handover}.png. Pass: Next enabled -> click -> Step 3 panel. Fail: Next disabled, pill 3 click ignored, verdict
  shows the triangle fact once (red row "9,400 of 8,000 allowed, down from 310,000") and the bullet "The cleaned shape drifted too far from your original."; Redo -> pass -> Next enabled.
  (dir: C:/Users/DANTE/AppData/Local/Temp/claude/C--Users-DANTE-Documents-GitHub-asset-forge--claude-worktrees-
  asset-forge-status-0d338f/32c9f533-fe4e-47ae-b55b-70ec62248734/scratchpad/s2/shots)
Screen-fix round 2 (lead's critic list): fail state has no duplicate triangle bullet; one line says Press
Redo to try again; outline wording has no numbers; pass row says "down from"; Step 3 pill has no "soon"
pill (it is built); Step 3 shows the cleaned model in its own colour (textured clean.glb, also in the rig
view); --dim lifted to #b0b8c6. Contrast measured on the 1366 fail shot (pillow): disabled Next 8.2,
Compare label 8.2, Drag hint 8.7, footer text 8.2, all above 4.5 (Next and soon pill were already 8.2
and 8.8 before; the critic's numbers did not reproduce). API result gains `broken` (count) and
`all_problems` (full gate text, used by the batch message); `problems` is the screen list.
Unit 190 passed in a fresh venv, ruff clean; test_clean_api / test_library timings assert flaked once
(KeyError 'timings', passed on rerun; likely pre-existing race).
### Not exercised
Real Blender/clean.py through the app (no GPU; mocked); screen-critic and first-use walk-through; a real
textured clean.glb (the mock is a flat orange colour); batch in the browser; real gate wording is #9's
(see findings). Monster and animal pages use the same code, not clicked.
### Board and log
STATUS item 12 -> in review. No decision needed. D-TBD-none.
## Findings for the lead
- gates.check text for triangles says "Decimate harder." and silhouette says "raise the detail": jargon on a
  main-path screen (D-014); suggest #9 reword to "Press Redo" style. Not changed here (#9 owns gates).
- Failed colour-region gate names are shown raw (`'<gate>'`); give them plain labels in #9's report if wanted.
