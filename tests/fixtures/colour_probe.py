"""Blender script for tests/test_clean_colour.py (run with blender -b -P).

Builds a small synthetic creature, a synthetic reference picture, calls clean.py's bake_colour and
dumps measurements as JSON. Args after --: MODE CLEAN_PY OUT

    head     humanoid-like figure; the reference draws the head left of centre with a red face disc
    headtiny same, but the reference head is a fifth as wide as the model head (must not be used)
    animal   side-projected animal; reference has a dark eye on the near flank (camera +X)
    rim      tall body; reference has a dark shadow strip down its left edge
"""

import importlib.util
import json
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Matrix

mode, clean_py, out = sys.argv[sys.argv.index("--") + 1:][:3]
spec = importlib.util.spec_from_file_location("clean_mod", clean_py)
clean = importlib.util.module_from_spec(spec)
sys.argv = [sys.argv[0], "--", "x", "y"]
spec.loader.exec_module(clean)


def build(parts):
    """parts: (centre xyz, radii xyz) ellipsoids, joined into one object with a UV map."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bm = bmesh.new()
    for (cx, cy, cz), (rx, ry, rz) in parts:
        m = bmesh.ops.create_uvsphere(bm, u_segments=40, v_segments=28, radius=1.0)
        bmesh.ops.transform(bm, matrix=Matrix.Translation((cx, cy, cz))
                            @ Matrix.Diagonal((rx, ry, rz, 1.0)), verts=m["verts"])
    me = bpy.data.meshes.new("m")
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new("m", me)
    bpy.context.scene.collection.objects.link(obj)
    clean.select_only(obj)
    bpy.ops.object.shade_smooth()
    clean.uv_unwrap(obj)
    return obj


def disc(img, cx, cy, r, rgb):
    yy, xx = np.mgrid[:img.shape[0], :img.shape[1]]
    img[(xx - cx) ** 2 + (yy - cy) ** 2 <= r * r, :3] = rgb


def blank(w, h):
    return np.zeros((h, w, 4), np.float32)


def figure_ref(head_r, face_r):
    """128 x 256 picture, row 0 = bottom. Body bar x 30..98, head disc left of centre."""
    img = blank(128, 256)
    img[0:150, 30:98] = (0.2, 0.3, 0.8, 1.0)
    cx, cy = 40, 222
    yy, xx = np.mgrid[:256, :128]
    head = (xx - cx) ** 2 + (yy - cy) ** 2 <= head_r ** 2
    img[head] = (0.8, 0.7, 0.5, 1.0)
    disc(img, cx, cy, face_r, (0.9, 0.1, 0.1))  # the face
    return img


def luma(c):
    return c[..., 0] * 0.2126 + c[..., 1] * 0.7152 + c[..., 2] * 0.0722


def sel(info, **kw):
    p = info["pos"]
    m = np.ones(len(p), bool)
    for k, (lo, hi) in kw.items():
        a = {"x": p[:, 0], "y": p[:, 1], "z": p[:, 2], "w": info["facing"]}[k]
        m &= (a >= lo) & (a <= hi)
    return m


res = {}
if mode in ("head", "headtiny"):
    # Body ellipsoid 0.3 x 0.15 x 0.9, head sphere r 0.12 centred (the generator centred it).
    obj = build([((0, 0, 0.9), (0.3, 0.15, 0.9)), ((0, 0, 1.78), (0.12, 0.12, 0.12))])
    ref = figure_ref(10, 6) if mode == "head" else figure_ref(2, 1)
    img, stats, info = clean.bake_colour(obj, ref, (0.0, -1.0, 0.0), 256)
    m = sel(info, x=(-0.03, 0.03), z=(1.7, 1.95), w=(0.8, 1.0))
    col = info["colour"][m]
    res = {"n": int(m.sum()), "mean_rgb": col.mean(axis=0).tolist() if len(col) else [0, 0, 0],
           "stats": stats}
elif mode == "animal":
    # Faces -Y: body along Y, head sphere at the -Y end. Camera is on +X (image right = +Y).
    obj = build([((0, 0.1, 0.5), (0.16, 0.6, 0.22)), ((0, -0.62, 0.72), (0.15, 0.15, 0.15))])
    ref = blank(256, 128)
    yy, xx = np.mgrid[:128, :256]
    body = ((xx - 150) / 100.0) ** 2 + ((yy - 40) / 38.0) ** 2 <= 1
    head = ((xx - 62) / 26.0) ** 2 + ((yy - 62) / 26.0) ** 2 <= 1
    ref[body | head, 3] = 1.0
    ref[body, :3] = (0.55, 0.3, 0.12)
    ref[head, :3] = (0.9, 0.5, 0.15)
    disc(ref, 62, 62, 4, (0.02, 0.02, 0.02))  # the eye, on the near flank
    img, stats, info = clean.bake_colour(obj, ref, (1.0, 0.0, 0.0), 256)
    eye_far = sel(info, x=(-0.2, -0.05), y=(-0.80, -0.44), z=(0.55, 0.9))
    back = sel(info, y=(0.45, 0.8))
    luma_far = luma(info["colour"][eye_far])
    col_back = info["colour"][back]
    res = {"far_min_luma": float(luma_far.min()) if len(luma_far) else 9.0,
           "far_n": int(eye_far.sum()), "back_n": int(back.sum()),
           "back_min_luma": float(luma(col_back).min()) if len(col_back) else 0.0,
           "back_std": float(col_back.std(axis=0).max()) if len(col_back) else 9.0,
           "stats": stats}
elif mode == "rim":
    obj = build([((0, 0, 0.9), (0.3, 0.3, 0.9))])
    ref = blank(128, 256)
    ref[0:256, 30:98] = (0.8, 0.6, 0.55, 1.0)
    ref[0:256, 30:42, :3] = 0.08  # shadow strip down the left edge
    img, stats, info = clean.bake_colour(obj, ref, (0.0, -1.0, 0.0), 256)
    back = sel(info, w=(-1.0, -0.5))
    col = info["colour"][back]
    res = {"back_n": int(back.sum()),
           "back_mean_luma": float(luma(col).mean()) if len(col) else 0.0, "stats": stats}
json.dump(res, open(out, "w"))
