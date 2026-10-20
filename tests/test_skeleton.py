"""Step 3 (Skeleton), pure Python: templates, the fit, the weight limit, the .glb gate, the
rig() wrapper with Blender mocked. The Blender run itself is in test_skeleton_blender.py."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np
import pytest
from glb_factory import write_cube_glb
from skin_factory import write_skinned_glb

from asset_forge import skeleton
from asset_forge.skeleton import fit, weights
from asset_forge.skeleton.glb import read_skin
from asset_forge.skeleton.pose import TEST_POSES
from asset_forge.skeleton.templates import MAX_BONES, TEMPLATES, joint_names

# SkeletonProfileHumanoid names (Godot 4.x) the humanoid template must use, spelled out so a
# rename in the template fails here.
GODOT_HUMANOID = {
    "Hips", "Spine", "Chest", "UpperChest", "Neck", "Head", "Root",
    *(f"{s}{b}" for s in ("Left", "Right") for b in (
        "Shoulder", "UpperArm", "LowerArm", "Hand", "UpperLeg", "LowerLeg", "Foot", "Toes")),
}


def _cloud(rng, centre, size, n=400):
    return np.asarray(centre) + (rng.random((n, 3)) - 0.5) * np.asarray(size)


def stick_human(rng, height=1.8):
    """Hand-built body: legs, torso, head, A-pose arms, feet pointing -Y."""
    H = height
    parts = [
        _cloud(rng, (0.09 * H, 0.0, 0.27 * H), (0.07 * H, 0.08 * H, 0.54 * H)),
        _cloud(rng, (-0.09 * H, 0.0, 0.27 * H), (0.07 * H, 0.08 * H, 0.54 * H)),
        _cloud(rng, (0.09 * H, -0.04 * H, 0.015 * H), (0.07 * H, 0.16 * H, 0.03 * H)),
        _cloud(rng, (-0.09 * H, -0.04 * H, 0.015 * H), (0.07 * H, 0.16 * H, 0.03 * H)),
        _cloud(rng, (0, 0, 0.67 * H), (0.30 * H, 0.14 * H, 0.30 * H), 800),
        _cloud(rng, (0, 0, 0.93 * H), (0.12 * H, 0.14 * H, 0.14 * H)),
        _cloud(rng, (0, 0, 0.84 * H), (0.06 * H, 0.06 * H, 0.04 * H)),
    ]
    for sgn in (1, -1):  # arms hang away from the body, hands at 0.45 H
        for t in np.linspace(0, 1, 12):
            x = sgn * (0.24 + 0.1 * t) * H
            parts.append(_cloud(rng, (x, 0, (0.75 - 0.30 * t) * H), (0.05 * H,) * 3, 40))
    v = np.vstack(parts)
    v[:, 2] -= v[:, 2].min()
    return v


def stick_fox(rng, yaw=0.0):
    """Body along Y, head at -Y, four legs, a tail trailing to +Y. yaw turns it in the plane."""
    parts = [_cloud(rng, (0, 0, 0.28), (0.12, 0.35, 0.16), 600),
             _cloud(rng, (0, -0.24, 0.33), (0.08, 0.12, 0.10)),
             _cloud(rng, (0, 0.30, 0.22), (0.05, 0.28, 0.05))]
    for x in (0.045, -0.045):
        for y in (-0.12, 0.12):
            parts.append(_cloud(rng, (x, y, 0.1), (0.03, 0.04, 0.2), 120))
    v = np.vstack(parts)
    c, s = np.cos(yaw), np.sin(yaw)
    v[:, :2] = v[:, :2] @ np.array([[c, s], [-s, c]])
    v[:, 2] -= v[:, 2].min()
    return v


def stick_bird(rng):
    parts = [_cloud(rng, (0, 0, 0.09), (0.05, 0.1, 0.09), 600),
             _cloud(rng, (0, -0.05, 0.125), (0.03, 0.03, 0.03)),
             _cloud(rng, (0, 0.07, 0.08), (0.02, 0.06, 0.005), 100)]
    for x in (0.01, -0.01):
        parts.append(_cloud(rng, (x, 0.0, 0.025), (0.003, 0.003, 0.05), 80))
        parts.append(_cloud(rng, (x, -0.01, 0.002), (0.003, 0.03, 0.003), 40))
    v = np.vstack(parts)
    v[:, 2] -= v[:, 2].min()
    return v


# ------------------------------------------------------------------ templates

@pytest.mark.parametrize("name", list(TEMPLATES))
def test_template_is_a_valid_tree_within_the_bone_limit(name):
    bones = TEMPLATES[name]
    names = [b.name for b in bones]
    assert len(names) == len(set(names)) and len(names) <= MAX_BONES
    assert [b.name for b in bones if b.parent is None] == ["Root"]
    for b in bones:
        assert b.parent is None or b.parent in names
        assert b.tail in joint_names(name)


def test_humanoid_uses_godot_profile_names():
    assert {b.name for b in TEMPLATES["humanoid"]} == GODOT_HUMANOID


def test_every_test_pose_names_real_bones():
    for name, pose in TEST_POSES.items():
        names = {b.name for b in TEMPLATES[name]}
        assert pose and all(bone in names and axis in "XYZ" for bone, axis, _ in pose)


# ------------------------------------------------------------------ fit

def test_humanoid_fit_puts_joints_where_a_body_has_them():
    v = stick_human(np.random.default_rng(1))
    H = v[:, 2].max()
    J = fit.fit(v, "humanoid")
    assert set(J) == set(joint_names("humanoid"))
    assert J["Hips"][2] == pytest.approx(0.52 * H, rel=0.05)
    assert J["Head"][2] > J["Neck"][2] > J["UpperChest"][2] > J["Hips"][2]
    for s, side in ((1, "Left"), (-1, "Right")):  # the characters left is +X
        assert s * J[f"{side}UpperArm"][0] > 0.05 * H
        assert J[f"{side}Hand"][2] < J[f"{side}UpperArm"][2]
        assert 0.35 * H < J[f"{side}Hand"][2] < 0.6 * H  # the arm cloud ends at about 0.45 H
        assert s * J[f"{side}UpperLeg"][0] > 0
        assert J[f"{side}Foot"][2] < J[f"{side}LowerLeg"][2] < J[f"{side}UpperLeg"][2]
        assert J[f"{side}ToesTip"][1] < J[f"{side}Foot"][1]  # toes point to -Y


@pytest.mark.parametrize("yaw", [0.0, 0.5, -0.4])
def test_four_legged_fit_follows_the_body_not_the_axes(yaw):
    v = stick_fox(np.random.default_rng(2), yaw)
    assert fit.choose_animal_template(v) == "four_legged"
    J = fit.fit(v, "four_legged")
    fwd = J["HeadTip"] - J["Hips"]
    assert fwd[1] < 0  # the head end is towards -Y
    assert np.linalg.norm(fwd[:2]) > 0.3
    # the tail runs away from the head, the legs stand under the body
    assert (J["TailTip"] - J["Hips"])[:2] @ fwd[:2] < 0
    for leg in ("FrontLeft", "FrontRight", "HindLeft", "HindRight"):
        assert J[f"{leg}Foot"][2] < J[f"{leg}LowerLeg"][2] < J[f"{leg}UpperLeg"][2]
    assert J["FrontLeftFoot"][:2] @ fwd[:2] > J["HindLeftFoot"][:2] @ fwd[:2]


def test_two_legs_on_the_ground_choose_the_bird_template():
    bird = stick_bird(np.random.default_rng(3))
    assert fit.count_leg_columns(bird) == 2
    assert fit.choose_animal_template(bird) == "bird"
    J = fit.fit(bird, "bird")
    assert set(J) == set(joint_names("bird"))
    assert J["Head"][2] > J["Hips"][2]
    assert J["LeftFoot"][2] < 0.02 and J["RightFoot"][2] < 0.02


def test_humanoid_foot_has_ankle_ball_and_toe_tip_along_the_foot():
    """A real foot: ankle a quarter of the way from the heel, ball of the foot about 72% of the
    way, toe tip at the front. The old fit put the ball straight under the ankle."""
    v = stick_human(np.random.default_rng(1))
    H = v[:, 2].max()
    heel, toe = 0.04 * H, -0.12 * H  # the stick feet run from y = +0.04 H to -0.12 H
    flen = heel - toe
    J = fit.fit(v, "humanoid")
    for side in ("Left", "Right"):
        ankle, ball, tip = J[f"{side}Foot"], J[f"{side}Toes"], J[f"{side}ToesTip"]
        assert heel - ankle[1] == pytest.approx(0.25 * flen, abs=0.06 * flen)
        assert heel - ball[1] == pytest.approx(0.72 * flen, abs=0.06 * flen)
        assert tip[1] == pytest.approx(toe, abs=0.04 * flen)
        assert ball[1] - tip[1] > 0.15 * flen  # the toes are a real segment, not a stub
        assert tip[2] <= ball[2] < ankle[2]
    pivots = fit.foot_pivots(v, "humanoid")
    assert pivots["LeftHeel"][1] == pytest.approx(heel, abs=0.04 * flen)
    assert pivots["LeftHeel"][2] == pytest.approx(0.0, abs=0.01 * H)


def turned_head_fox(rng, yaw=0.0):
    """A fox looking to its left (head and neck swung to +X), long paws pointing forward
    (-Y): the shape that tilted the whole-mesh axis of the generated fox by 18 degrees."""
    parts = [_cloud(rng, (0, 0, 0.28), (0.12, 0.40, 0.16), 900),
             _cloud(rng, (0.10, -0.22, 0.36), (0.16, 0.08, 0.10), 400),
             _cloud(rng, (0.20, -0.24, 0.36), (0.10, 0.06, 0.06), 200),
             _cloud(rng, (-0.02, 0.36, 0.20), (0.05, 0.28, 0.05))]
    for x in (0.045, -0.045):
        for y in (-0.14, 0.14):
            parts.append(_cloud(rng, (x, y, 0.11), (0.03, 0.03, 0.2), 120))
            parts.append(_cloud(rng, (x, y - 0.04, 0.008), (0.03, 0.10, 0.016), 120))
    v = np.vstack(parts)
    c, s = np.cos(yaw), np.sin(yaw)
    v[:, :2] = v[:, :2] @ np.array([[c, s], [-s, c]])
    v[:, 2] -= v[:, 2].min()
    return v


def _deg(a, b):
    a, b = np.asarray(a[:2], float), np.asarray(b[:2], float)
    return float(np.degrees(np.arccos(np.clip(a @ b / np.linalg.norm(a) / np.linalg.norm(b),
                                              -1, 1))))


@pytest.mark.parametrize("yaw", [0.0, 0.5])
def test_four_legged_body_axis_ignores_a_turned_head(yaw):
    v = turned_head_fox(np.random.default_rng(4), yaw)
    fwd = np.array([np.sin(yaw), -np.cos(yaw)])
    J = fit.fit(v, "four_legged")
    # facing -Y (what Clean hands over) the body axis is exact; turned 29 degrees it follows
    # the body to within 5 (the whole-mesh axis was 11 off)
    assert _deg(J["Chest"] - J["Hips"], fwd) < (0.5 if yaw == 0 else 5.0)
    left = np.array([-fwd[1], fwd[0]])
    for part in ("Front", "Hind"):  # left legs on the left, front legs ahead of hind
        assert (J[f"{part}LeftFoot"] - J[f"{part}RightFoot"])[:2] @ left > 0.05
    assert (J["FrontLeftFoot"] - J["HindLeftFoot"])[:2] @ fwd > 0.2


def test_four_legged_paw_runs_from_behind_the_ankle_to_the_toe_front():
    v = turned_head_fox(np.random.default_rng(4))
    J = fit.fit(v, "four_legged")
    for part, y_leg in (("Front", -0.14), ("Hind", 0.14)):
        for side in ("Left", "Right"):
            ankle, tip = J[f"{part}{side}Foot"], J[f"{part}{side}FootTip"]
            assert tip[1] == pytest.approx(y_leg - 0.09, abs=0.015)  # paw front at y - 0.09
            assert ankle[1] - tip[1] > 0.06  # the paw is about 0.10 long
            assert tip[2] < ankle[2]


def _segment(rng, p0, p1, size=0.025, n=80):
    t = rng.random((n, 1))
    p0, p1 = np.asarray(p0), np.asarray(p1)
    return p0 + t * (p1 - p0) + (rng.random((n, 3)) - 0.5) * size


def bent_leg_fox(rng):
    """A fox whose hind legs bend back at the hock (y = 0.19, z = 0.10), like the generated
    foxes: paw forward, cannon bone up and back to the hock, shin forward up to the body."""
    parts = [_cloud(rng, (0, 0, 0.28), (0.12, 0.40, 0.16), 900),
             _cloud(rng, (0, -0.24, 0.33), (0.08, 0.12, 0.10)),
             _cloud(rng, (0, 0.36, 0.22), (0.05, 0.28, 0.05))]
    for x in (0.045, -0.045):
        parts.append(_cloud(rng, (x, -0.14, 0.11), (0.03, 0.03, 0.2), 120))
        parts.append(_cloud(rng, (x, -0.18, 0.008), (0.03, 0.10, 0.016), 120))
        parts.append(_cloud(rng, (x, 0.10, 0.008), (0.03, 0.10, 0.016), 120))
        parts.append(_segment(rng, (x, 0.13, 0.02), (x, 0.19, 0.10)))
        parts.append(_segment(rng, (x, 0.19, 0.10), (x, 0.12, 0.21)))
    v = np.vstack(parts)
    v[:, 2] -= v[:, 2].min()
    return v


def test_four_legged_hind_knee_joint_sits_in_the_hock():
    """The hind leg's middle joint goes where the leg bends back (the hock), inside the leg;
    the old fit put it ahead of the leg, in the air."""
    v = bent_leg_fox(np.random.default_rng(5))
    J = fit.fit(v, "four_legged")
    for side in ("Left", "Right"):
        hock = J[f"Hind{side}LowerLeg"]
        assert hock[1] == pytest.approx(0.19, abs=0.02)
        assert hock[2] == pytest.approx(0.10, abs=0.02)


def test_bird_ankle_sits_over_the_leg_and_the_toe_tip_at_the_toes():
    J = fit.fit(stick_bird(np.random.default_rng(3)), "bird")
    for side in ("Left", "Right"):
        assert J[f"{side}Foot"][1] == pytest.approx(0.0, abs=0.003)  # the leg column, y = 0
        assert J[f"{side}FootTip"][1] == pytest.approx(-0.025, abs=0.003)  # toes reach -0.025


def test_bird_lifted_foot_keeps_its_joints_in_the_foot():
    v = stick_bird(np.random.default_rng(3))
    v[(v[:, 0] < -0.005) & (v[:, 2] < 0.05), 2] += 0.015  # right foot raised 15 mm
    J = fit.fit(v, "bird")
    assert J["RightFootTip"][2] == pytest.approx(J["LeftFootTip"][2] + 0.015, abs=0.003)
    assert J["RightFoot"][2] == pytest.approx(J["LeftFoot"][2] + 0.015, abs=0.003)


# ------------------------------------------------------------------ weights

def test_limit_keeps_four_strongest_and_renormalises():
    w = np.random.default_rng(4).random((50, 9))
    assert weights.influence_counts(w).max() == 9  # the known-bad input
    out = weights.limit_influences(w)
    assert weights.influence_counts(out).max() == 4
    assert np.allclose(out.sum(axis=1), 1.0)
    keep = np.argsort(w, axis=1)[:, -4:]
    assert all(set(np.nonzero(out[i])[0]) == set(keep[i]) for i in range(50))


def test_distance_fallback_weights_every_vertex_with_at_most_four_bones():
    v = stick_human(np.random.default_rng(5))
    J = fit.fit(v, "humanoid")
    bones = [b for b in TEMPLATES["humanoid"] if b.name != "Root"]
    heads = np.array([J[b.name] for b in bones])
    tails = np.array([J[b.tail] for b in bones])
    w = weights.distance_weights(v, heads, tails)
    assert w.shape == (len(v), len(bones))
    assert np.allclose(w.sum(axis=1), 1.0)
    assert weights.influence_counts(w).max() <= 4
    names = [b.name for b in bones]
    left_hand = int(np.argmax(np.where(v[:, 2] < 0.6 * v[:, 2].max(), v[:, 0], -9)))
    assert names[int(np.argmax(w[left_hand]))].startswith("Left")
    foot = int(np.argmin(v[:, 2]))
    assert any(k in names[int(np.argmax(w[foot]))] for k in ("Leg", "Foot", "Toes"))


# ------------------------------------------------------------------ the .glb gate

def test_gate_passes_a_four_influence_rig(tmp_path):
    glb = write_skinned_glb(tmp_path / "ok.glb", bones=5, influences=4)
    skin = read_skin(glb)
    assert (skin.bones, skin.max_influences, skin.unweighted_vertices) == (5, 4, 0)
    assert skeleton.check_rig_glb(glb) == []


def test_gate_fails_more_than_four_influences_per_vertex(tmp_path):
    glb = write_skinned_glb(tmp_path / "bad.glb", bones=8, influences=8)
    assert read_skin(glb).max_influences == 8
    problems = skeleton.check_rig_glb(glb)
    assert any("8 bones at once" in p and "limit is 4" in p for p in problems)


def test_gate_fails_five_influences_too(tmp_path):
    problems = skeleton.check_rig_glb(write_skinned_glb(tmp_path / "five.glb", 6, 5))
    assert problems and "5 bones at once" in problems[0]


def test_gate_fails_over_64_bones_and_a_model_with_no_skeleton(tmp_path):
    many = skeleton.check_rig_glb(write_skinned_glb(tmp_path / "many.glb", 65, 4))
    assert any("65 bones" in p for p in many)
    assert skeleton.check_rig_glb(write_cube_glb(tmp_path / "cube.glb")) == [
        "The model has no skeleton."]


def test_gate_reports_an_unreadable_file_in_plain_words(tmp_path):
    f = tmp_path / "junk.glb"
    f.write_bytes(b"not a glb at all")
    assert skeleton.check_rig_glb(f)[0].startswith("The rigged file could not be read")


# ------------------------------------------------------------------ rig() with Blender mocked

def _fake_blender(influences=4, rc=0, report=True):
    def run(cmd, **kw):
        out = Path(cmd[cmd.index("--") + 2])
        write_skinned_glb(out / "rigged.glb", 5, influences)
        if report:
            (out / "skeleton.json").write_text(json.dumps({
                "template": "humanoid", "bones": 5, "seconds": 1.2,
                "weights": {"method": "blender_automatic", "max_influences": influences,
                            "problems": []}}))
        return subprocess.CompletedProcess(cmd, rc, stdout="RIG_OK {}", stderr="")
    return run


@pytest.fixture
def clean_glb(tmp_path):
    exe = tmp_path / "blender.exe"
    exe.write_bytes(b"")
    return write_cube_glb(tmp_path / "clean.glb"), str(exe)


def test_rig_runs_blender_and_returns_the_result(tmp_path, clean_glb, monkeypatch):
    glb, exe = clean_glb
    monkeypatch.setattr(subprocess, "run", _fake_blender())
    res = skeleton.rig(glb, tmp_path / "out", "humanoid", exe)
    assert (res.template, res.bones, res.weights_method) == ("humanoid", 5, "blender_automatic")
    assert res.public()["max_influences"] == 4


def test_rig_command_names_the_script_type_and_template():
    cmd = skeleton.rig_command("blender", Path("repo"), Path("c.glb"), Path("o"), "animal", "bird")
    assert cmd[:3] == ["blender", "-b", "--factory-startup"]
    assert cmd[cmd.index("-P") + 1].endswith("rig.py")
    assert cmd[-4:] == ["--type", "animal", "--template", "bird"]


def test_rig_refuses_a_rig_that_breaks_the_influence_limit(tmp_path, clean_glb, monkeypatch):
    glb, exe = clean_glb
    monkeypatch.setattr(subprocess, "run", _fake_blender(influences=8))
    with pytest.raises(skeleton.RigFailed, match="at once"):
        skeleton.rig(glb, tmp_path / "out", "humanoid", exe)


@pytest.mark.parametrize("kind", ["blender_crash", "no_report"])
def test_rig_failure_is_plain_words(tmp_path, clean_glb, monkeypatch, kind):
    glb, exe = clean_glb
    monkeypatch.setattr(subprocess, "run", _fake_blender(
        rc=1 if kind == "blender_crash" else 0, report=kind != "no_report"))
    with pytest.raises(skeleton.RigFailed, match="Press Redo"):
        skeleton.rig(glb, tmp_path / "out", "humanoid", exe)


def test_rig_says_what_to_click_for_each_missing_piece(tmp_path, clean_glb):
    glb, exe = clean_glb
    with pytest.raises(skeleton.RigFailed, match="Run Clean up first"):
        skeleton.rig(tmp_path / "none.glb", tmp_path / "o", "humanoid", exe)
    with pytest.raises(skeleton.RigFailed, match="config.local.toml"):
        skeleton.rig(glb, tmp_path / "o", "humanoid", "")
    with pytest.raises(skeleton.RigFailed, match="Monsters"):
        skeleton.rig(glb, tmp_path / "o", "monster", exe)
