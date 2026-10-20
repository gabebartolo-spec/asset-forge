"""Find a creature's body core and limbs from its shape, and count legs and arms.

Used twice: Step 3 proposes a monster skeleton from it (the user then fixes markers), and Step 1
counts limbs on the fresh mesh so an impossible count (a spider with ten legs) is caught.

Method (numpy + scipy, no Blender): voxelise the solid; the body core is the thick part (voxels
deep inside, by distance transform) grown back to its surface; whatever is left after cutting
the core away falls into pieces. Each piece is walked outwards from where it meets the core
(geodesic distance in voxels) and sliced into bands; the bands' connected parts form a tree,
and every long branch of that tree is one limb (short ones are fingers, toes, bumps). A limb
whose tip reaches the ground is a leg; otherwise it is an arm (root beside the body), a head
(root in front or on top) or a tail (root behind or below).

Frame: metres, Z up, the model faces -Y (the Clean step's frame and the generators' own).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import ndimage, sparse
from scipy.sparse import csgraph

RES = 160  # voxels along the longest side
CORE_DEPTH = 0.5  # core seed: voxels at least this share of the deepest voxel's depth
CORE_GROW = 1.1  # grow the seed back by this many times its depth
CORE_MARGIN = 0.3  # and this many core depths more (rounds off box corners)
MIN_LIMB = 1.0  # a limb is at least this many core depths long (beyond the core)
GROUND = 0.12  # a tip below this share of the height is on the ground
FULL = np.ones((3, 3, 3), bool)
HALF = [d for d in np.argwhere(FULL) - 1 if tuple(d) > (0, 0, 0)]


@dataclass
class Limb:
    kind: str  # leg | arm | head | tail
    joints: list[list[float]]  # root .. tip, 4 points
    length: float

    def public(self) -> dict:
        return {"kind": self.kind, "joints": [[round(c, 4) for c in p] for p in self.joints]}


@dataclass
class Proposal:
    spine: list[list[float]]  # 4 points, rear/bottom to front/top
    limbs: list[Limb] = field(default_factory=list)
    height: float = 0.0

    def counts(self) -> dict[str, int]:
        out = {"legs": 0, "arms": 0, "heads": 0, "tails": 0}
        for lb in self.limbs:
            out[lb.kind + "s"] += 1
        return out

    def public(self) -> dict:
        return {"spine": [[round(c, 4) for c in p] for p in self.spine],
                "limbs": [lb.public() for lb in self.limbs], "counts": self.counts(),
                "height": round(self.height, 4)}


# ---------------------------------------------------------------- voxels


def _surface_points(v: np.ndarray, f: np.ndarray, step: float) -> np.ndarray:
    """Points over every triangle, no farther apart than `step`."""
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    longest = np.max(np.stack([np.linalg.norm(b - a, axis=1), np.linalg.norm(c - b, axis=1),
                               np.linalg.norm(a - c, axis=1)]), axis=0)
    n = np.clip(np.ceil(longest / step).astype(int), 1, 256)
    pts = [v]
    for k in np.unique(n):
        sel = n == k
        i, j = np.meshgrid(np.arange(k + 1), np.arange(k + 1), indexing="ij")
        keep = i + j <= k
        u, w = i[keep] / k, j[keep] / k
        pa, pb, pc = a[sel], b[sel], c[sel]
        p = (pa[:, None] * (1 - u - w)[None, :, None] + pb[:, None] * u[None, :, None]
             + pc[:, None] * w[None, :, None])
        pts.append(p.reshape(-1, 3))
    return np.vstack(pts)


def voxelize(v: np.ndarray, f: np.ndarray, res: int = RES):
    """Solid occupancy grid: (grid, origin, voxel size). Keeps the biggest solid part only."""
    lo, hi = v.min(axis=0), v.max(axis=0)
    size = float((hi - lo).max())
    vox = size / (res - 1)
    origin = lo - 2 * vox
    shape = np.ceil((hi - lo) / vox).astype(int) + 5
    p = _surface_points(v, f, 0.5 * vox)
    ijk = np.floor((p - origin) / vox).astype(int)
    grid = np.zeros(shape, bool)
    grid[ijk[:, 0], ijk[:, 1], ijk[:, 2]] = True
    grid = ndimage.binary_fill_holes(grid)
    lab, n = ndimage.label(grid, FULL)
    if n > 1:
        sizes = ndimage.sum_labels(grid, lab, range(1, n + 1))
        grid = lab == (int(np.argmax(sizes)) + 1)
    return grid, origin, vox


def _geodesic(mask: np.ndarray, start: np.ndarray) -> np.ndarray:
    """Steps from `start` to every voxel of `mask` (26-connected); -1 where unreachable."""
    idx = np.full(mask.shape, -1, np.int64)
    n = int(mask.sum())
    idx[mask] = np.arange(n)
    rows, cols = [], []
    for d in HALF:
        a = idx[tuple(slice(max(0, -k), mask.shape[i] - max(0, k)) for i, k in enumerate(d))]
        b = idx[tuple(slice(max(0, k), mask.shape[i] - max(0, -k)) for i, k in enumerate(d))]
        m = (a >= 0) & (b >= 0)
        rows.append(a[m])
        cols.append(b[m])
    src = idx[start & mask]
    out = np.full(mask.shape, -1, np.int32)
    if len(src) == 0:
        return out
    # one virtual source (number n) joined to every start voxel
    r = np.concatenate(rows + [np.full(len(src), n)])
    c = np.concatenate(cols + [src])
    g = sparse.csr_matrix((np.ones(len(r), np.int8), (r, c)), shape=(n + 1, n + 1))
    d = csgraph.shortest_path(g, directed=False, unweighted=True, indices=[n])[0][:n] - 1
    ok = np.isfinite(d)
    vals = np.full(n, -1, np.int32)
    vals[ok] = d[ok].astype(np.int32)
    out[mask] = vals
    return out


def _centre(grid: np.ndarray, dt: np.ndarray) -> tuple:
    """The body's middle: the deepest voxel halfway (by walking inside the body) between the
    two points farthest apart (leg tip to leg tip, nose to tail, head to foot)."""
    one = np.zeros_like(grid)
    one[np.unravel_index(int(np.argmax(dt)), dt.shape)] = True
    da = _geodesic(grid, one)
    p = np.zeros_like(grid)
    p[np.unravel_index(int(np.argmax(da)), da.shape)] = True
    dp = _geodesic(grid, p)
    q = np.zeros_like(grid)
    q[np.unravel_index(int(np.argmax(dp)), dp.shape)] = True
    dq = _geodesic(grid, q)
    mid = grid & (dp >= 0) & (np.abs(dp - dq) <= 2)
    score = np.where(mid, dt, -1.0)
    return np.unravel_index(int(np.argmax(score)), dt.shape)


# ---------------------------------------------------------------- the tree of one piece


def _branches(piece: np.ndarray, contact: np.ndarray, band: int, min_len: int):
    """Long branches of one piece: lists of voxel-index arrays per band, root to tip."""
    g = _geodesic(piece, contact)
    if g.max() < min_len:
        return [], g
    bands = np.where(g >= 0, g // band, -1)
    node = np.zeros(piece.shape, np.int32)
    info = []  # per node: (band, voxel indices)
    for b in range(int(bands.max()) + 1):
        lab, n = ndimage.label(bands == b, FULL)
        for k in range(1, n + 1):
            sel = lab == k
            node[sel] = len(info) + 1
            info.append((b, np.argwhere(sel)))
    # parents: a node's neighbour in the band before it (the biggest contact wins)
    parent = {}
    touch: dict[tuple[int, int], int] = {}
    pad = np.pad(node, 1)
    core = pad[1:-1, 1:-1, 1:-1]
    for d in np.argwhere(FULL) - 1:
        if not d.any():
            continue
        sh = pad[1 + d[0]:pad.shape[0] - 1 + d[0], 1 + d[1]:pad.shape[1] - 1 + d[1],
                 1 + d[2]:pad.shape[2] - 1 + d[2]]
        m = (core > 0) & (sh > 0)
        a, c = core[m], sh[m]
        for x, y in set(zip(a.tolist(), c.tolist(), strict=True)):
            if info[x - 1][0] == info[y - 1][0] + 1:
                touch[(x, y)] = touch.get((x, y), 0) + 1
    for (x, y), cnt in touch.items():
        if x not in parent or cnt > touch[(x, parent[x])]:
            parent[x] = y
    children: dict[int, list[int]] = {}
    for x, y in parent.items():
        children.setdefault(y, []).append(x)
    # depth below each node (in bands), deepest first
    reach = {}
    for x in sorted(range(1, len(info) + 1), key=lambda k: -info[k - 1][0]):
        reach[x] = max([reach[c] + 1 for c in children.get(x, [])], default=0)
    min_bands = max(1, int(np.ceil(min_len / band)))
    out = []

    def walk(start: int, prefix: list[int]):
        path = prefix + [start]
        x = start
        while children.get(x):
            kids = sorted(children[x], key=lambda c: -reach[c])
            for side in kids[1:]:
                if reach[side] + 1 >= min_bands:
                    walk(side, [x])
            x = kids[0]
            path.append(x)
        out.append(path)

    roots = [x for x in range(1, len(info) + 1) if info[x - 1][0] == 0]
    for r in sorted(roots, key=lambda k: -reach[k]):
        walk(r, [])
    return [[info[x - 1][1] for x in path] for path in out
            if (len(path) - 1) * band >= min_len], g


def _resample(points: np.ndarray, n: int = 4) -> np.ndarray:
    seg = np.linalg.norm(np.diff(points, axis=0), axis=1)
    s = np.concatenate([[0], np.cumsum(seg)])
    if s[-1] <= 0:
        return np.repeat(points[:1], n, axis=0)
    t = np.linspace(0, s[-1], n)
    return np.stack([np.interp(t, s, points[:, k]) for k in range(3)], axis=1)


# ---------------------------------------------------------------- the proposal


def _core(grid, dt, centre, frac, grow):
    """The thick body round `centre`: voxels at least `frac` of the centre's depth that join
    up with it, grown back as the union of balls of `grow` x each voxel's depth."""
    depth = float(dt[centre])
    lab, _ = ndimage.label(dt >= frac * depth, FULL)
    seed = lab == lab[centre]
    core = np.zeros_like(grid)
    top = float(dt[seed].max())
    edges = np.linspace(frac * depth, top, 5)
    for lo, hi in zip(edges[:-1], edges[1:], strict=True):
        part = seed & (dt >= lo) & (dt <= hi + 1e-9)
        if part.any():
            core |= ndimage.distance_transform_edt(~part) <= grow * lo + CORE_MARGIN * depth
    return core & grid, depth


def propose(v: np.ndarray, f: np.ndarray, res: int = RES) -> Proposal:
    """Spine through the body core and one 4-joint chain per limb."""
    v, f = np.asarray(v, float), np.asarray(f, np.int64)
    grid, origin, vox = voxelize(v, f, res)
    z0 = float(v[:, 2].min())
    height = float(v[:, 2].max()) - z0

    def world(ijk):
        return origin + (np.asarray(ijk, float) + 0.5) * vox

    dt = ndimage.distance_transform_edt(grid)
    core, depth = _core(grid, dt, _centre(grid, dt), CORE_DEPTH, CORE_GROW)
    rest = grid & ~core
    near_core = ndimage.binary_dilation(core, FULL)

    cpts = world(np.argwhere(core))
    centre = cpts.mean(axis=0)
    half_x = max(float(np.percentile(np.abs(cpts[:, 0] - centre[0]), 95)), vox)

    band = max(2, int(round(0.4 * CORE_DEPTH * depth)))
    min_len = max(3, int(round(MIN_LIMB * depth)))
    limbs: list[Limb] = []
    plab, pn = ndimage.label(rest, FULL)
    for obj, sl in zip(range(1, pn + 1), ndimage.find_objects(plab), strict=True):
        sl = tuple(slice(max(s.start - 1, 0), s.stop + 1) for s in sl)
        piece = plab[sl] == obj
        contact = piece & near_core[sl]
        if not contact.any():
            continue
        off = np.array([s.start for s in sl])
        paths, g = _branches(piece, contact, band, min_len)
        for path in paths:
            pts = [world(ix.mean(axis=0) + off) for ix in path]
            last = path[-1]
            pts.append(world(last[np.argmax(g[tuple(last.T)])] + off))
            pts = np.array(pts)
            chain = _resample(pts)
            length = float(np.linalg.norm(np.diff(pts, axis=0), axis=1).sum())
            limbs.append(Limb("", chain.tolist(), length))
    _classify(limbs, centre, half_x, z0, height)
    return Proposal(_spine(cpts, z0), _order(limbs, centre), height)


def _goes_down(c: np.ndarray, h: float, by: float) -> bool:
    return c[0, 2] - c[-1, 2] > by * h


def _classify(limbs: list[Limb], centre: np.ndarray, half_x: float, z0: float,
              h: float) -> None:
    """Leg: runs down to the ground, or down from where the grounded legs start (a raised
    spider leg). Arm: runs out beside the body. Head: forward or up. Tail: backward."""
    chains = [np.array(lb.joints) for lb in limbs]
    grounded = [c[-1, 2] - z0 < GROUND * h and _goes_down(c, h, 0.15) for c in chains]
    top = max([c[0, 2] for c, g in zip(chains, grounded, strict=True) if g], default=None)
    for lb, c, g in zip(limbs, chains, grounded, strict=True):
        side = float(np.mean(np.abs(c[1:, 0] - centre[0])))
        if g or (top is not None and c[0, 2] <= top + 0.1 * h and _goes_down(c, h, 0.2)
                 and c[-1, 2] - z0 < 0.45 * h):
            lb.kind = "leg"
        elif side > max(0.6 * half_x, 0.1 * h):
            lb.kind = "arm"
        elif c[-1, 1] - c[0, 1] > max(0.0, c[-1, 2] - c[0, 2]):
            lb.kind = "tail"
        else:
            lb.kind = "head"


def _order(limbs: list[Limb], centre: np.ndarray) -> list[Limb]:
    """Legs, arms, heads, tails; each front to back, then left before right."""
    rank = {"leg": 0, "arm": 1, "head": 2, "tail": 3}
    return sorted(limbs, key=lambda lb: (rank[lb.kind], round(lb.joints[0][1] - centre[1], 2),
                                         -lb.joints[0][0]))


def _spine(cpts: np.ndarray, z0: float) -> list[list[float]]:
    """Four points along the core's long axis: rear to front, or bottom to top if upright."""
    c = cpts.mean(axis=0)
    if len(cpts) < 4:
        return [(c + [0, 0, k * 0.01]).tolist() for k in range(4)]
    w, vec = np.linalg.eigh(np.cov((cpts - c).T))
    axis = vec[:, int(np.argmax(w))]
    if abs(axis[2]) > 0.7:
        axis = axis if axis[2] > 0 else -axis
    else:
        axis = axis if axis[1] < 0 else -axis
    t = (cpts - c) @ axis
    lo, hi = np.percentile(t, 5), np.percentile(t, 95)
    pts = []
    for s in np.linspace(lo, hi, 4):
        near = cpts[np.abs(t - s) < 0.1 * (hi - lo) + 1e-9]
        p = near.mean(axis=0) if len(near) else c + s * axis
        # the middle of a bent slice can fall outside the body (a hunched back): use the
        # body point closest to it, so every body-line marker starts inside
        pts.append(cpts[np.argmin(((cpts - p) ** 2).sum(axis=1))])
    return [p.tolist() for p in pts]


def count_limbs(v: np.ndarray, f: np.ndarray) -> dict[str, int]:
    return propose(v, f).counts()


OUTSIDE_TOL = 0.02  # a marker may sit this share of the model's longest side outside its skin


def outside_joints(v: np.ndarray, f: np.ndarray, chain: dict,
                   res: int = RES) -> list[tuple[int, int]]:
    """(limb, joint) for every marker that sits outside the body (limb -1 is the body line).
    A bone outside the body moves nothing, so the page names these and marks them red."""
    v, f = np.asarray(v, float), np.asarray(f, np.int64)
    grid, origin, vox = voxelize(v, f, res)
    gap = ndimage.distance_transform_edt(~grid) * vox  # how far each empty voxel is from the solid
    tol = max(2 * vox, OUTSIDE_TOL * float(np.ptp(v, axis=0).max()))

    def out(p) -> bool:
        ijk = np.floor((np.asarray(p, float) - origin) / vox).astype(int)
        if (ijk < 0).any() or (ijk >= grid.shape).any():
            return True
        return bool(gap[tuple(ijk)] > tol)

    found = [(-1, j) for j, p in enumerate(chain.get("spine") or []) if out(p)]
    for i, lb in enumerate(chain.get("limbs") or []):
        found += [(i, j) for j, p in enumerate(lb["joints"]) if out(p)]
    return found
