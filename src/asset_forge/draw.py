"""Text-only input: a local image model draws the reference picture, then image-to-3D runs
(design 5.2 Step 1). The draw sits behind this one small interface.

The real drawer is `SdxlReferenceDrawer` (SDXL 1.0 base, no LoRA). `MockDrawer` is for tests.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path

from PIL import Image, ImageDraw

from .config import Settings

UNAVAILABLE_NOTE = ("Drawing a picture from your words isn't ready yet. "
                    "Add a picture to make a model.")


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


# One style for every type (the bake-off's, tools/bakeoff/prompts.toml), plus a view per type.
STYLE = ("single full-body subject, centered, plain flat white background, soft even studio "
         "lighting, clean 3D game asset concept render, whole body visible head to feet, no "
         "shadow on the ground, no text")
NEGATIVE = ("cropped, cut off, multiple characters, scenery, background objects, text, watermark, "
            "frame, blurry, photo of a toy, pedestal, ground shadow")
VIEWS = {
    "humanoid": "standing straight in an A-pose with arms angled down away from the body, "
                "front view, facing the camera",
    "monster": "three-quarter front view, every limb, leg and arm clearly visible and apart",
    "animal": "standing, side view facing left, all four legs or both legs visible",
}
WEIGHTS = "models--stabilityai--stable-diffusion-xl-base-1.0"
Runner = Callable[[dict, Callable[[str], None]], bytes]


def _env_python(models: Path) -> Path:
    return models / "envs" / "sdxl" / "Scripts" / "python.exe"


def _has_weights(models: Path) -> bool:
    snaps = models / "hf" / "hub" / WEIGHTS / "snapshots"
    return (_env_python(models).is_file() and snaps.is_dir()
            and any((d / "model_index.json").is_file() for d in snaps.iterdir()))


class SdxlReferenceDrawer(ReferenceDrawer):
    """Text -> one clean reference picture, SDXL 1.0 base in its own env (models/envs/sdxl), so
    the app never imports torch. Each draw is a short-lived process: it loads, draws and exits,
    which frees the VRAM. It runs inside a queue job, which already holds models/gpu.lock, so it
    must not take the lock again."""

    def __init__(self, models_dir: Path | None = None, runner: Runner | None = None,
                 steps: int = 30, guidance: float = 6.0) -> None:
        self.models_dir, self.steps, self.guidance = models_dir, steps, guidance
        self._runner = runner or self._run_process
        self.last_stats: dict = {}  # peak_vram_mb of the latest draw

    def build_job(self, prompt: str, asset_type: str, seed: int) -> dict:
        if asset_type not in VIEWS:
            raise DrawError("Choose Humanoid, Monster or Animal first.")
        text = f"{prompt.strip()}, {VIEWS[asset_type]}, {STYLE}"
        return {"prompt": text, "negative": NEGATIVE, "seed": seed, "steps": self.steps,
                "guidance": self.guidance}

    def draw(self, prompt, asset_type, seed, progress):  # noqa: ANN001
        job = self.build_job(prompt, asset_type, seed)
        progress("Drawing your picture...")
        return self._runner(job, progress)

    def _run_process(self, job: dict, progress: Callable[[str], None]) -> bytes:  # noqa: ARG002
        models = self.models_dir
        env = {**os.environ, "HF_HOME": str(models / "hf"), "HF_HUB_OFFLINE": "1",
               "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
               "PYTHONUNBUFFERED": "1"}
        with tempfile.TemporaryDirectory() as tmp:
            job = {**job, "out": str(Path(tmp) / "ref.png")}
            proc = subprocess.run(  # noqa: S603
                [str(_env_python(models)), "-m", "asset_forge.refdraw_worker"],
                input=json.dumps(job), capture_output=True, text=True, env=env,
                encoding="utf-8", errors="replace", timeout=900, check=False)
            out = Path(job["out"])
            if proc.returncode != 0 or not out.is_file():
                tail = (proc.stderr or "").strip().splitlines()[-1:] or ["no detail"]
                raise DrawError("The picture maker failed. Check the graphics card is free and "
                                f"press Draw another. ({tail[0][:140]})")
            try:
                self.last_stats = json.loads((proc.stdout or "{}").strip().splitlines()[-1])
            except (ValueError, IndexError):
                self.last_stats = {}
            return out.read_bytes()


def default_drawer(settings: Settings) -> ReferenceDrawer:
    if _has_weights(settings.models_dir):
        return SdxlReferenceDrawer(settings.models_dir)
    return UnavailableDrawer()


def save_png(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
