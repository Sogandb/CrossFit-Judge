"""
Workout definitions. Each workout is a JSON-serialisable dict describing the
movements, time cap, and scoring format.

Supported scoring formats:
  - "amrap"     : as many reps as possible within the time cap (score = total reps)
  - "for_time"  : finish the prescribed work as fast as possible (score = time)
  - "max_reps"  : maximum reps of a single movement within the time cap
  - "tabata"    : 20s work / 10s rest x 8 rounds (score = total reps)
  - "emom"      : every minute on the minute (score = total reps completed)
"""
from __future__ import annotations

import copy
from typing import Any

WORKOUTS: dict[str, dict[str, Any]] = {
    # ---------------------------------------------------------------- AMRAP
    "squat_amrap": {
        "name": "Air Squat",
        "format": "amrap",
        "time_cap_seconds": 60,
        "movements": [
            {
                "name": "squat",
                "reps_per_round": 1,
                "standards": {
                    "min_knee_angle": 95,
                    "full_extension_angle": 165,
                },
            }
        ],
        "scoring": "reps_completed",
        "description": "As many air squats as possible in 60 seconds.",
    },
    "pushup_amrap": {
        "name": "Push-up",
        "format": "amrap",
        "time_cap_seconds": 60,
        "movements": [
            {
                "name": "pushup",
                "reps_per_round": 1,
                "standards": {
                    "top_lockout_angle": 155,
                    "bottom_chest_distance": 0.08,
                },
            }
        ],
        "scoring": "reps_completed",
        "description": "As many push-ups as possible in 60 seconds.",
    },
    "burpee_amrap": {
        "name": "Burpee",
        "format": "amrap",
        "time_cap_seconds": 60,
        "movements": [
            {
                "name": "burpee",
                "reps_per_round": 1,
                "standards": {
                    "min_descent_ratio": 0.35,
                    "jump_height_ratio": 0.02,
                    "overhead_margin": -0.03,
                },
            }
        ],
        "scoring": "reps_completed",
        "description": "As many burpees as possible in 60 seconds.",
    },
    "thruster_amrap": {
        "name": "Thruster",
        "format": "amrap",
        "time_cap_seconds": 60,
        "movements": [
            {
                "name": "thruster",
                "reps_per_round": 1,
                "standards": {
                    "min_knee_angle": 95,
                    "full_extension_angle": 155,
                    "overhead_lockout_angle": 150,
                },
            }
        ],
        "scoring": "reps_completed",
        "description": "As many thrusters as possible in 60 seconds.",
    },
    "pullup_amrap": {
        "name": "Pull-up",
        "format": "amrap",
        "time_cap_seconds": 60,
        "movements": [
            {
                "name": "pullup",
                "reps_per_round": 1,
                "standards": {
                    "chin_above_bar_y_threshold": 0.0,
                    "bottom_lockout_angle": 150,
                },
            }
        ],
        "scoring": "reps_completed",
        "description": "As many pull-ups as possible in 60 seconds.",
    },
    "kb_swing_amrap": {
        "name": "Kettlebell Swing",
        "format": "amrap",
        "time_cap_seconds": 60,
        "movements": [
            {
                "name": "kettlebell_swing",
                "reps_per_round": 1,
                "standards": {
                    "top_angle": 150,
                    "bottom_hinge_angle": 95,
                },
            }
        ],
        "scoring": "reps_completed",
        "description": "As many kettlebell swings as possible in 60 seconds.",
    },

    # ------------------------------------------------------------ For Time
    "wod_cindy_lite": {
        "name": "Cindy Lite",
        "format": "for_time",
        "time_cap_seconds": 300,
        "movements": [
            {"name": "pullup", "reps_per_round": 5, "standards": {
                "chin_above_bar_y_threshold": 0.0, "bottom_lockout_angle": 150}},
            {"name": "pushup", "reps_per_round": 10, "standards": {
                "top_lockout_angle": 155, "bottom_chest_distance": 0.08}},
            {"name": "squat", "reps_per_round": 15, "standards": {
                "min_knee_angle": 95, "full_extension_angle": 165}},
        ],
        "scoring": "time_to_complete",
        "description": "5 pull-ups, 10 push-ups, 15 squats — as many rounds as possible in 5 min.",
    },
    "wod_open_25_1": {
        "name": "Open WOD 25.1 (Demo)",
        "format": "amrap",
        "time_cap_seconds": 120,
        "movements": [
            {"name": "burpee", "reps_per_round": 15, "standards": {
                "min_descent_ratio": 0.35, "jump_height_ratio": 0.02, "overhead_margin": -0.03}},
            {"name": "squat", "reps_per_round": 15, "standards": {
                "min_knee_angle": 95, "full_extension_angle": 165}},
        ],
        "scoring": "reps_completed",
        "description": "AMRAP 2 min: 15 burpees + 15 squats.",
    },

    # --------------------------------------------------------------- Tabata
    "tabata_squat": {
        "name": "Air Squats",
        "format": "tabata",
        "time_cap_seconds": 240,
        "movements": [
            {"name": "squat", "reps_per_round": 1, "standards": {
                "min_knee_angle": 95, "full_extension_angle": 165}},
        ],
        "scoring": "reps_completed",
        "description": "8 rounds of 20s work / 10s rest. Score = total reps.",
    },
    "tabata_pushup": {
        "name": "Push-ups",
        "format": "tabata",
        "time_cap_seconds": 240,
        "movements": [
            {"name": "pushup", "reps_per_round": 1, "standards": {
                "top_lockout_angle": 155, "bottom_chest_distance": 0.08}},
        ],
        "scoring": "reps_completed",
        "description": "8 rounds of 20s work / 10s rest. Score = total reps.",
    },
    "tabata_burpee": {
        "name": "Burpees",
        "format": "tabata",
        "time_cap_seconds": 240,
        "movements": [
            {"name": "burpee", "reps_per_round": 1, "standards": {
                "min_descent_ratio": 0.35, "jump_height_ratio": 0.02, "overhead_margin": -0.03}},
        ],
        "scoring": "reps_completed",
        "description": "8 rounds of 20s work / 10s rest. Score = total reps.",
    },

    # ---------------------------------------------------------------- EMOM
    "emom_squat_thruster": {
        "name": "Squat + Thruster",
        "format": "emom",
        "time_cap_seconds": 600,
        "movements": [
            {"name": "squat", "reps_per_round": 10, "standards": {
                "min_knee_angle": 95, "full_extension_angle": 165}},
            {"name": "thruster", "reps_per_round": 10, "standards": {
                "min_knee_angle": 95, "full_extension_angle": 155,
                "overhead_lockout_angle": 150}},
        ],
        "scoring": "reps_completed",
        "description": "Every minute on the minute for 10 min: 10 squats / 10 thrusters alternating.",
    },
    "emom_burpee_pullup": {
        "name": "Burpee + Pull-up",
        "format": "emom",
        "time_cap_seconds": 480,
        "movements": [
            {"name": "burpee", "reps_per_round": 7, "standards": {
                "min_descent_ratio": 0.35, "jump_height_ratio": 0.02, "overhead_margin": -0.03}},
            {"name": "pullup", "reps_per_round": 5, "standards": {
                "chin_above_bar_y_threshold": 0.0, "bottom_lockout_angle": 150}},
        ],
        "scoring": "reps_completed",
        "description": "Every minute on the minute for 8 min: 7 burpees / 5 pull-ups alternating.",
    },

    # -------------------------------------------------------- Max Reps
    "max_rep_squat": {
        "name": "Squats",
        "format": "max_reps",
        "time_cap_seconds": 60,
        "movements": [
            {"name": "squat", "reps_per_round": 1, "standards": {
                "min_knee_angle": 95, "full_extension_angle": 165}},
        ],
        "scoring": "reps_completed",
        "description": "Maximum air squats in 60 seconds.",
    },
    "max_rep_pushup": {
        "name": "Push-ups",
        "format": "max_reps",
        "time_cap_seconds": 60,
        "movements": [
            {"name": "pushup", "reps_per_round": 1, "standards": {
                "top_lockout_angle": 155, "bottom_chest_distance": 0.08}},
        ],
        "scoring": "reps_completed",
        "description": "Maximum push-ups in 60 seconds.",
    },
}


def get_workout(workout_id: str) -> dict[str, Any]:
    """Return a copy of the workout definition by id."""
    if workout_id not in WORKOUTS:
        raise KeyError(f"Unknown workout: {workout_id}")
    return copy.deepcopy(WORKOUTS[workout_id])


def list_workouts() -> list[dict[str, Any]]:
    """Return a lightweight list of available workouts for the frontend."""
    return [
        {"id": wid, "name": w["name"], "format": w["format"],
         "time_cap_seconds": w["time_cap_seconds"],
         "description": w.get("description", ""),
         "movements": [m["name"] for m in w.get("movements", [])]}
        for wid, w in WORKOUTS.items()
    ]


def make_custom_workout(name: str, format: str, time_cap_seconds: int,
                        movement_names: list[str]) -> dict[str, Any]:
    """
    Build a workout definition from user-supplied parameters (for the custom
    upload flow). Returns a workout dict ready for the analyzer.
    """
    # Default standards per movement — can be refined later.
    DEFAULT_STANDARDS = {
        "squat": {"min_knee_angle": 95, "full_extension_angle": 165},
        "pushup": {"top_lockout_angle": 155, "bottom_chest_distance": 0.08},
        "burpee": {"min_descent_ratio": 0.35, "jump_height_ratio": 0.02, "overhead_margin": -0.03},
        "thruster": {"min_knee_angle": 95, "full_extension_angle": 155,
                      "overhead_lockout_angle": 150},
        "pullup": {"chin_above_bar_y_threshold": 0.0, "bottom_lockout_angle": 150},
        "kettlebell_swing": {"top_angle": 150, "bottom_hinge_angle": 95},
    }
    movements = []
    for mname in movement_names:
        movements.append({
            "name": mname,
            "reps_per_round": 1,
            "standards": DEFAULT_STANDARDS.get(mname, {}),
        })
    return {
        "name": name,
        "format": format,
        "time_cap_seconds": time_cap_seconds,
        "movements": movements,
        "scoring": "reps_completed" if format != "for_time" else "time_to_complete",
        "description": f"Custom workout: {', '.join(movement_names)}",
    }
