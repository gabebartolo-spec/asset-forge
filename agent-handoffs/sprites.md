# Sprites handoff, 2026-10-20 (round 2: art-QA fixes)
## State: final GPU runs, then push
## Task
Fix PR #11 (sprite mode A) against the art-QA verdict: shadow, accents, pinholes, one palette per pair,
speckle, back drawn from front, same-creature gate, speed (pair under 60 s), 3/4 front.
## What changed (src/asset_forge/sprites/)
- post.py: enclosed shadow removal (same grey as a proven open shadow); shared_palette / reduce_palette_shared
  (median cut + 3 reserved accent slots by area x saturation x error); fill_holes 4-connected; clean_speckle
  (isolated interior pixels join a 4-neighbour; outline/edge never; accent colours of <=4 px kept);
  prepare()/finish() split so a pair gets ONE palette.
- qa.py: check_same_creature (colour hist distance <=0.65, aspect x1/1.6..1.6, mass x0.5..2),
  check_front_faces_viewer (mirror IoU >=0.55; profile 0.38, facing 0.7-0.95), holes 4-connected,
  enclosed gaps >=40 px allowed as drawn gaps (lead: say if that policy is wrong).
- draw.py/pipeline.py: draw_batch; back = img2img from a BLURRED front (blur 20, strength 0.9, 20 steps)
  because plain img2img copies the face; back batch of 3, first passing wins.
- tests/sprites/test_fixes.py: 14 new tests; 52 sprite tests pass; ruff clean.
## Evidence
Real runs in C:\Users\DANTE\AppData\Roaming\Claude\side-session-notes\local_d40f4221-0337-4df7-aee9-69379fac41e2\sprites2\
## Findings for the lead
- Local Southern Cross pack (Documents/GitHub/pokemon-southern-cross/game): Graphics/Pokemon/Front|Back
  confirmed; names UPPERCASE (ABRA.png); Front 160 (654 files) or 192 px (180); ALL Back files 160x160.
  Our Back export is 288 (96x3): mismatch.
- Grid detect found=False on the new fronts (pitch 8 holds ~0.71 of edge energy, limit 0.80); the fallback
  pitch 8 is the true pitch.
## Rules learnt the hard way
- Long heredocs with quotes in the Bash tool fail; write scripts with the Write tool.
- Never `ruff format src` (touches other files); format only src/asset_forge/sprites and tests/sprites.
