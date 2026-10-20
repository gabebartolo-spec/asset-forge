"""Target presets (design 5.3). A preset is data: size, palette limit, views and export layout."""

from __future__ import annotations

from dataclasses import dataclass

# One dark colour for every outline, so "outlined" is a plain fact the QA can check.
OUTLINE_COLOUR = (22, 18, 30)
OUTLINE_LUMA_MAX = 70  # an edge pixel at or below this brightness counts as outline
EDGE_MARGIN_PX = 2  # director/design: the sprite stays 2 px clear of the canvas edge
BACK_IOU_MAX = 0.90  # a back whose outline overlaps the front's (or its mirror) more is rejected

# Same-creature gate (front vs back); calibrated in the PR notes.
GAP_OK_FRAC = 0.0035  # an enclosed see-through gap this share of the canvas (32 px at 96) is drawn
LEG_GAP_ZONE = 0.35  # a see-through gap in this bottom share of the sprite is between the legs
MAX_HOLE_PX_LEGS = 13  # ... and counts as drawn when it is at least this big
BACK_SYMMETRY_MIN = 0.55  # a view from behind mirrors onto itself at least this well
FRONT_SYMMETRY_MIN = 0.55  # a front facing the viewer mirrors onto itself at least this well
COLOUR_DISTANCE_MAX = 0.65
ASPECT_RATIO_MAX = 1.6
MASS_RATIO_MAX = 2.0


@dataclass(frozen=True)
class Preset:
    key: str
    label: str
    art_size: int  # square art canvas, pixels
    max_colours: int  # opaque colours allowed, outline colour included
    indexed: bool  # export as an indexed PNG (index 0 transparent)
    front_scale: int  # integer nearest-neighbour upscale on export
    back_scale: int
    layout: str  # "southern_cross" (pack folders) or "flat" (front.png / back.png)


PRESETS: dict[str, Preset] = {
    "southern_cross": Preset(
        key="southern_cross",
        label="Southern Cross (Essentials v21.1, Gen 9 Pack v3.3.8)",
        art_size=80,  # D-023: drawn at 80 px, exported 2x = 160, like the real pack
        max_colours=32,  # no fixed limit in the pack; this cap keeps the art clean
        indexed=False,
        front_scale=2,
        back_scale=2,
        layout="southern_cross",
    ),
    "gba": Preset(
        key="gba",
        label="GBA",
        art_size=64,
        max_colours=15,  # 16 including the transparent index
        indexed=True,
        front_scale=1,
        back_scale=1,
        layout="flat",
    ),
}
DEFAULT_PRESET = "southern_cross"


def get_preset(key: str) -> Preset:
    try:
        return PRESETS[key]
    except KeyError:
        raise ValueError(f"unknown preset {key!r}; choose one of {sorted(PRESETS)}") from None
