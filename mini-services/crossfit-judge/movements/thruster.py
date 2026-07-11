"""
Thruster detector (front squat + overhead press).

A thruster combines a deep squat with an overhead press. The state machine is
squat-driven (knee angle) but the top standard additionally requires full
overhead lockout of the arms.

Standards (CrossFit Games):
  * Bottom: hip crease below the knee (deep squat)
  * Top:    full hip/knee extension AND full overhead lockout (elbow straight,
            bar/dumbbell over the head)
"""
from __future__ import annotations

from typing import Any

from core.pose_detector import PoseFrame
from movements.base_movement import BaseMovement, _RepBuffer
from utils.geometry import angle_2d
from utils.smoothing import AngleSmoother


class Thruster(BaseMovement):
    name = "thruster"
    start_threshold = 160.0
    bottom_threshold = 105.0
    extended_is_high = True

    def __init__(self, standards: dict[str, Any] | None = None):
        super().__init__(standards)
        self.min_knee_angle = float(self.standards.get("min_knee_angle", 100))
        self.full_ext_angle = float(self.standards.get("full_extension_angle", 155))
        self.overhead_lockout = float(self.standards.get("overhead_lockout_angle", 150))
        self._knee_smoother = AngleSmoother(5)
        self._elbow_smoother = AngleSmoother(5)

    def _key_signals(self, pose: PoseFrame) -> dict[str, float]:
        lh, rh = pose.get("left_hip"), pose.get("right_hip")
        lk, rk = pose.get("left_knee"), pose.get("right_knee")
        la, ra = pose.get("left_ankle"), pose.get("right_ankle")
        ls, rs = pose.get("left_shoulder"), pose.get("right_shoulder")
        le, re = pose.get("left_elbow"), pose.get("right_elbow")
        lw, rw = pose.get("left_wrist"), pose.get("right_wrist")
        if not all([lh, rh, lk, rk, la, ra]):
            return {}

        left = angle_2d(lh, lk, la)
        right = angle_2d(rh, rk, ra)
        knee = self._knee_smoother.update((left + right) / 2) or 0.0

        elbow = 0.0
        if all([ls, rs, le, re, lw, rw]):
            el = angle_2d(ls, le, lw)
            er = angle_2d(rs, re, rw)
            elbow = self._elbow_smoother.update((el + er) / 2) or 0.0

        # Vertical offset of wrist vs shoulder (positive when wrist overhead).
        wrist_overhead = 0.0
        if lw and rw and ls and rs:
            wrist_y = (lw.y + rw.y) / 2
            shoulder_y = (ls.y + rs.y) / 2
            wrist_overhead = shoulder_y - wrist_y

        return {"primary": knee, "knee": knee, "elbow": elbow,
                "wrist_overhead": wrist_overhead}

    def _validate(self, rep: _RepBuffer) -> tuple[bool, str | None, str | None, float]:
        extremes = rep.extremes()
        knee_ex = extremes.get("knee")
        elbow_ex = extremes.get("elbow")
        wrist_ex = extremes.get("wrist_overhead")
        if not knee_ex:
            return False, "Knee angle not detected", "knee_not_detected", 0.0

        knee_min = knee_ex["min"]
        knee_max = knee_ex["max"]

        # --- Bottom: deep squat ----------------------------------------------
        if knee_min > self.min_knee_angle:
            reason_en = f"Insufficient squat depth (knee angle {knee_min:.0f}°)"
            return False, reason_en, "insufficient_depth", 0.3

        # --- Top: knee extension ---------------------------------------------
        if knee_max < self.full_ext_angle:
            reason_en = f"Incomplete knee extension at top ({knee_max:.0f}°)"
            return False, reason_en, "incomplete_knee_extension", 0.35

        # --- Top: overhead lockout -------------------------------------------
        if elbow_ex is not None:
            elbow_max = elbow_ex["max"]
            if elbow_max < self.overhead_lockout:
                reason_en = f"Incomplete overhead lockout (elbow angle {elbow_max:.0f}°)"
                return False, reason_en, "incomplete_overhead_lockout", 0.35
        if wrist_ex is not None and wrist_ex["max"] <= 0.0:
            reason_en = "Weight not pressed overhead"
            return False, reason_en, "not_overhead", 0.3

        conf_depth = self._confidence_from_margin(knee_min, self.min_knee_angle, "below")
        conf_lock = self._confidence_from_margin(knee_max, self.full_ext_angle, "above")
        confidence = min(conf_depth, conf_lock) * 0.6 + 0.4
        return True, None, None, confidence
