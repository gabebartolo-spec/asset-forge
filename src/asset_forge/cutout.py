"""Cut the subject out of a picture. The quick path is matte.py (a plain background is found from
the border and flooded away). A picture with a busy background, or one the quick cut left whole,
goes to BiRefNet (MIT, docs/LICENCES.md) in models/envs/sdxl, one short-lived process per cut so
the VRAM is freed; code and weights come from the pinned local snapshot, offline."""

from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path

import numpy as np
from PIL import Image

from .matte import one_subject

REVISION = "e2bf8e4460fc8fa32bba5ea4d94b3233d367b0e4"  # pinned: trust_remote_code runs this code
WEIGHTS = "models--ZhengPeng7--BiRefNet"
KEEP_MAX = 0.90  # a quick cut that keeps more than this of the picture did not find a background
UNAVAILABLE_NOTE = ("Cutting out a busy background is not set up on this PC yet. Use a picture on "
                    "a plain background, or ask for the cut-out tool to be installed.")


class CutoutError(RuntimeError):
    """Plain words for the page."""


def needs_model(cut: Image.Image) -> bool:
    """True when the quick cut did not leave one whole subject: the background was not plain."""
    a = np.asarray(cut.getchannel("A")) > 0
    return bool(a.mean() > KEEP_MAX) or not one_subject(cut)


class Cutter(ABC):
    available: bool = True
    note: str = ""

    @abstractmethod
    def cut(self, png: bytes) -> bytes:
        """Return the picture as an RGBA PNG with the background transparent."""


class UnavailableCutter(Cutter):
    available = False
    note = UNAVAILABLE_NOTE

    def cut(self, png: bytes) -> bytes:
        raise CutoutError(UNAVAILABLE_NOTE)


Runner = Callable[[dict], bytes]


class BiRefNetCutter(Cutter):
    def __init__(self, models_dir: Path, runner: Runner | None = None) -> None:
        self.models_dir = models_dir
        self._runner = runner or self._run_process
        self.last_stats: dict = {}

    def cut(self, png: bytes) -> bytes:
        return self._runner({"png": png})

    def _run_process(self, job: dict) -> bytes:
        models = self.models_dir
        env = {**os.environ, "HF_HOME": str(models / "hf"), "HF_HUB_OFFLINE": "1",
               "PYTHONPATH": str(Path(__file__).resolve().parents[1]), "PYTHONUNBUFFERED": "1"}
        with tempfile.TemporaryDirectory() as tmp:
            src, out = Path(tmp) / "in.png", Path(tmp) / "out.png"
            src.write_bytes(job["png"])
            spec = {"src": src.as_posix(), "out": out.as_posix(), "revision": REVISION}
            proc = subprocess.run(  # noqa: S603
                [str(models / "envs" / "sdxl" / "Scripts" / "python.exe"), "-m",
                 "asset_forge.refcut_worker"],
                input=json.dumps(spec), capture_output=True, text=True, env=env,
                encoding="utf-8", errors="replace", timeout=300, check=False)
            if proc.returncode != 0 or not out.is_file():
                tail = (proc.stderr or "").strip().splitlines()[-1:] or ["no detail"]
                raise CutoutError("The cut-out tool failed. Check the graphics card is free and "
                                  f"try again. ({tail[0][:140]})")
            try:
                self.last_stats = json.loads((proc.stdout or "{}").strip().splitlines()[-1])
            except (ValueError, IndexError):
                self.last_stats = {}
            return out.read_bytes()


def _has_model(models: Path) -> bool:
    snaps = models / "hf" / "hub" / WEIGHTS / "snapshots" / REVISION
    return ((models / "envs" / "sdxl" / "Scripts" / "python.exe").is_file()
            and (snaps / "model.safetensors").is_file() and (snaps / "birefnet.py").is_file())


def default_cutter(models_dir: Path) -> Cutter:
    return BiRefNetCutter(models_dir) if _has_model(models_dir) else UnavailableCutter()


def as_png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()
