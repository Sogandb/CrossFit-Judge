"""
Air Squat detector.

State machine driven by the knee angle (hip-knee-ankle), averaged across
both legs. At a 45-degree camera angle the projected knee angle runs a few
degrees lower than a pure side view, so thresholds are tuned accordingly.

Standards (CrossFit Games):
  * Bottom: hip crease below the top of the knee  (knee angle <= ~95)
  * Top:    full hip & knee extension             (knee angle >= ~170)
"""
from __future__ import annotations

from typing import Any

from core.pose_detector import PoseFrame
from movements.base_movement import BaseMovement, Phase, _RepBuffer
from utils.geometry import angle_2d
from utils.smoothing import AngleSmoother


class Squat(BaseMovement):
    name = "squat"
    start_threshold = 165.0
    bottom_threshold = 100.0
    extended_is_high = True

    def __init__(self, standards: dict[str, Any] | None = None):
        super().__init__(standards)
        # User-configurable standard thresholds.
        self.min_knee_angle = float(self.standards.get("min_knee_angle", 95))
        self.full_ext_angle = float(self.standards.get("full_extension_angle", 165))
        self._knee_smoother = AngleSmoother(window=5)

    def _key_signals(self, pose: PoseFrame) -> dict[str, float]:
        lh, rh = pose.get("left_hip"), pose.get("right_hip")
        lk, rk = pose.get("left_knee"), pose.get("right_knee")
        la, ra = pose.get("left_ankle"), pose.get("right_ankle")
        if not all([lh, rh, lk, rk, la, ra]):
            return {}

        left = angle_2d(lh, lk, la)
        right = angle_2d(rh, rk, ra)
        raw_knee = (left + right) / 2
        knee = self._knee_smoother.update(raw_knee)
        if knee is None:
            return {}

        # Hip angle (shoulder-hip-knee) tracks whether the hip is fully open
        # at the top - a secondary standard.
        ls, rs = pose.get("left_shoulder"), pose.get("right_shoulder")
        hip_angle = None
        if ls and rs and lh and rh and lk and rk:
            ha_l = angle_2d(ls, lh, lk)
            ha_r = angle_2d(rs, rh, rk)
            hip_angle = (ha_l + ha_r) / 2

        return {"primary": knee, "knee": knee, "hip": hip_angle or 0.0}

    def _validate(self, rep: _RepBuffer) -> tuple[bool, str | None, str | None, float]:
        extremes = rep.extremes()
        knee_ex = extremes.get("knee")
        if not knee_ex:
            return False, "Knee angle not detected", "knee_not_detected", 0.0

        knee_min = knee_ex["min"]      # most bent (bottom of squat)
        knee_max = knee_ex["max"]      # most extended (top)
        confidences = []

        # --- Bottom standard: hip crease below knee -------------------------
        if knee_min > self.min_knee_angle:
            reason_en = f"Insufficient depth (knee angle {knee_min:.0f}° above allowed {self.min_knee_angle:.0f}°)"
            return False, reason_en, "insufficient_depth", 0.3

        confidences.append(self._confidence_from_margin(
            knee_min, self.min_knee_angle, "below"))

        # --- Top standard: full extension ------------------------------------
        if knee_max < self.full_ext_angle:
            reason_en = f"Incomplete extension at top (knee angle {knee_max:.0f}° below {self.full_ext_angle:.0f}°)"
            return False, reason_en, "incomplete_extension", 0.4

        confidences.append(self._confidence_from_margin(
            knee_max, self.full_ext_angle, "above"))

        confidence = min(confidences) * 0.7 + 0.3   # floor at 0.3
        return True, None, None, confidence
