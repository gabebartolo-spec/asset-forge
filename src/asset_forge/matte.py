"""Make the reference image ready for the generators, which want a cut-out (RGBA) picture.

A picture that already has transparency is used as it is. A picture with a plain background
(the design's "clean reference, plain background") gets that background cut out: it is found from
the border, then flooded inward. Photos with busy backgrounds need a real matting model (BiRefNet,
later); this is the simple path for the plain-background case.
"""

from __future__ import annotations

from collections import deque
from io import BytesIO

import numpy as np
from PIL import Image

MAX_SIDE = 1024
TOLERANCE = 28.0


def has_cutout(img: Image.Image) -> bool:
    if img.mode != "RGBA":
        return False
    alpha = np.asarray(img.getchannel("A"))
    return bool((alpha < 250).mean() > 0.02)


def cut_out_plain_background(img: Image.Image, tol: float = TOLERANCE) -> Image.Image:
    rgb = np.asarray(img.convert("RGB"), dtype=np.float32)
    h, w, _ = rgb.shape
    border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
    bg = np.median(border, axis=0)
    near = np.linalg.norm(rgb - bg, axis=2) <= tol
    outside = np.zeros((h, w), dtype=bool)
    q: deque[tuple[int, int]] = deque()
    for x in range(w):
        for y in (0, h - 1):
            if near[y, x] and not outside[y, x]:
                outside[y, x] = True
                q.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if near[y, x] and not outside[y, x]:
                outside[y, x] = True
                q.append((y, x))
    while q:
        y, x = q.popleft()
        for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if 0 <= ny < h and 0 <= nx < w and near[ny, nx] and not outside[ny, nx]:
                outside[ny, nx] = True
                q.append((ny, nx))
    out = np.dstack([rgb.astype(np.uint8), np.where(outside, 0, 255).astype(np.uint8)])
    return Image.fromarray(out, "RGBA")


def prepare_reference(data: bytes) -> Image.Image:
    """Bytes of any common image file -> RGBA cut-out, longest side at most 1024 px.
    Raises ValueError (plain words) when the file is not a picture or nothing is left."""
    try:
        img = Image.open(BytesIO(data))
        img.load()
    except Exception as e:  # noqa: BLE001 - any decode failure means "not a picture"
        raise ValueError("That file is not a picture. Choose a PNG or JPG image.") from e
    img = img.convert("RGBA")
    if max(img.size) > MAX_SIDE:
        scale = MAX_SIDE / max(img.size)
        img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    if not has_cutout(img):
        img = cut_out_plain_background(img)
    if (np.asarray(img.getchannel("A")) > 0).sum() < 100:
        raise ValueError(
            "I could not find the character in that picture. Use a picture of one character "
            "on a plain background."
        )
    return img
