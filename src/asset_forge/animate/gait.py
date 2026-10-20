"""The gait generator (where each foot is on every frame of a walk or run) and the foot-slide
metric that proves planted feet do not slide. Pure numpy.

The clips are in place: the body stays over the origin and the ground runs under it at the
clip's `speed` (metres per second, along -Y). A planted foot therefore moves backwards at exactly
`speed`; seen from the ground it stands still. The game moves the character at that speed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

# Walk and run patterns. phase = when in the cycle each foot lands (fraction of the cycle).
BIPED = {"Left": 0.0, "Right": 0.5}
QUAD_WALK = {"HindLeft": 0.0, "FrontLeft": 0.25, "HindRight": 0.5, "FrontRight": 0.75}
QUAD_TROT = {"FrontLeft": 0.0, "HindRight": 0.0, "FrontRight": 0.5, "HindLeft": 0.5}
HOP = {"Left": 0.0, "Right": 0.0}  # both feet together: a small bird's hop


@dataclass(frozen=True)
class Gait:
    frames: int              # frames in one cycle (the clip loops after it)
    fps: int
    duty: float              # fraction of the cycle each foot is on the ground
    stroke: float            # metres a planted foot travels under the body
    lift: float              # metres a swinging foot rises
    phases: dict[str, float]
    early: tuple[str, ...] = ()  # legs whose foot lifts early in the swing (a tuck, not a drag)
    lifts: dict[str, float] = field(default_factory=dict)  # leg -> its own swing lift (metres)

    @property
    def seconds(self) -> float:
        return self.frames / self.fps

    @property
    def speed(self) -> float:
        """Ground speed in m/s that keeps a planted foot still."""
        return self.stroke / (self.duty * self.seconds)

    def lift_of(self, leg: str) -> float:
        return self.lifts.get(leg, self.lift)

    def swinging(self, leg: str, frame: float) -> float:
        """How far through its swing the foot is, as sin(pi s): 0 on the ground, 1 mid-swing."""
        x, z, on, s = self.foot(leg, frame)
        return 0.0 if on else float(np.sin(np.pi * s))

    def foot(self, leg: str, frame: float) -> tuple[float, float, bool, float]:
        """(forward offset from the foot's rest spot, lift, on the ground, swing progress 0-1)."""
        phi = (frame / self.frames + self.phases[leg]) % 1.0
        lift = self.lift_of(leg)
        half = self.stroke / 2
        if phi < self.duty:
            return half - self.stroke * phi / self.duty, 0.0, True, 0.0
        s = (phi - self.duty) / (1.0 - self.duty)
        # Hermite from the back to the front; both ends move at the planted foot's speed, so the
        # foot leaves and meets the ground without skidding.
        m = -self.stroke * (1.0 - self.duty) / self.duty
        h00, h10 = 2 * s**3 - 3 * s**2 + 1, s**3 - 2 * s**2 + s
        h01, h11 = -2 * s**3 + 3 * s**2, s**3 - s**2
        x = h00 * -half + h10 * m + h01 * half + h11 * m
        if leg in self.early:  # highest 30% of the way through, then down to land
            p = 0.3
            w = s / p if s < p else 1.0 + (s - p) / (1.0 - p)
            return x, lift * np.sin(0.5 * np.pi * w), False, s
        return x, lift * np.sin(np.pi * s), False, s

    def roll(self, leg: str, frame: float, start: float = 0.55, settle: float = 0.4) -> float:
        """How far (0-1) the heel is lifted: it rises over the last part of the stance (from
        `start` of it) as the leg pushes off, and settles over the first `settle` of the swing.
        The foot pivots about its ball or tip, which stays planted, so this lengthens the
        stride without sliding."""
        phi = (frame / self.frames + self.phases[leg]) % 1.0
        if phi < self.duty:
            return _smooth((phi / self.duty - start) / (1.0 - start))
        return 1.0 - _smooth((phi - self.duty) / (1.0 - self.duty) / settle)

    def strike(self, leg: str, frame: float, flat: float = 0.2, ready: float = 0.35) -> float:
        """How far (0-1) the toes are up for heel strike: they come up over the last `ready`
        of the swing, the heel lands, and the foot rocks down about the heel to lie flat by
        `flat` of the stance (the heel stays planted, so nothing slides)."""
        phi = (frame / self.frames + self.phases[leg]) % 1.0
        if phi < self.duty:
            return 1.0 - _smooth(phi / self.duty / flat)
        return _smooth(((phi - self.duty) / (1.0 - self.duty) - (1.0 - ready)) / ready)


def _smooth(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return x * x * (3.0 - 2.0 * x)


@dataclass
class Slide:
    worst_m: float           # longest distance one planted foot slid in a single contact
    worst_speed: float       # fastest a planted foot moved over the ground (m/s)
    contact_frames: int

    def ok(self, leg_len: float, frac: float = 0.02) -> bool:
        return self.contact_frames > 0 and self.worst_m <= frac * leg_len


def foot_slide(track: np.ndarray, fps: float, speed: float, forward=(0.0, -1.0, 0.0),
               up=(0.0, 0.0, 1.0), tol: float = 0.01) -> Slide:
    """Slide of one foot over a clip. track: (F, 3) positions of a point on the foot, in place.
    A frame is a contact frame when the point is within `tol` metres of its lowest height.
    Seen from the ground (track + forward * speed * t) a planted foot must not move."""
    p = np.asarray(track, float)
    fwd, up = np.asarray(forward, float), np.asarray(up, float)
    t = np.arange(len(p)) / fps
    ground = p + np.outer(t * speed, fwd)
    h = p @ up
    contact = h <= h.min() + tol
    flat = ground - np.outer(ground @ up, up)
    worst, run, fastest = 0.0, 0.0, 0.0
    for i in range(len(p) - 1):
        if contact[i] and contact[i + 1]:
            d = float(np.linalg.norm(flat[i + 1] - flat[i]))
            run += d
            fastest = max(fastest, d * fps)
            worst = max(worst, run)
        else:
            run = 0.0
    return Slide(worst, fastest, int(contact.sum()))
