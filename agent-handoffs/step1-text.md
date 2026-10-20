# step1-text builder handoff (2026-10-20)
## State: PR #14 open, CI + critic pending

## Task
Wire the text path into Step 1 Generate: text box + "Expand my idea" (Qwen3-1.7B on the GPU queue),
text-only run path (draw reference -> check/re-roll -> image-to-3D) behind a mocked drawer, and the two
PR #8 nits (queued footer, hide spin hint while working).

## Branch and commit
claude/step1-text, worktree asset-forge-wt/step1-text (own .venv, gitignored). PYTHONPATH=src.

## What changed
- src/asset_forge/draw.py: ReferenceDrawer interface, UnavailableDrawer (default, TODO PR #11),
  MockDrawer (tests/screenshots). api.py: POST /api/expand (job on the GPU queue), POST
  /api/assets/from-text, POST /api/assets/{id}/draw (re-roll = call again); /api/menu has text_draw.
- prompts: optional seed = sampled re-roll (greedy has no variation). Idea writer is stopped
  (llm.stop) before every draw/3D job so its 4.2 GB VRAM is not held.
- web: textarea, Expand my idea, Try another version, reference shown in viewer, Draw a picture button,
  footer "Waiting for the graphics card..." while queued, spin hint hidden while working.
- tests/test_text_path.py (new, 13) + one updated test in test_app_api.py.

## Evidence so far
72 unit tests pass, ruff clean. Real Qwen run via the page: expand 29 s cold (incl. load), reroll 1.2 s warm. Shots in step1_text/ (real_* = faked 3D makers + real Qwen; mock_* = mock drawer draw/re-roll flow). TripoSG card is partly below the fold at 1366 (panel scrolls).

## Open decisions / flagged for lead
- With a picture AND words, the 3D run uses the picture only (generators take images); the words are
  not used. Say if the design wants otherwise.
- Expanded prompt contains the fixed view words ("T-pose", "plain white background") by design of the back end.

## Rules learnt the hard way
- GPU lock is often held by other agents; any app job (even a faked one) waits for it.

## Round 2 (critic + lead)
Fixed: box auto-grows to 5+ lines then scrolls, placeholder colour, Try another disabled while writing,
plain footer copy, 44 px small buttons, "Your picture builds the model; your words are kept as notes.",
both maker cards fit at 1366x768 (measured scroll 0). Re-shot real_* at both sizes. Left: lead walk-through.

## Round 3 (walk-through fixes, lead-approved)
Words-path note moved under the words box (shown after Expand or 3+ words, no picture); Redo hidden until a result; "Pick what it is first: Humanoid, Monster or Animal" beside Expand; "3. Choose how to build it". Footer no longer says "Press Draw a picture" when drawing is unavailable. Web-only change (web/app.js, index.html, style.css); no Python logic changed. Re-shot real_* both sizes with a fake idea writer (no GPU) + fake makers, via Playwright on Edge. Left: CI at new head, PR body evidence.
