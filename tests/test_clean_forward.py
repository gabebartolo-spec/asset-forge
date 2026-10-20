"""Clean step: facing, forward axis (D-021) and colour on unseen surfaces. Local only
(`pytest -m blender`). CLEAN_SCRIPT overrides the script under test."""

import json
import os
import struct
import subprocess
from pathlib import Path

import pytest
from test_clean_step import FIX, ROOT, blender_exe

pytestmark = pytest.mark.blender
PROBE = FIX / "forward_probe.py"
CLEAN = Path(os.environ.get("CLEAN_SCRIPT", ROOT / "blender" / "clean.py"))


def blender(*args):
    done = subprocess.run([blender_exe(), "-b", "--factory-startup", *args],
                          capture_output=True, text=True, timeout=300)
    assert done.returncode == 0, done.stdout[-1500:] + done.stderr[-1500:]


def probe(mode, out):
    blender("-P", str(PROBE), "--", mode, str(CLEAN), str(out))


def gltf_positions(path):
    """All POSITION vertices (x, y, z) of a .glb, in glTF coordinates, parsed by hand."""
    data = Path(path).read_bytes()
    jlen = struct.unpack_from("<I", data, 12)[0]
    doc = json.loads(data[20:20 + jlen])
    blen = struct.unpack_from("<I", data, 20 + jlen)[0]
    binary = data[28 + jlen:28 + jlen + blen]
    pts = []
    for mesh in doc["meshes"]:
        for prim in mesh["primitives"]:
            acc = doc["accessors"][prim["attributes"]["POSITION"]]
            view = doc["bufferViews"][acc["bufferView"]]
            off = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
            stride = view.get("byteStride", 12)
            pts += [struct.unpack_from("<3f", binary, off + i * stride)
                    for i in range(acc["count"])]
    return pts


def facing(path):
    """Mid-range glTF z of the head band minus that of the body band. The model is re-centred,
    so only this difference (not an absolute z) shows which way the nose points: > 0 means +z."""
    pts = gltf_positions(path)
    ys = [p[1] for p in pts]
    low, top = min(ys), max(ys)
    h = top - low

    def mean_z(a, b):
        sel = [p[2] for p in pts if low + a * h <= p[1] <= low + b * h]
        return (max(sel) + min(sel)) / 2

    return mean_z(0.82, 1.0) - mean_z(0.2, 0.6)


def test_export_puts_blender_minus_y_on_gltf_plus_z(tmp_path):
    glb = tmp_path / "marker.glb"
    probe("export", glb)
    assert facing(glb) > 0.02  # the nose (Blender -Y) is on glTF +z


def test_clean_keeps_a_generator_front_on_gltf_plus_z(tmp_path):
    raw = tmp_path / "raw.glb"
    probe("make", raw)  # generator-style output: front on glTF +z
    assert facing(raw) > 0.02
    out = tmp_path / "clean"
    blender("-P", str(CLEAN), "--", str(raw), str(out), "--type", "humanoid", "--ref",
            str(FIX / "figure_ref.png"), "--generator", "triposg", "--no-sheets")
    assert facing(out / "clean.glb") > 0.02  # the face still points at glTF +z (Godot model front)


def test_unseen_surfaces_get_low_frequency_colour_not_a_mirrored_picture(tmp_path):
    out = tmp_path / "back.json"
    probe("back", out)
    r = json.loads(out.read_text())
    assert r["back_texels"] > 100
    assert r["back_projected"] == 0          # nothing on the back is a copy of the picture
    assert r["back_min_luma"] > 0.6          # the black visor did not appear on the back
    assert r["back_std"] < 0.1               # smooth
    assert r["stats"]["mirrored_far_side"] is False
