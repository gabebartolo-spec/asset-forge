"""A humanoid's clips come from the hand-made library (Quaternius, CC0), re-targeted."""

import numpy as np
import pytest
from test_animate import body

from asset_forge.animate import library
from asset_forge.animate.clips import CLIP_NAMES, LOOPING, make_clips
from asset_forge.animate.gait import foot_slide


@pytest.fixture(scope="module")
def made():
    b = body("humanoid")
    return b, {c.name: c for c in make_clips(b)}


def test_a_humanoid_gets_all_six_clips_from_the_library(made):
    _, clips = made
    assert list(clips) == list(CLIP_NAMES)
    assert all(c.library for c in clips.values())


def test_the_library_is_cc0_and_names_its_source():
    lib = library.load()
    assert "CC0" in lib["source"] and lib["url"].startswith("https://")


def test_other_bodies_stay_procedural():
    for t in ("four_legged", "bird"):
        assert not any(c.library for c in make_clips(body(t)))


def test_the_procedural_humanoid_is_still_there_to_fall_back_on():
    assert not any(c.library for c in make_clips(body("humanoid"), library=False))


@pytest.mark.parametrize("name", LOOPING)
def test_loops_end_on_their_first_frame(made, name):
    _, clips = made
    c = clips[name]
    for bone, Da in c.deltas[0].items():
        assert np.allclose(Da, c.deltas[-1][bone], atol=1e-9)


def test_every_frame_is_a_clean_solve(made):
    _, clips = made
    for c in clips.values():
        assert sum(c.short.values()) <= 4  # a leg may just fail to reach in a run's flight
        for D in c.deltas:
            for M in D.values():
                assert np.isfinite(M).all()
                assert np.allclose(M[:3, :3] @ M[:3, :3].T, np.eye(3), atol=1e-6)  # no shear


@pytest.mark.parametrize("name", ["walk", "run"])
def test_planted_feet_do_not_slide(made, name):
    b, clips = made
    c = clips[name]
    assert c.speed > 0.3
    for side in ("Left", "Right"):
        tr = np.array([b.joint_positions(D)[f"{side}Toes"] for D in c.deltas])
        s = foot_slide(tr, c.fps, c.speed, (0.0, -1.0, 0.0), (0.0, 0.0, 1.0), 0.01 * b.leg_len)
        assert s.contact_frames > 0
        assert s.worst_m <= 0.02 * b.leg_len


def test_the_walk_speed_follows_the_leg_length():
    small, big = body("humanoid", 0.5), body("humanoid", 1.0)
    v_small = {c.name: c.speed for c in make_clips(small)}["walk"]
    v_big = {c.name: c.speed for c in make_clips(big)}["walk"]
    assert 0.4 < v_small / v_big < 0.6


def test_the_faint_lands_and_stays_down(made):
    b, clips = made
    c = clips["faint"]
    assert c.land_frame is not None and 0 < c.land_frame < c.frames - 1
    hips = [b.joint_positions(D)["Hips"][2] for D in c.deltas]
    assert hips[0] > 0.45 * b.height and min(hips) < 0.2 * b.height  # up, then down on the ground
    assert max(hips[c.land_frame:]) - min(hips[c.land_frame:]) < 0.12 * b.height  # then still


def test_the_retarget_keeps_each_bone_pointing_where_the_source_points():
    """Fed the library's own rest pose a bone points where the library's bone points."""
    b = body("humanoid")
    lib = library.load()
    fix = library.rest_correction(b, lib)
    for info in lib["bones"].values():
        d_t = b.tail[info["ours"]] - b.head[info["ours"]]
        d_t = d_t / np.linalg.norm(d_t)
        assert np.allclose(fix[info["ours"]] @ np.array(info["dir"]), d_t, atol=1e-6)
