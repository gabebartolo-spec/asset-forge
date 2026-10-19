"""Export step with Godot and the gates mocked."""

import json
import sys
import types

import pytest

from asset_forge.export import ExportRefused, export, godot_check


def _asset(tmp_path, with_blend=True):
    d = tmp_path / "lib" / "fox-01"
    d.mkdir(parents=True)
    (d / "fox-01.glb").write_bytes(b"glb")
    if with_blend:
        (d / "fox-01.blend").write_bytes(b"blend")
    (d / "report.json").write_text(json.dumps({"triangles": 10}))
    return d


@pytest.fixture
def gates(monkeypatch):
    state = {"problems": []}
    mod = types.ModuleType("asset_forge.gates")
    mod.check = lambda report, asset_type: list(state["problems"])
    monkeypatch.setitem(sys.modules, "asset_forge.gates", mod)
    return state


@pytest.fixture
def godot(monkeypatch):
    state = {"result": godot_check.GodotResult(True)}
    monkeypatch.setattr(godot_check, "check_glb", lambda glb, exe=None: state["result"])
    return state


def test_clean_export_copies_glb_and_blend(tmp_path, gates, godot):
    dest = export(_asset(tmp_path), "animal", exports_dir=tmp_path / "exports")
    assert sorted(p.name for p in dest.iterdir()) == ["fox-01.blend", "fox-01.glb"]


def test_gate_failure_refuses_and_copies_nothing(tmp_path, gates, godot):
    gates["problems"] = ["Triangles: 9,000, the limit is 2,000."]
    with pytest.raises(ExportRefused) as e:
        export(_asset(tmp_path), "animal", exports_dir=tmp_path / "exports")
    assert "Triangles" in str(e.value)
    assert not (tmp_path / "exports").exists()


def test_godot_failure_refuses(tmp_path, gates, godot):
    godot["result"] = godot_check.GodotResult(False, ["ERROR: bad accessor"])
    with pytest.raises(ExportRefused) as e:
        export(_asset(tmp_path), "animal", exports_dir=tmp_path / "exports")
    assert "Godot could not load" in str(e.value)
    assert not (tmp_path / "exports").exists()


def test_both_failures_are_both_named(tmp_path, gates, godot):
    gates["problems"] = ["Bones: 70, the limit is 64."]
    godot["result"] = godot_check.GodotResult(False, ["ERROR: x"])
    with pytest.raises(ExportRefused) as e:
        export(_asset(tmp_path), "monster", exports_dir=tmp_path / "exports")
    assert len(e.value.reasons) == 2


def test_missing_glb_or_report_refuses(tmp_path, gates, godot):
    d = _asset(tmp_path)
    (d / "report.json").unlink()
    with pytest.raises(ExportRefused, match="no report"):
        export(d, "animal", exports_dir=tmp_path / "e")
    (d / "fox-01.glb").unlink()
    with pytest.raises(ExportRefused, match="no cleaned model"):
        export(d, "animal", exports_dir=tmp_path / "e")


def test_export_without_blend_is_fine(tmp_path, gates, godot):
    dest = export(_asset(tmp_path, with_blend=False), "animal", exports_dir=tmp_path / "e")
    assert [p.name for p in dest.iterdir()] == ["fox-01.glb"]


def test_godot_check_without_exe_says_so(tmp_path):
    r = godot_check.check_glb(tmp_path / "x.glb", exe=tmp_path / "missing.exe")
    assert not r.ok and "config.local.toml" in r.problems[0]


def test_godot_exe_reads_config(tmp_path):
    cfg = tmp_path / "c.toml"
    cfg.write_text('[godot]\nexe = "G.exe"\n')
    assert str(godot_check.godot_exe(cfg)) == "G.exe"
    assert godot_check.godot_exe(tmp_path / "none.toml") is None
