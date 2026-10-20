"""Export of the animated model (Step 4): the gate measured on the final .glb, with known-bad
files for every limit, and the Godot checks mocked (the real ones are -m blender)."""

from __future__ import annotations

import json

import pytest
from anim_factory import write_budget_glb
from skin_factory import write_skinned_glb

from asset_forge.export import ExportRefused, export_animated, godot_check
from asset_forge.export.animated import gate_problems, measure_glb


@pytest.fixture
def godot(monkeypatch):
    state = {"rig": godot_check.GodotResult(True, [], "RIG_CHECK_OK"),
             "imp": godot_check.GodotResult(True, [], "LOOP_CHECK_OK"), "loops": None}

    def imp(glb, loops, exe=None):
        state["loops"] = loops
        state["sidecar"] = glb.with_name(glb.name + ".import").read_text()
        return state["imp"]

    monkeypatch.setattr(godot_check, "check_rig", lambda glb, exe=None, humanoid=False:
                        state["rig"])
    monkeypatch.setattr(godot_check, "check_import", imp)
    return state


def _anim_dir(tmp_path, **kw):
    d = tmp_path / "lib" / "fox-01" / "animate"
    d.mkdir(parents=True)
    write_budget_glb(d / "animated.glb", **kw)
    (d / "animated.blend").write_bytes(b"blend")
    (d / "clips.json").write_text(json.dumps({"template": "four_legged"}))
    return d


def test_measure_reads_the_file_itself(tmp_path):
    m = measure_glb(write_budget_glb(tmp_path / "a.glb", tris=2001, materials=2, tex_px=1024))
    assert m == {"triangles": 2001, "materials": 2, "texture_px": 1024, "bones": 0,
                 "influences": 0}


def test_an_animal_inside_its_budget_exports_with_its_loop_sidecar(tmp_path, godot):
    dest, rep = export_animated(_anim_dir(tmp_path, tris=2000, tex_px=512), "fox-01", "animal",
                                tmp_path / "exports")
    assert sorted(p.name for p in dest.iterdir()) == [
        "fox-01.blend", "fox-01.clips.json", "fox-01.export.json", "fox-01.glb",
        "fox-01.glb.import"]
    side = (dest / "fox-01.glb.import").read_text()
    assert side == godot["sidecar"]
    for n in ("idle", "walk", "run"):
        assert f'"{n}": {{\n"settings/loop_mode": 1' in side
    assert "attack" not in side
    assert godot["loops"] == {"idle": 1, "walk": 1, "run": 1, "attack": 0, "hit": 0, "faint": 0}
    assert rep["measured"]["triangles"] == 2000 and rep["problems"] == []


@pytest.mark.parametrize("kw, words", [
    ({"tris": 2001}, "The model has 2,001 triangles; the limit for an animal is 2,000."),
    ({"materials": 2}, "The model uses 2 materials; the limit is 1."),
    ({"tex_px": 1024}, "The texture is 1024 pixels across; the limit for an animal is 512."),
])
def test_an_animal_over_its_budget_is_refused_and_nothing_is_copied(tmp_path, godot, kw, words):
    with pytest.raises(ExportRefused) as e:
        export_animated(_anim_dir(tmp_path, **kw), "fox-01", "animal", tmp_path / "exports")
    assert words in e.value.reasons
    assert not (tmp_path / "exports").exists()


def test_the_budget_follows_the_asset_type(tmp_path, godot):
    m = measure_glb(write_budget_glb(tmp_path / "a.glb", tris=7999, tex_px=1024))
    assert gate_problems(m, "humanoid") == []
    assert len(gate_problems(m, "animal")) == 2
    assert gate_problems(m, "animal", {"triangles": 8000, "texture_px": 1024}) == []


def test_too_many_bones_or_influences_are_refused(tmp_path):
    m = measure_glb(write_skinned_glb(tmp_path / "s.glb", bones=70, influences=8))
    assert gate_problems(m, "humanoid") == [
        "The skeleton has 70 bones; the limit is 64.",
        "Some parts of the model follow 8 bones at once; the limit is 4."]


def test_a_godot_failure_refuses_the_export(tmp_path, godot):
    godot["imp"] = godot_check.GodotResult(False, ["IMPORT_CHECK_FAIL: idle has loop mode 0"])
    with pytest.raises(ExportRefused) as e:
        export_animated(_anim_dir(tmp_path), "fox-01", "animal", tmp_path / "exports")
    assert e.value.reasons == ["Godot could not load the model cleanly: IMPORT_CHECK_FAIL: idle "
                               "has loop mode 0"]
    assert not (tmp_path / "exports").exists()


def test_no_animations_yet_says_what_to_click(tmp_path, godot):
    with pytest.raises(ExportRefused, match="Press Animate first"):
        export_animated(tmp_path, "fox-01", "animal", tmp_path / "exports")


def test_loop_sidecar_names_only_the_looping_clips():
    s = godot_check.loop_sidecar(["idle", "walk", "run"])
    assert s.startswith('[remap]\n\nimporter="scene"\nimporter_version=1\n')
    assert s.count('"settings/loop_mode": 1') == 3
