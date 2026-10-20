"""Step 4 (Animate), pure Python: the six clips made from the skeleton alone, the gait speeds
(Froude number), loops, the IK, and the checks on the exported .glb (clip names, loop seams,
foot slide) with known-bad files. The Blender run itself is in test_animate_blender.py."""

from __future__ import annotations

import numpy as np
import pytest
from anim_factory import GAIT, LEG, clips_json, foot_track, write_anim_glb
from test_skeleton import stick_bird, stick_fox, stick_human

from asset_forge.animate import AnimFailed, animate
from asset_forge.animate.body import FWD, UP, Body
from asset_forge.animate.check import (
    check_animated_glb,
    foot_joints,
    read_animations,
    seam_errors,
)
from asset_forge.animate.clips import (
    CLIP_NAMES,
    FROUDE,
    LOOPING,
    G,
    animator,
    froude_speed,
    make_clips,
    stride_length,
)
from asset_forge.animate.gait import foot_slide
from asset_forge.skeleton import fit

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

def test_walk_and_run_move_at_their_froude_number(made):
    b, clips = made
    for name in ("walk", "run"):
        c = clips[name]
        assert c.speed == pytest.approx(froude_speed(FROUDE[name][b.template], b.leg_len))
        assert c.speed**2 / (G * b.leg_len) == pytest.approx(FROUDE[name][b.template])
        assert c.froude == pytest.approx(FROUDE[name][b.template])


def test_froude_numbers_are_walk_a_quarter_and_run_between_one_and_two_and_a_half():
    for t in STICKS:
        assert FROUDE["walk"][t] == pytest.approx(0.25)
        assert 1.0 <= FROUDE["run"][t] <= 2.5


def test_froude_speed_and_stride_formulas():
    assert froude_speed(0.25, 0.9) == pytest.approx(np.sqrt(0.25 * 9.81 * 0.9))
    assert stride_length(1.0, 1.0) == pytest.approx(2.3)


@pytest.mark.parametrize("template", list(STICKS))
def test_a_small_body_steps_fast_instead_of_shuffling(template):
    big, small = body(template), body(template, 0.5)
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
        alexander = froude_speed(fr, b.leg_len) / stride_length(fr, b.leg_len)
        strides_per_s = 1 / clips[name].gait.seconds
        assert alexander * 0.8 <= strides_per_s <= alexander * 1.6, (name, strides_per_s)


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
