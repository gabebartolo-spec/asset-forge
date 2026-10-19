"""Render and label the bake-off inspection sheets, then write the report's data table.

    uv run --with pillow python tools/bakeoff/sheets.py [candidate ...] [--yaw cand=deg]

For every candidate in models/bakeoff/out/<candidate>/run.json and every mesh it produced:
  1. headless Blender renders six views, clay and colour (render_views.py, cached);
  2. a labelled per-candidate sheet: reference | six clay views | six colour views;
then per prompt a comparison board (one labelled row per candidate) and summary.json.
Output: models/bakeoff/sheets/ (copied into docs/audits/bakeoff/ for the report).
"""

from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parent))
from gpu_lock import _models_dir, gpu_lock  # noqa: E402

HERE = Path(__file__).parent
MODELS = _models_dir()
OUT = MODELS / "bakeoff" / "out"
SHEETS = MODELS / "bakeoff" / "sheets"
VIEWS = ["front", "three_quarter", "left", "back", "right", "top"]
TILE = 300


def blender_exe() -> str:
    cfg = HERE.parents[1] / "config.local.toml"
    if not cfg.exists():
        cfg = HERE.parents[1] / "config.example.toml"
    return tomllib.loads(cfg.read_text())["blender"]["exe"]


def font(size: int) -> ImageFont.ImageFont:
    for name in ("arialbd.ttf", "arial.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def tile(path: Path | None, label: str) -> Image.Image:
    im = Image.new("RGB", (TILE, TILE), (235, 235, 235))
    if path and path.exists():
        src = Image.open(path).convert("RGBA")
        src.thumbnail((TILE, TILE), Image.LANCZOS)
        bg = Image.new("RGBA", src.size, (235, 235, 235, 255))
        im.paste(Image.alpha_composite(bg, src).convert("RGB"),
                 ((TILE - src.width) // 2, (TILE - src.height) // 2))
    else:
        ImageDraw.Draw(im).text((TILE // 2, TILE // 2), "none", fill=(150, 0, 0),
                                font=font(28), anchor="mm")
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, TILE, 30), fill=(30, 30, 30))
    d.text((8, 4), label, fill="white", font=font(20))
    return im


def render(mesh: Path, dest: Path, yaw: float) -> dict:
    stats = dest / "stats.json"
    if not stats.exists():
        cmd = [blender_exe(), "-b", "--factory-startup", "-P", str(HERE / "render_views.py"),
               "--", str(mesh), str(dest), "--yaw", str(yaw)]
        with gpu_lock(f"bakeoff-render:{mesh.parent.name}"):
            subprocess.run(cmd, check=True, capture_output=True)
    return json.loads(stats.read_text())


def header(text: str, width: int, size: int = 30) -> Image.Image:
    im = Image.new("RGB", (width, size + 20), (255, 255, 255))
    ImageDraw.Draw(im).text((10, 8), text, fill="black", font=font(size))
    return im


def stack(rows: list[Image.Image]) -> Image.Image:
    w = max(r.width for r in rows)
    out = Image.new("RGB", (w, sum(r.height for r in rows)), "white")
    y = 0
    for r in rows:
        out.paste(r, (0, y))
        y += r.height
    return out


def row(tiles: list[Image.Image]) -> Image.Image:
    out = Image.new("RGB", (TILE * len(tiles) + 4 * (len(tiles) - 1), TILE), "white")
    for i, t in enumerate(tiles):
        out.paste(t, (i * (TILE + 4), 0))
    return out


def main() -> int:
    argv = sys.argv[1:]
    yaws = dict(a.split("=") for a in argv if "=" in a)
    names = [a for a in argv if "=" not in a and not a.startswith("--")] or sorted(
        p.parent.name for p in OUT.glob("*/run.json"))
    refs = MODELS / "bakeoff" / "refs"
    SHEETS.mkdir(parents=True, exist_ok=True)
    summary: dict = {}
    for letter, name in zip("ABCDEFGH", names, strict=False):
        run = json.loads((OUT / name / "run.json").read_text())
        summary[name] = {"letter": letter, "run": run, "items": {}}
        for item in run.get("items", []):
            pid = item["id"]
            mesh = OUT / name / item["mesh"] if item.get("mesh") else None
            if not mesh or not mesh.exists():
                summary[name]["items"][pid] = {"error": item.get("error") or "no mesh"}
                continue
            dest = SHEETS / "renders" / name / pid
            stats = render(mesh, dest, float(yaws.get(name, 0)))
            summary[name]["items"][pid] = {**item, **stats}
            clay = [tile(dest / f"{v}_clay.png", v.replace("_", " ")) for v in VIEWS]
            colour = [tile(dest / f"{v}_colour.png", v.replace("_", " ") + " colour")
                      for v in VIEWS]
            title = (f"{letter}  {name} - {pid}   {stats['triangles']:,} tris   "
                     f"{item.get('gen_s', 0):.0f} s   peak {item.get('gpu_peak_gb', '?')} GB   "
                     f"parts {stats['loose_parts_over_1pct']}   open edges {stats['open_edges']:,}")
            sheet = stack([
                header(title, TILE * 7 + 24),
                row([tile(refs / f"{pid}.png", "reference")] + clay),
                row([tile(None, "")] + colour) if stats["colour_source"] else
                header("no colour output (geometry only)", TILE * 7 + 24, 22),
            ])
            sheet.save(SHEETS / f"{name}_{pid}.png")

    # One comparison board per prompt: a labelled row per candidate.
    prompts = tomllib.loads((HERE / "prompts.toml").read_text())["prompt"]
    for p in prompts:
        pid = p["id"]
        rows = [header(f"{pid}: {p['text'][:90]}", TILE * 7 + 24, 24),
                row([tile(refs / f"{pid}.png", "reference")])]
        for name, s in summary.items():
            dest = SHEETS / "renders" / name / pid
            it = s["items"].get(pid, {})
            label = f"{s['letter']}  {name}"
            if "triangles" in it:
                label += f"   {it.get('gen_s', 0):.0f} s   {it['triangles']:,} tris"
            else:
                label += f"   FAILED: {it.get('error', '?')[:60]}"
            rows.append(header(label, TILE * 7 + 24, 26))
            tiles = [tile(dest / f"{v}_clay.png", v.replace("_", " ")) for v in VIEWS]
            tiles.append(tile(dest / "three_quarter_colour.png", "3/4 colour"))
            rows.append(row(tiles))
        stack(rows).save(SHEETS / f"board_{pid}.png")
    (SHEETS / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print(f"sheets in {SHEETS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
