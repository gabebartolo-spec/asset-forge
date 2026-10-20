"""Split a turnaround sheet into its single-creature views (round 3).

SDXL draws a turnaround as a row (or several) of views, not always two. So the sheet is cut into
one image per creature, and the pipeline lets the gates choose which view is the front and which
is the back. Everything is deterministic and works on the sheet's own pixel grid.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

from .post import label, remove_background

CELL = 8  # the generator's pixel pitch; the sheet is labelled on blocks of this size
JOIN_CELLS = 2  # blocks apart that still belong to one creature (a tail, a raised arm)
MIN_HEIGHT_FRAC = 0.42  # a view shorter than this share of the sheet is too small to use
MAX_VIEWS = 6
PAD = 16


def _dilate(m: np.ndarray, r: int) -> np.ndarray:
    h, w = m.shape
    pad = np.pad(m, r, constant_values=False)
    rows = np.zeros_like(m)
    for d in range(-r, r + 1):
        rows |= pad[r + d : r + d + h, r : r + w]
    pad = np.pad(rows, r, constant_values=False)
    out = np.zeros_like(m)
    for d in range(-r, r + 1):
        out |= pad[r : r + h, r + d : r + d + w]
    return out


def split_sheet(sheet: Image.Image) -> list[Image.Image]:
    """One RGB image per creature, others painted out, biggest views first, left to right
    among the kept ones. Views smaller than MIN_HEIGHT_FRAC of the sheet are dropped."""
    rgb = np.asarray(sheet.convert("RGB"))
    h, w, _ = rgb.shape
    solid = remove_background(rgb)[..., 3] > 0
    ch, cw = h // CELL, w // CELL
    cells = solid[: ch * CELL, : cw * CELL].reshape(ch, CELL, cw, CELL).any(axis=(1, 3))
    labels, n = label(_dilate(cells, JOIN_CELLS), eight=True)
    corners = np.concatenate([rgb[:PAD, :PAD].reshape(-1, 3), rgb[-PAD:, -PAD:].reshape(-1, 3)])
    bg = np.median(corners, axis=0).astype(np.uint8)
    found = []
    for k in range(1, n + 1):
        own = (labels == k) & cells  # cells of this creature
        ys, xs = np.nonzero(own)
        if len(ys) == 0:
            continue
        height = (ys.max() - ys.min() + 1) * CELL
        if height < MIN_HEIGHT_FRAC * h:
            continue
        mask = np.kron(_dilate(labels == k, 1), np.ones((CELL, CELL), bool))
        full = np.zeros((h, w), bool)
        full[: ch * CELL, : cw * CELL] = mask
        y0, y1 = max(0, ys.min() * CELL - PAD), min(h, (ys.max() + 1) * CELL + PAD)
        x0, x1 = max(0, xs.min() * CELL - PAD), min(w, (xs.max() + 1) * CELL + PAD)
        crop = np.where(full[y0:y1, x0:x1, None], rgb[y0:y1, x0:x1], bg)
        found.append((int(xs.min()), -height, Image.fromarray(crop.astype(np.uint8), "RGB")))
    found.sort(key=lambda t: t[1])  # tallest first
    found = found[:MAX_VIEWS]
    found.sort(key=lambda t: t[0])  # then left to right
    return [f[2] for f in found]
