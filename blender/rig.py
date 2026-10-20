"""Blender (headless) script: rig a cleaned model.

    blender -b --factory-startup -P blender/rig.py -- CLEAN_GLB OUT_DIR --type humanoid|animal
        [--template humanoid|four_legged|bird] [--no-sheets] [--force-fallback]

Fits the fixed template to the mesh, binds it (Blender automatic weights, falling back to
distance weights when they fail), limits every vertex to 4 bones, strikes a test pose and writes
OUT_DIR/rigged.glb, rigged.blend, test_pose.glb, skeleton.json and (unless --no-sheets) the
test-pose sheet as OUT_DIR/pose_<view>_<clay|colour>.png.
"""

import json
import math
import sys
import time
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from asset_forge.skeleton import fit as fitter  # noqa: E402
from asset_forge.skeleton import weights as wmod  # noqa: E402
from asset_forge.skeleton.pose import TEST_POSES  # noqa: E402
from asset_forge.skeleton.templates import MAX_INFLUENCES, TEMPLATES  # noqa: E402

SHEET_VIEWS = {"front": (0, 5), "back": (180, 5), "left": (90, 5), "right": (-90, 5),
               "three_quarter": (35, 20), "top": (0, 89.5)}
SHEET_RES = 512
SHEET_EXPOSURE = 1.1


def parse():
    a = sys.argv[sys.argv.index("--") + 1:]
    o = {"glb": Path(a[0]), "out": Path(a[1]), "type": "humanoid", "template": None,
         "sheets": "--no-sheets" not in a, "fallback": "--force-fallback" in a}
    if "--type" in a:
        o["type"] = a[a.index("--type") + 1]
    if "--template" in a:
        o["template"] = a[a.index("--template") + 1]
    return o


def select_only(*objs):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[-1]


def import_mesh(path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(path))
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    if len(meshes) > 1:
        select_only(*meshes)
        bpy.ops.object.join()
        meshes = [bpy.context.view_layer.objects.active]
    obj = meshes[0]
    select_only(obj)
    obj.parent = None
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    obj.name = "Model"
    for o in list(bpy.context.scene.objects):
        if o is not obj:
            bpy.data.objects.remove(o, do_unlink=True)
    return obj


def verts_np(obj):
    n = len(obj.data.vertices)
    a = np.empty(n * 3, dtype=np.float32)
    obj.data.vertices.foreach_get("co", a)
    return a.reshape(n, 3).astype(float)


def build_armature(template, joints):
    bpy.ops.object.armature_add(enter_editmode=True)
    arm = bpy.context.view_layer.objects.active
    arm.name = "Armature"
    arm.data.name = "Armature"
    eb = arm.data.edit_bones
    for b in list(eb):
        eb.remove(b)
    made = {}
    for bd in TEMPLATES[template]:
        head = Vector(joints[bd.name].tolist())
        tail = Vector(joints[bd.tail].tolist())
        if (tail - head).length < 1e-4:
            tail = head + Vector((0, 0, 0.01))
        e = eb.new(bd.name)
        e.head, e.tail = head, tail
        made[bd.name] = e
    for bd in TEMPLATES[template]:
        if bd.parent:
            made[bd.name].parent = made[bd.parent]
            if (made[bd.name].head - made[bd.parent].tail).length < 1e-6:
                made[bd.name].use_connect = True
    made["Root"].use_deform = False
    bpy.ops.object.mode_set(mode="OBJECT")
    return arm


def read_weights(obj, bone_names):
    idx = {n: i for i, n in enumerate(bone_names)}
    gname = {g.index: g.name for g in obj.vertex_groups}
    w = np.zeros((len(obj.data.vertices), len(bone_names)))
    for v in obj.data.vertices:
        for g in v.groups:
            n = gname.get(g.group)
            if n in idx:
                w[v.index, idx[n]] = g.weight
    return w


def write_weights(obj, bone_names, w):
    obj.vertex_groups.clear()
    groups = [obj.vertex_groups.new(name=n) for n in bone_names]
    for j, g in enumerate(groups):
        for i in np.nonzero(w[:, j] > 1e-6)[0]:
            g.add([int(i)], float(w[i, j]), "REPLACE")


def welded_auto_weights(obj, arm, deform):
    """Blender automatic weights on a welded copy (UV and normal seams split the exported
    mesh into open edges, which makes bone heat fail), mapped back to every original vertex."""
    import bmesh
    from mathutils.kdtree import KDTree

    dup = obj.copy()
    dup.data = obj.data.copy()
    bpy.context.scene.collection.objects.link(dup)
    bm = bmesh.new()
    bm.from_mesh(dup.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bm.to_mesh(dup.data)
    bm.free()
    select_only(dup, arm)
    bpy.ops.object.parent_set(type="ARMATURE_AUTO")
    wc = read_weights(dup, deform)
    kd = KDTree(len(dup.data.vertices))
    for v in dup.data.vertices:
        kd.insert(v.co, v.index)
    kd.balance()
    nearest = [kd.find(v.co)[1] for v in obj.data.vertices]
    mesh = dup.data
    bpy.data.objects.remove(dup, do_unlink=True)
    bpy.data.meshes.remove(mesh)
    return wc[nearest]


def bind(obj, arm, force_fallback):
    deform = [b.name for b in arm.data.bones if b.use_deform]
    heads = np.array([arm.data.bones[n].head_local[:] for n in deform])
    tails = np.array([arm.data.bones[n].tail_local[:] for n in deform])
    method, problems = "blender_automatic", []
    w = np.zeros((len(obj.data.vertices), len(deform)))
    if force_fallback:
        problems.append("fallback forced")
    else:
        try:
            w = welded_auto_weights(obj, arm, deform)
        except RuntimeError as e:
            problems.append(f"automatic weights raised: {e}")
    unweighted = int((w.sum(axis=1) <= 1e-6).sum())
    dead = [n for j, n in enumerate(deform) if (w[:, j] > 1e-4).sum() < 3]
    if force_fallback or unweighted or dead:
        method = "distance_fallback"
        if unweighted and not force_fallback:
            problems.append(f"{unweighted} vertices had no weight")
        if dead and not force_fallback:
            problems.append(f"no weight on: {', '.join(dead)}")
        w = wmod.distance_weights(verts_np(obj), heads, tails)
    before = int(wmod.influence_counts(w).max())
    w = wmod.limit_influences(w, MAX_INFLUENCES)
    write_weights(obj, deform, w)
    if not [m for m in obj.modifiers if m.type == "ARMATURE"]:
        obj.modifiers.new("Armature", "ARMATURE").object = arm
    obj.parent = arm
    return {"method": method, "problems": problems, "max_influences_before_limit": before,
            "max_influences": int(wmod.influence_counts(w).max()),
            "unweighted_vertices": int((w.sum(axis=1) <= 1e-6).sum()),
            "bones_with_weight": int((w.max(axis=0) > 1e-4).sum()), "deform_bones": len(deform)}


def rotate_bone(arm, name, axis, deg):
    bpy.context.view_layer.update()
    pb = arm.pose.bones[name]
    t = Matrix.Translation(pb.head.copy())
    pb.matrix = t @ Matrix.Rotation(math.radians(deg), 4, axis) @ t.inverted() @ pb.matrix
    bpy.context.view_layer.update()


def strike_pose(arm, template):
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="POSE")
    for name, axis, deg in TEST_POSES[template]:
        rotate_bone(arm, name, axis, deg)
    arm.animation_data_create()
    arm.animation_data.action = bpy.data.actions.new("test_pose")
    for pb in arm.pose.bones:
        pb.keyframe_insert("location", frame=1)
        pb.keyframe_insert("rotation_quaternion", frame=1)
        pb.keyframe_insert("scale", frame=1)
    bpy.ops.object.mode_set(mode="OBJECT")


def export(path, objs, animations):
    select_only(*objs)
    bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", use_selection=True,
                              export_yup=True, export_animations=animations,
                              export_skins=True, export_all_influences=False)


def render_sheet(obj, out):
    scene = bpy.context.scene
    ev = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    me = ev.to_mesh()
    n = len(me.vertices)
    a = np.empty(n * 3, dtype=np.float32)
    me.vertices.foreach_get("co", a)
    ev.to_mesh_clear()
    pts = a.reshape(n, 3).astype(float)
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    centre = Vector(((lo + hi) / 2).tolist())
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = SHEET_EXPOSURE
    scene.render.resolution_x = scene.render.resolution_y = SHEET_RES
    sh = scene.display.shading
    sh.light = "STUDIO"
    sh.show_cavity = True
    sh.show_specular_highlight = False
    sh.cavity_type = "BOTH"
    sh.show_object_outline = False
    sh.background_type = "VIEWPORT"
    sh.background_color = (0.92, 0.92, 0.92)
    scene.world = bpy.data.worlds.new("sheetworld")
    cam_data = bpy.data.cameras.new("sheetcam")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = float(max(hi - lo)) * 1.3
    cam = bpy.data.objects.new("sheetcam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    for shade, ctype in (("clay", "SINGLE"), ("colour", "TEXTURE")):
        sh.color_type = ctype
        sh.single_color = (0.75, 0.75, 0.75)
        for view, (az, el) in SHEET_VIEWS.items():
            ar, er = math.radians(az), math.radians(el)
            d = Vector((math.sin(ar) * math.cos(er), -math.cos(ar) * math.cos(er), math.sin(er)))
            cam.location = centre + d * 20
            cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
            scene.render.filepath = str(out / f"pose_{view}_{shade}.png")
            bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(cam, do_unlink=True)


def main():
    t0 = time.perf_counter()
    o = parse()
    out = o["out"]
    out.mkdir(parents=True, exist_ok=True)
    obj = import_mesh(o["glb"])
    v = verts_np(obj)
    template = o["template"]
    if template is None:
        template = "humanoid" if o["type"] == "humanoid" else fitter.choose_animal_template(v)
    joints = fitter.fit(v, template)
    arm = build_armature(template, joints)
    info = bind(obj, arm, o["fallback"])
    bones = TEMPLATES[template]

    export(out / "rigged.glb", [arm, obj], False)
    bpy.ops.wm.save_as_mainfile(filepath=str(out / "rigged.blend"), copy=True)
    strike_pose(arm, template)
    export(out / "test_pose.glb", [arm, obj], True)
    if o["sheets"]:
        render_sheet(obj, out)

    rep = {
        "template": template, "type": o["type"], "bones": len(bones), "weights": info,
        "joints": {b.name: [round(float(x), 5) for x in joints[b.name]] for b in bones},
        "bone_list": [{"name": b.name, "parent": b.parent,
                       "tail": [round(float(x), 5) for x in joints[b.tail]]} for b in bones],
        "foot_pivots": {k: [round(float(x), 5) for x in p]
                        for k, p in fitter.foot_pivots(v, template).items()},
        "forward": "-Y (glTF +Z)", "seconds": round(time.perf_counter() - t0, 1),
    }
    (out / "skeleton.json").write_text(json.dumps(rep, indent=1))
    print("RIG_OK", json.dumps({k: rep[k] for k in ("template", "bones", "weights", "seconds")}))


main()
