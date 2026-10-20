# Handoff: animation (anim-b4 round 3, motion "Fix first"), updated 2026-10-20
State: stood down at the context guard (221k) mid-task. Local WIP commit on claude/animation
(on top of 350dcf2), NOT pushed. PR #20 is ready (not draft); a push re-runs CI. Do not merge.
Worktree: C:/Users/DANTE/Documents/GitHub/asset-forge-wt/animation (own .venv). gpu.lock:
C:/Users/DANTE/Documents/GitHub/asset-forge/models/gpu.lock. Rigs (six): ../asset-forge/models/skeleton_out/<gen>/<body>/.
Evidence folder: C:/Users/DANTE/AppData/Roaming/Claude/side-session-notes/32c9f533-fe4e-47ae-b55b-70ec62248734/animation/
Scratch (old code for failing-first runs): %TEMP%/claude/C--Users-DANTE-Documents-GitHub-asset-forge--claude-worktrees-session-context-optimization-b3f75f/f1b204c2-5c54-4f23-a732-130a57d70b7c/scratchpad/headsrc/src
  (PYTHONPATH=$(cygpath -w <that>) .venv/Scripts/python.exe -m pytest tests/test_animate.py); rigs.py there prints rig sizes.

## Brief (lead, 2026-10-20)
Apply every fix in C:/Users/DANTE/AppData/Roaming/Claude/side-session-notes/local_7fdc3e78-46c6-48b7-9439-a48ba40b7296/motion_critic_s7.md
to all six rigs and every clip it applies to (run, idle, hit get weight/secondary/chain too).
Structural: (a) hop gait for small birds; (b) per-bone time offsets (kinetic chain) for attack,
hit, faint; (c) faint as a gravity collapse (knees first, accelerating fall, hard stop, small
bounce, no drift). Keep foot slide, loop seams, Godot loop check, export gate green. New unit
tests shown failing on old code first. Evidence: tools/animate/previews.py --export for all six
rigs under gpu.lock -> GIFs (same names) in <evidence>/previews_v4/, constant framing (one
ortho scale per rig for every clip). View own strips at 2x; lead runs the critic. Update PR #20
body (round 3 section, Not exercised); unit + ruff + pytest -m blender (animate tests); commit by
file name; push once at the end. Rewrite this handoff before reporting.

## Done (WIP commit)
- curves.py: Keys(shape=[...]) per-segment timing shapes smooth/in/in3/out/lin; Keys.shifted;
  Chain(keys, lags, start) = per-group time offsets (start=2 keeps wind-up shared, lags strike).
- gait.py: HOP phases, Gait.lifts (per-leg lift), lift_of, swinging(); flight property (unused,
  delete if still unused).
- clips.py rewritten: WALK_REACH 0.995 (old stance knee at mid-stance was 48 deg), bob dip,
  hip joints by FK (hip_joints) for the reach need, swing_pitch(s, lg); person walk/run upper
  (pelvis +-4/chest +-7 two frames late, arms 28/35 deg 4 frames late, elbow 20-40, pelvis list
  4 + spine counter, weight shift 0.03L, head steady +-1); idle weight shift with lags; attack
  (hold 0.30-0.38, "in" strike 0.05 s, overshoot, back heel lift, deeper lunge, Chain start=2);
  hit (Chain chest 0/hips 1F/head 2F/arms 3F, "out" impact); faint (reel + right foot step back,
  knees buckle "in", fall in3 to 90 at 0.67 s = f20, bounce 87 over 0.08 s, arm splay, all
  settled by land+0.15 s, hold to 1.30 s). Fox: spine counter-turn from leg positions, roll,
  nod 6 gaze level, tail 1 frame/segment + lift +-10, forepaw curl 70 + lift 0.20L, walk cap
  ANIMAL_WALK_STRIDES_PER_S 1.3, bite/hit chains. Bird: HOP_MAX_HEIGHT 0.3 m (all six rigs and
  the stick bird hop; >0.3 m walks with uneven Right phase 7/16, roll 5); hop = dip (landing
  give), rise (arc 0.30L/0.40L), tuck, tail flick 15 at landing, wings lift, head hold-and-thrust
  (_head_hold). Animal/bird faint = _side_faint (sink "in", tip in3, land 0.70 s, bounce).
- tests/test_animate.py: 20 new tests (end of file). On old code 19 fail, the large-bird guard
  passes: <evidence>/unit_failing_first_v4.txt (names + reasons).
- ruff clean on animate + test file.

## Done since (anim-b4 fresh life, uncommitted on top of 5a87bdd)
- Unit green: tests/test_animate.py 79 passed; + test_animate_api, test_export_animated: 97 passed.
  Fixes: test reads clips.max_strides_per_s (fox walk 1.3); hop has roll=0 (both feet flat);
  body.py STAND_REACH humanoid 0.995 (0.96 floated feet 3 cm = bent stance knee, the "sneak");
  walk drop = bob + cover(need - bob) (cover lifted the mid-stance low point); bob 0.05L;
  run: shoulders 1 frame late, arms on pelvis timing (walk 2 and 2 frames); bird walk Right
  lands 1 whole frame early (gait_clip early_right) instead of 7/16; attack chain lags
  hips 0 / spine .5 / chest 1 / arm 1.5 / head, larm 2 frames (longer smeared the strike);
  hit neck/arms lag in the world (counter the torso, follow it 2-3 frames late).
- blender/animate.py render_previews: all boxes first, one ortho scale per rig, idle centre.

## Left (in order)
1. DONE (see above). Was: Make the unit suite green. Last run: 9 failed, 70 passed. Diagnoses (not yet verified):
   - test_cadence_follows_the_stride_rule[four_legged]: test still uses MAX_STRIDES_PER_S; use
     clips.max_strides_per_s(name, template) (fox walk cap 1.3 from critic B5).
   - test_a_small_body_steps_fast[bird] (ratio 1.0): k=16 bird walks with Right phase 7/16 so
     _quantum = 16 frames; both sizes round to the same n. Use an even-q uneven phase or loosen.
   - swipe test: strike top speed 15.3 vs wind-up 6.5 (needs 3x): wind-up now faster/longer
     or `wind` index moved by the arm lag; check where argmax(hand back) lands.
   - arm swing [run]: hand-vs-foot corr -0.02: 4-frame arm lag on a 22-frame run cycle is ~65
     deg of phase; use smaller lags for the run (or lag as a phase fraction) and re-measure.
   - bob ptp 0.026L < 0.03L: raise the bob (0.04L -> 0.05L) or shorten the cover radius.
   - hop (both): zl vs zr not equal (line ~489); print c.short and per-frame foot z: likely
     one side out of reach (hip lean/rotation) or heel roll; fix so both feet are identical.
   - attack hold: still frames end 5 frames before peak (needs <= 3): chest/hips lead moves the
     hand early; shrink lags (hips 0, chest 1F, arm 2F) or start the chain later.
   - hit: all peaks at frame 0 because the test reads WORLD angular speed (head inherits the
     chest). Measure each bone relative to its parent (D_parent^-1 D) in the test, or whip more.
2. Old tests must stay green (slide, seams, reach, knees, Froude, faint flat, start at idle root).
3. DONE. blender/animate.py render_previews: one shared ortho scale for all clips of a rig (compute
   every clip's box first, idle anchor), so the figure is the same size in every GIF.
4. pytest -m blender tests/test_animate_blender.py under gpu.lock (scratch locked_pytest.py of
   the old scratch dir, or wrap with gpu_lock), Godot loop check included.
5. previews.py --export on ../asset-forge/models/skeleton_out -> <evidence>/previews_v4/ +
   previews_v4.txt; check loop seams; look at own strips at 2x (crops only).
6. PR #20 body: round 3 section (fixes, numbers, failing-first file, previews_v4 path), Not
   exercised (large-bird walk only on a scaled stick bird; "less even cadence" only for that
   walk; person walk may stay slightly mechanical, no mocap compare). Board/log lines for the
   lead: fox walk cap 1.3/s (critic B5), HOP_MAX_HEIGHT 0.3 m (builder pick, lead to confirm).
7. Commit by file name, push once, report to lead (<= 8 lines).
