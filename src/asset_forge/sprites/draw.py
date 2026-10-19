"""The draw step: local SDXL 1.0 base + the pixel-art-xl LoRA (both CLEARED in LICENCES.md).

Run inside the SDXL env (models/envs/sdxl: diffusers, torch, peft). Weights live under
models/hf. Never Stability Matrix's ComfyUI. Tests use a fake Drawer instead.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Protocol

from PIL import Image

SDXL_REPO = "stabilityai/stable-diffusion-xl-base-1.0"
LORA_REPO = "nerijs/pixel-art-xl"
LORA_FILE = "pixel-art-xl.safetensors"

STYLE = "pixel art, flat colours, clean pixels, full body, centred, plain white background"
VIEW_PROMPTS = {
    "front": "{subject}, three-quarter front view, facing the viewer, face and eyes visible, "
    + STYLE,
    "back": (
        "{subject}, seen from directly behind, rear view, turned away from the viewer, "
        "showing its back and rump and tail, head turned away, face hidden, " + STYLE
    ),
}
NEGATIVE = {
    "front": "blurry, smooth, gradient, photo, 3d render, text, watermark, cropped, scenery",
    "back": (
        "face, eyes, mouth, front view, facing the viewer, blurry, smooth, gradient, photo, "
        "3d render, text, watermark, cropped, scenery"
    ),
}


class Drawer(Protocol):
    def draw(self, subject: str, view: str, seed: int) -> Image.Image: ...


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

    def __init__(self, steps: int = 24, guidance: float = 6.5, size: int = 1024):
        self.steps, self.guidance, self.size = steps, guidance, size
        self.pipe = None
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
        pipe.set_progress_bar_config(disable=True)
        torch.cuda.reset_peak_memory_stats()
        self.pipe = pipe
        self.load_seconds = time.perf_counter() - t0

    def draw(self, subject: str, view: str, seed: int) -> Image.Image:
        import torch

        if self.pipe is None:
            self._load()
        gen = torch.Generator("cuda").manual_seed(seed)
        t0 = time.perf_counter()
        image = self.pipe(
            prompt=VIEW_PROMPTS[view].format(subject=subject),
            negative_prompt=NEGATIVE[view],
            num_inference_steps=self.steps,
            guidance_scale=self.guidance,
            width=self.size,
            height=self.size,
            generator=gen,
        ).images[0]
        self.timings.append(time.perf_counter() - t0)
        self.peak_vram_mb = max(self.peak_vram_mb, torch.cuda.max_memory_allocated() / 2**20)
        return image
