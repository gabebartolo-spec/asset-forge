"""Mode A end to end: draw -> post-process -> QA (retry on a new seed) -> export."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

from .draw import Drawer
from .post import finish, isolated_share, prepare
from .presets import Preset, get_preset
from .qa import check_back_view, check_front_faces_viewer, check_same_creature, check_sprite

MAX_ATTEMPTS = 6
FRONT_FIRST_BATCH = 1  # the first front usually passes; later fronts are drawn 3 at a time
FRONT_BATCH = 3
BACK_BATCH = 3  # back candidates per call; the first that passes every check wins


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


def _batches(seeds: list[int], first: int, rest: int):
    """Seeds in draw batches: `first` for the opening call, `rest` for later ones."""
    i, size = 0, first
    while i < len(seeds):
        yield seeds[i : i + size]
        i += size
        size = rest


def _save_raw(keep_raw: Path | None, view: str, seed: int, raw: Image.Image) -> None:
    if keep_raw is not None:
        keep_raw.mkdir(parents=True, exist_ok=True)
        raw.save(keep_raw / f"{view}_seed{seed}.png")


def _draw_front(drawer, subject, seed, preset, keep_raw, times):
    """First front that passes the sprite QA. Returns (raw, prepared, sprite, seed, meta)."""
    failures: list[list[str]] = []
    tried = 0
    seeds = [seed + k for k in range(MAX_ATTEMPTS)]
    for group in _batches(seeds, FRONT_FIRST_BATCH, FRONT_BATCH):
        t = time.perf_counter()
        raws = drawer.draw_batch(subject, "front", group)
        times["draw_front"] = times.get("draw_front", 0.0) + time.perf_counter() - t
        for s, raw in zip(group, raws, strict=True):
            tried += 1
            _save_raw(keep_raw, "front", s, raw)
            t = time.perf_counter()
            pre, meta = prepare(raw, preset)
            sprite = finish([pre], preset)[0]
            problems = check_sprite(sprite, preset)
            face_problems, face = check_front_faces_viewer(sprite)
            problems += face_problems
            times["post"] = times.get("post", 0.0) + time.perf_counter() - t
            if not problems:
                return raw, pre, s, {**meta, **face, "candidates_tried": tried}
            failures.append(problems)
    raise SpriteFailed("front", failures)


def _draw_back(drawer, subject, front_raw, front_pre, seed, preset, keep_raw, times):
    """First back drawn from the front that passes every check, as a pair with the front.

    Returns (front, back, seed, meta)."""
    failures: list[list[str]] = []
    tried = 0
    seeds = [seed + k for k in range(MAX_ATTEMPTS)]
    for group in _batches(seeds, BACK_BATCH, BACK_BATCH):
        t = time.perf_counter()
        raws = drawer.draw_batch(subject, "back", group, init=front_raw)
        times["draw_back"] = times.get("draw_back", 0.0) + time.perf_counter() - t
        for s, raw in zip(group, raws, strict=True):
            tried += 1
            _save_raw(keep_raw, "back", s, raw)
            t = time.perf_counter()
            pre, meta = prepare(raw, preset)
            front, back = finish([front_pre, pre], preset)  # one palette for the pair
            problems = check_sprite(front, preset) + check_sprite(back, preset)
            extra_view, overlap = check_back_view(front, back)
            extra_same, same = check_same_creature(front, back)
            problems += extra_view + extra_same
            times["post"] = times.get("post", 0.0) + time.perf_counter() - t
            if not problems:
                return front, back, s, {**meta, **overlap, **same, "candidates_tried": tried}
            failures.append(problems)
    raise SpriteFailed("back", failures)


def make_pair(
    subject: str,
    drawer: Drawer,
    preset: str | Preset = "southern_cross",
    seed: int = 1,
    keep_raw: Path | None = None,
) -> SpriteResult:
    """Draw a front, then a back from that front, and return QA-clean sprites (not yet written)."""
    p = get_preset(preset) if isinstance(preset, str) else preset
    t0 = time.perf_counter()
    times: dict[str, float] = {}
    raw, pre, fs, fm = _draw_front(drawer, subject, seed, p, keep_raw, times)
    front, back, bs, bm = _draw_back(drawer, subject, raw, pre, seed + 1000, p, keep_raw, times)
    total = time.perf_counter() - t0
    return SpriteResult(
        preset=p.key,
        front=front,
        back=back,
        seeds={"front": fs, "back": bs},
        metrics={
            "front": fm,
            "back": bm,
            "speckle": {"front": isolated_share(front), "back": isolated_share(back)},
            "seconds": {k: round(v, 2) for k, v in times.items()},
        },
        seconds=total,
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
    problems += check_same_creature(result.front, result.back)[0]
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
