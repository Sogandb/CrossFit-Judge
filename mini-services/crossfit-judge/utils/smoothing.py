"""
Signal smoothing utilities for noisy pose data.
"""
from __future__ import annotations

from collections import deque

import numpy as np


class MovingAverageFilter:
    """O(1) moving average over a fixed window."""

    def __init__(self, window: int = 5):
        self.window = max(1, window)
        self._buf: deque[float] = deque(maxlen=self.window)
        self._sum = 0.0

    def update(self, value: float) -> float:
        if len(self._buf) == self._buf.maxlen:
            self._sum -= self._buf[0]
        self._buf.append(value)
        self._sum += value
        return self._sum / len(self._buf)

    def reset(self) -> None:
        self._buf.clear()
        self._sum = 0.0


class AngleSmoother:
    """
    Smooths a stream of joint angles. Angles wrap at 0/360 but for our use
    case (0-180 degree joints) a plain moving average is sufficient.
    """

    def __init__(self, window: int = 5):
        self._filter = MovingAverageFilter(window)

    def update(self, angle: float | None) -> float | None:
        if angle is None:
            return None
        return self._filter.update(angle)

    def reset(self) -> None:
        self._filter.reset()


def median_filter(values: list[float], window: int = 3) -> list[float]:
    """A simple offline median filter for post-processing."""
    if not values:
        return []
    half = window // 2
    out: list[float] = []
    for i in range(len(values)):
        lo = max(0, i - half)
        hi = min(len(values), i + half + 1)
        out.append(float(np.median(values[lo:hi])))
    return out
