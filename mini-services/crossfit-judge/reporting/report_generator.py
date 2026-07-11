"""
Assembles the final JSON report combining score, per-rep events, timing and
metadata. This is the canonical result consumed by the frontend.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from movements.base_movement import RepEvent
from judging.scorer import ScoreBreakdown


def build_report(workout: dict[str, Any], video_name: str,
                 video_duration: float, events: list[RepEvent],
                 score: ScoreBreakdown, annotated_video: str | None,
                 timeline_image: str | None) -> dict[str, Any]:
    no_rep_events = [e for e in events if not e.valid]
    avg_confidence = (
        sum(e.confidence for e in events) / len(events) if events else 0.0
    )
    return {
        "workout": {
            "id": workout.get("id", ""),
            "name": workout["name"],
            "format": workout["format"],
            "time_cap_seconds": workout["time_cap_seconds"],
            "description": workout.get("description", ""),
        },
        "video": {
            "name": video_name,
            "duration_seconds": round(video_duration, 2),
        },
        "score": score.to_dict(),
        "reps": [e.to_dict() for e in events],
        "no_reps": [e.to_dict() for e in no_rep_events],
        "summary": {
            "total_reps": len(events),
            "valid_reps": len([e for e in events if e.valid]),
            "no_rep_count": len(no_rep_events),
            "avg_confidence": round(avg_confidence, 3),
        },
        "assets": {
            "annotated_video": annotated_video,
            "timeline_image": timeline_image,
        },
    }
