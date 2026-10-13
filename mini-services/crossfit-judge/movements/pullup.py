"""
Pull-up detector.

The pull-up cycle starts at a dead hang (arms extended) and finishes back at
the dead hang. The "bottom" of the rep cycle is the TOP of the pull-up, where
the chin clears the bar.

Because the bar itself is rarely a tracked landmark, we estimate the bar line
from the wrist y-coordinate (the wrists grip the bar and stay roughly fixed).
The chin is approximated by the nose landmark.

Standards (CrossFit Games):
  * Top:    chin above the bar (nose y <= wrist y)
  * Bottom: full extension, arms straight (elbow angle >= ~160)
"""
from __future__ import annotations

from typing import Any

from core.pose_detector import PoseFrame
from movements.base_movement import BaseMovement, _RepBuffer
from utils.geometry import angle_2d
from utils.smoothing import AngleSmoother, MovingAverageFilter


class Pullup(BaseMovement):
    name = "pullup"
    start_threshold = 155.0    # dead hang (arms straight)
    bottom_threshold = 90.0    # chin at bar (arms bent)
    extended_is_high = True

    def __init__(self, standards: dict[str, Any] | None = None):
        super().__init__(standards)
        self.lockout_angle = float(self.standards.get("bottom_lockout_angle", 150))
        self.chin_margin = float(self.standards.get("chin_above_bar_y_threshold", 0.0))
        self._elbow_smoother = AngleSmoother(5)
        self._wrist_filter = MovingAverageFilter(7)
        self._nose_filter = MovingAverageFilter(5)
        self._bar_y: float | None = None

    def _key_signals(self, pose: PoseFrame) -> dict[str, float]:
        ls, rs = pose.get("left_shoulder"), pose.get("right_shoulder")
        le, re = pose.get("left_elbow"), pose.get("right_elbow")
        lw, rw = pose.get("left_wrist"), pose.get("right_wrist")
        nose = pose.get("nose")
        if not all([ls, rs, le, re, lw, rw, nose]):
            return {}

        el = angle_2d(ls, le, lw)
        er = angle_2d(rs, re, rw)
        elbow = self._elbow_smoother.update((el + er) / 2) or 0.0

        wrist_y = self._wrist_filter.update((lw.y + rw.y) / 2)
        nose_y = self._nose_filter.update(nose.y)
        # Use the minimum wrist y across the video as the bar line (wrists
        # stay at the bar; jitter can only push them lower).
        if self._bar_y is None or wrist_y < self._bar_y:
            self._bar_y = wrist_y

        # chin_above_bar: positive when nose is above (smaller y than) the bar.
        chin_above_bar = (self._bar_y - nose_y) if self._bar_y is not None else 0.0

        return {"primary": elbow, "elbow": elbow,
                "chin_above_bar": chin_above_bar, "wrist_y": wrist_y}

    def _validate(self, rep: _RepBuffer) -> tuple[bool, str | None, str | None, float]:
        extremes = rep.extremes()
        elbow_ex = extremes.get("elbow")
        chin_ex = extremes.get("chin_above_bar")
        if not elbow_ex:
            return False, "Elbow angle not detected", "elbow_not_detected", 0.0

        elbow_min = elbow_ex["min"]   # most bent (chin at bar)
        elbow_max = elbow_ex["max"]   # most extended (dead hang)

        # --- Top: chin above the bar -----------------------------------------
        if chin_ex is None or chin_ex["max"] < self.chin_margin:
            reason_en = "Chin did not clear the bar"
            return False, reason_en, "chin_below_bar", 0.3

        # --- Bottom: full extension (dead hang) ------------------------------
        if elbow_max < self.lockout_angle:
            reason_en = f"Incomplete extension at bottom (elbow angle {elbow_max:.0f}°)"
            return False, reason_en, "incomplete_extension", 0.35

        conf_chin = self._confidence_from_margin(
            chin_ex["max"], self.chin_margin + 0.02, "above")
        conf_hang = self._confidence_from_margin(
            elbow_max, self.lockout_angle, "above")
        confidence = min(conf_chin, conf_hang) * 0.6 + 0.4
        return True, None, None, confidence
