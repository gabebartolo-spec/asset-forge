"""Runs inside models/envs/sdxl: reads one JSON job on stdin ({src, out, revision}), writes the
picture back as an RGBA PNG with the background cut away (BiRefNet), then exits so the GPU memory
is freed. BiRefNet is MIT (docs/LICENCES.md); its code is loaded from the pinned, locally cached
revision only (HF_HUB_OFFLINE=1 is set by the caller)."""

from __future__ import annotations

import json
import sys

SIDE = 1024
MEAN = (0.485, 0.456, 0.406)
STD = (0.229, 0.224, 0.225)


def main() -> None:
    job = json.load(sys.stdin)
    import numpy as np
    import torch
    from PIL import Image
    from transformers import AutoModelForImageSegmentation

    model = AutoModelForImageSegmentation.from_pretrained(
        "ZhengPeng7/BiRefNet", revision=job["revision"], trust_remote_code=True)
    model.to("cuda").half().eval()
    img = Image.open(job["src"]).convert("RGB")
    x = np.asarray(img.resize((SIDE, SIDE), Image.BICUBIC), dtype=np.float32) / 255.0
    x = (x - np.array(MEAN, dtype=np.float32)) / np.array(STD, dtype=np.float32)
    batch = torch.from_numpy(x).permute(2, 0, 1).unsqueeze(0).half().to("cuda")
    torch.cuda.reset_peak_memory_stats()
    with torch.no_grad():
        mask = model(batch)[-1].sigmoid().float().cpu()[0, 0].numpy()
    alpha = Image.fromarray((mask * 255).clip(0, 255).astype("uint8"))
    alpha = alpha.resize(img.size, Image.BILINEAR)
    out = img.convert("RGBA")
    out.putalpha(alpha)
    out.save(job["out"])
    print(json.dumps({"peak_vram_mb": round(torch.cuda.max_memory_allocated() / 2**20)}))


if __name__ == "__main__":
    main()
