"""
Geometry helpers for joint-angle calculations from MediaPipe landmarks.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np


@dataclass(frozen=True)
class Point:
    """A 2D point with visibility/presence."""
    x: float
    y: float
    z: float = 0.0
    visibility: float = 1.0

    @property
    def is_visible(self) -> bool:
        return self.visibility >= 0.5


def to_point(landmark) -> Point:
    """Convert a MediaPipe landmark object to a Point."""
    return Point(
        x=float(landmark.x),
        y=float(landmark.y),
        z=float(getattr(landmark, "z", 0.0)),
        visibility=float(getattr(landmark, "visibility", 1.0)),
    )


def angle_2d(a: Point, b: Point, c: Point) -> float:
    """
    Angle (in degrees) at vertex `b` formed by points a-b-c, measured in the
    2D image plane. The MediaPipe coordinate system has y growing downward,
    but the angle is invariant to that sign flip.
    """
    a = np.array([a.x, a.y])
    b = np.array([b.x, b.y])
    c = np.array([c.x, c.y])
    ba = a - b
    bc = c - b
    cos_angle = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc) + 1e-8)
    cos_angle = float(np.clip(cos_angle, -1.0, 1.0))
    return math.degrees(math.acos(cos_angle))


def vertical_distance(a: Point, b: Point) -> float:
    """Absolute vertical distance in normalised coordinates."""
    return abs(a.y - b.y)


def midpoint(a: Point, b: Point) -> Point:
    return Point((a.x + b.x) / 2, (a.y + b.y) / 2)


def all_visible(points: Sequence[Point]) -> bool:
    return all(p.is_visible for p in points)


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))
