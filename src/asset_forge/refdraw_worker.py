"""Runs inside models/envs/sdxl: reads one JSON job on stdin, writes one PNG, then exits so the
GPU memory is freed. Job: prompt, negative, seed, steps, guidance, out."""

from __future__ import annotations

import json
import sys


def main() -> None:
    job = json.load(sys.stdin)
    import torch
    from diffusers import StableDiffusionXLPipeline

    pipe = StableDiffusionXLPipeline.from_pretrained(
        "stabilityai/stable-diffusion-xl-base-1.0", torch_dtype=torch.float16, variant="fp16",
        use_safetensors=True).to("cuda")
    pipe.set_progress_bar_config(disable=True)
    torch.cuda.reset_peak_memory_stats()
    image = pipe(prompt=job["prompt"], negative_prompt=job["negative"],
                 num_inference_steps=job["steps"], guidance_scale=job["guidance"],
                 width=1024, height=1024,
                 generator=torch.Generator("cuda").manual_seed(job["seed"])).images[0]
    image.save(job["out"])
    print(json.dumps({"peak_vram_mb": round(torch.cuda.max_memory_allocated() / 2**20)}))


if __name__ == "__main__":
    main()
