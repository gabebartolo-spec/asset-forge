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

FPS = 30            # keys per second; small bodies step fast and get FAST_FPS
FAST_FPS = 60
MIN_RUN_KEYS = 12   # a run stride shorter than this many keys at FPS is keyed at FAST_FPS
CLIP_NAMES = ("idle", "walk", "run", "attack", "hit", "faint")
LOOPING = ("idle", "walk", "run")
G = 9.81
REACH = 0.97  # a leg never stretches past 97% of its length (keeps the knee from snapping)
I3 = np.eye(3)

# Gait speed by the Froude number Fr = v^2 / (g L) (L = leg length): animals of every size
# that move alike move at the same Fr, so a small animal steps fast instead of shuffling.
# Walk ~0.25 for quadrupeds and birds; run/trot between 1 and 2.5. People: L here is hip to
# ankle, so a free adult walk (1.37 m/s, Perry and Burnfield 2010; L about 0.83 m) is Fr ~0.2.
FROUDE = {"walk": {"humanoid": 0.20, "four_legged": 0.25, "bird": 0.25},
          "run": {"humanoid": 1.5, "four_legged": 2.0, "bird": 1.5}}

# People take longer strides than the all-animal rule gives, in leg lengths (L hip to ankle):
# walk 1.41 m at L ~0.83 m = 1.7 (Perry and Burnfield 2010: 113 steps/min); run about 2.5 m at
# 3.5 m/s = 3.0 (about 165 steps/min, Cavanagh and Kram 1989).
HUMAN_STRIDE = {"walk": 1.65, "run": 3.0}

# Readability cap on cadence (lead decision, 2026-10-20). At game scale a small animal stepping
# at its Froude cadence strobes (a fox trot at 4.3 strides/s, a bird run at 6): the legs blur and
# the gait cannot be read. A walk shows at most 2 strides a second (a cycle of 0.5 s or more), a
# trot or run at most 3 (0.33 s or more). The stride stays what the legs reach, so a capped gait
# simply moves slower (a small bird walks at about 0.2 m/s). People never reach the cap.
MAX_STRIDES_PER_S = {"walk": 2.0, "run": 3.0}

# A four-legged animal's hind leg is two bones here (the thigh, then stifle to paw: shin and hock
# in one). Reaching far behind the hip with the stifle forward lays that lower bone flat along
# the ground (the triposg fox dragged a hind leg). Its lean from vertical is capped: the stroke
# is shortened at the back until every frame keeps under it.
HIND_SHIN_MAX_DEG = 45.0


def froude_speed(fr: float, leg: float) -> float:
    """Ground speed in m/s at Froude number `fr` for a leg `leg` metres long."""
    return float(np.sqrt(fr * G * leg))


def stride_length(fr: float, leg: float) -> float:
    """One full stride (a cycle) in metres, by Alexander's dynamic-similarity rule
    stride / leg = 2.3 Fr^0.3 (Alexander 1976, fitted to mammals including people, and birds)."""
    return 2.3 * fr**0.3 * leg


def _quantum(phases: dict[str, float]) -> int:
    """Smallest frame step that puts every foot's landing on a whole frame."""
    for q in (2, 4, 8):
        if all(abs(ph * q - round(ph * q)) < 1e-9 for ph in phases.values()):
            return q
    return 8


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
    froude: float = 0.0               # v^2 / (g L) of walk and run
    capped: bool = False              # cadence held at MAX_STRIDES_PER_S (slower than Froude)

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
        self.fps = self._fps()
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

    def _fps(self) -> int:
        fr = FROUDE["run"][self.b.template]
        stride_s = max(self.stride("run") / froude_speed(fr, self.L),
                       1.0 / MAX_STRIDES_PER_S["run"])
        return FPS if stride_s * FPS >= MIN_RUN_KEYS else FAST_FPS

    def stride(self, name: str) -> float:
        """The stride (metres per cycle) a gait wants: people by their own gait data, animals
        and birds by Alexander's rule."""
        if self.b.template == "humanoid":
            return HUMAN_STRIDE[name] * self.L
        return stride_length(FROUDE[name][self.b.template], self.L)

    def plan(self, fr: float, duty: float, phases: dict, most: float,
             stride: float | None = None, cap: float | None = None) -> tuple[int, float, bool]:
        """(frames per stride, stroke, capped) for a gait at Froude number `fr`: the speed is
        fixed by Fr, the stride by `stride` (default Alexander's rule), shortened when the leg
        cannot reach (`most`, the longest stroke the hip drop allows); the cadence follows.
        Frames come in steps that land every foot on a whole frame; the stroke is then set so
        the speed stays exactly the Froude speed. When that cadence is above `cap` strides a
        second (MAX_STRIDES_PER_S) the cycle is lengthened to the cap and the stroke kept, so
        the gait moves slower than its Froude speed."""
        v = froude_speed(fr, self.L)
        want = min(duty * (stride if stride is not None else stride_length(fr, self.L)), most)
        q = _quantum(phases)
        exact = want / (duty * v) * self.fps
        n = max(q, int(round(exact / q)) * q)
        if v * duty * n / self.fps > most + 1e-9:
            n = max(q, int(exact // q) * q)
        if cap is not None and n / self.fps < 1.0 / cap - 1e-9:
            return int(np.ceil(self.fps / cap / q - 1e-9)) * q, want, True
        return n, v * duty * n / self.fps, False

    def drop_needed(self, lg, target: np.ndarray, hips_xy=(0.0, 0.0)) -> float:
        """How far the hip must come down so the leg reaches `target` at REACH."""
        hip = lg.hip + np.array([hips_xy[0], hips_xy[1], 0.0])
        horiz = float(np.linalg.norm((target - hip)[:2]))
        lim = REACH * lg.length
        if horiz >= lim:
            return float("inf")
        return max(0.0, float(hip[2] - target[2]) - float(np.sqrt(lim**2 - horiz**2)))

    def pivot(self, lg) -> np.ndarray:
        """The point a lifting heel turns about: the toe tip, or the paw tip. (A person's fitted
        ball joint sits under the ankle, so turning about it would not lengthen the stride.)"""
        return lg.tip

    def heel(self, lg) -> np.ndarray:
        """The point a landing foot rocks on before it lies flat: a person's heel, on the
        ground a little behind the ankle. Animals land on the paw (no heel strike)."""
        return np.array([lg.ankle[0], lg.ankle[1], lg.tip[2]]) - FWD * 0.035 * self.H

    def roll_offset(self, lg, deg: float) -> np.ndarray:
        """How the ankle moves when the heel lifts by `deg` about the pivot."""
        return (pitch(deg) - I3) @ (lg.ankle - self.pivot(lg))

    def strike_offset(self, lg, deg: float) -> np.ndarray:
        """How the ankle moves when the toes are up by `deg` with the heel on the ground."""
        return (pitch(-deg) - I3) @ (lg.ankle - self.heel(lg)) if deg else np.zeros(3)

    def lean_limited(self, lg) -> bool:
        """Legs whose lower bone may not lean past HIND_SHIN_MAX_DEG: a four-legged animal's
        hind legs (see the constant)."""
        return self.b.template == "four_legged" and lg.group == "Hind"

    def stroke(self, drop_max: float, roll: float = 0.0, strike: float = 0.0,
               back: float = 1.0) -> tuple[float, dict[str, float]]:
        """The longest stroke every leg can make with at most `drop_max` of hip drop, and where
        each leg's stroke is centred (forward offset from its rest spot). A leg reaches some
        way ahead of its hip and, with the heel lifted by `roll` degrees at push-off, further
        behind it, and with the toes up by `strike` degrees at heel strike, further ahead; its
        stroke sits in the middle of that window. `back` scales how far behind the hip the
        lean-limited legs reach."""
        legs = [lg for lg in self.b.legs if lg.name not in self.b.short_legs] or self.b.legs

        def reach(lg, sg):
            under = float((lg.hip - lg.ankle) @ FWD)  # the spot under the hip

            def ok(x):
                p = self.spot(lg, under + sg * x)
                off = self.roll_offset(lg, roll) if sg < 0 else self.strike_offset(lg, strike)
                return self.drop_needed(lg, p + off) <= drop_max

            lo, hi = 0.0, 1.2 * self.L
            if not ok(lo):
                return under, 0.0
            for _ in range(40):
                mid = 0.5 * (lo + hi)
                lo, hi = (mid, hi) if ok(mid) else (lo, mid)
            return under, lo

        win = {}
        for lg in self.b.legs:
            under, ahead = reach(lg, 1)
            _, behind = reach(lg, -1)
            if self.lean_limited(lg):
                behind *= back
            win[lg.name] = (under + (ahead - behind) / 2, ahead + behind)
        S = min(win[lg.name][1] for lg in legs)
        return S, {k: v[0] for k, v in win.items()}

    def finish(self, clip: Clip) -> Clip:
        for p in clip.poses:
            D, short = self.b.solve(p)
            clip.deltas.append(D)
            for s in short:
                clip.short[s] = clip.short.get(s, 0) + 1
        return clip

    # ------------------------------------------------------------------ walk and run
    def gait_clip(self, name: str, gait_kw: dict, crouch: float, bob_max: float,
                  compress: float, upper: Callable, swing_pitch: Callable,
                  roll: float = 30.0, strike: float = 0.0) -> Clip:
        """gait_kw: duty, lift, phases. crouch, bob_max, compress are fractions of leg length:
        the knee bend everywhere, the most the hips may dip at the stroke ends, an extra dip at
        mid-stance (running). roll: degrees the heel lifts at push-off; strike: degrees the
        toes are up when the heel lands. The speed comes from FROUDE[name], the stride from
        self.stride(name)."""
        clip = None
        for k in range(12):  # shorten the hind legs' back reach until no lower leg lies flat
            clip = self._gait_clip(name, gait_kw, crouch, bob_max, compress, upper, swing_pitch,
                                   roll, strike, 0.88**k)
            if self.max_lean(clip) <= HIND_SHIN_MAX_DEG:
                break
        return clip

    def max_lean(self, clip: Clip) -> float:
        """The most a lean-limited leg's lower bone leans from vertical (degrees) while its foot
        is near the ground (below half the swing lift): low and flat is a drag; a foot lifted
        higher is a tucked leg, which may fold further."""
        legs = [lg for lg in self.b.legs if self.lean_limited(lg)]
        near = 0.5 * clip.gait.lift if clip.gait else 0.0
        worst = 0.0
        for D in clip.deltas if legs else []:
            P = self.b.joint_positions(D)
            for lg in legs:
                if P[lg.foot][2] - lg.ground_z >= near:
                    continue
                u = unit(P[lg.foot] - P[lg.lower])
                worst = max(worst, float(np.degrees(np.arccos(np.clip(-u[2], -1.0, 1.0)))))
        return worst

    def _gait_clip(self, name, gait_kw, crouch, bob_max, compress, upper, swing_pitch, roll,
                   strike, back) -> Clip:
        fr = FROUDE[name][self.b.template]
        most, centre = self.stroke((crouch + bob_max) * self.L, roll, strike, back)
        frames, S, capped = self.plan(fr, gait_kw["duty"], gait_kw["phases"], most,
                                      self.stride(name), MAX_STRIDES_PER_S[name])
        early = tuple(lg.name for lg in self.b.legs if self.lean_limited(lg))
        g = Gait(frames=frames, stroke=S, fps=self.fps, early=early, **gait_kw)
        n = g.frames
        sway = [upper(f / n, g)[1].get("Hips", np.zeros(3)) for f in range(n)]
        feet_all, need = [], np.zeros(n)
        for f in range(n):
            feet = {}
            for lg in self.b.legs:
                x, z, on, s = g.foot(lg.name, f)
                a = roll * g.roll(lg.name, f)
                h = strike * g.strike(lg.name, f)
                feet[lg.name] = (self.spot(lg, centre[lg.name] + x, z)
                                 + self.roll_offset(lg, a) + self.strike_offset(lg, h),
                                 pitch(a - h) if on else pitch(a - h + swing_pitch(s)))
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
        return self.finish(Clip(name, self.fps, True, g.speed, poses, gait=g,
                                froude=g.speed**2 / (G * self.L), capped=capped))

    # ------------------------------------------------------------------ one-shot helper
    def keyed_clip(self, name: str, keys: Keys, frame_fn: Callable[[dict, float], Pose],
                   loop: bool = False) -> Clip:
        n = int(np.ceil(keys.end * self.fps - 1e-9))  # the last frame reaches the last key
        poses = [frame_fn(keys.at(f / self.fps), f / self.fps) for f in range(n + 1)]
        return self.finish(Clip(name, self.fps, loop, 0.0, poses))


# ====================================================================== humanoid
class Humanoid(Animator):
    def idle(self) -> Clip:
        n = 4 * self.fps
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
        return self.finish(Clip("idle", self.fps, True, 0.0, poses))

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
            kw = dict(duty=0.36, lift=0.24 * self.L, phases=BIPED)
            return self.gait_clip(name, kw, 0.07, 0.05, 0.03, upper,
                                  lambda s: 28 * np.sin(np.pi * s) ** 2, roll=35.0, strike=8.0)
        # walk: heel strike (toes up ~15 deg) and push-off over the toes (heel up ~45 deg) give
        # the stride its length; the hips dip no more than 7.5% of the leg
        kw = dict(duty=0.62, lift=0.09 * self.L, phases=BIPED)
        return self.gait_clip(name, kw, 0.02, 0.055, 0.0, upper,
                              lambda s: 14 * np.sin(np.pi * s) * (1 - 1.3 * s),
                              roll=45.0, strike=15.0)

    def walk(self) -> Clip:
        return self._gait("walk", False)

    def run(self) -> Clip:
        return self._gait("run", True)

    def attack(self) -> Clip:
        """A right-hand swipe: the wind-up cocks the arm up and back with the torso turned
        away, the strike sweeps it fast round the right side and across the body while the
        left foot steps out and the hips drive into the lunge, a short recoil, back to stand.
        The step is shortened until the leg reaches it on every frame."""
        clip = None
        for k in range(8):
            clip = self._attack(0.42 * 0.9**k)
            if not clip.short:
                break
        return clip

    def _attack(self, stride_frac: float) -> Clip:
        L = self.L
        # keys: rest, wind-up, strike (arm level, out front), follow-through, recoil, rest.
        # The upper arm's direction is keyed as angles in the chest's frame, so the sweep is
        # an arc, not a reach: el from straight down (0) through level (90) to up (180); az
        # round the body: 0 out to the right side, 90 forward, 180 the left side, -90 back.
        k = Keys([0.0, 0.26, 0.33, 0.40, 0.52, 0.90],
                 hx=[0, -0.04, 0.12, 0.17, 0.13, 0], hz=[0, 0.03, 0.08, 0.10, 0.08, 0],
                 tyaw=[0, -35, 10, 38, 28, 0], tpitch=[0, -6, 10, 16, 10, 0],
                 el=[12, 140, 85, 50, 55, 12], az=[10, -40, 55, 120, 105, 10],
                 relbow=[12, 70, 20, 15, 35, 12],
                 lfwd=[0, -40, -20, 10, 0, 0], lelbow=[12, 70, 50, 30, 25, 12],
                 hd=[0, -6, 4, 6, 3, 0])
        # the left foot steps out (lands at 0.30 s, as the strike starts) and back (lands at
        # 0.86 s); it only moves while it is off the ground, so it never slides
        reach = Keys([0.0, 0.03, 0.15, 0.27, 0.62, 0.70, 0.80, 0.86],
                     s=[0, 0, 0.45, 1.0, 1.0, 0.55, 0, 0])
        lift = Keys([0.0, 0.12, 0.30, 0.58, 0.72, 0.86, 0.90], z=[0, 0.07, 0, 0, 0.06, 0, 0])
        stride = stride_frac * L
        left = self.b.leg("Left")
        arm = self.b.head["RightLowerArm"] - self.b.head["RightUpperArm"]

        def aim(el, az):
            e, a = np.radians(el), np.radians(az)
            return np.array([-np.cos(a) * np.sin(e), -np.sin(a) * np.sin(e), -np.cos(e)])

        def frame(c, t):
            r = {"Hips": yaw(c["tyaw"] * 0.4),
                 "Spine": yaw(c["tyaw"] * 0.3) @ pitch(c["tpitch"] * 0.5),
                 "Chest": yaw(c["tyaw"] * 0.3) @ pitch(c["tpitch"] * 0.5),
                 "Head": yaw(-c["tyaw"] * 0.6) @ pitch(c["hd"] - c["tpitch"] * 0.6),
                 "LeftUpperArm": pitch(c["lfwd"]) @ roll(10)}
            rep = {"RightUpperArm": rot_between(arm, aim(c["el"], c["az"])),
                   "RightLowerArm": self._elbow("Right", c["relbow"]),
                   "LeftLowerArm": self._elbow("Left", c["lelbow"])}
            feet = self.planted()
            feet["Left"] = (self.spot(left, stride * reach.at(t)["s"], lift.at(t)["z"] * L), I3)
            mv = {"Hips": FWD * c["hx"] * L + np.array([0.0, 0.0, -0.02 * L - c["hz"] * L])}
            return self.pose(r, mv, feet, replace=rep)

        return self.keyed_clip("attack", k, frame)

    def hit(self) -> Clip:
        """Struck from the front: the hips are knocked back, the torso and head snap back
        (the head lags, then whips further), the arms fly forward a little; then it all
        settles, with a small overshoot forward, back to stand. Feet stay planted."""
        L = self.L
        k = Keys([0.0, 0.06, 0.16, 0.30, 0.42, 0.55],
                 hx=[0, -0.07, -0.06, 0.01, 0, 0], hz=[0, 0.03, 0.05, 0.02, 0, 0],
                 back=[0, -24, -20, 4, -1, 0], head=[0, -14, -22, 5, 0, 0],
                 arms=[0, -14, -10, 0, 0, 0], elbow=[12, 35, 30, 15, 12, 12],
                 twist=[0, 10, 8, -2, 0, 0])

        def frame(c, t):
            r = {"Hips": pitch(c["back"] * 0.2),
                 "Spine": pitch(c["back"] * 0.3) @ yaw(c["twist"]),
                 "Chest": pitch(c["back"] * 0.3), "UpperChest": pitch(c["back"] * 0.2),
                 "Neck": pitch(c["head"] * 0.4), "Head": pitch(c["head"] * 0.6),
                 "LeftUpperArm": pitch(c["arms"]) @ roll(-c["arms"] * 0.3),
                 "RightUpperArm": pitch(c["arms"]) @ roll(c["arms"] * 0.3)}
            rep = {"LeftLowerArm": self._elbow("Left", c["elbow"]),
                   "RightLowerArm": self._elbow("Right", c["elbow"])}
            mv = {"Hips": FWD * c["hx"] * L + np.array([0.0, 0.0, -0.02 * L - c["hz"] * L])}
            return self.pose(r, mv, self.planted(), replace=rep)

        return self.keyed_clip("hit", k, frame)

    def faint(self) -> Clip:
        """Knees buckle, the body falls forward onto the ground, a small bounce, and it lies
        flat: legs straight, feet pointed, arms by the sides, head turned onto one cheek."""
        L = self.L
        k = Keys([0.0, 0.30, 0.45, 0.85, 0.95, 1.05, 1.6],
                 hz=[0, 0.30, 0.32, 0.08, 0.02, -0.02, -0.02],
                 chest=[0, 22, 26, 6, 2, 0, 0], head=[0, 28, 30, 6, 2, 0, 0],
                 hyaw=[0, 0, 10, 70, 75, 75, 75], arms=[0, -12, -18, -15, -6, -2, -2],
                 out=[0, 5, 8, 25, 22, 20, 20], elbow=[12, 20, 25, 25, 12, 6, 6],
                 point=[0, 0, 0.15, 0.7, 0.95, 1, 1], straight=[0, 0, 0, 0.6, 1, 1, 1],
                 fall=[0, 0, 4, 90, 86, 90, 90])
        pivot = self._front_pivot()
        # where each ankle is with its leg straight and in line with the trunk (lying face
        # down), whatever the stance the model was made in
        reach = {lg.name: lg.hip - UP * 0.995 * lg.length for lg in self.b.legs}
        # and how far each foot turns to point: toes 80 degrees below the shin's forward, so
        # lying face down the top of the foot rests on the floor, toes just down
        slope = {lg.name: np.degrees(np.arctan2(lg.ankle[2] - lg.tip[2], (lg.ankle - lg.tip) @ FWD))
                 for lg in self.b.legs}
        land = int(round(0.85 * self.fps))

        def frame(c, t):
            r = {"Spine": pitch(c["chest"] * 0.4), "Chest": pitch(c["chest"] * 0.6),
                 "Head": pitch(c["head"] * 0.5) @ yaw(c["hyaw"]), "Neck": pitch(c["head"] * 0.5),
                 "LeftUpperArm": pitch(c["arms"]) @ roll(c["out"]),
                 "RightUpperArm": pitch(c["arms"]) @ roll(-c["out"])}
            rep = {"LeftLowerArm": self._elbow("Left", c["elbow"]),
                   "RightLowerArm": self._elbow("Right", c["elbow"])}
            # hz -0.02 at the end cancels the standing hip drop, and the feet move out to where
            # the legs lie straight
            mv = {"Hips": np.array([0.0, 0.0, -0.02 * L - c["hz"] * L])}
            w = c["straight"]
            feet = {n: ((1 - w) * p + w * reach[n], pitch(c["point"] * max(0.0, 80.0 - slope[n])))
                    for n, (p, _) in self.planted().items()}
            root = about(pitch(c["fall"]), pivot)
            return self.pose(r, mv, feet, root=root, replace=rep)

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
        n = 4 * self.fps
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

        return self.finish(Clip("idle", self.fps, True, 0.0, [frame(f % n) for f in range(n + 1)]))

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
        # No standing crouch and no mid-stance knee give: every bit of hip drop bends the hind
        # leg's single lower bone further back (HIND_SHIN_MAX_DEG), which costs stride
        if trot:
            kw = dict(duty=0.38, lift=0.22 * self.L, phases=QUAD_TROT)
            return self.gait_clip(name, kw, 0.0, 0.04, 0.0, upper, curl)
        kw = dict(duty=0.62, lift=0.16 * self.L, phases=QUAD_WALK)
        return self.gait_clip(name, kw, 0.0, 0.04, 0.0, upper, curl)

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
        clip.land_frame = int(round(0.90 * self.fps))
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
        n = 4 * self.fps
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

        return self.finish(Clip("idle", self.fps, True, 0.0, [frame(f % n) for f in range(n + 1)]))

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
            kw = dict(duty=0.38, lift=0.28 * self.L, phases=BIPED)
            return self.gait_clip(name, kw, 0.0, 0.03, 0.0, upper, curl)
        kw = dict(duty=0.6, lift=0.22 * self.L, phases=BIPED)
        return self.gait_clip(name, kw, 0.0, 0.03, 0.0, upper, curl)

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
        clip.land_frame = int(round(0.90 * self.fps))
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
