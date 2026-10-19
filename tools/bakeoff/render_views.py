"""Blender (headless) script: render one generated mesh from six views, untextured and textured,
and measure it. Design 5.2 inspection: front, back, both sides, three-quarter, top.

    blender -b --factory-startup -P tools/bakeoff/render_views.py -- MESH OUT_DIR [--yaw DEG]

Writes OUT_DIR/<view>_<shade>.png (shade = clay | colour) and OUT_DIR/stats.json
(triangles, vertices, loose parts, open edges, colour source). Workbench engine: fast, no bake.
"""

import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

VIEWS = {  # name: (azimuth deg around Z from front, elevation deg)
    "front": (0, 5), "back": (180, 5), "left": (90, 5), "right": (-90, 5),
    "three_quarter": (35, 20), "top": (0, 89.5),
}
RES = 512


def args():
    argv = sys.argv[sys.argv.index("--") + 1:]
    mesh, out = Path(argv[0]), Path(argv[1])
    yaw = float(argv[argv.index("--yaw") + 1]) if "--yaw" in argv else 0.0
    return mesh, out, yaw


def import_mesh(path: Path):
    ext = path.suffix.lower()
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=str(path))
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=str(path))
    elif ext == ".ply":
        bpy.ops.wm.ply_import(filepath=str(path))
    elif ext == ".stl":
        bpy.ops.wm.stl_import(filepath=str(path))
    else:
        raise SystemExit(f"unsupported mesh {ext}")
    return [o for o in bpy.context.scene.objects if o.type == "MESH"]


def join(objs):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    if len(objs) > 1:
        bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return obj


def measure(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    # Exporters split vertices along UV and normal seams; weld them before counting parts.
    dims = obj.dimensions
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=max(dims) * 1e-5)
    bm.verts.index_update()
    tris = sum(len(f.verts) - 2 for f in bm.faces)
    open_edges = sum(1 for e in bm.edges if len(e.link_faces) != 2)
    parent = list(range(len(bm.verts)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for e in bm.edges:
        a, b = find(e.verts[0].index), find(e.verts[1].index)
        if a != b:
            parent[a] = b
    roots = {}
    for v in bm.verts:
        r = find(v.index)
        roots[r] = roots.get(r, 0) + 1
    big = max(roots.values()) if roots else 0
    stats = {
        "triangles": tris, "vertices": len(bm.verts), "loose_parts": len(roots),
        "loose_parts_over_1pct": sum(1 for n in roots.values() if n >= 0.01 * big),
        "open_edges": open_edges,
    }
    bm.free()
    return stats


def colour_source(obj):
    has_tex = any(
        n.type == "TEX_IMAGE" and n.image
        for s in obj.material_slots if s.material and s.material.use_nodes
        for n in s.material.node_tree.nodes
    )
    if has_tex:
        return "TEXTURE"
    if obj.data.color_attributes:
        obj.data.color_attributes.active_color = obj.data.color_attributes[0]
        return "VERTEX"
    return None


def main():
    mesh, out, yaw = args()
    out.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    obj = join(import_mesh(mesh))
    obj.rotation_euler.z = math.radians(yaw)
    bpy.ops.object.transform_apply(rotation=True)
    stats = measure(obj)

    # Normalise: centre on the bounding box, largest side = 2 units, feet on z = 0.
    pts = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    size = max(hi - lo)
    obj.location -= (lo + hi) / 2
    obj.scale *= 2.0 / size
    bpy.ops.object.transform_apply(location=True, scale=True)
    stats["bbox_ratio_xyz"] = [round(v / size, 3) for v in (hi - lo)]

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.resolution_x = scene.render.resolution_y = RES
    scene.render.film_transparent = False
    shading = scene.display.shading
    shading.light = "STUDIO"
    shading.show_cavity = True
    shading.cavity_type = "BOTH"
    shading.show_object_outline = False
    shading.background_type = "VIEWPORT"
    shading.background_color = (0.92, 0.92, 0.92)
    world = bpy.data.worlds.new("w")
    scene.world = world

    cam_data = bpy.data.cameras.new("cam")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = 2.5
    cam = bpy.data.objects.new("cam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam

    src = colour_source(obj)
    stats["colour_source"] = src
    for shade in ("clay", "colour"):
        if shade == "colour" and src is None:
            continue
        shading.color_type = "SINGLE" if shade == "clay" else src
        shading.single_color = (0.75, 0.75, 0.75)
        for view, (az, el) in VIEWS.items():
            a, e = math.radians(az), math.radians(el)
            # Front camera sits on -Y looking towards +Y (Blender's front view).
            d = Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)))
            cam.location = d * 10
            cam.rotation_euler = (-d).to_track_quat("-Z", "Z" if el < 89 else "Y").to_euler()
            scene.render.filepath = str(out / f"{view}_{shade}.png")
            bpy.ops.render.render(write_still=True)
    (out / "stats.json").write_text(json.dumps(stats, indent=2))
    print("STATS", json.dumps(stats))


main()
