"""The draw step: local SDXL 1.0 base + the pixel-art-xl LoRA (both CLEARED in LICENCES.md).

Run inside the SDXL env (models/envs/sdxl: diffusers, torch, peft). Weights live under
models/hf. Never Stability Matrix's ComfyUI. Tests use a fake Drawer instead.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Protocol

from PIL import Image, ImageFilter

SDXL_REPO = "stabilityai/stable-diffusion-xl-base-1.0"
LORA_REPO = "nerijs/pixel-art-xl"
LORA_FILE = "pixel-art-xl.safetensors"

# The back is drawn from a blurred copy of the front: it keeps the colours and the body mass but
# not the face, so the model turns the creature round instead of copying the front (art-QA fix 6).
BACK_STRENGTH = 0.9
BACK_BLUR = 20
BACK_STEPS = 20

STYLE = (
    "pixel art, flat colours, clean pixels, full body, centred, "
    "plain white background, no shadow, no ground, a single creature, solo"
)
VIEW_PROMPTS = {
    "front": "{subject}, three-quarter view from the front, head turned toward the viewer, "
    "both eyes visible, looking at the camera, " + STYLE,
    "back": "pixel art, one single sprite of {subject} seen from behind, rear view, back of the "
    "body and tail visible, facing away from the viewer, no face, battle sprite, plain "
    "background, no shadow",
}
_BAD = "blurry, smooth, gradient, photo, 3d render, text, watermark, cropped, scenery, plants, "
_BAD += "shadow, ground, floor, multiple creatures, sprite sheet, collage, group, many, top view"
NEGATIVE = {
    "front": "side view, profile, facing left, facing right, from the side, " + _BAD,
    "back": "face, eyes, mouth, front view, facing the viewer, side view, profile, " + _BAD,
}


class Drawer(Protocol):
    """`draw_batch` makes one image per seed in one call. With `init` (the accepted front) the
    back is drawn from it (img2img), so it stays the same creature."""

    def draw_batch(
        self, subject: str, view: str, seeds: list[int], init: Image.Image | None = None
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
        size: int = 1024,
        strength: float = BACK_STRENGTH,
    ):
        self.steps, self.guidance, self.size, self.strength = steps, guidance, size, strength
        self.pipe = None
        self.img2img = None
        self.peak_vram_mb = 0.0
        self.timings: list[float] = []
        self.load_seconds = 0.0

    def _load(self) -> None:
        hub = models_dir() / "hf" / "hub"
        os.environ.setdefault("HF_HOME", str(models_dir() / "hf"))
        os.environ.setdefault("HF_HUB_CACHE", str(hub))
        import torch
        from diffusers import StableDiffusionXLImg2ImgPipeline, StableDiffusionXLPipeline
        from huggingface_hub import hf_hub_download

        t0 = time.perf_counter()
        pipe = StableDiffusionXLPipeline.from_pretrained(
            SDXL_REPO, torch_dtype=torch.float16, variant="fp16", cache_dir=str(hub)
        )
        pipe.load_lora_weights(hf_hub_download(LORA_REPO, LORA_FILE, cache_dir=str(hub)))
        pipe.to("cuda")
        pipe.vae.enable_slicing()
        self.img2img = StableDiffusionXLImg2ImgPipeline(**pipe.components)  # shares the weights
        self.img2img.set_progress_bar_config(disable=True)
        pipe.set_progress_bar_config(disable=True)
        torch.cuda.reset_peak_memory_stats()
        self.pipe = pipe
        self.load_seconds = time.perf_counter() - t0

    def draw_batch(
        self, subject: str, view: str, seeds: list[int], init: Image.Image | None = None
    ) -> list[Image.Image]:
        import torch

        if self.pipe is None:
            self._load()
        gens = [torch.Generator("cuda").manual_seed(s) for s in seeds]
        t0 = time.perf_counter()
        common = {
            "prompt": [VIEW_PROMPTS[view].format(subject=subject)] * len(seeds),
            "negative_prompt": [NEGATIVE[view]] * len(seeds),
            "num_inference_steps": self.steps,
            "guidance_scale": self.guidance,
            "generator": gens,
        }
        if init is None:
            images = self.pipe(width=self.size, height=self.size, **common).images
        else:
            start = init.convert("RGB").resize((self.size, self.size))
            start = start.filter(ImageFilter.GaussianBlur(BACK_BLUR))
            common["num_inference_steps"] = BACK_STEPS
            images = self.img2img(image=start, strength=self.strength, **common).images
        torch.cuda.synchronize()
        self.timings.append(time.perf_counter() - t0)
        self.peak_vram_mb = max(self.peak_vram_mb, torch.cuda.max_memory_allocated() / 2**20)
        return images
