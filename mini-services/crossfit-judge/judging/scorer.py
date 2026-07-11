"""
Scoring engine — implements CrossFit Games scoring standards for each
workout format.

  AMRAP     : Score = total valid reps completed within the time cap.
              More reps = better. (e.g., 47 reps)
  For Time  : Score = time to complete all prescribed work.
              If completed within cap: time in seconds (lower = better).
              If NOT completed (DNF): score = total reps completed, and
              ranked below all finishers.
  Tabata    : 8 rounds of 20s work / 10s rest. Score = total reps.
  EMOM      : Every Minute On the Minute. Score = total reps completed.
  Max Reps  : Single movement, max reps in time cap. Score = total reps.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from movements.base_movement import RepEvent


@dataclass
class ScoreBreakdown:
    format: str
    total_reps: int
    valid_reps: int
    no_reps: int
    score: float
    score_label: str
    score_display: str           # human-readable score (e.g., "8:32" or "47 reps")
    time_seconds: float | None = None
    completed: bool = False      # did the athlete finish all prescribed work?
    rounds_completed: int = 0    # for AMRAP/For Time
    per_movement: dict[str, dict[str, int]] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": self.format,
            "total_reps": self.total_reps,
            "valid_reps": self.valid_reps,
            "no_reps": self.no_reps,
            "score": self.score,
            "score_label": self.score_label,
            "score_display": self.score_display,
            "time_seconds": round(self.time_seconds, 2) if self.time_seconds else None,
            "completed": self.completed,
            "rounds_completed": self.rounds_completed,
            "per_movement": self.per_movement,
            "extra": self.extra,
        }


class Scorer:
    def __init__(self, workout: dict[str, Any]):
        self.workout = workout
        self.format: str = workout.get("format", "amrap")
        self.time_cap: float = float(workout.get("time_cap_seconds", 0))
        self.movements: list[dict] = workout.get("movements", [])

    def _total_prescribed_reps(self) -> int:
        """Total reps per round = sum of reps_per_round for all movements."""
        return sum(m.get("reps_per_round", 1) for m in self.movements)

    def _format_time(self, seconds: float) -> str:
        """Format seconds as m:ss or mm:ss."""
        m = int(seconds // 60)
        s = int(seconds % 60)
        return f"{m}:{s:02d}"

    def score(self, events: list[RepEvent],
              timer_started: bool, final_time: float | None,
              sequence=None) -> ScoreBreakdown:
        total = len(events)
        valid = [e for e in events if e.valid]
        no_reps = total - len(valid)

        per_movement: dict[str, dict[str, int]] = {}
        for e in events:
            m = per_movement.setdefault(e.movement, {"total": 0, "valid": 0, "no_rep": 0})
            m["total"] += 1
            if e.valid:
                m["valid"] += 1
            else:
                m["no_rep"] += 1

        rounds_completed = sequence.rounds_completed if sequence else 0
        time_s = final_time

        if self.format == "for_time":
            # CrossFit Games For Time:
            # - If athlete completes ALL prescribed reps within cap:
            #   score = time (lower = better)
            # - If not finished (DNF): score = reps completed (ranked below)
            prescribed_total = self._total_prescribed_reps()
            # For Time typically has 1 round (fixed work). If rounds > 1,
            # the prescribed total is rounds * per-round reps.
            # We check if valid reps >= prescribed_total for 1 round.
            finished = len(valid) >= prescribed_total and len(valid) > 0

            if finished:
                score = time_s if time_s else 0.0
                score_label = "time"
                score_display = self._format_time(score)
                completed = True
            else:
                # DNF — score by reps completed
                score = float(len(valid))
                score_label = "reps (DNF)"
                score_display = f"{int(score)} reps (DNF)"
                completed = False

        elif self.format == "amrap":
            # AMRAP: score = total valid reps. More = better.
            score = float(len(valid))
            score_label = "reps"
            score_display = f"{int(score)} reps"
            completed = False  # AMRAP never "completes"

        elif self.format == "tabata":
            # Tabata: 8 rounds × 20s work. Score = total reps.
            score = float(len(valid))
            score_label = "reps"
            score_display = f"{int(score)} reps"
            completed = False

        elif self.format == "emom":
            # EMOM: score = total reps completed.
            score = float(len(valid))
            score_label = "reps"
            score_display = f"{int(score)} reps"
            completed = False

        elif self.format == "max_reps":
            # Max Reps: score = total valid reps.
            score = float(len(valid))
            score_label = "reps"
            score_display = f"{int(score)} reps"
            completed = False

        else:
            score = float(len(valid))
            score_label = "reps"
            score_display = f"{int(score)} reps"
            completed = False

        return ScoreBreakdown(
            format=self.format,
            total_reps=total,
            valid_reps=len(valid),
            no_reps=no_reps,
            score=score,
            score_label=score_label,
            score_display=score_display,
            time_seconds=time_s,
            completed=completed,
            rounds_completed=rounds_completed,
            per_movement=per_movement,
            extra={"time_cap_seconds": self.time_cap,
                   "timer_started": timer_started},
        )
