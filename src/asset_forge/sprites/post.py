"""Deterministic sprite clean-up on RGBA uint8 arrays (H, W, 4), alpha always 0 or 255."""

from __future__ import annotations

from collections import deque

import numpy as np
from PIL import Image

from .grid import detect_grid, downsample_on_grid
from .presets import EDGE_MARGIN_PX, OUTLINE_COLOUR, OUTLINE_LUMA_MAX, Preset

POCKET_MIN_PX = 24  # an enclosed background-coloured area this big is not part of the sprite
MAX_HOLE_PX = 12  # smaller see-through pockets are filled; bigger ones fail the QA instead
SHADOW_MIN_PX = 20
SHADOW_FLATNESS = 0.35  # a shadow is at most this tall compared to its width
SECOND_BODY_FRAC = 0.25  # a separate piece this big, relative to the biggest, is a second body
N4 = ((1, 0), (-1, 0), (0, 1), (0, -1))
N8 = N4 + ((1, 1), (1, -1), (-1, 1), (-1, -1))


def luma(rgb: np.ndarray) -> np.ndarray:
    rgb = rgb.astype(np.float64)
    return 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]


def label(mask: np.ndarray, eight: bool = False) -> tuple[np.ndarray, int]:
    """Connected components of a boolean mask. Returns (labels starting at 1, count)."""
    h, w = mask.shape
    labels = np.zeros((h, w), dtype=np.int32)
    steps = N8 if eight else N4
    n = 0
    for y0, x0 in zip(*np.nonzero(mask), strict=True):
        if labels[y0, x0]:
            continue
        n += 1
        labels[y0, x0] = n
        q = deque([(y0, x0)])
        while q:
            y, x = q.popleft()
            for dy, dx in steps:
                yy, xx = y + dy, x + dx
                if 0 <= yy < h and 0 <= xx < w and mask[yy, xx] and not labels[yy, xx]:
                    labels[yy, xx] = n
                    q.append((yy, xx))
    return labels, n


def opaque(rgba: np.ndarray) -> np.ndarray:
    return rgba[..., 3] > 0


def bbox(rgba: np.ndarray) -> tuple[int, int, int, int] | None:
    """(x0, y0, x1, y1), end exclusive, of the opaque pixels; None when empty."""
    ys, xs = np.nonzero(opaque(rgba))
    if len(ys) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def _border_labels(labels: np.ndarray) -> set[int]:
    ring = np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]])
    return {int(v) for v in np.unique(ring) if v}


def remove_background(rgb: np.ndarray, tolerance: float = 48.0) -> np.ndarray:
    """Make the border-connected background colour transparent. Returns RGBA."""
    h, w, _ = rgb.shape
    border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
    k = (border >> 3).astype(np.int32)
    keys = (k[:, 0] << 10) | (k[:, 1] << 5) | k[:, 2]
    uniq, counts = np.unique(keys, return_counts=True)
    bg = border[keys == uniq[counts.argmax()]].mean(axis=0)
    close = np.linalg.norm(rgb.astype(np.float64) - bg, axis=2) <= tolerance
    labels, _ = label(close)
    touching = _border_labels(labels)
    is_bg = np.isin(labels, list(touching)) if touching else np.zeros((h, w), bool)
    # Large background-coloured pockets (inside a curled tail, between legs) are background too.
    sizes = np.bincount(labels.ravel())
    for k in np.nonzero(sizes >= POCKET_MIN_PX)[0]:
        if k:
            is_bg |= labels == k
    is_bg |= _ground_shadow(rgb, is_bg)
    out = np.dstack([rgb, np.where(is_bg, 0, 255).astype(np.uint8)])
    out[is_bg, :3] = 0
    return out


def _ground_shadow(rgb: np.ndarray, is_bg: np.ndarray) -> np.ndarray:
    """Flat, wide, grey patches on the background: a drawn ground shadow, not the sprite."""
    f = rgb.astype(np.float64)
    sat = (f.max(axis=2) - f.min(axis=2)) / np.maximum(f.max(axis=2), 1.0)
    grey = (sat < 0.12) & (luma(rgb) > 80) & (luma(rgb) < 235) & ~is_bg
    labels, n = label(grey)
    pad = np.pad(is_bg, 1, constant_values=False)
    near_bg = pad[:-2, 1:-1] | pad[2:, 1:-1] | pad[1:-1, :-2] | pad[1:-1, 2:]
    out = np.zeros_like(is_bg)
    for k in range(1, n + 1):
        region = labels == k
        ys, xs = np.nonzero(region)
        h, w = ys.max() - ys.min() + 1, xs.max() - xs.min() + 1
        if len(ys) >= SHADOW_MIN_PX and h <= SHADOW_FLATNESS * w and (region & near_bg).any():
            out |= region
    return out


def remove_strays(rgba: np.ndarray, max_px: int = 2) -> np.ndarray:
    """Drop opaque pieces of max_px pixels or fewer (8-connected), unless they are all there is."""
    out = rgba.copy()
    labels, n = label(opaque(out), eight=True)
    if n <= 1:
        return out
    sizes = np.bincount(labels.ravel(), minlength=n + 1)
    for k in range(1, n + 1):
        if sizes[k] <= max_px and sizes[k] < sizes[1:].max():
            out[labels == k] = 0
    return out


def keep_main_bodies(rgba: np.ndarray, frac: float = SECOND_BODY_FRAC) -> np.ndarray:
    """Drop separate pieces smaller than `frac` of the biggest (stray bits of a sheet or a tail)."""
    out = rgba.copy()
    labels, n = label(opaque(out), eight=True)
    if n <= 1:
        return out
    sizes = np.bincount(labels.ravel(), minlength=n + 1)
    for k in range(1, n + 1):
        if sizes[k] < frac * sizes[1:].max():
            out[labels == k] = 0
    return out


def fill_holes(rgba: np.ndarray) -> np.ndarray:
    """Fill small pockets enclosed by the sprite with their neighbours' common colour."""
    out = rgba.copy()
    h, w, _ = out.shape
    labels, n = label(~opaque(out), eight=True)
    edge = _border_labels(labels)
    for k in range(1, n + 1):
        if k in edge:
            continue
        region = labels == k
        if region.sum() > MAX_HOLE_PX:
            continue
        ys, xs = np.nonzero(region)
        around = []
        for y, x in zip(ys, xs, strict=True):
            for dy, dx in N4:
                yy, xx = y + dy, x + dx
                if 0 <= yy < h and 0 <= xx < w and out[yy, xx, 3]:
                    around.append(tuple(int(c) for c in out[yy, xx, :3]))
        colour = max(sorted(set(around)), key=around.count) if around else OUTLINE_COLOUR
        out[region] = (*colour, 255)
    return out


def _mode_resample(rgba: np.ndarray, new_w: int, new_h: int) -> np.ndarray:
    """Resize taking each output pixel's dominant source colour (no blending)."""
    h, w, _ = rgba.shape
    out = np.zeros((new_h, new_w, 4), dtype=np.uint8)
    for j in range(new_h):
        y0 = int(j * h / new_h)
        y1 = max(int((j + 1) * h / new_h), y0 + 1)
        for i in range(new_w):
            x0 = int(i * w / new_w)
            x1 = max(int((i + 1) * w / new_w), x0 + 1)
            blk = rgba[y0:y1, x0:x1].reshape(-1, 4)
            solid = blk[blk[:, 3] > 0]
            if len(solid) * 2 < len(blk):
                continue
            colours, counts = np.unique(solid[:, :3], axis=0, return_counts=True)
            out[j, i] = (*colours[counts.argmax()], 255)
    return out


def fit_to_canvas(rgba: np.ndarray, size: int, margin: int = EDGE_MARGIN_PX + 1) -> np.ndarray:
    """Crop to the sprite and scale it to the largest box leaving `margin` (outline included)."""
    box = bbox(rgba)
    if box is None:
        return np.zeros((size, size, 4), dtype=np.uint8)
    x0, y0, x1, y1 = box
    crop = rgba[y0:y1, x0:x1]
    h, w, _ = crop.shape
    s = (size - 2 * margin) / max(h, w)
    nw, nh = max(1, round(w * s)), max(1, round(h * s))
    scaled = _mode_resample(crop, nw, nh) if (nw, nh) != (w, h) else crop.copy()
    canvas = np.zeros((size, size, 4), dtype=np.uint8)
    ox, oy = (size - nw) // 2, (size - nh) // 2
    canvas[oy : oy + nh, ox : ox + nw] = scaled
    return canvas


def reduce_palette(rgba: np.ndarray, colours: int) -> np.ndarray:
    """Median-cut the opaque pixels to at most `colours`: no dithering, alpha untouched."""
    out = rgba.copy()
    mask = opaque(out)
    px = out[mask][:, :3]
    if len(px) == 0 or len(np.unique(px, axis=0)) <= colours:
        return out
    q = Image.fromarray(px.reshape(-1, 1, 3), "RGB").quantize(
        colors=colours, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE
    )
    pal = np.array(q.getpalette()[: 3 * colours], dtype=np.uint8).reshape(-1, 3)
    d = ((px[:, None, :].astype(np.int32) - pal[None, :, :].astype(np.int32)) ** 2).sum(axis=2)
    out[mask, :3] = pal[d.argmin(axis=1)]
    return out


def edge_pixels(rgba: np.ndarray) -> np.ndarray:
    """Opaque pixels with a transparent 4-neighbour (the canvas edge counts as transparent)."""
    solid = opaque(rgba)
    pad = np.pad(solid, 1, constant_values=False)
    clear = ~pad[:-2, 1:-1] | ~pad[2:, 1:-1] | ~pad[1:-1, :-2] | ~pad[1:-1, 2:]
    return solid & clear


def is_outline(rgba: np.ndarray) -> np.ndarray:
    return opaque(rgba) & (luma(rgba[..., :3]) <= OUTLINE_LUMA_MAX)


def add_outline(rgba: np.ndarray) -> np.ndarray:
    """Dark edge pixels become the outline colour; a ring is added where the edge is not dark."""
    out = rgba.copy()
    dark_edge = edge_pixels(out) & is_outline(out)
    out[dark_edge] = (*OUTLINE_COLOUR, 255)
    solid = opaque(out)
    need = solid & ~is_outline(out)
    pad = np.pad(need, 1, constant_values=False)
    touches = pad[:-2, 1:-1] | pad[2:, 1:-1] | pad[1:-1, :-2] | pad[1:-1, 2:]
    out[~solid & touches] = (*OUTLINE_COLOUR, 255)
    return out


def process(raw: Image.Image, preset: Preset) -> tuple[np.ndarray, dict]:
    """Raw generated image -> pixel-perfect RGBA sprite at the preset's art size."""
    rgb = np.asarray(raw.convert("RGB"))
    info = detect_grid(rgb)
    native = downsample_on_grid(rgb, info)
    sprite = keep_main_bodies(remove_strays(remove_background(native)))
    sprite = fit_to_canvas(sprite, preset.art_size)
    sprite = reduce_palette(sprite, preset.max_colours - 1)
    sprite = fill_holes(remove_strays(sprite))
    sprite = add_outline(sprite)
    meta = {
        "grid_pitch": info.pitch,
        "grid_found": info.found,
        "grid_confidence": round(info.confidence, 3),
    }
    return sprite, meta
