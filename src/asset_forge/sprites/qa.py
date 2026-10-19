"""Sprite QA (design 5.3): plain-words problems. An empty list means the sprite may be exported."""

from __future__ import annotations

import numpy as np

from .post import SECOND_BODY_FRAC, bbox, edge_pixels, is_outline, label, opaque
from .presets import (
    ASPECT_RATIO_MAX,
    BACK_IOU_MAX,
    COLOUR_DISTANCE_MAX,
    EDGE_MARGIN_PX,
    FRONT_SYMMETRY_MIN,
    GAP_OK_PX,
    MASS_RATIO_MAX,
    Preset,
)


def check_sprite(rgba: np.ndarray, preset: Preset) -> list[str]:
    problems: list[str] = []
    n = preset.art_size
    if rgba.shape != (n, n, 4):
        return [f"The sprite is {rgba.shape[1]}x{rgba.shape[0]}, the preset needs {n}x{n}."]
    alpha = rgba[..., 3]
    solid = opaque(rgba)
    if not solid.any():
        return ["The sprite is empty."]

    soft = int(((alpha > 0) & (alpha < 255)).sum())
    if soft:
        problems.append(f"{soft} semi-transparent pixels (soft edges); pixel art needs hard edges.")
    if solid.mean() > 0.85:
        problems.append("The background was not removed (almost the whole canvas is filled).")

    x0, y0, x1, y1 = bbox(rgba)
    m = EDGE_MARGIN_PX
    if x0 < m or y0 < m or x1 > n - m or y1 > n - m:
        problems.append(f"The sprite is closer than {m} px to the canvas edge.")
    if max(x1 - x0, y1 - y0) < 0.5 * n:
        problems.append("The sprite is too small; it fills less than half of the canvas.")

    unoutlined = int((edge_pixels(rgba) & ~is_outline(rgba)).sum())
    if unoutlined:
        problems.append(f"{unoutlined} edge pixels have no dark outline.")

    labels, count = label(solid, eight=True)
    if count > 1:
        sizes = np.bincount(labels.ravel(), minlength=count + 1)[1:]
        strays = int(((sizes <= 2) & (sizes < sizes.max())).sum())
        big = np.sort(sizes[sizes > 2])
        if len(big) > 1 and big[-2] >= SECOND_BODY_FRAC * big[-1]:
            problems.append("The sprite has more than one separate body (a second creature).")
        if strays:
            problems.append(f"{strays} stray pixels (pieces of 1-2 pixels) float off the body.")

    clear_labels, clear_count = label(~solid)  # 4-connected, as the hole fill
    ring = np.concatenate(
        [clear_labels[0], clear_labels[-1], clear_labels[:, 0], clear_labels[:, -1]]
    )
    outside = {int(v) for v in np.unique(ring) if v}
    sizes = np.bincount(clear_labels.ravel(), minlength=clear_count + 1)
    # a big enclosed gap is a drawn one (a tail loop, between the legs), ringed by the outline;
    # a small one the hole fill could not close is a defect
    holes = sum(1 for k in range(1, clear_count + 1) if k not in outside and sizes[k] < GAP_OK_PX)
    if holes:
        problems.append(f"{holes} holes: see-through gaps fully enclosed by the sprite.")

    colours = len(np.unique(rgba[solid][:, :3], axis=0))
    if colours > preset.max_colours:
        problems.append(f"{colours} colours; the {preset.label} limit is {preset.max_colours}.")
    return problems


def _iou(a: np.ndarray, b: np.ndarray) -> float:
    union = (a | b).sum()
    return float((a & b).sum() / union) if union else 0.0


def back_overlap(front: np.ndarray, back: np.ndarray) -> dict[str, float]:
    """Silhouette overlap (intersection over union) of the back with the front and its mirror."""
    f, b = opaque(front), opaque(back)
    return {"iou_front": _iou(f, b), "iou_mirror": _iou(f[:, ::-1], b)}


def check_back_view(front: np.ndarray, back: np.ndarray) -> tuple[list[str], dict[str, float]]:
    """A real back view has a different outline than the front or its mirror."""
    metrics = back_overlap(front, back)
    worst = max(metrics.values())
    problems = []
    if worst > BACK_IOU_MAX:
        problems.append(
            f"The back view has the same outline as the front ({worst:.0%} overlap, limit "
            f"{BACK_IOU_MAX:.0%}); it looks like the front, not a view from behind."
        )
    return problems, metrics


def _colour_hist(rgba: np.ndarray) -> np.ndarray:
    """Share of body pixels (outline excluded) per coarse RGB cell."""
    body = opaque(rgba) & ~is_outline(rgba)
    px = (rgba[body][:, :3] >> 5).astype(np.int32)
    hist = np.bincount((px[:, 0] << 6) | (px[:, 1] << 3) | px[:, 2], minlength=512).astype(float)
    return hist / max(hist.sum(), 1.0)


def same_creature_metrics(front: np.ndarray, back: np.ndarray) -> dict[str, float]:
    fx0, fy0, fx1, fy1 = bbox(front)
    bx0, by0, bx1, by1 = bbox(back)
    f_aspect, b_aspect = (fx1 - fx0) / (fy1 - fy0), (bx1 - bx0) / (by1 - by0)
    return {
        "colour_distance": float(1.0 - np.minimum(_colour_hist(front), _colour_hist(back)).sum()),
        "aspect_ratio": float(b_aspect / f_aspect),
        "mass_ratio": float(opaque(back).sum() / opaque(front).sum()),
    }


def check_same_creature(front: np.ndarray, back: np.ndarray) -> tuple[list[str], dict[str, float]]:
    """The back must be the front's creature: similar colours, proportions and size."""
    if not opaque(front).any() or not opaque(back).any():
        return ["A view is empty."], {}
    m = same_creature_metrics(front, back)
    problems = []
    if m["colour_distance"] > COLOUR_DISTANCE_MAX:
        problems.append(
            f"The back's colours differ from the front's ({m['colour_distance']:.0%} apart, limit "
            f"{COLOUR_DISTANCE_MAX:.0%}); it is not the same creature."
        )
    a, k, r = m["aspect_ratio"], ASPECT_RATIO_MAX, m["mass_ratio"]
    if not (1 / k <= a <= k) or not (1 / MASS_RATIO_MAX <= r <= MASS_RATIO_MAX):
        problems.append(
            f"The back's shape does not match the front's (width/height ratio x{a:.2f}, size "
            f"x{r:.2f}; allowed x{1 / k:.2f}-{k:.2f} and x{1 / MASS_RATIO_MAX:.2f}-"
            f"{MASS_RATIO_MAX:.2f})."
        )
    return problems, m


def check_front_faces_viewer(front: np.ndarray) -> tuple[list[str], dict[str, float]]:
    """A three-quarter battle front is roughly left-right balanced; a profile is not."""
    x0, y0, x1, y1 = bbox(front)
    m = opaque(front)[y0:y1, x0:x1]
    sym = _iou(m, m[:, ::-1])
    if sym < FRONT_SYMMETRY_MIN:
        return [
            f"The front is a side view ({sym:.0%} left-right balance, needs "
            f"{FRONT_SYMMETRY_MIN:.0%}); it must face the viewer."
        ], {"front_symmetry": sym}
    return [], {"front_symmetry": sym}
