"""The rig as the animator sees it: bones at rest, the legs (for the feet IK) and one solver that
turns a Pose (a few rotations, a body move and foot targets) into a delta per bone.

Pure numpy. Built from the Step 3 skeleton (`skeleton.json`, or the bones Blender reads from
rigged.blend). Forward is always -Y, the export convention (D-021): the clips walk along -Y.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from asset_forge.animate.kin import UP, about, apply, frame, two_bone_ik, unit
from asset_forge.skeleton.templates import TEMPLATES

FWD = np.array([0.0, -1.0, 0.0])
LEFT = np.array([1.0, 0.0, 0.0])

# Which way each knee bends (a template fact, never read from the fit: a fitted knee can sit a
# little behind the hip-ankle line, and a humanoid knee bending backwards is the worst defect).
#   humanoid: knees forward. four-legged: front legs fold back, hind knees forward.
#   bird: the visible joint is the ankle, it points back.
STAND_REACH = {"humanoid": 0.995}

_POLE = {"humanoid": {"": 1.0}, "four_legged": {"Front": -1.0, "Hind": 1.0}, "bird": {"": -1.0}}


@dataclass
class Leg:
    name: str          # "Left", "FrontLeft", ...
    upper: str
    lower: str
    foot: str
    side: float        # +1 left, -1 right
    group: str         # "", "Front" or "Hind"
    hip: np.ndarray
    knee: np.ndarray
    ankle: np.ndarray
    tip: np.ndarray    # the far end of the foot (toe tip or paw tip)
    ball: np.ndarray   # where a lifting heel turns: a person's ball joint (Toes), else the tip
    pole: np.ndarray
    l1: float = 0.0
    l2: float = 0.0
    ground_z: float = 0.0  # ankle height when the foot stands on the ground

    @property
    def length(self) -> float:
        return self.l1 + self.l2


@dataclass
class Pose:
    """One frame. rot: bone -> 3x3 rotation about the bone's own head, in rest axes, after the
    parent has moved. move: bone -> translation applied before its rotation (the body bob lives
    on Hips). feet: leg name -> (ankle target, absolute 3x3 foot turn), both before `root`.
    root: a 4x4 move of the whole character (only the faint uses it)."""

    rot: dict[str, np.ndarray] = field(default_factory=dict)
    move: dict[str, np.ndarray] = field(default_factory=dict)
    feet: dict[str, tuple[np.ndarray, np.ndarray]] = field(default_factory=dict)
    root: np.ndarray = field(default_factory=lambda: np.eye(4))


class Body:
    def __init__(self, template: str, bones: list[tuple[str, str | None, np.ndarray, np.ndarray]]):
        if template not in TEMPLATES:
            raise ValueError(f"unknown template {template!r}")
        self.template = template
        self.parent: dict[str, str | None] = {}
        self.head: dict[str, np.ndarray] = {}
        self.tail: dict[str, np.ndarray] = {}
        for name, parent, head, tail in bones:
            self.parent[name] = parent
            self.head[name] = np.asarray(head, float)
            self.tail[name] = np.asarray(tail, float)
        self.names = self._order()
        missing = [b.name for b in TEMPLATES[template] if b.name not in self.head]
        if missing:
            raise ValueError(f"the skeleton is missing bones: {missing}")
        pts = np.array([*self.head.values(), *self.tail.values()])
        self.height = float(pts[:, 2].max())
        self.legs = self._legs()
        self.leg_len = float(np.mean([lg.length for lg in self.legs]))
        lo = min(lg.ankle[2] for lg in self.legs)
        self.short_legs: list[str] = []
        # A standing leg reaches at most this much of its length. A person stands straight-
        # legged (at 0.96 the feet floated 3 cm and every clip stood on bent knees, a crouch);
        # an animal's leg keeps a little bend.
        most = STAND_REACH.get(template, 0.96)
        for lg in self.legs:  # a paw the model holds up still stands on the ground...
            lg.ground_z = float(min(lg.ankle[2], lo + 0.02 * self.height))
            # ...unless its bones are too short to reach it (the fit followed the raised paw)
            horiz = float(np.linalg.norm((lg.hip - lg.ankle)[:2]))
            dz = float(np.sqrt(max((most * lg.length) ** 2 - horiz**2, 0.0)))
            if lg.hip[2] - lg.ground_z > dz:
                lg.ground_z = float(lg.hip[2] - dz)
                if lg.ground_z > lo + 0.05 * self.height:
                    self.short_legs.append(lg.name)

    # ------------------------------------------------------------------ construction
    @classmethod
    def from_joints(cls, template: str, joints: dict) -> Body:
        return cls(template, [(b.name, b.parent, joints[b.name], joints[b.tail])
                              for b in TEMPLATES[template]])

    @classmethod
    def from_skeleton_report(cls, rep: dict) -> Body:
        """From the Skeleton step's skeleton.json."""
        return cls(rep["template"], [(b["name"], b["parent"], rep["joints"][b["name"]], b["tail"])
                                     for b in rep["bone_list"]])

    def _order(self) -> list[str]:
        out, seen = [], set()

        def visit(n):
            if n in seen:
                return
            p = self.parent[n]
            if p is not None:
                visit(p)
            seen.add(n)
            out.append(n)

        for n in self.parent:
            visit(n)
        return out

    def _legs(self) -> list[Leg]:
        poles = _POLE[self.template]
        groups = ("Front", "Hind") if self.template == "four_legged" else ("",)
        legs = []
        for g in groups:
            for side, s in (("Left", 1.0), ("Right", -1.0)):
                nm = f"{g}{side}"
                up, lo, ft = f"{nm}UpperLeg", f"{nm}LowerLeg", f"{nm}Foot"
                if self.template == "humanoid":
                    tip, ball = self.tail[f"{nm}Toes"], self.head[f"{nm}Toes"]
                else:
                    tip = ball = self.tail[ft]
                lg = Leg(nm, up, lo, ft, s, g, self.head[up], self.head[lo], self.head[ft], tip,
                         ball, FWD * poles[g])
                lg.l1 = float(np.linalg.norm(lg.knee - lg.hip))
                lg.l2 = float(np.linalg.norm(lg.ankle - lg.knee))
                legs.append(lg)
        return legs

    def leg(self, name: str) -> Leg:
        return next(lg for lg in self.legs if lg.name == name)

    def children(self, name: str) -> list[str]:
        return [n for n in self.names if self.parent[n] == name]

    # ------------------------------------------------------------------ solving
    def solve(self, pose: Pose) -> tuple[dict[str, np.ndarray], list[str]]:
        """Delta per bone, and the legs whose foot target was out of reach this frame."""
        D: dict[str, np.ndarray] = {}
        short: list[str] = []
        ik = {lg.upper: lg for lg in self.legs if lg.name in pose.feet}
        skip: set[str] = set()
        for n in self.names:
            if n in skip:
                continue
            p = self.parent[n]
            Dp = D[p] if p is not None else pose.root
            if n in ik:
                lg = ik[n]
                target, foot_r = pose.feet[lg.name]
                hip = apply(Dp, lg.hip)
                pole = Dp[:3, :3] @ lg.pole
                knee, ankle, ok = two_bone_ik(hip, apply(pose.root, target), lg.l1, lg.l2, pole)
                if not ok:
                    short.append(lg.name)
                D[lg.upper] = _align(lg.hip, lg.knee - lg.hip, lg.pole, hip, knee - hip, pole)
                D[lg.lower] = _align(lg.knee, lg.ankle - lg.knee, lg.pole, knee, ankle - knee, pole)
                Rf = pose.root[:3, :3] @ foot_r
                Mf = np.eye(4)
                Mf[:3, :3] = Rf
                Mf[:3, 3] = ankle - Rf @ lg.ankle
                D[lg.foot] = Mf
                skip |= {lg.lower, lg.foot}
                continue
            R = pose.rot.get(n, np.eye(3))
            if p is None:  # the whole-body move rides on the root bone: Hips is joined to the
                # root's tail in the rig, and a joined bone cannot be moved, only turned
                mv = pose.move.get(n, np.zeros(3)) + pose.move.get("Hips", np.zeros(3))
            elif n == "Hips":
                mv = np.zeros(3)
            else:
                mv = pose.move.get(n, np.zeros(3))
            D[n] = Dp @ about(R, self.head[n], mv)
        return D, short

    def joint_positions(self, D: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        """Where every bone head and tail is under the deltas D ("<bone>.tail" for tails)."""
        out = {}
        for n in self.names:
            out[n] = apply(D[n], self.head[n])
            out[n + ".tail"] = apply(D[n], self.tail[n])
        return out


def _align(h0, u0, p0, h1, u1, p1) -> np.ndarray:
    """Rigid move taking point h0 to h1, direction u0 to u1, with the bend side p0 to p1."""
    R = frame(u1, p1) @ frame(u0, p0).T
    M = np.eye(4)
    M[:3, :3] = R
    M[:3, 3] = np.asarray(h1, float) - R @ np.asarray(h0, float)
    return M


__all__ = ["Body", "Leg", "Pose", "FWD", "LEFT", "UP", "unit"]
