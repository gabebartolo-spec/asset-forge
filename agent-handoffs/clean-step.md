# Handoff: clean-step (PR #9, builder round 3), 2026-10-20
State: round-3 pushed (head-to-head registration + fox fixes); waiting on CI and the lead's fresh fidelity check.
Done in blender/clean.py:
- Head-to-head (humanoid/monster only): ref head = highest compact mass of the silhouette (smoothed top
  contour); model head = centre of top 8% of the mesh. Head rows (top 18%, fade to 34%) of the picture are
  shifted so the two meet. Independent gate: darkest facial features of the picture vs the model's most
  forward blob after the shift; > 0.25 head width => head low-frequency, no face (HEAD_AGREE).
  report.json colour_route.registration.head_to_head. hi3dgen brute gates out (0.387), triposg brute paints
  (0.20), humanoids/spiders shift ~0 (0.00-0.01) and pass.
- Foxes: pale sources x2.5 in fill (animals only; x5 whitened humanoid steel and legs), fill specks dropped
  (SPECK_SCALE 8), texels not facing the camera limited to 0.10 luma from the fill, mirrored points that land
  > 2% height off the surface give no specks (turned head => the extra eye spot is gone; robin keeps 2 eyes).
- Tests: tests/test_clean_colour.py::test_face_is_registered_head_to_head_when_the_outline_is_centred
  (fixture mode headoff). Fails on the c00428c script (red-green 0.017), passes now; 6 colour tests pass.
- Sheets regenerated (docs/audits/clean), Godot import check 10/10 IMPORT_CHECK_OK.
Open: hi3dgen fox front legs pink-grey (ref black); triposg fox chest smooth pale grey, not white faceted;
 cue B (face features) is my call and is noisy on three-quarter faces.
Scratch: scratchpad/one.py cand prompt [--sheets] runs one model.
