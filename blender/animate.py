"""Blender (headless) script: animate a rigged model.

    blender -b --factory-startup -P blender/animate.py -- RIGGED_BLEND OUT_DIR
        [--previews DIR] [--preview-size PX]

Opens the Skeleton step's rigged.blend, makes the six clips (asset_forge.animate.clips: pure
numpy, from the skeleton alone), keys every bone on every frame, puts each clip on its own NLA
track and writes OUT_DIR/animated.glb (clips idle, walk, run, attack, hit, faint), animated.blend
and clips.json. The faint is kept out of the ground (and on it once it lands) by measuring the
skinned mesh. With --previews it also renders each clip at game speed, a side-on three-quarter
view over a checker floor that runs at the clip's ground speed, to DIR/<clip>/0000.png...
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
from asset_forge.animate.body import Body  # noqa: E402
from asset_forge.animate.clips import ground_offsets, make_clips  # noqa: E402


def parse():
    a = sys.argv[sys.argv.index("--") + 1:]
    o = {"blend": Path(a[0]), "out": Path(a[1]), "previews": None, "size": 320}
    if "--previews" in a:
        o["previews"] = Path(a[a.index("--previews") + 1])
    if "--preview-size" in a:
        o["size"] = int(a[a.index("--preview-size") + 1])
    return o


def template_of(arm) -> str:
    names = set(arm.data.bones.keys())
    if "FrontLeftUpperLeg" in names:
        return "four_legged"
    if "LeftWing1" in names:
        return "bird"
    return "humanoid"


def np4(m) -> np.ndarray:
    return np.array([list(r) for r in m])


def mesh_z(obj) -> np.ndarray:
    """World height of every vertex of the skinned (evaluated) mesh."""
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = ev.to_mesh()
    n = len(me.vertices)
    a = np.empty(n * 3, dtype=np.float32)
    me.vertices.foreach_get("co", a)
    ev.to_mesh_clear()
    pts = a.reshape(n, 3) @ np4(obj.matrix_world)[:3, :3].T + np4(obj.matrix_world)[:3, 3]
    return pts[:, 2]


def mesh_min_z(obj) -> float:
    return float(mesh_z(obj).min())


def torso_mask(obj, arm) -> np.ndarray:
    """Rest-pose vertices of the trunk: between the hips and the neck, and no further out
    sideways than the shoulder joints (so not the arms or legs). Chosen by position, not by
    skin weight, because a blocky skinning gives the trunk to the shoulders and legs."""
    bones = arm.data.bones
    lo = bones["Hips"].head_local.z
    hi = (bones["Neck"] if "Neck" in bones else bones["Neck1"]).head_local.z
    side = abs(bones["LeftUpperArm"].head_local.x) if "LeftUpperArm" in bones else 1e9
    m = np4(obj.matrix_world)
    co = np.array([v.co[:] for v in obj.data.vertices], dtype=float)
    pts = co @ m[:3, :3].T + m[:3, 3]
    return (pts[:, 2] >= lo) & (pts[:, 2] <= hi) & (np.abs(pts[:, 0]) <= side)


def mesh_box(obj):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = ev.to_mesh()
    n = len(me.vertices)
    a = np.empty(n * 3, dtype=np.float32)
    me.vertices.foreach_get("co", a)
    ev.to_mesh_clear()
    pts = a.reshape(n, 3).astype(float)
    return pts.min(axis=0), pts.max(axis=0)


def use_action(arm, act):
    ad = arm.animation_data or arm.animation_data_create()
    ad.action = act
    if act is not None and hasattr(ad, "action_slot") and len(act.slots):
        ad.action_slot = act.slots[0]


class Keyer:
    """Turns the solver's deltas into pose-bone keys:  basis = rest^-1 @ Dp^-1 @ D @ rest."""

    def __init__(self, arm, body):
        self.arm, self.body = arm, body
        self.rest = {b.name: np4(b.matrix_local) for b in arm.data.bones}
        self.rest_inv = {k: np.linalg.inv(v) for k, v in self.rest.items()}

    def basis(self, D, name):
        p = self.body.parent[name]
        Dp_inv = np.linalg.inv(D[p]) if p is not None else np.eye(4)
        return self.rest_inv[name] @ Dp_inv @ D[name] @ self.rest[name]

    def key(self, act, deltas, only=None):
        use_action(self.arm, act)
        prev = {}
        for f, D in enumerate(deltas):
            for name in only or self.body.names:
                pb = self.arm.pose.bones[name]
                loc, q, _ = Matrix(self.basis(D, name).tolist()).decompose()
                if name in prev and prev[name].dot(q) < 0:
                    q.negate()
                prev[name] = q.copy()
                pb.rotation_mode = "QUATERNION"
                pb.location = loc
                pb.rotation_quaternion = q
                pb.scale = (1, 1, 1)
                pb.keyframe_insert("location", frame=f, group=name)
                pb.keyframe_insert("rotation_quaternion", frame=f, group=name)
                if only is None:
                    pb.keyframe_insert("scale", frame=f, group=name)


def ground_faint(clip, keyer, act, model):
    """Lift the body wherever the skinned mesh dips below the floor; from the landing on, also
    lower it onto the floor. Moves only the root bone, so every other key stays as it is."""
    scene = bpy.context.scene
    use_action(keyer.arm, act)
    mins = []
    for f in range(clip.frames):
        scene.frame_set(f)
        mins.append(mesh_min_z(model))
    up = ground_offsets(np.array(mins), clip.land_frame)
    root = next(n for n in keyer.body.names if keyer.body.parent[n] is None)
    for f, D in enumerate(clip.deltas):
        T = np.eye(4)
        T[2, 3] = up[f]
        for n in D:
            D[n] = T @ D[n]
    keyer.key(act, clip.deltas, only=[root])
    # how it lies at the end: the lowest vertex is on the floor; the trunk's lowest vertex
    # should be too (a body propped on its knees or hands is crouched, not lying)
    scene.frame_set(clip.frames - 1)
    z = mesh_z(model)
    mask = torso_mask(model, keyer.arm)
    gap = float(z[mask].min() - z.min()) if mask.any() else float("nan")
    return {"lowest_before_mm": round(min(mins) * 1000, 1),
            "lift_max_mm": round(float(up.max()) * 1000, 1),
            "end_lowest_mm": round(float(z.min()) * 1000, 1),
            "end_torso_gap_mm": round(gap * 1000, 1)}


def push_to_nla(arm, actions):
    ad = arm.animation_data
    for tr in list(ad.nla_tracks):
        ad.nla_tracks.remove(tr)
    for act in actions:
        tr = ad.nla_tracks.new()
        tr.name = act.name
        strip = tr.strips.new(act.name, 0, act)
        if hasattr(strip, "action_slot") and strip.action_slot is None and len(act.slots):
            strip.action_slot = act.slots[0]
        act.use_fake_user = True
    use_action(arm, None)


def export_glb(path, objs):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", use_selection=True,
                              export_yup=True, export_animations=True,
                              export_animation_mode="NLA_TRACKS", export_skins=True,
                              export_all_influences=False, export_force_sampling=True,
                              export_frame_step=1, export_anim_slide_to_zero=True)


# ------------------------------------------------------------------ previews
def checker_ground(tile: float, size: float):
    img = bpy.data.images.new("checker", 64, 64)
    px = np.zeros((64, 64, 4), dtype=np.float32)
    yy, xx = np.mgrid[0:64, 0:64]
    on = ((xx // 32) + (yy // 32)) % 2 == 0
    px[..., :3] = np.where(on[..., None], 0.62, 0.42)
    px[..., 3] = 1
    img.pixels.foreach_set(px.ravel())
    mat = bpy.data.materials.new("ground")
    mat.use_nodes = True
    nt = mat.node_tree
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    tex.interpolation = "Closest"
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    nt.links.new(tex.outputs[0], bsdf.inputs[0])
    nt.nodes.active = tex
    bpy.ops.mesh.primitive_plane_add(size=size)
    plane = bpy.context.active_object
    plane.name = "PreviewGround"
    plane.data.materials.append(mat)
    reps = size / (2 * tile)
    for loop in plane.data.uv_layers.active.data:
        loop.uv = (loop.uv[0] * reps, loop.uv[1] * reps)
    return plane


def render_previews(clips, actions, arm, model, body, out: Path, size: int):
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.view_settings.view_transform = "Standard"
    scene.render.resolution_x = scene.render.resolution_y = size
    scene.render.image_settings.file_format = "PNG"
    sh = scene.display.shading
    sh.light = "STUDIO"
    sh.color_type = "TEXTURE"
    sh.show_cavity = True
    sh.cavity_type = "BOTH"
    sh.background_type = "VIEWPORT"
    sh.background_color = (0.86, 0.88, 0.92)
    scene.world = bpy.data.worlds.new("pw")
    tile = 0.5 * body.leg_len
    plane = checker_ground(tile, 60 * body.height)
    cam_data = bpy.data.cameras.new("pcam")
    cam_data.type = "ORTHO"
    cam = bpy.data.objects.new("pcam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    az, el = math.radians(55), math.radians(12)
    d = Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el)))
    made = {}
    for clip, act in zip(clips, actions, strict=True):
        use_action(arm, act)
        lo, hi = np.full(3, np.inf), np.full(3, -np.inf)
        for f in range(0, clip.frames, 3):
            scene.frame_set(f)
            a, b = mesh_box(model)
            lo, hi = np.minimum(lo, a), np.maximum(hi, b)
        centre = Vector(((lo + hi) / 2).tolist())
        cam_data.ortho_scale = float(max(hi - lo)) * 1.25
        cam.location = centre + d * 30 * body.height
        cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
        cam_data.clip_end = 100 * body.height
        folder = out / clip.name
        folder.mkdir(parents=True, exist_ok=True)
        step = max(1, clip.fps // 30)  # previews play at 30 frames a second
        shots = range(0, clip.frames - (1 if clip.loop else 0), step)
        for i, f in enumerate(shots):
            scene.frame_set(f)
            plane.location.y = (clip.speed * f / clip.fps) % (2 * tile)
            scene.render.filepath = str(folder / f"{i:04d}.png")
            bpy.ops.render.render(write_still=True)
        made[clip.name] = {"frames": len(shots), "fps": clip.fps / step}
    bpy.data.objects.remove(plane, do_unlink=True)
    bpy.data.objects.remove(cam, do_unlink=True)
    return made


def main():
    t0 = time.perf_counter()
    o = parse()
    out = o["out"]
    out.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(o["blend"]))
    arm = next(ob for ob in bpy.context.scene.objects if ob.type == "ARMATURE")
    model = next(ob for ob in bpy.context.scene.objects if ob.type == "MESH")
    if not np.allclose(np4(arm.matrix_world), np.eye(4), atol=1e-6):
        raise SystemExit("ANIM_FAIL the armature is moved or turned; the Skeleton step "
                         "always leaves it at the origin")
    template = template_of(arm)
    body = Body(template, [(b.name, b.parent.name if b.parent else None,
                            np.array(b.head_local[:]), np.array(b.tail_local[:]))
                           for b in arm.data.bones])
    clips = make_clips(body)
    if arm.animation_data:
        arm.animation_data.action = None
    keyer = Keyer(arm, body)
    actions, grounded = [], {}
    for clip in clips:
        act = bpy.data.actions.new(clip.name)
        keyer.key(act, clip.deltas)
        if clip.land_frame is not None:
            grounded[clip.name] = ground_faint(clip, keyer, act, model)
        actions.append(act)
    previews = {}
    if o["previews"]:
        previews = render_previews(clips, actions, arm, model, body, o["previews"], o["size"])
    push_to_nla(arm, actions)
    scene = bpy.context.scene
    scene.render.fps = clips[0].fps
    scene.frame_start, scene.frame_end = 0, max(c.frames for c in clips) - 1
    export_glb(out / "animated.glb", [arm, model])
    bpy.ops.wm.save_as_mainfile(filepath=str(out / "animated.blend"), copy=True)
    rep = {
        "template": template, "fps": clips[0].fps, "leg_length_m": round(body.leg_len, 4),
        "height_m": round(body.height, 4), "forward": "-Y (glTF +Z)",
        "legs": [lg.name for lg in body.legs],
        "clips": [{"name": c.name, "frames": c.frames, "seconds": round(c.seconds, 3),
                   "loop": c.loop, "speed_m_s": round(c.speed, 4),
                   "froude": round(c.froude, 3), "cadence_capped": c.capped,
                   "strides_per_s": round(1 / c.gait.seconds, 3) if c.gait else None,
                   "feet_out_of_reach_frames": c.short, "land_frame": c.land_frame}
                  for c in clips],
        "grounding": grounded, "previews": previews, "short_legs": body.short_legs,
        "seconds": round(time.perf_counter() - t0, 1),
    }
    (out / "clips.json").write_text(json.dumps(rep, indent=1))
    print("ANIM_OK", json.dumps({k: rep[k] for k in ("template", "seconds", "short_legs")}))


main()
