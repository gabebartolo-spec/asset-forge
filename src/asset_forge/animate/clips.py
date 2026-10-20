"""The six procedural clips for each body type, made from the skeleton alone (never from text).

    idle    breathing, a slow shift of weight, loops
    walk    loops; feet planted by IK from the gait generator (2 legs alternate, 4 legs walk,
            a small bird hops with both feet together)
    run     loops; 2 legs run with a flight phase, 4 legs trot, a small bird hops faster
    attack  humanoid: a swipe with a lunge step; four-legged: a bite; bird: a peck
    hit     a short flinch
    faint   a collapse to the ground under gravity, a hard stop, a small bounce, then still

Weight and timing (director 2026-10-20, "Fix first"; lead's motion critic s7): the body moves
as a chain, not a plank. The pelvis and the shoulders turn against each other, arms swing
against their own leg, the head and tail follow a frame or two late (curves.Chain, per-bone
time offsets), a blow is driven hard into its target and a fall accelerates into the floor
(curves timing shapes).

`make_clips(body)` returns Clip objects holding one Pose and one solved delta per frame. Loops
end on exactly their first frame, so the seam is invisible. Everything is in place: walk and
run carry the ground `speed` the game moves the character at so the feet do not slide.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from asset_forge.animate.body import FWD, LEFT, Body, Pose
from asset_forge.animate.curves import Chain, Keys
from asset_forge.animate.gait import BIPED, HOP, QUAD_TROT, QUAD_WALK, Gait
from asset_forge.animate.kin import UP, about, apply, rot, rot_between, unit

FPS = 30            # keys per second; small bodies step fast and get FAST_FPS
FAST_FPS = 60
MIN_RUN_KEYS = 12   # a run stride shorter than this many keys at FPS is keyed at FAST_FPS
CLIP_NAMES = ("idle", "walk", "run", "attack", "hit", "faint")
LOOPING = ("idle", "walk", "run")
G = 9.81
REACH = 0.97  # a leg never stretches past 97% of its length (keeps the knee from snapping)
WALK_REACH = 0.995  # a person's stance leg is nearly straight at mid-stance (a walk, not a sneak)
I3 = np.eye(3)
FRAME = 1.0 / 30    # one frame at game speed: the unit of the kinetic-chain delays

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
# A four-legged walk at 1.9 strides/s still read as hurried (motion critic s7): it shows at most
# 1.3 strides a second.
ANIMAL_WALK_STRIDES_PER_S = 1.3

# Small birds (a robin, a sparrow) hop with both feet together instead of walking; larger birds
# (a pigeon up) walk. Standing height in metres.
HOP_MAX_HEIGHT = 0.3

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


def max_strides_per_s(name: str, template: str) -> float:
    """The readability cap on cadence for a gait (strides a second)."""
    if name == "walk" and template == "four_legged":
        return ANIMAL_WALK_STRIDES_PER_S
    return MAX_STRIDES_PER_S[name]


def _quantum(phases: dict[str, float]) -> int:
    """Smallest frame step that puts every foot's landing on a whole frame."""
    for q in (2, 4, 8, 16):
        if all(abs(ph * q - round(ph * q)) < 1e-9 for ph in phases.values()):
            return q
    return 16


def pitch(a: float) -> np.ndarray:
    """Nose down / top forward for a > 0 (about the character's left axis)."""
    return rot(LEFT, a)


def yaw(a: float) -> np.ndarray:
    """Turn left for a > 0."""
    return rot(UP, a)


def roll(a: float) -> np.ndarray:
    """Lean right for a > 0 (about the forward axis)."""
    return rot(FWD, a)


def _pulse(t: float, rise: float) -> float:
    """A flick that peaks (at 1) `rise` seconds after t = 0 and dies away: t/r * e^(1 - t/r)."""
    x = max(t, 0.0) / rise
    return float(x * np.exp(1.0 - x))


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
    capped: bool = False              # cadence held at the readability cap (slower than Froude)
    library: bool = False             # hand-made clip re-targeted from the animation library

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
        second (the readability cap) the cycle is lengthened to the cap and the stroke kept, so
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

    def drop_needed(self, lg, target: np.ndarray, hips_xy=(0.0, 0.0), reach: float = REACH,
                    hip: np.ndarray | None = None) -> float:
        """How far the hip must come down so the leg reaches `target` at `reach` of its length.
        hip: where the hip joint is this frame (default its rest spot moved by hips_xy)."""
        if hip is None:
            hip = lg.hip + np.array([hips_xy[0], hips_xy[1], 0.0])
        horiz = float(np.linalg.norm((target - hip)[:2]))
        lim = reach * lg.length
        if horiz >= lim:
            return float("inf")
        return max(0.0, float(hip[2] - target[2]) - float(np.sqrt(lim**2 - horiz**2)))

    def hip_joints(self, rot_: dict, move: dict, rep: dict) -> dict[str, np.ndarray]:
        """Where each leg's hip joint is under an upper-body pose (the pelvis turned and rolled,
        the chest turned for the front legs), before any foot is placed."""
        D, _ = self.b.solve(self.pose(rot_, move, {}, replace=rep))
        return {lg.name: apply(D[lg.upper], lg.hip) for lg in self.b.legs}

    def pivot(self, lg) -> np.ndarray:
        """The point a lifting heel turns about: a person's ball joint (the toes stay flat on
        the ground and bend there, see toe_bend), or an animal's paw tip."""
        return lg.ball

    def toe_bend(self, lg, deg: float) -> dict[str, np.ndarray]:
        """The toes kept flat while the heel is up `deg` about the ball (a person only)."""
        if self.b.template != "humanoid" or not deg:
            return {}
        return {f"{lg.name}Toes": pitch(-deg)}

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

    def swing_turn(self, lg, rise: float, lift: float, base: float, curl: float) -> float:
        """The foot's turn in the swing: `base` (heel up / toes up) plus as much of the swing
        `curl` as keeps the toe or paw tip clear of the ground: at least 3/4 of the swing's
        `lift` above where it stands (`rise`: the ankle above its standing height). A curl
        that would scuff the tip along the floor or push it through is cut back."""
        v = lg.tip - lg.ankle

        def clear(k):
            return rise + float((pitch(base + k * curl) @ v)[2] - v[2]) >= 0.75 * lift - 1e-9

        if clear(1.0) or not clear(0.0):
            return base + curl if clear(1.0) else base
        lo, hi = 0.0, 1.0
        for _ in range(24):
            mid = 0.5 * (lo + hi)
            lo, hi = (mid, hi) if clear(mid) else (lo, mid)
        return base + lo * curl

    def lean_limited(self, lg) -> bool:
        """Legs whose lower bone may not lean past HIND_SHIN_MAX_DEG: a four-legged animal's
        hind legs (see the constant)."""
        return self.b.template == "four_legged" and lg.group == "Hind"

    def stroke(self, drop_max: float, roll: float = 0.0, strike: float = 0.0,
               back: float = 1.0, reach_: float = REACH) -> tuple[float, dict[str, float]]:
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
                return self.drop_needed(lg, p + off, reach=reach_) <= drop_max

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
                  roll: float = 30.0, strike: float = 0.0, dip: Callable | None = None,
                  rise: Callable | None = None, reach: float = REACH, early_right: int = 0) -> Clip:
        """gait_kw: duty, lift, phases (and optional per-leg lifts). crouch, bob_max, compress
        are fractions of leg length: the knee bend everywhere, the most the hips may dip at the
        stroke ends, an extra dip at mid-stance (running). roll: degrees the heel lifts at
        push-off; strike: degrees the toes are up when the heel lands. dip(phi, g): the least
        the hips are down this frame (metres; a walk's bob, a hop's landing crouch); rise(phi, g):
        how far the body is lifted (metres; a hop's arc). early_right: whole frames the Right
        foot lands early (an uneven step). The speed comes from FROUDE[name], the stride from
        self.stride(name)."""
        clip = None
        for k in range(12):  # shorten the hind legs' back reach until no lower leg lies flat
            clip = self._gait_clip(name, gait_kw, crouch, bob_max, compress, upper, swing_pitch,
                                   roll, strike, 0.88**k, dip, rise, reach, early_right)
            if self.max_lean(clip) <= HIND_SHIN_MAX_DEG:
                break
        return clip

    def max_lean(self, clip: Clip) -> float:
        """The most a lean-limited leg's lower bone leans from vertical (degrees) while its foot
        is near the ground (below half the swing lift): low and flat is a drag; a foot lifted
        higher is a tucked leg, which may fold further."""
        legs = [lg for lg in self.b.legs if self.lean_limited(lg)]
        worst = 0.0
        for D in clip.deltas if legs else []:
            P = self.b.joint_positions(D)
            for lg in legs:
                near = 0.5 * clip.gait.lift_of(lg.name) if clip.gait else 0.0
                if P[lg.foot][2] - lg.ground_z >= near:
                    continue
                u = unit(P[lg.foot] - P[lg.lower])
                worst = max(worst, float(np.degrees(np.arccos(np.clip(-u[2], -1.0, 1.0)))))
        return worst

    def _gait_clip(self, name, gait_kw, crouch, bob_max, compress, upper, swing_pitch, roll,
                   strike, back, dip, rise, reach, early_right) -> Clip:
        fr = FROUDE[name][self.b.template]
        most, centre = self.stroke((crouch + bob_max) * self.L, roll, strike, back, reach)
        frames, S, capped = self.plan(fr, gait_kw["duty"], gait_kw["phases"], most,
                                      self.stride(name), max_strides_per_s(name, self.b.template))
        early = tuple(lg.name for lg in self.b.legs if self.lean_limited(lg))
        if early_right:  # after the cycle is set, so the step stays on a whole frame
            ph = dict(gait_kw["phases"])
            ph["Right"] = (ph["Right"] - early_right / frames) % 1.0
            gait_kw = {**gait_kw, "phases": ph}
        g = Gait(frames=frames, stroke=S, fps=self.fps, early=early, **gait_kw)
        n = g.frames
        ups = [upper(f / n, g) for f in range(n)]
        lift = np.array([rise(f / n, g) if rise else 0.0 for f in range(n)])
        want = np.array([dip(f / n, g) if dip else 0.0 for f in range(n)])
        feet_all, need = [], np.zeros(n)
        for f in range(n):
            rot_, move, rep = ups[f]
            hips = move.get("Hips", np.zeros(3)) + UP * lift[f]
            at = self.hip_joints(rot_, {**move, "Hips": hips}, rep)
            feet, toes = {}, {}
            for lg in self.b.legs:
                x, z, on, s = g.foot(lg.name, f)
                a = roll * g.roll(lg.name, f)
                h = strike * g.strike(lg.name, f)
                toes.update(self.toe_bend(lg, a))
                at_ = (self.spot(lg, centre[lg.name] + x, z)
                       + self.roll_offset(lg, a) + self.strike_offset(lg, h))
                turn = a - h if on else self.swing_turn(lg, at_[2] - lg.ground_z, z, a - h,
                                                        swing_pitch(s, lg))
                feet[lg.name] = (at_, pitch(turn))
                need[f] = max(need[f], self.drop_needed(lg, feet[lg.name][0], reach=reach,
                                                        hip=at[lg.name]))
            feet_all.append(feet)
            ups[f] = ({**rot_, **toes}, move, rep)
        # the drop follows the wanted dip exactly and is smoothed only where the reach needs
        # more (smoothing the dip itself lifts its low point: a bent knee at mid-stance)
        need = np.minimum(need, 0.5 * self.L)
        drop = want + _periodic_cover(np.maximum(need - want, 0.0), max(1, n // 16))
        drop += crouch * self.L
        if compress:  # running: the knees give a little at mid-stance
            mids = sorted({(ph + g.duty / 2) % 1.0 for ph in g.phases.values()})
            phi = np.arange(n) / n
            wave = np.cos(2 * np.pi * len(mids) * (phi - mids[0]))
            drop += compress * self.L * (0.5 + 0.5 * wave)
        poses = []
        for f in range(n + 1):  # frame n repeats frame 0: the loop seam
            k = f % n
            rot_, move, rep = ups[k]
            hips = move.get("Hips", np.zeros(3)) + np.array([0.0, 0.0, lift[k] - drop[k]])
            move = {**move, "Hips": hips}
            poses.append(self.pose(rot_, move, feet_all[k], replace=rep))
        return self.finish(Clip(name, self.fps, True, g.speed, poses, gait=g,
                                froude=g.speed**2 / (G * self.L), capped=capped))

    # ------------------------------------------------------------------ one-shot helper
    def keyed_clip(self, name: str, keys, frame_fn: Callable[[dict, float], Pose],
                   loop: bool = False, end: float | None = None) -> Clip:
        """keys: Keys or Chain (anything with .at(t) and .end); end: the clip length when
        frame_fn reads more keys than these."""
        last = keys.end if end is None else end
        n = int(np.ceil(last * self.fps - 1e-9))  # the last frame reaches the last key
        poses = [frame_fn(keys.at(f / self.fps), f / self.fps) for f in range(n + 1)]
        return self.finish(Clip(name, self.fps, loop, 0.0, poses))


# ====================================================================== humanoid
class Humanoid(Animator):
    def idle(self) -> Clip:
        """Two breaths and one slow shift of weight from foot to foot over 4 s: the pelvis drops
        on the unweighted side, the spine and head right themselves a beat later, the shoulders
        and arms follow the breath late."""
        n = 4 * self.fps
        L = self.L

        def frame(f):
            t = f / n
            br = np.sin(2 * np.pi * 2 * t)                # two breaths
            brl = np.sin(2 * np.pi * 2 * t - 0.6)         # the shoulders and arms, late
            sw = np.sin(2 * np.pi * t)                    # weight over the left foot when > 0
            swl = np.sin(2 * np.pi * t - 0.5)             # the spine rights itself late
            r = {"Chest": pitch(-1.2 * br) @ roll(-0.4 * swl), "UpperChest": pitch(-0.8 * br),
                 "Hips": roll(1.5 * sw), "Spine": roll(-1.0 * swl), "Neck": roll(-0.4 * swl),
                 "Head": yaw(3 * np.sin(2 * np.pi * t + 1.0)) @ roll(-0.3 * swl),
                 "LeftShoulder": roll(-1.0 * brl), "RightShoulder": roll(1.0 * brl),
                 "LeftUpperArm": pitch(1.5 * brl) @ roll(1.0 * brl + 0.8 * swl),
                 "RightUpperArm": pitch(1.5 * brl) @ roll(-1.0 * brl + 0.8 * swl)}
            mv = {"Hips": [0.014 * L * sw, 0.0, -0.02 * L - 0.004 * L * (0.5 + 0.5 * br)]}
            return self.pose(r, mv, self.planted())

        poses = [frame(f % n) for f in range(n + 1)]
        return self.finish(Clip("idle", self.fps, True, 0.0, poses))

    def _upper(self, phi, g, run: bool):
        """The upper body over a stride (phi 0-1; the left heel lands at 0, the right at 0.5).
        The pelvis turns with the leg that swings forward, the shoulders turn against it two
        frames late, each arm swings against its own leg (two frames later again) with the
        elbow bending as it comes forward. The pelvis drops on the swing side and shifts over
        the standing foot; the spine rights it, late; the head steadies against the shoulders."""
        L = self.L
        w = 2 * np.pi * phi
        # the shoulders trail the pelvis two game frames walking, one running (a shorter
        # cycle), as a phase angle; walking, the arms trail the shoulders as much again.
        # Running, the arms keep the pelvis's timing: the short stance brings each foot
        # forward earlier in the cycle, so arms timed later would swing with their own leg
        lag = 2 * np.pi * (1 if run else 2) * FRAME / g.seconds
        c = np.cos(w)                                 # +1: left leg forward (left heel strike)
        cs, ca = np.cos(w - lag), np.cos(w - (0 if run else 2) * lag)
        side = np.cos(w - np.pi * g.duty)             # +1 over the left foot (left mid-stance)
        sidel = np.cos(w - np.pi * g.duty - lag)
        turn_p, turn_c = (6.0, 10.0) if run else (4.0, 7.0)
        lean = 9.0 if run else 3.0
        swing = 35.0 if run else 28.0
        hips_y, chest_y = -turn_p * c, turn_c * cs
        spine_y = 0.5 * (hips_y + chest_y)
        tilt = (3.0 if run else 4.0) * side           # + leans right: the right (swing) side drops
        tiltl = (3.0 if run else 4.0) * sidel
        nod = (1.5 if run else 1.0) * np.cos(2 * w - lag)  # a little nod as each heel lands
        r = {"Hips": yaw(hips_y) @ roll(tilt),
             "Spine": pitch(lean * 0.5) @ yaw(spine_y - hips_y) @ roll(-0.6 * tiltl),
             "Chest": pitch(lean * 0.5) @ yaw(chest_y - spine_y) @ roll(-0.4 * tiltl),
             "Neck": pitch(-lean * 0.5 + 0.5 * nod),
             "Head": pitch(-lean * 0.5 + 0.5 * nod) @ yaw(-chest_y - 1.0 * cs),
             "LeftUpperArm": pitch(swing * ca), "RightUpperArm": pitch(-swing * ca)}
        bend, more = (75.0, 20.0) if run else (20.0, 20.0)
        rep = {"LeftLowerArm": self._elbow("Left", bend + more * (0.5 - 0.5 * ca)),
               "RightLowerArm": self._elbow("Right", bend + more * (0.5 + 0.5 * ca))}
        mv = {"Hips": np.array([(0.012 if run else 0.03) * L * side, 0.0, 0.0])}
        return r, mv, rep

    def _gait(self, name, run):
        def upper(phi, g):
            return self._upper(phi, g, run)

        if run:
            kw = dict(duty=0.36, lift=0.24 * self.L, phases=BIPED)
            return self.gait_clip(name, kw, 0.07, 0.05, 0.03, upper,
                                  lambda s, lg: 28 * np.sin(np.pi * s) ** 2, roll=35.0, strike=8.0)
        # walk: heel strike (toes up ~15 deg) and push-off over the toes (heel up ~45 deg) give
        # the stride its length. The stance leg is nearly straight at mid-stance (WALK_REACH) and
        # the hips bob like an inverted pendulum: lowest just after each heel strike, highest
        # over the standing foot
        L = self.L

        def bob(phi, g):
            return 0.05 * L * (0.5 + 0.5 * np.cos(4 * np.pi * (phi - 0.03)))

        kw = dict(duty=0.60, lift=0.09 * L, phases=BIPED)
        return self.gait_clip(name, kw, 0.0, 0.065, 0.0, upper,
                              lambda s, lg: 14 * np.sin(np.pi * s) * (1 - 1.3 * s),
                              roll=45.0, strike=15.0, dip=bob, reach=WALK_REACH)

    def walk(self) -> Clip:
        return self._gait("walk", False)

    def run(self) -> Clip:
        return self._gait("run", True)

    def attack(self) -> Clip:
        """A right-hand swipe: the wind-up cocks the arm up and back with the torso turned
        away and holds a beat; the strike is driven hard from the back foot through the hips,
        the chest and then the arm (each a frame or two after the last), sweeping fast round
        the right side and across the body while the left foot steps out into the lunge; the
        follow-through overshoots and settles back. The step is shortened until the leg
        reaches it on every frame."""
        clip = None
        for k in range(8):
            clip = self._attack(0.42 * 0.9**k)
            if not clip.short:
                break
        return clip

    def _attack(self, stride_frac: float) -> Clip:
        L = self.L
        # keys: rest, wound up, held, strike (arm level, out front), follow-through (past the
        # settle, an overshoot), settle back, rest. The upper arm's direction is keyed as
        # angles in the chest's frame, so the sweep is an arc, not a reach: el from straight
        # down (0) through level (90) to up (180); az round the body: 0 out to the right side,
        # 90 forward, 180 the left side, -90 back.
        k = Keys([0.0, 0.30, 0.38, 0.43, 0.50, 0.62, 0.95],
                 shape=["smooth", "smooth", "in", "out", "smooth", "smooth"],
                 hx=[0, -0.05, -0.05, 0.12, 0.17, 0.13, 0],
                 hz=[0, 0.03, 0.035, 0.12, 0.15, 0.11, 0],
                 heel=[0, 0, 4, 25, 28, 15, 0],
                 tyaw=[0, -38, -40, 12, 44, 30, 0], tpitch=[0, -6, -6, 10, 18, 10, 0],
                 el=[12, 140, 142, 85, 45, 55, 12], az=[10, -40, -42, 55, 128, 108, 10],
                 relbow=[12, 70, 72, 15, 12, 35, 12],
                 lfwd=[0, -40, -42, -20, 15, 0, 0], lelbow=[12, 70, 70, 50, 30, 25, 12],
                 hd=[0, -6, -6, 4, 6, 3, 0])
        # the kinetic chain: from the strike on, each part moves a little after the one below
        # (in game frames: half a frame per link up to the hand; longer delays smear the
        # strike so the hand never gets much faster than the wind-up)
        lags = {"hips": 0.0, "spine": 0.5 * FRAME, "chest": 1 * FRAME, "arm": 1.5 * FRAME,
                "head": 2 * FRAME, "larm": 2 * FRAME}
        chain = Chain(k, lags, start=2)
        # the left foot steps out (lands at 0.36 s, as the strike starts) and back (lands at
        # 0.90 s); it only moves while it is off the ground, so it never slides
        reach = Keys([0.0, 0.03, 0.15, 0.36, 0.66, 0.74, 0.84, 0.90],
                     s=[0, 0, 0.45, 1.0, 1.0, 0.55, 0, 0])
        lift = Keys([0.0, 0.12, 0.36, 0.62, 0.76, 0.90, 0.94], z=[0, 0.07, 0, 0, 0.06, 0, 0])
        stride = stride_frac * L
        left, right = self.b.leg("Left"), self.b.leg("Right")
        arm = self.b.head["RightLowerArm"] - self.b.head["RightUpperArm"]

        def aim(el, az):
            e, a = np.radians(el), np.radians(az)
            return np.array([-np.cos(a) * np.sin(e), -np.sin(a) * np.sin(e), -np.cos(e)])

        def frame(c, t):
            h, s, ch, hd, la, ra = (c[g] for g in ("hips", "spine", "chest", "head", "larm",
                                                   "arm"))
            r = {"Hips": yaw(h["tyaw"] * 0.4),
                 "Spine": yaw(s["tyaw"] * 0.3) @ pitch(s["tpitch"] * 0.5),
                 "Chest": yaw(ch["tyaw"] * 0.3) @ pitch(ch["tpitch"] * 0.5),
                 "Head": yaw(-hd["tyaw"] * 0.6) @ pitch(hd["hd"] - hd["tpitch"] * 0.6),
                 "LeftUpperArm": pitch(la["lfwd"]) @ roll(10)}
            rep = {"RightUpperArm": rot_between(arm, aim(ra["el"], ra["az"])),
                   "RightLowerArm": self._elbow("Right", ra["relbow"]),
                   "LeftLowerArm": self._elbow("Left", la["lelbow"])}
            feet = self.planted()
            feet["Left"] = (self.spot(left, stride * reach.at(t)["s"], lift.at(t)["z"] * L), I3)
            a = h["heel"]  # the back heel lifts as it drives the lunge; the toes stay planted
            feet["Right"] = (self.spot(right) + self.roll_offset(right, a), pitch(a))
            r.update(self.toe_bend(right, a))
            mv = {"Hips": FWD * h["hx"] * L + np.array([0.0, 0.0, -0.02 * L - h["hz"] * L])}
            return self.pose(r, mv, feet, replace=rep)

        return self.keyed_clip("attack", chain, frame)

    def hit(self) -> Clip:
        """Struck in the chest: the chest is knocked back at once (fast, then slowing), the
        hips a frame later, the head two frames later (it lags, then whips further), the arms
        fly forward three frames later; then it all settles, with a small overshoot forward,
        back to stand. Feet stay planted."""
        L = self.L
        k = Keys([0.0, 0.06, 0.16, 0.30, 0.42, 0.60],
                 shape=["out", "smooth", "smooth", "smooth", "smooth"],
                 hx=[0, -0.07, -0.06, 0.01, 0, 0], hz=[0, 0.03, 0.05, 0.02, 0, 0],
                 back=[0, -24, -20, 4, -1, 0], head=[0, -14, -24, 6, -1, 0],
                 arms=[0, -16, -10, 2, 0, 0], elbow=[12, 38, 30, 14, 12, 12],
                 twist=[0, 10, 8, -2, 0, 0])
        chain = Chain(k, {"chest": 0.0, "hips": FRAME, "head": 2 * FRAME, "arms": 3 * FRAME})

        def frame(c, t):
            ch, hp, hd, ar = c["chest"], c["hips"], c["head"], c["arms"]
            # the head and arms lag in the world, not only on top of the chest: each holds
            # where the torso was (its own delay ago) and only then is carried back with it
            torso = 0.2 * hp["back"] + 0.8 * ch["back"]
            r = {"Hips": pitch(hp["back"] * 0.2),
                 "Spine": pitch(ch["back"] * 0.3) @ yaw(ch["twist"]),
                 "Chest": pitch(ch["back"] * 0.3), "UpperChest": pitch(ch["back"] * 0.2),
                 "Neck": pitch(hd["back"] - torso + hd["head"] * 0.4),
                 "Head": pitch(hd["head"] * 0.6),
                 "LeftUpperArm": pitch(ar["back"] - torso + ar["arms"]) @ roll(-ar["arms"] * 0.3),
                 "RightUpperArm": pitch(ar["back"] - torso + ar["arms"]) @ roll(ar["arms"] * 0.3)}
            rep = {"LeftLowerArm": self._elbow("Left", ar["elbow"]),
                   "RightLowerArm": self._elbow("Right", ar["elbow"])}
            mv = {"Hips": FWD * hp["hx"] * L + np.array([0.0, 0.0, -0.02 * L - hp["hz"] * L])}
            return self.pose(r, mv, self.planted(), replace=rep)

        return self.keyed_clip("hit", chain, frame)

    def faint(self) -> Clip:
        """A reel back, then the knees buckle and the hips drop (accelerating, under gravity);
        the torso folds a few frames later and the head last. The body topples forward faster
        and faster and stops dead on the floor at 0.67 s, bounces a little, the arms splay;
        then it lies still and flat: legs straight, feet pointed, arms by the sides, head
        turned onto one cheek."""
        L = self.L
        land = 0.67
        # the whole body: it topples about the front of the feet, accelerating into the floor
        fall = Keys([0.0, 0.30, land, land + 0.04, land + 0.08, 1.30], v=[0, 0, 90, 87, 90, 90],
                    shape=["smooth", "in3", "out", "in", "smooth"])
        # legs and hips first: a reel back, the knees buckle (a gravity drop), then the legs
        # stretch out as the body goes down; done when it lands
        legs = Keys([0.0, 0.18, 0.45, land, 1.30],
                    shape=["smooth", "in", "smooth", "smooth"],
                    hz=[0, -0.01, 0.32, -0.02, -0.02], hx=[0, 0.03, 0.0, 0.0, 0.0],
                    straight=[0, 0, 0, 1, 1])
        step = Keys([0.0, 0.04, 0.20], s=[0, 0.5, 1.0])  # the right foot steps back as it reels
        lift = Keys([0.0, 0.04, 0.12, 0.20], z=[0, 0.02, 0.04, 0])
        # the torso folds 4 frames after the knees, the arms follow, the head comes last;
        # each is settled within 0.15 s of the landing, so nothing drifts after
        chest = Keys([0.0, 0.18, 0.30, 0.48, 0.58, 0.64], chest=[0, -5, 2, 30, 6, 0])
        head = Keys([0.0, 0.18, 0.30, 0.44, 0.54, 0.60],
                    head=[0, -6, -4, -18, 6, 0], hyaw=[0, 0, 0, 30, 70, 75])
        arms = Keys([0.0, 0.18, 0.32, 0.42, 0.50],
                    arms=[0, -10, -18, -8, 1], elbow=[12, 20, 25, 14, 6], out=[0, 5, 8, 16, 20])
        # the arms splay out on the impact (2 frames) and settle back a little
        splay = Keys([0.0, land, land + 0.07, land + 0.13], out=[0, 0, 12, 9],
                     shape=["smooth", "out", "smooth"])
        lag = {"chest": 4 * FRAME, "head": 6 * FRAME, "arms": 5 * FRAME}
        pivot = self._front_pivot()
        right = self.b.leg("Right")
        # where each ankle is with its leg straight and in line with the trunk (lying face
        # down), whatever the stance the model was made in
        reach = {lg.name: lg.hip - UP * 0.995 * lg.length for lg in self.b.legs}
        # Toppling about the toe tips leaves the trunk as high as the hips stood behind them;
        # it sinks with the fall to lie at the depth of a body's front half (the joints run
        # down the middle of the body), its legs at that height too.
        depth = 0.06 * self.H
        sink = max(0.0, float((self.b.head["Hips"] - pivot) @ -FWD) - depth)
        # each foot points so its toe tip just reaches the floor from that ankle height: the
        # turn from the foot's rest slope (degrees below level, toes forward) to that angle
        # below the shin's line, which lying face down is the floor
        turn = {}
        for lg in self.b.legs:
            foot = float(np.linalg.norm(lg.tip - lg.ankle))
            rest = np.degrees(np.arctan2(lg.ankle[2] - lg.tip[2], (lg.tip - lg.ankle) @ FWD))
            down = np.degrees(np.arcsin(np.clip((depth - 0.005 * self.H) / foot, 0.0, 1.0)))
            turn[lg.name] = max(0.0, 90.0 - down - rest)

        def frame(c, t):
            lg_ = legs.at(t)
            ch = chest.at(t - lag["chest"])
            hd = head.at(t - lag["head"])
            ar = arms.at(t - lag["arms"])
            out = ar["out"] + splay.at(t)["out"]
            r = {"Spine": pitch(ch["chest"] * 0.4), "Chest": pitch(ch["chest"] * 0.6),
                 "Head": pitch(hd["head"] * 0.5) @ yaw(hd["hyaw"]),
                 "Neck": pitch(hd["head"] * 0.5),
                 "LeftUpperArm": pitch(ar["arms"]) @ roll(out),
                 "RightUpperArm": pitch(ar["arms"]) @ roll(-out)}
            rep = {"LeftLowerArm": self._elbow("Left", ar["elbow"]),
                   "RightLowerArm": self._elbow("Right", ar["elbow"])}
            # hz -0.02 at the end cancels the standing hip drop, and the feet move out to where
            # the legs lie straight
            mv = {"Hips": FWD * lg_["hx"] * L + np.array([0.0, 0.0, -0.02 * L - lg_["hz"] * L])}
            w = lg_["straight"]
            # the feet point and the body sinks together, as it nears the floor (so the toes
            # stay on the floor while it topples over them)
            v = fall.at(t)["v"]
            low = np.sin(np.radians(min(v, 90.0))) ** 4
            feet = {}
            for n, (p, _) in self.planted().items():
                if n == right.name:
                    p = self.spot(right, -0.12 * L * step.at(t)["s"], lift.at(t)["z"] * L)
                feet[n] = ((1 - w) * p + w * reach[n], pitch(np.sqrt(low) * turn[n]))
            root = about(pitch(v), pivot, -UP * sink * low)
            pose = self.pose(r, mv, feet, root=root, replace=rep)
            return self._toes_off_floor(pose, r, mv, feet, root, rep)

        clip = self.keyed_clip("faint", fall, frame)
        clip.land_frame = int(round(land * self.fps))
        return clip

    def _toes_off_floor(self, pose, r, mv, feet, root, rep):
        """While the body topples over its pointed feet, toes that would dip into the floor
        bend back at the ball and lie on it instead."""
        D, _ = self.b.solve(pose)
        P = self.b.joint_positions(D)
        floor = 0.005 * self.H
        bend = {}
        for lg in self.b.legs:
            ball, tip = P[f"{lg.name}Toes"], P[f"{lg.name}Toes.tail"]
            if tip[2] >= floor or ball[2] <= floor:
                continue
            # every turn here is about the left axis, so the toes turn in the side plane: from
            # their angle now to the nearer angle that puts the tip on the floor
            t = tip - ball
            n = float(np.hypot(t[1], t[2]))
            now = np.arctan2(t[2], t[1])
            a = np.arcsin(np.clip((floor - ball[2]) / n, -1.0, 1.0))
            d = min(((x + np.pi) % (2 * np.pi) - np.pi for x in (a - now, np.pi - a - now)),
                    key=abs)
            bend[f"{lg.name}Toes"] = pitch(np.degrees(d))
        if not bend:
            return pose
        return self.pose({**r, **bend}, mv, feet, root=root, replace=rep)

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
        """The spine bends: the pelvis turns with the hind leg that swings forward and the
        shoulders with the foreleg, so the back is never a plank; each drops a little on the
        side whose leg swings. The head nods once a stride with its gaze kept level; the tail
        follows the pelvis round a frame late per segment and lifts and droops once a stride."""
        turn, tip, nod = (6.0, 3.0, 5.0) if trot else (9.0, 4.0, 6.0)

        def upper(phi, g):
            f = phi * g.frames
            w = 2 * np.pi * phi
            lagf = FRAME * self.fps                    # one game frame, in clip frames
            S = max(g.stroke, 1e-9)

            def turn_at(a, b, df=0.0):  # + turns left: the right leg is the one forward
                return -turn * (g.foot(a, f - df)[0] - g.foot(b, f - df)[0]) / S

            def drop(a, b, df=0.0):     # + leans right: the right leg is the one swinging
                return tip * (g.swinging(b, f - df) - g.swinging(a, f - df))

            hips_y = turn_at("HindLeft", "HindRight")
            chest_y = turn_at("FrontLeft", "FrontRight", lagf)
            spine_y = 0.5 * (hips_y + chest_y)
            hips_r = drop("HindLeft", "HindRight")
            chest_r = drop("FrontLeft", "FrontRight", lagf)
            lagw = 2 * np.pi * lagf / g.frames
            r = {"Hips": yaw(hips_y) @ roll(hips_r),
                 "Spine": yaw(spine_y - hips_y) @ pitch((2.5 if trot else 1) * np.sin(2 * w)),
                 "Chest": yaw(chest_y - spine_y) @ roll(chest_r - hips_r),
                 "Neck1": pitch(nod * np.sin(w - 2 * lagw)) @ yaw(-0.5 * chest_y),
                 "Head": pitch(-0.85 * nod * np.sin(w - 2 * lagw)) @ yaw(-0.4 * chest_y)}
            for i in range(1, 5):  # each segment a frame behind the one before
                lag_y = turn_at("HindLeft", "HindRight", i * lagf)
                lift = (14 if trot else 4) + 10 * np.sin(w - i * lagw)
                r[f"Tail{i}"] = yaw(-0.7 * lag_y) @ pitch(lift / 4)
            return r, {}, {}

        front = ("FrontLeft", "FrontRight")

        def curl(s, lg):  # the forepaw folds right back as it swings (no straight stilts)
            return (70 if lg.name in front else 45) * np.sin(np.pi * s) ** 1.5  # flat on landing

        # No standing crouch and no mid-stance knee give: every bit of hip drop bends the hind
        # leg's single lower bone further back (HIND_SHIN_MAX_DEG), which costs stride
        L = self.L
        if trot:
            kw = dict(duty=0.38, lift=0.22 * L, phases=QUAD_TROT,
                      lifts={n: 0.26 * L for n in front})
            return self.gait_clip(name, kw, 0.0, 0.04, 0.0, upper, curl)
        kw = dict(duty=0.62, lift=0.16 * L, phases=QUAD_WALK, lifts={n: 0.20 * L for n in front})
        return self.gait_clip(name, kw, 0.0, 0.04, 0.0, upper, curl)

    def walk(self) -> Clip:
        return self._gait("walk", False)

    def run(self) -> Clip:
        return self._gait("run", True)

    def attack(self) -> Clip:
        """Bite: weight back with the head up, held a beat, then a lunge driven from the hips
        through the chest, neck and head (each a frame after the last) into a snap that
        overshoots, back to stand. The tail lags behind."""
        L, BL = self.L, self._len()
        k = Keys([0.0, 0.28, 0.35, 0.40, 0.47, 0.85],
                 shape=["smooth", "smooth", "in", "out", "smooth"],
                 hx=[0, -0.06, -0.065, 0.10, 0.11, 0], hz=[0, 0.06, 0.065, 0.10, 0.10, 0],
                 lean=[0, -4, -4, 8, 9, 0], neck=[0, -18, -19, 20, 25, 0],
                 head=[0, -12, -13, 16, 21, 0], tail=[0, 10, 11, -6, -8, 0])
        chain = Chain(k, {"hips": 0.0, "chest": FRAME, "neck": 2 * FRAME, "head": 3 * FRAME,
                          "tail": 3 * FRAME}, start=2)

        def frame(c, t):
            hp, ch, nk, hd, tl = (c[g] for g in ("hips", "chest", "neck", "head", "tail"))
            r = {"Spine": pitch(hp["lean"] * 0.5), "Chest": pitch(ch["lean"] * 0.5),
                 "Neck1": pitch(nk["neck"] * 0.6), "Neck2": pitch(nk["neck"] * 0.4),
                 "Head": pitch(hd["head"]), **self._tail(0, 0, tl["tail"] * 4)}
            mv = {"Hips": FWD * hp["hx"] * BL + np.array([0.0, 0.0, -0.02 * L - hp["hz"] * L])}
            return self.pose(r, mv, self.planted())

        return self.keyed_clip("attack", chain, frame)

    def hit(self) -> Clip:
        """Knocked back at once (fast, then slowing); the neck, head and tail follow a frame
        or more later, then settle."""
        L, BL = self.L, self._len()
        k = Keys([0.0, 0.07, 0.20, 0.33, 0.5], shape=["out", "smooth", "smooth", "smooth"],
                 hx=[0, -0.05, -0.04, 0.01, 0], hz=[0, 0.05, 0.05, 0.01, 0],
                 side=[0, 0.03, 0.02, 0, 0], neck=[0, -16, -8, 2, 0], tail=[0, -25, -18, -3, 0],
                 roll_=[0, 5, 3, 0, 0])
        chain = Chain(k, {"hips": 0.0, "neck": FRAME, "head": 2 * FRAME, "tail": 3 * FRAME})

        def frame(c, t):
            hp, nk, hd, tl = (c[g] for g in ("hips", "neck", "head", "tail"))
            r = {"Neck1": pitch(nk["neck"]), "Head": pitch(hd["neck"] * 0.5),
                 "Hips": roll(hp["roll_"]), **self._tail(0, 0, tl["tail"] * 4)}
            mv = {"Hips": FWD * hp["hx"] * BL + LEFT * hp["side"] * BL
                  + np.array([0.0, 0.0, -0.02 * L - hp["hz"] * L])}
            return self.pose(r, mv, self.planted())

        return self.keyed_clip("hit", chain, frame)

    def faint(self) -> Clip:
        return _side_faint(self, neck=(-6, 20, 8), tail=(0, -15, -5), sink_to=0.40, fall=86)


# ====================================================================== bird
class Bird(Animator):
    def _wings(self, open_: float, raise_: float) -> dict:
        """Wings out from the body (open, degrees) and up (raise, degrees)."""
        out = {}
        for side, s in (("Left", 1.0), ("Right", -1.0)):
            out[f"{side}Wing1"] = roll(s * raise_) @ yaw(-s * open_)
        return out

    @property
    def hops(self) -> bool:
        """Small birds hop with both feet together (HOP_MAX_HEIGHT)."""
        return self.H <= HOP_MAX_HEIGHT

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

    def _neck_reach(self) -> float:
        return float(np.linalg.norm(self.b.head["Neck2"] - self.b.head["Neck1"]))

    def _head_hold(self, phi: float, g: Gait, events: list[float]) -> dict:
        """The bird's head bob: the head holds still over the ground (it slides back along the
        body at the ground speed) and then thrusts forward in 0.1 s, once after each event
        (cycle phases: each landing when walking, each take-off when hopping). The neck
        carries it: Neck1 pitches the head forward or back, Neck2 undoes the turn so the head
        stays level."""
        T = g.seconds
        thrust = min(0.1 / T, 0.4 / len(events))
        reach = self._neck_reach()
        ev = sorted(e % 1.0 for e in events)
        gaps = [((ev[(i + 1) % len(ev)] - e) % 1.0) or 1.0 for i, e in enumerate(ev)]
        amp = [g.speed * (gap - thrust) * T / 2 for gap in gaps]
        scale = min(1.0, 0.35 * reach / max(amp))  # never more than ~20 degrees of neck
        amp = [a * scale for a in amp]
        i = min(range(len(ev)), key=lambda j: (phi - ev[j]) % 1.0)  # the last event
        since = (phi - ev[i]) % 1.0
        a_now, a_prev = amp[i], amp[i - 1]
        if since < thrust:          # thrust: from the back of the last hold to the front
            s = since / thrust
            s = s * s * (3 - 2 * s)
            x = -a_prev + (a_now + a_prev) * s
        else:                       # hold: slides back at the ground speed
            x = a_now - 2 * a_now * (since - thrust) / (gaps[i] - thrust)
        th = np.degrees(x / reach)
        return {"Neck1": pitch(th), "Neck2": pitch(-th)}

    def _gait(self, name: str, run: bool) -> Clip:
        if self.hops:
            return self._hop(name, run)
        L = self.L
        def upper(phi, g):
            right = g.phases["Right"]  # a walk's steps are a little uneven (a frame early)
            w = 2 * np.pi * phi
            f = phi * g.frames
            side = g.swinging("Right", f) - g.swinging("Left", f)  # + : right foot in the air
            T = g.seconds
            since = min((phi - 0.0) % 1.0, (phi - right) % 1.0) * T
            pump = 8 * _pulse(since, 0.05)  # the tail flicks up as each foot lands
            r = {"Hips": roll(5 * side) @ pitch(10 if run else 0) @ yaw(3 * np.cos(w)),
                 "Head": pitch(-(10 if run else 0) * 0.5),
                 "Tail1": pitch(pump), "Tail2": pitch(0.6 * pump),
                 **self._wings(12 if run else 0, (14 if run else 1) + 3 * np.sin(2 * w)),
                 **self._head_hold(phi, g, [0.0, right])}
            return r, {"Hips": np.array([0.015 * L * np.cos(w - np.pi * g.duty), 0.0, 0.0])}, {}

        def curl(s, lg):
            return 70 * np.sin(np.pi * s) ** 1.5

        if run:
            kw = dict(duty=0.38, lift=0.30 * L, phases=BIPED)
            return self.gait_clip(name, kw, 0.0, 0.03, 0.0, upper, curl)
        kw = dict(duty=0.6, lift=0.30 * L, phases=BIPED)
        return self.gait_clip(name, kw, 0.0, 0.03, 0.0, upper, curl, early_right=1)

    def _hop(self, name: str, run: bool) -> Clip:
        """A small bird's hop: both feet together; on landing the legs give (a crouch), push
        off, the body arcs through the air with the feet tucked, and lands planted. The body
        tips forward into the push and back for the landing, the tail flicks up as it lands,
        the wings lift a little in the air, the head holds still over the ground and thrusts
        forward at take-off."""
        L = self.L
        duty = 0.42 if run else 0.55
        arc = (0.40 if run else 0.30) * L
        tuck = 0.20 * L
        give = (0.18 if run else 0.14) * L

        def air(phi, g):
            x, z, on, s = g.foot("Left", phi * g.frames)
            return None if on else s

        def rise(phi, g):
            s = air(phi, g)
            return 0.0 if s is None else arc * 4 * s * (1 - s)

        def dip(phi, g):
            return give * np.sin(np.pi * phi / duty) if air(phi, g) is None else 0.0

        def upper(phi, g):
            s = air(phi, g)
            T = g.seconds
            since = phi * T                               # landing is phi 0
            pump = 15 * _pulse(since, 0.05)
            pump2 = 15 * _pulse(since - FRAME, 0.05)      # the tail tip a frame behind
            if s is None:                                 # on the ground: tip into the push
                lean = 8 * np.sin(np.pi * phi / duty) ** 2 * (phi / duty)
                flap = 0.0
            else:                                         # in the air: level, nose up to land
                lean = 8 * (1 - s) ** 2 - 4 * s * s
                flap = np.sin(np.pi * s)
            r = {"Hips": pitch(lean + (6 if run else 0)),
                 "Head": pitch(-(lean + (6 if run else 0)) * 0.7),
                 "Tail1": pitch(pump), "Tail2": pitch(0.6 * pump2),
                 **self._wings(8 * flap, 12 * flap),
                 **self._head_hold(phi, g, [duty])}
            return r, {}, {}

        def curl(s, lg):
            return 70 * np.sin(np.pi * s) ** 1.5

        # no heel roll: both feet push off and land flat together (a roll about each toe tip
        # would lift two feet of slightly different shape by different heights)
        kw = dict(duty=duty, lift=arc + tuck, phases=HOP)
        return self.gait_clip(name, kw, 0.0, 0.03, 0.0, upper, curl, roll=0.0, dip=dip,
                              rise=rise)

    def walk(self) -> Clip:
        return self._gait("walk", False)

    def run(self) -> Clip:
        return self._gait("run", True)

    def attack(self) -> Clip:
        """Peck: the neck draws back with the wings up and holds a beat, then strikes forward
        and down, driven from the body through the neck to the head (a frame each), past the
        mark, and back."""
        L = self.L
        k = Keys([0.0, 0.26, 0.33, 0.38, 0.45, 0.82],
                 shape=["smooth", "smooth", "in", "out", "smooth"],
                 lean=[0, -8, -8, 18, 20, 0], neck=[0, -25, -26, 30, 34, 0],
                 head=[0, -10, -11, 20, 24, 0], wopen=[0, 25, 25, 10, 8, 0],
                 wraise=[0, 35, 36, 10, 8, 0], hz=[0, 0.04, 0.04, 0.08, 0.08, 0])
        chain = Chain(k, {"body": 0.0, "neck": FRAME, "head": 2 * FRAME, "wings": 2 * FRAME},
                      start=2)

        def frame(c, t):
            bd, nk, hd, wg = (c[g] for g in ("body", "neck", "head", "wings"))
            r = {"Hips": pitch(bd["lean"]), "Neck1": pitch(nk["neck"] * 0.6),
                 "Neck2": pitch(nk["neck"] * 0.4), "Head": pitch(hd["head"]),
                 **self._wings(wg["wopen"], wg["wraise"])}
            mv = {"Hips": np.array([0.0, 0.0, -0.02 * L - bd["hz"] * L])}
            return self.pose(r, mv, self.planted())

        return self.keyed_clip("attack", chain, frame)

    def hit(self) -> Clip:
        """Knocked back at once; the neck and head whip a frame or two later and the wings
        flare late, then it settles."""
        L = self.L
        k = Keys([0.0, 0.07, 0.20, 0.33, 0.5], shape=["out", "smooth", "smooth", "smooth"],
                 back=[0, -12, -8, 2, 0], neck=[0, -20, -10, 3, 0], wopen=[0, 30, 20, 3, 0],
                 wraise=[0, 40, 25, 4, 0], hz=[0, 0.05, 0.05, 0.01, 0], hx=[0, -0.08, -0.06, 0, 0])
        chain = Chain(k, {"body": 0.0, "neck": FRAME, "head": 2 * FRAME, "wings": 2 * FRAME})

        def frame(c, t):
            bd, nk, hd, wg = (c[g] for g in ("body", "neck", "head", "wings"))
            r = {"Hips": pitch(bd["back"]), "Neck1": pitch(nk["neck"]),
                 "Head": pitch(hd["neck"] * 0.5),
                 **self._wings(wg["wopen"], wg["wraise"])}
            mv = {"Hips": FWD * bd["hx"] * L + np.array([0.0, 0.0, -0.02 * L - bd["hz"] * L])}
            return self.pose(r, mv, self.planted())

        return self.keyed_clip("hit", chain, frame)

    def faint(self) -> Clip:
        return _side_faint(self, neck=(-8, 28, 12), tail=None, sink_to=0.50, fall=84)


def _side_faint(a: Animator, neck: tuple, tail: tuple | None, sink_to: float,
                fall: float) -> Clip:
    """An animal's or bird's faint: a small reel (head up), the legs fold and the body drops
    (accelerating, under gravity), it tips over onto its right side faster and faster, stops
    dead on the floor at 0.70 s with a small bounce, and lies still. The neck and head follow a
    few frames late, the tail later, the wings splay; all settled within 0.15 s of the landing."""
    b = a.b
    land = 0.70
    sink = min(lg.hip[2] - lg.ground_z for lg in b.legs)
    body = Keys([0.0, 0.12, land, land + 0.04, land + 0.08, 1.30],
                shape=["smooth", "in", "out", "in", "smooth"],
                hz=[0, 0, sink_to, sink_to, sink_to, sink_to])
    tip = Keys([0.0, 0.30, land, land + 0.04, land + 0.08, 1.30],
               shape=["smooth", "in3", "out", "in", "smooth"],
               v=[0, 0, fall, fall - 4, fall, fall])
    nk = Keys([0.0, 0.12, 0.45, 0.62], neck=list((0, *neck)))
    tl = Keys([0.0, 0.15, 0.45, 0.60], tail=list((0, *tail))) if tail else None
    wings = Keys([0.0, 0.30, land, land + 0.07, land + 0.13], o=[0, 10, 30, 40, 35],
                 r=[0, 5, -5, -12, -10])
    pts = np.array([*b.head.values(), *b.tail.values()])
    pivot = np.array([float(pts[:, 0].min()), float(np.median(pts[:, 1])), 0.0])
    lag_neck, lag_tail = 3 * FRAME, 5 * FRAME

    def frame(c, t):
        n = nk.at(t - lag_neck)["neck"]
        r = {"Neck1": pitch(n), "Head": pitch(n * 0.6)}
        if tl is not None:
            r.update(a._tail(0, 0, tl.at(t - lag_tail)["tail"] * 4))
        if isinstance(a, Bird):
            w = wings.at(t)
            r.update(a._wings(w["o"], w["r"]))
        mv = {"Hips": np.array([0.0, 0.0, -0.02 * a.L - c["hz"] * sink])}  # standing drop
        return a.pose(r, mv, a.planted(), root=about(roll(tip.at(t)["v"]), pivot))

    clip = a.keyed_clip("faint", body, frame)
    clip.land_frame = int(round(land * a.fps))
    return clip


ANIMATORS = {"humanoid": Humanoid, "four_legged": FourLegged, "bird": Bird}


def animator(body: Body) -> Animator:
    return ANIMATORS[body.template](body)


def library_clip(body: Body, name: str) -> Clip:
    """A humanoid's clip from the hand-made library (animate.library), solved like the rest."""
    from asset_forge.animate import library

    poses, meta = library.retarget(body, library.LIBRARY_CLIPS[name])
    if meta["loop"]:
        poses[-1] = poses[0]  # a loop ends on exactly its first frame
    clip = Clip(name, meta["fps"], meta["loop"], meta["speed"] if name in ("walk", "run") else 0.0,
                poses, library=True)
    a = Animator.__new__(Animator)
    a.b = body
    clip = Animator.finish(a, clip)
    if name in ("walk", "run"):
        clip.speed = _fit_speed(body, clip)
        _pin_feet(body, clip)
    if name == "faint":  # lands when the pelvis is within a tenth of the height of its final rest
        z = np.array([p.move["Hips"][2] for p in poses])
        clip.land_frame = int(np.argmax(z <= z[-1] + 0.1 * body.height))
    return clip


def _fit_speed(body: Body, clip: Clip) -> float:
    """The ground speed (near the nominal one) at which the planted feet slide least: a clip made
    for another body may be a few percent off the speed its feet were made for."""
    from asset_forge.animate.gait import foot_slide

    toes = [f"{s}Toes" for s in ("Left", "Right")]
    tracks = [np.array([body.joint_positions(D)[t] for D in clip.deltas]) for t in toes]
    best, best_w = clip.speed, float("inf")
    for k in np.linspace(0.6, 1.5, 91):
        v = clip.speed * float(k)
        w = max(foot_slide(tr, clip.fps, v, (0.0, -1.0, 0.0), (0.0, 0.0, 1.0),
                           0.01 * body.leg_len).worst_m for tr in tracks)
        if w < best_w:
            best, best_w = v, w
    return best


PIN_TOL = 0.01   # a foot is down when its ball is this close (of leg length) to its lowest
PIN_RAMP = 1     # frames a hold is eased in and out over


def _pin_feet(body: Body, clip: Clip) -> None:
    """Hold every planted foot still on the ground. A hand-made walk made for another body
    leaves the feet a cm or two off the ground speed (the stance foot swings on an arc). For
    each stretch of frames a foot is down, its ankle is moved (a few cm at most, eased in and
    out) to stay where it was set down, and the leg is re-solved by IK; the foot keeps its own
    turn. The loop is unrolled three times so a stretch that wraps the seam is one stretch."""
    P = [body.joint_positions(D) for D in clip.deltas]
    m = clip.frames - 1  # a loop's last frame is its first
    fwd = np.array([0.0, -1.0, 0.0])
    tol = PIN_TOL * body.leg_len
    ramp = PIN_RAMP
    for lg in body.legs:
        toes_z = np.array([p[f"{lg.name}Toes"][2] for p in P[:m]])
        contact = np.tile(toes_z <= toes_z.min() + tol, 3)
        ank = np.array([p[lg.foot] for p in P[:m]])
        ball = np.array([p[f"{lg.name}Toes"] for p in P[:m]])  # what stays put: the ball
        g = np.tile(ball, (3, 1)) + np.outer(np.arange(3 * m) / clip.fps * clip.speed, fwd)
        shift = np.zeros((m, 3))
        e = 0
        while e < 3 * m:
            if not contact[e]:
                e += 1
                continue
            j = e
            while j + 1 < 3 * m and contact[j + 1]:
                j += 1
            run = np.arange(e, j + 1)
            hold = g[run].mean(axis=0)
            for k, i in enumerate(run):
                if m <= i < 2 * m:
                    w = min((min(k, len(run) - 1 - k) + 1) / (ramp + 1), 1.0)
                    d = (hold - g[i]) * w
                    d[2] = 0.0
                    shift[i - m] = d
            e = j + 1
        for f, pose in enumerate(clip.poses):
            D = clip.deltas[f]
            pose.feet[lg.name] = (ank[f % m] + shift[f % m], D[lg.foot][:3, :3].copy())
    clip.deltas, clip.short = [], {}
    for pose in clip.poses:
        D, short = body.solve(pose)
        clip.deltas.append(D)
        for s_ in short:
            clip.short[s_] = clip.short.get(s_, 0) + 1


def make_clips(body: Body, names=CLIP_NAMES, library: bool = True) -> list[Clip]:
    """The six clips. A humanoid's come from the hand-made library (library=False, or the
    AF_PROCEDURAL_HUMANOID=1 environment variable, makes the procedural ones instead)."""
    if body.template == "humanoid" and library and os.environ.get("AF_PROCEDURAL_HUMANOID") != "1":
        return [library_clip(body, n) for n in names]
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
