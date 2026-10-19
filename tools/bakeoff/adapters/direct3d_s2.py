"""Direct3D-S2 adapter (MIT code; weights wushuang98/Direct3D-S2, subfolder direct3d-s2-v-1-1).

Windows port notes:
  * torchsparse built locally (MSVC + CUDA 13.4), sparsehash replaced by a std::unordered_map shim.
  * flash_attn has no Windows build for torch 2.14 / cu130: replaced here by a small torch-SDPA shim
    (same maths, incl. softmax lse for the compressed-attention branch).
  * Remesh/simplify is OFF, so the GPL pymeshfix / pyvista / igraph / utils3d fill-hole imports are
    stubbed and never installed.
  * The model's own background removal (BiRefNet) is never used: inputs are RGBA, already matted.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
import types
from pathlib import Path

import torch
import torch.nn.functional as F


def install_flash_attn_shim() -> None:
    def _expand(k, h):
        return k if k.shape[-2] == h else k.repeat_interleave(h // k.shape[-2], dim=-2)

    def flash_attn_func(q, k, v, **kw):  # [B,N,H,C]
        k, v = _expand(k, q.shape[-2]), _expand(v, q.shape[-2])
        o = F.scaled_dot_product_attention(q.transpose(1, 2), k.transpose(1, 2), v.transpose(1, 2))
        return o.transpose(1, 2)

    def _lse_attn(q, k, v, chunk=2048):  # q [Lq,H,C] -> out [Lq,H,C], lse [H,Lq]
        scale = 1.0 / math.sqrt(q.shape[-1])
        qh, kh, vh = q.transpose(0, 1).float(), k.transpose(0, 1).float(), v.transpose(0, 1).float()
        outs, lses = [], []
        for s in range(0, qh.shape[1], chunk):
            sc = torch.matmul(qh[:, s:s + chunk], kh.transpose(1, 2)) * scale
            lse = torch.logsumexp(sc, dim=-1)
            outs.append(torch.matmul(torch.exp(sc - lse[..., None]), vh))
            lses.append(lse)
        return torch.cat(outs, 1).transpose(0, 1).to(q.dtype), torch.cat(lses, 1)

    def flash_attn_varlen_func(q, k, v, cu_q, cu_k, max_q, max_k, causal=False,
                               return_attn_probs=False, **kw):
        k, v = _expand(k, q.shape[1]), _expand(v, q.shape[1])
        cq, ck = cu_q.tolist(), cu_k.tolist()
        outs, lses = [], []
        for i in range(len(cq) - 1):
            qs, ks, vs = q[cq[i]:cq[i + 1]], k[ck[i]:ck[i + 1]], v[ck[i]:ck[i + 1]]
            if return_attn_probs:
                o, l = _lse_attn(qs, ks, vs)
                lses.append(l)
            else:
                o = F.scaled_dot_product_attention(
                    qs.transpose(0, 1)[None], ks.transpose(0, 1)[None], vs.transpose(0, 1)[None]
                )[0].transpose(0, 1)
            outs.append(o)
        out = torch.cat(outs, 0)
        if return_attn_probs:
            return out, torch.cat(lses, 1), None
        return out

    def flash_attn_kvpacked_func(q, kv, **kw):
        return flash_attn_func(q, kv[:, :, 0], kv[:, :, 1])

    def flash_attn_qkvpacked_func(qkv, **kw):
        return flash_attn_func(qkv[:, :, 0], qkv[:, :, 1], qkv[:, :, 2])

    def flash_attn_varlen_kvpacked_func(q, kv, cu_q, cu_k, max_q, max_k, **kw):
        return flash_attn_varlen_func(q, kv[:, 0], kv[:, 1], cu_q, cu_k, max_q, max_k)

    def flash_attn_varlen_qkvpacked_func(qkv, cu, max_s, **kw):
        return flash_attn_varlen_func(qkv[:, 0], qkv[:, 1], qkv[:, 2], cu, cu, max_s, max_s)

    m = types.ModuleType("flash_attn")
    m.flash_attn_kvpacked_func = flash_attn_kvpacked_func
    m.flash_attn_qkvpacked_func = flash_attn_qkvpacked_func
    m.flash_attn_varlen_kvpacked_func = flash_attn_varlen_kvpacked_func
    m.flash_attn_varlen_qkvpacked_func = flash_attn_varlen_qkvpacked_func
    m.flash_attn_func = flash_attn_func
    m.flash_attn_varlen_func = flash_attn_varlen_func
    sys.modules["flash_attn"] = m


def stub_unused_modules() -> None:
    for name in ("pymeshfix", "pymeshfix._meshfix", "utils3d", "igraph", "pyvista"):
        sys.modules.setdefault(name, types.ModuleType(name))
    sys.modules["pymeshfix"]._meshfix = sys.modules["pymeshfix._meshfix"]


def install_offload(pipe) -> dict:
    """Keep only the sub-models of the running stage on the GPU; record per-stage torch peaks (GB)."""
    peaks: dict = {}
    dev = pipe.device

    def wrap_model(m, name):
        if m is None:
            return
        m.to("cpu")

    for n in ("dense_vae", "dense_dit", "sparse_vae_512", "sparse_dit_512", "sparse_vae_1024",
              "sparse_dit_1024", "refiner", "refiner_1024", "dense_image_encoder", "sparse_image_encoder"):
        wrap_model(getattr(pipe, n), n)

    def timed_stage(label, models, fn):
        def run(*a, **k):
            for m in models:
                m.to(dev)
            torch.cuda.empty_cache()
            torch.cuda.reset_peak_memory_stats()
            t = time.time()
            try:
                return fn(*a, **k)
            finally:
                torch.cuda.synchronize()
                peaks[label] = {"peak_gb": round(torch.cuda.max_memory_allocated() / 2**30, 2),
                                "s": round(time.time() - t, 1)}
                print(f"STAGE {label}: {peaks[label]}", flush=True)
                for m in models:
                    m.to("cpu")
                torch.cuda.empty_cache()
        return run

    orig_inf = pipe.inference
    ctx = {"stage": 0}

    def inference(image, vae, dit, conditioner, scheduler, *a, **k):
        mode = k.get("mode", "dense")
        refiner = pipe.refiner if mode == "sparse512" else pipe.refiner_1024 if mode == "sparse1024" else None
        # refiner is moved on-demand inside run(), after the dit/vae/conditioner are released
        if refiner is not None:
            orig_run = refiner.run

            def run_ref(*ra, **rk):
                for m in (dit, vae, conditioner):
                    m.to("cpu")
                torch.cuda.empty_cache()
                refiner.to(dev)
                torch.cuda.reset_peak_memory_stats()
                t = time.time()
                try:
                    return orig_run(*ra, **rk)
                finally:
                    torch.cuda.synchronize()
                    peaks[f"{mode}_refiner"] = {"peak_gb": round(torch.cuda.max_memory_allocated() / 2**30, 2),
                                                "s": round(time.time() - t, 1)}
                    print(f"STAGE {mode}_refiner: {peaks[mode + '_refiner']}", flush=True)
                    refiner.to("cpu")
                    torch.cuda.empty_cache()
            refiner.run = run_ref
        return timed_stage(mode, [vae, dit, conditioner], lambda *x, **y: orig_inf(image, vae, dit, conditioner, scheduler, *a, **k))()

    pipe.inference = inference
    return peaks


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--src", required=True)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--sdf-resolution", type=int, default=512)
    a = ap.parse_args()
    src = Path(a.src)
    # this file is named direct3d_s2.py: keep its folder off sys.path so it cannot shadow the package
    sys.path[:] = [x for x in sys.path if Path(x or '.').resolve() != Path(__file__).resolve().parent]
    sys.path.insert(0, str(src))
    sys.path.insert(0, str(src.parent / "torchsparse_d3d"))
    sys.path.insert(0, str(src.parent / "direct3d_s2_udf"))  # compiled udf_ext
    import diffusers  # noqa: F401  (before the shim: it probes flash_attn.__spec__)
    install_flash_attn_shim()
    stub_unused_modules()
    import os
    os.environ.setdefault("TORCH_HOME", str(src.parent.parent / "torch_hub"))
    from PIL import Image
    from direct3d_s2.pipeline import Direct3DS2Pipeline

    t0 = time.time()
    pipe = Direct3DS2Pipeline.from_pretrained("wushuang98/Direct3D-S2", subfolder="direct3d-s2-v-1-1")
    pipe.device = torch.device("cuda:0")  # models stay on CPU; the active sub-model is moved in per stage
    stage_peaks = install_offload(pipe)
    load_s = time.time() - t0

    # library defaults, recorded
    settings = {
        "sdf_resolution": a.sdf_resolution, "dense_steps": 50, "dense_cfg": 7.0,
        "sparse512_steps": 30, "sparse512_cfg": 7.0, "sparse1024_steps": 15, "sparse1024_cfg": 7.0,
        "mc_threshold": 0.2, "remove_interior": True, "remesh": False, "simplify": False,
        "own_background_removal": False, "dtype": "float16", "seed": a.seed,
        "attention": "torch SDPA shim (no flash-attn on Windows)", "sparse_backend": "torchsparse (local build)",
    }
    out = Path(a.out)
    items = []
    for png in sorted(Path(a.inputs).glob("*.png")):
        pid = png.stem
        item = {"id": pid, "mesh": None, "gen_s": None, "torch_peak_gb": None, "textured": False, "error": None}
        print(f"BEGIN {pid}", flush=True)
        try:
            torch.cuda.reset_peak_memory_stats()
            t1 = time.time()
            gen = torch.Generator(device="cuda:0").manual_seed(a.seed)
            img = Image.open(png).convert("RGBA")
            mesh = pipe(img, sdf_resolution=a.sdf_resolution, remesh=False, remove_interior=True,
                        generator=gen)["mesh"]
            torch.cuda.synchronize()
            item["gen_s"] = round(time.time() - t1, 2)
            item["torch_peak_gb"] = round(torch.cuda.max_memory_allocated() / 2**30, 2)
            path = out / f"{pid}.glb"
            mesh.export(str(path))
            item["mesh"] = path.name
            item["stage_peaks"] = stage_peaks
            item["faces"] = int(len(mesh.faces))
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            item["error"] = f"{type(e).__name__}: {e}"
        finally:
            torch.cuda.empty_cache()
        print(f"END {pid}", flush=True)
        items.append(item)
    (out / "results.json").write_text(json.dumps({"load_s": round(load_s, 2), "settings": settings, "items": items}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
