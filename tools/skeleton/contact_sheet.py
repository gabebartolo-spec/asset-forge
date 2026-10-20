"""Tile one rig's test-pose views into one labelled image per shade.

    python tools/skeleton/contact_sheet.py RIG_DIR OUT.png [--shade clay|colour] [--size 256]
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

VIEWS = ("front", "back", "left", "right", "three_quarter", "top")


def main() -> None:
    a = sys.argv[1:]
    src, out = Path(a[0]), Path(a[1])
    shade = a[a.index("--shade") + 1] if "--shade" in a else "colour"
    size = int(a[a.index("--size") + 1]) if "--size" in a else 256
    sheet = Image.new("RGB", (size * len(VIEWS), size), "white")
    for i, v in enumerate(VIEWS):
        im = Image.open(src / f"pose_{v}_{shade}.png").convert("RGB").resize((size, size))
        ImageDraw.Draw(im).text((6, 6), v, fill=(0, 0, 0))
        sheet.paste(im, (i * size, 0))
    sheet.save(out)


if __name__ == "__main__":
    main()
