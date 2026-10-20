"""A monster's skeleton from its confirmed limb chains (pure numpy; runs inside Blender too).

The page sends what the user confirmed in the limb editor:

    {"spine": [[x, y, z] x 4], "limbs": [{"kind": "leg|arm|head|tail", "joints": [[x, y, z] x 4]}]}

in the Clean step's frame (metres, Z up, the model faces -Y, the character's left is +X).
This turns it into bones the same shape as a fixed template (BoneDef + joints), so the same
binding, weight limit, export and Godot check apply. Names: Root, Spine1..3, then per limb
<Kind><Side><n>_1.._3 (Side L, R or none for a limb on the middle line), front to back.
"""

from __future__ import annotations

import numpy as np

from asset_forge.skeleton.templates import MAX_BONES, BoneDef
from asset_forge.skeleton.weights import segment_distance

KINDS = {"leg": "Leg", "arm": "Arm", "head": "Head", "tail": "Tail"}
JOINTS_PER_LIMB = 4
MAX_LIMBS = (MAX_BONES - 4) // (JOINTS_PER_LIMB - 1)  # Root + 3 spine bones, 3 per limb


class ChainError(ValueError):
    """The limb chains cannot make a skeleton; the message says why in plain words."""


def _points(raw, n: int, what: str) -> np.ndarray:
    try:
        p = np.asarray(raw, float)
    except (TypeError, ValueError):
        raise ChainError(f"The {what} has a marker that is not a point.") from None
    if p.shape != (n, 3) or not np.isfinite(p).all():
        raise ChainError(f"The {what} needs {n} markers.")
    return p


def monster_bones(chain: dict) -> tuple[list[BoneDef], dict[str, np.ndarray], list[dict]]:
    """(bones, joints, limbs) for a monster. Raises ChainError in plain words."""
    spine = _points(chain.get("spine"), 4, "body line")
    limbs = chain.get("limbs") or []
    if not limbs:
        raise ChainError("Add at least one limb before you confirm.")
    if len(limbs) > MAX_LIMBS:
        raise ChainError(f"That is {len(limbs)} limbs; a game skeleton can hold {MAX_LIMBS}. "
                         "Remove some, then confirm.")
    J: dict[str, np.ndarray] = {}
    bones = [BoneDef("Root", None, "Spine1")]
    J["Root"] = np.array([spine[0, 0], spine[0, 1], 0.0])
    names = ["Spine1", "Spine2", "Spine3", "SpineTip"]
    for k in range(3):
        bones.append(BoneDef(names[k], "Root" if k == 0 else names[k - 1], names[k + 1]))
    for k, n in enumerate(names):
        J[n] = spine[k]
    mid_x = float(spine[:, 0].mean())
    width = max(float(np.ptp(spine[:, 0])), 1e-3)
    count: dict[str, int] = {}
    info = []
    for i, lb in enumerate(limbs):
        kind = lb.get("kind")
        if kind not in KINDS:
            raise ChainError(f"Limb {i + 1} needs a kind: leg, arm, head or tail.")
        p = _points(lb.get("joints"), JOINTS_PER_LIMB, f"{kind} {i + 1}")
        dx = p[0, 0] - mid_x
        side = "" if abs(dx) < 0.05 * width + 0.01 else ("L" if dx > 0 else "R")
        key = KINDS[kind] + side
        count[key] = count.get(key, 0) + 1
        base = f"{key}{count[key]}"
        d = [float(segment_distance(p[:1], spine[k], spine[k + 1])[0]) for k in range(3)]
        parent = names[int(np.argmin(d))]
        chain_names = [f"{base}_{k}" for k in range(1, JOINTS_PER_LIMB)] + [f"{base}_Tip"]
        for k in range(JOINTS_PER_LIMB - 1):
            bones.append(BoneDef(chain_names[k], parent if k == 0 else chain_names[k - 1],
                                 chain_names[k + 1]))
        for k, n in enumerate(chain_names):
            J[n] = p[k]
        info.append({"name": base, "kind": kind, "side": side or "middle",
                     "bones": chain_names[:-1], "tip": [round(float(x), 5) for x in p[-1]]})
    return bones, J, info


def monster_pose(limbs: list[dict], joints: dict[str, np.ndarray]):
    """The quick test pose for a monster: every limb bends once, about 30 degrees at each joint,
    so a bad fit shows at a glance (legs lift and fold, arms raise and bend, heads and tails
    turn); the body twists a little. (bone, world axis, degrees)."""
    up = np.array([0.0, 0.0, 1.0])
    pose: list[tuple[str, list[float], float]] = [("Spine2", [0.0, 0.0, 1.0], 8.0)]
    for lb in limbs:
        b1, b2 = lb["bones"][0], lb["bones"][1]
        d = joints[lb["bones"][-1].rsplit("_", 1)[0] + "_Tip"] - joints[b1]
        h = np.array([d[0], d[1], 0.0])
        if np.linalg.norm(h) < 1e-6:
            h = np.array([1.0, 0.0, 0.0])
        lift = np.cross(h / np.linalg.norm(h), up).tolist()  # +deg raises the tip
        b3 = lb["bones"][2]
        if lb["kind"] == "leg":
            pose += [(b1, lift, 30.0), (b2, lift, -30.0), (b3, lift, -30.0)]
        elif lb["kind"] == "arm":
            pose += [(b1, lift, 35.0), (b2, lift, 35.0), (b3, lift, 30.0)]
        else:
            turn = 30.0 if lb["kind"] == "head" else -30.0
            pose += [(b1, [0.0, 0.0, 1.0], turn), (b2, [0.0, 0.0, 1.0], turn)]
    return pose
