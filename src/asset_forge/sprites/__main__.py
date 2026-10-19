"""CLI the UI will later call: python -m asset_forge.sprites "a small fire lizard creature" ...

Run it with the SDXL env's python (models/envs/sdxl) under the GPU lock:
  python tools/bakeoff/gpu_lock.py run sprites -- <env python> -m asset_forge.sprites ...
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .draw import SdxlDrawer
from .pipeline import SpriteFailed, export_pair, grid_preview, make_pair, to_image
from .presets import DEFAULT_PRESET, PRESETS


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="asset_forge.sprites")
    ap.add_argument("subject", help='what to draw, e.g. "a small fire lizard creature"')
    ap.add_argument("--preset", default=DEFAULT_PRESET, choices=sorted(PRESETS))
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--name", default="Sprite")
    ap.add_argument("--out", type=Path, required=True, help="export folder")
    ap.add_argument("--shots", type=Path, help="also save 1x and 6x grid previews here")
    ap.add_argument("--keep-raw", type=Path, help="save the raw generated images here")
    a = ap.parse_args(argv)

    drawer = SdxlDrawer()
    try:
        res = make_pair(a.subject, drawer, a.preset, a.seed, keep_raw=a.keep_raw)
    except SpriteFailed as e:
        print(f"NOT EXPORTED: {e}", file=sys.stderr)
        return 1
    files = export_pair(res, a.name, a.out)
    if a.shots:
        a.shots.mkdir(parents=True, exist_ok=True)
        for view, arr in (("front", res.front), ("back", res.back)):
            to_image(arr).save(a.shots / f"{a.preset}_{view}_1x.png")
            grid_preview(arr, 6).save(a.shots / f"{a.preset}_{view}_6x_grid.png")
    report = {
        "files": [str(f) for f in files],
        "seeds": res.seeds,
        "metrics": res.metrics,
        "seconds_total": round(res.seconds, 1),
        "seconds_per_image": [round(t, 1) for t in drawer.timings],
        "model_load_seconds": round(drawer.load_seconds, 1),
        "peak_vram_mb": round(drawer.peak_vram_mb),
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
