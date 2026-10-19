"""Step1X-3D geometry-only adapter (Apache-2.0). No texture stage, no background remover.

rembg and pymeshlab (GPL) are stubbed: inputs are already matted RGBA so rembg is never called,
and floater removal / decimation are done here with trimesh + fast_simplification (MIT).
Env knobs: STEP1X_DTYPE=fp16|bf16|fp32 (default fp16), STEP1X_OFFLOAD=none|model|sequential.
"""
import argparse, json, os, sys, time, types
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--inputs", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--src", required=True)
ap.add_argument("--seed", type=int, default=0)
args = ap.parse_args()

sys.path.insert(0, args.src)
def _stub(name):
    import importlib.machinery
    m = types.ModuleType(name)
    m.__spec__ = importlib.machinery.ModuleSpec(name, None)

    def ga(attr):
        if attr.startswith("__"):
            raise AttributeError(attr)
        return type(attr, (), {})
    m.__getattr__ = ga
    sys.modules[name] = m


# rembg (never called: inputs are matted), pymeshlab (GPL; replaced below by trimesh +
# fast_simplification), streaming (training-only dataloader) are import-time stubs only.
for _n in ("rembg", "pymeshlab", "streaming", "wandb"):
    _stub(_n)

import numpy as np, torch, trimesh  # noqa: E402
import PIL.Image  # noqa: E402

STEPS, GUIDANCE, OCTREE, MAXFACES = 50, 7.5, 384, 200000
DTYPE = os.environ.get("STEP1X_DTYPE", "fp16")
OFFLOAD = os.environ.get("STEP1X_OFFLOAD", "none")
dt = {"fp16": torch.float16, "bf16": torch.bfloat16, "fp32": torch.float32}[DTYPE]

from step1x3d_geometry.models.pipelines.pipeline import Step1X3DGeometryPipeline  # noqa: E402

if os.environ.get("STEP1X_IMPORT_ONLY"):
    print("IMPORT OK"); sys.exit(0)
models = Path(os.environ["HF_HOME"]).parent if "HF_HOME" in os.environ else Path(args.src).parents[1]
weights = str(Path(os.environ.get("HF_HOME", models / "hf")) / "Step1X-3D-local")

t0 = time.time()
pipe = Step1X3DGeometryPipeline.from_pretrained(weights, subfolder="Step1X-3D-Geometry-1300m", torch_dtype=dt)
if OFFLOAD == "model":
    pipe.enable_model_cpu_offload()
elif OFFLOAD == "sequential":
    pipe.enable_sequential_cpu_offload()
else:
    pipe.to("cuda")
load_s = time.time() - t0


def clean(m: trimesh.Trimesh, max_faces: int) -> trimesh.Trimesh:
    # The hierarchical decoder marks cells outside the near-surface band as NaN; marching cubes
    # then emits NaN vertices at the band edge. Real surface faces are fully finite: drop the rest.
    ok = np.isfinite(m.vertices).all(axis=1)
    m = trimesh.Trimesh(m.vertices, m.faces[ok[m.faces].all(axis=1)], process=False)
    m.remove_unreferenced_vertices()
    parts = m.split(only_watertight=False)
    if len(parts) > 1:
        keep = [p for p in parts if len(p.faces) >= 0.001 * len(m.faces)]
        m = trimesh.util.concatenate(keep)
    if len(m.faces) > max_faces:
        import fast_simplification
        v, f = fast_simplification.simplify(m.vertices, m.faces, target_count=max_faces)
        m = trimesh.Trimesh(v, f, process=False)
    m.fix_normals()
    return m


out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
items = []
for png in sorted(Path(args.inputs).glob("*.png")):
    pid = png.stem
    item = {"id": pid, "mesh": None, "gen_s": None, "torch_peak_gb": None, "textured": False, "error": None}
    print(f"BEGIN {pid}", flush=True)
    try:
        torch.cuda.reset_peak_memory_stats()
        t1 = time.time()
        g = torch.Generator(device="cuda").manual_seed(args.seed)
        res = pipe(str(png), guidance_scale=GUIDANCE, num_inference_steps=STEPS, generator=g,
                   octree_resolution=OCTREE, output_type="raw", force_remove_background=False)
        raw = res.mesh[0]
        m = trimesh.Trimesh(raw.verts.cpu().numpy(), raw.faces.cpu().numpy(), process=False)
        print("raw", len(m.vertices), len(m.faces), "nan", int(np.isnan(m.vertices).sum()), flush=True)
        m = clean(m, MAXFACES)
        print("clean nan", int(np.isnan(m.vertices).sum()), flush=True)
        p = out / f"{pid}.glb"
        m.export(p)
        torch.cuda.synchronize()
        item.update(mesh=str(p), gen_s=round(time.time() - t1, 1),
                    torch_peak_gb=round(torch.cuda.max_memory_allocated() / 2**30, 2), faces=int(len(m.faces)))
    except Exception as e:  # noqa: BLE001
        import traceback; traceback.print_exc()
        item["error"] = f"{type(e).__name__}: {e}"[:500]
    print(f"END {pid}", flush=True)
    items.append(item)

(out / "results.json").write_text(json.dumps({
    "load_s": round(load_s, 1),
    "settings": {"steps": STEPS, "guidance": GUIDANCE, "octree_resolution": OCTREE, "max_faces": MAXFACES,
                 "dtype": DTYPE, "offload": OFFLOAD, "surface_extractor": "mc (skimage)", "seed": args.seed,
                 "model": "Step1X-3D-Geometry-1300m", "bg_removal": "none (alpha used)"},
    "items": items}, indent=2))
