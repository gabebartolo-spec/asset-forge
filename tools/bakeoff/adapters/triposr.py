"""TripoSR (MIT) adapter. Matted RGBA in -> resize_foreground(0.85) -> grey 0.5 composite -> GLB with vertex colours.

rembg is never imported (inputs are already matted). The repo's torchmcubes is used if importable
(CUDA build); otherwise a skimage shim is injected (see results.json settings.marching_cubes).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import types
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--inputs", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--src", required=True)
ap.add_argument("--seed", type=int, default=0)
ap.add_argument("--mc-resolution", type=int, default=256)
ap.add_argument("--foreground-ratio", type=float, default=0.85)
args = ap.parse_args()
sys.path.insert(0, args.src)

import numpy as np  # noqa: E402
import torch  # noqa: E402
from PIL import Image  # noqa: E402

mc_backend = "torchmcubes"
try:
    import torchmcubes  # noqa: F401
except Exception:  # noqa: BLE001
    from skimage import measure

    def marching_cubes(vol, thresh):
        v = vol.detach().cpu().numpy()
        verts, faces, _, _ = measure.marching_cubes(v, float(thresh))
        # torchmcubes returns verts in reversed axis order relative to skimage's index order
        verts = verts[:, ::-1].copy()
        return torch.from_numpy(verts).float(), torch.from_numpy(faces.astype(np.int64)[:, ::-1].copy())

    shim = types.ModuleType("torchmcubes")
    shim.marching_cubes = marching_cubes
    sys.modules["torchmcubes"] = shim
    mc_backend = "skimage.measure.marching_cubes (shim, CPU)"

sys.modules.setdefault("rembg", types.ModuleType("rembg"))  # tsr.utils imports it at top level; never called
from tsr.system import TSR  # noqa: E402
from tsr.utils import resize_foreground  # noqa: E402

out = Path(args.out)
out.mkdir(parents=True, exist_ok=True)
torch.manual_seed(args.seed)
dev = "cuda:0"

t0 = time.time()
model = TSR.from_pretrained("stabilityai/TripoSR", config_name="config.yaml", weight_name="model.ckpt")
model.renderer.set_chunk_size(8192)
model.to(dev)
load_s = time.time() - t0

items = []
for png in sorted(Path(args.inputs).glob("*.png")):
    pid = png.stem
    item = {"id": pid, "mesh": None, "gen_s": None, "torch_peak_gb": None, "textured": True, "error": None}
    print(f"BEGIN {pid}", flush=True)
    try:
        torch.cuda.reset_peak_memory_stats()
        t1 = time.time()
        im = resize_foreground(Image.open(png).convert("RGBA"), args.foreground_ratio)
        a = np.array(im).astype(np.float32) / 255.0
        a = a[:, :, :3] * a[:, :, 3:4] + (1 - a[:, :, 3:4]) * 0.5
        im = Image.fromarray((a * 255.0).astype(np.uint8))
        with torch.no_grad():
            codes = model([im], device=dev)
            mesh = model.extract_mesh(codes, True, resolution=args.mc_resolution)[0]
        torch.cuda.synchronize()
        item["gen_s"] = round(time.time() - t1, 2)
        item["torch_peak_gb"] = round(torch.cuda.max_memory_allocated() / 2**30, 2)
        p = out / f"{pid}.glb"
        mesh.export(str(p))
        item["mesh"] = str(p)
        item["faces"] = int(len(mesh.faces))
    except Exception as e:  # noqa: BLE001
        item["error"] = f"{type(e).__name__}: {e}"
    print(f"END {pid}", flush=True)
    items.append(item)

settings = {"mc_resolution": args.mc_resolution, "foreground_ratio": args.foreground_ratio,
            "bg_grey": 0.5, "chunk_size": 8192, "marching_cubes": mc_backend, "threshold": 25.0,
            "rembg": False, "texture": "vertex colours (no bake)", "precision": "fp32", "seed": args.seed}
(out / "results.json").write_text(json.dumps({"load_s": round(load_s, 2), "settings": settings, "items": items}, indent=1))
