"""Text-only input: a local image model draws the reference picture, then image-to-3D runs
(design 5.2 Step 1). The draw sits behind this one small interface.

TODO(PR #11, claude/sprites): the real SDXL drawer lands with the sprite update. Until then the
app uses `UnavailableDrawer` and says so in plain words; `MockDrawer` is what the tests use.
When #11 merges, add `SdxlDrawer(ReferenceDrawer)` and return it from `default_drawer`.
"""

from __future__ import annotations

import io
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path

from PIL import Image, ImageDraw

from .config import Settings

UNAVAILABLE_NOTE = ("Drawing from text arrives with the sprite update. "
                    "For now, add a picture.")


class DrawError(RuntimeError):
    """A plain-words error the page can show as is."""


class ReferenceDrawer(ABC):
    available: bool = True
    note: str = ""  # shown instead of the Draw button when `available` is False

    @abstractmethod
    def draw(self, prompt: str, asset_type: str, seed: int, progress: Callable[[str], None]
             ) -> bytes:
        """Return one PNG: a clean front reference of `prompt` on a plain background."""


class UnavailableDrawer(ReferenceDrawer):
    available = False
    note = UNAVAILABLE_NOTE

    def draw(self, prompt, asset_type, seed, progress):  # noqa: ANN001
        raise DrawError(UNAVAILABLE_NOTE)


class MockDrawer(ReferenceDrawer):
    """Tests and screenshots only: a plain figure whose colour follows the seed."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int]] = []

    def draw(self, prompt, asset_type, seed, progress):  # noqa: ANN001
        self.calls.append((prompt, asset_type, seed))
        progress("Drawing your picture...")
        colour = (60 + seed * 37 % 160, 90 + seed * 71 % 120, 150 + seed * 13 % 90, 255)
        img = Image.new("RGBA", (256, 256), (255, 255, 255, 255))
        d = ImageDraw.Draw(img)
        d.ellipse((98, 20, 158, 80), fill=colour)
        d.rounded_rectangle((88, 84, 168, 180), 14, fill=colour)
        d.rectangle((92, 180, 122, 236), fill=colour)
        d.rectangle((134, 180, 164, 236), fill=colour)
        buf = io.BytesIO()
        img.save(buf, "PNG")
        return buf.getvalue()


def default_drawer(settings: Settings) -> ReferenceDrawer:  # noqa: ARG001
    return UnavailableDrawer()


def save_png(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
