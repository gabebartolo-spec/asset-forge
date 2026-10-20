"""Pair gates (round 3): a back with no face, and a back with the front's anatomy.

Both are deterministic and size-relative, return plain-words problems, and a pair that fails
either never exports (pipeline.export_pair re-runs them).
"""

from __future__ import annotations

import numpy as np

from .post import bbox, is_outline, label, opaque
from .presets import BACK_SYMMETRY_MIN

HEAD_FRAC = 0.40  # the head area: the top 40% of the sprite's rows ...
HEAD_SIDE = 0.15  # ... without the outer 15% of the width on each side
FACE_CONTRAST = 55.0  # and differs this much (RGB) from the head's main colour
FEATURE_MAX_FRAC = 0.012  # an eye, beak or mouth patch is at most this share of the canvas
FEATURE_MIN_PX = 2
EYE_MAX_FRAC = 0.004  # an eye is at most this share of the canvas
DARK_LUMA = 70.0
EYE_DY = 0.04  # two eyes sit within this share of the canvas height of each other
EYE_DX = 0.06  # and at least this share of the width apart
FEATURE_CONTRAST = 90.0  # a face patch differs this much (RGB) from the pixels around it
BODY_COLOUR_FRAC = 0.025  # a colour covering this share of the body below the head is not face-only
FACE_MATCH = 30.0  # a back pixel this close to a face colour is that face colour
FACE_BACK_PX_MAX = 3  # a back head with more face-coloured feature pixels than this has a face
FACE_MIN_PX = 2  # a front without 2 px of face colours has no face to compare

LIMB_OPEN_FRAC = 0.075  # opening radius (share of the canvas) that strips limbs from the body
LIMB_MIN_FRAC = 0.002  # a protrusion this share of the canvas counts as a limb/tail/head
COUNT_TOL = 1  # limb blobs and ground contacts may differ by this many
STANCE_RATIO_MAX = 1.4  # height/width of the back vs the front
FOOT_SPAN_RATIO_MAX = 2.0  # width of the foot row, back vs front


def _head_box(rgba: np.ndarray) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = bbox(rgba)
    h, w = y1 - y0, x1 - x0
    return x0 + int(HEAD_SIDE * w), y0, x1 - int(HEAD_SIDE * w), y0 + max(2, int(HEAD_FRAC * h))


def face_features(
    rgba: np.ndarray, dark: bool = False
) -> list[tuple[np.ndarray, int, tuple[float, float]]]:
    """Eye, beak and mouth candidates in the head area: small patches of one colour (outline
    colours and edge pixels excluded) that stand out from everything around them. Returns
    (colour, pixel count, (y, x) centre) per patch. `dark` also admits outline-dark patches
    (a pupil). A cheek or a shaded cheek is too big or too close in colour."""
    solid = opaque(rgba)
    body = solid if dark else solid & ~is_outline(rgba)
    hx0, hy0, hx1, hy1 = _head_box(rgba)
    n = rgba.shape[0]
    pad = np.pad(body, 1, constant_values=False)
    inner = body & pad[:-2, 1:-1] & pad[2:, 1:-1] & pad[1:-1, :-2] & pad[1:-1, 2:]
    out = []
    seen = np.zeros(body.shape, bool)
    for y in range(hy0, hy1):
        for x in range(hx0, hx1):
            if not inner[y, x] or seen[y, x]:
                continue
            colour = rgba[y, x, :3]
            same = (rgba[..., :3] == colour).all(axis=2) & body
            labels, _ = label(same, eight=True)
            patch = labels == labels[y, x]
            seen |= patch
            size = int(patch.sum())
            if not (FEATURE_MIN_PX <= size <= FEATURE_MAX_FRAC * n * n):
                continue
            ring = _dilate(patch, 1) & ~patch & solid & ~is_outline(rgba)
            if not ring.any():
                continue
            ring_mean = rgba[ring][:, :3].astype(float).mean(axis=0)
            if np.linalg.norm(colour.astype(float) - ring_mean) >= FEATURE_CONTRAST:
                ys, xs = np.nonzero(patch)
                out.append((colour.astype(np.uint8), size, (float(ys.mean()), float(xs.mean()))))
    return out


def face_colours(front: np.ndarray) -> np.ndarray:
    """Colours that belong to the front's face only: its eye, beak and mouth patches, minus any
    colour the body below the head also uses (white fur, a belly, feet)."""
    cand = np.array([c for c, _, _ in face_features(front)], np.uint8).reshape(-1, 3)
    if len(cand) == 0:
        return cand
    hx0, hy0, hx1, hy1 = _head_box(front)
    below = opaque(front) & ~is_outline(front)
    below[hy0:hy1, hx0:hx1] = False
    px = front[below][:, :3].astype(float)
    keep = []
    for c in np.unique(cand, axis=0):
        share = (
            (np.linalg.norm(px - c.astype(float), axis=1) <= FACE_MATCH).mean() if len(px) else 0
        )
        if share < BODY_COLOUR_FRAC:
            keep.append(c)
    return np.array(keep, np.uint8).reshape(-1, 3)


def back_face_pixels(back: np.ndarray, colours: np.ndarray) -> int:
    """Pixels in the back's head area (no outline) with one of the front's face colours."""
    if len(colours) == 0 or bbox(back) is None:
        return 0
    hx0, hy0, hx1, hy1 = _head_box(back)
    region = back[hy0:hy1, hx0:hx1]
    solid = (region[..., 3] > 0) & ~is_outline(region)
    px = region[..., :3].astype(float)
    hit = np.zeros(solid.shape, bool)
    for c in colours:
        hit |= np.linalg.norm(px - c.astype(float), axis=2) <= FACE_MATCH
    return int((hit & solid).sum())


def luma_of(c: np.ndarray) -> float:
    return float(0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2])


def eye_pairs(rgba: np.ndarray) -> list[np.ndarray]:
    """Colours of every pair of same-coloured eye-sized patches at about the same height, set
    apart, in the head area: both eyes show."""
    n = rgba.shape[0]
    feats = [f for f in face_features(rgba, dark=True) if f[1] <= EYE_MAX_FRAC * n * n]
    out = []
    for i, (c1, _, (y1, x1)) in enumerate(feats):
        for c2, _, (y2, x2) in feats[i + 1 :]:
            same = np.linalg.norm(c1.astype(float) - c2.astype(float)) <= FACE_MATCH
            if same and abs(y1 - y2) <= EYE_DY * n and abs(x1 - x2) >= EYE_DX * n:
                out.append(c1)
    return out


def has_eye_pair(rgba: np.ndarray, colours: list[np.ndarray] | None = None) -> bool:
    """Both eyes show; with `colours`, only eyes of one of those colours count."""
    found = eye_pairs(rgba)
    if colours is None:
        return bool(found)
    # a dark pair (pupils) is also what ear insides and stripes look like from behind: only a
    # coloured eye (teal, green, yellow) proves the back shows a face
    lit = [c for c in found if luma_of(c) > DARK_LUMA]
    return any(
        np.linalg.norm(c.astype(float) - e.astype(float)) <= FACE_MATCH
        for c in lit
        for e in colours
    )


def check_back_faces_away(back: np.ndarray) -> tuple[list[str], dict]:
    """A view from behind is roughly left-right balanced; a profile or a turned head is not."""
    x0, y0, x1, y1 = bbox(back)
    m = opaque(back)[y0:y1, x0:x1]
    union = (m | m[:, ::-1]).sum()
    sym = float((m & m[:, ::-1]).sum() / union) if union else 0.0
    if sym < BACK_SYMMETRY_MIN:
        return [
            f"The back is a side view ({sym:.0%} left-right balance, needs "
            f"{BACK_SYMMETRY_MIN:.0%}); it must be seen from directly behind."
        ], {"back_symmetry": sym}
    return [], {"back_symmetry": sym}


def check_back_has_no_face(front: np.ndarray, back: np.ndarray) -> tuple[list[str], dict]:
    colours = face_colours(front)
    n_face = back_face_pixels(front, colours)
    seen = back_face_pixels(back, colours)
    metrics = {"face_colours": len(colours), "front_face_px": n_face, "back_face_px": seen}
    if n_face < FACE_MIN_PX:
        return [
            "The front shows no face (no eye, beak or mouth colour found in its head), so the "
            "pair cannot be checked."
        ], metrics
    if not has_eye_pair(front):
        return ["The front does not show both eyes, so it is not facing the viewer."], metrics | {
            "front_eyes": 0
        }
    if has_eye_pair(back, eye_pairs(front)):
        return [
            "The back shows both eyes: it is a view from the front, not from behind."
        ], metrics | {"back_eyes": 2}
    if seen > FACE_BACK_PX_MAX:
        return [
            f"The back still shows a face: {seen} pixels in its head area use the colours of the "
            f"front's face ({n_face} px there). A back must be seen from behind."
        ], metrics
    return [], metrics


def _erode(m: np.ndarray, r: int) -> np.ndarray:
    h, w = m.shape
    pad = np.pad(m, r, constant_values=False)
    rows = np.ones_like(m)
    for d in range(-r, r + 1):
        rows &= pad[r + d : r + d + h, r : r + w]
    pad = np.pad(rows, r, constant_values=False)
    out = np.ones_like(m)
    for d in range(-r, r + 1):
        out &= pad[r : r + h, r + d : r + d + w]
    return out


def _dilate(m: np.ndarray, r: int) -> np.ndarray:
    return ~_erode(~m, r)


def anatomy(rgba: np.ndarray) -> dict[str, float]:
    """Silhouette anatomy: limb/tail/head blobs, ground contacts, stance, head and foot widths."""
    sil = opaque(rgba)
    n = sil.shape[0]
    x0, y0, x1, y1 = bbox(rgba)
    w, h = x1 - x0, y1 - y0
    r = max(1, round(LIMB_OPEN_FRAC * n))
    core = _dilate(_erode(sil, r), r)
    rest = sil & ~_dilate(core, 1)
    labels, k = label(rest, eight=True)
    sizes = np.bincount(labels.ravel(), minlength=k + 1)[1:] if k else np.zeros(0, int)
    blobs = int((sizes >= LIMB_MIN_FRAC * n * n).sum())
    foot_row = sil[max(y0, y1 - 3)]
    runs = int(((foot_row[1:] & ~foot_row[:-1]).sum()) + foot_row[0])
    xs = np.nonzero(foot_row)[0]
    top = sil[y0 : y0 + max(2, h // 5)]
    top_w = float(np.ptp(np.nonzero(top.any(axis=0))[0]) + 1) if top.any() else 1.0
    return {
        "limb_blobs": blobs,
        "ground_contacts": runs,
        "stance": h / w,
        "head_width": top_w / w,
        "foot_span": float((xs.max() - xs.min() + 1) / w) if len(xs) else 0.0,
    }


def check_anatomy_match(front: np.ndarray, back: np.ndarray) -> tuple[list[str], dict]:
    a, b = anatomy(front), anatomy(back)
    metrics = {f"front_{k}": round(v, 3) for k, v in a.items()}
    metrics |= {f"back_{k}": round(v, 3) for k, v in b.items()}
    problems = []
    if abs(a["limb_blobs"] - b["limb_blobs"]) > COUNT_TOL:
        problems.append(
            f"Limbs, tail and head differ: the front has {int(a['limb_blobs'])} separate "
            f"protrusions, the back {int(b['limb_blobs'])} (allowed difference {COUNT_TOL})."
        )
    if abs(a["ground_contacts"] - b["ground_contacts"]) > COUNT_TOL:
        problems.append(
            f"The creature stands on {int(a['ground_contacts'])} points in the front and "
            f"{int(b['ground_contacts'])} in the back."
        )
    ratio = max(a["stance"] / b["stance"], b["stance"] / a["stance"])
    if ratio > STANCE_RATIO_MAX:
        problems.append(
            f"The stance differs: height/width is {a['stance']:.2f} in the front and "
            f"{b['stance']:.2f} in the back (allowed x{STANCE_RATIO_MAX})."
        )
    if a["foot_span"] and b["foot_span"]:
        fs = max(a["foot_span"] / b["foot_span"], b["foot_span"] / a["foot_span"])
        if fs > FOOT_SPAN_RATIO_MAX:
            problems.append("The feet are a different width apart in the front and the back.")
    return problems, metrics
