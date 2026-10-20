"""Step 2 fidelity gates for animals, measured on the fox bake-off meshes (local only: needs the
gitignored models/ folder and Blender). The reference picture's chest, flank, tail body, tail tip
and legs are read as colour regions, and the same regions on the baked albedo (every texel, so
the front of the chest counts too) must match: black socks stay black, the chest is pale, the tail
is orange with white only at its tip. The gates themselves live in blender/clean.py
(REGION_GATES, region_gate_checks) and are written to report.json colour_route.region_gates.
CLEAN_SCRIPT overrides the script under test."""

import json
import os
import sys
from pathlib import Path

import pytest
from test_clean_forward import blender
from test_clean_step import ROOT

sys.path.insert(0, str(ROOT / "tools" / "bakeoff"))
from gpu_lock import _models_dir  # noqa: E402

pytestmark = pytest.mark.blender
CLEAN = Path(os.environ.get("CLEAN_SCRIPT", ROOT / "blender" / "clean.py"))
MODELS = _models_dir()
REF = MODELS / "bakeoff" / "refs" / "fox.png"


@pytest.mark.parametrize("generator", ["hi3dgen", "triposg"])
def test_fox_colours_match_the_reference_regions(generator, tmp_path):
    raw = MODELS / "bakeoff" / "out" / generator / "fox.glb"
    if not (raw.exists() and REF.exists()):
        pytest.skip("bake-off fox meshes are not on this machine")
    blender("-P", str(CLEAN), "--", str(raw), str(tmp_path), "--type", "animal", "--ref", str(REF),
            "--generator", generator, "--height", "0.40", "--no-sheets")
    gates = json.loads((tmp_path / "report.json").read_text())["colour_route"]["region_gates"]
    failed = [g for g in gates["gates"] if not g["ok"]]
    assert not failed, failed
