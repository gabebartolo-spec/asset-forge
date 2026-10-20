"""Rotations, forward kinematics and the two-bone leg IK. Pure numpy, no Blender.

Frame: armature space of the Skeleton step (metres, Z up, feet on z=0, the model faces -Y, +X is
the character's left). A pose is a 4x4 "delta" per bone: the rigid move from where the bone sits
at rest to where it sits now, so a point p of the rest body moves to D @ p. Blender turns a delta
into a pose-bone basis with  basis = rest^-1 @ D_parent^-1 @ D @ rest  (see blender/animate.py).
"""

from __future__ import annotations

import numpy as np

UP = np.array([0.0, 0.0, 1.0])


def unit(v) -> np.ndarray:
    v = np.asarray(v, float)
    n = float(np.linalg.norm(v))
    return v / n if n > 1e-12 else v * 0.0


def rot(axis, deg: float) -> np.ndarray:
    """3x3 rotation about `axis` by `deg` degrees (right hand rule)."""
    a = unit(axis)
    t = np.radians(deg)
    k = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    return np.eye(3) + np.sin(t) * k + (1 - np.cos(t)) * (k @ k)


def rot_between(u, v) -> np.ndarray:
    """Smallest rotation taking direction u to direction v."""
    u, v = unit(u), unit(v)
    c = float(np.clip(u @ v, -1.0, 1.0))
    ax = np.cross(u, v)
    if np.linalg.norm(ax) < 1e-9:
        if c > 0:
            return np.eye(3)
        ax = np.cross(u, [1.0, 0, 0]) if abs(u[0]) < 0.9 else np.cross(u, [0, 1.0, 0])
    return rot(ax, np.degrees(np.arccos(c)))


def frame(u, p) -> np.ndarray:
    """Orthonormal basis (columns) from a main direction u and a second direction p."""
    u = unit(u)
    p = unit(np.asarray(p, float) - (np.asarray(p, float) @ u) * u)
    return np.stack([u, p, np.cross(u, p)], axis=1)


def about(R: np.ndarray, pivot, move=(0.0, 0.0, 0.0)) -> np.ndarray:
    """4x4: rotate by R about `pivot`, then translate by `move`."""
    M = np.eye(4)
    M[:3, :3] = R
    M[:3, 3] = np.asarray(pivot, float) + np.asarray(move, float) - R @ np.asarray(pivot, float)
    return M


def apply(M: np.ndarray, p) -> np.ndarray:
    return M[:3, :3] @ np.asarray(p, float) + M[:3, 3]


def two_bone_ik(hip, target, l1: float, l2: float, pole) -> tuple[np.ndarray, np.ndarray, bool]:
    """Knee position for a two-bone chain from `hip` to `target`, bending towards `pole`.
    Returns (knee, ankle, reached); when the target is out of reach the ankle stops short."""
    hip, target = np.asarray(hip, float), np.asarray(target, float)
    d = target - hip
    dist = float(np.linalg.norm(d))
    reach = (l1 + l2) * 0.9995
    reached = dist <= reach
    dist = float(np.clip(dist, abs(l1 - l2) + 1e-6, reach))
    dn = unit(d)
    ankle = hip + dn * dist
    p = np.asarray(pole, float) - (np.asarray(pole, float) @ dn) * dn
    if np.linalg.norm(p) < 1e-9:
        p = np.cross(dn, [1.0, 0, 0])
    p = unit(p)
    cos_a = np.clip((l1 * l1 + dist * dist - l2 * l2) / (2 * l1 * dist), -1.0, 1.0)
    sin_a = np.sqrt(1 - cos_a * cos_a)
    knee = hip + l1 * (cos_a * dn + sin_a * p)
    return knee, ankle, reached
