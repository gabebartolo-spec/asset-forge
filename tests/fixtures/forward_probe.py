"""Blender script for tests/test_clean_forward.py (run with blender -b -P).

    mode make   : write a generator-style marker glb (tall body, head, nose toward glTF +Z)
    mode export : build the marker facing Blender -Y and export it with clean.py's export_glb
    mode back   : bake the reference onto a sphere with clean.py and dump back-texel stats as JSON
Args after --: MODE CLEAN_PY OUT
"""

import importlib.util
import json
import math
import sys

import bmesh
import bpy
import numpy as np

mode, clean_py, out = sys.argv[sys.argv.index("--") + 1:][:3]
spec = importlib.util.spec_from_file_location("clean_mod", clean_py)
clean = importlib.util.module_from_spec(spec)
sys.argv = [sys.argv[0], "--", "x", "y"]  # parse() is not called at import
spec.loader.exec_module(clean)


def marker_object():
    """Blender frame: faces -Y. Body ellipsoid, head sphere, nose cone sticking out toward -Y."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bm = bmesh.new()
    for (r, z, sx, sy, sz) in ((1.0, 0.9, 0.3, 0.15, 0.9), (1.0, 1.7, 0.18, 0.18, 0.18)):
        m = bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=16, radius=r)
        verts = m["verts"]
        bmesh.ops.scale(bm, vec=(sx, sy, sz), verts=verts)
        bmesh.ops.translate(bm, vec=(0, 0, z), verts=verts)
    cone = bmesh.ops.create_cone(bm, segments=16, radius1=0.15, radius2=0.0, depth=0.5,
                                 cap_ends=True)
    cv = cone["verts"]
    bmesh.ops.rotate(bm, verts=cv, cent=(0, 0, 0),
                     matrix=__import__("mathutils").Matrix.Rotation(math.radians(90), 3, "X"))
    bmesh.ops.translate(bm, vec=(0, -0.3, 1.7), verts=cv)  # base inside the head, tip at y = -0.55
    me = bpy.data.meshes.new("marker")
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new("marker", me)
    bpy.context.scene.collection.objects.link(obj)
    return obj


if mode in ("make", "export"):
    obj = marker_object()
    if mode == "export":
        clean.export_glb(obj, out)
    else:
        clean.select_only(obj)
        bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", use_selection=True,
                                  export_yup=True)
elif mode == "back":
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=32, radius=1.0)
    obj = bpy.context.active_object
    bpy.ops.object.shade_smooth()
    clean.uv_unwrap(obj)
    size = 256
    ref = np.zeros((64, 64, 4), np.float32)
    ref[..., :3] = (0.1, 0.8, 0.1)  # green body
    ref[..., 3] = 1.0
    yy, xx = np.mgrid[:64, :64]
    ref[(xx - 32) ** 2 + (yy - 32) ** 2 < 14 ** 2, :3] = 0.0  # black "visor" in the middle
    res = clean.bake_colour(obj, ref, (0.0, -1.0, 0.0), size)
    stats, info = res[1], res[2]
    back = info["facing"] < -0.9
    col = info["colour"][back]
    json.dump({"back_texels": int(back.sum()), "back_projected": int(info["projected"][back].sum()),
               "back_min_luma": float(col.sum(axis=1).min()) if len(col) else None,
               "back_std": float(col.std(axis=0).max()) if len(col) else None,
               "stats": stats}, open(out, "w"))
