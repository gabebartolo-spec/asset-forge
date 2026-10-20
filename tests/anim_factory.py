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
    frame twice), "rot_pop" (idle turns the head and does not turn it back), "turn" (a
    smooth idle sway that turns round at the seam: must pass)."""
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
            if bad == "turn":  # turning points half a frame before the seam and mid-clip
                ang = 0.05 * np.cos(2 * np.pi * (np.arange(frames) + 0.5) / (frames - 1))
        q = np.stack([np.zeros(frames), np.sin(ang / 2), np.zeros(frames), np.cos(ang / 2)], 1)
        samplers.append({"input": add(times, "SCALAR"), "output": add(q, "VEC4"),
                         "interpolation": "LINEAR"})
        chans.append({"sampler": len(samplers) - 1, "target": {"node": 3, "path": "rotation"}})
        anims.append({"name": name, "channels": chans, "samplers": samplers})
    gltf = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}],
            "nodes": nodes, "animations": anims, "accessors": accessors,
            "bufferViews": views, "buffers": [{"byteLength": len(blob)}]}
    return _pack(path, gltf, bytes(blob))


PAW_TIP = np.array([0.0, -0.05, 0.02])  # from the ankle node: below it and a little ahead


def paw_tips() -> dict:
    """clips.json "foot_tips" for write_paw_glb (rest positions, glTF axes)."""
    return {"LeftFoot.tail": [0.1, *PAW_TIP[1:]], "RightFoot.tail": [-0.1, *PAW_TIP[1:]]}


def write_paw_glb(path: Path, names=CLIP_NAMES) -> Path:
    """Two feet that stand still in every clip, except that in idle the left paw peels off the
    ground and back about its planted tip (PAW_TIP): the tip never moves, the ankle node swings
    forward 13 mm while staying within the contact band."""
    nodes = [{"name": "Root", "children": [1, 2]},
             {"name": "LeftFoot", "translation": [0.1, 0.0, 0.0]},
             {"name": "RightFoot", "translation": [-0.1, 0.0, 0.0]}]
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
        frames = 25
        times = np.arange(frames, dtype=float) / FPS
        a = np.zeros(frames)
        if name == "idle":
            a = 0.25 * np.sin(np.pi * np.arange(frames) / (frames - 1)) ** 2
        c, s_ = np.cos(a), np.sin(a)
        # turned about x by a, then moved so the tip stays where it rests: t = x0 + p - R p
        rp = np.stack([np.zeros(frames), PAW_TIP[1] * c - PAW_TIP[2] * s_,
                       PAW_TIP[1] * s_ + PAW_TIP[2] * c], 1)
        tr = np.array([0.1, 0.0, 0.0]) + PAW_TIP - rp
        q = np.stack([np.sin(a / 2), np.zeros(frames), np.zeros(frames), np.cos(a / 2)], 1)
        chans, samplers = [], []
        for out, path_ in ((tr, "translation"), (q, "rotation")):
            samplers.append({"input": add(times, "SCALAR"),
                             "output": add(out, "VEC3" if path_ == "translation" else "VEC4"),
                             "interpolation": "LINEAR"})
            chans.append({"sampler": len(samplers) - 1, "target": {"node": 1, "path": path_}})
        anims.append({"name": name, "channels": chans, "samplers": samplers})
    gltf = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}],
            "nodes": nodes, "animations": anims, "accessors": accessors,
            "bufferViews": views, "buffers": [{"byteLength": len(blob)}]}
    return _pack(path, gltf, bytes(blob))


__all__ = ["FPS", "GAIT", "LEG", "PAW_TIP", "clips_json", "foot_track", "paw_tips",
           "write_anim_glb", "write_paw_glb"]


def write_budget_glb(path: Path, tris: int = 100, materials: int = 1, tex_px: int = 0) -> Path:
    """A mesh with `tris` triangles split over `materials` materials and, if tex_px, one
    embedded PNG texture tex_px pixels square: for the export gate."""
    import io

    from PIL import Image

    pos = np.array([(0, 0, 0), (1, 0, 0), (0, 1, 0)], "<f4").tobytes()
    blob = bytearray(pos)
    views = [{"buffer": 0, "byteOffset": 0, "byteLength": len(pos)}]
    accessors = [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3",
                  "min": [0, 0, 0], "max": [1, 1, 0]}]
    prims = []
    per = [tris // materials + (1 if i < tris % materials else 0) for i in range(materials)]
    for i, n in enumerate(per):
        idx = np.tile(np.array([0, 1, 2], "<u2"), n).tobytes()
        idx += b"\0" * (-len(idx) % 4)
        views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(idx)})
        blob.extend(idx)
        accessors.append({"bufferView": len(views) - 1, "componentType": 5123,
                          "count": 3 * n, "type": "SCALAR"})
        prims.append({"attributes": {"POSITION": 0}, "indices": len(accessors) - 1,
                      "material": i})
    gltf = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}],
            "nodes": [{"mesh": 0}], "meshes": [{"primitives": prims}],
            "materials": [{"name": f"m{i}"} for i in range(materials)]}
    if tex_px:
        buf = io.BytesIO()
        Image.new("RGB", (tex_px, tex_px), (200, 120, 40)).save(buf, "PNG")
        png = buf.getvalue() + b"\0" * (-len(buf.getvalue()) % 4)
        views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(buf.getvalue())})
        blob.extend(png)
        gltf["images"] = [{"bufferView": len(views) - 1, "mimeType": "image/png"}]
    gltf.update(accessors=accessors, bufferViews=views, buffers=[{"byteLength": len(blob)}])
    return _pack(path, gltf, bytes(blob))
