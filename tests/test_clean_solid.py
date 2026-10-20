"""Solid rebuild in blender/clean.py (escape-count hollow fill, cylinder bridge), on synthetic voxel
grids inside headless Blender (clean.py imports bpy). Local only: `pytest -m blender`.
Known-bad inputs: an open hollow shell (Hi3DGen-like: the old seal trick left it hollow) and a limb
about 6 voxels off the body (TripoSG fox: the old lens bridge left two parts); a solid block with
a dent is the control that must not change."""

import json
import subprocess

import pytest
from test_clean_step import ROOT, blender_exe

pytestmark = pytest.mark.blender

PROBE = """
import importlib.util, json, sys
import numpy as np
spec = importlib.util.spec_from_file_location("clean", sys.argv[sys.argv.index("--") + 1])
C = importlib.util.module_from_spec(spec)
spec.loader.exec_module(C)
out = {}
n = 60
g = np.zeros((n, n, n), bool)
g[10:50, 10:50, 10:50] = True
g[13:47, 13:47, 13:47] = False      # hollow shell, walls 3 voxels
g[26:34, 26:34, 47:50] = False      # an open mouth 8 voxels wide on top
f, info = C.solid_filler(g)
s = g | f
cav = s[13:47, 13:47, 13:47]
out["shell"] = dict(info, filled_share=float(cav.mean()), below_mouth=bool(cav[:, :, :28].all()),
                    outside_untouched=bool(not s[:9].any() and not s[51:].any()))
g = np.zeros((n, n, n), bool)
g[10:50, 20:40, 30:45] = True       # body
g[22:26, 26:30, 8:24] = True        # leg, 6 voxels below the body
f, info = C.solid_filler(g)
out["leg"] = dict(info, parts_now=len(C._label_big(g | f)))
g = np.zeros((n, n, n), bool)
g[10:50, 10:50, 10:50] = True
g[25:35, 25:35, 40:50] = False      # a dent open to the outside
f, info = C.solid_filler(g)
out["block"] = dict(info, added=int((f & ~g).sum()))
print("SOLID" + json.dumps(out))
"""


def test_solid_filler_fills_open_shell_bridges_leg_and_leaves_solid_alone(tmp_path):
    probe = tmp_path / "probe.py"
    probe.write_text(PROBE)
    done = subprocess.run([blender_exe(), "-b", "--factory-startup", "--python-exit-code", "1",
                           "-P", str(probe), "--", str(ROOT / "blender" / "clean.py")],
                          capture_output=True, text=True, timeout=300)
    assert done.returncode == 0, done.stdout[-1500:] + done.stderr[-1500:]
    line = next(x for x in done.stdout.splitlines() if x.startswith("SOLID"))
    out = json.loads(line[5:])
    shell, leg, block = out["shell"], out["leg"], out["block"]
    assert shell["hollow_share"] >= 0.10
    # all of the hollow is filled except a shallow dimple left under the mouth
    assert shell["filled_share"] > 0.99 and shell["below_mouth"] and shell["outside_untouched"]
    assert leg["parts_voxels"][1:] and leg["bridges_gap_voxels"]
    assert leg["parts_after"] == leg["parts_now"] == 1
    assert block["hollow_share"] < 0.10 and block["added"] == 0
