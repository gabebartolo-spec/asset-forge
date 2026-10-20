"""Mode A end to end: draw -> post-process -> QA (retry on a new seed) -> export."""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

from .draw import Drawer
from .pairqa import check_anatomy_match, check_back_faces_away, check_back_has_no_face
from .post import finish, isolated_share, prepare
from .presets import Preset, get_preset
from .qa import check_back_view, check_front_faces_viewer, check_same_creature, check_sprite
from .sheet import split_sheet

SHEET_BATCH = 3  # sheets per draw call (one call is ~33 s warm)
MAX_BATCHES = 2  # then the pair fails and the user is offered a re-roll


class SpriteFailed(Exception):
    """No pair passed the sprite QA, so nothing is exported."""

    def __init__(self, view: str, attempts: list[list[str]]):
        self.view, self.attempts = view, attempts
        last = "; ".join(attempts[-1]) if attempts else "nothing was drawn"
        if view == "pair":
            msg = (
                f"No front and back pair passed the checks: {last} Nothing was exported. "
                "Re-roll to draw a new turnaround sheet."
            )
        else:
            msg = f"The {view} sprite failed the QA: {last}"
        super().__init__(msg)


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


def _save_raw(keep_raw: Path | None, name: str, raw: Image.Image) -> None:
    if keep_raw is not None:
        keep_raw.mkdir(parents=True, exist_ok=True)
        raw.save(keep_raw / name)


def pair_problems(front: np.ndarray, back: np.ndarray, preset: Preset) -> tuple[list[str], dict]:
    """Every gate on a front and back that share a palette. Empty list = may be exported."""
    problems = check_sprite(front, preset) + check_sprite(back, preset)
    metrics: dict = {}
    for fn in (
        check_back_view,
        check_same_creature,
        lambda f, b: check_back_faces_away(b),
        check_back_has_no_face,
        check_anatomy_match,
    ):
        found, m = fn(front, back)
        problems += found
        metrics |= m
    return problems, metrics


def _shape_problems(front: np.ndarray, back: np.ndarray) -> list[str]:
    """The cheap shape-only gates, run on unpaired sprites to skip hopeless pairs."""
    return (
        check_back_view(front, back)[0]
        + check_back_faces_away(back)[0]
        + check_same_creature(front, back)[0]
        + check_anatomy_match(front, back)[0]
    )


def _best_pair(views: list[Image.Image], preset: Preset, failures: Counter):
    """The first front/back pair among one sheet's views that passes every gate, else None."""
    prepped = []
    for img in views:
        pre, meta = prepare(img, preset)
        alone = finish([pre], preset)[0]
        problems = check_sprite(alone, preset)
        face_problems, face = check_front_faces_viewer(alone)
        prepped.append((pre, alone, meta | face, problems, face_problems))
    usable = [i for i, p in enumerate(prepped) if not p[3]]
    fronts = [i for i in usable if not prepped[i][4]]
    fronts.sort(key=lambda i: -prepped[i][2]["front_symmetry"])
    if not fronts:
        failures.update(p for q in prepped for p in q[3] + q[4])
    for i in fronts:
        for j in usable:
            if j == i:
                continue
            quick = _shape_problems(prepped[i][1], prepped[j][1])
            if quick:
                failures.update(quick)
                continue
            front, back = finish([prepped[i][0], prepped[j][0]], preset)
            problems, metrics = pair_problems(front, back, preset)
            if not problems:
                return front, back, {"front": prepped[i][2], "back": prepped[j][2], **metrics}
            failures.update(problems)
    return None


def make_pair(
    subject: str,
    drawer: Drawer,
    preset: str | Preset = "southern_cross",
    seed: int = 1,
    keep_raw: Path | None = None,
) -> SpriteResult:
    """Draw turnaround sheets (front and back of one creature together), cut them into views and
    return the first QA-clean front/back pair (not yet written). Raises SpriteFailed otherwise."""
    p = get_preset(preset) if isinstance(preset, str) else preset
    t0 = time.perf_counter()
    times = {"draw": 0.0, "post": 0.0}
    failures: Counter = Counter()
    tried = 0
    for batch in range(MAX_BATCHES):
        seeds = [seed + batch * SHEET_BATCH + k for k in range(SHEET_BATCH)]
        t = time.perf_counter()
        sheets = drawer.draw_sheet(subject, seeds)
        times["draw"] += time.perf_counter() - t
        for s, sheet in zip(seeds, sheets, strict=True):
            tried += 1
            _save_raw(keep_raw, f"sheet_seed{s}.png", sheet)
            t = time.perf_counter()
            views = split_sheet(sheet)
            if len(views) < 2:
                failures["The sheet held fewer than two usable views."] += 1
                times["post"] += time.perf_counter() - t
                continue
            found = _best_pair(views, p, failures)
            times["post"] += time.perf_counter() - t
            if found:
                front, back, metrics = found
                return SpriteResult(
                    preset=p.key,
                    front=front,
                    back=back,
                    seeds={"sheet": s},
                    metrics={
                        **metrics,
                        "sheets_tried": tried,
                        "views_in_sheet": len(views),
                        "speckle": {"front": isolated_share(front), "back": isolated_share(back)},
                        "seconds": {k: round(v, 2) for k, v in times.items()},
                    },
                    seconds=time.perf_counter() - t0,
                )
    common = [text for text, _ in failures.most_common(3)]
    raise SpriteFailed("pair", [common])


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
    problems = pair_problems(result.front, result.back, p)[0]
    if problems:
        raise SpriteFailed("pair", [problems])
    out_dir = Path(out_dir)
    if p.layout == "southern_cross":
        # Essentials layout: Graphics/Pokemon/Front/<Name>.png and Back/<Name>.png
        base = out_dir / "Graphics" / "Pokemon"
        fdir, bdir = base / "Front", base / "Back"
        fname = bname = f"{name.upper()}.png"  # D-023: pack names are UPPERCASE
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


def pair_preview(front: np.ndarray, back: np.ndarray, scale: int = 6) -> Image.Image:
    """Front and back side by side, each on the 6x grid (the pair as the director sees it)."""
    a, b = grid_preview(front, scale), grid_preview(back, scale)
    out = Image.new("RGB", (a.width + b.width + 12, max(a.height, b.height)), (60, 60, 60))
    out.paste(a, (0, 0))
    out.paste(b, (a.width + 12, 0))
    return out
