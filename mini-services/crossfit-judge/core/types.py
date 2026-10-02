"""Shared data types for the analysis pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from utils.geometry import Point


# --------------------------------------------------------------------------- #
# Pose frames
# --------------------------------------------------------------------------- #
# MediaPipe Pose landmark indices (subset used for judging).
LM_INDEX = {
    "nose": 0,
    "left_shoulder": 11, "right_shoulder": 12,
    "left_elbow": 13, "right_elbow": 14,
    "left_wrist": 15, "right_wrist": 16,
    "left_hip": 23, "right_hip": 24,
    "left_knee": 25, "right_knee": 26,
    "left_ankle": 27, "right_ankle": 28,
    "left_heel": 29, "right_heel": 30,
    "left_foot_index": 31, "right_foot_index": 32,
}


@dataclass
class PoseFrame:
    """Named landmarks for one frame (image pixels, y grows downward)."""
    points: dict[str, Point] = field(default_factory=dict)
    frame_index: int = 0
    timestamp: float = 0.0
    person_detected: bool = False

    def get(self, name: str) -> Optional[Point]:
        return self.points.get(name)

    def mid(self, a: str, b: str) -> Optional[Point]:
        pa, pb = self.points.get(a), self.points.get(b)
        if pa is None or pb is None:
            return None
        return Point((pa.x + pb.x) / 2, (pa.y + pb.y) / 2, (pa.z + pb.z) / 2,
                     min(pa.visibility, pb.visibility))


# --------------------------------------------------------------------------- #
# Scene model — calibration, ground plane, bar anchor
# --------------------------------------------------------------------------- #
@dataclass
class SceneModel:
    """Everything the movement FSMs need to know about the scene.

    H            : athlete body height in pixels (scale reference — every
                   spatial threshold is a fraction of H)
    ground       : linear ground model y = a + b·x fitted from foot contacts
    bar_anchor   : estimated bar-on-ground position (x, y, confidence)
    """
    H: float = 0.0
    ground_a: float = 0.0
    ground_b: float = 0.0
    ground_fit: bool = False
    bar_x: float = 0.0
    bar_y: float = 0.0
    bar_confidence: float = 0.0

    def ground_y_at(self, x: float) -> Optional[float]:
        if not self.ground_fit:
            return None
        return self.ground_a + self.ground_b * x

    def set_ground(self, a: float, b: float) -> None:
        self.ground_a, self.ground_b, self.ground_fit = a, b, True

    def set_bar(self, x: float, y: float, confidence: float) -> None:
        self.bar_x, self.bar_y = x, y
        self.bar_confidence = max(self.bar_confidence, confidence)


# --------------------------------------------------------------------------- #
# Attempts & events
# --------------------------------------------------------------------------- #
REP = "rep"
NO_REP = "no_rep"

@dataclass
class Attempt:
    """One judged rep attempt of a movement."""
    movement: str
    t_start: float
    t_end: float
    frame_start: int
    frame_end: int
    outcome: str                       # REP | NO_REP
    reason_code: Optional[str] = None  # why no-rep (or None when credited)
    details: dict = field(default_factory=dict)
    review_flags: list[str] = field(default_factory=list)  # reason codes to review

    def to_dict(self) -> dict:
        return {
            "movement": self.movement,
            "t_start": round(self.t_start, 2),
            "t_end": round(self.t_end, 2),
            "frame_start": self.frame_start,
            "frame_end": self.frame_end,
            "outcome": self.outcome,
            "reason_code": self.reason_code,
            "details": self.details,
            "review_flags": list(self.review_flags),
        }
