"""Find the true pixel grid of a generated image and downsample on it (no smoothing)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

FALLBACK_PITCH = 8  # what pixel-art-xl at 1024 px usually produces
MIN_STEP = 60  # summed RGB difference below this is not a pixel edge
MIN_SHARE = 0.80  # share of all edge energy that must sit on the grid lines


@dataclass(frozen=True)
class GridInfo:
    pitch: int
    phase_x: int
    phase_y: int
    confidence: float  # share of edge energy on the grid beyond chance, 0..1
    found: bool


def _edge_profiles(rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Edge strength per column / row boundary. Weak steps (noise, JPEG fuzz) are ignored."""
    a = rgb.astype(np.int32)
    dx = np.abs(np.diff(a, axis=1)).sum(axis=2)  # step between col i and i+1 -> boundary i+1
    dy = np.abs(np.diff(a, axis=0)).sum(axis=2)
    dx[dx < MIN_STEP] = 0
    dy[dy < MIN_STEP] = 0
    return dx.sum(axis=0).astype(np.float64), dy.sum(axis=1).astype(np.float64)


def _best_phase(g: np.ndarray, pitch: int) -> tuple[int, float]:
    best_phase, best = 0, -1.0
    for phase in range(pitch):
        idx = np.arange(phase if phase else pitch, len(g) + 1, pitch) - 1
        s = g[idx].sum()
        if s > best:
            best, best_phase = s, phase
    return best_phase, best


def detect_grid(rgb: np.ndarray, min_pitch: int = 2, max_pitch: int = 32) -> GridInfo:
    """Pick the largest pitch that still holds nearly all the edge energy.

    Every divisor of the true pitch holds all the edges too, and a multiple of it holds only
    some, so the largest pitch above the share threshold is the true one.
    """
    gx, gy = _edge_profiles(rgb)
    total = gx.sum() + gy.sum()
    if total <= 0:
        return GridInfo(FALLBACK_PITCH, 0, 0, 0.0, False)
    best: GridInfo | None = None
    for p in range(min_pitch, max_pitch + 1):
        px, sx = _best_phase(gx, p)
        py, sy = _best_phase(gy, p)
        share = (sx + sy) / total
        if share >= MIN_SHARE:
            best = GridInfo(p, px, py, float(share - 1.0 / p), True)
    return best or GridInfo(FALLBACK_PITCH, 0, 0, 0.0, False)


def downsample_on_grid(rgb: np.ndarray, info: GridInfo) -> np.ndarray:
    """One output pixel per grid cell: the dominant colour of the cell's centre (no blending)."""
    p = info.pitch
    h, w, _ = rgb.shape
    nx = (w - info.phase_x) // p
    ny = (h - info.phase_y) // p
    q = p // 4
    out = np.zeros((ny, nx, 3), dtype=np.uint8)
    for j in range(ny):
        y0 = info.phase_y + j * p
        for i in range(nx):
            x0 = info.phase_x + i * p
            blk = rgb[y0 + q : y0 + p - q, x0 + q : x0 + p - q].reshape(-1, 3)
            out[j, i] = _dominant(blk)
    return out


def _dominant(pixels: np.ndarray) -> np.ndarray:
    p = pixels.astype(np.int32) >> 3
    keys = (p[:, 0] << 10) | (p[:, 1] << 5)
    keys |= pixels[:, 2] >> 3
    uniq, inv, counts = np.unique(keys, return_inverse=True, return_counts=True)
    win = counts.argmax()
    return pixels[inv == win].mean(axis=0).round().astype(np.uint8)
