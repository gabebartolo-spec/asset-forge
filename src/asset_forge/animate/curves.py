"""Key poses to motion.

Between two keys a control moves on a shape-preserving cubic (no overshoot past a key), flat at
the first and last key so a one-shot clip starts and ends at rest. A segment can instead be
given a timing shape, so a move has weight instead of easing in and out everywhere:

    "smooth"  the shape-preserving cubic (default)
    "in"      starts at rest and speeds up the whole way: a fall under gravity (s^2), or a blow
              driven hard into its target (a hard stop at the key)
    "in3"     the same, sharper (s^3): a body toppling over
    "out"     starts at full speed and slows to rest: a recoil from a blow, the rebound of a bounce
    "lin"     constant speed

A Chain samples one set of keys later and later down the body (per-bone time offsets): the
kinetic chain of a swing (hips, then chest, then arm, then head) or the lag of a collapse.
"""

from __future__ import annotations

import numpy as np

SHAPES = ("smooth", "in", "in3", "out", "lin")


def _ease(shape: str, s: float) -> float:
    if shape == "in":
        return s * s
    if shape == "in3":
        return s * s * s
    if shape == "out":
        return 1.0 - (1.0 - s) ** 2
    return s  # "lin"


def pchip(times, values, t: float, shapes=None) -> float:
    xs = np.asarray(times, float)
    ys = np.asarray(values, float)
    if t <= xs[0]:
        return float(ys[0])
    if t >= xs[-1]:
        return float(ys[-1])
    k = int(np.searchsorted(xs, t, side="right") - 1)
    h = np.diff(xs)
    s = (t - xs[k]) / h[k]
    if shapes is not None and shapes[k] != "smooth":
        return float(ys[k] + (ys[k + 1] - ys[k]) * _ease(shapes[k], s))
    d = np.diff(ys) / h
    m = np.zeros(len(xs))
    for j in (k, k + 1):
        if 0 < j < len(xs) - 1 and d[j - 1] * d[j] > 0:
            w1, w2 = 2 * h[j] + h[j - 1], h[j] + 2 * h[j - 1]
            m[j] = (w1 + w2) / (w1 / d[j - 1] + w2 / d[j])
    h00, h10 = 2 * s**3 - 3 * s**2 + 1, s**3 - 2 * s**2 + s
    h01, h11 = -2 * s**3 + 3 * s**2, s**3 - s**2
    return float(h00 * ys[k] + h10 * h[k] * m[k] + h01 * ys[k + 1] + h11 * h[k] * m[k + 1])


class Keys:
    """Named controls keyed at shared times: Keys([0, .3, .9], hx=[0, -.03, 0], ...).
    shape: one timing shape per segment (len(times) - 1, see SHAPES); default all smooth."""

    def __init__(self, times, shape=None, **controls):
        self.times = list(times)
        for name, vals in controls.items():
            if len(vals) != len(self.times):
                raise ValueError(f"{name}: {len(vals)} keys for {len(self.times)} times")
        if shape is not None:
            shape = list(shape)
            if len(shape) != len(self.times) - 1 or any(s not in SHAPES for s in shape):
                raise ValueError(f"shape needs {len(self.times) - 1} of {SHAPES}")
        self.shape = shape
        self.controls = controls

    def at(self, t: float) -> dict[str, float]:
        return {k: pchip(self.times, v, t, self.shape) for k, v in self.controls.items()}

    def __getitem__(self, name):
        return self.controls[name]

    def shifted(self, lag: float, start: int = 0) -> Keys:
        """The same keys with every time from index `start` on moved `lag` seconds later."""
        times = [t + (lag if i >= start else 0.0) for i, t in enumerate(self.times)]
        return Keys(times, self.shape, **self.controls)

    @property
    def end(self) -> float:
        return self.times[-1]


class Chain:
    """Per-bone time offsets: the same keys, later for each body group by `lags[group]`
    seconds, so a move starts in the hips and arrives in the hand (or head) a few frames after.
    Keys from index `start` on are delayed; earlier keys stay shared (start=2 on a swing keeps
    the wind-up together and lags the strike; start=0 lags the whole move).
    at(t) -> {group: controls}; the clip lasts until the last group has finished."""

    def __init__(self, keys: Keys, lags: dict[str, float], start: int = 0):
        self.groups = {g: keys.shifted(lag, start) for g, lag in lags.items()}

    def at(self, t: float) -> dict[str, dict[str, float]]:
        return {g: k.at(t) for g, k in self.groups.items()}

    @property
    def end(self) -> float:
        return max(k.end for k in self.groups.values())
