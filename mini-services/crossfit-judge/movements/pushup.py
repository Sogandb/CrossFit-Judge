"""
Push-up detector.

Driven by the elbow angle (shoulder-elbow-wrist). The bottom position is
additionally verified by checking that the chest (mid-shoulder y) drops close
to the floor, which is the CrossFit standard ("chest to ground").

Standards:
  * Bottom: chest touches the ground (shoulder y near frame bottom)
  * Top:    full lockout, elbow angle >= ~160
"""
from __future__ import annotations

from typing import Any

from core.pose_detector import PoseFrame
from movements.base_movement import BaseMovement, _RepBuffer
from utils.geometry import angle_2d, midpoint
from utils.smoothing import AngleSmoother


class Pushup(BaseMovement):
    name = "pushup"
    start_threshold = 160.0
    bottom_threshold = 90.0
    extended_is_high = True

    def __init__(self, standards: dict[str, Any] | None = None):
        super().__init__(standards)
        self.lockout_angle = float(self.standards.get("top_lockout_angle", 155))
        self.chest_distance = float(self.standards.get("bottom_chest_distance", 0.08))
        self._elbow_smoother = AngleSmoother(window=5)
        self._ground_y: float | None = None  # calibrated per-video

    def calibrate(self, ground_y: float) -> None:
        """Set the ground line y-coordinate (normalised) from the first frame."""
        self._ground_y = ground_y

    def _key_signals(self, pose: PoseFrame) -> dict[str, float]:
        ls, rs = pose.get("left_shoulder"), pose.get("right_shoulder")
        le, re = pose.get("left_elbow"), pose.get("right_elbow")
        lw, rw = pose.get("left_wrist"), pose.get("right_wrist")
        if not all([ls, rs, le, re, lw, rw]):
            return {}

        left = angle_2d(ls, le, lw)
        right = angle_2d(rs, re, rw)
        raw_elbow = (left + right) / 2
        elbow = self._elbow_smoother.update(raw_elbow)
        if elbow is None:
            return {}

        chest = midpoint(ls, rs)
        # Distance from chest to the calibrated ground line (or ankle y).
        ground = self._ground_y
        if ground is None:
            la, ra = pose.get("left_ankle"), pose.get("right_ankle")
            if la and ra:
                ground = (la.y + ra.y) / 2
        chest_to_ground = (ground - chest.y) if ground is not None else 0.0

        return {"primary": elbow, "elbow": elbow, "chest_to_ground": chest_to_ground}

    def _validate(self, rep: _RepBuffer) -> tuple[bool, str | None, str | None, float]:
        extremes = rep.extremes()
        elbow_ex = extremes.get("elbow")
        chest_ex = extremes.get("chest_to_ground")
        if not elbow_ex:
            return False, "Elbow angle not detected", "elbow_not_detected", 0.0

        elbow_min = elbow_ex["min"]   # most bent (bottom)
        elbow_max = elbow_ex["max"]   # most extended (top)

        # --- Bottom: chest to ground -----------------------------------------
        if chest_ex is not None:
            chest_min_dist = chest_ex["min"]  # closest chest got to ground
            if chest_min_dist > self.chest_distance:
                reason_en = f"Chest did not reach ground (distance {chest_min_dist:.2f} above allowed)"
                return False, reason_en, "chest_not_to_ground", 0.35

        # --- Top: full lockout ------------------------------------------------
        if elbow_max < self.lockout_angle:
            reason_en = f"Incomplete lockout at top (elbow angle {elbow_max:.0f}°)"
            return False, reason_en, "incomplete_lockout", 0.4

        conf_depth = self._confidence_from_margin(
            elbow_min, self.bottom_threshold + 10, "below")
        conf_lock = self._confidence_from_margin(
            elbow_max, self.lockout_angle, "above")
        confidence = min(conf_depth, conf_lock) * 0.7 + 0.3
        return True, None, None, confidence
