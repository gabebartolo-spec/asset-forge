"""Game-speed preview GIFs of every clip for every rig, for the motion review (local only).

    python tools/animate/previews.py RIGS_DIR OUT_DIR [--lock models/gpu.lock] [--export]

RIGS_DIR holds Step 3 outputs as <generator>/<body>/rigged.blend. For each rig, under the
shared GPU lock (one Blender job at a time): animate with previews, then one GIF per clip at
30 frames a second (OUT_DIR/<generator>_<body>_<clip>.gif) and a line of gait numbers. With
--export it also runs the export gate and the headless Godot checks on the result.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from asset_forge.animate import AnimFailed, animate  # noqa: E402
from asset_forge.config import load_settings  # noqa: E402
from asset_forge.export import ExportRefused, export_animated  # noqa: E402
from asset_forge.gpu_lock import gpu_lock  # noqa: E402

DURATIONS = (30, 30, 40)  # GIF delays are whole centiseconds: 30, 30, 40 ms average 1/30 s


def write_gif(frames_dir: Path, gif: Path) -> int:
    paths = sorted(frames_dir.glob("*.png"))
    frames = [Image.open(p).convert("RGB") for p in paths]
    if not frames:
        return 0
    durs = [DURATIONS[i % 3] for i in range(len(frames))]
    frames[0].save(gif, save_all=True, append_images=frames[1:], duration=durs, loop=0,
                   optimize=True)
    return len(frames)


def gait_line(rep: dict) -> str:
    out = []
    for c in rep["clips"]:
        if c["speed_m_s"]:
            sps = c["strides_per_s"]
            out.append(f"{c['name']} {c['speed_m_s']:.2f} m/s, {sps:.2f} strides/s "
                       f"({sps * 120:.0f} steps/min), Fr {c['froude']:.2f}, {c['frames'] - 1} keys")
    return "; ".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("rigs", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--lock", type=Path, default=REPO / "models" / "gpu.lock")
    ap.add_argument("--size", type=int, default=320)
    ap.add_argument("--export", action="store_true")
    a = ap.parse_args()
    blender = load_settings().blender_exe
    a.out.mkdir(parents=True, exist_ok=True)
    bad = 0
    for blend in sorted(a.rigs.glob("*/*/rigged.blend")):
        gen, body = blend.parent.parent.name, blend.parent.name
        kind = "humanoid" if body == "humanoid" else "animal"
        with tempfile.TemporaryDirectory(prefix="forge_previews_") as tmp:
            anim, frames = Path(tmp) / "anim", Path(tmp) / "frames"
            t0 = time.perf_counter()
            try:
                with gpu_lock(a.lock, "anim-previews"):
                    res = animate(blend, anim, blender, kind, previews=frames)
            except AnimFailed as e:
                print(f"{gen}/{body} FAIL {e}", flush=True)
                bad += 1
                continue
            secs = time.perf_counter() - t0
            rep = json.loads((anim / "clips.json").read_text(encoding="utf-8"))
            gifs = {c: write_gif(frames / c, a.out / f"{gen}_{body}_{c}.gif")
                    for c in sorted(p.name for p in frames.iterdir() if p.is_dir())}
            print(f"{gen}/{body} {res.template} OK {secs:.0f}s fps={rep['fps']} "
                  f"slide_cm={res.checks['slide_cm']} | {gait_line(rep)} | gif frames {gifs}",
                  flush=True)
            if a.export:
                try:
                    _, report = export_animated(anim, f"{gen}_{body}", kind,
                                                exports_dir=Path(tmp) / "exports")
                    print(f"  export OK {report['measured']} | {report['godot_rig']} | "
                          f"{report['godot_import']}", flush=True)
                except ExportRefused as e:
                    print(f"  export REFUSED {e.reasons}", flush=True)
                    bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
