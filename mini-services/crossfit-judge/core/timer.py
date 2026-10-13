"""
Workout timer with a time-cap. The timer runs from frame zero (video start)
to the final processed frame, so the reported time equals the full video
duration. This matches how online competition evidence videos are reviewed.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WorkoutTimer:
    time_cap_seconds: float
    started: bool = False
    start_time: float = 0.0
    end_time: float | None = None
    # The actual full duration of the source video (for accurate reporting).
    video_duration_seconds: float = 0.0

    def maybe_start(self, timestamp: float, movement_active: bool) -> None:
        """Always start at frame zero so the timer covers the whole video."""
        if not self.started:
            self.started = True
            self.start_time = 0.0

    def force_start(self, timestamp: float) -> None:
        self.started = True
        self.start_time = 0.0

    def elapsed(self, timestamp: float) -> float:
        if not self.started:
            return 0.0
        return max(0.0, timestamp - self.start_time)

    def within_cap(self, timestamp: float) -> bool:
        if not self.started:
            return True
        return self.elapsed(timestamp) <= self.time_cap_seconds

    def final_time(self) -> float | None:
        """Return the full video duration, falling back to the last elapsed."""
        if self.end_time is not None:
            return self.end_time
        return self.video_duration_seconds if self.video_duration_seconds > 0 else None

    def stop(self, timestamp: float) -> None:
        """Stop the timer, preferring the known video duration for accuracy."""
        if self.end_time is None:
            # Use the actual video duration if available — more accurate than
            # the last processed frame timestamp (which can be cut short by
            # frame sampling).
            if self.video_duration_seconds > 0:
                self.end_time = self.video_duration_seconds
            else:
                self.end_time = self.elapsed(timestamp)

    def reset(self) -> None:
        self.started = False
        self.start_time = 0.0
        self.end_time = None
