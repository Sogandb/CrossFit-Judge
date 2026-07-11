"""
Movement sequencer — tracks which movement should be active based on the
workout's rep scheme. This prevents cross-detection (e.g., a burpee
triggering the squat detector).

For a workout like "15 burpees + 15 squats AMRAP":
  - Start with burpees, count until 15 valid reps
  - Switch to squats, count until 15 valid reps
  - Switch back to burpees (new round)
  - Continue until time cap

For single-movement workouts, always returns that movement (no switching).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MovementSequence:
    """Tracks the current movement in a workout's rep scheme."""
    movements: list[dict[str, Any]]
    current_index: int = 0
    current_round: int = 1
    reps_in_current_movement: int = 0
    total_reps_completed: int = 0
    # Track per-movement and per-round stats
    movement_reps: dict[str, int] = field(default_factory=dict)
    rounds_completed: int = 0

    def __post_init__(self):
        for m in self.movements:
            name = m["name"]
            if name not in self.movement_reps:
                self.movement_reps[name] = 0

    @property
    def current_movement(self) -> dict[str, Any]:
        return self.movements[self.current_index]

    @property
    def current_movement_name(self) -> str:
        return self.current_movement["name"]

    @property
    def current_reps_target(self) -> int:
        return self.current_movement.get("reps_per_round", 1)

    @property
    def is_single_movement(self) -> bool:
        return len(self.movements) <= 1

    def record_rep(self, valid: bool) -> None:
        """Record a rep for the current movement. If we've hit the target,
        advance to the next movement (or next round)."""
        if not valid:
            return

        self.reps_in_current_movement += 1
        self.total_reps_completed += 1
        self.movement_reps[self.current_movement_name] += 1

        # Check if we've completed the target reps for this movement.
        if self.reps_in_current_movement >= self.current_reps_target:
            self._advance()

    def _advance(self) -> None:
        """Move to the next movement, or wrap to the next round."""
        self.current_index += 1
        self.reps_in_current_movement = 0

        if self.current_index >= len(self.movements):
            # Completed a full round.
            self.current_index = 0
            self.current_round += 1
            self.rounds_completed += 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_movement": self.current_movement_name,
            "current_index": self.current_index,
            "current_round": self.current_round,
            "reps_in_current_movement": self.reps_in_current_movement,
            "current_reps_target": self.current_reps_target,
            "total_reps_completed": self.total_reps_completed,
            "rounds_completed": self.rounds_completed,
            "movement_reps": dict(self.movement_reps),
        }
