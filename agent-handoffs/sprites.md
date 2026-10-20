# Sprites handoff, 2026-10-20 (round 3: back views by turnaround sheet)
## State (b4): merged main, trim_spurs added in post.finish (66 tests pass); final 3x2 run DONE: 0 of 6 passed (report.json there; raw sheets in <subject>/raw); PR body + push + CI left -> evidence in AppData/Roaming/Claude/side-session-notes/local_d40f4221-.../sprites3 (local_f6b2f763 folder does not exist); then PR body, push, CI
## Task (lead brief)
1 draw front+back together as one SDXL turnaround sheet, split, post-process with shared palette; measure on lizard/bird/fox
2 gates that FAIL: (a) no face on the back, (b) pair anatomy match; pair failing both = tell user + re-roll, never export
3 clean-ups: ground fringe under lizard SC feet, 1-px stray tips at beak/toes
4 sizes in ONE preset table; D-023 (director): Southern Cross art 80 px, export 2x = 160 for front AND back, UPPERCASE names; GBA unchanged; PR body "D-023 to log"
Done = pushed, CI green, PR body (Evidence, Not exercised), shots in side-session-notes/local_f6b2f763.../sprites3/

## Done locally (uncommitted)
- presets.py: SC art_size 80, front_scale 2, back_scale 2 (D-023). pipeline.export_pair: name.upper().
- pairqa.py (new): face gate (face_features, face_colours, eye pairs, back head matching front face colours) and anatomy gate (limb blobs, ground contacts, stance, foot span).
- sheet.py (new): split_sheet cuts a sheet into per-creature crops (8 px cells, join 2 cells, min height 0.42).
- draw.py: SHEET prompt, draw_sheet (1344x768), draw_front, draw_back (inpaint experiment); old img2img back removed.
- pipeline.py: make_pair now draws sheets (3 per call, 2 calls), picks first front/back pair passing every gate; pair_problems; pair_preview.
- tests/fixtures/sprites/r2_*.png: the 8 round-2 sprites (known-bad backs) for the gate tests.
## Findings
- Sheet 1344x768: SDXL draws rows of 3-10 views (front, 3/4, side, back), not 2. Yield of a gate-passing pair: 1 of 18 sheets (fox/lizard/bird x 6 seeds, run_a). Bird sheets draw tiny figures (<0.42 of height).
- Inpaint-right-strip variant (front pasted left, back painted right, strength .99): returned BLANK background in 4 of 4 tries (lizard), abandoned.
- Gate (a) on round-2 bad backs: all 4 fail (lizard SC/GBA by eye pair or face colours, bird SC/GBA by beak/eye colours). Gate (b): lizard SC (limb blobs 1 vs 3), lizard GBA (contacts 3 vs 1, stance) fail; bird pairs pass (b) but fail (a).
- post.py: _ground_fringe peels 2 layers of dull pixels on the bottom edge (checked on the round-2 lizard SC raw: ragged teal fringe gone under the feet; not yet re-run end to end).
- Sheet variant V2 (1216x704, negative 'side view, three views, small'): 0 of 18 sheets gave a passing pair; V1 (1344x768): 1 of 18 (fox seed 6). Views per sheet 2-5. Both bounded; stop searching, report.
- Tests: 65 pass locally (sprites dir); test_pair_gates.py shows gates failing on the 4 round-2 pairs.
## Left
- NOT DONE: trim 1-px spurs at beak/toes (post.finish, before add_outline); real end-to-end runs 3 subjects x 2 presets with the final pipeline (cache sheets per subject, run both presets), shots in sprites3/ (1x, 6x grid, pair); pair time; PR body (Evidence, Not exercised, Board and log: D-023 to log); CI green.
- Open question for lead: yield is ~3-6 percent of sheets, so make_pair mostly fails after 6 sheets (re-roll message works). Decide: accept, or allow more sheets/another method.
## (old list)
tests (rework FakeDrawer to draw_sheet), clean-ups (fringe, stray tips), real runs x2 presets x3 subjects, PR body, CI.
## Rules learnt
- Write scripts with Write tool; never ruff format outside sprites dirs; GPU jobs through tools/bakeoff/gpu_lock.py run.
