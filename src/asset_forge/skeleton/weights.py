"""Skin weights as an (N vertices x B bones) numpy matrix: the 4-influence limit and the
fallback used when Blender's automatic weights fail on a generated mesh."""

from __future__ import annotations

import numpy as np

from asset_forge.skeleton.templates import MAX_INFLUENCES


def limit_influences(w: np.ndarray, k: int = MAX_INFLUENCES) -> np.ndarray:
    """Keep each vertex's k strongest bones and renormalise so the weights sum to 1."""
    w = np.asarray(w, float).copy()
    if w.shape[1] > k:
        drop = np.argsort(w, axis=1)[:, : w.shape[1] - k]
        np.put_along_axis(w, drop, 0.0, axis=1)
    s = w.sum(axis=1, keepdims=True)
    return np.divide(w, s, out=np.zeros_like(w), where=s > 0)


def influence_counts(w: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    return (np.asarray(w) > eps).sum(axis=1)


def segment_distance(p: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Distance from each point of p (N,3) to the segment a-b."""
    ab = b - a
    t = np.clip(((p - a) @ ab) / max(float(ab @ ab), 1e-12), 0.0, 1.0)
    return np.linalg.norm(p - (a + t[:, None] * ab), axis=1)


def distance_weights(verts: np.ndarray, heads: np.ndarray, tails: np.ndarray,
                     power: float = 3.0, k: int = MAX_INFLUENCES) -> np.ndarray:
    """Envelope-style fallback: a vertex follows the bones it is nearest to, weight falling
    off with distance from the bone segment. Always gives every vertex a weight."""
    d = np.stack([segment_distance(verts, h, t) for h, t in zip(heads, tails, strict=True)], axis=1)
    scale = max(float(np.ptp(verts, axis=0).max()), 1e-9) * 0.01
    w = 1.0 / (d + scale) ** power
    # a bone much farther than the nearest one contributes nothing
    w[d > d.min(axis=1, keepdims=True) * 2.5 + scale] = 0.0
    return limit_influences(w, k)
