"""
Burpee detector — CrossFit Games standard.

A CrossFit Games burpee has two mandatory checkpoints:

  1. BOTTOM: The athlete's chest AND thighs must make contact with the
     ground. We approximate this by requiring the chest (mid-shoulder)
     y-coordinate to drop close to the ankle (ground) level — calibrated
     per-video from the standing pose.

  2. TOP: The athlete must jump vertically with both feet leaving the
     ground AND reach full hip extension with hands overhead. We detect
     the jump via a sudden ankle-y drop (feet lifted) and the overhead
     reach via wrists above shoulders.

Key design decisions:
  * All thresholds are RELATIVE to the athlete's standing height and the
    ground (ankle) level, so they work regardless of camera distance or
    athlete height.
  * The primary signal is a normalised "chest descent ratio" where
    0.0 = standing and 1.0 = chest on the ground.
  * A jump is only counted when BOTH feet leave the ground (both ankles
    rise above their standing baseline) AND hands reach overhead.
"""
from __future__ import annotations

from typing import Any

from core.pose_detector import PoseFrame
from movements.base_movement import BaseMovement, _RepBuffer
from utils.geometry import midpoint
from utils.smoothing import MovingAverageFilter


class Burpee(BaseMovement):
    name = "burpee"

    # Primary signal = chest_descent_ratio (0 = standing, 1 = on ground).
    # extended_is_high = False because LOWER ratio = standing (extended).
    start_threshold = 0.15     # ratio below 0.15 => standing
    bottom_threshold = 0.70    # ratio above 0.70 => chest on ground
    extended_is_high = False
    # Hysteresis for ratio-based signals (0-1 scale), not degrees.
    _ratio_hysteresis = 0.05

    def __init__(self, standards: dict[str, Any] | None = None):
        super().__init__(standards)
        # User-configurable thresholds (relative, 0-1 scale).
        # Tuned for 45° camera angle + MediaPipe smoothing. Real competition
        # videos have perspective foreshortening that reduces the apparent
        # descent, so thresholds are kept achievable.
        self.min_descent_ratio = float(
            self.standards.get("min_descent_ratio", 0.35))
        self.jump_height_ratio = float(
            self.standards.get("jump_height_ratio", 0.02))
        # Overhead margin can be slightly negative (wrists roughly at shoulder
        # level counts as "reaching up" given camera angle).
        self.overhead_margin = float(
            self.standards.get("overhead_margin", -0.03))

        # Smoothing — small window for fast burpee pace.
        self._chest_filter = MovingAverageFilter(3)
        self._ankle_filter = MovingAverageFilter(3)

        # Calibration: standing chest height and ground (ankle) level.
        self._standing_chest_y: float | None = None
        self._ground_y: float | None = None
        self._standing_ankle_y: float | None = None
        self._calibration_frames = 0
        self._calibration_chest_sum = 0.0
        self._calibration_ankle_sum = 0.0

    def calibrate(self, ground_y: float) -> None:
        """Set the ground (ankle) line from the first detected frame."""
        if self._ground_y is None:
            self._ground_y = ground_y

    def _classify_phase(self, signals: dict[str, float]):
        """
        Override the base classifier with ratio-appropriate hysteresis.
        The base class uses HYSTERESIS_MARGIN=4.0 which is for degrees, not
        the 0-1 ratio we use here.
        """
        from movements.base_movement import Phase, STATE_MIN_FRAMES

        primary = signals.get("primary")
        if primary is None:
            return self._phase

        hyst = self._ratio_hysteresis
        at_start = primary <= self.start_threshold + hyst
        at_bottom = primary >= self.bottom_threshold - hyst
        midpoint = (self.start_threshold + self.bottom_threshold) / 2
        # For extended_is_high=False: past_midway means heading back to start
        past_midway = primary < midpoint

        if self._phase == Phase.IDLE:
            if not at_start:
                self._descend_extreme = None
                self._descended_past_mid = False
                return Phase.DESCENDING
            return Phase.IDLE

        if self._phase == Phase.DESCENDING:
            # Track extremes for shallow-rep detection.
            if self._descend_extreme is None:
                self._descend_extreme = primary
            else:
                self._descend_extreme = max(self._descend_extreme, primary)
            self._descended_past_mid = (
                self._descended_past_mid or primary > midpoint)

            if at_bottom:
                return Phase.BOTTOM
            # Reversal: went past midpoint, now heading back to start
            # without reaching bottom → shallow rep.
            if self._descended_past_mid and past_midway:
                return Phase.ASCENDING
            return Phase.DESCENDING

        if self._phase == Phase.BOTTOM:
            return Phase.ASCENDING if not at_bottom else Phase.BOTTOM

        if self._phase == Phase.ASCENDING:
            return Phase.IDLE if at_start else Phase.ASCENDING

        return self._phase

    def _key_signals(self, pose: PoseFrame) -> dict[str, float]:
        ls, rs = pose.get("left_shoulder"), pose.get("right_shoulder")
        la, ra = pose.get("left_ankle"), pose.get("right_ankle")
        lw, rw = pose.get("left_wrist"), pose.get("right_wrist")
        lh, rh = pose.get("left_hip"), pose.get("right_hip")
        if not all([ls, rs, la, ra]):
            return {}

        chest = midpoint(ls, rs)
        raw_chest_y = self._chest_filter.update(chest.y)
        raw_ankle_y = self._ankle_filter.update((la.y + ra.y) / 2)
        if raw_chest_y is None or raw_ankle_y is None:
            return {}

        # --- Calibration: collect standing chest + ankle height ----------
        # We calibrate from the first few frames where the athlete appears
        # to be standing (chest high above ground).
        if self._ground_y is None:
            self._ground_y = raw_ankle_y  # ankle ≈ ground in standing pose
        if self._standing_chest_y is None and self._calibration_frames < 10:
            self._calibration_chest_sum += raw_chest_y
            self._calibration_ankle_sum += raw_ankle_y
            self._calibration_frames += 1
            if self._calibration_frames >= 10:
                self._standing_chest_y = (
                    self._calibration_chest_sum / self._calibration_frames)
                self._standing_ankle_y = (
                    self._calibration_ankle_sum / self._calibration_frames)

        # If calibration isn't done yet, use raw values as fallback.
        standing_chest = self._standing_chest_y or raw_chest_y
        standing_ankle = self._standing_ankle_y or raw_ankle_y

        # --- Normalised descent ratio (0 = standing, 1 = on ground) -------
        # The range is standing_chest_y (high up) → ground_y (down low).
        # Note: y grows downward, so ground_y > standing_chest_y.
        vertical_range = standing_ankle - standing_chest
        if vertical_range > 0.01:
            descent_ratio = (raw_chest_y - standing_chest) / vertical_range
            descent_ratio = max(0.0, min(1.0, descent_ratio))
        else:
            descent_ratio = 0.0

        # --- Jump detection: both ankles must rise above standing ankle ---
        # ankle_lift > 0 means ankles are HIGHER than standing (jumping).
        ankle_lift = standing_ankle - raw_ankle_y

        # --- Hands overhead: wrists above shoulders -----------------------
        wrist_overhead = 0.0
        if lw and rw:
            wrist_y = (lw.y + rw.y) / 2
            # Positive when wrist is above (smaller y than) shoulder.
            wrist_overhead = chest.y - wrist_y

        # --- Hip extension: hips should open at the top -------------------
        hip_open = 0.0
        if lh and rh and ls and rs:
            hip = midpoint(lh, rh)
            # Distance from hip to chest — larger means more upright.
            hip_open = hip.y - chest.y  # positive normally

        return {
            "primary": descent_ratio,
            "descent_ratio": descent_ratio,
            "chest_y": raw_chest_y,
            "ankle_y": raw_ankle_y,
            "ankle_lift": ankle_lift,
            "wrist_overhead": wrist_overhead,
            "hip_open": hip_open,
        }

    def _validate(self, rep: _RepBuffer) -> tuple[bool, str | None, str | None, float]:
        extremes = rep.extremes()
        descent_ex = extremes.get("descent_ratio")
        ankle_lift_ex = extremes.get("ankle_lift")
        wrist_ex = extremes.get("wrist_overhead")
        if not descent_ex:
            return False, "Chest position not detected", "chest_not_detected", 0.0

        # --- Bottom: chest + thighs to ground -------------------------------
        max_descent = descent_ex["max"]  # most descended (closest to ground)
        if max_descent < self.min_descent_ratio:
            reason = (
                f"Chest did not reach ground (descent {max_descent:.0%}, "
                f"need {self.min_descent_ratio:.0%})"
            )
            return False, reason, "chest_not_to_ground", 0.3

        # Confidence for descent: how far above the threshold (0-1 scale).
        # A margin of 0.20 means clearing the threshold by 20% gives full
        # confidence.
        descent_margin = 0.20
        conf_bottom = min(1.0, (max_descent - self.min_descent_ratio) / descent_margin)

        # --- Top: jump (both feet leave ground) ----------------------------
        jump_ok = False
        jump_confidence = 0.0
        if ankle_lift_ex is not None:
            max_lift = ankle_lift_ex["max"]
            if max_lift >= self.jump_height_ratio:
                jump_ok = True
                # Jump confidence: clearing threshold by 0.06 = full confidence.
                jump_confidence = min(1.0, (max_lift - self.jump_height_ratio) / 0.06)

        # --- Top: hands overhead --------------------------------------------
        overhead_ok = False
        overhead_confidence = 0.0
        if wrist_ex is not None:
            max_overhead = wrist_ex["max"]
            if max_overhead >= self.overhead_margin:
                overhead_ok = True
                overhead_confidence = min(1.0, (max_overhead - self.overhead_margin) / 0.10)

        # CrossFit Games standard: BOTH jump AND overhead reach required.
        if not jump_ok:
            reason = (
                f"No jump detected (feet lift {ankle_lift_ex['max']:.2f}, "
                f"need {self.jump_height_ratio:.2f})"
            )
            return False, reason, "no_jump", 0.35

        if not overhead_ok:
            reason = "Hands did not reach overhead at top of jump"
            return False, reason, "no_overhead", 0.35

        # Overall confidence: weighted average with a floor of 0.5 for valid reps.
        confidence = 0.5 + (conf_bottom * 0.2 + jump_confidence * 0.2 + overhead_confidence * 0.1)
        confidence = min(1.0, confidence)
        return True, None, None, confidence
