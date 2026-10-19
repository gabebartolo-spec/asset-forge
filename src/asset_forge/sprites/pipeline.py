"""Mode A end to end: draw -> post-process -> QA (retry on a new seed) -> export."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

from .draw import Drawer
from .post import process
from .presets import Preset, get_preset
from .qa import check_back_view, check_sprite

MAX_ATTEMPTS = 4


class SpriteFailed(Exception):
    """No attempt passed the sprite QA, so nothing is exported."""

    def __init__(self, view: str, attempts: list[list[str]]):
        self.view, self.attempts = view, attempts
        last = "; ".join(attempts[-1]) if attempts else "nothing was drawn"
        super().__init__(f"The {view} sprite failed the QA after {len(attempts)} tries: {last}")


@dataclass
class SpriteResult:
    preset: str
    front: np.ndarray
    back: np.ndarray
    seeds: dict[str, int]
    files: list[Path] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    seconds: float = 0.0


def to_image(rgba: np.ndarray) -> Image.Image:
    return Image.fromarray(rgba, "RGBA")


def _attempt(drawer, subject, view, seed, preset, front=None, keep_raw=None):
    failures: list[list[str]] = []
    for k in range(MAX_ATTEMPTS):
        s = seed + k
        raw = drawer.draw(subject, view, s)
        if keep_raw is not None:
            keep_raw.mkdir(parents=True, exist_ok=True)
            raw.save(keep_raw / f"{view}_seed{s}.png")
        sprite, meta = process(raw, preset)
        problems = check_sprite(sprite, preset)
        overlap: dict = {}
        if view == "back" and front is not None:
            extra, overlap = check_back_view(front, sprite)
            problems += extra
        if not problems:
            return sprite, s, {**meta, **overlap, "tries": k + 1}
        failures.append(problems)
    raise SpriteFailed(view, failures)


def make_pair(
    subject: str,
    drawer: Drawer,
    preset: str | Preset = "southern_cross",
    seed: int = 1,
    keep_raw: Path | None = None,
) -> SpriteResult:
    """Draw a front and a real back view and return QA-clean sprites (not yet written)."""
    p = get_preset(preset) if isinstance(preset, str) else preset
    t0 = time.perf_counter()
    front, fs, fm = _attempt(drawer, subject, "front", seed, p, keep_raw=keep_raw)
    back, bs, bm = _attempt(drawer, subject, "back", seed + 1000, p, front=front, keep_raw=keep_raw)
    return SpriteResult(
        preset=p.key,
        front=front,
        back=back,
        seeds={"front": fs, "back": bs},
        metrics={"front": fm, "back": bm},
        seconds=time.perf_counter() - t0,
    )


def _scaled(rgba: np.ndarray, scale: int) -> Image.Image:
    img = to_image(rgba)
    return img.resize((img.width * scale, img.height * scale), Image.Resampling.NEAREST)


def _indexed(rgba: np.ndarray) -> Image.Image:
    """Indexed PNG: index 0 is transparent, the rest are the sprite's colours."""
    solid = rgba[..., 3] > 0
    colours = np.unique(rgba[solid][:, :3], axis=0)
    if len(colours) > 15:
        raise ValueError("more than 15 opaque colours cannot fit a 16-colour indexed PNG")
    lookup = {tuple(int(v) for v in c): i + 1 for i, c in enumerate(colours)}
    idx = np.zeros(solid.shape, dtype=np.uint8)
    for y, x in zip(*np.nonzero(solid), strict=True):
        idx[y, x] = lookup[tuple(int(v) for v in rgba[y, x, :3])]
    img = Image.fromarray(idx, "P")
    pal = [0, 0, 0] + [int(v) for c in colours for v in c]
    img.putpalette(pal)
    img.info["transparency"] = 0
    return img


def export_pair(result: SpriteResult, name: str, out_dir: Path) -> list[Path]:
    """Write the pair in the preset's layout. Re-checks the QA, so a failing sprite never lands."""
    p = get_preset(result.preset)
    problems = check_sprite(result.front, p) + check_sprite(result.back, p)
    problems += check_back_view(result.front, result.back)[0]
    if problems:
        raise SpriteFailed("pair", [problems])
    out_dir = Path(out_dir)
    if p.layout == "southern_cross":
        # Essentials layout: Graphics/Pokemon/Front/<Name>.png and Back/<Name>.png
        base = out_dir / "Graphics" / "Pokemon"
        fdir, bdir = base / "Front", base / "Back"
        fname = bname = f"{name}.png"
    else:
        fdir = bdir = out_dir
        fname, bname = f"{name}_front.png", f"{name}_back.png"
    fdir.mkdir(parents=True, exist_ok=True)
    bdir.mkdir(parents=True, exist_ok=True)
    files = []
    for rgba, folder, fn, scale in (
        (result.front, fdir, fname, p.front_scale),
        (result.back, bdir, bname, p.back_scale),
    ):
        img = _indexed(rgba) if p.indexed else _scaled(rgba, scale)
        img.save(folder / fn, optimize=False)
        files.append(folder / fn)
    result.files = files
    return files


def grid_preview(rgba: np.ndarray, scale: int = 6) -> Image.Image:
    """The sprite at `scale`x on a checker with a darker line between pixels (design 5.3)."""
    h, w, _ = rgba.shape
    yy, xx = np.mgrid[0 : h * scale, 0 : w * scale]
    out = np.where(((yy // scale + xx // scale) % 2)[..., None] == 0, 200, 170)
    out = np.repeat(out, 3, axis=2).astype(np.uint8)
    big = np.repeat(np.repeat(rgba, scale, axis=0), scale, axis=1)
    solid = big[..., 3] > 0
    out[solid] = big[solid][:, :3]
    line = (yy % scale == 0) | (xx % scale == 0)
    out[line] = (out[line] * 0.8).astype(np.uint8)
    return Image.fromarray(out, "RGB")
