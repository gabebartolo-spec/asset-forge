"""Step 3 in real headless Blender (and Godot) on the tiny box fixtures. Local only (marker
blender); skipped without the executables. Fixtures: tests/fixtures/blockman.glb, blockfox.glb
(made by tools/skeleton/make_fixtures.py)."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest

from asset_forge import skeleton
from asset_forge.export.godot_check import check_rig, godot_exe
from asset_forge.skeleton.glb import read_skin
from asset_forge.skeleton.templates import TEMPLATES

pytestmark = pytest.mark.blender
FIX = Path(__file__).parent / "fixtures"
CFG = Path(__file__).resolve().parents[1] / "config.local.toml"
BLENDER = (tomllib.loads(CFG.read_text(encoding="utf-8")).get("blender", {}).get("exe", "")
           if CFG.is_file() else "")
GODOT = godot_exe()
needs_blender = pytest.mark.skipif(not BLENDER or not Path(BLENDER).is_file(),
                                   reason="no Blender in config.local.toml")
needs_godot = pytest.mark.skipif(GODOT is None or not GODOT.is_file(), reason="no Godot in config")


@pytest.fixture(scope="module")
def man(tmp_path_factory):
    out = tmp_path_factory.mktemp("man")
    return skeleton.rig(FIX / "blockman.glb", out, "humanoid", BLENDER)


@pytest.fixture(scope="module")
def fox(tmp_path_factory):
    out = tmp_path_factory.mktemp("fox")
    return skeleton.rig(FIX / "blockfox.glb", out, "animal", BLENDER)


@needs_blender
def test_humanoid_rig_has_the_template_bones_and_obeys_the_limits(man):
    assert man.template == "humanoid" and man.bones == len(TEMPLATES["humanoid"]) == 23
    assert man.max_influences <= 4
    skin = read_skin(man.out_dir / "rigged.glb")
    assert (skin.bones, skin.unweighted_vertices) == (23, 0) and skin.max_influences <= 4
    rep = json.loads((man.out_dir / "skeleton.json").read_text())
    # boxes that overlap defeat bone heat, so this fixture also proves the fallback path works
    assert rep["weights"]["method"] in ("blender_automatic", "distance_fallback")
    assert rep["weights"]["bones_with_weight"] == rep["weights"]["deform_bones"]


@needs_blender
def test_animal_rig_picks_the_four_legged_template(fox):
    assert fox.template == "four_legged" and fox.bones == 23
    assert skeleton.check_rig_glb(fox.out_dir / "rigged.glb") == []


@needs_blender
def test_test_pose_file_and_sheet_are_written(man):
    for name in ("rigged.glb", "test_pose.glb", "rigged.blend", "skeleton.json",
                 "pose_front_clay.png", "pose_top_colour.png"):
        assert (man.out_dir / name).stat().st_size > 0, name


@needs_blender
def test_forced_fallback_weights_still_obey_the_limit(tmp_path):
    import subprocess

    out = tmp_path / "fb"
    cmd = skeleton.rig_command(BLENDER, Path(__file__).resolve().parents[1],
                               FIX / "blockman.glb", out, "humanoid") + [
        "--force-fallback", "--no-sheets"]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    assert "RIG_OK" in proc.stdout
    rep = json.loads((out / "skeleton.json").read_text())
    assert rep["weights"]["method"] == "distance_fallback"
    assert skeleton.check_rig_glb(out / "rigged.glb") == []


@needs_blender
@needs_godot
def test_godot_maps_every_required_humanoid_profile_bone(man):
    r = check_rig(man.out_dir / "rigged.glb", GODOT, humanoid=True)
    assert r.ok, r.problems
    assert "required_missing=[]" in r.summary and "filled=23" in r.summary
    r = check_rig(man.out_dir / "test_pose.glb", GODOT, humanoid=True)
    assert r.ok, r.problems
    assert "animations=1" in r.summary


@needs_blender
@needs_godot
def test_godot_imports_the_animal_rig_with_no_errors(fox):
    for name in ("rigged.glb", "test_pose.glb"):
        r = check_rig(fox.out_dir / name, GODOT)
        assert r.ok, r.problems
