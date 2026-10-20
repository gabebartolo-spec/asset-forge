"""Tiny animated .glb writer for the Step 4 checks (no Blender needed).

A two-foot "body": a Root node with LeftFoot and RightFoot children, and one clip per name
moving the feet. Feet follow asset_forge.animate.gait, written in glTF axes (forward +Z, up +Y)
like the Blender export, so a good file passes check_animated_glb and each `bad` option breaks
exactly one rule.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from glb_factory import _pack

from asset_forge.animate.clips import CLIP_NAMES, LOOPING
from asset_forge.animate.gait import BIPED, Gait

FPS = 30
LEG = 0.5
GAIT = Gait(frames=24, fps=FPS, duty=0.6, stroke=0.3, lift=0.05, phases=BIPED)


def foot_track(leg: str, frames: int, gait: Gait = GAIT) -> np.ndarray:
    """(frames, 3) glTF positions of one foot over a walk (x to the side, y up, z forward)."""
    side = 0.1 if leg == "Left" else -0.1
    out = []
    for f in range(frames):
        x, z, _, _ = gait.foot(leg, f % gait.frames)
        out.append((side, z, x))
    return np.array(out)


def clips_json(speed: float = GAIT.speed, names=CLIP_NAMES) -> dict:
    """The clips.json the Animate step writes, for these files."""
    return {"template": "bird", "fps": FPS, "leg_length_m": LEG, "height_m": 1.0,
            "legs": ["Left", "Right"],
            "clips": [{"name": n, "speed_m_s": speed if n in ("walk", "run") else 0.0,
                       "loop": n in LOOPING} for n in names]}


def write_anim_glb(path: Path, names=CLIP_NAMES, bad: str | None = None) -> Path:
    """bad: None (passes), "pop" (walk ends away from its start), "stall" (walk shows its last
    frame twice), "rot_pop" (idle turns the head and does not turn it back)."""
    nodes = [{"name": "Root", "children": [1, 2, 3]},
             {"name": "LeftFoot", "translation": [0.1, 0.0, 0.0]},
             {"name": "RightFoot", "translation": [-0.1, 0.0, 0.0]},
             {"name": "Head", "translation": [0.0, 1.0, 0.0]}]
    blob = bytearray()
    accessors, views, anims = [], [], []

    def add(arr: np.ndarray, kind: str) -> int:
        data = np.ascontiguousarray(arr, dtype="<f4").tobytes()
        views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(data)})
        blob.extend(data)
        acc = {"bufferView": len(views) - 1, "componentType": 5126, "count": len(arr),
               "type": kind}
        if kind == "SCALAR":
            acc["min"], acc["max"] = [float(arr.min())], [float(arr.max())]
        accessors.append(acc)
        return len(accessors) - 1

    for name in names:
        loop = name in LOOPING
        frames = GAIT.frames + 1 if loop else 16  # a loop's last key repeats its first
        times = np.arange(frames, dtype=float) / FPS
        chans, samplers = [], []
        for node, leg in ((1, "Left"), (2, "Right")):
            if name in ("walk", "run"):
                tr = foot_track(leg, frames)
            else:
                tr = np.tile([0.1 if leg == "Left" else -0.1, 0.0, 0.0], (frames, 1))
            if name == "walk" and node == 1:
                if bad == "pop":
                    tr[-1] += [0.0, 0.0, 0.05]
                if bad == "stall":  # the seam frame shown twice: no jump, but a hitch
                    tr = np.vstack([tr, tr[-1]])
            t_ = np.arange(len(tr), dtype=float) / FPS
            samplers.append({"input": add(t_, "SCALAR"), "output": add(tr, "VEC3"),
                             "interpolation": "LINEAR"})
            chans.append({"sampler": len(samplers) - 1,
                          "target": {"node": node, "path": "translation"}})
        ang = np.zeros(frames)
        if name == "idle":
            ang = 0.05 * np.sin(2 * np.pi * np.arange(frames) / (frames - 1))
            if bad == "rot_pop":
                ang[-1] = 0.3
        q = np.stack([np.zeros(frames), np.sin(ang / 2), np.zeros(frames), np.cos(ang / 2)], 1)
        samplers.append({"input": add(times, "SCALAR"), "output": add(q, "VEC4"),
                         "interpolation": "LINEAR"})
        chans.append({"sampler": len(samplers) - 1, "target": {"node": 3, "path": "rotation"}})
        anims.append({"name": name, "channels": chans, "samplers": samplers})
    gltf = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}],
            "nodes": nodes, "animations": anims, "accessors": accessors,
            "bufferViews": views, "buffers": [{"byteLength": len(blob)}]}
    return _pack(path, gltf, bytes(blob))


__all__ = ["FPS", "GAIT", "LEG", "clips_json", "foot_track", "write_anim_glb"]
