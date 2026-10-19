"""Draw and matte the bake-off reference candidates (SDXL base 1.0 + BiRefNet).

    python tools/bakeoff/gpu_lock.py run sdxl -- models/envs/sdxl/Scripts/python.exe tools/bakeoff/make_refs.py [--only fox] [--seeds 8]

Writes models/bakeoff/ref_candidates/<id>_s<seed>.png, <id>_s<seed>_rgba.png, <id>_sheet.png and
timing.json. The lead picks the final refs (models/bakeoff/refs/<id>.png); this script does not.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import tomllib
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from gpu_lock import _models_dir  # noqa: E402

MODELS = _models_dir()
os.environ.setdefault("HF_HOME", str(MODELS / "hf"))

import torch  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

SDXL = "stabilityai/stable-diffusion-xl-base-1.0"
BIREFNET = "ZhengPeng7/BiRefNet"
BIREFNET_REV = "e2bf8e4460fc8fa32bba5ea4d94b3233d367b0e4"  # trust_remote_code: pinned


def matte(model, img: Image.Image) -> Image.Image:
    import numpy as np
    from torchvision import transforms

    tf = transforms.Compose([
        transforms.Resize((1024, 1024)), transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])])
    x = tf(img.convert("RGB")).unsqueeze(0).cuda().half()
    with torch.no_grad():
        pred = model(x)[-1].sigmoid().float().cpu()[0, 0]
    mask = Image.fromarray((pred.numpy() * 255).astype("uint8")).resize(img.size, Image.BILINEAR)
    rgba = img.convert("RGBA")
    rgba.putalpha(mask)
    a = np.array(mask)
    ys, xs = np.where(a > 20)
    if len(xs) == 0:
        return rgba
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    w, h = x1 - x0, y1 - y0
    side = int(max(w, h) * 1.2)  # ~10% margin each side, square
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(rgba.crop((x0, y0, x1, y1)), (side // 2 - w // 2, side // 2 - h // 2))
    return canvas.resize((1024, 1024), Image.LANCZOS)


def sheet(pid: str, tiles: list[tuple[int, Image.Image]], out: Path) -> None:
    t = 384
    s = Image.new("RGB", (4 * t, 2 * t), "white")
    d = ImageDraw.Draw(s)
    try:
        font = ImageFont.truetype("arial.ttf", 28)
    except OSError:
        font = ImageFont.load_default()
    for i, (seed, im) in enumerate(tiles):
        s.paste(im.convert("RGB").resize((t, t), Image.LANCZOS), ((i % 4) * t, (i // 4) * t))
        d.text(((i % 4) * t + 8, (i // 4) * t + 6), f"{pid} s{seed}", fill="red", font=font)
    s.save(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--seed-start", type=int, default=0)
    ap.add_argument("--text", default="", help="override the prompt text (single --only id)")
    ap.add_argument("--tag", default="", help="suffix for the sheet file name")
    ap.add_argument("--steps", type=int, default=30)
    ap.add_argument("--cfg", type=float, default=6.0)
    args = ap.parse_args()

    cfg = tomllib.loads((HERE / "prompts.toml").read_text(encoding="utf-8"))
    prompts = cfg["prompt"]
    if args.only:
        prompts = [p for p in prompts if p["id"] in args.only.split(",")]
    if args.text:
        assert len(prompts) == 1, "--text needs exactly one --only id"
        prompts[0] = {**prompts[0], "text": args.text}
    out = MODELS / "bakeoff" / "ref_candidates"
    out.mkdir(parents=True, exist_ok=True)

    from diffusers import StableDiffusionXLPipeline
    from transformers import AutoModelForImageSegmentation

    timing: dict = {"settings": {"model": SDXL, "matte": BIREFNET, "steps": args.steps,
                                 "cfg": args.cfg, "size": 1024, "dtype": "fp16",
                                 "text_override": args.text}, "items": []}
    t0 = time.time()
    pipe = StableDiffusionXLPipeline.from_pretrained(
        SDXL, torch_dtype=torch.float16, variant="fp16", use_safetensors=True).to("cuda")
    bire = AutoModelForImageSegmentation.from_pretrained(BIREFNET, revision=BIREFNET_REV,
                                                        trust_remote_code=True)
    bire = bire.half().cuda().eval()
    timing["load_s"] = round(time.time() - t0, 1)
    print("load_s", timing["load_s"], flush=True)

    for p in prompts:
        tiles = []
        for seed in range(args.seed_start, args.seed_start + args.seeds):
            torch.cuda.reset_peak_memory_stats()
            t1 = time.time()
            g = torch.Generator("cuda").manual_seed(seed)
            img = pipe(prompt=f"{p['text']}, {cfg['style']}", negative_prompt=cfg["negative"],
                       num_inference_steps=args.steps, guidance_scale=args.cfg,
                       width=1024, height=1024, generator=g).images[0]
            torch.cuda.synchronize()
            gen_s = time.time() - t1
            img.save(out / f"{p['id']}_s{seed}.png")
            t2 = time.time()
            rgba = matte(bire, img)
            rgba.save(out / f"{p['id']}_s{seed}_rgba.png")
            matte_s = time.time() - t2
            peak = torch.cuda.max_memory_allocated() / 2**30
            tiles.append((seed, rgba_on_white(rgba)))
            timing["items"].append({"id": p["id"], "seed": seed, "gen_s": round(gen_s, 2),
                                    "matte_s": round(matte_s, 2), "torch_peak_gb": round(peak, 2)})
            print(f"{p['id']} s{seed} gen {gen_s:.1f}s matte {matte_s:.1f}s peak {peak:.2f} GB",
                  flush=True)
        sheet(p["id"], tiles, out / f"{p['id']}{args.tag}_sheet.png")
        (out / f"timing{args.tag}.json").write_text(json.dumps(timing, indent=2))
    return 0


def rgba_on_white(im: Image.Image) -> Image.Image:
    bg = Image.new("RGBA", im.size, "white")
    return Image.alpha_composite(bg, im)


if __name__ == "__main__":
    sys.exit(main())
