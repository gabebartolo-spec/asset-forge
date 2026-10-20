"""Step 4 (Animate), pure Python: the six clips made from the skeleton alone, the gait speeds
(Froude number), loops, the IK, and the checks on the exported .glb (clip names, loop seams,
foot slide) with known-bad files. The Blender run itself is in test_animate_blender.py."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from anim_factory import (
    GAIT,
    LEG,
    clips_json,
    foot_track,
    paw_tips,
    write_anim_glb,
    write_paw_glb,
)
from test_skeleton import stick_bird, stick_fox, stick_human

from asset_forge.animate import AnimFailed, animate
from asset_forge.animate.body import FWD, UP, Body
from asset_forge.animate.check import (
    check_animated_glb,
    foot_joints,
    read_animations,
    seam_errors,
    world_positions,
)
from asset_forge.animate.clips import (
    CLIP_NAMES,
    FROUDE,
    HIND_SHIN_MAX_DEG,
    LOOPING,
    MAX_STRIDES_PER_S,
    G,
    animator,
    froude_speed,
    make_clips,
    max_strides_per_s,
    stride_length,
)
from asset_forge.animate.gait import foot_slide
from asset_forge.skeleton import fit

TRIPOSG_FOX = Path(__file__).parent / "fixtures" / "triposg_fox_skeleton.json"
STICKS = {"humanoid": stick_human, "four_legged": stick_fox, "bird": stick_bird}


def body(template: str, scale: float = 1.0) -> Body:
    rng = np.random.default_rng(7)  # pinned seed
    J = fit.fit(STICKS[template](rng), template)
    return Body.from_joints(template, {k: v * scale for k, v in J.items()})


@pytest.fixture(scope="module", params=list(STICKS))
def made(request):
    b = body(request.param)
    return b, {c.name: c for c in make_clips(b)}


# ------------------------------------------------------------------ foot-slide metric

def test_foot_slide_is_zero_for_a_planted_gait():
    s = foot_slide(foot_track("Left", 49), GAIT.fps, GAIT.speed, (0, 0, 1), (0, 1, 0), 0.005)
    assert s.contact_frames > 10
    assert s.worst_m < 1e-6 and s.ok(LEG)


def test_foot_slide_catches_a_foot_that_slides():
    # the ground runs at half the speed the foot is drawn at: the planted foot skids
    s = foot_slide(foot_track("Left", 49), GAIT.fps, GAIT.speed / 2, (0, 0, 1), (0, 1, 0), 0.005)
    assert s.worst_m > 0.02 * LEG and not s.ok(LEG)


# ------------------------------------------------------------------ the .glb checks

def test_a_good_animated_file_passes(tmp_path):
    r = check_animated_glb(write_anim_glb(tmp_path / "a.glb"), clips_json())
    assert r.problems == []
    assert set(r.seams) == set(LOOPING) and r.slide_cm["walk"] < 0.01


def test_a_file_missing_run_is_refused_in_plain_words(tmp_path):
    names = [n for n in CLIP_NAMES if n != "run"]
    r = check_animated_glb(write_anim_glb(tmp_path / "a.glb", names), clips_json(names=names))
    assert "The animation run is missing." in r.problems


def test_an_extra_or_misnamed_clip_is_refused(tmp_path):
    names = [*CLIP_NAMES[:-1], "Faint"]
    r = check_animated_glb(write_anim_glb(tmp_path / "a.glb", names), clips_json(names=names))
    assert any("faint is missing" in p for p in r.problems)
    assert any("Unexpected animation" in p and "Faint" in p for p in r.problems)


def test_sliding_feet_in_the_file_are_refused(tmp_path):
    r = check_animated_glb(write_anim_glb(tmp_path / "a.glb"), clips_json(GAIT.speed / 2))
    assert any(p.startswith("In walk, the Left foot slides") for p in r.problems), r.problems


@pytest.mark.parametrize("bad, words", [("pop", "jumps"), ("stall", "hitches"),
                                        ("rot_pop", "jumps")])
def test_a_broken_loop_seam_is_refused(tmp_path, bad, words):
    p = write_anim_glb(tmp_path / "a.glb", bad=bad)
    clip = "idle" if bad == "rot_pop" else "walk"
    r = check_animated_glb(p, clips_json())
    assert any(f"The {clip} loop {words}" in q for q in r.problems), r.problems


def test_seam_errors_measure_the_pop(tmp_path):
    a = read_animations(write_anim_glb(tmp_path / "a.glb", bad="pop"))
    _, pos, stalls = seam_errors(a, "walk")
    assert pos == pytest.approx(0.05, abs=1e-6) and stalls == 0
    assert seam_errors(read_animations(write_anim_glb(tmp_path / "b.glb")), "walk")[1] < 1e-6


def test_a_sway_turning_round_at_the_seam_is_not_a_hitch(tmp_path):
    # a sway with its turning point half a frame before the seam: the last step is tiny, as at
    # a hitch, but the motion reverses there, so the loop is smooth
    a = read_animations(write_anim_glb(tmp_path / "a.glb", bad="turn"))
    assert seam_errors(a, "idle")[2] == 0


def test_an_unreadable_file_is_plain_words(tmp_path):
    p = tmp_path / "junk.glb"
    p.write_bytes(b"nope")
    assert check_animated_glb(p, clips_json()).problems[0].startswith("The animated file could")


# ------------------------------------------------------------------ the clips themselves

def test_every_body_gets_the_six_clips_by_name(made):
    _, clips = made
    assert tuple(clips) == CLIP_NAMES == ("idle", "walk", "run", "attack", "hit", "faint")
    assert [n for n, c in clips.items() if c.loop] == list(LOOPING)


def test_loops_end_exactly_where_they_start(made):
    _, clips = made
    for name in LOOPING:
        d = clips[name].deltas
        for bone in d[0]:
            np.testing.assert_allclose(d[-1][bone], d[0][bone], atol=1e-9, err_msg=name)


def test_one_shot_clips_end_where_they_start(made):
    _, clips = made
    for name in ("attack", "hit"):
        d = clips[name].deltas
        for bone in d[0]:
            np.testing.assert_allclose(d[-1][bone], d[0][bone], atol=1e-6, err_msg=name)


def test_every_foot_reaches_its_target(made):
    _, clips = made
    for name in ("idle", "walk", "run", "attack", "hit"):
        assert clips[name].short == {}, name


def _ground_slide(b, clip, joint):
    tr = np.array([b.joint_positions(D)[joint] for D in clip.deltas])
    return foot_slide(tr, clip.fps, clip.speed, FWD, UP, 0.01 * b.leg_len)


def test_planted_feet_do_not_slide_on_the_ground(made):
    b, clips = made
    joints = foot_joints(b.template, [lg.name for lg in b.legs])
    for name in ("idle", "walk", "run", "attack", "hit"):
        for j in joints:
            s = _ground_slide(b, clips[name], j)
            assert s.contact_frames > 0, (name, j)
            assert s.worst_m <= 0.02 * b.leg_len, (name, j, s.worst_m)


def test_knees_bend_the_way_the_template_says(made):
    b, clips = made
    for lg in b.legs:
        pole = lg.pole / np.linalg.norm(lg.pole)
        for D in clips["walk"].deltas + clips["run"].deltas:
            P = b.joint_positions(D)
            ahead = (P[lg.lower] - (P[lg.upper] + P[lg.foot]) / 2) @ pole
            assert ahead > 0, (lg.name, ahead)
    if b.template == "humanoid":
        assert all(lg.pole @ FWD > 0 for lg in b.legs)  # a human knee never bends backwards


# ------------------------------------------------------------------ gait speed: Froude number

def test_walk_and_run_move_at_their_froude_number_unless_capped(made):
    b, clips = made
    for name in ("walk", "run"):
        c, g = clips[name], clips[name].gait
        v = froude_speed(FROUDE[name][b.template], b.leg_len)
        assert c.speed == pytest.approx(g.stroke / (g.duty * g.seconds))  # planted feet hold
        assert c.froude == pytest.approx(c.speed**2 / (G * b.leg_len))
        assert 1 / g.seconds <= max_strides_per_s(name, b.template) + 1e-9, name
        if not c.capped:                                   # exactly the Froude speed
            assert c.speed == pytest.approx(v), name
        else:                                              # slower, never faster
            assert c.speed < v, name


def test_froude_numbers_are_walk_a_quarter_and_run_between_one_and_two_and_a_half():
    for t in STICKS:  # people: a fifth, with L hip to ankle (1.37 m/s free walk, Perry 2010)
        assert FROUDE["walk"][t] == pytest.approx(0.20 if t == "humanoid" else 0.25)
        assert 1.0 <= FROUDE["run"][t] <= 2.5


def test_froude_speed_and_stride_formulas():
    assert froude_speed(0.25, 0.9) == pytest.approx(np.sqrt(0.25 * 9.81 * 0.9))
    assert stride_length(1.0, 1.0) == pytest.approx(2.3)


@pytest.mark.parametrize("template", list(STICKS))
def test_a_small_body_steps_fast_instead_of_shuffling(template):
    # the Froude law itself, on bodies big enough to stay under the readability cap
    k = 1.0 if template == "humanoid" else 16.0
    big, small = body(template, k), body(template, k / 2)
    for name in ("walk", "run"):
        a = getattr(animator(big), name)()
        b = getattr(animator(small), name)()
        assert b.speed == pytest.approx(a.speed / np.sqrt(2), rel=1e-6)   # v ~ sqrt(L)
        ratio = a.gait.seconds / b.gait.seconds                   # cadence ~ 1/sqrt(L)
        assert ratio == pytest.approx(np.sqrt(2), rel=0.2), (name, ratio)


def test_cadence_follows_the_stride_rule(made):
    b, clips = made
    for name in ("walk", "run"):
        fr = FROUDE[name][b.template]
        rule = froude_speed(fr, b.leg_len) / animator(b).stride(name)
        strides_per_s = 1 / clips[name].gait.seconds
        cap = max_strides_per_s(name, b.template)   # a fox walk: 1.3 (motion critic s7)
        if rule > cap:                       # a small animal: held at the readability cap
            assert 0.9 * cap <= strides_per_s <= cap
            continue
        # Animals and birds by Alexander (1976), people by their gait data (HUMAN_STRIDE): a
        # clip may step up to a quarter faster (a short reach) and a little slower (whole frames)
        assert rule * 0.85 <= strides_per_s <= rule * 1.25, (name, strides_per_s, rule)


def test_the_readability_cap_is_two_strides_a_second_walking_and_three_running():
    # lead decision 2026-10-20: a fox trot at 4.3 strides/s and a bird run at 6 strobe at game
    # scale; the stride stays within the leg's reach, so the capped gait simply moves slower
    assert MAX_STRIDES_PER_S == {"walk": 2.0, "run": 3.0}


@pytest.mark.parametrize("template", ["four_legged", "bird"])
def test_small_animals_step_no_faster_than_the_cap(template):
    b = body(template)   # fox and robin sized: their Froude cadence is well over the cap
    a = animator(b)
    for name in ("walk", "run"):
        c = getattr(a, name)()
        rule = froude_speed(FROUDE[name][template], b.leg_len) / a.stride(name)
        assert rule > MAX_STRIDES_PER_S[name], (name, rule)
        assert c.capped and c.gait.seconds >= 1 / max_strides_per_s(name, template) - 1e-9, name
        assert c.speed < froude_speed(FROUDE[name][template], b.leg_len)
        assert c.short == {}


def _hind_lean_near_ground(b, clip) -> float:
    """Most a hind lower leg (stifle to paw) leans from vertical while its paw is within half
    the swing lift of the ground: low and flat is a leg dragging along the ground."""
    worst = 0.0
    for D in clip.deltas:
        P = b.joint_positions(D)
        for lg in b.legs:
            if lg.group != "Hind" or P[lg.foot][2] - lg.ground_z >= 0.5 * clip.gait.lift:
                continue
            u = P[lg.foot] - P[lg.lower]
            worst = max(worst, float(np.degrees(np.arccos(-u[2] / np.linalg.norm(u)))))
    return worst


@pytest.mark.parametrize("rig", ["stick", "triposg_fox"])
def test_a_hind_leg_never_lies_flat_along_the_ground(rig):
    # the triposg fox's hind lower leg lay flat behind it (near the ground: walk 52, run 61
    # degrees) because the stroke reached far behind the hip with the stifle forward
    if rig == "stick":
        b = body("four_legged")
    else:
        b = Body.from_skeleton_report(json.loads(TRIPOSG_FOX.read_text(encoding="utf-8")))
    a = animator(b)
    assert HIND_SHIN_MAX_DEG == 45.0
    for name in ("walk", "run"):
        c = getattr(a, name)()
        assert _hind_lean_near_ground(b, c) <= HIND_SHIN_MAX_DEG + 1e-6, name
        assert c.short == {}


def test_a_run_stride_has_enough_keys_to_see_the_steps(made):
    _, clips = made
    assert clips["run"].gait.frames >= 8


# ------------------------------------------------------------------ the wrapper

def test_monsters_get_plain_words_not_yet(tmp_path):
    with pytest.raises(AnimFailed, match="later version"):
        animate(tmp_path / "rigged.blend", tmp_path, "blender.exe", "monster")


def test_no_skeleton_says_what_to_click(tmp_path):
    with pytest.raises(AnimFailed, match="step 3"):
        animate(tmp_path / "rigged.blend", tmp_path, "blender.exe", "animal")


# ------------------------------------------------------------------ real gait data
# Adults walking freely (Perry and Burnfield, Gait Analysis, 2nd ed. 2010): cadence about 113
# steps/min, stride 1.41 m, 1.37 m/s, so a stride is about 0.8 of standing height. Recreational
# runners at 3-4 m/s: about 155-180 steps/min (Cavanagh and Kram 1989).

def _steps_per_min(clip) -> float:
    return 2 * 60 / clip.gait.seconds   # two steps per stride


def _hip_drop(b, clip) -> float:
    return max(-float(p.move["Hips"][2]) for p in clip.poses) / b.leg_len


def test_a_person_walks_at_a_real_cadence_and_stride():
    b = body("humanoid")
    walk = animator(b).walk()
    assert 100 <= _steps_per_min(walk) <= 120, _steps_per_min(walk)
    stride = walk.speed * walk.gait.seconds
    assert 0.7 <= stride / b.height <= 0.85, stride / b.height
    assert 1.1 <= walk.speed <= 1.5, walk.speed
    assert _hip_drop(b, walk) <= 0.08, _hip_drop(b, walk)   # no deep crouch


def test_a_person_runs_at_a_real_cadence():
    b = body("humanoid")
    run = animator(b).run()
    assert 150 <= _steps_per_min(run) <= 180, _steps_per_min(run)


# ------------------------------------------------------------------ the person's one-shots

def _track(b, clip, joint) -> np.ndarray:
    return np.array([b.joint_positions(D)[joint] for D in clip.deltas])


def test_the_attack_is_a_swipe_across_the_body_not_a_reach():
    b = body("humanoid")
    a = animator(b).attack()
    hand = _track(b, a, "RightHand.tail")
    shoulder = _track(b, a, "RightUpperArm")
    hips = _track(b, a, "Hips")
    wind = int(np.argmax(hand[:, 1] - shoulder[:, 1]))    # the hand furthest back
    # wound up: the hand behind the shoulder and well above it
    assert hand[wind, 1] > shoulder[wind, 1] and hand[wind, 2] > shoulder[wind, 2] + 0.05 * b.height
    # then it sweeps across: from the right of the body (x < 0) to the left of the middle
    after = hand[wind:]
    assert hand[wind, 0] < 0 and after[:, 0].max() > 0.05 * b.height
    # fast: the strike's top speed is at least three times the wind-up's
    v = np.linalg.norm(np.diff(hand, axis=0), axis=1) * a.fps
    assert v[wind:].max() >= 3 * v[:wind].max(), (v[wind:].max(), v[:wind].max())
    # the hips lunge forward into it (forward is -Y) and come back
    assert (hips[0, 1] - hips[:, 1].min()) >= 0.1 * b.leg_len
    np.testing.assert_allclose(hips[-1], hips[0], atol=1e-6)


def test_a_hit_knocks_the_torso_and_head_back_then_settles():
    b = body("humanoid")
    h = animator(b).hit()
    head = _track(b, h, "Head")
    chest = _track(b, h, "UpperChest")
    back = head[:, 1] - head[0, 1]                         # + is backwards
    peak = int(np.argmax(back))
    assert back[peak] >= 0.08 * b.height, back[peak]
    # the torso itself tips back, not only the head
    lean0 = head[0] - chest[0]
    leanp = head[peak] - chest[peak]
    tilt = np.degrees(np.arctan2(leanp[1], leanp[2]) - np.arctan2(lean0[1], lean0[2]))
    assert tilt >= 15.0, tilt
    assert peak < len(head) // 2                           # quick to recoil, slower to settle
    np.testing.assert_allclose(head[-1], head[0], atol=1e-6)


@pytest.mark.parametrize("template", list(STICKS))
def test_every_clip_starts_at_the_idle_root_position(template):
    b = body(template)
    a = animator(b)
    start = b.joint_positions(a.idle().deltas[0])["Hips"]
    for name in ("attack", "hit", "faint"):
        hips = b.joint_positions(getattr(a, name)().deltas[0])["Hips"]
        np.testing.assert_allclose(hips[:2], start[:2], atol=1e-3 * b.height)  # in place
        assert abs(hips[2] - start[2]) <= 0.01 * b.height, (name, hips, start)


def test_the_faint_ends_lying_flat_with_straight_legs():
    b = body("humanoid")
    f = animator(b).faint()
    P = b.joint_positions(f.deltas[-1])
    lo = min(p[2] for p in P.values())
    trunk = np.array([P[n] for n in ("Hips", "Spine", "Chest", "UpperChest", "Neck")])
    # the trunk lies low and level, not propped up on knees or hands
    assert trunk[:, 2].max() - lo <= 0.1 * b.height, trunk[:, 2].max() - lo
    assert np.ptp(trunk[:, 2]) <= 0.05 * b.height
    # stretched out at full length along the ground
    ys = np.array([P[n][1] for n in ("Head.tail", "LeftToes.tail", "RightToes.tail")])
    assert np.ptp(ys) >= 0.85 * b.height, np.ptp(ys)
    for lg in b.legs:                                      # legs straight, knees not bent up
        u, v = P[lg.lower] - P[lg.upper], P[lg.foot] - P[lg.lower]
        bend = np.degrees(np.arccos(u @ v / np.linalg.norm(u) / np.linalg.norm(v)))
        assert bend <= 15.0, (lg.name, bend)


# ------------------------------------------------------------------ weight, follow-through, timing
# Director 2026-10-20, "Fix first" on person walk, fox walk, bird walk, person attack and person
# faint: the motion lacked weight, secondary motion and timing (lead's motion critic s7).

def _P(b, clip) -> list[dict]:
    return [b.joint_positions(D) for D in clip.deltas]


def _arr(P, joint) -> np.ndarray:
    return np.array([p[joint] for p in P])


def _deg(u, v) -> np.ndarray:
    """Angle in degrees between matching rows of u and v."""
    c = np.sum(u * v, axis=1) / np.linalg.norm(u, axis=1) / np.linalg.norm(v, axis=1)
    return np.degrees(np.arccos(np.clip(c, -1.0, 1.0)))


def _line_yaw(P, left, right) -> np.ndarray:
    d = _arr(P, left) - _arr(P, right)
    return np.degrees(np.unwrap(np.arctan2(d[:, 1], d[:, 0])))


def _lag(lead, follow, most) -> int:
    """Frames by which `follow` trails `lead` in a loop (best circular match)."""
    a, b = lead - lead.mean(), follow - follow.mean()
    return max(range(most + 1), key=lambda k: float(a @ np.roll(b, -k)))


@pytest.mark.parametrize("name", ["walk", "run"])
def test_a_person_swings_each_arm_against_its_own_leg(name):
    b = body("humanoid")
    c = getattr(animator(b), name)()
    P = _P(b, c)[:-1]                                      # one cycle
    hips = _arr(P, "Hips")
    for side in ("Left", "Right"):
        sh, el, wr = (_arr(P, f"{side}{j}") for j in ("UpperArm", "LowerArm", "Hand"))
        u, v = el - sh, wr - el
        swing = np.degrees(np.arctan2(u @ FWD, -u[:, 2]))  # upper arm forward of hanging down
        assert np.ptp(swing) / 2 >= (25 if name == "walk" else 32), (side, np.ptp(swing) / 2)
        hand, foot = (wr - sh) @ FWD, (_arr(P, f"{side}Foot") - hips) @ FWD
        assert np.corrcoef(hand, foot)[0, 1] <= -0.8           # the arm swings against its leg
        flex = _deg(u, v)                                       # the elbow bends as it swings on
        assert np.ptp(flex) >= 15, (side, np.ptp(flex))
        assert np.corrcoef(flex, swing)[0, 1] >= 0.7


@pytest.mark.parametrize("name", ["walk", "run"])
def test_a_person_turns_the_shoulders_against_the_pelvis(name):
    b = body("humanoid")
    c = getattr(animator(b), name)()
    P = _P(b, c)[:-1]
    pelvis = _line_yaw(P, "LeftUpperLeg", "RightUpperLeg")
    shoulders = _line_yaw(P, "LeftUpperArm", "RightUpperArm")
    assert np.ptp(pelvis) / 2 >= 3.0, np.ptp(pelvis) / 2
    assert np.ptp(shoulders) / 2 >= 6.0, np.ptp(shoulders) / 2
    assert np.corrcoef(pelvis, shoulders)[0, 1] <= -0.8
    # the shoulders follow the pelvis round a couple of frames late (not locked to it)
    assert 1 <= _lag(-pelvis, shoulders, len(P) // 4) <= 4


def test_a_person_walks_tall_and_bobs_lowest_at_heel_strike():
    b = body("humanoid")
    w = animator(b).walk()
    n, duty = w.gait.frames, w.gait.duty
    z = _arr(_P(b, w)[:-1], "Hips")[:, 2]

    def near(f, targets):
        return min(min(abs(f - t) % n, n - abs(f - t) % n) for t in targets) <= 0.1 * n

    strikes, mids = (0, n // 2), (round(duty / 2 * n), round(duty / 2 * n + n / 2) % n)
    assert near(int(np.argmin(z)), strikes), (int(np.argmin(z)), strikes)
    assert near(int(np.argmax(z)), mids), (int(np.argmax(z)), mids)
    assert np.ptp(z) >= 0.03 * b.leg_len, np.ptp(z) / b.leg_len
    # the stance knee is nearly straight at mid-stance: a walk, not a crouched sneak
    P = _P(b, w)[mids[0]]
    lg = b.leg("Left")
    knee = _deg((P[lg.lower] - P[lg.upper])[None], (P[lg.foot] - P[lg.lower])[None])[0]
    assert knee <= 12.0, knee


@pytest.mark.parametrize("name", ["walk", "run"])
def test_a_small_bird_hops_with_both_feet_together(name):
    b = body("bird")                                       # robin sized
    c = getattr(animator(b), name)()
    P = _P(b, c)
    left, right = _arr(P, "LeftFoot"), _arr(P, "RightFoot")
    zl, zr = left[:, 2] - left[:, 2].min(), right[:, 2] - right[:, 2].min()
    np.testing.assert_allclose(zl, zr, atol=1e-3 * b.leg_len)          # up together
    gap = (left - right) @ FWD
    np.testing.assert_allclose(gap, gap[0], atol=1e-3 * b.leg_len)     # side by side
    air = zl > 0.05 * b.leg_len
    assert air.any() and (~air).any()
    hips = _arr(P, "Hips")[:, 2]
    assert np.ptp(hips) >= 0.2 * b.leg_len, np.ptp(hips) / b.leg_len   # the body arcs
    assert hips[air].max() > hips[0] + 0.1 * b.leg_len
    for j in ("LeftFoot", "RightFoot"):                                 # and lands planted
        assert _ground_slide(b, c, j).worst_m <= 0.02 * b.leg_len


def test_a_large_bird_walks_one_foot_after_the_other():
    b = body("bird", 4.0)                                  # half a metre tall
    c = animator(b).walk()
    P = _P(b, c)
    zl, zr = _arr(P, "LeftFoot")[:, 2], _arr(P, "RightFoot")[:, 2]
    assert np.abs(zl - zr).max() >= 0.05 * b.leg_len
    assert c.short == {}


def test_a_bird_flicks_its_tail_up_as_it_lands():
    b = body("bird")
    c = animator(b).walk()
    n = c.gait.frames
    up = []
    for D in c.deltas[:-1]:
        P = b.joint_positions(D)
        v = D["Hips"][:3, :3].T @ (P["Tail1.tail"] - P["Tail1"])
        up.append(np.degrees(np.arctan2(v[2], abs(v[1]))))
    up = np.array(up)
    assert np.ptp(up) >= 12.0, np.ptp(up)
    peak = int(np.argmax(up))                               # landing is frame 0
    assert peak <= 0.15 * c.fps or peak >= n - 1, (peak, n)


def test_a_fox_walks_with_a_bending_spine_and_lifted_forepaws():
    b = body("four_legged")
    w = animator(b).walk()
    P = _P(b, w)[:-1]
    pelvis = _line_yaw(P, "HindLeftUpperLeg", "HindRightUpperLeg")
    shoulders = _line_yaw(P, "FrontLeftUpperLeg", "FrontRightUpperLeg")
    assert np.ptp(shoulders - pelvis) / 2 >= 6.0, np.ptp(shoulders - pelvis) / 2  # not a plank
    paw = _arr(P, "FrontLeftFoot")
    assert np.ptp(paw[:, 2]) >= 0.16 * b.leg_len, np.ptp(paw[:, 2]) / b.leg_len
    rest = b.tail["FrontLeftFoot"] - b.head["FrontLeftFoot"]
    curl = _deg(_arr(P, "FrontLeftFoot.tail") - paw, np.tile(rest, (len(P), 1)))
    assert curl.max() >= 60.0, curl.max()                   # the forepaw folds as it swings
    assert 1 / w.gait.seconds <= 1.35, 1 / w.gait.seconds    # an unhurried walk
    tail = _line_yaw(P, "Tail4.tail", "Tail4") - pelvis
    assert np.ptp(tail) / 2 >= 10.0, np.ptp(tail) / 2       # the tail swings, not a stick


def _ang_speed(clip, bone) -> np.ndarray:
    R = [D[bone][:3, :3] for D in clip.deltas]
    return np.array([np.degrees(np.arccos(np.clip((np.trace(R[i + 1] @ R[i].T) - 1) / 2, -1, 1)))
                     for i in range(len(R) - 1)]) * clip.fps


def test_the_attack_drives_from_the_hips_out_to_the_hand():
    a = animator(body("humanoid")).attack()
    pk = {n: int(np.argmax(_ang_speed(a, n))) for n in ("Hips", "Chest", "RightUpperArm")}
    assert pk["Hips"] < pk["Chest"] < pk["RightUpperArm"], pk


def test_the_attack_winds_up_holds_then_strikes_hard():
    b = body("humanoid")
    a = animator(b).attack()
    P = _P(b, a)
    hand = _arr(P, "RightHand.tail")
    v = np.linalg.norm(np.diff(hand, axis=0), axis=1) * a.fps
    pk = int(np.argmax(v))
    lo = max(0, pk - int(0.3 * a.fps))
    still = v[lo:pk] < 0.15 * v[pk]                                   # a held wind-up...
    best, run = 0, 0
    for s in still:
        run = run + 1 if s else 0
        best = max(best, run)
    assert best >= 2, still
    last_still = lo + int(np.flatnonzero(still).max())
    assert (pk - last_still) / a.fps <= 0.1, (pk, last_still)        # ...then fast into it
    lg = b.leg("Left")
    knee = _deg(_arr(P, lg.lower) - _arr(P, lg.upper), _arr(P, lg.foot) - _arr(P, lg.lower))
    assert knee[pk:].max() >= 15.0, knee[pk:].max()                   # the front knee gives
    heel = _arr(P, "RightFoot")[:, 2] - _arr(P, "RightFoot")[0, 2]
    assert heel.max() >= 0.012 * b.height, heel.max() / b.height       # the back heel lifts


def test_a_hit_snaps_the_chest_first_then_the_head_and_arms():
    h = animator(body("humanoid")).hit()
    pk = {n: int(np.argmax(_ang_speed(h, n))) for n in ("Chest", "Head", "LeftUpperArm")}
    assert pk["Chest"] < pk["Head"] and pk["Chest"] < pk["LeftUpperArm"], pk


def test_a_person_faints_knees_first_then_the_torso_then_the_head():
    b = body("humanoid")
    f = animator(b).faint()
    P = _P(b, f)
    lg = b.leg("Left")
    knee = _deg(_arr(P, lg.lower) - _arr(P, lg.upper), _arr(P, lg.foot) - _arr(P, lg.lower))
    pelvis = _arr(P, "Spine") - _arr(P, "Hips")
    chest = _arr(P, "Neck") - _arr(P, "Chest")
    head = _arr(P, "Head.tail") - _arr(P, "Head")
    fold, nod = _deg(pelvis, chest), _deg(chest, head)

    def onset(x, thr):
        return int(np.argmax(x - x[0] >= thr))

    k = f.fps / 30
    assert onset(knee, 20) + 3 * k <= onset(fold, 10), (onset(knee, 20), onset(fold, 10))
    assert onset(fold, 10) < onset(nod, 10), (onset(fold, 10), onset(nod, 10))


@pytest.mark.parametrize("template", list(STICKS))
def test_a_faint_falls_faster_and_faster_then_stops_dead(template):
    b = body(template)
    f = animator(b).faint()
    z = np.array([np.mean([p[2] for p in P.values()]) for P in _P(b, f)])
    v = -np.diff(z) * f.fps                                  # falling speed of the body's centre
    pk = int(np.argmax(v))
    k = f.fps / 30
    assert abs(pk + 1 - f.land_frame) <= k, (pk + 1, f.land_frame)  # fastest just as it lands
    start = int(np.argmax(v > 0.1 * v[pk]))
    early = v[start:start + max(1, (pk - start) // 3)].mean()
    assert early <= 0.5 * v[pk], (early, v[pk])              # slow to start: gravity
    assert abs(v[pk + 1]) <= 0.35 * v[pk], (v[pk + 1], v[pk])  # a hard stop on the floor


@pytest.mark.parametrize("template", list(STICKS))
def test_nothing_moves_once_the_faint_has_settled(template):
    b = body(template)
    f = animator(b).faint()
    P = _P(b, f)
    settle = f.land_frame + int(round(0.15 * f.fps))         # landing, bounce and arm splay
    assert len(P) - settle >= 0.4 * f.fps                    # then it lies still a while
    for p in P[settle:]:
        worst = max(float(np.linalg.norm(p[j] - P[settle][j])) for j in p)
        assert worst <= 0.002 * b.height, worst / b.height


# ------------------------------------------------------------------ on the Step 3 fit's feet (#22)

def test_a_paw_that_turns_about_its_planted_tip_does_not_slide(tmp_path):
    # the ankle swings forward 13 mm (over the 10 mm limit) as the pad peels off; the tip stays
    glb = write_paw_glb(tmp_path / "paw.glb")
    rep = {**clips_json(speed=0.0), "foot_tips": paw_tips()}
    assert check_animated_glb(glb, rep).problems == []
    tracked = world_positions(read_animations(glb), "idle", ["LeftFoot.tail"], 30, paw_tips())
    assert np.ptp(tracked[:, 0], axis=0).max() < 1e-6       # the tip really is still
    # a file whose clips.json does not say where the tips are falls back to the ankle
    without = check_animated_glb(glb, clips_json(speed=0.0)).problems
    assert any("slides" in p for p in without), without


def test_toes_and_paws_never_dip_below_where_they_stand_in_the_swing(made):
    b, clips = made
    for name in ("walk", "run"):
        P = _P(b, clips[name])
        for lg in b.legs:
            tip = f"{lg.foot}.tail" if b.template != "humanoid" else f"{lg.name}Toes.tail"
            z = _arr(P, tip)[:, 2]
            stand = np.median(z[z <= z.min() + 0.01 * b.leg_len])
            assert z.min() >= stand - 0.005 * b.leg_len, (name, lg.name, stand - z.min())


def test_a_person_lifts_the_heel_about_the_ball_with_the_toes_flat():
    b = body("humanoid")
    w = animator(b).walk()
    P = _P(b, w)[:-1]
    g = w.gait
    for lg in b.legs:
        ball, tip = _arr(P, f"{lg.name}Toes"), _arr(P, f"{lg.name}Toes.tail")
        lifted = [f for f in range(g.frames)
                  if g.foot(lg.name, f)[2] and g.roll(lg.name, f) > 0.5]  # heel well up
        assert lifted
        for f in lifted:  # the ball and the toe tip both stay down on the ground
            assert ball[f, 2] - ball[:, 2].min() <= 0.01 * b.leg_len, (lg.name, f)
            assert tip[f, 2] - tip[:, 2].min() <= 0.01 * b.leg_len, (lg.name, f)


def test_the_fainted_body_lies_on_the_floor_and_nothing_goes_through_it():
    b = body("humanoid")
    f = animator(b).faint()
    P = _P(b, f)
    for i, p in enumerate(P):  # the root bone carries no mesh
        low = min(v[2] for k, v in p.items() if not k.startswith("Root"))
        assert low >= -0.005 * b.height, (i, low)
    trunk = [P[-1][n][2] for n in ("Hips", "Spine", "Chest", "UpperChest", "Neck")]
    assert max(trunk) <= 0.08 * b.height, max(trunk) / b.height  # lying, not floating
    feet = [P[-1][f"{lg.name}Toes.tail"][2] for lg in b.legs]
    assert max(feet) <= 0.02 * b.height, feet                       # toes resting on the floor
