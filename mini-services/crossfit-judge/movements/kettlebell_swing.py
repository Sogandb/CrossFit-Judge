"""
Kettlebell swing detector.

The cycle is top -> down -> between-legs -> up -> top, and a rep is counted
when the bell returns to the top with full hip and knee extension. The
primary signal is the wrist y-coordinate (which tracks the bell height). The
hip angle (shoulder-hip-knee) is used to verify the hinge at the bottom and
full extension at the top.

Defaults to the Russian standard (bell to eye/chest height); set
``top_angle`` higher for American (overhead).

Standards (CrossFit Games):
  * Bottom: clear hip hinge
  * Top:    bell reaches target height + full hip & knee extension
"""
from __future__ import annotations

from typing import Any

from core.pose_detector import PoseFrame
from movements.base_movement import BaseMovement, _RepBuffer
from utils.geometry import angle_2d
from utils.smoothing import AngleSmoother, MovingAverageFilter


class KettlebellSwing(BaseMovement):
    name = "kettlebell_swing"
    # primary = wrist_y, smaller y = bell up (extended)
    start_threshold = 0.35
    bottom_threshold = 0.50
    extended_is_high = False

    def __init__(self, standards: dict[str, Any] | None = None):
        super().__init__(standards)
        self.top_angle = float(self.standards.get("top_angle", 150))  # hip ext at top
        self.bottom_hinge = float(self.standards.get("bottom_hinge_angle", 95))
        self._wrist_filter = MovingAverageFilter(5)
        self._hip_smoother = AngleSmoother(5)
        self._knee_smoother = AngleSmoother(5)

    def _key_signals(self, pose: PoseFrame) -> dict[str, float]:
        lw, rw = pose.get("left_wrist"), pose.get("right_wrist")
        ls, rs = pose.get("left_shoulder"), pose.get("right_shoulder")
        lh, rh = pose.get("left_hip"), pose.get("right_hip")
        lk, rk = pose.get("left_knee"), pose.get("right_knee")
        la, ra = pose.get("left_ankle"), pose.get("right_ankle")
        if not all([lw, rw, ls, rs, lh, rh, lk, rk, la, ra]):
            return {}

        wrist_y = self._wrist_filter.update((lw.y + rw.y) / 2)
        hip = self._hip_smoother.update(
            (angle_2d(ls, lh, lk) + angle_2d(rs, rh, rk)) / 2) or 0.0
        knee = self._knee_smoother.update(
            (angle_2d(lh, lk, la) + angle_2d(rh, rk, ra)) / 2) or 0.0

        return {"primary": wrist_y, "wrist_y": wrist_y,
                "hip": hip, "knee": knee}

    def _validate(self, rep: _RepBuffer) -> tuple[bool, str | None, str | None, float]:
        extremes = rep.extremes()
        wrist_ex = extremes.get("wrist_y")
        hip_ex = extremes.get("hip")
        if not wrist_ex:
            return False, "Bell position not detected", "bell_not_detected", 0.0

        wrist_min_y = wrist_ex["min"]  # highest bell point (top of swing)

        # --- Top: bell reaches target height ---------------------------------
        if wrist_min_y > self.start_threshold + 0.05:
            reason_en = f"Bell did not reach target height (wrist height {wrist_min_y:.2f})"
            return False, reason_en, "insufficient_height", 0.3

        # --- Bottom: hip hinge -----------------------------------------------
        if hip_ex is not None:
            hip_min = hip_ex["min"]
            if hip_min > self.bottom_hinge + 15:
                reason_en = f"Insufficient hip hinge (hip angle {hip_min:.0f}°)"
                return False, reason_en, "insufficient_hinge", 0.35

        # --- Top: full hip extension -----------------------------------------
        if hip_ex is not None:
            hip_max = hip_ex["max"]
            if hip_max < self.top_angle:
                reason_en = f"Incomplete hip extension at top (hip angle {hip_max:.0f}°)"
                return False, reason_en, "incomplete_hip_extension", 0.35

        conf_top = self._confidence_from_margin(
            self.start_threshold + 0.05, wrist_min_y, "above")
        conf_hip = self._confidence_from_margin(
            hip_ex["max"], self.top_angle, "above") if hip_ex else 0.5
        confidence = min(conf_top, conf_hip) * 0.6 + 0.4
        return True, None, None, confidence
