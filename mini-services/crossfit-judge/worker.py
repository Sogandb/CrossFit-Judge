"""
Analysis worker — runs in a separate subprocess so that MediaPipe segfaults
don't crash the main FastAPI server.

Usage:
    python3 worker.py <job_id> <video_path> <workout_json_path>

The worker writes its progress and final result to:
    data/results/<job_id>/report.json   (final report on success)
    data/results/<job_id>/progress.json (progress updates during processing)

If the worker crashes (segfault), the parent process detects the non-zero
exit code and marks the job as failed.
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path

# Add the service directory to the path.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config.settings import RESULTS_DIR
from core.analyzer import WorkoutAnalyzer


def write_progress(job_id: str, progress: float, message: str,
                   status: str = "processing") -> None:
    """Write a progress update that the main server can read."""
    p = RESULTS_DIR / job_id / "progress.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as f:
        json.dump({
            "status": status,
            "progress": progress,
            "status_message": message,
        }, f)


def main() -> int:
    if len(sys.argv) < 4:
        print("Usage: worker.py <job_id> <video_path> <workout_json_path>")
        return 1

    job_id = sys.argv[1]
    video_path = sys.argv[2]
    workout_path = sys.argv[3]

    try:
        with open(workout_path, "r") as f:
            workout = json.load(f)
    except Exception as e:
        write_progress(job_id, 0.0, f"Failed to load workout: {e}", "failed")
        return 1

    def on_progress(p: float, msg: str) -> None:
        write_progress(job_id, p, msg)

    try:
        write_progress(job_id, 0.02, "Opening video...")
        analyzer = WorkoutAnalyzer(video_path, workout, job_id, on_progress)
        report = analyzer.run()
        # The analyzer already wrote report.json; write a final progress.
        write_progress(job_id, 1.0, "Done", "completed")
        return 0
    except Exception as e:
        tb = traceback.format_exc()
        write_progress(job_id, 0.0, f"Analysis failed: {e}", "failed")
        # Also write the error to the result dir for debugging.
        err_path = RESULTS_DIR / job_id / "error.txt"
        err_path.parent.mkdir(parents=True, exist_ok=True)
        with open(err_path, "w") as f:
            f.write(str(e) + "\n\n" + tb)
        return 1


if __name__ == "__main__":
    sys.exit(main())
