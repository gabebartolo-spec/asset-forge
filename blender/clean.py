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
 5. Colour (generators here are geometry only), all in bake_colour:
    - Head-to-head (humanoid/monster): the picture's head (highest compact mass) is shifted onto the
      model's head (top slice of the mesh); a second cue pair (darkest facial features vs the most
      forward blob) must then agree within HEAD_AGREE head widths, else no face (low frequency).
    - Animals: specks (eye, nose, white patch) never seed the fill, and mirrored sources that land
      off the surface (turned head) or texels facing away from the camera get no specks.
    - Registration: the reference outline is fitted to the model's outline seen from the reference
      camera (bbox scale per axis, then a smoothed per-row sideways shift), so a head drawn off
      centre lands on the geometric head. If the model's head band and the picture's differ too
      much in width (HEAD_WIDTH_RATIO) the head gets low-frequency colour instead of a misplaced
      face.
    - Projection onto surfaces facing the reference camera (humanoid/monster: front, -Y; animal:
      the left side, +X) with a ray test. Side views also mirror LEFT-RIGHT across the body's
      sagittal plane (x only, never front-to-back), so the far flank gets the eye and the face.
    - Fill (back, grazing edges, under-sides): normalised diffusion over the mesh graph from
      well-facing, sunlit vertices (grazing under 70 deg and shadow-dark pixels are ignored),
      interpolated across triangles; the picture fades into it over FEATHER x height of surface.
    The result is padded and written to ONE texture on ONE material; report.json records the
    albedo's luminance and saturation per height band against the reference.
 6. Silhouette check: 1 - IoU of the filled outline against the raw mesh from front, side, top.
"""

import contextlib
import json
import math
import os
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
    # method B colour: --mv-python EXE --mv-src DIR [--hf-home DIR], or --mv-views DIR (reuse)
    opts["mv"] = None
    if "--mv-views" in argv:
        opts["mv"] = {"views": get("--mv-views")}
    elif "--mv-python" in argv:
        opts["mv"] = {"python": get("--mv-python"), "src": get("--mv-src"),
                      "hf_home": get("--hf-home"), "gpu_lock": get("--gpu-lock")}
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
        raise SystemExit("Could not tell which way the animal's head points from the picture. "
                         "Use a side-on picture with the whole animal in view, then press Redo. "
                         f"(outline match by turn: {table}; developers: --turn DEG)")
    return max(table, key=table.get), table, "side outline (profile, head toward -Y)"


# ---------------------------------------------------------------- solid rebuild

# Some generators (Hi3DGen) return a thin hollow shell: voxel remesh keeps it hollow, so about half
# of the triangle budget and texture goes on an inside wall nobody sees. Others (TripoSG fox) leave
# a limb a few mm off the body: two parts. Both are fixed on a coarse voxel copy of the remeshed
# surface: the hollow is filled and a detached part is bridged to the body, then the filler is fused
# in by a second voxel remesh (the outer surface is untouched).
SOLID_N = 128            # voxels along the longest side
SOLID_ESCAPE = 3         # a free voxel with a clear straight line to the border in at least this
                         # many of the 26 grid directions is outside; the rest is hollow
SOLID_MIN_CAVITY = 0.10  # hollow share of (solid + hollow) from which it is filled (measured:
                         # hollow Hi3DGen shells 0.31-0.61, every solid model <= 0.017)
SOLID_FILL_PASSES = 4    # fill, count escapes again, fill what is now enclosed (closes a mouth)
SOLID_MIN_PART = 0.002   # parts smaller than this share of the solid are left to drop_floaters
SOLID_MAX_GAP = 12       # voxels: a part further than this from the body is not bridged
SOLID_BRIDGE_R = 2.5     # voxels: radius of the cylinder painted across a gap
SOLID_BRIDGE_EXT = 2     # voxels: the cylinder runs this far into the part and the body


def _dil(m, k=1):
    for _ in range(k):
        d = m.copy()
        d[1:] |= m[:-1]
        d[:-1] |= m[1:]
        d[:, 1:] |= m[:, :-1]
        d[:, :-1] |= m[:, 1:]
        d[:, :, 1:] |= m[:, :, :-1]
        d[:, :, :-1] |= m[:, :, 1:]
        m = d
    return m


def _shift2(m, du, dv):
    """2D shift of m by (du, dv) cells (each -1, 0 or 1); cells shifted in from outside are True."""
    out = np.ones_like(m)
    su = slice(None) if du == 0 else (slice(0, -1) if du == 1 else slice(1, None))
    tu = slice(None) if du == 0 else (slice(1, None) if du == 1 else slice(0, -1))
    sv = slice(None) if dv == 0 else (slice(0, -1) if dv == 1 else slice(1, None))
    tv = slice(None) if dv == 0 else (slice(1, None) if dv == 1 else slice(0, -1))
    out[su, sv] = m[tu, tv]
    return out


def escape_count(solid):
    """For each voxel, in how many of the 26 grid directions a straight line reaches the grid's
    border without crossing solid (solid voxels get 0). One sweep of 2D slices per direction."""
    free = ~solid
    cnt = np.zeros(solid.shape, np.uint8)
    for d in [(x, y, z) for x in (-1, 0, 1) for y in (-1, 0, 1) for z in (-1, 0, 1) if x or y or z]:
        ax = next(a for a in range(3) if d[a])
        f = np.moveaxis(free, ax, 0)
        du, dv = [d[a] for a in range(3) if a != ax]
        e = np.empty_like(f)
        order = range(f.shape[0] - 1, -1, -1) if d[ax] > 0 else range(f.shape[0])
        prev = None
        for i in order:
            # voxel p escapes if p + d escapes (p + d outside the grid counts as escaped)
            nxt = np.ones_like(f[i]) if prev is None else _shift2(prev, du, dv)
            e[i] = f[i] & nxt
            prev = e[i]
        cnt += np.moveaxis(e, 0, ax)
    return cnt


def voxel_solid(obj, n=SOLID_N):
    """Inside of obj's closed surface on a voxel grid (ray parity along x, y and z, majority vote).
    Returns (solid (nx,ny,nz) bool, origin, voxel size); a 2-voxel empty border is added."""
    bvh = bvhtree.BVHTree.FromObject(obj, bpy.context.evaluated_depsgraph_get())
    co = verts_np(obj).astype(np.float64)
    lo, hi = co.min(axis=0), co.max(axis=0)
    h = float(max(hi - lo)) / n
    pad = 2 + SOLID_MAX_GAP
    org = lo - pad * h
    shape = tuple(int(np.ceil((hi[a] - lo[a]) / h)) + 2 * pad for a in range(3))
    votes = np.zeros(shape, np.uint8)
    span = float(max(hi - lo)) * 4
    for ax in range(3):
        a1, a2 = [a for a in range(3) if a != ax]
        cen = [org[a] + (np.arange(shape[a]) + 0.5) * h for a in range(3)]
        d = Vector(tuple(1.0 if a == ax else 0.0 for a in range(3)))
        for i in range(shape[a1]):
            for j in range(shape[a2]):
                p = [0.0, 0.0, 0.0]
                p[a1], p[a2], p[ax] = cen[a1][i], cen[a2][j], org[ax] - h
                o = Vector(p)
                hits = []
                while True:
                    loc, _n, _i, dist = bvh.ray_cast(o, d, span)
                    if loc is None:
                        break
                    t = loc[ax]
                    if not hits or t - hits[-1] > 1e-7 * span:
                        hits.append(t)
                    o = loc + d * (1e-6 * span)
                if len(hits) < 2:
                    continue
                k = np.searchsorted(np.array(hits), cen[ax], side="right")
                inside = (k % 2) == 1
                idx = [slice(None)] * 3
                idx[a1], idx[a2] = i, j
                votes[tuple(idx)] += inside.astype(np.uint8)
    return votes >= 2, org, h


def _label_big(solid, min_share=SOLID_MIN_PART, most=8):
    """Connected parts of `solid` of at least min_share of it, biggest first (bool grids)."""
    idx = np.full(solid.shape, -1, np.int64)
    n = int(solid.sum())
    idx[solid] = np.arange(n)
    pairs = []
    for ax in range(3):
        a = np.moveaxis(idx, ax, 0)
        both = (a[1:] >= 0) & (a[:-1] >= 0)
        pairs.append(np.stack([a[1:][both], a[:-1][both]], 1))
    e = np.concatenate(pairs)
    lab = np.arange(n)
    while True:  # union-find: hook the larger root onto the smaller, then jump pointers
        li, lj = lab[e[:, 0]], lab[e[:, 1]]
        diff = li != lj
        if not diff.any():
            break
        lab[np.maximum(li, lj)[diff]] = np.minimum(li, lj)[diff]
        while True:
            nxt = lab[lab]
            if (nxt == lab).all():
                break
            lab = nxt
    roots, size = np.unique(lab, return_counts=True)
    order = np.argsort(-size)
    parts = []
    for r in roots[order][:most]:
        if size[roots == r][0] < min_share * max(n, 1):
            break
        m = np.zeros_like(solid)
        m[solid] = lab == r
        parts.append(m)
    return parts


def _paint_cylinder(mask, a, b, r, ext):
    """Set the voxels within r of the segment a-b, extended by ext voxels past both ends."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    ab = b - a
    ln = float(np.linalg.norm(ab))
    u = ab / ln if ln > 0 else np.array([0.0, 0.0, 1.0])
    a, b = a - u * ext, b + u * ext
    lo = np.maximum(np.floor(np.minimum(a, b) - r).astype(int), 0)
    hi = np.minimum(np.ceil(np.maximum(a, b) + r).astype(int) + 1, mask.shape)
    g = np.stack(np.meshgrid(*[np.arange(lo[k], hi[k]) for k in range(3)], indexing="ij"), -1)
    t = np.clip(((g - a) @ u) / max(float(np.linalg.norm(b - a)), 1e-9), 0, 1)
    dist = np.linalg.norm(g - (a + t[..., None] * (b - a)), axis=-1)
    mask[lo[0]:hi[0], lo[1]:hi[1], lo[2]:hi[2]] |= dist <= r


def solid_filler(solid):
    """Voxels to add: the hollow and a cylinder from each detached part to the body across their
    closest approach. Returns (filler, info). An open hollow has voxels near its mouth that still
    see out; the escape count is taken again after each fill, so the mouth closes in a few passes.
    """
    info = {}
    filled = solid.copy()
    for k in range(SOLID_FILL_PASSES):
        free = ~filled
        hollow = free & (escape_count(filled) < SOLID_ESCAPE)
        if k == 0:
            cav = float(hollow.sum() / max(int(solid.sum() + hollow.sum()), 1))
            info["hollow_share"] = round(cav, 4)
            if cav < SOLID_MIN_CAVITY:
                break
        if hollow.sum() < SOLID_MIN_PART * solid.sum():
            break
        filled |= hollow
    filler = filled & ~solid
    filler |= _dil(filler, 1) & solid  # reach one voxel into the walls so the remesh fuses them
    parts = _label_big(filled)
    info["parts_voxels"] = [int(p.sum()) for p in parts]
    bridges = []
    if len(parts) > 1:
        body = parts[0]
        for part in parts[1:]:
            grown = part
            for k in range(1, SOLID_MAX_GAP + 1):
                grown = _dil(grown)
                touch = grown & body
                if touch.any():
                    c = np.argwhere(touch)[0]
                    pv = np.argwhere(part)
                    pa = pv[np.argmin(((pv - c) ** 2).sum(1))]
                    bv = np.argwhere(body & _dil(part, k + 1))
                    pb = bv[np.argmin(((bv - pa) ** 2).sum(1))]
                    cyl = np.zeros_like(solid)
                    _paint_cylinder(cyl, pa, pb, SOLID_BRIDGE_R, SOLID_BRIDGE_EXT)
                    filler |= cyl & ~filled
                    bridges.append(round(float(np.linalg.norm(pb - pa)), 1))
                    body = body | part | cyl
                    break
    info["bridges_gap_voxels"] = bridges
    info["parts_after"] = len(_label_big(solid | filler))
    info["filler_voxels"] = int(filler.sum())
    return filler, info


def voxel_box_mesh(mask, org, h, name="filler"):
    """Closed mesh of the voxel blocks in `mask` (outward quads on every exposed face)."""
    nx, ny, nz = mask.shape
    m = np.pad(mask, 1)
    quads = []
    for ax in range(3):
        a = np.diff(m.astype(np.int8), axis=ax)
        for sgn in (1, -1):  # 1: empty->solid (face looks toward -ax), -1: solid->empty (+ax)
            idx = np.argwhere(a == sgn)
            if not len(idx):
                continue
            base = idx.astype(np.int64)
            base[:, ax] += 1                       # corner plane along ax (in padded coords)
            base -= 1                              # back to unpadded corner coords
            base[:, ax] = idx[:, ax]
            u, v = [b for b in range(3) if b != ax]
            c0 = base.copy()
            c1 = base.copy()
            c1[:, u] += 1
            c2 = c1.copy()
            c2[:, v] += 1
            c3 = base.copy()
            c3[:, v] += 1
            q = np.stack([c0, c1, c2, c3], axis=1)
            if (sgn == -1) != (ax != 1):  # u x v is +ax except for ax = y: flip to face outward
                q = q[:, ::-1]
            quads.append(q)
    q = np.concatenate(quads)
    flat = q.reshape(-1, 3)
    key = (flat[:, 0] * (ny + 3) + flat[:, 1]) * (nz + 3) + flat[:, 2]
    uniq, inv = np.unique(key, return_inverse=True)
    corners = np.zeros((len(uniq), 3))
    corners[inv] = flat
    verts = org + corners * h
    faces = inv.reshape(-1, 4)
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts.tolist(), [], faces.tolist())
    me.update()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def make_solid(work, voxel_size):
    """Fill a hollow shell, bridge detached parts (block comment above). Returns (obj, info)."""
    t0 = time.perf_counter()
    solid, org, h = voxel_solid(work)
    filler, info = solid_filler(solid)
    info["voxel_size"] = round(h, 6)
    if filler.any():
        ob = voxel_box_mesh(filler, org, h)
        work = join([work, ob])
        select_only(work)
        work.data.remesh_voxel_size = voxel_size
        bpy.ops.object.voxel_remesh()
    info["seconds"] = round(time.perf_counter() - t0, 2)
    return work, info


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


MIN_FACING = 0.34  # cos 70 deg: a surface turned more than 70 deg from the camera is grazing
FULL_FACING = 0.70  # fully trusted from here (cos 45 deg)
SHADOW_REL = 0.55   # fill ignores reference pixels darker than this x their height-band median
BANDS = 8           # height bands for the shadow median
HEAD_BAND = 0.16    # top fraction of the height treated as the head for the registration gate
# model head-band width / reference head-band width allowed (squeeze to 2.5x, stretch to 2x)
HEAD_WIDTH_RATIO = (0.4, 2.0)
FEATHER = 0.05      # projected-to-fill seam width, as a fraction of the height (surface distance)
REG_ROWS = 64
# Head-to-head registration (humanoid/monster front projection). The head is found in the picture
# and on the model by features, not by outline: reference = the highest compact mass of the
# silhouette, model = the top slice of the mesh; a second, independent pair (the darkest facial
# features in the picture, the most forward blob of the model's upper body) must agree after the
# shift, within HEAD_AGREE head widths, or no face is painted.
HEAD_TOP_SLICE = 0.08     # model: top fraction of the height whose centre is the head's centre
HEAD_FULL = 0.18          # rows (from the top, of the height) shifted fully onto the head
HEAD_FADE = 0.34          # ... fading back to the outline fit by here (shoulders, torso)
HEAD_WIDTH_OF_H = 0.16    # nominal head width as a fraction of the figure height
HEAD_AGREE = 0.25         # allowed cue disagreement after registration, in head widths
# Animals. A speck (eye, nose, an ear's inner mark) is a SMALL connected dark or white component of
# the picture: under SPECK_AREA of the silhouette. Large dark or white regions (black socks, a
# white chest or tail tip) are not specks and project as they are. Specks are never used by the
# fill, and only painted where the surface faces the camera (not onto the far flank or the back).
SPECK_AREA = 0.0025
# Neutral (white/grey) sources fill the neutral region from their brightest, well-lit pixels
# (weight luma^NEUTRAL_POWER), where most of the nearby sources are neutral: averaging a white
# chest with its shadowed facets and orange neighbours gives grey-mauve.
OUTLINE_BLEED = 24    # animals: px the picture's colours grow past its outline
GRAZE_MIN, GRAZE_TRUST = -MIN_FACING, 0.5
SPECK_DARK_LUMA = 0.32
NEUTRAL_LUMA_MIN = 0.30
NEUTRAL_POWER = 4
NEUTRAL_SHARE = (0.4, 0.6)   # neutral share of the nearby source weight: none .. all brightest fill
NEUTRAL_ITERS = 12
MIRROR_SNAP = 0.02   # mirrored source must land within this x height of the surface for specks
SPECK_FULL = (0.5, 0.7)    # facing cos from which the cap lifts completely
HEAD_DARK = 0.04          # picture: darkest fraction of the head box taken as the face features
MIRROR_DIRS = ((1.0, 0.0, 0.0),)  # camera directions that are side views (animals)
# Outline warp (animals, side view): the picture's outline is fitted onto the model's outline seen
# from the reference camera by a smooth 2D displacement (non-rigid ICP on the two contours), not by
# per-row sideways shifts only: a bird whose beak sits lower on the model, or a fox whose legs
# stand further forward, then has the picture's beak and legs land on the model's.
WARP_GRID = 128          # mask resolution of both outlines (bounding-box normalised)
WARP_NODES = 16          # control nodes per side of the displacement grid (bilinear)
WARP_ITERS = 30
WARP_SMOOTH = (30.0, 1.0)  # smoothness weight, annealed from the first to the second value
WARP_CLOUD = 60000       # surface points used for the model's outline


def luma(c):
    return c[..., 0] * 0.2126 + c[..., 1] * 0.7152 + c[..., 2] * 0.0722


def sat(c):
    mx = c.max(axis=-1)
    return np.where(mx > 1e-6, (mx - c.min(axis=-1)) / np.maximum(mx, 1e-6), 0.0)


def ramp(w):
    return np.clip((w - MIN_FACING) / (FULL_FACING - MIN_FACING), 0, 1)


def smooth_rows(a, sigma):
    """Gaussian smooth of a 1D array with NaN holes (holes interpolated first)."""
    x = np.arange(len(a))
    ok = ~np.isnan(a)
    if not ok.any():
        return np.zeros_like(a)
    a = np.interp(x, x[ok], a[ok])
    k = np.exp(-0.5 * (np.arange(-int(3 * sigma) - 1, int(3 * sigma) + 2) / sigma) ** 2)
    pad = len(k) // 2
    ap = np.pad(a, pad, mode="edge")
    return np.convolve(ap, k / k.sum(), mode="valid")


def row_extents(sn, vn, rows):
    r = np.minimum((vn * rows).astype(int), rows - 1)
    lo = np.full(rows, np.inf)
    hi = np.full(rows, -np.inf)
    np.minimum.at(lo, r, sn)
    np.maximum.at(hi, r, sn)
    bad = ~np.isfinite(lo)
    lo[bad] = np.nan
    hi[bad] = np.nan
    return lo, hi


def _grow(m, k=1):
    for _ in range(k):
        d = m.copy()
        d[1:] |= m[:-1]
        d[:-1] |= m[1:]
        d[:, 1:] |= m[:, :-1]
        d[:, :-1] |= m[:, 1:]
        m = d
    return m


def _shrink(m, k=1):
    return ~_grow(~m, k)


def warp_mask(uv, n=WARP_GRID):
    """Filled outline of points uv (n,2) in [0,1]^2 (v up): splat, close."""
    g = np.zeros((n, n), bool)
    iy = np.clip((uv[:, 1] * n).astype(int), 0, n - 1)
    ix = np.clip((uv[:, 0] * n).astype(int), 0, n - 1)
    g[iy, ix] = True
    return _shrink(_grow(g, 2), 2)


def warp_contour(m):
    ys, xs = np.nonzero(m & ~_shrink(m, 1))
    return np.stack([(xs + 0.5) / m.shape[1], (ys + 0.5) / m.shape[0]], axis=1)


def warp_weights(x, c=WARP_NODES):
    """Bilinear weights of points x (n,2) in [0,1]^2 on a c x c node grid: (idx (n,4), w (n,4))."""
    t = np.clip(x, 0, 1) * (c - 1)
    i0 = np.minimum(t.astype(int), c - 2)
    f = t - i0
    ix, iy, fx, fy = i0[:, 0], i0[:, 1], f[:, 0], f[:, 1]
    idx = np.stack([iy * c + ix, iy * c + ix + 1, (iy + 1) * c + ix, (iy + 1) * c + ix + 1], 1)
    return idx, np.stack([(1 - fx) * (1 - fy), fx * (1 - fy), (1 - fx) * fy, fx * fy], 1)


def warp_apply(D, x):
    idx, w = warp_weights(x, int(round(np.sqrt(len(D)))))
    return x + (D[idx] * w[..., None]).sum(axis=1)


def _nearest(a, b):
    out = np.empty(len(a), int)
    for i in range(0, len(a), 1024):
        out[i:i + 1024] = ((a[i:i + 1024, None, :] - b[None]) ** 2).sum(-1).argmin(1)
    return out


def fit_outline_warp(model_uv, pic_mask):
    """Smooth displacement D (nodes^2, 2): picture uv = warp_apply(D, model uv), both in their own
    bounding-box frames. Each round matches every model contour point to its nearest picture contour
    point and every picture contour point to its nearest warped model contour point, then solves the
    least-squares node displacements with a smoothness term that starts stiff (a near-global move)
    and relaxes (local fits: a beak, a leg). Returns (D, outline IoU before, after)."""
    c = WARP_NODES
    n = pic_mask.shape[0]
    mm = warp_mask(model_uv, n)
    mc, pc = warp_contour(mm), warp_contour(pic_mask)
    # nearest picture contour point for every grid cell (the forward match is a lookup)
    gy, gx = np.mgrid[0:n, 0:n]
    cells = np.stack([(gx.ravel() + 0.5) / n, (gy.ravel() + 0.5) / n], axis=1)
    near_pc = _nearest(cells, pc).reshape(n, n)
    idx, w = warp_weights(mc, c)
    A = np.zeros((len(mc), c * c))
    np.put_along_axis(A, idx, w, axis=1)
    lap = []
    for y in range(c):
        for x in range(c):
            for dx, dy in ((1, 0), (0, 1)):
                if x + dx < c and y + dy < c:
                    r = np.zeros(c * c)
                    r[y * c + x], r[(y + dy) * c + x + dx] = -1.0, 1.0
                    lap.append(r)
    lap = np.array(lap)
    LtL = lap.T @ lap / len(lap)
    AtA_f = A.T @ A / len(mc)
    D = np.zeros((c * c, 2))
    for it in range(WARP_ITERS):
        lam = WARP_SMOOTH[0] * (WARP_SMOOTH[1] / WARP_SMOOTH[0]) ** (it / max(WARP_ITERS - 1, 1))
        wm = mc + A @ D
        g = np.clip((wm * n).astype(int), 0, n - 1)
        tf = pc[near_pc[g[:, 1], g[:, 0]]] - mc
        j = _nearest(pc, wm)
        Ab, tb = A[j], pc - mc[j]
        M = AtA_f + Ab.T @ Ab / len(pc) + lam * LtL + 1e-3 * np.eye(c * c)
        rhs = A.T @ tf / len(mc) + Ab.T @ tb / len(pc)
        D = np.linalg.solve(M, rhs)
    after = warp_mask(warp_apply(D, model_uv), n)
    i0 = float((mm & pic_mask).sum() / max((mm | pic_mask).sum(), 1))
    i1 = float((after & pic_mask).sum() / max((after | pic_mask).sum(), 1))
    return D, i0, i1


class Registration:
    """Fit the reference's alpha outline to the model's outline seen from the reference camera.
    Both outlines are normalised to their own bounding box (scale per axis), then each height row
    of the reference is shifted sideways so its outline centre sits on the model's outline centre
    (a smoothed shear), so a head that the generator centred but the picture drew left of centre
    still lands on the geometric head."""

    def __init__(self, P_all, right, ref, depth_dir=None, cloud=None):
        """cloud: dense surface points (the texel positions); given, the outline is fitted by the
        2D warp (fit_outline_warp) instead of the per-row shift."""
        s, z = P_all @ right, P_all[:, 2]
        self.s0, self.sw = s.min(), max(np.ptp(s), 1e-9)
        self.z0, self.zh = z.min(), max(np.ptp(z), 1e-9)
        ys, xs = np.where(ref_mask(ref))
        self.rx0, self.rx1, self.ry0, self.ry1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
        self.warp, self.warp_iou = None, None
        if cloud is not None:
            cl = cloud[:: max(1, len(cloud) // WARP_CLOUD)]
            uv = np.stack([(cl @ right - self.s0) / self.sw, (cl[:, 2] - self.z0) / self.zh], 1)
            g = (np.arange(WARP_GRID) + 0.5) / WARP_GRID
            gx = np.rint(self.rx0 + g * (self.rx1 - 1 - self.rx0)).astype(int)
            gy = np.rint(self.ry0 + g * (self.ry1 - 1 - self.ry0)).astype(int)
            self.warp, i0, i1 = fit_outline_warp(uv, ref_mask(ref)[np.ix_(gy, gx)])
            self.warp_iou = (round(i0, 4), round(i1, 4))
        rw, rh = self.rx1 - 1 - self.rx0, self.ry1 - 1 - self.ry0
        mlo, mhi = row_extents((s - self.s0) / self.sw, (z - self.z0) / self.zh, REG_ROWS)
        rlo, rhi = row_extents((xs - self.rx0) / max(rw, 1), (ys - self.ry0) / max(rh, 1),
                               REG_ROWS)
        self.mid_m = smooth_rows((mlo + mhi) / 2, 2.0)
        self.mid_r = smooth_rows((rlo + rhi) / 2, 2.0)
        self.shift = self.mid_r - self.mid_m
        self.rows_v = (np.arange(REG_ROWS) + 0.5) / REG_ROWS
        h0 = int((1 - HEAD_BAND) * REG_ROWS)
        wm = np.nanmean((mhi - mlo)[h0:]) if np.isfinite((mhi - mlo)[h0:]).any() else np.nan
        wr = np.nanmean((rhi - rlo)[h0:]) if np.isfinite((rhi - rlo)[h0:]).any() else np.nan
        ok = bool(wr and np.isfinite(wr) and wr > 0)
        self.head_width_ratio = float(wm / wr) if ok else float("nan")
        self.head_shift = float(np.mean(self.shift[h0:]))
        self.head_cues = None
        if depth_dir is not None:
            self.register_head(P_all, s, z, depth_dir, ref, mask_xy=(xs, ys))

    def head_weight(self, vn):
        return np.clip((HEAD_FADE - (1 - vn)) / (HEAD_FADE - HEAD_FULL), 0, 1)

    def register_head(self, P_all, s, z, depth_dir, ref, mask_xy):
        """Shift the head rows of the reference sideways so the head found in the picture lands on
        the head found on the model (both in outline-normalised coordinates), then measure how far
        the independent second cue pair is from agreeing."""
        xs, ys = mask_xy
        rw, rh = self.rx1 - 1 - self.rx0, self.ry1 - 1 - self.ry0
        # picture, cue A: highest compact mass of the silhouette (smoothed top contour)
        m = ref_mask(ref)
        cols = np.arange(self.rx0, self.rx1)
        topc = np.array([np.nonzero(m[:, c])[0].max() if m[:, c].any() else -1 for c in cols],
                        float)
        k = max(3, int(0.02 * len(cols))) | 1
        tops = np.convolve(np.pad(topc, k // 2, mode="edge"), np.ones(k) / k, mode="valid")
        near = tops >= tops.max() - 0.01 * rh
        ref_a = float(cols[near].mean())
        # picture, cue B: centroid of the darkest facial features inside the head box
        hw = 0.5 * HEAD_WIDTH_OF_H * rh * 1.25
        y_lo = self.ry1 - 1 - 0.20 * rh
        colx = np.arange(m.shape[1])[None, :]
        rowy = np.arange(m.shape[0])[:, None]
        inbox = m & (colx >= ref_a - hw) & (colx <= ref_a + hw) & (rowy >= y_lo)
        by, bx = np.nonzero(inbox)
        lum = luma(ref[by, bx, :3])
        dark = lum <= np.quantile(lum, HEAD_DARK)
        ref_b = (float(bx[dark].mean()), float(by[dark].mean()))
        # model, cue A: centre of the top slice of the mesh
        zn = (z - self.z0) / self.zh
        sn = (s - self.s0) / self.sw
        model_a = float(sn[zn >= 1 - HEAD_TOP_SLICE].mean())
        # model, cue B: the most forward blob of the upper body
        up = zn > 0.75
        depth = P_all @ np.array(depth_dir, float)
        fwd = up & (depth >= np.quantile(depth[up], 0.85))
        model_b = (float(sn[fwd].mean()), float(zn[fwd].mean()))
        ref_a_n = (ref_a - self.rx0) / max(rw, 1)
        head_shift = ref_a_n - model_a
        w = self.head_weight(self.rows_v)
        self.shift = self.shift * (1 - w) + head_shift * w
        # agreement of the second pair after the shift, in head widths (reference pixels)
        px, py = self.to_ref(np.array([model_b[0] * self.sw + self.s0]),
                             np.array([model_b[1] * self.zh + self.z0]))
        head_w = HEAD_WIDTH_OF_H * rh
        self.head_cues = {
            "reference_head_x": round(ref_a_n, 4), "model_head_x": round(model_a, 4),
            "head_shift_applied": round(float(head_shift), 4),
            "feature_offset_px": [round(float(px[0] - ref_b[0]), 1),
                                  round(float(py[0] - ref_b[1]), 1)],
            "head_width_px": round(head_w, 1),
            "disagreement_head_widths": round(float(abs(px[0] - ref_b[0]) / head_w), 3),
        }

    def head_agrees(self):
        return self.head_cues is None or self.head_cues["disagreement_head_widths"] <= HEAD_AGREE

    def head_ok(self):
        lo, hi = HEAD_WIDTH_RATIO
        return bool(np.isfinite(self.head_width_ratio) and lo <= self.head_width_ratio <= hi
                    and self.head_agrees())

    def to_ref(self, sv, z):
        """(s along camera right, z) of source points -> reference pixel coordinates."""
        vn = np.clip((z - self.z0) / self.zh, 0, 1)
        if self.warp is not None:
            w = warp_apply(self.warp, np.stack([(sv - self.s0) / self.sw, vn], axis=1))
            xn, vn = w[:, 0], w[:, 1]
        else:
            xn = (sv - self.s0) / self.sw + np.interp(vn, self.rows_v, self.shift)
        px = self.rx0 + xn * (self.rx1 - 1 - self.rx0)
        py = self.ry0 + vn * (self.ry1 - 1 - self.ry0)
        return px, py


def box_blur(img, r):
    if r <= 0:
        return img
    k = 2 * r + 1
    p = np.pad(img, ((r, r), (r, r), (0, 0)), mode="edge")
    c = np.cumsum(np.cumsum(p, axis=0), axis=1)
    c = np.pad(c, ((1, 0), (1, 0), (0, 0)))
    return (c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]) / (k * k)


def mesh_edges(vi):
    e = np.concatenate([vi[:, [0, 1]], vi[:, [1, 2]], vi[:, [2, 0]]])
    e = np.unique(np.sort(e, axis=1), axis=0)
    return np.concatenate([e, e[:, ::-1]])  # both directions (i -> j)


def graph_mean(x, edges, deg):
    """One diffusion step: average of self and neighbours along mesh edges (x: (nv, k))."""
    acc = np.zeros_like(x)
    for c in range(x.shape[1]):
        acc[:, c] = np.bincount(edges[:, 0], weights=x[edges[:, 1], c], minlength=len(x))
    return (x + acc) / (deg[:, None] + 1)


def diffuse(x, edges, deg, iters):
    for _ in range(iters):
        x = graph_mean(x, edges, deg)
    return x


def fill_colour(c, s, edges, deg):
    """Normalised graph diffusion of colour c (nv,3) with source weight s (nv,): at each vertex the
    smallest scale (iterations) that has gathered enough weight is used, so the fill is the
    nearest trustworthy colour on the surface, never a UV-block average."""
    x = np.concatenate([c * s[:, None], s[:, None]], axis=1)
    out = np.full((len(c), 3), np.nan)
    done = 0
    for target in (3, 6, 12, 24, 48, 96, 192, 384):
        x = diffuse(x, edges, deg, target - done)
        done = target
        ok = np.isnan(out[:, 0]) & (x[:, 3] > 0.12)
        out[ok] = x[ok, :3] / x[ok, 3:4]
    if np.isnan(out[:, 0]).any():
        out[np.isnan(out[:, 0])] = c[s > 0].mean(axis=0) if (s > 0).any() else 0.5
    return diffuse(out, edges, deg, 3)


# ---------------------------------------------------------------- multi-view colour (method B)
# MV-Adapter image+geometry (src/asset_forge/multiview.py) paints six views of OUR mesh from the
# reference picture; the views are aligned to the mesh because they are conditioned on its own
# position and normal maps, rendered here. Its frame: the model centred, max |coord| = 0.5,
# orthographic box +-0.55, cameras at distance 1.8 looking at the origin, z up; view 0 is the
# reference camera (the mesh is turned about z so that d0 points to -y).
MV_SIZE = 768
MV_BOX = 0.55
MV_VIEWS = ((-90.0, 0.0), (0.0, 0.0), (90.0, 0.0), (180.0, 0.0), (90.0, 89.99), (90.0, -89.99))
MV_POWER = 4          # view weight = facing ** MV_POWER (a view seen head-on wins)
MV_DEPTH_TOL = 0.006  # z-test: texel within this distance (model frame units) of the view's surface
MV_ERODE = 2          # px dropped at each view's silhouette (the edge pixels blend the background)
MV_FULL_WEIGHT = 0.3  # summed view weight from which the views replace the fill completely
MV_GAIN = (0.5, 2.0)  # allowed per-channel contrast change when matching the views to the picture
MV_MATCH_GRID = (6, 12)  # cells (across, down) of the picture's outline box, colour match
MV_MATCH_PRIOR = 200     # samples worth of the whole-view statistics mixed into each cell
MV_MATCH_FACING = 0.05   # view weight (facing ** MV_POWER) from which a texel counts
MV_PICTURE = True     # the picture paints what its camera directly sees; the views the rest


def mv_frame(co, d0):
    """(R, c, s): std = s * R @ (p - c); R turns d0 onto -y about z."""
    ang = math.atan2(-1.0, 0.0) - math.atan2(d0[1], d0[0])
    ca, sa = math.cos(ang), math.sin(ang)
    R = np.array([[ca, -sa, 0.0], [sa, ca, 0.0], [0.0, 0.0, 1.0]])
    c = (co.min(axis=0) + co.max(axis=0)) / 2
    s = 0.5 / max(np.abs((co - c) @ R.T).max(), 1e-9)
    return R, c, s


def mv_cameras():
    """Per view (camera position, lookat, right, up), MV-Adapter's get_c2w convention."""
    cams = []
    for az, el in MV_VIEWS:
        a, e = math.radians(az), math.radians(el)
        pos = 1.8 * np.array([math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), math.sin(e)])
        look = -pos / np.linalg.norm(pos)
        right = np.cross(look, [0.0, 0.0, 1.0])
        right /= np.linalg.norm(right)
        up = np.cross(right, look)
        cams.append((pos, look, right, up / np.linalg.norm(up)))
    return cams


def mv_pixel(q, cam, size=MV_SIZE):
    """std points (m,3) -> (column, row, depth) floats; row 0 = top."""
    pos, look, right, up = cam
    d = q - pos
    col = (d @ right + MV_BOX) / (2 * MV_BOX) * size
    row = (MV_BOX - d @ up) / (2 * MV_BOX) * size
    return col, row, d @ look


def mv_control(q, vi, vn_std, size=MV_SIZE):
    """Rasterise the mesh (std frame) in the six views: per view the visible surface position,
    smooth normal and depth (inf on the background). Returns pos, nrm (6,size,size,3), depth."""
    cams = mv_cameras()
    pos = np.zeros((6, size, size, 3), np.float32)
    nrm = np.zeros((6, size, size, 3), np.float32)
    dep = np.full((6, size, size), np.inf)
    for k, cam in enumerate(cams):
        col, row, z = mv_pixel(q, cam, size)
        X, Y, Z = col[vi], row[vi], z[vi]  # (nt,3)
        zb, pb, nb = dep[k], pos[k], nrm[k]
        for t in range(len(vi)):
            a, b, c = (X[t, 0], Y[t, 0]), (X[t, 1], Y[t, 1]), (X[t, 2], Y[t, 2])
            den = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
            if abs(den) < 1e-12:
                continue
            x0, x1 = max(int(min(a[0], b[0], c[0])), 0), min(int(max(a[0], b[0], c[0])) + 1, size)
            y0, y1 = max(int(min(a[1], b[1], c[1])), 0), min(int(max(a[1], b[1], c[1])) + 1, size)
            if x1 <= x0 or y1 <= y0:
                continue
            gx, gy = np.meshgrid(np.arange(x0, x1) + 0.5, np.arange(y0, y1) + 0.5)
            w0 = ((b[1] - c[1]) * (gx - c[0]) + (c[0] - b[0]) * (gy - c[1])) / den
            w1 = ((c[1] - a[1]) * (gx - c[0]) + (a[0] - c[0]) * (gy - c[1])) / den
            w2 = 1 - w0 - w1
            m = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
            if not m.any():
                continue
            w = np.stack([w0[m], w1[m], w2[m]], axis=1)
            zz = w @ Z[t]
            ys, xs = np.nonzero(m)
            ys, xs = ys + y0, xs + x0
            near = zz < zb[ys, xs]
            if not near.any():
                continue
            ys, xs, w = ys[near], xs[near], w[near]
            zb[ys, xs] = zz[near]
            pb[ys, xs] = w @ q[vi[t]]
            nn = w @ vn_std[vi[t]]
            nb[ys, xs] = nn / np.maximum(np.linalg.norm(nn, axis=1, keepdims=True), 1e-12)
    return pos, nrm, dep


def mv_write_control(path, pos, nrm, dep):
    bg = ~np.isfinite(dep)
    p = np.clip(pos + 0.5, 0, 1)
    n = np.clip(nrm / 2 + 0.5, 0, 1)
    p[bg], n[bg] = 0.5, 0.5
    np.savez(path, pos=p.astype(np.float32), normal=n.astype(np.float32))


def mv_load_views(view_dir):
    """The six generated views as (6,H,W,3) float, row 0 = top (display values, like the ref)."""
    out = []
    for k in range(len(MV_VIEWS)):
        img = bpy.data.images.load(str(Path(view_dir) / f"view_{k}.png"))
        w, h = img.size
        px = np.empty(w * h * 4, np.float32)
        img.pixels.foreach_get(px)
        out.append(px.reshape(h, w, 4)[::-1, :, :3])
        bpy.data.images.remove(img)
    return np.stack(out)


def mv_sample_views(views, dep, frame, P, Nn):
    """Colour of surface points P (model frame, normals Nn) in each view that sees them: z-test
    against the view's depth, weight facing ** MV_POWER, silhouettes eroded. Returns
    (rgb (K,n,3), w (K,n)); w = 0 where the view does not see the point."""
    R, c, s = frame
    q = s * (P - c) @ R.T
    nq = Nn @ R.T
    size = views.shape[1]
    cols = np.zeros((len(views), len(P), 3))
    ws = np.zeros((len(views), len(P)))
    for k, cam in enumerate(mv_cameras()):
        fg = np.isfinite(dep[k])
        for _ in range(MV_ERODE):
            e = fg.copy()
            e[1:] &= fg[:-1]
            e[:-1] &= fg[1:]
            e[:, 1:] &= fg[:, :-1]
            e[:, :-1] &= fg[:, 1:]
            fg = e
        col, row, z = mv_pixel(q, cam, size)
        ix = np.clip(col.astype(int), 0, size - 1)
        iy = np.clip(row.astype(int), 0, size - 1)
        facing = np.clip(-(nq @ cam[1]), 0, 1)
        ok = fg[iy, ix] & (np.abs(z - np.where(fg[iy, ix], dep[k][iy, ix], np.inf))
                           <= MV_DEPTH_TOL)
        ws[k] = np.where(ok, facing ** MV_POWER, 0.0)
        cols[k] = views[k][iy, ix]
    return cols, ws


def mv_blend(cols, ws):
    """Weighted blend of the per-view colours. Returns (rgb, summed weight)."""
    wsum = ws.sum(axis=0)
    return (cols * ws[..., None]).sum(axis=0) / np.maximum(wsum[:, None], 1e-12), wsum


_XYZ = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
_WHITE = np.array([0.95047, 1.0, 1.08883])


def srgb_to_lab(c):
    c = np.clip(c, 0, 1)
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    xyz = lin @ _XYZ.T / _WHITE
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]),
                     200 * (f[..., 1] - f[..., 2])], axis=-1)


def lab_to_srgb(lab):
    fy = (lab[..., 0] + 16) / 116
    f = np.stack([fy + lab[..., 1] / 500, fy, fy - lab[..., 2] / 200], axis=-1)
    xyz = np.where(f > 0.206893, f ** 3, (f - 16 / 116) / 7.787) * _WHITE
    lin = np.clip(xyz @ np.linalg.inv(_XYZ).T, 0, 1)
    return np.where(lin <= 0.0031308, lin * 12.92, 1.055 * lin ** (1 / 2.4) - 0.055)


def _mean_var(x, n0=0, prior=None):
    if prior is None or n0 == 0:
        return x.mean(axis=0), x.var(axis=0)
    m0, v0 = prior
    n = len(x)
    m = (x.sum(axis=0) + n0 * m0) / (n + n0)
    v = (((x - m) ** 2).sum(axis=0) + n0 * (v0 + (m0 - m) ** 2)) / (n + n0)
    return m, v


def mv_match(cols, ws, uv, pic, pic_uv, grid=MV_MATCH_GRID):
    """Per-view colour matching. The generator lights each view its own way (a back view brighter
    or washed out), so each view is matched to the picture on its own: in each cell of a grid over
    the picture's outline box (uv 0..1 through the same registration the gates use; one cell holds
    the same body part front and back, near and far flank) the view's Lab mean and spread move onto
    the picture's pixels' mean and spread in that cell, measured on the texels the view sees.
    A cell with few samples leans on the whole-view statistics (MV_MATCH_PRIOR).
    Returns (gain, offset) Lab fields (K, gu, gv, 3) and the texels counted per view."""
    gu, gv = grid

    def cells(u):
        return (np.clip((u[0] * gu).astype(int), 0, gu - 1),
                np.clip((u[1] * gv).astype(int), 0, gv - 1))

    iu, iv = cells(uv)
    lab_p = srgb_to_lab(pic)
    pu, pv = cells(pic_uv)
    prior_p = _mean_var(lab_p)
    K = len(cols)
    gain = np.ones((K, gu, gv, 3))
    offs = np.zeros((K, gu, gv, 3))
    counts = []
    for k in range(K):
        sel = ws[k] > MV_MATCH_FACING
        counts.append(int(sel.sum()))
        if sel.sum() < 20 or len(lab_p) < 20:
            continue
        lab_v = srgb_to_lab(cols[k][sel])
        prior_v = _mean_var(lab_v)
        cu, cv = iu[sel], iv[sel]
        for a in range(gu):
            for b in range(gv):
                m_v, v_v = _mean_var(lab_v[(cu == a) & (cv == b)], MV_MATCH_PRIOR, prior_v)
                m_p, v_p = _mean_var(lab_p[(pu == a) & (pv == b)], MV_MATCH_PRIOR, prior_p)
                g = np.clip(np.sqrt(v_p / np.maximum(v_v, 1e-6)), *MV_GAIN)
                gain[k, a, b], offs[k, a, b] = g, m_p - g * m_v
    return gain, offs, counts


def mv_apply(match, cols, uv):
    """Matched per-view colours: the cell fields bilinearly interpolated at each point."""
    gain, offs = match[:2]
    gu, gv = gain.shape[1:3]
    x = np.clip(uv[0] * gu - 0.5, 0, gu - 1)
    y = np.clip(uv[1] * gv - 0.5, 0, gv - 1)
    x0, y0 = np.minimum(x.astype(int), gu - 2), np.minimum(y.astype(int), gv - 2)
    fx, fy = (x - x0)[:, None], (y - y0)[:, None]

    def at(F):
        return ((F[x0, y0] * (1 - fx) + F[x0 + 1, y0] * fx) * (1 - fy)
                + (F[x0, y0 + 1] * (1 - fx) + F[x0 + 1, y0 + 1] * fx) * fy)

    out = np.empty_like(cols)
    for k in range(len(cols)):
        out[k] = lab_to_srgb(srgb_to_lab(cols[k]) * at(gain[k]) + at(offs[k]))
    return out


def mv_generate(obj_co, vi, vn, d0, ref_path, work_dir, mv):
    """Render the control maps, run the generator (unless mv['views'] is given) and return
    (views, depth, frame, info)."""
    import subprocess
    frame = mv_frame(obj_co, d0)
    R, c, s = frame
    t0 = time.perf_counter()
    pos, nrm, dep = mv_control(s * (obj_co - c) @ R.T, vi, vn @ R.T)
    info = {"seconds_control_maps": round(time.perf_counter() - t0, 2)}
    view_dir = Path(mv["views"]) if mv.get("views") else Path(work_dir) / "multiview"
    if not mv.get("views"):
        view_dir.mkdir(parents=True, exist_ok=True)
        mv_write_control(view_dir / "control.npz", pos, nrm, dep)
        script = HERE.parent / "src" / "asset_forge" / "multiview.py"
        cmd = [mv["python"], "-I", str(script), str(view_dir / "control.npz"), str(ref_path),
               str(view_dir), "--mv-src", mv["src"]]
        t1 = time.perf_counter()
        env = dict(os.environ)
        if mv.get("hf_home"):
            env["HF_HOME"] = mv["hf_home"]
        env["HF_HUB_OFFLINE"] = "1"  # weights are on disk; never download during a clean
        # --gpu-lock DIR: hold the shared GPU lock only while the generator runs (the rest of the
        # clean is CPU work and runs in parallel with other jobs)
        lock = contextlib.nullcontext()
        if mv.get("gpu_lock"):
            sys.path.insert(0, str(HERE.parent / "src"))
            from asset_forge.gpu_lock import gpu_lock
            lock = gpu_lock(Path(mv["gpu_lock"]), "clean multiview", 5.0)
        with lock:
            r = subprocess.run(cmd, capture_output=True, text=True, env=env)
        info["seconds_generator"] = round(time.perf_counter() - t1, 2)
        if r.returncode:
            raise SystemExit("Painting the sides the picture cannot see failed. Press Redo; if it "
                             "fails again, close other programs using the graphics card. "
                             f"(multiview generator log: {r.stderr[-2000:]})")
    gen = view_dir / "multiview.json"
    if gen.exists():
        info["generator"] = json.loads(gen.read_text())
    return mv_load_views(view_dir), dep, frame, info


# Measured colour gates (Step 2 fidelity check). Regions are boxes in the reference outline's own
# normalised coordinates (u from the left, v from the TOP of the bounding box), optionally limited
# to one side of the model: "back" (texels facing away from the reference camera), "far" (an
# animal's far flank, the mirrored side), "near", "under" (facing down). The same boxes are read on
# the reference picture (always its visible side) and on the saved albedo through the same
# registration. Only references named here are checked; the gates were written from the round-4
# critic's fix list (PR #9): hidden sides must carry the part's colour, not a neighbour's.
REGION_GATES = {
    "fox": {
        "chest": (0.08, 0.28, 0.38, 0.58),
        "flank": (0.35, 0.65, 0.25, 0.55),
        "tail_body": (0.80, 0.97, 0.30, 0.70),
        "tail_tip": (0.90, 1.00, 0.72, 1.00),
        "legs": (0.00, 0.90, 0.78, 1.00),
        "front_lower_legs": (0.17, 0.36, 0.62, 1.00),
        "hind_lower_legs": (0.55, 0.86, 0.72, 1.00),
    },
    "brute": {
        "shorts": (0.32, 0.58, 0.42, 0.55),
        "shorts_back": (0.32, 0.58, 0.42, 0.55, "back"),
    },
    "humanoid": {
        "torso": (0.36, 0.64, 0.20, 0.40),
        "torso_back": (0.36, 0.64, 0.20, 0.40, "back"),
        "greaves": (0.30, 0.72, 0.72, 0.88),
        "greaves_back": (0.30, 0.72, 0.72, 0.88, "back"),
        "boots": (0.28, 0.85, 0.92, 1.00),
        "boots_back": (0.28, 0.85, 0.92, 1.00, "back"),
    },
    "bird": {
        "beak": (0.00, 0.11, 0.07, 0.13),
    },
}
DARK_LUMA = 0.20    # a dark (black sock) pixel
PALE_LUMA_MIN, PALE_SAT_MAX = 0.55, 0.22   # a white/pale pixel
WHITE_LUMA = 0.75   # a white streak texel (brighter than polished steel's mid-tones)
SIDE_COS = 0.3      # |facing| or |normal z| beyond which a texel is on a side
HEAD_END = 0.2      # animals: head-end fraction of the body length (neck and shoulder zone)
FAR_PALE_GAP = 0.10  # far neck pale fraction allowed above the near neck's


def region_stats(rgb):
    if not len(rgb):
        return {"n": 0, "rgb": np.full(3, np.nan), "p90_luma": float("nan"), "pale": float("nan"),
                "dark": float("nan"), "white": float("nan"), "std_luma": float("nan")}
    mx, mn = rgb.max(axis=1), rgb.min(axis=1)
    sa = (mx - mn) / np.maximum(mx, 1e-6)
    lu = luma(rgb)
    return {"n": int(len(rgb)), "rgb": rgb.mean(axis=0), "p90_luma": float(np.quantile(lu, 0.9)),
            "pale": float(((lu > PALE_LUMA_MIN) & (sa < PALE_SAT_MAX)).mean()),
            "dark": float((lu < DARK_LUMA).mean()), "white": float((lu > WHITE_LUMA).mean()),
            "std_luma": float(lu.std())}


def _dist(a, b):
    return float(np.linalg.norm(a["rgb"] - b["rgb"]))


def _warm(s):
    return float(s["rgb"][0] - s["rgb"][2])


def region_gate_checks(ref_s, tex_s, name="fox", model=None):
    """(name, measured, limit text, ok) per gate; ref_s/tex_s are region_stats by region; model
    holds the model-space measures (animals). A region with no texels fails (NaN compares false)."""
    r, t = ref_s, tex_s
    if name == "brute":  # shorts all the way round, not skin at the back (reads naked)
        d = _dist(t["shorts_back"], r["shorts"])
        return [("shorts_back_colour_distance", d, "<= 0.10", d <= 0.10)]
    if name == "humanoid":
        out = []
        for k, lim in (("torso_back", 0.15), ("greaves_back", 0.12), ("boots_back", 0.12)):
            d = _dist(t[k], r[k.replace("_back", "")])
            out.append((f"{k}_colour_distance", d, f"<= {lim}", d <= lim))
        # the back is not one flat colour: the torso keeps at least 0.4 of the picture's contrast
        q = t["torso_back"]["std_luma"] / max(r["torso"]["std_luma"], 1e-6)
        out.append(("torso_back_contrast_ratio", q, ">= 0.40", q >= 0.40))
        # brown boots stay browner than the steel greaves at the back (not one dull taupe)
        gap_r = _warm(r["boots"]) - _warm(r["greaves"])
        gap_t = _warm(t["boots_back"]) - _warm(t["greaves_back"])
        out.append(("boots_minus_greaves_warmth_back", gap_t, f">= {0.5 * gap_r:.3f}",
                    gap_t >= 0.5 * gap_r))
        w = _warm(t["greaves_back"])
        out.append(("greaves_back_warmth", w, f"<= {_warm(r['greaves']) + 0.02:.3f}",
                    w <= _warm(r["greaves"]) + 0.02))
        return out
    if name == "bird":
        return [("beak_dark_fraction", t["beak"]["dark"], f">= {0.5 * r['beak']['dark']:.2f}",
                 t["beak"]["dark"] >= 0.5 * r["beak"]["dark"])]
    d = lambda k: _dist(t[k], r[k])  # noqa: E731
    out = [
        ("legs_dark_fraction", t["legs"]["dark"], f">= {0.5 * r['legs']['dark']:.2f}",
         t["legs"]["dark"] >= 0.5 * r["legs"]["dark"]),
        ("chest_p90_luma_ratio", t["chest"]["p90_luma"] / max(r["chest"]["p90_luma"], 1e-6),
         "0.85 .. 1.25",
         0.85 <= t["chest"]["p90_luma"] / max(r["chest"]["p90_luma"], 1e-6) <= 1.25),
        ("chest_pale_fraction", t["chest"]["pale"], f">= {0.6 * r['chest']['pale']:.2f}",
         t["chest"]["pale"] >= 0.6 * r["chest"]["pale"]),
        ("flank_colour_distance", d("flank"), "<= 0.12", d("flank") <= 0.12),
        ("tail_body_colour_distance", d("tail_body"), "<= 0.15", d("tail_body") <= 0.15),
        ("tail_body_pale_fraction", t["tail_body"]["pale"],
         f"<= {r['tail_body']['pale'] + 0.10:.2f}",
         t["tail_body"]["pale"] <= r["tail_body"]["pale"] + 0.10),
        # presence only: the box also holds some tail body of a model whose tail is shorter
        ("tail_tip_pale_fraction", t["tail_tip"]["pale"],
         f">= {0.15 * r['tail_tip']['pale']:.2f}",
         t["tail_tip"]["pale"] >= 0.15 * r["tail_tip"]["pale"]),
    ]
    for k in ("front_lower_legs", "hind_lower_legs"):  # black from the elbow / hock down
        out.append((f"{k}_dark_fraction", t[k]["dark"], f">= {0.9 * r[k]['dark']:.2f}",
                    t[k]["dark"] >= 0.9 * r[k]["dark"]))
    if model is not None:
        # the far flank's neck is not whiter than the near one (a mirrored cheek smear)
        gap = model["far_minus_near_neck_pale"]
        out.append(("far_minus_near_neck_pale", gap, f"<= {FAR_PALE_GAP}", gap <= FAR_PALE_GAP))
        # the tail's end-on faces (toward the back) carry the tail, not a white streak
        out.append(("tail_end_on_pale_fraction", model["tail_end_on_pale"],
                    f"<= {r['tail_body']['pale'] + 0.05:.2f}",
                    model["tail_end_on_pale"] <= r["tail_body"]["pale"] + 0.05))
    return out


def model_side_measures(p, colour, normal, cx, tail, height):
    """Animals, in model space (head toward -Y, D-021): how much paler the far flank's neck and
    shoulder (head-end fifth of the length, upper half of the height) is than the near flank's
    (a mirrored cheek or ruff smeared onto the far side); pale fraction of tail texels whose faces
    point along the body (end-on to the side camera)."""
    pale = (luma(colour) > PALE_LUMA_MIN) & (sat(colour) < PALE_SAT_MAX)
    yf = (p[:, 1] - p[:, 1].min()) / max(np.ptp(p[:, 1]), 1e-9)
    zf = (p[:, 2] - p[:, 2].min()) / max(height, 1e-9)
    zone = (yf < HEAD_END) & (zf >= 0.5)
    far = zone & (p[:, 0] < cx)
    near = zone & (p[:, 0] >= cx)
    gap = (float(pale[far].mean()) if far.any() else 0.0) - (
        float(pale[near].mean()) if near.any() else 0.0)
    end_on = tail & (np.abs(normal[:, 1]) > 0.6)
    return {"far_minus_near_neck_pale": gap, "neck_far_texels": int(far.sum()),
            "neck_near_texels": int(near.sum()),
            "tail_end_on_pale": float(pale[end_on].mean()) if end_on.any() else 0.0,
            "tail_end_on_texels": int(end_on.sum())}


def region_gates(name, ref, reg, right, p, colour, facing=None, normal=None, far=None,
                 model=None):
    """facing: texel normal . camera direction; normal: texel normals; far: bool, far flank;
    model: model_side_measures (animals)."""
    boxes = REGION_GATES.get(name)
    if not boxes:
        return None
    rw1, rh1 = reg.rx1 - 1 - reg.rx0, reg.ry1 - 1 - reg.ry0
    rm = ref_mask(ref)
    yy, xx = np.mgrid[0:ref.shape[0], 0:ref.shape[1]]
    ru, rv = (xx - reg.rx0) / max(rw1, 1), 1 - (yy - reg.ry0) / max(rh1, 1)
    px, py = reg.to_ref(p @ right, p[:, 2])
    tu, tv = (px - reg.rx0) / max(rw1, 1), 1 - (py - reg.ry0) / max(rh1, 1)
    n = len(p)
    every = np.ones(n, bool)
    side_sel = {
        "all": every,
        "back": (facing < -SIDE_COS) if facing is not None else every,
        "under": (normal[:, 2] < -SIDE_COS) if normal is not None else every,
        "far": far if far is not None else ~every,
        "near": ~far if far is not None else every,
    }
    ref_s, tex_s = {}, {}
    for k, box in boxes.items():
        u0, u1, v0, v1 = box[:4]
        side = box[4] if len(box) > 4 else "all"
        ref_s[k] = region_stats(ref[rm & (ru >= u0) & (ru < u1) & (rv >= v0) & (rv < v1)][:, :3])
        sel = (tu >= u0) & (tu < u1) & (tv >= v0) & (tv < v1) & side_sel[side]
        tex_s[k] = region_stats(colour[sel])
    checks = region_gate_checks(ref_s, tex_s, name, model)
    fmt = lambda s: {k: ([round(float(x), 3) for x in v] if k == "rgb" else round(v, 3))  # noqa
                     for k, v in s.items()}
    return {"reference": name, "passed": all(c[3] for c in checks),
            "gates": [{"gate": c[0], "value": round(float(c[1]), 3), "limit": c[2],
                       "ok": bool(c[3])} for c in checks],
            "reference_regions": {k: fmt(v) for k, v in ref_s.items()},
            "albedo_regions": {k: fmt(v) for k, v in tex_s.items()},
            "model_measures": {k: round(float(v), 4) for k, v in (model or {}).items()}}


def bleed(img, mask, px):
    """Grow the picture's colours px pixels outwards over its own outline (4-neighbour average of
    known pixels, like the island padding): a model outline that misses the picture's by a few
    pixels (a thin tail tip) still finds the picture's colours there. Returns (img, mask)."""
    img, have = img.copy(), mask.copy()
    for _ in range(px):
        acc = np.zeros_like(img)
        cnt = np.zeros(mask.shape, np.float64)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            h = np.roll(have, (dy, dx), (0, 1))
            acc += np.roll(img, (dy, dx), (0, 1)) * h[..., None]
            cnt += h
        grow = (~have) & (cnt > 0)
        img[grow] = acc[grow] / cnt[grow, None]
        have |= grow
    return img, have


def ref_specks(ref):
    """Boolean image: small connected dark or white components of the picture (SPECK_AREA of the
    silhouette, 4-connected, dark and white labelled apart), grown by 2 px for the sampling blur."""
    from collections import deque
    m = ref_mask(ref)
    lu, sa = luma(ref[..., :3]), sat(ref[..., :3])
    limit = SPECK_AREA * int(m.sum())
    out = np.zeros(m.shape, bool)
    h, w = m.shape
    for cls in (m & (lu < SPECK_DARK_LUMA), m & (lu > PALE_LUMA_MIN) & (sa < PALE_SAT_MAX)):
        seen = np.zeros(m.shape, bool)
        for y0, x0 in zip(*np.nonzero(cls), strict=True):
            if seen[y0, x0]:
                continue
            comp, q = [], deque([(y0, x0)])
            seen[y0, x0] = True
            while q:
                y, x = q.popleft()
                comp.append((y, x))
                for yy, xx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                    if 0 <= yy < h and 0 <= xx < w and cls[yy, xx] and not seen[yy, xx]:
                        seen[yy, xx] = True
                        q.append((yy, xx))
            if len(comp) < limit:
                cy, cx = zip(*comp, strict=True)
                out[list(cy), list(cx)] = True
    return box_blur(out[..., None].astype(np.float64), 2)[..., 0] > 0.01


def bake_colour(obj, ref, d0, size, ref_name=None, mv=None, ref_path=None, work_dir=None):
    """Project `ref` onto obj (see module docstring). Returns (RGBA array, stats, info).
    mv (method B): {"python", "src", "hf_home"} to generate six views, or {"views": DIR} to reuse
    them; the picture then paints only what its camera directly sees (no mirror) and the views
    paint everything else they see; the graph fill is left for what no view sees."""
    me = obj.data
    me.calc_loop_triangles()
    uvl = me.uv_layers.active.data
    tris = me.loop_triangles
    nt = len(tris)
    nv = len(me.vertices)
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
    area = np.linalg.norm(N, axis=1)
    N /= np.maximum(area[:, None], 1e-12)
    vn = np.zeros((nv, 3))
    for k in range(3):
        np.add.at(vn, vi[:, k], N * area[:, None])
    vn /= np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-12)

    # Rasterise: per texel the triangle and barycentric weights.
    tid = np.full((size, size), -1, np.int32)
    bary = np.zeros((size, size, 3))
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
        ys, xs = np.nonzero(m)
        tid[y0 + ys, x0 + xs] = t
        bary[y0 + ys, x0 + xs] = np.stack([w0[m], w1[m], w2[m]], axis=1)
    cov = tid >= 0
    ty, tx = np.nonzero(cov)
    tt = tid[ty, tx]
    bw = bary[ty, tx]                                        # (m,3)
    p = np.einsum("mk,mkc->mc", bw, P[tt])                   # texel positions
    n = N[tt]                                                # face normals
    d_arr = np.array(d0, float)
    wt = np.einsum("mk,mkc->mc", bw, vn[vi[tt]]) @ d_arr     # smooth facing

    f = -d_arr
    right = np.cross(f, [0, 0, 1.0])
    right /= np.linalg.norm(right)
    mirror = tuple(round(x, 3) for x in d0) in MIRROR_DIRS
    use_mirror = mirror and mv is None
    reg = Registration(co, right, ref, None if mirror else d0, cloud=p if mirror else None)
    height = max(np.ptp(co[:, 2]), 1e-9)
    mask = ref_mask(ref, erode=3)
    ref_s_img = ref.astype(np.float64)
    if mirror:
        ref_s_img, mask = bleed(ref_s_img, mask, OUTLINE_BLEED)
    rh, rw = ref.shape[:2]
    bvh = bvhtree.BVHTree.FromObject(obj, bpy.context.evaluated_depsgraph_get())
    eps = max(np.ptp(co, axis=0)) * 1e-3
    d_vec = Vector(d0)
    cx = 0.0
    if mirror:  # sagittal plane: the body's mid-length slice (the head and tail may be turned)
        yv = co[:, 1]
        body = (yv > yv.min() + 0.25 * np.ptp(yv)) & (yv < yv.max() - 0.25 * np.ptp(yv))
        cx = (co[body, 0].min() + co[body, 0].max()) / 2
    n_mirrored = [0]
    tail_y = None
    if mirror:
        # the tail end: beyond the body's mid-length slice, on the side away from the head (the
        # head is the high end of the animal)
        y_head = co[co[:, 2] >= co[:, 2].min() + 0.92 * height, 1].mean()
        y_mid = (yv.min() + yv.max()) / 2
        tail_y = (y_mid, -np.sign(y_head - y_mid), 0.25 * np.ptp(yv))

    def in_tail(P):
        return tail_y[1] * (P[:, 1] - tail_y[0]) > tail_y[2]

    def sources(Pp, w, Nn, seen_min=MIN_FACING):
        """Source point on the surface that the camera sees for each point: the point itself, or
        (side views) for the far flank its left-right mirror image across the sagittal plane
        (x -> 2 cx - x only, never front-to-back) snapped to the nearest surface."""
        Q, WQ, NQ = Pp.copy(), w.copy(), Nn.copy()
        snap = np.zeros(len(Pp))
        far = np.zeros(len(Pp), bool)
        if use_mirror:
            tail = in_tail(Pp)
            for k in np.nonzero(w < -MIN_FACING)[0]:
                m = Vector((2 * cx - Pp[k, 0], Pp[k, 1], Pp[k, 2]))
                loc, nrm, _i, _d = bvh.find_nearest(m)
                if loc is not None and (not tail[k] or (nrm.dot(d_vec) >= MIN_FACING
                                                      and _d <= MIRROR_SNAP * height)):
                    Q[k], NQ[k] = (loc.x, loc.y, loc.z), (nrm.x, nrm.y, nrm.z)
                    WQ[k] = nrm.dot(d_vec)
                    snap[k] = _d
                    n_mirrored[0] += 1
                elif tail[k]:
                    # the far side of the tail has no mirror image (a tail swung to one side): it
                    # takes the colour of the picture at its own place, as seen from the opposite
                    # camera; never specks (snap = inf)
                    WQ[k], far[k], snap[k] = -w[k], True, np.inf
        seen = np.zeros(len(Pp), bool)
        for k in np.nonzero(WQ >= seen_min)[0]:
            dv = -d_vec if far[k] else d_vec
            org = Vector(Q[k] + NQ[k] * eps) + (dv * eps * 2 if seen_min < 0 else Vector((0, 0, 0)))
            if bvh.ray_cast(org, dv)[0] is None:
                seen[k] = True
        sources.snap = snap
        return Q, WQ, seen

    def pixels(Q):
        px, py = reg.to_ref(Q @ right, Q[:, 2])
        return (np.clip(np.rint(py).astype(int), 0, rh - 1),
                np.clip(np.rint(px).astype(int), 0, rw - 1))

    def sample(Q, img):
        iy, ix = pixels(Q)
        return img[iy, ix, :3], mask[iy, ix]

    ref64 = ref_s_img
    blur5 = box_blur(ref64, 2)

    # Vertex level: where the picture is trusted (a0) and where the fill colour comes from.
    vw = vn @ d_arr
    VQ, VWQ, vseen = sources(co, vw, vn, GRAZE_MIN if mirror else MIN_FACING)
    vcol, vinside = sample(VQ, blur5)
    head_ok = reg.head_ok()
    vz = (co[:, 2] - co[:, 2].min()) / height
    # Animals: the tail (thin, often edge-on to the side camera) is painted from the picture's
    # pixels there at vertex resolution even where it is edge-on; elsewhere edge-on stays fill.
    a0 = np.maximum(ramp(VWQ), GRAZE_TRUST * in_tail(co) if mirror else 0.0) * (vseen & vinside)
    if not head_ok:
        a0 = np.where(vz >= 1 - HEAD_BAND, 0.0, a0)  # head does not match: low frequency only
    lum_v = luma(vcol)
    band = np.minimum((vz * BANDS).astype(int), BANDS - 1)
    shadow = np.zeros(nv, bool)
    for b in range(BANDS):
        sel = (a0 > 0) & (band == b)
        if sel.sum() >= 5:
            shadow[sel] = lum_v[sel] < SHADOW_REL * np.median(lum_v[sel])
    s_fill = np.where(shadow, 0.0, a0)
    edges = mesh_edges(vi)
    deg = np.bincount(edges[:, 0], minlength=nv).astype(np.float64)
    # Pale sources (a white chest next to an orange shoulder) count more: a fill that averages
    # them with their neighbours turns white into grey-mauve.
    specks = ref_specks(ref) if mirror else None
    if mirror:
        sy, sx = pixels(VQ)
        speck = (s_fill > 0) & specks[sy, sx]
        s_fill = np.where(speck, 0.0, s_fill)
        n_speck_v = int(speck.sum())
    else:
        n_speck_v = 0
    mv_info = None
    if mv is not None:
        views, mv_dep, mv_fr, mv_info = mv_generate(co, vi, vn, d0, ref_path, work_dir, mv)
        rw1, rh1 = max(reg.rx1 - 1 - reg.rx0, 1), max(reg.ry1 - 1 - reg.ry0, 1)

        def plane_uv(Pp):  # the gates' frame: u from the outline's left, v from its top
            px, py = reg.to_ref(Pp @ right, Pp[:, 2])
            return ((px - reg.rx0) / rw1, (py - reg.ry0) / rh1)

        rm = ref_mask(ref)
        yy, xx = np.nonzero(rm)
        sn = np.einsum("mk,mkc->mc", bw, vn[vi[tt]])
        sn /= np.maximum(np.linalg.norm(sn, axis=1, keepdims=True), 1e-12)
        tc_k, tw_k = mv_sample_views(views, mv_dep, mv_fr, p, sn)
        # The generator lights and exposes each view its own way: match every view to the
        # picture cell by cell (mv_match) before the views are blended.
        match = mv_match(tc_k, tw_k, plane_uv(p), ref[yy, xx, :3].astype(np.float64),
                         ((xx - reg.rx0) / rw1, (yy - reg.ry0) / rh1))
        vc_k, vw_k = mv_sample_views(views, mv_dep, mv_fr, co, vn)
        mv_vc, mv_vw = mv_blend(mv_apply(match, vc_k, plane_uv(co)), vw_k)
        mv_info["calibration"] = {
            "method": "per view, per image-plane cell: Lab mean and spread onto the picture's",
            "grid": list(MV_MATCH_GRID), "view_texels": match[2],
            "mean_L_gain": match[0][..., 0].mean(axis=(1, 2)).round(3).tolist(),
            "mean_L_offset": match[1][..., 0].mean(axis=(1, 2)).round(2).tolist()}
        src = s_fill > 0  # the picture's own sunlit sources first, the views everywhere else
        fill_v = fill_colour(np.where(src[:, None], vcol, mv_vc),
                             np.where(src, s_fill, np.clip(mv_vw / MV_FULL_WEIGHT, 0, 1)),
                             edges, deg)
    else:
        fill_v = fill_colour(vcol, s_fill, edges, deg)
    if mirror and mv is None:
        neutral = (sat(vcol) < PALE_SAT_MAX) & (lum_v > NEUTRAL_LUMA_MIN) & (s_fill > 0)
        if neutral.any():
            bright = (lum_v / max(np.quantile(lum_v[neutral], 0.95), 1e-6)) ** NEUTRAL_POWER
            fill_n = fill_colour(vcol, np.where(neutral, s_fill * bright, 0.0), edges, deg)
            share = (diffuse(np.where(neutral, s_fill, 0.0)[:, None], edges, deg,
                             NEUTRAL_ITERS)[:, 0]
                     / np.maximum(diffuse(s_fill[:, None], edges, deg, NEUTRAL_ITERS)[:, 0], 1e-9))
            t = np.clip((share - NEUTRAL_SHARE[0]) / (NEUTRAL_SHARE[1] - NEUTRAL_SHARE[0]), 0, 1)
            fill_v = fill_v * (1 - t[:, None]) + fill_n * t[:, None]
    # Seam feather: diffuse the trust over a surface distance of FEATHER x height.
    mean_edge = float(np.linalg.norm(co[edges[:, 0]] - co[edges[:, 1]], axis=1).mean())
    iters = int(np.clip(round((FEATHER * height / max(mean_edge, 1e-9)) ** 2 * 2), 4, 80))
    a_diff = diffuse((a0 > 0).astype(np.float64)[:, None], edges, deg, iters)[:, 0]
    a_vert = np.clip((a_diff - 0.5) * 2.0, 0, 1) * (a0 > 0)  # 0 at the seam, 1 well inside

    # Texel level: detail from the picture inside the trusted area, vertex-interpolated fill else.
    fill_t = np.einsum("mk,mkc->mc", bw, fill_v[vi[tt]])
    alpha_t = np.einsum("mk,mk->m", bw, a_vert[vi[tt]])
    if mv is not None:
        mv_tc, mv_tw = mv_blend(mv_apply(match, tc_k, plane_uv(p)), tw_k)
        del tc_k, tw_k
        k_mv = np.clip(mv_tw / MV_FULL_WEIGHT, 0, 1)[:, None]
        fill_t = fill_t * (1 - k_mv) + mv_tc * k_mv
        mv_info["texels_from_views"] = int((mv_tw > 0).sum())
        mv_info["texels_no_view"] = int((mv_tw <= 0).sum())
        if not MV_PICTURE:
            alpha_t = np.zeros_like(alpha_t)
    colour = fill_t.copy()
    known = np.zeros(len(tt), bool)
    n_speck = [0]
    cand = np.nonzero(alpha_t > 0.01)[0]
    if len(cand):
        Q, WQ, seen = sources(p[cand], wt[cand], n[cand], GRAZE_MIN if mirror else MIN_FACING)
        pc, inside = sample(Q, ref64)
        ok = seen & inside
        if mirror:  # edge-on texels are painted on the tail only (thin: the smear is short)
            ok &= (WQ >= MIN_FACING) | in_tail(Q)
        kk = cand[ok]
        known[kk] = True
        # Specks (eye, nose) only on texels well facing the camera, and not from a mirrored point
        # that landed off the surface (a turned head is not symmetric about the body plane).
        pc_used = pc[ok]
        if mirror:
            lift = np.clip((WQ[ok] - SPECK_FULL[0]) / (SPECK_FULL[1] - SPECK_FULL[0]), 0, 1)
            lift = lift * (sources.snap[ok] <= MIRROR_SNAP * height)
            ty_, tx_ = pixels(Q[ok])
            drop = specks[ty_, tx_] & (lift < 1)
            n_speck[0] = int(drop.sum())
            pc_used = np.where(drop[:, None], fill_t[kk], pc_used)
        colour[kk] = alpha_t[kk, None] * pc_used + (1 - alpha_t[kk, None]) * fill_t[kk]
    alpha_used = np.where(known, alpha_t, 0.0)
    model_m = (model_side_measures(p, colour, n, cx, in_tail(p), height)
               if mirror and ref_name in REGION_GATES else None)
    gates = region_gates(ref_name, ref, reg, right, p, colour, facing=wt, normal=n,
                         far=(p[:, 0] < cx) if mirror else None, model=model_m)
    painted = int((alpha_used > 0.5).sum())

    img = np.zeros((size, size, 4), np.float32)
    img[..., :3] = 0.5
    img[ty, tx, :3] = colour
    img[ty, tx, 3] = 1.0
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
        "texels_projected_full_trust": int((alpha_used >= 0.99).sum()),
        "texels_low_frequency": int(len(ty) - painted),
        "mirrored_far_side": False,
        "mirrored_left_right": bool(use_mirror),
        "multiview": mv_info,
        "mirrored_points": int(n_mirrored[0]),
        "region_gates": gates,
        "registration": {
            "method": "outline fit: per-axis bbox scale + smoothed per-row shift (centre of the "
                      f"reference outline onto the centre of the model outline), {REG_ROWS} rows",
            "head_band": HEAD_BAND,
            "head_shift_of_width": round(reg.head_shift, 4),
            "head_width_ratio": round(reg.head_width_ratio, 3),
            "head_width_ratio_allowed": list(HEAD_WIDTH_RATIO),
            "head_painted_from_reference": head_ok,
            "max_row_shift": round(float(np.abs(reg.shift).max()), 4),
            "outline_warp_iou_before_after": reg.warp_iou,
            "head_to_head": reg.head_cues,
        },
        "fill": {
            "min_facing_cos": MIN_FACING, "full_facing_cos": FULL_FACING,
            "shadow_rel_to_band_median": SHADOW_REL, "shadow_bands": BANDS,
            "shadow_vertices_ignored": int(shadow.sum()),
            "method": "normalised vertex-graph diffusion, interpolated across triangles",
            "speck_area_frac": SPECK_AREA,
            "ref_speck_pixels": int(specks.sum()) if mirror else 0,
            "texels_speck_replaced": n_speck[0], "fill_specks_dropped": n_speck_v,
            "seam_feather_height_frac": FEATHER, "seam_feather_iterations": iters,
        },
    }
    info = {"facing": wt, "pos": p, "colour": colour, "projected": alpha_used > 0.5,
            "alpha": alpha_used, "texel_xy": (ty, tx)}
    return img, stats, info



def albedo_check(tex_path, info, ref, bands=4):
    """Mean luminance and saturation of the SAVED albedo texture against the reference, per height
    band (bottom to top). The texture is read back from the PNG on disk (so a colour-space error
    in saving shows), texels sit in a band by the height of the surface point they cover, reference
    pixels by their row inside the reference outline. Ratios near 1.0 mean the bake is true."""
    img = bpy.data.images.load(str(tex_path))
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    ty, tx = info["texel_xy"]
    rows = band_stats(px.reshape(h, w, 4)[ty, tx, :3], info["pos"][:, 2], ref, bands)
    for r in rows:
        r["luma_ratio"] = round(r["albedo_luma"] / max(r["ref_luma"], 1e-6), 3)
        r["sat_ratio"] = round(r["albedo_sat"] / max(r["ref_sat"], 1e-6), 3)
    return rows


def band_stats(tex_rgb, texel_z, ref, bands=4):
    """tex_rgb (m,3) texel colours, texel_z (m,) heights; per band luma/sat of texture vs ref."""
    z = (texel_z - texel_z.min()) / max(np.ptp(texel_z), 1e-9)
    ys, xs = np.where(ref_mask(ref))
    ry = (ys - ys.min()) / max(np.ptp(ys), 1)
    rgb = ref[ys, xs, :3]
    out = []
    for b in range(bands):
        lo, hi = b / bands, (b + 1) / bands
        sel = (z >= lo) & (z < hi + (1e-9 if b == bands - 1 else 0))
        rsel = (ry >= lo) & (ry < hi + (1e-9 if b == bands - 1 else 0))
        if not sel.any() or not rsel.any():
            continue
        out.append({"band": b, "albedo_luma": round(float(luma(tex_rgb[sel]).mean()), 4),
                    "ref_luma": round(float(luma(rgb[rsel]).mean()), 4),
                    "albedo_sat": round(float(sat(tex_rgb[sel]).mean()), 4),
                    "ref_sat": round(float(sat(rgb[rsel]).mean()), 4)})
    return out


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
# EV: studio shading averages 0.68 of the albedo (encoded); this makes the sheet read true
SHEET_EXPOSURE = 1.1


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
    # The factory default view transform (AgX) darkens and desaturates every colour; the sheet
    # must read the albedo true, so it is rendered with the Standard transform.
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = SHEET_EXPOSURE
    scene.render.resolution_x = scene.render.resolution_y = SHEET_RES
    scene.render.film_transparent = False
    sh = scene.display.shading
    sh.light = "STUDIO"
    sh.show_cavity = True
    sh.show_specular_highlight = False  # highlights wash the albedo out to white
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
    work, solid_info = make_solid(work, work.data.remesh_voxel_size)
    report["solid"] = solid_info
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
    img_arr, bake_stats, bake_info = bake_colour(work, ref, d0, tex_px, Path(o["ref"]).stem,
                                                mv=o["mv"], ref_path=o["ref"], work_dir=out)
    img = make_material(work, img_arr, out, tex_px)
    albedo = albedo_check(out / "texture.png", bake_info, ref)
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
        # one model is one skin: a second loose part (a tail cut off by the remesh) fails
        "single_part": {"parts": parts_mid - floaters2 if parts_mid else 1,
                        "ok": (parts_mid - floaters2 if parts_mid else 1) == 1},
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
        "albedo_vs_reference": albedo,
        "timings_s": timings,
    })
    report["timings_s"]["total"] = round(time.perf_counter() - t_all, 2)
    (out / "report.json").write_text(json.dumps(report, indent=2))
    print("REPORT", json.dumps({k: report[k] for k in ("triangles", "materials", "texture",
                                                        "silhouette")}))


if __name__ == "__main__":
    main()
