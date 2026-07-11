"""
Base classes for movement detection.

Every CrossFit movement is modelled as a finite state machine with four
phases:

    IDLE -> DESCENDING -> BOTTOM -> ASCENDING -> (back to IDLE = 1 rep)

A rep is only counted when the full cycle completes AND every standard check
passes at the relevant phase. Otherwise a no-rep is emitted with a Persian
reason string (the judging committee's working language) plus an English key.

Subclasses implement three methods:
  * `_key_signals(pose)`        - extract the angles/distances that matter
  * `_classify_phase(signals)`  - decide which phase we are in
  * `_validate(rep)`            - run the movement-specific standard checks
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from config.settings import HYSTERESIS_MARGIN, STATE_MIN_FRAMES
from core.pose_detector import PoseFrame


class Phase(str, Enum):
    IDLE = "idle"
    DESCENDING = "descending"
    BOTTOM = "bottom"
    ASCENDING = "ascending"


@dataclass
class RepEvent:
    """A completed rep attempt (valid or no-rep)."""
    rep_number: int
    movement: str
    start_time: float
    end_time: float
    valid: bool
    confidence: float                       # 0.0 - 1.0
    no_rep_reason_fa: str | None = None     # Persian reason
    no_rep_reason_en: str | None = None     # English key
    peak_signals: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rep_number": self.rep_number,
            "movement": self.movement,
            "start_time": round(self.start_time, 2),
            "end_time": round(self.end_time, 2),
            "duration": round(self.end_time - self.start_time, 2),
            "valid": self.valid,
            "confidence": round(self.confidence, 3),
            "no_rep_reason_fa": self.no_rep_reason_fa,
            "no_rep_reason_en": self.no_rep_reason_en,
            "peak_signals": {k: round(v, 1) for k, v in self.peak_signals.items()},
        }


@dataclass
class _RepBuffer:
    """Accumulates signals across the frames of one rep attempt."""
    start_time: float = 0.0
    frames: list[PoseFrame] = field(default_factory=list)
    signals: list[dict[str, float]] = field(default_factory=list)
    timestamps: list[float] = field(default_factory=list)
    peak: dict[str, float] = field(default_factory=dict)  # extremes per signal

    def push(self, pose: PoseFrame, signals: dict[str, float]) -> None:
        self.frames.append(pose)
        self.signals.append(signals)
        self.timestamps.append(pose.timestamp)
        for k, v in signals.items():
            if v is None:
                continue
            if k not in self.peak:
                self.peak[k] = v
            else:
                # track both min and max so subclasses can pick
                self.peak[k] = v  # latest; extremes computed at validate time

    def extremes(self) -> dict[str, dict[str, float]]:
        """Return {signal: {min, max, mean}} over the rep."""
        out: dict[str, dict[str, float]] = {}
        if not self.signals:
            return out
        keys = self.signals[0].keys()
        for k in keys:
            vals = [s[k] for s in self.signals if s.get(k) is not None]
            if not vals:
                continue
            out[k] = {"min": min(vals), "max": max(vals),
                      "mean": sum(vals) / len(vals)}
        return out


class BaseMovement:
    """
    Abstract base. Subclasses set ``name``, ``start_threshold``,
    ``bottom_threshold`` and implement the three hook methods.
    """

    name: str = "base"

    # Thresholds are set by subclasses. ``start_threshold`` is the angle/value
    # that marks the standing/extended position; ``bottom_threshold`` marks the
    # compressed/bottom position. Whether "higher is extended" depends on the
    # movement and is encoded in ``extended_is_high``.
    start_threshold: float = 160.0
    bottom_threshold: float = 100.0
    extended_is_high: bool = True   # True: larger signal value = extended

    def __init__(self, standards: dict[str, Any] | None = None):
        self.standards = standards or {}
        self._phase = Phase.IDLE
        self._desired_phase: Phase = Phase.IDLE
        self._desired_hold = 0    # consecutive frames wanting _desired_phase
        self._buffer = _RepBuffer()
        self._rep_count = 0
        self._events: list[RepEvent] = []
        self._last_signals: dict[str, float] = {}
        # Track the most extreme primary value seen during the current
        # DESCENDING phase, so we can detect a reversal (shallow rep) even if
        # the formal bottom threshold was never crossed.
        self._descend_extreme: float | None = None
        self._descended_past_mid: bool = False

    # ------------------------------------------------------------------ hooks
    def _key_signals(self, pose: PoseFrame) -> dict[str, float]:
        """Extract named signals (angles, distances) from a pose frame."""
        raise NotImplementedError

    def _classify_phase(self, signals: dict[str, float]) -> Phase:
        """
        Decide the phase from the current signals. Default implementation
        uses a single ``primary`` signal vs the start/bottom thresholds with
        hysteresis. Subclasses may override for multi-signal logic.

        If the athlete reverses direction without reaching the bottom (a
        shallow rep), we transition DESCENDING -> ASCENDING so the attempt is
        still finalised and flagged as a no-rep by ``_validate``.
        """
        primary = signals.get("primary")
        if primary is None:
            return self._phase

        if self.extended_is_high:
            at_start = primary >= self.start_threshold - HYSTERESIS_MARGIN
            at_bottom = primary <= self.bottom_threshold + HYSTERESIS_MARGIN
            midpoint = (self.start_threshold + self.bottom_threshold) / 2
            past_midway = primary > midpoint   # signal heading back to start
        else:
            at_start = primary <= self.start_threshold + HYSTERESIS_MARGIN
            at_bottom = primary >= self.bottom_threshold - HYSTERESIS_MARGIN
            midpoint = (self.start_threshold + self.bottom_threshold) / 2
            past_midway = primary < midpoint

        if self._phase == Phase.IDLE:
            if not at_start:
                self._descend_extreme = None
                self._descended_past_mid = False
                return Phase.DESCENDING
            return Phase.IDLE
        if self._phase == Phase.DESCENDING:
            # Track the extreme and whether we've passed the midpoint.
            if self._descend_extreme is None:
                self._descend_extreme = primary
            else:
                if self.extended_is_high:
                    self._descend_extreme = min(self._descend_extreme, primary)
                else:
                    self._descend_extreme = max(self._descend_extreme, primary)
            if self.extended_is_high:
                self._descended_past_mid = self._descended_past_mid or (primary < midpoint)
            else:
                self._descended_past_mid = self._descended_past_mid or (primary > midpoint)

            if at_bottom:
                return Phase.BOTTOM
            # Reversal: signal went past midpoint and is now heading back to
            # start without ever reaching bottom -> shallow rep.
            if self._descended_past_mid and past_midway:
                return Phase.ASCENDING
            return Phase.DESCENDING
        if self._phase == Phase.BOTTOM:
            return Phase.ASCENDING if not at_bottom else Phase.BOTTOM
        if self._phase == Phase.ASCENDING:
            return Phase.IDLE if at_start else Phase.ASCENDING
        return self._phase

    def _validate(self, rep: _RepBuffer) -> tuple[bool, str | None, str | None, float]:
        """
        Return (valid, reason_fa, reason_en, confidence).
        Subclasses must implement movement-specific standard checks.
        """
        raise NotImplementedError

    # ------------------------------------------------------------------ public
    def update(self, pose: PoseFrame) -> RepEvent | None:
        """
        Feed one pose frame. Returns a RepEvent if a rep just completed,
        otherwise None.
        """
        signals = self._key_signals(pose)
        self._last_signals = signals
        if not signals or not pose.person_detected:
            return None

        self._buffer.push(pose, signals)

        target = self._classify_phase(signals)

        # Count consecutive frames that want the same target phase.
        if target == self._desired_phase:
            self._desired_hold += 1
        else:
            self._desired_phase = target
            self._desired_hold = 1

        # Commit a transition once the target has been stable long enough.
        if target != self._phase and self._desired_hold >= STATE_MIN_FRAMES:
            old = self._phase
            self._phase = target
            self._desired_hold = 0

            # IDLE <- ASCENDING means a full cycle just completed.
            if old == Phase.ASCENDING and self._phase == Phase.IDLE:
                return self._finalize_rep()

        return None

    def _finalize_rep(self) -> RepEvent:
        self._rep_count += 1
        valid, reason_fa, reason_en, confidence = self._validate(self._buffer)
        extremes = self._buffer.extremes()
        peak_signals: dict[str, float] = {}
        primary_key = "primary"
        if primary_key in extremes:
            peak_signals["primary_min"] = extremes[primary_key]["min"]
            peak_signals["primary_max"] = extremes[primary_key]["max"]
        peak_signals.update(
            {k: v["min"] for k, v in extremes.items() if k != primary_key}
        )
        event = RepEvent(
            rep_number=self._rep_count,
            movement=self.name,
            start_time=self._buffer.start_time or self._buffer.timestamps[0],
            end_time=self._buffer.timestamps[-1],
            valid=valid,
            confidence=confidence,
            no_rep_reason_fa=reason_fa,
            no_rep_reason_en=reason_en,
            peak_signals=peak_signals,
        )
        self._events.append(event)
        self._buffer = _RepBuffer()
        return event

    # ------------------------------------------------------------------ helpers
    def _confidence_from_margin(self, value: float, threshold: float,
                                direction: str = "above") -> float:
        """
        Map how far ``value`` clears ``threshold`` to a 0-1 confidence.
        ``direction`` is "above" (good when value >= threshold) or "below".
        """
        margin = 25.0  # degrees of clearance -> confidence 1.0
        if direction == "above":
            score = (value - threshold) / margin
        else:
            score = (threshold - value) / margin
        return max(0.0, min(1.0, score))

    @property
    def events(self) -> list[RepEvent]:
        return list(self._events)

    @property
    def rep_count(self) -> int:
        return self._rep_count

    @property
    def valid_rep_count(self) -> int:
        return sum(1 for e in self._events if e.valid)

    @property
    def phase(self) -> Phase:
        return self._phase
