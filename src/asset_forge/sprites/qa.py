"""Sprite QA (design 5.3): plain-words problems. An empty list means the sprite may be exported."""

from __future__ import annotations

import numpy as np

from .post import SECOND_BODY_FRAC, bbox, edge_pixels, is_outline, label, opaque
from .presets import BACK_IOU_MAX, EDGE_MARGIN_PX, Preset


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

    clear_labels, clear_count = label(~solid, eight=True)
    ring = np.concatenate(
        [clear_labels[0], clear_labels[-1], clear_labels[:, 0], clear_labels[:, -1]]
    )
    holes = clear_count - len({int(v) for v in np.unique(ring) if v})
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
