"""The six procedural clips for each body type, made from the skeleton alone (never from text).

    idle    breathing and a slight sway, loops
    walk    loops; feet planted by IK from the gait generator (2 legs alternate, 4 legs walk)
    run     loops; 2 legs run with a flight phase, 4 legs trot
    attack  humanoid: a swipe with a lunge step; four-legged: a bite; bird: a peck
    hit     a short flinch
    faint   a collapse to the ground (humanoid falls forward, animals roll onto their side)

`make_clips(body)` returns Clip objects holding one Pose and one solved delta per frame. Loops
end on exactly their first frame, so the seam is invisible. Everything is in place: walk and
run carry the ground `speed` the game moves the character at so the feet do not slide.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from asset_forge.animate.body import FWD, LEFT, Body, Pose
from asset_forge.animate.curves import Keys
from asset_forge.animate.gait import BIPED, QUAD_TROT, QUAD_WALK, Gait
from asset_forge.animate.kin import UP, about, rot, rot_between, unit

FPS = 30
CLIP_NAMES = ("idle", "walk", "run", "attack", "hit", "faint")
LOOPING = ("idle", "walk", "run")
G = 9.81
REACH = 0.97  # a leg never stretches past 97% of its length (keeps the knee from snapping)
I3 = np.eye(3)


def pitch(a: float) -> np.ndarray:
    """Nose down / top forward for a > 0 (about the character's left axis)."""
    return rot(LEFT, a)


def yaw(a: float) -> np.ndarray:
    """Turn left for a > 0."""
    return rot(UP, a)


def roll(a: float) -> np.ndarray:
    """Lean right for a > 0 (about the forward axis)."""
    return rot(FWD, a)


@dataclass
class Clip:
    name: str
    fps: int
    loop: bool
    speed: float                      # ground speed in m/s (0 when standing)
    poses: list[Pose]
    deltas: list[dict] = field(default_factory=list)
    short: dict[str, int] = field(default_factory=dict)  # leg -> frames its foot fell short
    land_frame: int | None = None     # faint: the frame the body reaches the ground
    gait: Gait | None = None

    @property
    def frames(self) -> int:
        return len(self.poses)

    @property
    def seconds(self) -> float:
        return (self.frames - 1) / self.fps


def _periodic_cover(d: np.ndarray, r: int) -> np.ndarray:
    """Smooth periodic curve that is never below d: a wrap-around max filter, then a box blur of
    the same radius (every blurred sample averages values that are each >= d there)."""
    n = len(d)
    idx = (np.arange(n)[:, None] + np.arange(-r, r + 1)[None, :]) % n
    m = d[idx].max(axis=1)
    return m[idx].mean(axis=1)


class Animator:
    def __init__(self, body: Body):
        self.b = body
        self.L = body.leg_len
        self.H = body.height
        self.base = self._base()
        self.notes: list[str] = []
        for name in body.short_legs:
            self.notes.append(f"{name} leg is too short to reach the ground (the model holds that "
                              "foot up), so that foot steps a little above the ground.")

    # ------------------------------------------------------------------ helpers
    def _base(self) -> dict[str, np.ndarray]:
        """The standing pose every clip starts from. Humanoid: arms down by the sides, whatever
        the model was made in (T-pose or A-pose)."""
        b = self.b
        base: dict[str, np.ndarray] = {}
        if b.template == "humanoid":
            for side, s in (("Left", 1.0), ("Right", -1.0)):
                u = b.head[f"{side}LowerArm"] - b.head[f"{side}UpperArm"]
                base[f"{side}UpperArm"] = rot_between(u, unit([s * 0.2, -0.04, -1.0]))
                base[f"{side}LowerArm"] = self._elbow(side, 12.0)
        return base

    def _elbow(self, side: str, bend: float) -> np.ndarray:
        """Forearm forward by `bend` degrees, about the elbow's own hinge."""
        b = self.b
        u = b.tail[f"{side}LowerArm"] - b.head[f"{side}LowerArm"]
        return rot(unit(np.cross(u, FWD)), bend)

    def pose(self, rot_: dict | None = None, move: dict | None = None, feet: dict | None = None,
             root: np.ndarray | None = None, replace: dict | None = None) -> Pose:
        R = dict(self.base)
        for bone, Ra in (rot_ or {}).items():
            R[bone] = Ra @ R.get(bone, I3)
        R.update(replace or {})
        return Pose(R, {k: np.asarray(v, float) for k, v in (move or {}).items()}, feet or {},
                    root if root is not None else np.eye(4))

    def planted(self, shift: dict | None = None) -> dict:
        """Every foot on the ground at its rest spot (shift: leg -> (forward m, lift m))."""
        out = {}
        for lg in self.b.legs:
            f, z = (shift or {}).get(lg.name, (0.0, 0.0))
            out[lg.name] = (self.spot(lg, f, z), I3)
        return out

    def spot(self, lg, forward: float = 0.0, lift: float = 0.0) -> np.ndarray:
        return np.array([lg.ankle[0], lg.ankle[1], lg.ground_z]) + FWD * forward + UP * lift

    def cycle(self, k: float, minimum: int) -> int:
        """Frames per stride, scaled with leg length (same Froude number for every size), in
        steps of 4 so each foot lands on a whole frame; small bodies get a floor so the
        steps do not blur."""
        n = int(round(k * np.sqrt(self.L / G) * FPS / 4)) * 4
        return max(minimum, n)

    def drop_needed(self, lg, target: np.ndarray, hips_xy=(0.0, 0.0)) -> float:
        """How far the hip must come down so the leg reaches `target` at REACH."""
        hip = lg.hip + np.array([hips_xy[0], hips_xy[1], 0.0])
        horiz = float(np.linalg.norm((target - hip)[:2]))
        lim = REACH * lg.length
        if horiz >= lim:
            return float("inf")
        return max(0.0, float(hip[2] - target[2]) - float(np.sqrt(lim**2 - horiz**2)))

    def stroke(self, drop_max: float) -> float:
        """Longest stroke whose ends need at most `drop_max` of hip drop on every leg."""
        legs = [lg for lg in self.b.legs if lg.name not in self.b.short_legs] or self.b.legs

        def ok(S):
            return all(self.drop_needed(lg, self.spot(lg, sg * S / 2)) <= drop_max
                       for lg in legs for sg in (1, -1))

        lo, hi = 0.0, 1.2 * self.L
        if ok(hi):
            return hi
        for _ in range(40):
            mid = 0.5 * (lo + hi)
            lo, hi = (mid, hi) if ok(mid) else (lo, mid)
        return lo

    def finish(self, clip: Clip) -> Clip:
        for p in clip.poses:
            D, short = self.b.solve(p)
            clip.deltas.append(D)
            for s in short:
                clip.short[s] = clip.short.get(s, 0) + 1
        return clip

    # ------------------------------------------------------------------ walk and run
    def gait_clip(self, name: str, gait_kw: dict, crouch: float, bob_max: float,
                  compress: float, upper: Callable, swing_pitch: Callable) -> Clip:
        """crouch, bob_max, compress are fractions of leg length: the knee bend everywhere, the
        most the hips may dip at the stroke ends, an extra dip at mid-stance (running)."""
        S = self.stroke((crouch + bob_max) * self.L)
        g = Gait(stroke=S, fps=FPS, **gait_kw)
        n = g.frames
        sway = [upper(f / n, g)[1].get("Hips", np.zeros(3)) for f in range(n)]
        feet_all, need = [], np.zeros(n)
        for f in range(n):
            feet = {}
            for lg in self.b.legs:
                x, z, on, s = g.foot(lg.name, f)
                feet[lg.name] = (self.spot(lg, x, z), I3 if on else pitch(swing_pitch(s)))
                need[f] = max(need[f], self.drop_needed(lg, feet[lg.name][0], sway[f][:2]))
            feet_all.append(feet)
        need = np.minimum(need, 0.5 * self.L)
        drop = _periodic_cover(need, max(1, n // 16)) + crouch * self.L
        if compress:  # running: the knees give a little at mid-stance
            mids = sorted({(ph + g.duty / 2) % 1.0 for ph in g.phases.values()})
            phi = np.arange(n) / n
            wave = np.cos(2 * np.pi * len(mids) * (phi - mids[0]))
            drop += compress * self.L * (0.5 + 0.5 * wave)
        poses = []
        for f in range(n + 1):  # frame n repeats frame 0: the loop seam
            k = f % n
            rot_, move, rep = upper(k / n, g)
            hips = move.get("Hips", np.zeros(3)) + np.array([0.0, 0.0, -drop[k]])
            move = {**move, "Hips": hips}
            poses.append(self.pose(rot_, move, feet_all[k], replace=rep))
        return self.finish(Clip(name, FPS, True, g.speed, poses, gait=g))

    # ------------------------------------------------------------------ one-shot helper
    def keyed_clip(self, name: str, keys: Keys, frame_fn: Callable[[dict, float], Pose],
                   loop: bool = False) -> Clip:
        n = int(round(keys.end * FPS))
        poses = [frame_fn(keys.at(f / FPS), f / FPS) for f in range(n + 1)]
        return self.finish(Clip(name, FPS, loop, 0.0, poses))


# ====================================================================== humanoid
class Humanoid(Animator):
    def idle(self) -> Clip:
        n = 120
        L = self.L

        def frame(f):
            t = f / n
            br = np.sin(2 * np.pi * 2 * t)          # two breaths
            sw = np.sin(2 * np.pi * t)              # one slow sway
            r = {"Chest": pitch(-1.2 * br), "UpperChest": pitch(-0.8 * br),
                 "Hips": roll(-1.2 * sw), "Spine": roll(0.8 * sw),
                 "Neck": roll(0.4 * sw), "Head": yaw(3 * np.sin(2 * np.pi * t + 1.0)),
                 "LeftShoulder": roll(-1.0 * br), "RightShoulder": roll(1.0 * br),
                 "LeftUpperArm": pitch(1.5 * br) @ roll(1.0 * br),
                 "RightUpperArm": pitch(1.5 * br) @ roll(-1.0 * br)}
            mv = {"Hips": [0.012 * L * sw, 0.0, -0.02 * L - 0.004 * L * (0.5 + 0.5 * br)]}
            return self.pose(r, mv, self.planted())

        poses = [frame(f % n) for f in range(n + 1)]
        return self.finish(Clip("idle", FPS, True, 0.0, poses))

    def _upper(self, phi, g, run: bool):
        L = self.L
        c = np.cos(2 * np.pi * phi)
        side = np.cos(2 * np.pi * (phi - g.duty / 2))   # +1 over the left foot
        lean = 9.0 if run else 3.0
        swing = 30.0 if run else 14.0
        elbow = 80.0 if run else 18.0
        r = {"Hips": yaw(-(7 if run else 5) * c) @ roll(-2.5 * side),
             "Spine": pitch(lean * 0.5) @ yaw((5 if run else 4) * c),
             "Chest": pitch(lean * 0.5) @ yaw((5 if run else 3) * c),
             "Neck": pitch(-lean * 0.5),
             "Head": pitch(-lean * 0.5) @ yaw(-(3 if run else 2) * c),
             "LeftUpperArm": pitch(swing * c), "RightUpperArm": pitch(-swing * c)}
        rep = {"LeftLowerArm": self._elbow("Left", elbow + (12 if run else 6) * max(0, -c)),
               "RightLowerArm": self._elbow("Right", elbow + (12 if run else 6) * max(0, c))}
        mv = {"Hips": np.array([(0.012 if run else 0.025) * L * side, 0.0, 0.0])}
        return r, mv, rep

    def _gait(self, name, run):
        def upper(phi, g):
            return self._upper(phi, g, run)

        if run:
            kw = dict(frames=self.cycle(2.3, 16), duty=0.36, lift=0.24 * self.L, phases=BIPED)
            return self.gait_clip(name, kw, 0.07, 0.05, 0.03, upper,
                                  lambda s: 28 * np.sin(np.pi * s) ** 2)
        kw = dict(frames=self.cycle(3.6, 24), duty=0.62, lift=0.09 * self.L, phases=BIPED)
        return self.gait_clip(name, kw, 0.02, 0.05, 0.0, upper,
                              lambda s: 14 * np.sin(np.pi * s) * (1 - 1.3 * s))

    def walk(self) -> Clip:
        return self._gait("walk", False)

    def run(self) -> Clip:
        return self._gait("run", True)

    def attack(self) -> Clip:
        """Right-hand swipe with a lunge step of the left foot."""
        L = self.L
        k = Keys([0.0, 0.30, 0.42, 0.55, 0.92],
                 hx=[0, -0.03, 0.16, 0.15, 0], hz=[0, 0.04, 0.10, 0.09, 0],
                 tyaw=[0, -28, 30, 26, 0], tpitch=[0, -4, 14, 12, 0],
                 rraise=[0, 115, 40, 15, 0], rfwd=[0, -20, -75, -50, 0],
                 racross=[0, 0, 35, 45, 0], relbow=[12, 70, 10, 20, 12],
                 lfwd=[0, -35, -10, 0, 0], lelbow=[12, 70, 40, 25, 12],
                 hd=[0, -8, 6, 4, 0])
        # the left foot steps out (lands at 0.30 s, before the blow) and back (lands at 0.88 s);
        # it only moves while it is off the ground, so it never slides
        # (the foot lifts before it moves and stops moving before it touches down)
        reach = Keys([0.0, 0.03, 0.15, 0.27, 0.65, 0.75, 0.85, 0.92],
                     s=[0, 0, 0.45, 1.0, 1.0, 0.55, 0, 0])
        lift = Keys([0.0, 0.12, 0.30, 0.62, 0.75, 0.88, 0.92], z=[0, 0.07, 0, 0, 0.06, 0, 0])
        stride = 0.42 * L
        left = self.b.leg("Left")

        def frame(c, t):
            r = {"Hips": yaw(c["tyaw"] * 0.4),
                 "Spine": yaw(c["tyaw"] * 0.3) @ pitch(c["tpitch"] * 0.5),
                 "Chest": yaw(c["tyaw"] * 0.3) @ pitch(c["tpitch"] * 0.5),
                 "Head": yaw(-c["tyaw"] * 0.6) @ pitch(c["hd"] - c["tpitch"] * 0.6),
                 "RightUpperArm": yaw(-c["racross"]) @ pitch(c["rfwd"]) @ roll(-c["rraise"]),
                 "LeftUpperArm": pitch(c["lfwd"]) @ roll(10)}
            rep = {"RightLowerArm": self._elbow("Right", c["relbow"]),
                   "LeftLowerArm": self._elbow("Left", c["lelbow"])}
            feet = self.planted()
            feet["Left"] = (self.spot(left, stride * reach.at(t)["s"], lift.at(t)["z"] * L), I3)
            mv = {"Hips": FWD * c["hx"] * L + np.array([0.0, 0.0, -0.02 * L - c["hz"] * L])}
            return self.pose(r, mv, feet, replace=rep)

        return self.keyed_clip("attack", k, frame)

    def hit(self) -> Clip:
        L = self.L
        k = Keys([0.0, 0.07, 0.20, 0.33, 0.5],
                 hx=[0, -0.06, -0.05, 0.01, 0], hz=[0, 0.03, 0.04, 0.01, 0],
                 back=[0, -14, -10, 2, 0], head=[0, -18, -6, 3, 0], arms=[0, -22, -15, 0, 0],
                 elbow=[12, 55, 40, 15, 12], twist=[0, 8, 6, 0, 0])
        def frame(c, t):
            r = {"Spine": pitch(c["back"] * 0.4) @ yaw(c["twist"]),
                 "Chest": pitch(c["back"] * 0.6), "Head": pitch(c["head"]),
                 "LeftUpperArm": pitch(c["arms"]) @ roll(-c["arms"] * 0.3),
                 "RightUpperArm": pitch(c["arms"]) @ roll(c["arms"] * 0.3)}
            rep = {"LeftLowerArm": self._elbow("Left", c["elbow"]),
                   "RightLowerArm": self._elbow("Right", c["elbow"])}
            mv = {"Hips": FWD * c["hx"] * L + np.array([0.0, 0.0, -0.02 * L - c["hz"] * L])}
            return self.pose(r, mv, self.planted(), replace=rep)

        return self.keyed_clip("hit", k, frame)

    def faint(self) -> Clip:
        """Knees buckle, the body falls forward onto the ground, a small bounce, lies still."""
        L = self.L
        k = Keys([0.0, 0.32, 0.45, 0.88, 0.97, 1.06, 1.6],
                 hz=[0, 0.30, 0.30, 0.10, 0.08, 0.06, 0.06],
                 chest=[0, 22, 26, 6, 4, 4, 4], head=[0, 28, 30, 5, 5, 5, 5],
                 hyaw=[0, 0, 10, 70, 72, 72, 72], arms=[0, -12, -18, -35, -30, -30, -30],
                 out=[0, 5, 8, 25, 25, 25, 25], elbow=[12, 20, 25, 30, 30, 30, 30],
                 fall=[0, 0, 4, 88, 83, 88, 88])
        pivot = self._front_pivot()
        land = int(round(0.88 * FPS))

        def frame(c, t):
            r = {"Spine": pitch(c["chest"] * 0.4), "Chest": pitch(c["chest"] * 0.6),
                 "Head": pitch(c["head"] * 0.5) @ yaw(c["hyaw"]), "Neck": pitch(c["head"] * 0.5),
                 "LeftUpperArm": pitch(c["arms"]) @ roll(c["out"]),
                 "RightUpperArm": pitch(c["arms"]) @ roll(-c["out"])}
            rep = {"LeftLowerArm": self._elbow("Left", c["elbow"]),
                   "RightLowerArm": self._elbow("Right", c["elbow"])}
            mv = {"Hips": np.array([0.0, 0.0, -0.02 * L - c["hz"] * L])}
            root = about(pitch(c["fall"]), pivot)
            return self.pose(r, mv, self.planted(), root=root, replace=rep)

        clip = self.keyed_clip("faint", k, frame)
        clip.land_frame = land
        return clip

    def _front_pivot(self) -> np.ndarray:
        pts = np.array([*self.b.head.values(), *self.b.tail.values()])
        return np.array([0.0, float(pts[:, 1].min()), 0.0])


# ====================================================================== four-legged
class FourLegged(Animator):
    def _len(self) -> float:
        return float(np.linalg.norm((self.b.head["Head"] - self.b.head["Hips"])[:2]))

    def _tail(self, a: float, ph: float = 0.0, lift: float = 0.0, n: int = 4) -> dict:
        return {f"Tail{i}": yaw(a * np.sin(ph - 0.7 * i)) @ pitch(lift / n)
                for i in range(1, n + 1)}

    def idle(self) -> Clip:
        n = 120
        L = self.L

        def frame(f):
            t = f / n
            br = np.sin(2 * np.pi * 3 * t)
            r = {"Spine": pitch(-1.0 * br), "Chest": pitch(-0.8 * br),
                 "Neck1": yaw(7 * np.sin(2 * np.pi * t)) @ pitch(2 * np.sin(4 * np.pi * t)),
                 "Head": yaw(5 * np.sin(2 * np.pi * t - 0.8)) @ pitch(-2 * np.sin(4 * np.pi * t)),
                 **self._tail(10, 2 * np.pi * 2 * t, 6)}
            mv = {"Hips": [0.01 * L * np.sin(2 * np.pi * t), 0.0, -0.02 * L - 0.005 * L * br]}
            return self.pose(r, mv, self.planted())

        return self.finish(Clip("idle", FPS, True, 0.0, [frame(f % n) for f in range(n + 1)]))

    def _gait(self, name: str, trot: bool) -> Clip:
        def upper(phi, g):
            w = 2 * np.pi * phi
            r = {"Spine": yaw(4 * np.sin(w)) @ pitch((2.5 if trot else 1) * np.sin(2 * w)),
                 "Chest": yaw(-3 * np.sin(w)),
                 "Neck1": pitch((4 if trot else 3) * np.sin(2 * w + 0.5)),
                 "Head": pitch(-(4 if trot else 3) * np.sin(2 * w + 0.5)) @ yaw(2 * np.sin(w)),
                 "Hips": roll(2 * np.sin(w)),
                 **self._tail(12 if trot else 8, w, 14 if trot else 4)}
            return r, {}, {}

        curl = lambda s: 40 * np.sin(np.pi * s)  # noqa: E731
        if trot:
            kw = dict(frames=self.cycle(2.3, 16), duty=0.42, lift=0.22 * self.L, phases=QUAD_TROT)
            return self.gait_clip(name, kw, 0.05, 0.05, 0.03, upper, curl)
        kw = dict(frames=self.cycle(3.6, 24), duty=0.70, lift=0.16 * self.L, phases=QUAD_WALK)
        return self.gait_clip(name, kw, 0.03, 0.04, 0.0, upper, curl)

    def walk(self) -> Clip:
        return self._gait("walk", False)

    def run(self) -> Clip:
        return self._gait("run", True)

    def attack(self) -> Clip:
        """Bite: weight back with the head up, a lunge forward and a snap, back to stand."""
        L, BL = self.L, self._len()
        k = Keys([0.0, 0.28, 0.40, 0.52, 0.85],
                 hx=[0, -0.06, 0.10, 0.09, 0], hz=[0, 0.06, 0.10, 0.09, 0],
                 lean=[0, -4, 8, 7, 0], neck=[0, -18, 20, 16, 0], head=[0, -12, 16, 10, 0],
                 tail=[0, 10, -6, -4, 0])

        def frame(c, t):
            r = {"Spine": pitch(c["lean"] * 0.5), "Chest": pitch(c["lean"] * 0.5),
                 "Neck1": pitch(c["neck"] * 0.6), "Neck2": pitch(c["neck"] * 0.4),
                 "Head": pitch(c["head"]), **self._tail(0, 0, c["tail"] * 4)}
            mv = {"Hips": FWD * c["hx"] * BL + np.array([0.0, 0.0, -0.02 * L - c["hz"] * L])}
            return self.pose(r, mv, self.planted())

        return self.keyed_clip("attack", k, frame)

    def hit(self) -> Clip:
        L, BL = self.L, self._len()
        k = Keys([0.0, 0.07, 0.20, 0.33, 0.5],
                 hx=[0, -0.05, -0.04, 0.01, 0], hz=[0, 0.05, 0.05, 0.01, 0],
                 side=[0, 0.03, 0.02, 0, 0], neck=[0, -16, -8, 2, 0], tail=[0, -25, -18, -3, 0],
                 roll_=[0, 5, 3, 0, 0])

        def frame(c, t):
            r = {"Neck1": pitch(c["neck"]), "Head": pitch(c["neck"] * 0.5),
                 "Hips": roll(c["roll_"]), **self._tail(0, 0, c["tail"] * 4)}
            mv = {"Hips": FWD * c["hx"] * BL + LEFT * c["side"] * BL
                  + np.array([0.0, 0.0, -0.02 * L - c["hz"] * L])}
            return self.pose(r, mv, self.planted())

        return self.keyed_clip("hit", k, frame)

    def faint(self) -> Clip:
        """Legs fold, the body sinks, then rolls onto its right side and lies still."""
        b = self.b
        sink = min(lg.hip[2] - lg.ground_z for lg in b.legs)
        k = Keys([0.0, 0.35, 0.48, 0.90, 0.99, 1.08, 1.6],
                 hz=[0, 0.45, 0.50, 0.40, 0.40, 0.40, 0.40], neck=[0, 18, 22, 10, 8, 8, 8],
                 tail=[0, -10, -15, -5, -5, -5, -5], fall=[0, 0, 5, 86, 80, 86, 86])
        pts = np.array([*b.head.values(), *b.tail.values()])
        pivot = np.array([float(pts[:, 0].min()), float(np.median(pts[:, 1])), 0.0])

        def frame(c, t):
            r = {"Neck1": pitch(c["neck"]), "Head": pitch(c["neck"] * 0.6),
                 **self._tail(0, 0, c["tail"] * 4)}
            mv = {"Hips": np.array([0.0, 0.0, -c["hz"] * sink])}
            return self.pose(r, mv, self.planted(), root=about(roll(c["fall"]), pivot))

        clip = self.keyed_clip("faint", k, frame)
        clip.land_frame = int(round(0.90 * FPS))
        return clip


# ====================================================================== bird
class Bird(Animator):
    def _wings(self, open_: float, raise_: float) -> dict:
        """Wings out from the body (open, degrees) and up (raise, degrees)."""
        out = {}
        for side, s in (("Left", 1.0), ("Right", -1.0)):
            out[f"{side}Wing1"] = roll(s * raise_) @ yaw(-s * open_)
        return out

    def idle(self) -> Clip:
        n = 120
        L = self.L
        look = Keys([0, 0.4, 0.55, 1.5, 1.65, 2.5, 2.62, 3.4, 4.0],
                    y=[0, 0, 25, 25, -18, -18, 6, 6, 0], p=[0, 0, -6, -6, 4, 4, 0, 0, 0])

        def frame(f):
            t = f / n
            br = np.sin(2 * np.pi * 4 * t)
            c = look.at(t * 4.0)
            r = {"Chest": pitch(-1.5 * br), "Neck2": yaw(c["y"] * 0.4),
                 "Head": yaw(c["y"] * 0.6) @ pitch(c["p"]),
                 "Tail1": pitch(4 * max(0.0, np.sin(2 * np.pi * 3 * t)) ** 4),
                 **self._wings(0, 1.5 * br)}
            mv = {"Hips": [0.0, 0.0, -0.02 * L - 0.01 * L * (0.5 + 0.5 * br)]}
            return self.pose(r, mv, self.planted())

        return self.finish(Clip("idle", FPS, True, 0.0, [frame(f % n) for f in range(n + 1)]))

    def _gait(self, name: str, run: bool) -> Clip:
        def upper(phi, g):
            w = 2 * np.pi * phi
            side = np.cos(w - np.pi * g.duty)
            r = {"Hips": roll(-4 * side) @ pitch(10 if run else 0) @ yaw(3 * np.cos(w)),
                 "Neck1": pitch(-(10 if run else 0) * 0.5 + 7 * np.sin(2 * w)),
                 "Head": pitch(-(10 if run else 0) * 0.5 - 7 * np.sin(2 * w + 0.6)),
                 "Tail1": pitch(5 * np.sin(2 * w)),
                 **self._wings(12 if run else 0, (14 if run else 1) + 3 * np.sin(2 * w))}
            return r, {"Hips": np.array([0.015 * self.L * side, 0.0, 0.0])}, {}

        curl = lambda s: 45 * np.sin(np.pi * s)  # noqa: E731
        if run:
            kw = dict(frames=self.cycle(2.3, 16), duty=0.38, lift=0.28 * self.L, phases=BIPED)
            return self.gait_clip(name, kw, 0.08, 0.06, 0.03, upper, curl)
        kw = dict(frames=self.cycle(3.6, 24), duty=0.6, lift=0.22 * self.L, phases=BIPED)
        return self.gait_clip(name, kw, 0.04, 0.05, 0.0, upper, curl)

    def walk(self) -> Clip:
        return self._gait("walk", False)

    def run(self) -> Clip:
        return self._gait("run", True)

    def attack(self) -> Clip:
        """Peck: neck draws back with the wings up, then strikes forward and down."""
        L = self.L
        k = Keys([0.0, 0.26, 0.38, 0.50, 0.82],
                 lean=[0, -8, 18, 15, 0], neck=[0, -25, 30, 25, 0], head=[0, -10, 20, 14, 0],
                 wopen=[0, 25, 10, 8, 0], wraise=[0, 35, 10, 8, 0], hz=[0, 0.04, 0.08, 0.07, 0])

        def frame(c, t):
            r = {"Hips": pitch(c["lean"]), "Neck1": pitch(c["neck"] * 0.6),
                 "Neck2": pitch(c["neck"] * 0.4), "Head": pitch(c["head"]),
                 **self._wings(c["wopen"], c["wraise"])}
            mv = {"Hips": np.array([0.0, 0.0, -0.02 * L - c["hz"] * L])}
            return self.pose(r, mv, self.planted())

        return self.keyed_clip("attack", k, frame)

    def hit(self) -> Clip:
        L = self.L
        k = Keys([0.0, 0.07, 0.20, 0.33, 0.5],
                 back=[0, -12, -8, 2, 0], neck=[0, -20, -10, 3, 0], wopen=[0, 30, 20, 3, 0],
                 wraise=[0, 40, 25, 4, 0], hz=[0, 0.05, 0.05, 0.01, 0], hx=[0, -0.08, -0.06, 0, 0])

        def frame(c, t):
            r = {"Hips": pitch(c["back"]), "Neck1": pitch(c["neck"]),
                 "Head": pitch(c["neck"] * 0.5),
                 **self._wings(c["wopen"], c["wraise"])}
            mv = {"Hips": FWD * c["hx"] * L + np.array([0.0, 0.0, -0.02 * L - c["hz"] * L])}
            return self.pose(r, mv, self.planted())

        return self.keyed_clip("hit", k, frame)

    def faint(self) -> Clip:
        b = self.b
        sink = min(lg.hip[2] - lg.ground_z for lg in b.legs)
        k = Keys([0.0, 0.35, 0.48, 0.90, 0.99, 1.08, 1.6],
                 hz=[0, 0.55, 0.6, 0.5, 0.5, 0.5, 0.5], neck=[0, 25, 30, 15, 12, 12, 12],
                 wopen=[0, 10, 15, 35, 35, 35, 35], wraise=[0, 5, 10, -10, -10, -10, -10],
                 fall=[0, 0, 6, 84, 78, 84, 84])
        pts = np.array([*b.head.values(), *b.tail.values()])
        pivot = np.array([float(pts[:, 0].min()), float(np.median(pts[:, 1])), 0.0])

        def frame(c, t):
            r = {"Neck1": pitch(c["neck"]), "Head": pitch(c["neck"] * 0.6),
                 **self._wings(c["wopen"], c["wraise"])}
            mv = {"Hips": np.array([0.0, 0.0, -c["hz"] * sink])}
            return self.pose(r, mv, self.planted(), root=about(roll(c["fall"]), pivot))

        clip = self.keyed_clip("faint", k, frame)
        clip.land_frame = int(round(0.90 * FPS))
        return clip


ANIMATORS = {"humanoid": Humanoid, "four_legged": FourLegged, "bird": Bird}


def animator(body: Body) -> Animator:
    return ANIMATORS[body.template](body)


def make_clips(body: Body, names=CLIP_NAMES) -> list[Clip]:
    a = animator(body)
    return [getattr(a, n)() for n in names]


def ground_offsets(min_z: np.ndarray, land_frame: int | None) -> np.ndarray:
    """Upward shift per frame that keeps the body out of the ground; from `land_frame` on it
    also pulls a floating body down, so a fainted body lies on the ground, not above it."""
    z = np.asarray(min_z, float)
    up = np.maximum(-z, 0.0)
    if land_frame is not None:
        up[land_frame:] = -z[land_frame:]
    return up
