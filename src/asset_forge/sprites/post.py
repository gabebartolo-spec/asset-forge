"""Deterministic sprite clean-up on RGBA uint8 arrays (H, W, 4), alpha always 0 or 255."""

from __future__ import annotations

from collections import deque

import numpy as np
from PIL import Image

from .grid import detect_grid, downsample_on_grid
from .presets import EDGE_MARGIN_PX, LEG_GAP_ZONE, OUTLINE_COLOUR, OUTLINE_LUMA_MAX, Preset

POCKET_MIN_PX = 24  # an enclosed background-coloured area this big is not part of the sprite
MAX_HOLE_PX = 12  # smaller see-through pockets are filled; bigger ones fail the QA instead
MAX_HOLE_PX_BODY = 24  # above the legs a pocket this small (arm against the body) is filled too
SHADOW_MIN_PX = 20
SHADOW_SAT = 0.12  # a shadow is nearly colourless
SHADOW_MATCH = 16.0  # RGB distance to a proven shadow colour that counts as the same shadow
SHADOW_LOW = 0.65  # a contact shadow's centre sits in the bottom third of the sprite
SHADOW_CONTACT_FRAC = 0.25  # and is at most this share of the sprite
SHADOW_MAX_FRAC = 0.08  # a same-grey piece bigger than this share of the sprite is not shadow
SHADOW_FLATNESS = 0.35  # a shadow is at most this tall compared to its width
ACCENT_SLOTS = 3  # palette slots reserved for small saturated colours (eyes, flames)
ACCENT_MIN_SAT = 0.35
ACCENT_MIN_ERR = 45.0  # RGB distance from the base palette that makes a colour an outlier
ACCENT_MIN_PX = 2
ACCENT_LONE_PX = 4  # an accent colour with this few pixels is never speckle-cleaned
FRINGE_ZONE = 0.14  # the bottom share of the sprite where shadow scraps hang
FRINGE_SAT = 0.30
FRINGE_LAYERS = 2
FRINGE_EDGE_SHARE = 0.6  # a bottom edge this dull is a grey creature, not a shadow
SPECKLE_TARGET = 0.02  # clean until this share of pixels is isolated (the skill limit is 3%)
SPECKLE_PASSES = 6
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
    is_bg |= _ground_fringe(rgb, is_bg)
    out = np.dstack([rgb, np.where(is_bg, 0, 255).astype(np.uint8)])
    out[is_bg, :3] = 0
    return out


def _saturation(rgb: np.ndarray) -> np.ndarray:
    f = rgb.astype(np.float64)
    return (f.max(axis=2) - f.min(axis=2)) / np.maximum(f.max(axis=2), 1.0)


def _ground_shadow(rgb: np.ndarray, is_bg: np.ndarray) -> np.ndarray:
    """The generator's drawn ground shadow: flat grey beside the background, and the same grey
    anywhere else it was left (enclosed under a belly or along a tail). Never a grey creature:
    nothing is removed unless a flat grey patch touching the background proves a shadow exists."""
    grey = (_saturation(rgb) < SHADOW_SAT) & (luma(rgb) > 80) & (luma(rgb) < 235) & ~is_bg
    labels, n = label(grey)
    pad = np.pad(is_bg, 1, constant_values=False)
    near_bg = pad[:-2, 1:-1] | pad[2:, 1:-1] | pad[1:-1, :-2] | pad[1:-1, 2:]
    out = np.zeros_like(is_bg)
    seeds = []
    rows = np.nonzero((~is_bg).any(axis=1))[0]
    top, bottom = (int(rows.min()), int(rows.max())) if len(rows) else (0, 0)
    area = max(int((~is_bg).sum()), 1)
    for k in range(1, n + 1):
        region = labels == k
        ys, xs = np.nonzero(region)
        h, w = ys.max() - ys.min() + 1, xs.max() - xs.min() + 1
        flat = h <= SHADOW_FLATNESS * w
        # or a patch that sits in the bottom contact area, wrapped round the feet
        contact = ys.mean() >= top + SHADOW_LOW * (bottom - top) and ys.max() >= bottom - 16
        small = len(ys) <= SHADOW_CONTACT_FRAC * area
        if len(ys) >= SHADOW_MIN_PX and (flat or (contact and small)) and (region & near_bg).any():
            out |= region
            seeds.append(rgb[region].mean(axis=0))
    if not seeds:
        return out
    f = rgb.astype(np.float64)
    like = np.zeros_like(is_bg)
    for c in seeds:
        like |= np.linalg.norm(f - c, axis=2) <= SHADOW_MATCH
    like &= grey
    labels, n = label(like, eight=True)
    for k in range(1, n + 1):
        region = labels == k
        if region.sum() <= SHADOW_MAX_FRAC * area:
            out |= region
    return out


def _ground_fringe(rgb: np.ndarray, is_bg: np.ndarray) -> np.ndarray:
    """Shadow scraps left ragged round and between the feet: dull grey-ish pixels on the edge of
    the bottom rows, peeled two layers deep. Skipped when the whole bottom edge is dull (a grey
    creature, grey feet): then the dull colour is the creature."""
    removed = np.zeros_like(is_bg)
    rows = np.nonzero((~is_bg).any(axis=1))[0]
    if len(rows) == 0:
        return removed
    top, bottom = int(rows.min()), int(rows.max())
    zone = np.zeros_like(is_bg)
    zone[bottom - int(FRINGE_ZONE * (bottom - top)) : bottom + 1] = True
    dull = (_saturation(rgb) < FRINGE_SAT) & (luma(rgb) > 70) & zone
    gone = is_bg.copy()
    for layer in range(FRINGE_LAYERS):
        pad = np.pad(gone, 1, constant_values=False)
        edge = ~gone & (pad[:-2, 1:-1] | pad[2:, 1:-1] | pad[1:-1, :-2] | pad[1:-1, 2:]) & zone
        if layer == 0 and (edge & dull).sum() > FRINGE_EDGE_SHARE * max(int(edge.sum()), 1):
            return removed
        peel = edge & dull
        if not peel.any():
            break
        gone |= peel
        removed |= peel
    return removed


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
    """Fill small pockets enclosed by the sprite (4-connectivity) with their neighbours' colour."""
    out = rgba.copy()
    h, w, _ = out.shape
    labels, n = label(~opaque(out))  # 4-connected: a corner-only gap to the outside is a hole
    edge = _border_labels(labels)
    box = bbox(out)
    for k in range(1, n + 1):
        if k in edge:
            continue
        region = labels == k
        ys, xs = np.nonzero(region)
        legs = box is not None and ys.mean() >= box[1] + (1 - LEG_GAP_ZONE) * (box[3] - box[1])
        if region.sum() > (MAX_HOLE_PX if legs else MAX_HOLE_PX_BODY):
            continue
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


def _accent_colours(px: np.ndarray, pal: np.ndarray, slots: int) -> list[np.ndarray]:
    """Small, saturated colour clusters the base palette misses, best by area x saturation."""
    if slots <= 0:
        return []
    d = np.sqrt(((px[:, None, :].astype(np.int32) - pal[None].astype(np.int32)) ** 2).sum(axis=2))
    err = d.min(axis=1)
    sat = _saturation(px.reshape(-1, 1, 3)).ravel()
    cand = np.nonzero((sat >= ACCENT_MIN_SAT) & (err >= ACCENT_MIN_ERR))[0]
    if len(cand) == 0:
        return []
    keys = (px[cand] >> 5).astype(np.int32)
    keys = (keys[:, 0] << 6) | (keys[:, 1] << 3) | keys[:, 2]
    bins = []
    for key in np.unique(keys):
        members = cand[keys == key]
        if len(members) >= ACCENT_MIN_PX:
            score = len(members) * float(sat[members].mean()) * float(err[members].mean())
            bins.append((score, px[members].mean(axis=0)))
    chosen: list[np.ndarray] = []
    for _, colour in sorted(bins, key=lambda t: -t[0]):
        others = [*chosen, *pal]
        if all(np.linalg.norm(colour - o) > ACCENT_MIN_ERR for o in others):
            chosen.append(colour)
        if len(chosen) == slots:
            break
    return chosen


def shared_palette(sprites: list[np.ndarray], colours: int) -> tuple[np.ndarray, np.ndarray]:
    """One palette for all sprites: median cut plus reserved slots for small saturated accents.

    Returns (palette, accent colours)."""
    px = np.concatenate([s[opaque(s)][:, :3] for s in sprites])
    if len(px) == 0:
        return np.zeros((0, 3), np.uint8), np.zeros((0, 3), np.uint8)
    uniq = np.unique(px, axis=0)
    if len(uniq) <= colours:
        return uniq, np.zeros((0, 3), np.uint8)
    reserve = min(ACCENT_SLOTS, colours // 5)
    q = Image.fromarray(px.reshape(-1, 1, 3), "RGB").quantize(
        colors=colours - reserve, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE
    )
    pal = np.array(q.getpalette()[: 3 * (colours - reserve)], dtype=np.uint8).reshape(-1, 3)
    acc = _accent_colours(px, pal, reserve)
    acc_a = np.array([np.round(c) for c in acc], dtype=np.uint8).reshape(-1, 3)
    return np.concatenate([pal, acc_a]), acc_a


def apply_palette(rgba: np.ndarray, pal: np.ndarray) -> np.ndarray:
    out = rgba.copy()
    mask = opaque(out)
    px = out[mask][:, :3]
    if len(px) and len(pal):
        d = ((px[:, None, :].astype(np.int32) - pal[None].astype(np.int32)) ** 2).sum(axis=2)
        out[mask, :3] = pal[d.argmin(axis=1)]
    return out


def reduce_palette_shared(sprites: list[np.ndarray], colours: int) -> list[np.ndarray]:
    """Reduce several sprites (a front and back pair) to one shared palette of `colours`."""
    pal, _ = shared_palette(sprites, colours)
    return [apply_palette(s, pal) for s in sprites]


def reduce_palette(rgba: np.ndarray, colours: int) -> np.ndarray:
    """Median-cut the opaque pixels to at most `colours`, keeping small saturated accents."""
    return reduce_palette_shared([rgba], colours)[0]


def _same_neighbour(rgba: np.ndarray) -> np.ndarray:
    """Opaque pixels with an opaque 4-neighbour of exactly the same colour."""
    solid = opaque(rgba)
    rgb = rgba[..., :3]
    same = np.zeros(solid.shape, bool)
    h, w = solid.shape
    for dy, dx in N4:
        ok = np.zeros((h, w), bool)
        ys = slice(max(dy, 0), h + min(dy, 0))
        yt = slice(max(-dy, 0), h + min(-dy, 0))
        xs = slice(max(dx, 0), w + min(dx, 0))
        xt = slice(max(-dx, 0), w + min(-dx, 0))
        ok[yt, xt] = solid[ys, xs] & (rgb[ys, xs] == rgb[yt, xt]).all(axis=2)
        same |= ok
    return same & solid


def _isolated(rgba: np.ndarray) -> np.ndarray:
    return opaque(rgba) & ~_same_neighbour(rgba)


def isolated_share(rgba: np.ndarray) -> float:
    """Share of opaque pixels with no 4-neighbour of the same colour (slop_scan's measure)."""
    solid = opaque(rgba)
    return float(_isolated(rgba).sum() / solid.sum()) if solid.any() else 0.0


def clean_speckle(
    rgba: np.ndarray, protect: np.ndarray | None = None, target: float = SPECKLE_TARGET
) -> np.ndarray:
    """Interior pixels with no same-coloured 4-neighbour take their neighbours' majority colour.

    The outline, the edge and protected accent colours are never touched; alpha never changes."""
    out = rgba.copy()
    line = (out[..., :3] == OUTLINE_COLOUR).all(axis=2)  # only the drawn outline, not dark shades
    keep = edge_pixels(out) | line
    if protect is not None:
        for c in protect:
            of_colour = (out[..., :3] == c).all(axis=2) & opaque(out)
            if of_colour.sum() <= ACCENT_LONE_PX:  # a lone eye or highlight is kept as drawn;
                keep |= of_colour  # a bigger spread of the colour is texture, and gets cleaned
    dark = line
    h, w, _ = out.shape
    for _ in range(SPECKLE_PASSES):
        iso = _isolated(out) & ~keep
        if not iso.any() or isolated_share(out) < target:
            break
        changed = False
        for y, x in zip(*np.nonzero(iso), strict=True):
            me = tuple(int(v) for v in out[y, x, :3])
            votes: dict[tuple, int] = {}
            near: list[tuple] = []
            for dy, dx in N8:
                yy, xx = y + dy, x + dx
                if 0 <= yy < h and 0 <= xx < w and out[yy, xx, 3] and not dark[yy, xx]:
                    c = tuple(int(v) for v in out[yy, xx, :3])
                    votes[c] = votes.get(c, 0) + 1
                    if (dy, dx) in N4:
                        near.append(c)
            if me in near or not near:
                continue  # it has a twin by now (an earlier fix next to it), or nothing to join
            # join a 4-neighbour: the commonest colour around, then the closest to its own
            best = min(
                set(near),
                key=lambda c: (-votes[c], sum((a - b) ** 2 for a, b in zip(c, me, strict=True))),
            )
            out[y, x, :3] = best
            changed = True
        if not changed:
            break
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


def prepare(raw: Image.Image, preset: Preset) -> tuple[np.ndarray, dict]:
    """Raw generated image -> cut-out sprite on the art canvas, before palette and outline."""
    rgb = np.asarray(raw.convert("RGB"))
    info = detect_grid(rgb)
    native = downsample_on_grid(rgb, info)
    sprite = keep_main_bodies(remove_strays(remove_background(native)))
    sprite = fit_to_canvas(sprite, preset.art_size)
    meta = {
        "grid_pitch": info.pitch,
        "grid_found": info.found,
        "grid_confidence": round(info.confidence, 3),
    }
    return sprite, meta


def finish(prepared: list[np.ndarray], preset: Preset) -> list[np.ndarray]:
    """Shared palette, clean-up, outline and speckle pass for one sprite or a front/back pair."""
    pal, accents = shared_palette(prepared, preset.max_colours - 1)
    out = []
    for sprite in prepared:
        s = fill_holes(remove_strays(apply_palette(sprite, pal)))
        s = fill_holes(add_outline(s))  # the outline ring can close a notch into a hole
        out.append(clean_speckle(s, accents))
    return out


def process(raw: Image.Image, preset: Preset) -> tuple[np.ndarray, dict]:
    """Raw generated image -> pixel-perfect RGBA sprite at the preset's art size."""
    sprite, meta = prepare(raw, preset)
    return finish([sprite], preset)[0], meta
