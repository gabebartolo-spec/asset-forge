"""Run the Clean step (blender/clean.py) on the bake-off meshes and build before/after sheets.

    python tools/clean/run_all.py [candidate ...]     (default: hi3dgen triposg)

Needs Pillow. Output: models/clean_out/<candidate>/<prompt>/ (clean.glb, report.json, renders),
docs/audits/clean/<candidate>_<prompt>.jpg sheets and docs/audits/clean/table.md + summary.json.
Each Blender run takes the GPU lock (tools/bakeoff/gpu_lock.py).
"""

from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "bakeoff"))
from gpu_lock import _models_dir  # noqa: E402

MODELS = _models_dir()
TYPES = {"humanoid": "humanoid", "spider": "monster", "brute": "monster", "fox": "animal",
         "bird": "animal"}
# Real-world height per prompt (m), None = the type's editable default (--height).
HEIGHTS = {"humanoid": 1.8, "spider": None, "brute": None, "fox": 0.40, "bird": 0.14}
VIEWS = ["front", "three_quarter", "left", "back", "right", "top"]
TILE = 256


def blender_exe() -> str:
    for cfg in (ROOT / "config.local.toml", MODELS.parent / "config.local.toml"):
        if cfg.exists():
            return tomllib.loads(cfg.read_text())["blender"]["exe"]
    return "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe"


def font(size):
    for n in ("arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(n, size)
        except OSError:
            pass
    return ImageFont.load_default()


def run(cand: str, prompt: str) -> Path:
    out = MODELS / "clean_out" / cand / prompt
    raw = MODELS / "bakeoff" / "out" / cand / f"{prompt}.glb"
    ref = MODELS / "bakeoff" / "refs" / f"{prompt}.png"
    cmd = [sys.executable, str(ROOT / "tools/bakeoff/gpu_lock.py"), "run", "clean", "--",
           blender_exe(), "-b", "--factory-startup", "-P", str(ROOT / "blender/clean.py"), "--",
           str(raw), str(out), "--type", TYPES[prompt], "--ref", str(ref), "--generator", cand]
    if HEIGHTS[prompt]:
        cmd += ["--height", str(HEIGHTS[prompt])]
    done = subprocess.run(cmd, capture_output=True, text=True)
    if done.returncode or not (out / "report.json").exists():
        raise SystemExit(f"clean failed for {cand}/{prompt}:\n{done.stdout[-1500:]}")
    return out


def row(folder: Path, shade: str, label: str, ref: Image.Image | None) -> Image.Image:
    im = Image.new("RGB", (TILE * 7 + 120, TILE), (235, 235, 235))
    d = ImageDraw.Draw(im)
    d.multiline_text((6, 6), label, fill=(0, 0, 0), font=font(14))
    if ref is not None:
        im.paste(ref.resize((TILE, TILE)), (120, 0))
    for i, v in enumerate(VIEWS):
        p = folder / f"{v}_{shade}.png"
        if p.exists():
            im.paste(Image.open(p).convert("RGB").resize((TILE, TILE)), (120 + TILE * (i + 1), 0))
    return im


def lit_numbers(out: Path, prompt: str) -> dict:
    """Mean luminance and saturation of the lit front colour render (body pixels) against the
    reference picture (its opaque pixels). Ratios near 1.0 mean the sheet reads true."""
    import numpy as np

    ref = np.asarray(Image.open(MODELS / "bakeoff" / "refs" / f"{prompt}.png").convert("RGBA"),
                     np.float64) / 255
    rgb = ref[ref[..., 3] > 0.5][:, :3]
    img = Image.open(out / "after" / "front_colour.png").convert("RGB")
    shot = np.asarray(img, np.float64) / 255
    body = np.abs(shot - shot[2, 2]).sum(axis=2) > 0.06
    inner = body.copy()
    for sh in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        inner &= np.roll(body, sh, (0, 1))
    lit = shot[inner]

    def stats(c):
        mx, mn = c.max(axis=1), c.min(axis=1)
        luma = (c @ [0.2126, 0.7152, 0.0722]).mean()
        return float(luma), float(((mx - mn) / np.maximum(mx, 1e-6)).mean())

    (rl, rs), (ll, ls) = stats(rgb), stats(lit)
    return {"ref_luma": round(rl, 3), "lit_luma": round(ll, 3), "luma_ratio": round(ll / rl, 3),
            "ref_sat": round(rs, 3), "lit_sat": round(ls, 3), "sat_ratio": round(ls / rs, 3)}


def sheet(cand: str, prompt: str, out: Path, dest: Path):
    ref = Image.open(MODELS / "bakeoff" / "refs" / f"{prompt}.png").convert("RGBA")
    bg = Image.new("RGBA", ref.size, (255, 255, 255, 255))
    ref = Image.alpha_composite(bg, ref).convert("RGB")
    rows = [row(out / "before", "clay", "BEFORE\nraw, clay", ref),
            row(out / "after", "clay", "AFTER\nclean, clay", None),
            row(out / "after", "colour", "AFTER\nclean, colour", None)]
    w, h = rows[0].size
    img = Image.new("RGB", (w, h * 3 + 28), (255, 255, 255))
    ImageDraw.Draw(img).text((6, 6), f"{cand} / {prompt}   columns: reference, front, 3/4, left, "
                             "back, right, top; before and after share one camera", fill=(0, 0, 0),
                             font=font(15))
    for i, r in enumerate(rows):
        img.paste(r, (0, 28 + h * i))
    img.save(dest, quality=88)


def main():
    cands = sys.argv[1:] or ["hi3dgen", "triposg"]
    docs = ROOT / "docs" / "audits" / "clean"
    docs.mkdir(parents=True, exist_ok=True)
    summary, lines = {}, []
    lines.append("| Candidate | Prompt | Type | Raw tris | Clean tris | Texture | Parts (raw / "
                 "specks cut / final) | Outline diff front / side / top | Gates | Time (s) |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    sys.path.insert(0, str(ROOT / "src"))
    from asset_forge.gates import check
    for cand in cands:
        for prompt in TYPES:
            out = run(cand, prompt)
            sheet(cand, prompt, out, docs / f"{cand}_{prompt}.jpg")
            r = json.loads((out / "report.json").read_text())
            broken = check(r, TYPES[prompt])
            s = r["silhouette"]
            lp = r["loose_parts"]
            summary[f"{cand}/{prompt}"] = r | {"gate_failures": broken,
                                                "lit_vs_reference": lit_numbers(out, prompt)}
            lines.append(
                f"| {cand} | {prompt} | {r['type']} | {r['raw_triangles']:,} | {r['triangles']:,} "
                f"| {r['texture']['width']} | {lp['raw_after_weld']} / "
                f"{lp['floaters_deleted'] + lp['floaters_deleted_after_decimate']} / "
                f"{lp['after_clean']} | {s['front']:.3f} / {s['side']:.3f} / {s['top']:.3f} "
                f"| {'pass' if not broken else 'FAIL'} "
                f"| {r['timings_s']['total']:.1f} + {r['timings_s'].get('sheets', 0):.1f} sheets |")
            print(lines[-1], flush=True)
    (docs / "table.md").write_text("\n".join(lines) + "\n")
    (docs / "summary.json").write_text(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
