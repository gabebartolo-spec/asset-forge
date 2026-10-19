"""Run one bake-off candidate over the five reference images, timing it and sampling VRAM.

    python tools/bakeoff/run_candidate.py <candidate> [--only humanoid,fox]

Each candidate lives in its own env, `models/envs/<candidate>` (gitignored), with its source in
`models/src/<candidate>`. The runner holds the GPU lock, records the GPU's memory before the run
(baseline: desktop, other apps), samples it every 0.25 s while the adapter runs, and attributes
the peak to each prompt using the adapter's BEGIN/END lines.

Adapter contract (tools/bakeoff/adapters/<candidate>.py, run with the env's python):
    --inputs DIR   RGBA PNGs named <prompt_id>.png (already matted by BiRefNet)
    --out DIR      write <prompt_id>.glb (or .obj/.ply) per prompt
    --src DIR      the candidate's cloned source (add to sys.path yourself)
    --seed N
  print "BEGIN <id>" and "END <id>" (flushed) around each prompt, load the model once before the
  first BEGIN, and write DIR/results.json:
    {"load_s": float, "settings": {...},
     "items": [{"id", "mesh", "gen_s", "torch_peak_gb", "textured": bool, "error": str|null}]}
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from gpu_lock import _models_dir, gpu_lock  # noqa: E402

HERE = Path(__file__).parent
MODELS = _models_dir()


def gpu_used_mib() -> int:
    out = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
        capture_output=True, text=True, check=True,
    ).stdout
    return int(out.strip().splitlines()[0])


class Sampler(threading.Thread):
    def __init__(self) -> None:
        super().__init__(daemon=True)
        self.samples: list[tuple[float, int]] = []
        self.stop = threading.Event()

    def run(self) -> None:
        while not self.stop.is_set():
            try:
                self.samples.append((time.time(), gpu_used_mib()))
            except Exception:  # noqa: BLE001 - a missed sample is not fatal
                pass
            self.stop.wait(0.25)

    def peak(self, t0: float = 0.0, t1: float = float("inf")) -> int:
        vals = [m for t, m in self.samples if t0 <= t <= t1]
        return max(vals) if vals else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("candidate")
    ap.add_argument("--only", default="")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--timeout", type=int, default=3600)
    args = ap.parse_args()

    name = args.candidate
    py = MODELS / "envs" / name / "Scripts" / "python.exe"
    adapter = HERE / "adapters" / f"{name}.py"
    src = MODELS / "src" / name
    refs = MODELS / "bakeoff" / "refs"
    out = MODELS / "bakeoff" / "out" / name
    for p in (py, adapter, refs):
        if not p.exists():
            print(f"missing: {p}", file=sys.stderr)
            return 2
    out.mkdir(parents=True, exist_ok=True)

    inputs = refs
    if args.only:
        inputs = out / "_inputs"
        inputs.mkdir(exist_ok=True)
        for f in inputs.glob("*.png"):
            f.unlink()
        for pid in args.only.split(","):
            (inputs / f"{pid}.png").write_bytes((refs / f"{pid}.png").read_bytes())

    env = dict(os.environ)
    env.setdefault("HF_HOME", str(MODELS / "hf"))
    env["PYTHONUNBUFFERED"] = "1"
    cmd = [str(py), str(adapter), "--inputs", str(inputs), "--out", str(out),
           "--src", str(src), "--seed", str(args.seed)]

    with gpu_lock(f"bakeoff:{name}"):
        baseline = gpu_used_mib()
        sampler = Sampler()
        sampler.start()
        marks: dict[str, list[float]] = {}
        t_start = time.time()
        log = (out / "adapter.log").open("w", encoding="utf-8")
        proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace")
        assert proc.stdout
        for line in proc.stdout:
            log.write(line)
            log.flush()
            parts = line.split()
            if len(parts) == 2 and parts[0] in ("BEGIN", "END"):
                marks.setdefault(parts[1], []).append(time.time())
                print(line.rstrip(), flush=True)
            if time.time() - t_start > args.timeout:
                proc.kill()
                print("TIMEOUT", flush=True)
                break
        rc = proc.wait()
        wall = time.time() - t_start
        sampler.stop.set()
        sampler.join()
        log.close()

    res_path = out / "results.json"
    res = json.loads(res_path.read_text()) if res_path.exists() else {"items": []}
    for item in res.get("items", []):
        m = marks.get(item["id"], [])
        if len(m) == 2:
            item["gpu_peak_gb"] = round((sampler.peak(m[0], m[1]) - baseline) / 1024, 2)
    run = {
        "candidate": name, "rc": rc, "wall_s": round(wall, 1),
        "baseline_gb": round(baseline / 1024, 2),
        "gpu_peak_gb": round((sampler.peak() - baseline) / 1024, 2),
        "gpu_total_gb": round(sampler.peak() / 1024, 2),
        **res,
    }
    (out / "run.json").write_text(json.dumps(run, indent=2))
    print(json.dumps({k: run[k] for k in ("candidate", "rc", "wall_s", "gpu_peak_gb")}))
    return rc


if __name__ == "__main__":
    sys.exit(main())
