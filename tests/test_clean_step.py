"""Clean step on tiny fixture meshes, in headless Blender. Local only: `pytest -m blender`."""

import json
import os
import subprocess
import tomllib
from pathlib import Path

import pytest

from asset_forge.gates import check

pytestmark = pytest.mark.blender
ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures"
DEFAULT_EXE = "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe"


def blender_exe() -> str:
    env = os.environ.get("BLENDER_EXE")
    if env:
        return env
    main = ROOT.parent.parent / "asset-forge" / "config.local.toml"
    for cfg in (ROOT / "config.local.toml", main):
        if cfg.exists():
            return tomllib.loads(cfg.read_text())["blender"]["exe"]
    return DEFAULT_EXE


def run_clean(tmp_path, mesh, ref, kind, *extra, sheets=False):
    cmd = [blender_exe(), "-b", "--factory-startup", "-P", str(ROOT / "blender" / "clean.py"), "--",
           str(FIX / mesh), str(tmp_path), "--type", kind, "--ref", str(FIX / ref), *extra]
    if not sheets:
        cmd.append("--no-sheets")
    done = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    assert done.returncode == 0, done.stdout[-1500:] + done.stderr[-1500:]
    return json.loads((tmp_path / "report.json").read_text())


@pytest.fixture(scope="module")
def humanoid(tmp_path_factory):
    out = tmp_path_factory.mktemp("humanoid")
    return out, run_clean(out, "figure.obj", "figure_ref.png", "humanoid", sheets=True)


def test_humanoid_passes_the_gates(humanoid):
    out, rep = humanoid
    assert check(rep, "humanoid") == []
    assert rep["materials"] == 1
    assert rep["texture"]["width"] == rep["texture"]["height"] == 1024
    for f in ("clean.glb", "clean.blend", "texture.png", "report.json"):
        assert (out / f).is_file()


def test_humanoid_is_rebuilt_scaled_and_one_part(humanoid):
    _, rep = humanoid
    assert rep["height_m"] == pytest.approx(1.8, abs=0.01)
    assert rep["loose_parts"]["floaters_deleted"] >= 1  # the floating speck
    assert rep["loose_parts"]["after_clean"] == 1
    assert rep["forward"] == "+Y"
    assert rep["triangles"] < rep["voxel_remesh_triangles"]


def test_humanoid_sheets_exist(humanoid):
    out, _ = humanoid
    for side in ("before", "after"):
        assert (out / side / "front_clay.png").is_file()
    assert (out / "after" / "front_colour.png").is_file()


def test_over_budget_is_decimated_to_the_budget(tmp_path):
    rep = run_clean(tmp_path, "figure.obj", "figure_ref.png", "humanoid", "--budget", "300")
    assert rep["triangles"] <= 300


def test_animal_gets_the_small_budget_and_texture(tmp_path):
    rep = run_clean(tmp_path, "beast.obj", "beast_ref.png", "animal")
    assert rep["triangles"] <= 2000
    assert rep["texture"]["width"] == 512
    assert rep["orientation"]["turn_deg"] == 0  # already faces +Y; outline match keeps it
    assert check(rep, "animal") == []


def test_known_bad_shape_fails_the_silhouette_gate(tmp_path):
    # An absurdly low budget wrecks the shape; the silhouette gate must say so.
    rep = run_clean(tmp_path, "figure.obj", "figure_ref.png", "humanoid", "--budget", "12")
    assert any("outline changed" in m for m in check(rep, "humanoid", None))
