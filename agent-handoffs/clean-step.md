# Handoff: clean-step (PR #9, builder round 4), 2026-10-20
State: round-4 pushed (measured fox gates + speck-by-size fill); waiting on CI and the lead's fresh critic.
Method change (fox colour failed 3 tuning rounds): colour is now a MEASURED GATE in blender/clean.py
(REGION_GATES, region_gate_checks, report.json colour_route.region_gates). Reference regions (chest, flank,
tail body, tail tip, legs; boxes in the outline's own normalised coordinates) vs the saved albedo texels
mapped into the same boxes by the same registration. tests/test_clean_fox_gates.py (local, blender marker):
failed on 16e0339 (commit 1 of the push), passes now, both foxes.
Fix that meets them (heuristics removed: PALE_BOOST, SPECK_CAP, SPECK_SCALE/DARK/WHITE, diffusion specks):
- ref_specks: dark/white CONNECTED COMPONENTS under 0.25% of the silhouette = specks (eye, nose);
  never seed the fill, painted only where fully facing and snapped (no cap: socks/chest project as is).
- neutral (white/grey) fill field from the brightest sources, used where most nearby sources are neutral.
- bleed: picture colours grown 24 px past its outline (animals) - fixed black legs, thin tail tip.
- tail zone (end of the body away from the head): edge-on vertices trusted 0.5, edge-on texels painted,
  far side with no mirror image copies the picture at its own place (no specks).
Known: far-side shoulder/neck can carry a white ruff patch (mirrored cheek, head turned) on both foxes;
 tail-tip gate is presence only (0.15 x ref); tail body gate 0.15.
Tried and dropped: edge-on trust on the whole animal (bird chests blocky, backs streaked).
Scratch: scratchpad/one.py cand prompt [--sheets] (CLEAN=path overrides script), abl.sh.
