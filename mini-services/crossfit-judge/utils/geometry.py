"""Geometry helpers shared by all movement FSMs. All positions are in image
pixels (y grows downward). Scale is expressed as a fraction of the athlete's
calibrated body height H so every threshold is scale-invariant."""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable


@dataclass(frozen=True)
class Point:
    x: float
    y: float
    z: float = 0.0
    visibility: float = 1.0


def midpoint(a: Point, b: Point) -> Point:
    return Point(
        (a.x + b.x) / 2.0,
        (a.y + b.y) / 2.0,
        (a.z + b.z) / 2.0,
        min(a.visibility, b.visibility),
    )


def dist(a: Point, b: Point) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)


def angle_at(a: Point, b: Point, c: Point) -> float:
    """Interior angle at vertex b formed by segments b→a and b→c, in degrees (0–180)."""
    v1 = (a.x - b.x, a.y - b.y)
    v2 = (c.x - b.x, c.y - b.y)
    n1 = math.hypot(*v1)
    n2 = math.hypot(*v2)
    if n1 < 1e-9 or n2 < 1e-9:
        return 180.0
    cos = (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)
    cos = max(-1.0, min(1.0, cos))
    return math.degrees(math.acos(cos))


def line_tilt_deg(p: Point, q: Point) -> float:
    """Tilt of segment p→q vs the image horizontal axis, in degrees (0–90).

    0° = perfectly horizontal line (what we expect from the shoulders when an
    athlete is FACING the bar); approaching 90° = near-vertical line (body
    parallel to the bar — the faulty orientation)."""
    dx = abs(q.x - p.x)
    dy = abs(q.y - p.y)
    if dx < 1e-9 and dy < 1e-9:
        return 0.0
    return math.degrees(math.atan2(dy, dx))


def vis_ok(p: Point | None, threshold: float) -> bool:
    return p is not None and p.visibility >= threshold


def avg_visibility(points: Iterable[Point | None]) -> float:
    pts = [p for p in points if p is not None]
    if not pts:
        return 0.0
    return sum(p.visibility for p in pts) / len(pts)


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))
