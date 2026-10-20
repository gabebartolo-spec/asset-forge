"""Hand-made humanoid clips (Quaternius Universal Animation Library, CC0), re-targeted onto the
fitted humanoid skeleton.

The procedural humanoid clips read as stiff and slapstick (director, 2026-10-20: the walk
"looks like he's got shit in his pants", the punch arm "floppy spaghetti", the faint "looney
tunes"). People animate people better than a formula does, and the library is free for
commercial use, so a humanoid's clips come from it; four-legged animals and birds stay
procedural.

`blender/bake_library.py` stored, per clip and frame, each bone's world turn away from its rest
orientation. Re-targeting keeps what each bone points at: the target bone is turned so that
it points the same way in the world as the source bone does, after correcting for the two
rests differing (a T-pose against an A-pose arm). The pelvis move is scaled by the hip heights.
The result is a `Clip` of `Pose`s, so the same solver, grounding, gates and previews apply.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path

import numpy as np

from asset_forge.animate.body import Body, Pose
from asset_forge.animate.kin import rot_between

DATA = Path(__file__).with_name("data") / "ual_humanoid.json"
FPS = 30
LIBRARY_CLIPS = {"idle": "idle", "walk": "walk", "run": "run", "attack": "punch_jab",
                 "hit": "hit", "faint": "faint"}


@cache
def load() -> dict:
    return json.loads(DATA.read_text())


def _quat_to_mat(q) -> np.ndarray:
    w, x, y, z = q
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def _unit(v) -> np.ndarray:
    v = np.asarray(v, float)
    return v / np.linalg.norm(v)


def rest_correction(body: Body, src: dict) -> dict[str, np.ndarray]:
    """Per target bone: the smallest turn taking the source bone's rest direction to the
    target bone's rest direction."""
    out = {}
    for info in src["bones"].values():
        n = info["ours"]
        d_t = _unit(body.tail[n] - body.head[n])
        out[n] = rot_between(np.array(info["dir"]), d_t)
    return out


def retarget(body: Body, name: str, frames: slice | None = None) -> tuple[list[Pose], dict]:
    """The poses of library clip `name` on `body`, and the clip's data (fps, loop, speed)."""
    lib = load()
    clip = lib["clips"][name]
    fix = rest_correction(body, lib)
    ours_of = {s: i["ours"] for s, i in lib["bones"].items()}
    qs = {s: np.array(v) for s, v in clip["q"].items()}
    hips_src = np.array(clip["hips"])
    if clip["loop"]:  # drop trailing frames that merely repeat the first, then close the loop
        gap = np.max([np.abs(v - v[0]).max(axis=1) for v in qs.values()], axis=0)
        m = int(np.nonzero(gap > 1e-4)[0].max()) + 1
        qs = {s: np.concatenate([v[:m], v[:1]]) for s, v in qs.items()}
        hips_src = np.concatenate([hips_src[:m], hips_src[:1]])
    n_src = len(hips_src)
    sec = (n_src - 1) / clip["fps"]
    n_frames = round(sec * FPS) + 1  # resampled to the pipeline's frame rate; a loop still ends
    t = np.linspace(0.0, n_src - 1.0, n_frames)  # on exactly its first frame
    i0 = np.minimum(t.astype(int), n_src - 2)
    w = (t - i0)[:, None]

    def resample(a):
        return (1 - w) * a[i0] + w * a[i0 + 1]

    q = {}
    for s, v in qs.items():
        r = resample(v)  # a short blend of two close quaternions: normalise it
        q[ours_of[s]] = r / np.linalg.norm(r, axis=1, keepdims=True)
    scale = float(body.head["Hips"][2]) / float(lib["bones"]["pelvis"]["head"][2])
    hips = resample(hips_src) * scale
    poses = []
    for f in range(n_frames):
        world = {b: _quat_to_mat(q[b][f]) @ fix[b].T for b in q}  # delta turn of the target bone
        R = {}
        for b in body.names:
            if b not in world:
                continue
            p = body.parent[b]
            Rp = world.get(p, np.eye(3))
            R[b] = Rp.T @ world[b]
        poses.append(Pose(R, {"Hips": hips[f]}, {}, np.eye(4)))
    stretch = (n_frames - 1) / FPS / sec  # the resampled clip lasts a hair longer or shorter
    meta = {"fps": FPS, "loop": clip["loop"],
            "speed": float(clip["speed_m_s"]) / stretch * body.leg_len / _source_leg(lib)}
    return poses, meta


def _source_leg(lib: dict) -> float:
    """Hip to ankle length of the source rig (m)."""
    b = lib["bones"]
    return float(b["thigh_l"]["head"][2] - b["foot_l"]["head"][2])
