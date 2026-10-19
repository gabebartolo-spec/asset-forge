"""Blender (headless) script: Step 2 Clean (design 5.2). Rebuild a raw generated mesh into a
game-ready model: one surface, on budget, one material, one texture.

    blender -b --factory-startup -P blender/clean.py -- RAW.glb OUT_DIR
        --type humanoid|monster|animal --ref REF.png [--height M] [--budget TRIS]
        [--texture PX] [--generator hi3dgen|triposg] [--turn DEG] [--no-sheets]

Writes OUT_DIR/clean.glb, clean.blend, texture.png, report.json and (unless --no-sheets)
OUT_DIR/before/ and OUT_DIR/after/ six-view renders (tools/bakeoff/render_views.py).

What it does, in order (every number is in report.json):
 1. Import, weld, delete floating specks (parts under 1% of the biggest part's faces).
 2. Rebuild: voxel remesh (fuses touching parts into one watertight skin), consistent normals.
 3. Orient: the model is turned about Z to face Blender -Y, which exports as glTF +Z, Godot's
    model front (D-021). Humanoid/monster: the generator's own convention decides (both
    generators output the model with the reference view as its front, which is -Y in Blender
    after the glTF import; GENERATOR_FRONT_YAW below, measured once from the bake-off meshes), the
    outline is never used for front vs back. Animal: the reference is a side view, so only the
    turn that puts the head toward -Y is chosen, by outline, and it must win by a clear margin.
    Origin at the feet (centre of the footprint, lowest point on z = 0), real-world scale.
 4. Decimate (collapse) to the type's triangle budget, smart UV unwrap.
 5. Colour (generators here are geometry only): the reference is projected onto the surfaces that
    face the camera it was drawn from (humanoid/monster: the front, -Y; animal: the creature's
    left side, +X), with a ray-cast test so hidden texels get no paint. Nothing is mirrored. Every
    other texel (back, far side, grazing edges, under-sides) gets a low-frequency colour: a
    normal-weighted Gaussian blend of the projected colour in 3D, never a copy of the picture.
    The result is padded and written to ONE texture on ONE material.
 6. Silhouette check: 1 - IoU of the filled outline against the raw mesh from front, side, top.
"""

import json
import math
import sys
import time
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Vector, bvhtree

BUDGETS = {  # type: (triangles, texture px, default height m, projection direction toward camera)
    "humanoid": (8000, 1024, 1.8, (0.0, -1.0, 0.0)),
    "monster": (8000, 1024, 2.0, (0.0, -1.0, 0.0)),
    "animal": (2000, 512, 0.5, (1.0, 0.0, 0.0)),
}
# Where each generator puts the front of a humanoid/monster (the reference view), as the yaw about
# Z that turns the raw mesh to face Blender -Y (glTF +Z). Measured once on the bake-off meshes
# (docs/audits/clean, 2026-10-20): hi3dgen and triposg humanoid and brute meshes all face -Y, so 0.
GENERATOR_FRONT_YAW = {"hi3dgen": 0.0, "triposg": 0.0}
ANIMAL_MARGIN = 0.10  # best outline turn must beat the second best by this much
GRID = 64  # colour-blend grid cells along the longest side
BLUR_SIGMAS = (3, 6, 12, 24, 48)  # in grid cells; the smallest level that has data is used
SIL_THRESHOLD = 0.08  # silhouette difference (1 - IoU) allowed per view
SIL_RES = 256
FLOATER_FRACTION = 0.01
HERE = Path(__file__).resolve().parent


def parse():
    argv = sys.argv[sys.argv.index("--") + 1:]
    opts = {"raw": Path(argv[0]), "out": Path(argv[1]), "sheets": "--no-sheets" not in argv}

    def get(flag, cast=str, default=None):
        return cast(argv[argv.index(flag) + 1]) if flag in argv else default

    opts["type"] = get("--type", default="humanoid")
    opts["ref"] = get("--ref")
    opts["height"] = get("--height", float)
    opts["budget"] = get("--budget", int)
    opts["texture"] = get("--texture", int)
    opts["turn"] = get("--turn", float)
    opts["generator"] = get("--generator", default="triposg")
    if opts["generator"] not in GENERATOR_FRONT_YAW:
        raise SystemExit(f"--generator must be one of {sorted(GENERATOR_FRONT_YAW)}; measure a new "
                         "generator's front once and add it to GENERATOR_FRONT_YAW")
    opts["voxel_div"] = get("--voxel-div", float, 220.0)
    if opts["type"] not in BUDGETS:
        raise SystemExit(f"--type must be one of {sorted(BUDGETS)}")
    return opts


# ---------------------------------------------------------------- scene helpers

def import_raw(path: Path):
    ext = path.suffix.lower()
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=str(path))
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=str(path))
    elif ext == ".ply":
        bpy.ops.wm.ply_import(filepath=str(path))
    else:
        raise SystemExit(f"unsupported mesh {ext}")
    objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    return join(objs)


def select_only(obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def join(objs):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    if len(objs) > 1:
        bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    obj.rotation_mode = "XYZ"
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return obj


def weld(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    d = max(obj.dimensions) * 1e-5
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=d)
    bm.to_mesh(obj.data)
    bm.free()


def tri_count(obj):
    obj.data.calc_loop_triangles()
    return len(obj.data.loop_triangles)


def verts_np(obj):
    n = len(obj.data.vertices)
    a = np.empty(n * 3, dtype=np.float32)
    obj.data.vertices.foreach_get("co", a)
    return a.reshape(n, 3)


def drop_floaters(obj, fraction=FLOATER_FRACTION):
    """Split into loose parts, delete parts under `fraction` of the biggest part's faces, rejoin.
    Returns (obj, parts_before, parts_removed)."""
    select_only(obj)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.separate(type="LOOSE")
    bpy.ops.object.mode_set(mode="OBJECT")
    parts = [o for o in bpy.context.selected_objects if o.type == "MESH"]
    if obj not in parts:
        parts.append(obj)
    sizes = {o: len(o.data.polygons) for o in parts}
    big = max(sizes.values())
    keep = [o for o in parts if sizes[o] >= fraction * big]
    drop = [o for o in parts if o not in keep]
    for o in drop:
        bpy.data.objects.remove(o, do_unlink=True)
    return join(keep), len(parts), len(drop)


def bounds(verts):
    return verts.min(axis=0), verts.max(axis=0)


def apply_matrix(obj, m):
    obj.data.transform(m)
    obj.data.update()


# ---------------------------------------------------------------- orientation

def load_ref(path):
    img = bpy.data.images.load(str(path))
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(h, w, 4)  # row 0 = bottom
    return px


def ref_mask(ref, erode=0):
    m = ref[..., 3] > 0.5
    for _ in range(erode):
        n = m.copy()
        n[1:] &= m[:-1]
        n[:-1] &= m[1:]
        n[:, 1:] &= m[:, :-1]
        n[:, :-1] &= m[:, 1:]
        m = n
    return m


def crop_resize(mask, n):
    ys, xs = np.where(mask)
    mask = mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    ri = (np.arange(n) * mask.shape[0] / n).astype(int)
    ci = (np.arange(n) * mask.shape[1] / n).astype(int)
    return mask[np.ix_(ri, ci)]


def splat_outline(v, horiz, n=128):
    """Outline of a dense vertex cloud seen along the axis normal to (horiz, z): bounding-box
    normalised, n x n, row 0 = bottom, image right = +horiz."""
    h, z = v[:, horiz], v[:, 2]
    c = ((h - h.min()) / max(np.ptp(h), 1e-9) * (n - 1)).astype(int)
    r = ((z - z.min()) / max(np.ptp(z), 1e-9) * (n - 1)).astype(int)
    g = np.zeros((n, n), bool)
    g[r, c] = True
    for _ in range(2):
        d = g.copy()
        d[1:] |= g[:-1]
        d[:-1] |= g[1:]
        d[:, 1:] |= g[:, :-1]
        d[:, :-1] |= g[:, 1:]
        g = d
    return g


def iou(a, b):
    u = np.logical_or(a, b).sum()
    return float(np.logical_and(a, b).sum() / u) if u else 0.0


def pick_yaw(verts, ref, kind, generator):
    """Yaw (deg, about Z) that makes the creature face -Y. Returns (yaw, table, how)."""
    if kind != "animal":
        return GENERATOR_FRONT_YAW[generator], {}, f"generator convention ({generator})"
    rm = crop_resize(ref_mask(ref), 128)
    table = {}
    for yaw in (0, 90, 180, 270):
        a = math.radians(yaw)
        c, s = math.cos(a), math.sin(a)
        x = verts[:, 0] * c - verts[:, 1] * s
        y = verts[:, 0] * s + verts[:, 1] * c
        v = np.stack([x, y, verts[:, 2]], axis=1)
        # Camera on +X looking -X: image right = +Y, so a -Y-facing animal's head is on the left.
        side = np.stack([v[:, 1], v[:, 0], v[:, 2]], axis=1)
        table[yaw] = round(iou(splat_outline(side, 0), rm), 4)
    ranked = sorted(table.values(), reverse=True)
    if ranked[0] - ranked[1] < ANIMAL_MARGIN:
        raise SystemExit(f"animal head direction is ambiguous (outline match {table}); "
                         "pass --turn DEG")
    return max(table, key=table.get), table, "side outline (profile, head toward -Y)"


# ---------------------------------------------------------------- silhouettes

def render_silhouettes(objs_by_name, centre, scale, work_dir):
    """Filled outline of each object from front/side/top in one fixed world frame."""
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.resolution_x = scene.render.resolution_y = SIL_RES
    scene.render.film_transparent = True
    scene.display.shading.light = "FLAT"
    scene.display.shading.color_type = "SINGLE"
    scene.display.shading.single_color = (1, 1, 1)
    cam_data = bpy.data.cameras.new("silcam")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = scale
    cam = bpy.data.objects.new("silcam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    views = {"front": (0.0, 1.0, 0.0), "side": (-1.0, 0.0, 0.0), "top": (0.0, -0.01, 1.0)}
    out = {n: {} for n in objs_by_name}
    for name, obj in objs_by_name.items():
        for other in objs_by_name.values():
            other.hide_render = other is not obj
        for view, d in views.items():
            d = Vector(d).normalized()
            cam.location = centre + d * 20
            cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
            p = work_dir / f"_sil_{name}_{view}.png"
            scene.render.filepath = str(p)
            bpy.ops.render.render(write_still=True)
            img = bpy.data.images.load(str(p))
            a = np.empty(SIL_RES * SIL_RES * 4, dtype=np.float32)
            img.pixels.foreach_get(a)
            out[name][view] = a.reshape(SIL_RES, SIL_RES, 4)[..., 3] > 0.5
            bpy.data.images.remove(img)
            p.unlink()
    for other in objs_by_name.values():
        other.hide_render = False
    bpy.data.objects.remove(cam, do_unlink=True)
    return out


# ---------------------------------------------------------------- colour bake

def uv_unwrap(obj):
    select_only(obj)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.004)
    bpy.ops.object.mode_set(mode="OBJECT")


MIN_FACING = 0.2   # a texel must face the reference camera at least this much to be projected
FULL_FACING = 0.6  # ...and is fully trusted from here on


def gaussian_fft(shape, sigma):
    ker = 1.0
    for ax, n in enumerate(shape):
        f = np.fft.fftfreq(n) if ax < len(shape) - 1 else np.fft.rfftfreq(n)
        g = np.exp(-2 * np.pi ** 2 * sigma ** 2 * f ** 2)
        ker = ker * g.reshape([-1 if i == ax else 1 for i in range(len(shape))])
    return ker


def blend_field(p, colour, alpha, co):
    """Low-frequency colour at every point p: normal-weighted (alpha) Gaussian average of the
    projected colour in a 3D grid, using the smallest blur that reaches data. Returns (n, 3)."""
    lo = co.min(axis=0)
    cell = max(np.ptp(co, axis=0)) / GRID
    pad = int(BLUR_SIGMAS[-1] * 2)
    shape = tuple(int(np.ceil(np.ptp(co[:, i]) / cell)) + 1 + 2 * pad for i in range(3))
    idx = np.clip(((p - lo) / cell).astype(int) + pad, 0, np.array(shape) - 1)
    flat = np.ravel_multi_index(idx.T, shape)
    wsum = np.bincount(flat, weights=alpha, minlength=int(np.prod(shape))).reshape(shape)
    csum = np.stack([np.bincount(flat, weights=alpha * colour[:, c],
                                 minlength=int(np.prod(shape))).reshape(shape) for c in range(3)])
    out = np.full((len(p), 3), np.nan)
    for sg in BLUR_SIGMAS:
        ker = gaussian_fft(shape, sg)
        bw = np.fft.irfftn(np.fft.rfftn(wsum) * ker, s=shape)
        bc = [np.fft.irfftn(np.fft.rfftn(csum[c]) * ker, s=shape) for c in range(3)]
        wv = bw[tuple(idx.T)]
        ok = np.isnan(out[:, 0]) & (wv > 0.01 * bw.max())
        for c in range(3):
            out[ok, c] = bc[c][tuple(idx.T)][ok] / wv[ok]
    out[np.isnan(out[:, 0])] = 0.5
    return out


def bake_colour(obj, ref, d0, size):
    """Project `ref` onto obj (see module docstring). Returns (RGBA array, stats)."""
    me = obj.data
    me.calc_loop_triangles()
    uvl = me.uv_layers.active.data
    tris = me.loop_triangles
    nt = len(tris)
    vi = np.empty(nt * 3, np.int32)
    li = np.empty(nt * 3, np.int32)
    tris.foreach_get("vertices", vi)
    tris.foreach_get("loops", li)
    vi, li = vi.reshape(nt, 3), li.reshape(nt, 3)
    co = verts_np(obj).astype(np.float64)
    uvs = np.empty(len(me.loops) * 2, np.float32)
    uvl.foreach_get("uv", uvs)
    uvs = uvs.reshape(-1, 2)[li].astype(np.float64) * size  # (nt,3,2) in texels
    P = co[vi]  # (nt,3,3)
    N = np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])
    N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)

    pos = np.zeros((size, size, 3))
    nrm = np.zeros((size, size, 3))
    cov = np.zeros((size, size), bool)
    for t in range(nt):
        a, b, c = uvs[t]
        x0, x1 = int(max(min(a[0], b[0], c[0]) - 1, 0)), int(min(max(a[0], b[0], c[0]) + 1, size))
        y0, y1 = int(max(min(a[1], b[1], c[1]) - 1, 0)), int(min(max(a[1], b[1], c[1]) + 1, size))
        if x1 <= x0 or y1 <= y0:
            continue
        den = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(den) < 1e-12:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1) + 0.5, np.arange(y0, y1) + 0.5)
        w0 = ((b[1] - c[1]) * (gx - c[0]) + (c[0] - b[0]) * (gy - c[1])) / den
        w1 = ((c[1] - a[1]) * (gx - c[0]) + (a[0] - c[0]) * (gy - c[1])) / den
        w2 = 1 - w0 - w1
        m = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
        if not m.any():
            continue
        p = w0[m, None] * P[t, 0] + w1[m, None] * P[t, 1] + w2[m, None] * P[t, 2]
        ys, xs = np.nonzero(m)
        pos[y0 + ys, x0 + xs] = p
        nrm[y0 + ys, x0 + xs] = N[t]
        cov[y0 + ys, x0 + xs] = True

    # Map the mesh's outline box in the camera plane onto the reference's outline box.
    f = -np.array(d0, float)
    right = np.cross(f, [0, 0, 1.0])
    right /= np.linalg.norm(right)
    sv = co @ right
    zv = co[:, 2]
    ys, xs = np.where(ref_mask(ref))
    rh, rw = ref.shape[:2]
    rx0, rx1, ry0, ry1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    mask = ref_mask(ref, erode=3)

    ty, tx = np.nonzero(cov)
    p = pos[ty, tx]
    n = nrm[ty, tx]
    w = n @ np.array(d0, float)  # > 0: faces the camera the reference was drawn from
    cand = w >= MIN_FACING
    bvh = bvhtree.BVHTree.FromObject(obj, bpy.context.evaluated_depsgraph_get())
    eps = max(np.ptp(co, axis=0)) * 1e-3
    colour = np.zeros((len(ty), 4))
    known = np.zeros(len(ty), bool)
    d_vec = Vector(d0)
    for k in np.nonzero(cand)[0]:
        origin = Vector(p[k] + n[k] * eps)
        if bvh.ray_cast(origin, d_vec)[0] is None:  # not hidden from the camera
            known[k] = True
    q = p[known]
    u = (q @ right - sv.min()) / max(np.ptp(sv), 1e-9)
    v = (q[:, 2] - zv.min()) / max(np.ptp(zv), 1e-9)
    px = rx0 + u * (rx1 - rx0 - 1)
    py = ry0 + v * (ry1 - ry0 - 1)
    ix = np.clip(np.rint(px).astype(int), 0, rw - 1)
    iy = np.clip(np.rint(py).astype(int), 0, rh - 1)
    inside = mask[iy, ix]
    rgb = ref[iy, ix, :3]
    kk = np.nonzero(known)[0]
    colour[kk[inside], :3] = rgb[inside]
    known[kk[~inside]] = False  # outline background: treat as unpainted
    # Trust in a projected texel falls off towards the silhouette (stretched pixels there).
    alpha = np.where(known, np.clip((w - MIN_FACING) / (FULL_FACING - MIN_FACING), 0, 1), 0.0)
    painted = int(known.sum())

    # Low-frequency colour for everything else, and under the grazing edges of the painted part.
    field = blend_field(p, colour[:, :3], alpha, co)
    colour[:, :3] = alpha[:, None] * colour[:, :3] + (1 - alpha[:, None]) * field
    colour[:, 3] = 1.0

    img = np.zeros((size, size, 4), np.float32)
    img[..., :3] = 0.5
    img[ty, tx] = colour
    # Pad the islands (mip/filter bleed): grow painted texels outwards 8 px.
    have = cov.copy()
    for _ in range(8):
        acc = np.zeros((size, size, 4), np.float32)
        cnt = np.zeros((size, size), np.float32)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            h = np.roll(have, (dy, dx), (0, 1))
            acc += np.roll(img, (dy, dx), (0, 1)) * h[..., None]
            cnt += h
        grow = (~have) & (cnt > 0)
        img[grow] = acc[grow] / cnt[grow, None]
        have |= grow
    img[..., 3] = 1.0
    stats = {
        "texels_covered": int(cov.sum()),
        "texels_projected": painted,
        "texels_projected_full_trust": int((alpha >= 1).sum()),
        "texels_low_frequency": int(len(ty) - painted),
        "mirrored_far_side": False,
    }
    info = {"facing": w, "pos": p, "colour": colour[:, :3], "projected": known}
    return img, stats, info


def make_material(obj, img_array, out_dir, size):
    img = bpy.data.images.new("clean_colour", size, size, alpha=False)
    img.pixels.foreach_set(img_array.ravel())
    img.filepath_raw = str(out_dir / "texture.png")
    img.file_format = "PNG"
    img.save()
    img.pack()
    mat = bpy.data.materials.new("clean")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.9
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    return img


# ---------------------------------------------------------------- main

SHEET_VIEWS = {  # name: (azimuth deg around Z from the front, elevation deg)
    "front": (0, 5), "back": (180, 5), "left": (90, 5), "right": (-90, 5),
    "three_quarter": (35, 20), "top": (0, 89.5),
}
SHEET_RES = 512


def export_glb(obj, path):
    """glTF is Y-up, model front +Z; Blender -Y (where Clean puts the face) maps there."""
    select_only(obj)
    bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", use_selection=True,
                              export_yup=True)


def render_sheets(raw, clean, out):
    """Six views of raw (clay) and clean (clay, colour) from ONE camera set: the raw and clean
    meshes share a world frame, so a part that Clean lost is missing in the same pixels."""
    scene = bpy.context.scene
    lo = np.minimum(verts_np(raw).min(axis=0), verts_np(clean).min(axis=0))
    hi = np.maximum(verts_np(raw).max(axis=0), verts_np(clean).max(axis=0))
    centre = Vector(((lo + hi) / 2).tolist())
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.resolution_x = scene.render.resolution_y = SHEET_RES
    scene.render.film_transparent = False
    sh = scene.display.shading
    sh.light = "STUDIO"
    sh.show_cavity = True
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
    jobs = (("before", raw, "clay", "SINGLE"), ("after", clean, "clay", "SINGLE"),
            ("after", clean, "colour", "TEXTURE"))
    for folder, obj, shade, ctype in jobs:
        for other in (raw, clean):
            other.hide_render = other is not obj
        sh.color_type = ctype
        sh.single_color = (0.75, 0.75, 0.75)
        (out / folder).mkdir(parents=True, exist_ok=True)
        for view, (az, el) in SHEET_VIEWS.items():
            a, e = math.radians(az), math.radians(el)
            d = Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)))
            cam.location = centre + d * 20
            cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
            scene.render.filepath = str(out / folder / f"{view}_{shade}.png")
            bpy.ops.render.render(write_still=True)
    for other in (raw, clean):
        other.hide_render = False
    bpy.data.objects.remove(cam, do_unlink=True)


def main():
    t_all = time.perf_counter()
    o = parse()
    kind = o["type"]
    budget_tris, tex_px, def_h, d0 = BUDGETS[kind]
    budget_tris = o["budget"] or budget_tris
    tex_px = o["texture"] or tex_px
    height = o["height"] or def_h
    out = o["out"]
    out.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    timings = {}
    report = {"type": kind, "input": o["raw"].name, "generator_input_only": True}

    def lap(name, t0):
        timings[name] = round(time.perf_counter() - t0, 2)

    ref = load_ref(o["ref"]) if o["ref"] else None
    if ref is None:
        raise SystemExit("--ref is required: the generators are geometry only and colour comes "
                         "from the reference picture")

    t0 = time.perf_counter()
    raw = import_raw(o["raw"])
    raw_tris = tri_count(raw)
    raw.name = "raw"
    work = raw.copy()
    work.data = raw.data.copy()
    work.name = "clean"
    bpy.context.scene.collection.objects.link(work)
    weld(work)
    work, parts_before, floaters = drop_floaters(work)
    lap("import_and_weld", t0)

    t0 = time.perf_counter()
    select_only(work)
    work.data.remesh_voxel_size = max(work.dimensions) / o["voxel_div"]
    bpy.ops.object.voxel_remesh()
    remesh_tris = tri_count(work)
    lap("voxel_remesh", t0)

    # Orientation, scale, feet. The same matrix goes onto the raw copy for the outline check.
    t0 = time.perf_counter()
    v = verts_np(work)
    yaw, yaw_table, yaw_how = pick_yaw(v, ref, kind, o["generator"])
    if o["turn"] is not None:
        yaw = o["turn"]
    from mathutils import Matrix
    rot = Matrix.Rotation(math.radians(yaw), 4, "Z")
    apply_matrix(work, rot)
    lo, hi = bounds(verts_np(work))
    s = height / max(hi[2] - lo[2], 1e-9)
    centre_xy = ((lo + hi) / 2)[:2]
    m = Matrix.Scale(s, 4) @ Matrix.Translation((-centre_xy[0], -centre_xy[1], -lo[2]))
    apply_matrix(work, m)
    apply_matrix(raw, m @ rot)
    lap("orient_scale", t0)

    t0 = time.perf_counter()
    select_only(work)
    bm = bmesh.new()
    bm.from_mesh(work.data)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(work.data)
    bm.free()
    tris = tri_count(work)
    for _ in range(5):
        if tris <= budget_tris:
            break
        mod = work.modifiers.new("dec", "DECIMATE")
        mod.decimate_type = "COLLAPSE"
        mod.ratio = min(0.999, budget_tris * 0.97 / tris)
        bpy.ops.object.modifier_apply(modifier=mod.name)
        tris = tri_count(work)
    work, parts_mid, floaters2 = drop_floaters(work)
    select_only(work)
    bm = bmesh.new()
    bm.from_mesh(work.data)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(work.data)
    bm.free()
    work.name = "clean"
    try:
        bpy.ops.object.shade_auto_smooth(angle=math.radians(50))
    except Exception:
        bpy.ops.object.shade_smooth()
    lap("decimate", t0)

    t0 = time.perf_counter()
    uv_unwrap(work)
    lap("uv_unwrap", t0)

    t0 = time.perf_counter()
    img_arr, bake_stats, _ = bake_colour(work, ref, d0, tex_px)
    img = make_material(work, img_arr, out, tex_px)
    lap("colour_bake", t0)

    # Silhouette check against the raw mesh in the same world frame.
    t0 = time.perf_counter()
    rlo, rhi = bounds(verts_np(raw))
    centre = Vector(((rlo + rhi) / 2).tolist())
    scale = float(max(rhi - rlo)) * 1.2
    sil = render_silhouettes({"raw": raw, "clean": work}, centre, scale, out)
    diff = {k: round(1 - iou(sil["raw"][k], sil["clean"][k]), 4) for k in ("front", "side", "top")}
    lap("silhouette", t0)

    # Export.
    t0 = time.perf_counter()
    # Sheets first: raw and clean still share one world frame here.
    if o["sheets"]:
        ts = time.perf_counter()
        render_sheets(raw, work, out)
        timings["sheets"] = round(time.perf_counter() - ts, 2)
    bpy.data.objects.remove(raw, do_unlink=True)
    select_only(work)
    export_glb(work, out / "clean.glb")
    bpy.ops.wm.save_as_mainfile(filepath=str(out / "clean.blend"))
    lap("export", t0)

    final_dims = [round(x, 4) for x in work.dimensions]
    report.update({
        "triangles": tri_count(work),
        "triangle_budget": budget_tris,
        "materials": len(work.material_slots),
        "texture": {"width": img.size[0], "height": img.size[1], "max_px": tex_px},
        "raw_triangles": raw_tris,
        "voxel_remesh_triangles": remesh_tris,
        "loose_parts": {"raw_after_weld": parts_before, "floaters_deleted": floaters,
                        "after_clean": parts_mid - floaters2 if parts_mid else 1,
                        "floaters_deleted_after_decimate": floaters2},
        "silhouette": {
            "measure": "1 - IoU of the filled outline (256 px, fixed world frame) of clean vs raw",
            "threshold": SIL_THRESHOLD, **diff},
        "dimensions_m": final_dims,
        "height_m": round(work.dimensions[2], 4),
        "origin": "feet (footprint centre, lowest point at z=0)",
        "forward": "-Y (glTF +Z, Godot model front, D-021)",
        "orientation": {"turn_deg": yaw, "decided_by": yaw_how, "generator": o["generator"],
                        "outline_iou_by_turn": yaw_table},
        "colour_route": {"camera_toward": list(d0), "reference": o["ref"], **bake_stats},
        "timings_s": timings,
    })
    report["timings_s"]["total"] = round(time.perf_counter() - t_all, 2)
    (out / "report.json").write_text(json.dumps(report, indent=2))
    print("REPORT", json.dumps({k: report[k] for k in ("triangles", "materials", "texture",
                                                        "silhouette")}))


if __name__ == "__main__":
    main()
