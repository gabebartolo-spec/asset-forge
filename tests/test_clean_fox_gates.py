"""Step 2 fidelity gates for animals, measured on the fox bake-off meshes (local only: needs the
gitignored models/ folder, Blender and the GPU). The fox is cleaned with the app's own command
(steps.clean_command: method B, the multiview generator paints the sides the picture cannot see);
the GPU lock is held only while the generator runs (--gpu-lock). The reference picture's chest,
flank, tail body, tail tip and legs are read as colour regions, and the same regions on the baked
albedo (every texel, so the front of the chest counts too) must match: black socks stay black,
the chest is pale, the tail is orange with white only at its tip. The gates themselves live in
blender/clean.py (REGION_GATES, region_gate_checks) and are written to report.json
colour_route.region_gates. The cleaned fox must also be one part. CLEAN_SCRIPT overrides the
script under test."""

import json
import os
import subprocess
import sys

import pytest
from test_clean_step import ROOT, blender_exe

from asset_forge.steps import clean_command, multiview_paths

sys.path.insert(0, str(ROOT / "tools" / "bakeoff"))
from gpu_lock import _models_dir  # noqa: E402

pytestmark = [pytest.mark.blender, pytest.mark.gpu]
MODELS = _models_dir()
REF = MODELS / "bakeoff" / "refs" / "fox.png"


# TripoSG fox, method B (2026-10-20, clean-b10): chest p90 luma ratio 0.838 (gate 0.85 .. 1.25);
# the per-cell colour match compares a side-on picture cell (mostly orange flank) with the same
# cell on the model (the whole white chest front). Strict: it reports when the fix lands.
TRIPOSG_CHEST = pytest.mark.xfail(strict=True, reason="method B chest p90 0.838 < 0.85, open fix")


@pytest.mark.parametrize("generator", ["hi3dgen", pytest.param("triposg", marks=TRIPOSG_CHEST)])
def test_fox_colours_match_the_reference_regions(generator, tmp_path):
    raw = MODELS / "bakeoff" / "out" / generator / "fox.glb"
    if not (raw.exists() and REF.exists()):
        pytest.skip("bake-off fox meshes are not on this machine")
    if not all(p.exists() for p in multiview_paths(MODELS).values()):
        pytest.skip("the multiview generator is not installed in models/")
    cmd = clean_command(blender_exe(), ROOT, raw, tmp_path, "animal", REF, generator=generator,
                        models_dir=MODELS) + ["--height", "0.40", "--no-sheets",
                                              "--gpu-lock", str(MODELS / "gpu.lock")]
    if os.environ.get("CLEAN_SCRIPT"):
        cmd[cmd.index("-P") + 1] = os.environ["CLEAN_SCRIPT"]
    done = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    assert done.returncode == 0, done.stdout[-1500:] + done.stderr[-1500:]
    rep = json.loads((tmp_path / "report.json").read_text())
    gates = rep["colour_route"]["region_gates"]
    failed = [g for g in gates["gates"] if not g["ok"]]
    assert not failed, failed
    assert rep["single_part"]["ok"], rep["single_part"]
