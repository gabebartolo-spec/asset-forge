"""Sprite mode A: draw from text, make it pixel-perfect, check it, export it (design 5.3)."""

from .pipeline import SpriteFailed, SpriteResult, export_pair, grid_preview, make_pair
from .presets import DEFAULT_PRESET, PRESETS, Preset, get_preset
from .qa import check_back_view, check_sprite

__all__ = [
    "DEFAULT_PRESET",
    "PRESETS",
    "Preset",
    "SpriteFailed",
    "SpriteResult",
    "check_back_view",
    "check_sprite",
    "export_pair",
    "get_preset",
    "grid_preview",
    "make_pair",
]
