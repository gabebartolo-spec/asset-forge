"""TripoSG (MIT) adapter. Geometry only. Own RMBG-1.4 prep is NOT used (banned): our pre-matted RGBA
is composited on white and cropped/padded exactly as scripts/image_process.py does (alpha path)."""
import argparse, json, sys, time, traceback
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--inputs", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--src", required=True)
ap.add_argument("--seed", type=int, default=0)
a = ap.parse_args()
src = Path(a.src)
# adapter is named triposg.py and sys.path[0] is its folder: drop it so the repo package wins
sys.path = [p for p in sys.path if Path(p or ".").resolve() != Path(__file__).resolve().parent]
sys.path.insert(0, str(src))

import types
# diso is CC BY-NC 4.0 (banned). inference_utils imports it at module level but only the flash
# decoder uses it; stub it and use the repo's own non-diso hierarchical decoder + skimage marching cubes.
_d = types.ModuleType("diso")
_d.DiffDMC = None
sys.modules["diso"] = _d

import numpy as np, torch, trimesh
from PIL import Image

STEPS, GUIDANCE, NUM_TOKENS = 50, 7.0, 2048
WEIGHTS = src.parent.parent / "hf" / "triposg_weights"


def prep(path: Path) -> Image.Image:
    """Mirror image_process.load_image alpha branch: bbox of alpha>0, composite on white, pad 10%."""
    im = np.array(Image.open(path).convert("RGBA"))
    rgb = im[..., :3].astype(np.float32) / 255.0
    alpha = im[..., 3]
    ys, xs = np.where(alpha > 0)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    w, h = x1 - x0 + 1, y1 - y0 + 1
    al = (alpha.astype(np.float32) / 255.0)[..., None]
    comp = rgb * al + (1 - al)
    crop = comp[y0:y0 + h, x0:x0 + w]
    ratio = 0.1
    pad = [0] * 4  # left,right,top,bottom
    if w > h:
        pl = int(w * ratio); pt = int(pl + (w - h) / 2)
    else:
        pt = int(h * ratio); pl = int(pt + (h - w) / 2)
    pad = ((pt, pt), (pl, pl), (0, 0))
    crop = np.pad(crop, pad, mode="constant", constant_values=1.0)
    return Image.fromarray((crop * 255).astype(np.uint8))


def main():
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    from triposg.pipelines.pipeline_triposg import TripoSGPipeline
    pipe = TripoSGPipeline.from_pretrained(str(WEIGHTS)).to("cuda", torch.float16)
    load_s = time.time() - t0
    items = []
    for f in sorted(Path(a.inputs).glob("*.png")):
        pid = f.stem
        print(f"BEGIN {pid}", flush=True)
        item = {"id": pid, "mesh": None, "gen_s": None, "torch_peak_gb": None, "textured": False, "error": None}
        try:
            torch.cuda.reset_peak_memory_stats()
            t = time.time()
            img = prep(f)
            res = pipe(image=img, generator=torch.Generator(device="cuda").manual_seed(a.seed),
                       num_inference_steps=STEPS, guidance_scale=GUIDANCE, num_tokens=NUM_TOKENS,
                       use_flash_decoder=False, dense_octree_depth=8, hierarchical_octree_depth=9).samples[0]
            mesh = trimesh.Trimesh(res[0].astype(np.float32), np.ascontiguousarray(res[1]))
            torch.cuda.synchronize()
            item["gen_s"] = round(time.time() - t, 2)
            item["torch_peak_gb"] = round(torch.cuda.max_memory_allocated() / 2**30, 2)
            p = out / f"{pid}.glb"
            mesh.export(str(p))
            item["mesh"] = str(p)
            item["faces"] = int(len(mesh.faces))
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            item["error"] = repr(e)
        print(f"END {pid}", flush=True)
        items.append(item)
    settings = {"steps": STEPS, "guidance": GUIDANCE, "num_tokens": NUM_TOKENS, "dtype": "float16",
                "decoder": "hierarchical dense_octree_depth=8 hierarchical_octree_depth=9 + skimage lewiner MC (repo default is flash+diso, banned NC)",
                "bounds": 1.005, "prep": "own alpha-bbox crop, white bg, 10% pad, no RMBG", "simplify": False}
    (out / "results.json").write_text(json.dumps({"load_s": round(load_s, 2), "settings": settings, "items": items}, indent=2))

main()
