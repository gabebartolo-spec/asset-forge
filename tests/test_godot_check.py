"""Real headless Godot import check. Local only (marker blender); skipped without the exe."""

import pytest
from glb_factory import write_broken_glb, write_cube_glb

from asset_forge.export.godot_check import check_glb, godot_exe

pytestmark = pytest.mark.blender
EXE = godot_exe()
needs_godot = pytest.mark.skipif(EXE is None or not EXE.is_file(), reason="no Godot in config")


@needs_godot
def test_cube_imports_clean(tmp_path):
    r = check_glb(write_cube_glb(tmp_path / "cube.glb"), EXE)
    assert r.ok, r.problems
    assert "meshes=1" in r.summary


@needs_godot
def test_broken_glb_fails(tmp_path):
    r = check_glb(write_broken_glb(tmp_path / "bad.glb"), EXE)
    assert not r.ok and r.problems


@needs_godot
def test_not_a_glb_fails(tmp_path):
    p = tmp_path / "junk.glb"
    p.write_bytes(b"not a model")
    assert not check_glb(p, EXE).ok
