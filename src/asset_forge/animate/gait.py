"""The gait generator (where each foot is on every frame of a walk or run) and the foot-slide
metric that proves planted feet do not slide. Pure numpy.

The clips are in place: the body stays over the origin and the ground runs under it at the
clip's `speed` (metres per second, along -Y). A planted foot therefore moves backwards at exactly
`speed`; seen from the ground it stands still. The game moves the character at that speed.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Walk and run patterns. phase = when in the cycle each foot lands (fraction of the cycle).
BIPED = {"Left": 0.0, "Right": 0.5}
QUAD_WALK = {"HindLeft": 0.0, "FrontLeft": 0.25, "HindRight": 0.5, "FrontRight": 0.75}
QUAD_TROT = {"FrontLeft": 0.0, "HindRight": 0.0, "FrontRight": 0.5, "HindLeft": 0.5}


@dataclass(frozen=True)
class Gait:
    frames: int              # frames in one cycle (the clip loops after it)
    fps: int
    duty: float              # fraction of the cycle each foot is on the ground
    stroke: float            # metres a planted foot travels under the body
    lift: float              # metres a swinging foot rises
    phases: dict[str, float]

    @property
    def seconds(self) -> float:
        return self.frames / self.fps

    @property
    def speed(self) -> float:
        """Ground speed in m/s that keeps a planted foot still."""
        return self.stroke / (self.duty * self.seconds)

    def foot(self, leg: str, frame: float) -> tuple[float, float, bool, float]:
        """(forward offset from the foot's rest spot, lift, on the ground, swing progress 0-1)."""
        phi = (frame / self.frames + self.phases[leg]) % 1.0
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
        return x, self.lift * np.sin(np.pi * s), False, s


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
