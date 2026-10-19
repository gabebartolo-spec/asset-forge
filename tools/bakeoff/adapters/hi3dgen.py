"""Hi3DGen / Stable3DGen adapter (MIT). Geometry only. See run_candidate.py for the contract.

Pipeline: matted RGBA -> StableNormal turbo (yoso-normal-v1-8-1, normal map, uses the alpha as mask,
no BiRefNet) -> Hi3DGen (trellis-normal-v0-1: sparse structure flow, SLat flow, mesh decoder) -> mesh.
Weights resolve through HF_HOME; DINOv2 (Apache-2.0) comes from a local copy of facebookresearch/dinov2
placed in the torch hub dir, so nothing is fetched from GitHub at run time.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

os.environ.setdefault("SPCONV_ALGO", "native")
os.environ.setdefault("ATTN_BACKEND", "xformers")

def _dll_dirs() -> None:
    """spconv/cumm (cu126 wheel) wants cudart64_12 + nvrtc64_120_0: use the pip nvidia-*-cu12 runtime copies."""
    if os.name != "nt":
        return
    base = Path(sys.executable).parent.parent / "Lib" / "site-packages" / "nvidia"
    for d in ("cuda_runtime", "cuda_nvrtc"):
        p = base / d / "bin"
        if p.exists():
            os.add_dll_directory(str(p))
            os.environ["PATH"] = str(p) + os.pathsep + os.environ["PATH"]


SETTINGS = {
    "normal_model": "Stable-X/yoso-normal-v1-8-1 (StableNormal turbo, fp16)",
    "normal_resolution": 768,
    "preprocess_resolution": 1024,
    "ss_steps": 50, "ss_cfg": 3.0,
    "slat_steps": 6, "slat_cfg": 3.0,
    "gen_model": "Stable-X/trellis-normal-v0-1",
    "precision": "fp16 checkpoints",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--src", required=True)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    src = Path(a.src)
    models = src.parent
    sys.path.insert(0, str(src))
    sys.path.insert(0, str(models / "stablenormal_hub"))

    _dll_dirs()
    import numpy as np
    import torch
    from PIL import Image
    from huggingface_hub import snapshot_download

    t0 = time.time()
    hub = Path(os.environ.get("HF_HOME", models / "hf")) / "torchhub"
    hub.mkdir(parents=True, exist_ok=True)
    torch.hub.set_dir(str(hub))
    dino = hub / "facebookresearch_dinov2_main"
    if not dino.exists():
        shutil.copytree(models / "dinov2_hub", dino, ignore=shutil.ignore_patterns(".git"))

    import hi3dgen.pipelines.hi3dgen as hp
    hp.os = os  # upstream forgets this import; without it the local DINOv2 lookup is skipped
    from hi3dgen.pipelines import Hi3DGenPipeline
    from nirne.pipeline_yoso_normal import YOSONormalsPipeline

    gen_path = snapshot_download("Stable-X/trellis-normal-v0-1")
    nrm_path = snapshot_download("Stable-X/yoso-normal-v1-8-1")
    import gc
    # 12 GB fit: Hi3DGen stays on CPU, only the active sub-model is on the GPU; StableNormal runs first
    # for every input and is freed before Hi3DGen touches the GPU. Same steps/cfg/resolution as before.
    Hi3DGenPipeline.device = property(lambda self: torch.device("cuda"))
    pipe = Hi3DGenPipeline.from_pretrained(gen_path)
    pipe.cpu()

    def on_gpu(*names: str) -> None:
        for k, m in pipe.models.items():
            m.to("cuda" if k in names else "cpu")
        gc.collect()
        torch.cuda.empty_cache()

    nrm = YOSONormalsPipeline.from_pretrained(
        nrm_path, trust_remote_code=True, variant="fp16", torch_dtype=torch.float16, t_start=0
    ).to("cuda:0")
    import hubconf  # StableNormal's Predictor wrapper (RGBA alpha as mask)
    normal_predictor = hubconf.Predictor(nrm, yoso_version="yoso-normal-v1-8-1")
    normal_predictor.segmentation_handler.device = "cuda"
    load_s = time.time() - t0

    out = Path(a.out)
    items = []
    normals = {}
    nrm_peak = 0.0
    for f in sorted(Path(a.inputs).glob("*.png")):
        pid = f.stem
        t1 = time.time()
        try:
            torch.cuda.reset_peak_memory_stats()
            img = Image.open(f).convert("RGBA")
            img = pipe.preprocess_image(img, resolution=SETTINGS["preprocess_resolution"])
            normal = normal_predictor(img, resolution=SETTINGS["normal_resolution"],
                                      match_input_resolution=True, data_type="object")
            normal.save(out / f"{pid}_normal.png")
            normals[pid] = (normal, time.time() - t1, None)
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            normals[pid] = (None, time.time() - t1, f"{type(e).__name__}: {e}")
        nrm_peak = max(nrm_peak, torch.cuda.max_memory_allocated() / 2**30)
    del normal_predictor, nrm
    gc.collect()
    torch.cuda.empty_cache()

    for pid, (normal, normal_s, err) in normals.items():
        item = {"id": pid, "mesh": None, "gen_s": None, "torch_peak_gb": None, "textured": False, "error": err}
        print(f"BEGIN {pid}", flush=True)
        t1 = time.time()
        try:
            if err:
                raise RuntimeError(err)
            torch.cuda.reset_peak_memory_stats()
            with torch.no_grad():
                on_gpu("image_cond_model")
                cond = pipe.get_cond([normal])
                torch.manual_seed(a.seed)
                on_gpu("sparse_structure_flow_model")
                z_s = None
                flow = pipe.models["sparse_structure_flow_model"]
                noise = torch.randn(1, flow.in_channels, flow.resolution, flow.resolution, flow.resolution).cuda()
                z_s = pipe.sparse_structure_sampler.sample(
                    flow, noise, **cond,
                    **{**pipe.sparse_structure_sampler_params, "steps": SETTINGS["ss_steps"], "cfg_strength": SETTINGS["ss_cfg"]},
                    verbose=True)["samples"]
                on_gpu("sparse_structure_decoder")
                coords = torch.argwhere(pipe.models["sparse_structure_decoder"](z_s) > 0)[:, [0, 2, 3, 4]].int()
                del z_s, noise
                on_gpu("slat_flow_model")
                slat = pipe.sample_slat(cond, coords, {"steps": SETTINGS["slat_steps"], "cfg_strength": SETTINGS["slat_cfg"]})
                on_gpu("slat_decoder_mesh")
                res = pipe.decode_slat(slat, ["mesh"])
            tm = res["mesh"][0].to_trimesh(transform_pose=True)
            path = out / f"{pid}.glb"
            tm.export(path)
            item["mesh"] = path.name
            item["faces"] = int(len(tm.faces))
            torch.cuda.synchronize()
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            item["error"] = f"{type(e).__name__}: {e}"
        item["gen_s"] = round(time.time() - t1 + normal_s, 2)
        item["torch_peak_gb"] = round(max(torch.cuda.max_memory_allocated() / 2**30, nrm_peak), 2)
        print(f"END {pid}", flush=True)
        items.append(item)
        (out / "results.json").write_text(json.dumps(
            {"load_s": round(load_s, 2), "settings": SETTINGS, "items": items}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
