"""Step 2 Clean colour, method B: six views of the model painted from the reference picture by
MV-Adapter (image + geometry conditioned, SDXL). clean.py renders the control maps (position and
normal per view, in MV-Adapter's camera frame) and calls this script in the generator env:

    python -m asset_forge.multiview CONTROL.npz REF.png OUT_DIR --mv-src DIR [--seed N]

CONTROL.npz holds `pos` and `normal` (6, 768, 768, 3) float32, already mapped to 0..1 with the
0.5 background MV-Adapter was trained on. Writes OUT_DIR/view_<k>.png (768 px, view order as in
clean.py MV_VIEWS) and OUT_DIR/multiview.json (seconds, peak VRAM, seed, steps).

Licences (docs/LICENCES.md): MV-Adapter code and weights Apache-2.0, SDXL base 1.0 OpenRAIL++,
VAE madebyollin/sdxl-vae-fp16-fix MIT. MV-Adapter's own mesh renderer (nvdiffrast) is never
imported: the control maps come from clean.py.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

SIZE = 768
STEPS = 50
GUIDANCE = 3.0
SEED = 7
FP8_UNET = True
VRAM_CAP_GB = 11.0
PROMPT = "high quality"
NEGATIVE = "watermark, ugly, deformed, noisy, blurry, low contrast"
BASE = "stabilityai/stable-diffusion-xl-base-1.0"
VAE = "madebyollin/sdxl-vae-fp16-fix"
ADAPTER = "huanngzh/mv-adapter"
ADAPTER_FILE = "mvadapter_ig2mv_sdxl.safetensors"


def prepare_reference(rgba, size=SIZE):
    """MV-Adapter's reference layout: crop to the alpha box, longest side 0.9 x size, centred on a
    0.5 grey background. rgba: (h, w, 4) uint8. Returns (size, size, 3) uint8."""
    import numpy as np

    alpha = rgba[..., 3] > 0
    ys, xs = np.nonzero(alpha)
    y0, y1 = max(ys.min() - 1, 0), min(ys.max() + 1, rgba.shape[0])
    x0, x1 = max(xs.min() - 1, 0), min(xs.max() + 1, rgba.shape[1])
    crop = rgba[y0:y1, x0:x1]
    h, w = crop.shape[:2]
    if h > w:
        nh, nw = int(size * 0.9), max(int(w * size * 0.9 / h), 1)
    else:
        nh, nw = max(int(h * size * 0.9 / w), 1), int(size * 0.9)
    from PIL import Image

    crop = np.asarray(Image.fromarray(crop).resize((nw, nh), Image.LANCZOS))
    out = np.zeros((size, size, 4), np.uint8)
    sh, sw = (size - nh) // 2, (size - nw) // 2
    out[sh:sh + nh, sw:sw + nw] = crop
    f = out.astype(np.float32) / 255.0
    rgb = f[..., :3] * f[..., 3:] + (1 - f[..., 3:]) * 0.5
    return (rgb * 255).clip(0, 255).astype(np.uint8)


def _drop_reference_copy(module, args, kwargs):
    """MV-Adapter's pipeline keeps two copies of the reference-attention cache (~2.6 GB at 768 px,
    six views, guidance on): its local dict and the clone it hands to the denoiser. On the first
    denoising call the local one is emptied, so only the clone in use stays on the card."""
    import inspect

    cache = (kwargs.get("cross_attention_kwargs") or {}).get("ref_hidden_states")
    if not cache:
        return None
    for f in inspect.stack()[1:12]:
        local = f.frame.f_locals.get("ref_hidden_states")
        if isinstance(local, dict) and local is not cache and local:
            local.clear()
            break
    return None


def run(control, ref_png, out_dir, mv_src, seed=SEED, steps=STEPS):
    sys.path.insert(0, str(mv_src))
    import numpy as np
    import torch
    from diffusers import AutoencoderKL
    from mvadapter.models.attention_processor import DecoupledMVRowColSelfAttnProcessor2_0
    from mvadapter.pipelines.pipeline_mvadapter_i2mv_sdxl import MVAdapterI2MVSDXLPipeline
    from mvadapter.schedulers.scheduling_shift_snr import ShiftSNRScheduler
    from PIL import Image

    t0 = time.perf_counter()
    # cap this process below the card's 12 GB: the allocator frees its cache instead of growing
    # into shared system memory (which runs ~10x slower); measured peak in use is ~10.2 GB
    total = torch.cuda.get_device_properties(0).total_memory / 2**30
    torch.cuda.set_per_process_memory_fraction(min(VRAM_CAP_GB / total, 1.0))
    torch.cuda.reset_peak_memory_stats()
    dtype = torch.float16
    pipe = MVAdapterI2MVSDXLPipeline.from_pretrained(
        BASE, vae=AutoencoderKL.from_pretrained(VAE, torch_dtype=dtype), torch_dtype=dtype,
        variant="fp16")
    pipe.scheduler = ShiftSNRScheduler.from_scheduler(
        pipe.scheduler, shift_mode="interpolated", shift_scale=8.0, scheduler_class=None)
    pipe.init_custom_adapter(num_views=6, self_attn_processor=DecoupledMVRowColSelfAttnProcessor2_0)
    pipe.load_custom_adapter(ADAPTER, weight_name=ADAPTER_FILE)
    # 12 GB card: the text encoders run first and leave the GPU before denoising. (accelerate's
    # enable_model_cpu_offload cannot be used: its hooks copy the reference-attention cache dict
    # on every call, which silently empties it - KeyError on the first denoising step.)
    pipe.to(dtype=dtype)
    pipe.text_encoder.to("cuda")
    pipe.text_encoder_2.to("cuda")
    with torch.no_grad():
        pe, npe, ppe, nppe = pipe.encode_prompt(
            prompt=PROMPT, device="cuda", num_images_per_prompt=1,
            do_classifier_free_guidance=True, negative_prompt=NEGATIVE)
    pipe.text_encoder.to("cpu")
    pipe.text_encoder_2.to("cpu")
    pipe.text_encoder, pipe.text_encoder_2 = None, None
    torch.cuda.empty_cache()
    if FP8_UNET:  # weights stored in fp8, computed in fp16: the denoiser fits a 12 GB card
        pipe.unet.enable_layerwise_casting(storage_dtype=torch.float8_e4m3fn,
                                           compute_dtype=dtype)
    pipe.unet.to("cuda")
    pipe.unet.register_forward_pre_hook(_drop_reference_copy, with_kwargs=True)
    pipe.vae.to("cuda")
    pipe.cond_encoder.to(device="cuda", dtype=dtype)
    vram_weights = torch.cuda.memory_allocated() / 2**30
    pipe.vae.enable_slicing()
    t_load = time.perf_counter() - t0

    d = np.load(control)
    ctrl = np.concatenate([d["pos"], d["normal"]], axis=-1)  # (6, H, W, 6)
    ctrl = torch.from_numpy(ctrl).permute(0, 3, 1, 2).to("cuda", dtype)
    ref = Image.fromarray(prepare_reference(np.asarray(Image.open(ref_png).convert("RGBA"))))
    t1 = time.perf_counter()
    latents = pipe(
        prompt=None, prompt_embeds=pe, negative_prompt_embeds=npe, pooled_prompt_embeds=ppe,
        negative_pooled_prompt_embeds=nppe, height=SIZE, width=SIZE, num_inference_steps=steps,
        guidance_scale=GUIDANCE,
        num_images_per_prompt=6, control_image=ctrl, control_conditioning_scale=1.0,
        reference_image=ref, reference_conditioning_scale=1.0,
        cross_attention_kwargs={"scale": 1.0},
        generator=torch.Generator(device="cuda").manual_seed(seed), output_type="latent",
    ).images
    # decode one view at a time after the denoiser's caches are freed (peak stays under 12 GB)
    torch.cuda.empty_cache()
    images = []
    with torch.no_grad():
        for lat in latents:
            x = pipe.vae.decode(lat[None] / pipe.vae.config.scaling_factor).sample[0]
            x = (x / 2 + 0.5).clamp(0, 1).permute(1, 2, 0).float().cpu().numpy()
            images.append(Image.fromarray((x * 255).round().astype(np.uint8)))
    t_gen = time.perf_counter() - t1
    out_dir.mkdir(parents=True, exist_ok=True)
    for k, im in enumerate(images):
        im.save(out_dir / f"view_{k}.png")
    ref.save(out_dir / "reference_768.png")
    info = {"seconds_load": round(t_load, 1), "seconds_generate": round(t_gen, 1),
            "seconds_total": round(time.perf_counter() - t0, 1),
            "vram_peak_gb": round(torch.cuda.max_memory_allocated() / 2**30, 2),
            "vram_reserved_peak_gb": round(torch.cuda.max_memory_reserved() / 2**30, 2),
            "vram_weights_gb": round(vram_weights, 2), "vram_cap_gb": VRAM_CAP_GB,
            "seed": seed, "steps": steps, "guidance": GUIDANCE, "size": SIZE,
            "adapter": f"{ADAPTER}/{ADAPTER_FILE}", "base": BASE, "vae": VAE}
    (out_dir / "multiview.json").write_text(json.dumps(info, indent=1))
    print("MULTIVIEW", json.dumps(info))
    return info


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("control", type=Path)
    ap.add_argument("ref", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--mv-src", type=Path, required=True)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--steps", type=int, default=STEPS)
    a = ap.parse_args(argv)
    run(a.control, a.ref, a.out, a.mv_src, a.seed, a.steps)


if __name__ == "__main__":
    main()
