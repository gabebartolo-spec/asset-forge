"""Contact sheet of a clip's preview frames, for the lead's own look (local only).

    python tools/animate/sheet.py FRAMES_DIR/<clip> OUT.png [--cols 8] [--count 16]

Picks `count` evenly spaced frames, labels each with its frame number and lays them out in a grid.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("frames", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--cols", type=int, default=8)
    ap.add_argument("--count", type=int, default=16)
    a = ap.parse_args()
    paths = sorted(a.frames.glob("*.png"))
    n = min(a.count, len(paths))
    pick = [paths[round(i * (len(paths) - 1) / max(n - 1, 1))] for i in range(n)]
    ims = [Image.open(p).convert("RGB") for p in pick]
    w, h = ims[0].size
    rows = -(-n // a.cols)
    sheet = Image.new("RGB", (w * a.cols, h * rows), "white")
    for i, (p, im) in enumerate(zip(pick, ims, strict=True)):
        d = ImageDraw.Draw(im)
        d.text((6, 6), str(int(p.stem)), fill=(200, 0, 0))
        sheet.paste(im, ((i % a.cols) * w, (i // a.cols) * h))
    sheet.save(a.out)


if __name__ == "__main__":
    main()
