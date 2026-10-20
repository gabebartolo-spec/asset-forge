"""Key poses to smooth motion: a shape-preserving cubic (no overshoot past a key), flat at the
first and last key so a one-shot clip starts and ends at rest."""

from __future__ import annotations

import numpy as np


def pchip(times, values, t: float) -> float:
    xs = np.asarray(times, float)
    ys = np.asarray(values, float)
    if t <= xs[0]:
        return float(ys[0])
    if t >= xs[-1]:
        return float(ys[-1])
    h = np.diff(xs)
    d = np.diff(ys) / h
    m = np.zeros(len(xs))
    for k in range(1, len(xs) - 1):
        if d[k - 1] * d[k] > 0:
            w1, w2 = 2 * h[k] + h[k - 1], h[k] + 2 * h[k - 1]
            m[k] = (w1 + w2) / (w1 / d[k - 1] + w2 / d[k])
    k = int(np.searchsorted(xs, t, side="right") - 1)
    s = (t - xs[k]) / h[k]
    h00, h10 = 2 * s**3 - 3 * s**2 + 1, s**3 - 2 * s**2 + s
    h01, h11 = -2 * s**3 + 3 * s**2, s**3 - s**2
    return float(h00 * ys[k] + h10 * h[k] * m[k] + h01 * ys[k + 1] + h11 * h[k] * m[k + 1])


class Keys:
    """Named controls keyed at shared times: Keys([0, .3, .9], hx=[0, -.03, 0], ...)."""

    def __init__(self, times, **controls):
        self.times = list(times)
        for name, vals in controls.items():
            if len(vals) != len(self.times):
                raise ValueError(f"{name}: {len(vals)} keys for {len(self.times)} times")
        self.controls = controls

    def at(self, t: float) -> dict[str, float]:
        return {k: pchip(self.times, v, t) for k, v in self.controls.items()}

    def __getitem__(self, name):
        return self.controls[name]

    @property
    def end(self) -> float:
        return self.times[-1]
