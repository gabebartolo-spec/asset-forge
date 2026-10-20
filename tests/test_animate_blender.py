"""Step 4 in real headless Blender and Godot on the tiny box fixtures (rigged first by Step 3).
Local only (marker blender); skipped without the executables."""

from __future__ import annotations

import json
import shutil

import pytest
from test_skeleton_blender import BLENDER, FIX, GODOT, needs_blender, needs_godot

from asset_forge import skeleton
from asset_forge.animate import CLIP_NAMES, LOOPING, animate
from asset_forge.animate.check import check_animated_glb
from asset_forge.export import export_animated
from asset_forge.export.godot_check import LOOP_LINEAR, LOOP_NONE, check_import

pytestmark = pytest.mark.blender


def _animated(tmp_path_factory, name, fixture, kind):
    rig_dir = tmp_path_factory.mktemp(f"{name}_rig")
    skeleton.rig(FIX / fixture, rig_dir, kind, BLENDER)
    out = tmp_path_factory.mktemp(f"{name}_anim")
    return animate(rig_dir / "rigged.blend", out, BLENDER, kind)


@pytest.fixture(scope="module")
def man(tmp_path_factory):
    return _animated(tmp_path_factory, "man", "blockman.glb", "humanoid")


@pytest.fixture(scope="module")
def fox(tmp_path_factory):
    return _animated(tmp_path_factory, "fox", "blockfox.glb", "animal")


@needs_blender
@pytest.mark.parametrize("which", ["man", "fox"])
def test_the_six_clips_are_made_and_pass_their_checks(which, request):
    res = request.getfixturevalue(which)
    assert [c["name"] for c in res.clips] == list(CLIP_NAMES)
    assert res.template == ("humanoid" if which == "man" else "four_legged")
    rep = json.loads((res.out_dir / "clips.json").read_text(encoding="utf-8"))
    assert check_animated_glb(res.out_dir / "animated.glb", rep).problems == []
    assert (res.out_dir / "animated.blend").is_file()
    for name in ("walk", "run"):
        assert res.checks["slide_cm"][name] <= 2.0 * rep["leg_length_m"]  # 2% of the leg, in cm


@needs_blender
def test_the_person_walks_at_a_real_cadence(man):
    walk = next(c for c in man.clips if c["name"] == "walk")
    assert 100 <= walk["strides_per_s"] * 120 <= 120


@needs_blender
@needs_godot
@pytest.mark.parametrize("which", ["man", "fox"])
def test_export_passes_the_gate_and_godot_with_loops(which, request, tmp_path):
    res = request.getfixturevalue(which)
    kind = "humanoid" if which == "man" else "animal"
    dest, report = export_animated(res.out_dir, "a-test", kind, exports_dir=tmp_path)
    assert report["problems"] == []
    assert report["godot_import"].startswith("LOOP_CHECK_OK")
    assert {p.name for p in dest.iterdir()} >= {"a-test.glb", "a-test.glb.import",
                                                "a-test.blend", "a-test.clips.json"}


@needs_blender
@needs_godot
def test_without_the_sidecar_godot_imports_the_loops_as_play_once(man, tmp_path):
    glb = tmp_path / "bare.glb"
    shutil.copy2(man.out_dir / "animated.glb", glb)          # no bare.glb.import beside it
    loops = {n: LOOP_LINEAR if n in LOOPING else LOOP_NONE for n in CLIP_NAMES}
    res = check_import(glb, loops, exe=GODOT)
    assert not res.ok and any("walk" in p for p in res.problems), res.problems


@needs_blender
def test_the_person_ends_the_faint_lying_on_the_floor(man):
    rep = json.loads((man.out_dir / "clips.json").read_text(encoding="utf-8"))
    g = rep["grounding"]["faint"]
    assert abs(g["end_lowest_mm"]) <= 1.0                       # on the floor, not in or above it
    # the trunk touches the floor too: lying, not propped up on knees or hands
    assert g["end_torso_gap_mm"] <= 0.05 * rep["height_m"] * 1000, g
