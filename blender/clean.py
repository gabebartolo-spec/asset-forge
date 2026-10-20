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
PALE_BOOST = 1.5     # fill: pale (white/grey, low saturation) sources count this much more
PALE_LUMA = (0.45, 0.65)   # luma ramp for "pale"
PALE_SAT = (0.30, 0.12)    # saturation ramp (below the first = 0, below the second = full)
SPECK_CAP = 0.10     # texels not well facing the camera may differ from the fill by this luma only
SPECK_SCALE = 8      # fill: iterations of the local-colour estimate for speck removal (animals)
SPECK_DARK = 0.6     # ... a source darker than this x the local luma is a speck
SPECK_WHITE = 0.30   # ... or whiter than the local luma by this
MIRROR_SNAP = 0.02   # mirrored source must land within this x height of the surface for specks
SPECK_FULL = (0.5, 0.7)    # facing cos from which the cap lifts completely
HEAD_DARK = 0.04          # picture: darkest fraction of the head box taken as the face features
MIRROR_DIRS = ((1.0, 0.0, 0.0),)  # camera directions that are side views (animals)


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


class Registration:
    """Fit the reference's alpha outline to the model's outline seen from the reference camera.
    Both outlines are normalised to their own bounding box (scale per axis), then each height row
    of the reference is shifted sideways so its outline centre sits on the model's outline centre
    (a smoothed shear), so a head that the generator centred but the picture drew left of centre
    still lands on the geometric head."""

    def __init__(self, P_all, right, ref, depth_dir=None):
        s, z = P_all @ right, P_all[:, 2]
        self.s0, self.sw = s.min(), max(np.ptp(s), 1e-9)
        self.z0, self.zh = z.min(), max(np.ptp(z), 1e-9)
        ys, xs = np.where(ref_mask(ref))
        self.rx0, self.rx1, self.ry0, self.ry1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
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


# Measured colour gates for animals (Step 2 fidelity check). Regions are boxes in the reference
# outline's own normalised coordinates (u from the left, v from the TOP of the bounding box);
# the same boxes are read on the reference picture and on the saved albedo, through the same
# registration, over every texel (so the front of the chest counts, not only the picture's side).
# Only references named here are checked.
REGION_GATES = {
    "fox": {
        "chest": (0.08, 0.28, 0.38, 0.58),
        "flank": (0.35, 0.65, 0.25, 0.55),
        "tail_body": (0.80, 0.97, 0.30, 0.70),
        "tail_tip": (0.90, 1.00, 0.72, 1.00),
        "legs": (0.00, 0.90, 0.78, 1.00),
    },
}
DARK_LUMA = 0.20    # a dark (black sock) pixel
PALE_LUMA_MIN, PALE_SAT_MAX = 0.55, 0.22   # a white/pale pixel


def region_stats(rgb):
    mx, mn = rgb.max(axis=1), rgb.min(axis=1)
    sa = (mx - mn) / np.maximum(mx, 1e-6)
    lu = luma(rgb)
    return {"n": int(len(rgb)), "rgb": rgb.mean(axis=0), "p90_luma": float(np.quantile(lu, 0.9)),
            "pale": float(((lu > PALE_LUMA_MIN) & (sa < PALE_SAT_MAX)).mean()),
            "dark": float((lu < DARK_LUMA).mean())}


def region_gate_checks(ref_s, tex_s):
    """(name, measured, limit text, ok) per gate; ref_s/tex_s are region_stats by region."""
    d = lambda k: float(np.linalg.norm(tex_s[k]["rgb"] - ref_s[k]["rgb"]))  # noqa: E731
    out = [
        ("legs_dark_fraction", tex_s["legs"]["dark"], f">= {0.5 * ref_s['legs']['dark']:.2f}",
         tex_s["legs"]["dark"] >= 0.5 * ref_s["legs"]["dark"]),
        ("chest_p90_luma_ratio", tex_s["chest"]["p90_luma"] / max(ref_s["chest"]["p90_luma"], 1e-6),
         "0.85 .. 1.25",
         0.85 <= tex_s["chest"]["p90_luma"] / max(ref_s["chest"]["p90_luma"], 1e-6) <= 1.25),
        ("chest_pale_fraction", tex_s["chest"]["pale"], f">= {0.6 * ref_s['chest']['pale']:.2f}",
         tex_s["chest"]["pale"] >= 0.6 * ref_s["chest"]["pale"]),
        ("flank_colour_distance", d("flank"), "<= 0.12", d("flank") <= 0.12),
        ("tail_body_colour_distance", d("tail_body"), "<= 0.15", d("tail_body") <= 0.15),
        ("tail_body_pale_fraction", tex_s["tail_body"]["pale"],
         f"<= {ref_s['tail_body']['pale'] + 0.10:.2f}",
         tex_s["tail_body"]["pale"] <= ref_s["tail_body"]["pale"] + 0.10),
        ("tail_tip_pale_fraction", tex_s["tail_tip"]["pale"],
         f">= {0.6 * ref_s['tail_tip']['pale']:.2f}",
         tex_s["tail_tip"]["pale"] >= 0.6 * ref_s["tail_tip"]["pale"]),
    ]
    return out


def region_gates(name, ref, reg, right, p, colour):
    boxes = REGION_GATES.get(name)
    if not boxes:
        return None
    rw1, rh1 = reg.rx1 - 1 - reg.rx0, reg.ry1 - 1 - reg.ry0
    rm = ref_mask(ref)
    yy, xx = np.mgrid[0:ref.shape[0], 0:ref.shape[1]]
    ru, rv = (xx - reg.rx0) / max(rw1, 1), 1 - (yy - reg.ry0) / max(rh1, 1)
    px, py = reg.to_ref(p @ right, p[:, 2])
    tu, tv = (px - reg.rx0) / max(rw1, 1), 1 - (py - reg.ry0) / max(rh1, 1)
    ref_s, tex_s = {}, {}
    for k, (u0, u1, v0, v1) in boxes.items():
        ref_s[k] = region_stats(ref[rm & (ru >= u0) & (ru < u1) & (rv >= v0) & (rv < v1)][:, :3])
        sel = (tu >= u0) & (tu < u1) & (tv >= v0) & (tv < v1)
        tex_s[k] = region_stats(colour[sel])
    checks = region_gate_checks(ref_s, tex_s)
    fmt = lambda s: {k: ([round(float(x), 3) for x in v] if k == "rgb" else round(v, 3))  # noqa
                     for k, v in s.items()}
    return {"reference": name, "passed": all(c[3] for c in checks),
            "gates": [{"gate": c[0], "value": round(float(c[1]), 3), "limit": c[2], "ok": bool(c[3])}
                      for c in checks],
            "reference_regions": {k: fmt(v) for k, v in ref_s.items()},
            "albedo_regions": {k: fmt(v) for k, v in tex_s.items()}}


def bake_colour(obj, ref, d0, size, ref_name=None):
    """Project `ref` onto obj (see module docstring). Returns (RGBA array, stats, info)."""
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
    reg = Registration(co, right, ref, None if mirror else d0)
    height = max(np.ptp(co[:, 2]), 1e-9)
    mask = ref_mask(ref, erode=3)
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

    def sources(Pp, w, Nn):
        """Source point on the surface that the camera sees for each point: the point itself, or
        (side views) for the far flank its left-right mirror image across the sagittal plane
        (x -> 2 cx - x only, never front-to-back) snapped to the nearest surface."""
        Q, WQ, NQ = Pp.copy(), w.copy(), Nn.copy()
        snap = np.zeros(len(Pp))
        if mirror:
            for k in np.nonzero(w < -MIN_FACING)[0]:
                m = Vector((2 * cx - Pp[k, 0], Pp[k, 1], Pp[k, 2]))
                loc, nrm, _i, _d = bvh.find_nearest(m)
                if loc is not None:
                    Q[k], NQ[k] = (loc.x, loc.y, loc.z), (nrm.x, nrm.y, nrm.z)
                    WQ[k] = nrm.dot(d_vec)
                    snap[k] = _d
                    n_mirrored[0] += 1
        seen = np.zeros(len(Pp), bool)
        for k in np.nonzero(WQ >= MIN_FACING)[0]:
            if bvh.ray_cast(Vector(Q[k] + NQ[k] * eps), d_vec)[0] is None:
                seen[k] = True
        sources.snap = snap
        return Q, WQ, seen

    def sample(Q, img):
        px, py = reg.to_ref(Q @ right, Q[:, 2])
        ix = np.clip(np.rint(px).astype(int), 0, rw - 1)
        iy = np.clip(np.rint(py).astype(int), 0, rh - 1)
        return img[iy, ix, :3], mask[iy, ix]

    ref64 = ref.astype(np.float64)
    blur5 = box_blur(ref64, 2)

    # Vertex level: where the picture is trusted (a0) and where the fill colour comes from.
    vw = vn @ d_arr
    VQ, VWQ, vseen = sources(co, vw, vn)
    vcol, vinside = sample(VQ, blur5)
    head_ok = reg.head_ok()
    vz = (co[:, 2] - co[:, 2].min()) / height
    a0 = ramp(VWQ) * (vseen & vinside)
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
    if mirror:
        # Specks (eye, nose, ear tip, a white patch) must not seed the fill: a source that is much
        # darker (or whiter) than the weighted colour around it at SPECK_SCALE iterations goes.
        xs_ = diffuse(np.concatenate([vcol * s_fill[:, None], s_fill[:, None]], axis=1), edges,
                      deg, SPECK_SCALE)
        loc = xs_[:, :3] / np.maximum(xs_[:, 3:4], 1e-9)
        l_loc, l_v = luma(loc), lum_v
        speck = (s_fill > 0) & (xs_[:, 3] > 1e-3) & ((l_v < SPECK_DARK * l_loc)
                                                      | (l_v > l_loc + SPECK_WHITE))
        s_fill = np.where(speck, 0.0, s_fill)
        n_speck_v = int(speck.sum())
    else:
        n_speck_v = 0
    sv_ = sat(vcol)
    pale = (np.clip((lum_v - PALE_LUMA[0]) / (PALE_LUMA[1] - PALE_LUMA[0]), 0, 1)
            * np.clip((PALE_SAT[0] - sv_) / (PALE_SAT[0] - PALE_SAT[1]), 0, 1))
    s_fill = s_fill * (1 + (PALE_BOOST * pale if mirror else 0.0))  # animals only
    fill_v = fill_colour(vcol, s_fill, edges, deg)
    # Seam feather: diffuse the trust over a surface distance of FEATHER x height.
    mean_edge = float(np.linalg.norm(co[edges[:, 0]] - co[edges[:, 1]], axis=1).mean())
    iters = int(np.clip(round((FEATHER * height / max(mean_edge, 1e-9)) ** 2 * 2), 4, 80))
    a_diff = diffuse((a0 > 0).astype(np.float64)[:, None], edges, deg, iters)[:, 0]
    a_vert = np.clip((a_diff - 0.5) * 2.0, 0, 1) * (a0 > 0)  # 0 at the seam, 1 well inside

    # Texel level: detail from the picture inside the trusted area, vertex-interpolated fill else.
    fill_t = np.einsum("mk,mkc->mc", bw, fill_v[vi[tt]])
    alpha_t = np.einsum("mk,mk->m", bw, a_vert[vi[tt]])
    colour = fill_t.copy()
    known = np.zeros(len(tt), bool)
    n_speck = [0]
    cand = np.nonzero(alpha_t > 0.01)[0]
    if len(cand):
        Q, WQ, seen = sources(p[cand], wt[cand], n[cand])
        pc, inside = sample(Q, ref64)
        ok = seen & inside
        kk = cand[ok]
        known[kk] = True
        # Dark or white specks (eye, nose, ear tip) only on texels well facing the camera: elsewhere
        # the picture may differ from the fill by SPECK_CAP in luma, no more.
        lift = np.clip((WQ[ok] - SPECK_FULL[0]) / (SPECK_FULL[1] - SPECK_FULL[0]), 0, 1)
        # a mirrored point that lands off the surface (a turned head is not symmetric about the
        # body plane) is not the other eye: no specks from it
        lift = lift * (sources.snap[ok] <= MIRROR_SNAP * height)
        dev = pc[ok] - fill_t[kk]
        dl = luma(dev)
        cap = SPECK_CAP + (1 - SPECK_CAP) * lift  # luma allowed, 1.0 = anything
        scale = np.minimum(1.0, cap / np.maximum(np.abs(dl), 1e-6))
        n_speck[0] = int((scale < 1).sum())
        pc_used = fill_t[kk] + dev * scale[:, None]
        colour[kk] = alpha_t[kk, None] * pc_used + (1 - alpha_t[kk, None]) * fill_t[kk]
    alpha_used = np.where(known, alpha_t, 0.0)
    gates = region_gates(ref_name, ref, reg, right, p, colour)
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
        "mirrored_left_right": bool(mirror),
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
            "head_to_head": reg.head_cues,
        },
        "fill": {
            "min_facing_cos": MIN_FACING, "full_facing_cos": FULL_FACING,
            "shadow_rel_to_band_median": SHADOW_REL, "shadow_bands": BANDS,
            "shadow_vertices_ignored": int(shadow.sum()),
            "method": "normalised vertex-graph diffusion, interpolated across triangles",
            "pale_boost": PALE_BOOST, "speck_cap_luma": SPECK_CAP,
            "texels_speck_limited": n_speck[0], "fill_specks_dropped": n_speck_v,
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
    img_arr, bake_stats, bake_info = bake_colour(work, ref, d0, tex_px, Path(o["ref"]).stem)
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
