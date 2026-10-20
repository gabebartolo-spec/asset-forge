"""Checks on the exported animated .glb itself (not on what the script meant to write):

- the clips are exactly idle, walk, run, attack, hit, faint;
- every looping clip ends where it starts (no pop) and moves on at the same pace (no kink);
- planted feet do not slide: each foot joint is replayed through the node tree and measured
  with gait.foot_slide (the faint is left out: the body falls, the feet go with it).

Pure Python + numpy, reads glTF 2.0 binary directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from asset_forge.animate.clips import CLIP_NAMES, LOOPING
from asset_forge.animate.gait import foot_slide
from asset_forge.skeleton.glb import _accessor, _load

SLIDE_FRAC = 0.02      # a planted foot may slide at most 2% of the leg length in one contact
CONTACT_FRAC = 0.01    # a foot is on the ground within 1% of the leg length of its lowest point
SEAM_ROT = 2e-3        # quaternion components
SEAM_POS_FRAC = 1e-3   # of the body height
GLTF_FWD = (0.0, 0.0, 1.0)   # Blender -Y after the +Y-up export
GLTF_UP = (0.0, 1.0, 0.0)
NOT_PLANTED = ("faint",)


@dataclass
class Channel:
    node: int
    path: str
    times: np.ndarray
    values: np.ndarray


@dataclass
class GlbAnimations:
    nodes: list[dict]
    names: list[str]
    clips: dict[str, list[Channel]]

    def node_index(self, name: str) -> int:
        return self.names.index(name)

    def duration(self, clip: str) -> float:
        return max(float(c.times[-1]) for c in self.clips[clip])


def read_animations(path: Path) -> GlbAnimations:
    gltf, blob = _load(Path(path))
    nodes = gltf.get("nodes", [])
    clips: dict[str, list[Channel]] = {}
    for i, a in enumerate(gltf.get("animations", [])):
        chans = []
        for ch in a["channels"]:
            s = a["samplers"][ch["sampler"]]
            if s.get("interpolation", "LINEAR") == "CUBICSPLINE":
                raise ValueError("cubic spline keys are not expected from the exporter")
            chans.append(Channel(ch["target"]["node"], ch["target"]["path"],
                                 _accessor(gltf, blob, s["input"])[:, 0],
                                 _accessor(gltf, blob, s["output"])))
        clips[a.get("name", f"animation_{i}")] = chans
    return GlbAnimations(nodes, [n.get("name", "") for n in nodes], clips)


def _sample(ch: Channel, t: float) -> np.ndarray:
    ts, vs = ch.times, ch.values
    if t <= ts[0]:
        return vs[0]
    if t >= ts[-1]:
        return vs[-1]
    k = int(np.searchsorted(ts, t, side="right") - 1)
    u = (t - ts[k]) / (ts[k + 1] - ts[k])
    a, b = vs[k], vs[k + 1]
    if ch.path == "rotation":
        if a @ b < 0:
            b = -b
        q = (1 - u) * a + u * b
        return q / np.linalg.norm(q)
    return (1 - u) * a + u * b


def _trs(t, r, s) -> np.ndarray:
    x, y, z, w = r
    R = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                  [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                  [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    M = np.eye(4)
    M[:3, :3] = R * np.asarray(s)
    M[:3, 3] = t
    return M


def world_positions(anims: GlbAnimations, clip: str, joints: list[str], fps: float) -> np.ndarray:
    """(frames, len(joints), 3) world positions of the named nodes over a clip."""
    by_node: dict[int, dict[str, Channel]] = {}
    for ch in anims.clips[clip]:
        by_node.setdefault(ch.node, {})[ch.path] = ch
    parent = {c: i for i, n in enumerate(anims.nodes) for c in n.get("children", [])}
    want = [anims.node_index(j) for j in joints]
    n_frames = int(round(anims.duration(clip) * fps)) + 1
    out = np.zeros((n_frames, len(want), 3))
    for f in range(n_frames):
        t = f / fps
        cache: dict[int, np.ndarray] = {}

        def world(i, t=t, cache=cache):
            if i in cache:
                return cache[i]
            nd, ch = anims.nodes[i], by_node.get(i, {})
            tr = _sample(ch["translation"], t) if "translation" in ch else nd.get(
                "translation", [0, 0, 0])
            ro = _sample(ch["rotation"], t) if "rotation" in ch else nd.get(
                "rotation", [0, 0, 0, 1])
            sc = _sample(ch["scale"], t) if "scale" in ch else nd.get("scale", [1, 1, 1])
            M = _trs(tr, ro, sc)
            if i in parent:
                M = world(parent[i]) @ M
            cache[i] = M
            return M

        for k, i in enumerate(want):
            out[f, k] = world(i)[:3, 3]
    return out


def seam_errors(anims: GlbAnimations, clip: str) -> tuple[float, float, int]:
    """(worst rotation pop, worst position pop in metres, channels that stall at the seam).

    A pop: the last key is not the first. A stall: the motion is moving into and out of the seam
    but the last step is (almost) zero, i.e. a frame is shown twice and the loop hitches."""
    rot, pos, stalls = 0.0, 0.0, 0
    for ch in anims.clips[clip]:
        v = ch.values
        if len(v) < 4:
            continue
        a, b = v[0], v[-1]
        if ch.path == "rotation":
            rot = max(rot, float(min(np.abs(a - b).max(), np.abs(a + b).max())))
            v = v * np.where((v @ v[0]) < 0, -1.0, 1.0)[:, None]
        elif ch.path == "translation":
            pos = max(pos, float(np.abs(a - b).max()))
        last = float(np.abs(v[-1] - v[-2]).max())
        around = min(float(np.abs(v[1] - v[0]).max()), float(np.abs(v[-2] - v[-3]).max()))
        if around > 1e-4 and last < 0.1 * around:
            stalls += 1
    return rot, pos, stalls


@dataclass
class AnimReport:
    problems: list[str] = field(default_factory=list)
    slide_cm: dict[str, float] = field(default_factory=dict)
    seams: dict[str, dict] = field(default_factory=dict)

    def public(self) -> dict:
        return {"slide_cm": self.slide_cm, "seams": self.seams}


def foot_joints(template: str, legs: list[str]) -> list[str]:
    joints = [f"{lg}Foot" for lg in legs]
    if template == "humanoid":
        joints += [f"{lg}Toes" for lg in legs]
    return joints


def check_animated_glb(glb: Path, rep: dict) -> AnimReport:
    """Every way the animated .glb breaks the Step 4 rules, in plain words (rep: clips.json)."""
    out = AnimReport()
    try:
        anims = read_animations(Path(glb))
    except (OSError, ValueError, KeyError) as e:
        out.problems.append(f"The animated file could not be read ({e}).")
        return out
    have = list(anims.clips)
    missing = [n for n in CLIP_NAMES if n not in have]
    extra = [n for n in have if n not in CLIP_NAMES]
    if missing:
        out.problems.append(f"The animation{'s' if len(missing) > 1 else ''} "
                            f"{', '.join(missing)} {'are' if len(missing) > 1 else 'is'} missing.")
    if extra:
        out.problems.append(f"Unexpected animation{'s' if len(extra) > 1 else ''} in the file: "
                            f"{', '.join(extra)}.")
    height = float(rep.get("height_m", 1.0))
    for name in LOOPING:
        if name not in anims.clips:
            continue
        r, p, k = seam_errors(anims, name)
        out.seams[name] = {"rotation": round(r, 5), "position_mm": round(p * 1000, 3),
                           "stalled_channels": k}
        if r > SEAM_ROT or p > SEAM_POS_FRAC * height:
            out.problems.append(f"The {name} loop jumps where it starts again.")
        elif k:
            out.problems.append(f"The {name} loop hitches where it starts again (a frame "
                                "is shown twice).")
    leg_len = float(rep.get("leg_length_m", 1.0))
    joints = foot_joints(rep.get("template", "humanoid"), rep.get("legs", []))
    meta = {c["name"]: c for c in rep.get("clips", [])}
    if not joints or any(j not in anims.names for j in joints):
        out.problems.append("The feet could not be found in the animated file.")
        return out
    for name in CLIP_NAMES:
        if name not in anims.clips or name in NOT_PLANTED:
            continue
        speed = float(meta.get(name, {}).get("speed_m_s", 0.0))
        tr = world_positions(anims, name, joints, float(rep.get("fps", 30)))
        worst = 0.0
        for k, j in enumerate(joints):
            s = foot_slide(tr[:, k], rep.get("fps", 30), speed, GLTF_FWD, GLTF_UP,
                           CONTACT_FRAC * leg_len)
            worst = max(worst, s.worst_m)
            if s.worst_m > SLIDE_FRAC * leg_len:
                part = j.replace("Foot", " foot").replace("Toes", " toes")
                out.problems.append(f"In {name}, the {part} slides {s.worst_m * 100:.1f} cm while "
                                    f"planted (limit {SLIDE_FRAC * leg_len * 100:.1f} cm).")
        out.slide_cm[name] = round(worst * 100, 3)
    return out
