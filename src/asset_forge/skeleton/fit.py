"""Fit a fixed skeleton template to a cleaned mesh. Pure numpy, no Blender.

Input: an (N, 3) array of vertex positions in the Clean step's frame (metres, Z up, feet on
z=0, the model faces -Y). Output: {joint name: (x, y, z)} for every joint of the template.
The fit measures the mesh (neck, legs, arms, feet, tail) and falls back to body proportions
whenever a measurement is missing, so it always returns a full, sane skeleton.
"""

from __future__ import annotations

import numpy as np

from asset_forge.skeleton.templates import joint_names

Joints = dict[str, np.ndarray]
UP = np.array([0.0, 0.0, 1.0])


def _band(v: np.ndarray, lo: float, hi: float, axis: int = 2) -> np.ndarray:
    return v[(v[:, axis] >= lo) & (v[:, axis] < hi)]


def _largest_gap(xs: np.ndarray, lo: float, min_gap: float):
    """Widest empty stretch of sorted xs above `lo`; returns (below, above) or None."""
    xs = np.sort(xs[xs > lo])
    if len(xs) < 2:
        return None
    d = np.diff(xs)
    i = int(d.argmax())
    return (xs[i], xs[i + 1]) if d[i] > min_gap else None


def fit_humanoid(v: np.ndarray) -> Joints:
    v = np.asarray(v, float)
    H = float(v[:, 2].max())
    J: Joints = {}

    # neck: narrowest slice of the upper body, clamped to where a neck can be
    zs = np.arange(0.80, 0.90, 0.01)
    widths = []
    for z in zs:
        s = _band(v, z * H, (z + 0.015) * H)
        widths.append(np.ptp(s[:, 0]) if len(s) > 3 else np.inf)
    z_neck = float(np.clip(zs[int(np.argmin(widths))], 0.82, 0.88)) * H
    z_sh = 0.885 * z_neck
    z_hip = 0.52 * H

    def torso_y(z):
        s = _band(v, z - 0.02 * H, z + 0.02 * H)
        s = s[np.abs(s[:, 0]) < 0.09 * H]
        return float(s[:, 1].mean()) if len(s) else 0.0

    yc = torso_y(0.6 * H)
    J["Root"] = np.array([0, yc, 0.0])
    J["Hips"] = np.array([0, torso_y(z_hip), z_hip])
    J["Spine"] = np.array([0, torso_y(z_hip + 0.07 * H), z_hip + 0.07 * H])
    J["Chest"] = np.array([0, torso_y(z_sh - 0.09 * H), z_sh - 0.09 * H])
    J["UpperChest"] = np.array([0, torso_y(z_sh - 0.04 * H), z_sh - 0.04 * H])
    J["Neck"] = np.array([0, torso_y(z_neck - 0.01 * H), z_neck - 0.01 * H])
    head_s = _band(v, z_neck + 0.01 * H, H + 1)
    hy = float(head_s[:, 1].mean()) if len(head_s) else yc
    J["Head"] = np.array([0, hy, z_neck + 0.025 * H])
    J["HeadTop"] = np.array([0, hy, H])

    ref = _band(v, 0.45 * H, 0.55 * H)
    for sgn, side in ((1, "Left"), (-1, "Right")):
        # arms: split off the torso at the gap beside it; the hand is the lowest part of the arm
        sh_s = _band(v, z_sh - 0.02 * H, z_sh + 0.02 * H)
        sx = 0.8 * float(np.abs(sh_s[:, 0]).max()) if len(sh_s) else 0.17 * H
        sx = min(sx, 0.2 * H)
        sy = torso_y(z_sh)
        shoulder = np.array([sgn * sx, sy, z_sh])
        gap = _largest_gap(sgn * ref[:, 0], 0.08 * H, 0.015 * H)
        wrist = tip = None
        if gap is not None:
            xt = 0.5 * (gap[0] + gap[1])
            arm = v[(sgn * v[:, 0] > xt) & (v[:, 2] < 0.62 * H) & (v[:, 2] > 0.25 * H)]
            if len(arm) > 20:
                hand_c = arm[arm[:, 2] < arm[:, 2].min() + 0.07 * H].mean(axis=0)
                d = shoulder - hand_c
                d /= np.linalg.norm(d)
                wrist = hand_c + 0.035 * H * d
                tip = wrist + 2.0 * (hand_c - wrist)
        if wrist is None:  # arms glued to the body: hang them at a relaxed angle
            wrist = shoulder + np.array([sgn * 0.07 * H, 0.0, -0.30 * H])
            tip = wrist + np.array([sgn * 0.02 * H, 0.0, -0.08 * H])
        J[f"{side}Shoulder"] = np.array([sgn * 0.3 * sx, sy, z_sh + 0.01 * H])
        J[f"{side}UpperArm"] = shoulder
        J[f"{side}LowerArm"] = 0.5 * (shoulder + wrist) + np.array([0, 0.01 * H, 0])
        J[f"{side}Hand"] = wrist
        J[f"{side}HandTip"] = tip

        # legs: everything on this side below the skirt
        leg = v[(sgn * v[:, 0] > 0.01 * H) & (v[:, 2] < 0.24 * H)]
        z_ank = 0.055 * H
        z_knee = 0.5 * (z_ank + z_hip)
        foot = _band(leg, 0.0, 0.08 * H)
        knee_s = _band(leg, z_knee - 0.03 * H, z_knee + 0.03 * H)
        fx = float(foot[:, 0].mean()) if len(foot) else sgn * 0.08 * H
        kx = float(knee_s[:, 0].mean()) if len(knee_s) else fx
        ky = float(knee_s[:, 1].mean()) if len(knee_s) else yc
        y_toe = float(foot[:, 1].min()) if len(foot) else yc - 0.05 * H
        y_heel = float(foot[:, 1].max()) if len(foot) else yc + 0.03 * H
        flen = y_heel - y_toe
        J[f"{side}UpperLeg"] = np.array([sgn * min(abs(kx) * 0.9, 0.1 * H), J["Hips"][1], z_hip])
        J[f"{side}LowerLeg"] = np.array([kx, ky, z_knee])
        J[f"{side}Foot"] = np.array([fx, y_heel - 0.7 * flen, z_ank])
        J[f"{side}Toes"] = np.array([fx, y_toe + 0.3 * flen, 0.025 * H])
        J[f"{side}ToesTip"] = np.array([fx, y_toe, 0.012 * H])
    return J


# ---------------------------------------------------------------- animals


class _Frame:
    """Local frame of an animal: a runs towards the head, b to the left, z is up."""

    def __init__(self, v: np.ndarray):
        xy = v[:, :2]
        c = xy.mean(axis=0)
        w, vec = np.linalg.eigh(np.cov((xy - c).T))
        u = vec[:, int(np.argmax(w))]
        if u[1] > 0:  # the model faces -Y
            u = -u
        self.u = np.array([u[0], u[1], 0.0])
        self.w = np.cross(UP, self.u)  # left
        self.o = np.array([c[0], c[1], 0.0])

    def to_local(self, p) -> np.ndarray:
        p = np.asarray(p, float)
        d = p - self.o
        return np.stack([d @ self.u, d @ self.w, p[..., 2]], axis=-1)

    def to_world(self, q) -> np.ndarray:
        q = np.asarray(q, float)
        return self.o + q[..., 0:1] * self.u + q[..., 1:2] * self.w + UP * q[..., 2:3]


def _two_means_1d(x: np.ndarray, iters: int = 20) -> np.ndarray:
    c = np.array([np.percentile(x, 25), np.percentile(x, 75)])
    lab = np.zeros(len(x), int)
    for _ in range(iters):
        lab = (np.abs(x - c[1]) < np.abs(x - c[0])).astype(int)
        if lab.min() == lab.max():
            break
        c = np.array([x[lab == 0].mean(), x[lab == 1].mean()])
    return lab


def _tail(L: np.ndarray, a_start: float, a_end: float, n: int, z_default: float):
    """Joints Tail1..Tail<n> and the tip, following the tail's own centreline: each joint sits
    at the (b, z) centre of the vertices in its slice of a."""
    edges = np.linspace(a_start, a_end, n + 1)
    mids = []
    for lo, hi in zip(edges[:-1], edges[1:], strict=True):
        s = L[(L[:, 0] >= min(lo, hi)) & (L[:, 0] <= max(lo, hi))]
        mids.append(s[:, 1:].mean(axis=0) if len(s) > 2 else np.array([0.0, z_default]))
    heads = [np.array([edges[k], *mids[k]]) for k in range(n)]
    tip = np.array([edges[-1], *mids[-1]])
    return heads, tip


def count_leg_columns(v: np.ndarray) -> int:
    """How many separate legs touch the ground: 2 for a bird, 4 for a fox. Counts the
    grid-connected blobs among the lowest vertices that hold a real share of them."""
    v = np.asarray(v, float)
    H = float(v[:, 2].max())
    low = v[v[:, 2] < 0.12 * H]
    if len(low) < 10:
        return 0
    fr = _Frame(v)
    span = max(float(np.ptp(fr.to_local(v)[:, 0])), 1e-6)
    P = fr.to_local(low)[:, :2]
    cell = span / 40
    ij = np.floor((P - P.min(axis=0)) / cell).astype(int)
    cells: dict[tuple, int] = {}
    for i, j in map(tuple, ij):
        cells[(i, j)] = cells.get((i, j), 0) + 1
    seen, sizes = set(), []
    for c in cells:
        if c in seen:
            continue
        stack, n = [c], 0
        seen.add(c)
        while stack:
            i, j = stack.pop()
            n += cells[(i, j)]
            for di in (-1, 0, 1):
                for dj in (-1, 0, 1):
                    nb = (i + di, j + dj)
                    if nb in cells and nb not in seen:
                        seen.add(nb)
                        stack.append(nb)
        sizes.append(n)
    return sum(1 for n in sizes if n >= 0.12 * len(P))


def fit_four_legged(v: np.ndarray) -> Joints:
    v = np.asarray(v, float)
    H = float(v[:, 2].max())
    fr = _Frame(v)
    L = fr.to_local(v)
    a_min, a_max = float(L[:, 0].min()), float(L[:, 0].max())
    length = a_max - a_min
    b0 = float(np.median(L[:, 1]))
    mid = L[(L[:, 0] > a_min + 0.4 * length) & (L[:, 0] < a_min + 0.6 * length)]
    z_back = float(np.percentile(mid[:, 2], 92)) if len(mid) else 0.75 * H
    z_sp = 0.76 * z_back

    # feet: the lowest vertices outside the tail zone, split left/right then hind/front
    feet_v = L[(L[:, 2] < 0.3 * H) & (L[:, 0] > a_min + 0.25 * length)]
    default_a = {"Hind": a_min + 0.3 * length, "Front": a_min + 0.7 * length}
    feet = {}
    for sgn, side in ((1, "Left"), (-1, "Right")):
        s = feet_v[sgn * (feet_v[:, 1] - b0) > 0.0]
        lab = _two_means_1d(s[:, 0]) if len(s) >= 8 else np.zeros(len(s), int)
        for k, part in ((0, "Hind"), (1, "Front")):
            grp = s[lab == k]
            if len(grp) >= 3:
                low = grp[grp[:, 2] < grp[:, 2].min() + 0.06 * H]
                feet[(part, side)] = (low[:, 0].mean(), low[:, 1].mean(), grp[:, 2].min())
            else:
                feet[(part, side)] = (default_a[part], b0 + sgn * 0.18 * H, 0.0)
    hind_a = float(np.mean([feet[("Hind", s)][0] for s in ("Left", "Right")]))
    front_a = float(np.mean([feet[("Front", s)][0] for s in ("Left", "Right")]))
    if front_a <= hind_a + 0.05 * length:  # leg pairs overlapped: trust the proportions
        hind_a, front_a = default_a["Hind"], default_a["Front"]

    Jl: dict[str, np.ndarray] = {}
    Jl["Root"] = np.array([hind_a, b0, 0.0])
    Jl["Hips"] = np.array([hind_a - 0.03 * length, b0, z_sp])
    Jl["Spine"] = np.array([0.5 * (hind_a + front_a), b0, z_sp + 0.02 * H])
    Jl["Chest"] = np.array([front_a, b0, z_sp + 0.03 * H])

    head_s = L[L[:, 0] > a_max - 0.2 * length]
    hz = max(float(np.median(head_s[:, 2])) if len(head_s) else z_back, z_sp)
    Jl["Head"] = np.array([a_max - 0.2 * length, b0, hz])
    Jl["HeadTip"] = np.array([a_max, b0, float(np.percentile(head_s[:, 2], 40)) if len(head_s)
                              else hz])
    Jl["Neck1"] = Jl["Chest"] + np.array([0.02 * length, 0, 0.0])
    Jl["Neck2"] = 0.5 * (Jl["Neck1"] + Jl["Head"]) + np.array([0, 0, 0.01 * H])

    a_t0 = hind_a - 0.08 * length
    heads, tip = _tail(L[L[:, 0] < a_t0 + 0.02 * length], a_t0, a_min, 4, z_sp)
    for k, h in enumerate(heads, start=1):
        Jl[f"Tail{k}"] = h
    Jl["TailTip"] = tip

    for (part, side), (a, b, z) in feet.items():
        top_a = 0.5 * ((hind_a if part == "Hind" else front_a) + a)
        z_ank = max(0.07 * H, z + 0.04 * H)
        z_top = z_sp - 0.02 * H
        shift = 0.03 * length * (1 if part == "Hind" else -1)
        Jl[f"{part}{side}UpperLeg"] = np.array([top_a, b0 + 0.8 * (b - b0), z_top])
        Jl[f"{part}{side}LowerLeg"] = np.array([a + shift, b, 0.5 * (z_top + z_ank)])
        Jl[f"{part}{side}Foot"] = np.array([a - (0.01 * length if part == "Hind" else 0), b, z_ank])
        Jl[f"{part}{side}FootTip"] = np.array([a + 0.03 * length, b, z + 0.01 * H])
    return {k: fr.to_world(p) for k, p in Jl.items()}


def fit_bird(v: np.ndarray) -> Joints:
    v = np.asarray(v, float)
    H = float(v[:, 2].max())
    fr = _Frame(v)
    L = fr.to_local(v)
    a_min, a_max = float(L[:, 0].min()), float(L[:, 0].max())
    length = a_max - a_min
    b0 = float(np.median(L[:, 1]))
    body = L[L[:, 2] > 0.35 * H]
    half_w = float(np.percentile(np.abs(body[:, 1] - b0), 90))
    a_c = float(body[:, 0].mean())
    z_c = 0.55 * H

    Jl: dict[str, np.ndarray] = {}
    Jl["Root"] = np.array([a_c, b0, 0.0])
    Jl["Hips"] = np.array([a_c - 0.08 * length, b0, z_c])
    Jl["Chest"] = np.array([a_c + 0.1 * length, b0, z_c + 0.04 * H])
    head_s = L[(L[:, 0] > a_max - 0.3 * length) & (L[:, 2] > 0.6 * H)]
    hz = float(np.median(head_s[:, 2])) if len(head_s) else 0.85 * H
    Jl["Head"] = np.array([a_max - 0.2 * length, b0, hz])
    Jl["HeadTip"] = np.array([a_max, b0, float(np.percentile(head_s[:, 2], 30)) if len(head_s)
                              else hz])
    Jl["Neck1"] = Jl["Chest"] + np.array([0.05 * length, 0, 0.05 * H])
    Jl["Neck2"] = 0.5 * (Jl["Neck1"] + Jl["Head"])

    a_t0 = Jl["Hips"][0] - 0.05 * length
    heads, tip = _tail(L[L[:, 0] < a_t0 + 0.02 * length], a_t0, a_min, 2, z_c)
    Jl["Tail1"], Jl["Tail2"], Jl["TailTip"] = heads[0], heads[1], tip

    legs = L[L[:, 2] < 0.3 * H]
    for sgn, side in ((1, "Left"), (-1, "Right")):
        s = legs[sgn * (legs[:, 1] - b0) > 0]
        if len(s) > 3:
            lb, fa, toe_a = float(s[:, 1].mean()), float(s[:, 0].mean()), float(s[:, 0].max())
        else:
            lb, fa, toe_a = b0 + sgn * 0.3 * half_w, a_c, a_c + 0.1 * length
        Jl[f"{side}UpperLeg"] = np.array([a_c - 0.03 * length, b0 + 0.6 * (lb - b0), 0.42 * H])
        Jl[f"{side}LowerLeg"] = np.array([fa - 0.02 * length, lb, 0.22 * H])
        Jl[f"{side}Foot"] = np.array([fa, lb, 0.04 * H])
        Jl[f"{side}FootTip"] = np.array([toe_a, lb, 0.01 * H])
        wb = b0 + sgn * 0.85 * half_w
        Jl[f"{side}Wing1"] = np.array([a_c + 0.04 * length, wb, z_c + 0.1 * H])
        Jl[f"{side}Wing2"] = np.array([a_c - 0.1 * length, wb, z_c + 0.04 * H])
        Jl[f"{side}WingTip"] = np.array([a_c - 0.3 * length, wb, z_c - 0.02 * H])
    return {k: fr.to_world(p) for k, p in Jl.items()}


def fit(v: np.ndarray, template: str) -> Joints:
    fn = {"humanoid": fit_humanoid, "four_legged": fit_four_legged, "bird": fit_bird}[template]
    J = fn(v)
    missing = [j for j in joint_names(template) if j not in J]
    if missing:
        raise ValueError(f"the fit left out joints: {missing}")
    return {k: np.asarray(J[k], float) for k in joint_names(template)}


def choose_animal_template(v: np.ndarray) -> str:
    """Two legs on the ground is a bird (wings in place of front legs); otherwise four-legged."""
    return "bird" if count_leg_columns(v) <= 2 else "four_legged"
