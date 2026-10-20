"""The draw step: local SDXL 1.0 base + the pixel-art-xl LoRA (both CLEARED in LICENCES.md).

Run inside the SDXL env (models/envs/sdxl: diffusers, torch, peft). Weights live under
models/hf. Never Stability Matrix's ComfyUI. Tests use a fake Drawer instead.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Protocol

import numpy as np
from PIL import Image

SDXL_REPO = "stabilityai/stable-diffusion-xl-base-1.0"
LORA_REPO = "nerijs/pixel-art-xl"
LORA_FILE = "pixel-art-xl.safetensors"

# Front and back are drawn TOGETHER on one wide turnaround sheet (left front, right back), so the
# model keeps one creature: separate back draws gave a three-quarter front or another body.
SHEET_W, SHEET_H = 1344, 768
SHEET_PROMPT = (
    "pixel art character turnaround sheet of {subject}, two views side by side of the same "
    "creature: on the left the front view facing the camera with face visible, on the right the "
    "back view from behind with no face, rear of the body and tail, same colours, same size, "
    "flat colours, clean pixels, plain white background, no shadow, no ground"
)
SHEET_NEGATIVE = (
    "text, labels, arrows, grid, frame, border, shadow, ground, floor, scenery, photo, 3d render, "
    "blurry, gradient, watermark, three views, side view only, profile only, many creatures"
)


FRONT_PROMPT = (
    "{subject}, three-quarter view from the front, head turned toward the viewer, both eyes "
    "visible, looking at the camera, pixel art, flat colours, clean pixels, full body, centred, "
    "plain white background, no shadow, no ground, a single creature, solo"
)
FRONT_NEGATIVE = (
    "side view, profile, facing left, facing right, from the side, blurry, smooth, gradient, "
    "photo, 3d render, text, watermark, cropped, scenery, shadow, ground, floor, multiple "
    "creatures, sprite sheet, collage, group, many, top view"
)
# The back is painted into the empty right part of a canvas whose left part is the finished
# front, so the model sees the very creature it must turn round (outpainting a turnaround).
BACK_PROMPT = (
    "pixel art character turnaround sheet of {subject}: on the left the front view, on the right "
    "the same creature seen from directly behind, back of the head, rear of the body and tail, "
    "no face, same colours, same size, flat colours, clean pixels, plain white background, no "
    "shadow, no ground"
)
BACK_NEGATIVE = (
    "face, eyes, beak, mouth, front view, facing the viewer, side view, profile, text, labels, "
    "shadow, ground, scenery, blurry, gradient, photo, 3d render, many creatures"
)
FRONT_SIZE = 1024
BACK_W = 768  # width of the blank strip the back is painted into
BACK_STEPS = 24


class Drawer(Protocol):
    """`draw_sheet` makes one front+back turnaround sheet per seed (a wide image holding several
    views of one creature; `sheet.split_sheet` cuts it up)."""

    def draw_sheet(self, subject: str, seeds: list[int]) -> list[Image.Image]: ...

    def draw_front(self, subject: str, seeds: list[int]) -> list[Image.Image]: ...

    def draw_back(
        self, subject: str, front: Image.Image, seeds: list[int]
    ) -> list[Image.Image]: ...


def models_dir() -> Path:
    env = os.environ.get("FORGE_MODELS_DIR")
    if env:
        return Path(env)
    here = Path(__file__).resolve().parents[3]
    # worktrees (GitHub/asset-forge-wt/<topic>) share the main checkout's models/
    main = here.parent.parent / "asset-forge" / "models"
    return main if main.is_dir() else here / "models"


class SdxlDrawer:
    """Loads once, draws many. Records peak VRAM and seconds per image."""

    def __init__(
        self,
        steps: int = 24,
        guidance: float = 6.5,
    ):
        self.steps, self.guidance = steps, guidance
        self.pipe = None
        self.inpaint = None
        self.peak_vram_mb = 0.0
        self.timings: list[float] = []
        self.load_seconds = 0.0

    def _load(self) -> None:
        hub = models_dir() / "hf" / "hub"
        os.environ.setdefault("HF_HOME", str(models_dir() / "hf"))
        os.environ.setdefault("HF_HUB_CACHE", str(hub))
        import torch
        from diffusers import StableDiffusionXLPipeline
        from huggingface_hub import hf_hub_download

        t0 = time.perf_counter()
        pipe = StableDiffusionXLPipeline.from_pretrained(
            SDXL_REPO, torch_dtype=torch.float16, variant="fp16", cache_dir=str(hub)
        )
        pipe.load_lora_weights(hf_hub_download(LORA_REPO, LORA_FILE, cache_dir=str(hub)))
        pipe.to("cuda")
        pipe.vae.enable_slicing()
        pipe.set_progress_bar_config(disable=True)
        torch.cuda.reset_peak_memory_stats()
        self.pipe = pipe
        self.load_seconds = time.perf_counter() - t0

    def draw_front(self, subject: str, seeds: list[int]) -> list[Image.Image]:
        import torch

        if self.pipe is None:
            self._load()
        gens = [torch.Generator("cuda").manual_seed(s) for s in seeds]
        t0 = time.perf_counter()
        images = self.pipe(
            prompt=[FRONT_PROMPT.format(subject=subject)] * len(seeds),
            negative_prompt=[FRONT_NEGATIVE] * len(seeds),
            width=FRONT_SIZE,
            height=FRONT_SIZE,
            num_inference_steps=self.steps,
            guidance_scale=self.guidance,
            generator=gens,
        ).images
        self._tick(t0)
        return images

    def draw_back(self, subject: str, front: Image.Image, seeds: list[int]) -> list[Image.Image]:
        """Paint the back beside the front; returns the right-hand strip, one per seed."""
        import torch

        if self.pipe is None:
            self._load()
        if self.inpaint is None:
            from diffusers import StableDiffusionXLInpaintPipeline

            self.inpaint = StableDiffusionXLInpaintPipeline(**self.pipe.components)
            self.inpaint.set_progress_bar_config(disable=True)
        w = FRONT_SIZE + BACK_W
        bg = tuple(
            int(v)
            for v in np.median(np.asarray(front.convert("RGB"))[:8, :8].reshape(-1, 3), axis=0)
        )
        canvas = Image.new("RGB", (w, FRONT_SIZE), bg)
        canvas.paste(front.convert("RGB").resize((FRONT_SIZE, FRONT_SIZE)), (0, 0))
        mask = Image.new("L", (w, FRONT_SIZE), 0)
        mask.paste(255, (FRONT_SIZE, 0, w, FRONT_SIZE))
        gens = [torch.Generator("cuda").manual_seed(s) for s in seeds]
        t0 = time.perf_counter()
        out = self.inpaint(
            prompt=[BACK_PROMPT.format(subject=subject)] * len(seeds),
            negative_prompt=[BACK_NEGATIVE] * len(seeds),
            image=[canvas] * len(seeds),
            mask_image=[mask] * len(seeds),
            width=w,
            height=FRONT_SIZE,
            strength=0.99,
            num_inference_steps=BACK_STEPS,
            guidance_scale=self.guidance,
            generator=gens,
        ).images
        self._tick(t0)
        return [im.crop((FRONT_SIZE, 0, w, FRONT_SIZE)) for im in out]

    def _tick(self, t0: float) -> None:
        import torch

        torch.cuda.synchronize()
        self.timings.append(time.perf_counter() - t0)
        self.peak_vram_mb = max(self.peak_vram_mb, torch.cuda.max_memory_allocated() / 2**20)

    def draw_sheet(
        self, subject: str, seeds: list[int], prompt: str | None = None, size=None, negative=None
    ) -> list[Image.Image]:
        import torch

        if self.pipe is None:
            self._load()
        gens = [torch.Generator("cuda").manual_seed(s) for s in seeds]
        t0 = time.perf_counter()
        images = self.pipe(
            prompt=[(prompt or SHEET_PROMPT).format(subject=subject)] * len(seeds),
            negative_prompt=[negative or SHEET_NEGATIVE] * len(seeds),
            width=(size or (SHEET_W, SHEET_H))[0],
            height=(size or (SHEET_W, SHEET_H))[1],
            num_inference_steps=self.steps,
            guidance_scale=self.guidance,
            generator=gens,
        ).images
        torch.cuda.synchronize()
        self.timings.append(time.perf_counter() - t0)
        self.peak_vram_mb = max(self.peak_vram_mb, torch.cuda.max_memory_allocated() / 2**20)
        return images
