"""Small synthetic fixtures for the sprite tests (no GPU, no model files)."""

from __future__ import annotations

import numpy as np
from PIL import Image

from asset_forge.sprites.post import (
    add_outline,
    fill_holes,
    fit_to_canvas,
    reduce_palette,
    remove_background,
)
from asset_forge.sprites.presets import Preset

BODY = (200, 90, 40)
BELLY = (240, 180, 90)
SPOT = (160, 50, 30)


def _ellipse(h, w, cy, cx, ry, rx):
    yy, xx = np.mgrid[0:h, 0:w]
    return ((yy - cy) / ry) ** 2 + ((xx - cx) / rx) ** 2 <= 1.0


def native_creature(view: str = "front", n: int = 128) -> np.ndarray:
    """RGB pixel art, one array pixel per art pixel, on a white background."""
    img = np.full((n, n, 3), 255, dtype=np.uint8)
    if view == "front":  # facing the viewer: round head over a wide body, four legs
        img[_ellipse(n, n, 74, 64, 22, 28)] = BODY
        img[_ellipse(n, n, 80, 64, 12, 18)] = BELLY
        img[_ellipse(n, n, 46, 64, 15, 17)] = BODY
        for x in (40, 50, 72, 82):
            img[92:108, x : x + 7] = BODY
        img[42:46, 56:60] = SPOT
        img[42:46, 68:72] = SPOT
    elif view == "side":  # a profile: wide body, head to the right, four legs
        img[_ellipse(n, n, 70, 60, 22, 36)] = BODY
        img[_ellipse(n, n, 76, 60, 10, 24)] = BELLY
        img[_ellipse(n, n, 52, 100, 14, 14)] = BODY
        for x in (36, 48, 72, 84):
            img[88:108, x : x + 7] = BODY
        img[48:52, 104:108] = SPOT
    else:  # rounder shape seen from behind: two ears, a spot down the back, a tail below
        img[_ellipse(n, n, 64, 64, 28, 34)] = BODY
        img[_ellipse(n, n, 68, 64, 18, 10)] = SPOT
        img[_ellipse(n, n, 76, 64, 8, 20)] = BELLY
        img[24:42, 44:52] = BODY
        img[24:42, 76:84] = BODY
        img[88:102, 62:68] = BELLY
    return img


def raw_generated(
    view: str = "front", pitch: int = 8, noise: int = 0, seed: int = 7
) -> Image.Image:
    """What a generator hands us: the pixel art upscaled by `pitch`, optionally noisy."""
    native = native_creature(view)
    big = np.repeat(np.repeat(native, pitch, axis=0), pitch, axis=1).astype(np.int16)
    if noise:
        rng = np.random.default_rng(seed)
        big = big + rng.integers(-noise, noise + 1, big.shape)
    return Image.fromarray(np.clip(big, 0, 255).astype(np.uint8), "RGB")


def good_sprite(preset: Preset, view: str = "front") -> np.ndarray:
    """A sprite that passes every QA check, built through the real clean-up steps."""
    rgba = remove_background(native_creature(view))
    sprite = fit_to_canvas(rgba, preset.art_size)
    sprite = reduce_palette(sprite, preset.max_colours - 1)
    return fill_holes(add_outline(fill_holes(sprite)))


class FakeDrawer:
    """Returns fixture images instead of running SDXL. `back_like_front` fakes a lazy model."""

    def __init__(self, back_like_front: bool = False, noise: int = 0):
        self.calls: list[tuple[str, int]] = []
        self.inits: list[object] = []  # init image of each draw (None = from text)
        self.batches: list[int] = []
        self.back_like_front, self.noise = back_like_front, noise

    def draw_batch(self, subject, view, seeds, init=None) -> list[Image.Image]:
        self.batches.append(len(seeds))
        return [self.draw(subject, view, s, init) for s in seeds]

    def draw(self, subject: str, view: str, seed: int, init=None) -> Image.Image:
        self.calls.append((view, seed))
        self.inits.append(init)
        shown = "front" if (view == "front" or self.back_like_front) else "back"
        return raw_generated(shown, noise=self.noise)
