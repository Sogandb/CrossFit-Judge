"""
FastAPI server for the CrossFit Judge.

The heavy analysis (MediaPipe pose detection) runs in a **subprocess** so
that segfaults — which MediaPipe can trigger on certain video frames — only
kill the worker, not the main API server. The main server stays alive and
can report the failure to the frontend.

Endpoints
---------
GET  /api/health            - liveness probe
GET  /api/workouts          - list available workout definitions
GET  /api/movements         - list available movements
POST /api/judge             - upload a video + workout id, start analysis
POST /api/judge_custom      - upload with a custom workout definition
POST /api/demo/{workout_id} - run a demo with synthetic data
GET  /api/status/{job_id}   - polling endpoint for processing progress
GET  /api/results/{job_id}  - final JSON report
GET  /api/video/{job_id}    - annotated mp4 file
GET  /api/timeline/{job_id} - timeline png
"""
from __future__ import annotations

import json
import os
import subprocess
import time
import sys
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config.settings import UPLOADS_DIR, RESULTS_DIR
from config.workouts import list_workouts, get_workout

PORT = 8001


def _ensure_graphics_libs() -> None:
    """
    Ensure libGLESv2.so.2 and libEGL.so.1 symlinks exist. MediaPipe needs
    these but they're not installed system-wide; we borrow them from the
    bundled Chrome. These symlinks can disappear if the venv is recreated.
    """
    import os
    chrome_dir = "/home/z/.agent-browser/browsers/chrome-150.0.7871.49"
    venv_lib = "/home/z/.venv/lib"
    links = [
        ("libGLESv2.so.2", "libGLESv2.so"),
        ("libEGL.so.1", "libEGL.so"),
        ("libGLESv2.so", "libGLESv2.so"),
    ]
    for link_name, target_name in links:
        link_path = os.path.join(venv_lib, link_name)
        target_path = os.path.join(chrome_dir, target_name)
        if not os.path.exists(link_path) and os.path.exists(target_path):
            try:
                os.symlink(target_path, link_path)
            except OSError:
                pass


_ensure_graphics_libs()

app = FastAPI(title="CrossFit Judge", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

SERVICE_DIR = Path(__file__).resolve().parent
JOBS_DIR = RESULTS_DIR / "_jobs"
JOBS_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Disk-persistent job store — survives server restarts.
# ---------------------------------------------------------------------------
class JobStore:
    """Persists job state to disk so jobs survive server restarts."""

    @staticmethod
    def _job_path(job_id: str) -> Path:
        return JOBS_DIR / f"{job_id}.json"

    @staticmethod
    def save(job_id: str, job: dict[str, Any]) -> None:
        """Save job state to disk."""
        try:
            with open(JobStore._job_path(job_id), "w") as f:
                json.dump(job, f, ensure_ascii=False)
        except Exception:
            pass  # Don't crash the job if disk write fails.

    @staticmethod
    def load(job_id: str) -> dict[str, Any] | None:
        """Load a job from disk (or memory)."""
        path = JobStore._job_path(job_id)
        if path.exists():
            try:
                with open(path, "r") as f:
                    return json.load(f)
            except Exception:
                return None
        return None

    @staticmethod
    def load_all() -> dict[str, dict[str, Any]]:
        """Load all jobs from disk (called on startup)."""
        jobs = {}
        for p in JOBS_DIR.glob("*.json"):
            try:
                with open(p, "r") as f:
                    job = json.load(f)
                    jobs[job["job_id"]] = job
            except Exception:
                pass
        return jobs

    @staticmethod
    def list_all() -> list[dict[str, Any]]:
        """List all jobs (lightweight)."""
        result = []
        for p in sorted(JOBS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime,
                        reverse=True):
            try:
                with open(p, "r") as f:
                    job = json.load(f)
                    result.append({
                        "job_id": job.get("job_id", p.stem),
                        "status": job.get("status", "unknown"),
                        "progress": job.get("progress", 0),
                        "workout_id": job.get("workout_id", ""),
                        "video_name": job.get("video_name", ""),
                    })
            except Exception:
                pass
        return result


# In-memory cache (backed by disk).
_jobs: dict[str, dict[str, Any]] = JobStore.load_all()


def _save_job(job_id: str) -> None:
    """Save a job to both memory and disk."""
    if job_id in _jobs:
        JobStore.save(job_id, _jobs[job_id])


def _get_job(job_id: str) -> dict[str, Any] | None:
    """Get a job from memory, or load from disk if not in memory."""
    if job_id in _jobs:
        return _jobs[job_id]
    # Try loading from disk (server may have restarted).
    job = JobStore.load(job_id)
    if job:
        _jobs[job_id] = job
    return job


def _run_analysis_subprocess(job_id: str, video_path: str,
                             workout: dict[str, Any]) -> None:
    """
    Run the analysis in a subprocess so a MediaPipe segfault doesn't crash
    the main server. Progress is read from progress.json on disk.
    """
    job = _jobs[job_id]

    # Write the workout definition to a temp file for the worker.
    workout_file = RESULTS_DIR / job_id / "workout.json"
    workout_file.parent.mkdir(parents=True, exist_ok=True)
    with open(workout_file, "w") as f:
        json.dump(workout, f)

    # Environment for the subprocess.
    env = os.environ.copy()
    chrome_lib = "/home/z/.agent-browser/browsers/chrome-150.0.7871.49"
    env["LD_LIBRARY_PATH"] = (
        f"{chrome_lib}:/home/z/.venv/lib:{env.get('LD_LIBRARY_PATH', '')}"
    )
    env["MEDIAPIPE_DISABLE_GPU"] = "1"
    env["GLOG_minloglevel"] = "2"
    env["LIBGL_ALWAYS_SOFTWARE"] = "1"
    env["EGL_PLATFORM"] = "surfaceless"

    try:
        proc = subprocess.run(
            [sys.executable, str(SERVICE_DIR / "worker.py"),
             job_id, video_path, str(workout_file)],
            cwd=str(SERVICE_DIR),
            env=env,
            capture_output=True,
            text=True,
            timeout=300,  # 5-minute hard limit
        )

        if proc.returncode != 0:
            stderr = proc.stderr[-500:] if proc.stderr else ""
            if proc.returncode < 0:
                error_msg = (
                    f"The analysis engine crashed (signal {-proc.returncode}). "
                    f"This can happen with certain video formats. "
                    f"Try re-encoding to MP4 H.264."
                )
            else:
                error_msg = f"Analysis failed (exit {proc.returncode}). {stderr[:200]}"
            job["status"] = "failed"
            job["error"] = error_msg
            _save_job(job_id)
            return

        # Read the final report.
        report_path = RESULTS_DIR / job_id / "report.json"
        if report_path.exists():
            with open(report_path, "r") as f:
                report = json.load(f)
            job["status"] = "completed"
            job["progress"] = 1.0
            job["report"] = report
            _save_job(job_id)
        else:
            job["status"] = "failed"
            job["error"] = "Analysis completed but no report was generated."
            _save_job(job_id)
    except subprocess.TimeoutExpired:
        job["status"] = "failed"
        job["error"] = (
            "Analysis timed out (5 minute limit). The video may be too long. "
            "Try a shorter clip."
        )
        _save_job(job_id)
    except Exception as exc:  # noqa: BLE001
        job["status"] = "failed"
        job["error"] = f"Unexpected error: {exc}"
        _save_job(job_id)


def _run_demo(job_id: str, workout_id: str) -> None:
    """Run a demo analysis using synthetic pose data (in-process)."""
    job = _jobs[job_id]

    def on_progress(p: float, msg: str) -> None:
        job["progress"] = p
        job["status_message"] = msg
        _save_job(job_id)

    try:
        workout = get_workout(workout_id)
        workout["id"] = workout_id

        from tests.test_synthetic import (
            make_video, squat_pose, joints_to_pose, REST_FRAMES,
        )
        from config.settings import UPLOADS_DIR
        from core.analyzer import WorkoutAnalyzer

        video_path = str(UPLOADS_DIR / f"{job_id}_demo.mp4")
        make_video(video_path, squat_pose, cycles=8, frames_per_cycle=30)

        class _MockPose:
            def __init__(self):
                self._period = 30 + REST_FRAMES

            def process_frame(self, bgr_frame, frame_index, timestamp):
                pos = frame_index % self._period
                t = pos / 30 if pos < 30 else 0.0
                return joints_to_pose(squat_pose(t), frame_index, timestamp)

            def close(self):
                pass

        analyzer = WorkoutAnalyzer(video_path, workout, job_id, on_progress,
                                   pose_detector=_MockPose())
        report = analyzer.run()
        job["status"] = "completed"
        job["progress"] = 1.0
        job["report"] = report
        _save_job(job_id)
    except Exception as exc:  # noqa: BLE001
        job["status"] = "failed"
        job["error"] = str(exc)
        _save_job(job_id)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "service": "crossfit-judge"}


@app.get("/api/workouts")
async def api_workouts() -> dict[str, Any]:
    return {"workouts": list_workouts()}


@app.get("/api/movements")
async def api_movements() -> dict[str, Any]:
    from movements import MOVEMENTS
    return {"movements": list(MOVEMENTS.keys())}


@app.post("/api/demo/{workout_id}")
async def api_demo(workout_id: str) -> dict[str, Any]:
    if workout_id not in {w["id"] for w in list_workouts()}:
        raise HTTPException(status_code=400, detail=f"Unknown workout_id: {workout_id}")
    job_id = uuid.uuid4().hex[:12]
    _jobs[job_id] = {
        "job_id": job_id,
        "status": "processing",
        "created_at": time.time(),
        "progress": 0.0,
        "status_message": "Generating demo video...",
        "workout_id": workout_id,
        "video_name": "demo_squats.mp4",
    }
    _save_job(job_id)
    thread = threading.Thread(target=_run_demo, args=(job_id, workout_id),
                              daemon=True)
    thread.start()
    return {"job_id": job_id, "status": "processing",
        "created_at": time.time(), "demo": True}


# ---------------------------------------------------------------------------
# Chunked upload — bypasses the 32MB gateway body limit by splitting the
# video into small chunks (5MB each) and reassembling on the server.
# ---------------------------------------------------------------------------
# In-memory registry of in-progress chunked uploads.
_uploads: dict[str, dict[str, Any]] = {}

CHUNK_SIZE = 5 * 1024 * 1024  # 5 MB per chunk — well under the 32MB limit


@app.post("/api/upload/init")
async def api_upload_init(
    filename: str = Form(...),
    total_size: int = Form(...),
    workout_id: str = Form(default=""),
    # Custom workout fields (optional — used if workout_id == "custom")
    workout_name: str = Form(default=""),
    format: str = Form(default=""),
    time_cap_seconds: int = Form(default=60),
    movements: str = Form(default=""),
) -> dict[str, Any]:
    """Initialize a chunked upload session. Returns an upload_id."""
    upload_id = uuid.uuid4().hex[:16]
    ext = os.path.splitext(filename or "video.mp4")[1] or ".mp4"
    final_path = UPLOADS_DIR / f"{upload_id}{ext}"
    _uploads[upload_id] = {
        "filename": filename,
        "total_size": total_size,
        "received": 0,
        "final_path": str(final_path),
        "workout_id": workout_id,
        "workout_name": workout_name,
        "format": format,
        "time_cap_seconds": time_cap_seconds,
        "movements": movements,
        "chunks": [],
    }
    return {"upload_id": upload_id, "chunk_size": CHUNK_SIZE}


@app.post("/api/upload/{upload_id}/chunk")
async def api_upload_chunk(
    upload_id: str,
    chunk_index: int = Form(...),
    file: UploadFile = File(...),
) -> dict[str, Any]:
    """Receive one chunk of a chunked upload."""
    up = _uploads.get(upload_id)
    if not up:
        raise HTTPException(status_code=404, detail="Unknown upload_id")

    data = await file.read()
    chunk_path = UPLOADS_DIR / f"{upload_id}.part{chunk_index}"
    with open(chunk_path, "wb") as f:
        f.write(data)
    up["chunks"].append((chunk_index, str(chunk_path)))
    up["received"] += len(data)
    pct = (up["received"] / up["total_size"]) * 100 if up["total_size"] else 0
    return {
        "upload_id": upload_id,
        "chunk_index": chunk_index,
        "received": up["received"],
        "total": up["total_size"],
        "progress": round(pct, 1),
    }


@app.post("/api/upload/{upload_id}/complete")
async def api_upload_complete(upload_id: str) -> dict[str, Any]:
    """Reassemble chunks and start the analysis job."""
    up = _uploads.get(upload_id)
    if not up:
        raise HTTPException(status_code=404, detail="Unknown upload_id")

    # Reassemble chunks in order.
    final_path = up["final_path"]
    chunks = sorted(up["chunks"], key=lambda c: c[0])
    with open(final_path, "wb") as out:
        for _, chunk_path in chunks:
            with open(chunk_path, "rb") as f:
                out.write(f.read())
            # Clean up the chunk file.
            try:
                os.remove(chunk_path)
            except OSError:
                pass

    # Build the workout definition.
    if up["workout_id"] == "custom":
        from config.workouts import make_custom_workout
        movement_names = [m.strip() for m in up["movements"].split(",") if m.strip()]
        workout = make_custom_workout(
            up["workout_name"], up["format"],
            up["time_cap_seconds"], movement_names,
        )
        workout["id"] = "custom"
        workout_id_label = "custom"
    else:
        workout = get_workout(up["workout_id"])
        workout["id"] = up["workout_id"]
        workout_id_label = up["workout_id"]

    # Create the job and start analysis.
    job_id = uuid.uuid4().hex[:12]
    _jobs[job_id] = {
        "job_id": job_id,
        "status": "processing",
        "created_at": time.time(),
        "progress": 0.0,
        "status_message": "Queued",
        "workout_id": workout_id_label,
        "video_name": up["filename"],
    }
    _save_job(job_id)

    thread = threading.Thread(
        target=_run_analysis_subprocess,
        args=(job_id, final_path, workout),
        daemon=True,
    )
    thread.start()

    # Clean up the upload session.
    del _uploads[upload_id]

    return {"job_id": job_id, "status": "processing"}


@app.post("/api/judge")
async def api_judge(
    file: UploadFile = File(...),
    workout_id: str = Form(...),
) -> dict[str, Any]:
    if workout_id not in {w["id"] for w in list_workouts()}:
        raise HTTPException(status_code=400, detail=f"Unknown workout_id: {workout_id}")

    job_id = uuid.uuid4().hex[:12]
    ext = os.path.splitext(file.filename or "video.mp4")[1] or ".mp4"
    video_path = UPLOADS_DIR / f"{job_id}{ext}"
    # Stream to disk in chunks.
    with open(video_path, "wb") as f:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)

    workout = get_workout(workout_id)
    workout["id"] = workout_id

    _jobs[job_id] = {
        "job_id": job_id,
        "status": "processing",
        "created_at": time.time(),
        "progress": 0.0,
        "status_message": "Queued",
        "workout_id": workout_id,
        "video_name": file.filename,
    }
    _save_job(job_id)

    thread = threading.Thread(target=_run_analysis_subprocess,
                              args=(job_id, str(video_path), workout),
                              daemon=True)
    thread.start()

    return {"job_id": job_id, "status": "processing"}


@app.post("/api/judge_custom")
async def api_judge_custom(
    file: UploadFile = File(...),
    workout_name: str = Form(...),
    format: str = Form(...),
    time_cap_seconds: int = Form(...),
    movements: str = Form(...),
) -> dict[str, Any]:
    from config.workouts import make_custom_workout
    movement_names = [m.strip() for m in movements.split(",") if m.strip()]
    valid_movements = {"squat", "pushup", "burpee", "thruster", "pullup",
                       "kettlebell_swing"}
    for m in movement_names:
        if m not in valid_movements:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown movement: {m}. Valid: {', '.join(sorted(valid_movements))}")
    if format not in {"amrap", "for_time", "max_reps", "tabata", "emom"}:
        raise HTTPException(status_code=400, detail=f"Unknown format: {format}")
    if not movement_names:
        raise HTTPException(status_code=400, detail="At least one movement required")

    workout = make_custom_workout(workout_name, format, time_cap_seconds,
                                  movement_names)
    workout["id"] = "custom"

    job_id = uuid.uuid4().hex[:12]
    ext = os.path.splitext(file.filename or "video.mp4")[1] or ".mp4"
    video_path = UPLOADS_DIR / f"{job_id}{ext}"
    with open(video_path, "wb") as f:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)

    _jobs[job_id] = {
        "job_id": job_id,
        "status": "processing",
        "created_at": time.time(),
        "progress": 0.0,
        "status_message": "Queued",
        "workout_id": "custom",
        "video_name": file.filename,
    }
    _save_job(job_id)

    thread = threading.Thread(target=_run_analysis_subprocess,
                              args=(job_id, str(video_path), workout),
                              daemon=True)
    thread.start()

    return {"job_id": job_id, "status": "processing"}


@app.get("/api/status/{job_id}")
async def api_status(job_id: str) -> dict[str, Any]:
    # Use _get_job which loads from disk if not in memory (server restart).
    job = _get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Unknown job_id")

    # For subprocess jobs, read the latest progress from disk.
    if job["status"] == "processing":
        import time
        prog_path = RESULTS_DIR / job_id / "progress.json"
        if prog_path.exists():
            try:
                with open(prog_path, "r") as f:
                    prog = json.load(f)
                # If the worker wrote a "completed" or "failed" status to
                # progress.json, use that (the worker may have finished but
                # the main process hasn't updated the job yet).
                prog_status = prog.get("status", "")
                if prog_status in ("completed", "failed"):
                    job["status"] = prog_status
                    job["progress"] = prog.get("progress", 1.0)
                    job["status_message"] = prog.get("status_message", "")
                    if prog_status == "failed":
                        job["error"] = prog.get("status_message",
                                                "Analysis failed")
                    _save_job(job_id)
                else:
                    job["progress"] = prog.get("progress", job["progress"])
                    job["status_message"] = prog.get("status_message",
                                                      job["status_message"])
            except Exception:
                pass

        # Stale-job detection: if the job has been "processing" for more
        # than 90 seconds without a progress update, the worker probably
        # crashed (segfault) or the server restarted. Mark as failed so
        # the frontend can recover instead of hanging forever.
        prog_mtime = prog_path.stat().st_mtime if prog_path.exists() else 0
        job_created = job.get("created_at", time.time())
        now = time.time()

        if prog_mtime > 0:
            # Progress file exists — check if it's stale.
            if (now - prog_mtime) > 90:
                job["status"] = "failed"
                job["error"] = (
                    "Analysis was interrupted (the engine may have crashed "
                    "on this video). Try a shorter clip or re-encode to MP4 H.264."
                )
                _save_job(job_id)
        else:
            # No progress file at all — worker never started or crashed
            # immediately. If the job is older than 30 seconds, fail it.
            if (now - job_created) > 30:
                job["status"] = "failed"
                job["error"] = (
                    "Analysis failed to start. The server may be busy — "
                    "please try again."
                )
                _save_job(job_id)

    return {
        "job_id": job_id,
        "status": job["status"],
        "progress": job["progress"],
        "status_message": job["status_message"],
        "error": job.get("error"),
    }


@app.get("/api/results/{job_id}")
async def api_results(job_id: str) -> dict[str, Any]:
    job = _get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Unknown job_id")
    if job["status"] != "completed":
        raise HTTPException(status_code=409,
                            detail=f"Job is {job['status']}, not completed")
    return job["report"]


@app.get("/api/video/{job_id}")
async def api_video(job_id: str):
    path = RESULTS_DIR / job_id / "annotated.mp4"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Annotated video not found")
    return FileResponse(str(path), media_type="video/mp4",
                        filename=f"{job_id}_annotated.mp4")


@app.get("/api/timeline/{job_id}")
async def api_timeline(job_id: str):
    path = RESULTS_DIR / job_id / "timeline.png"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Timeline not found")
    return FileResponse(str(path), media_type="image/png")


@app.get("/api/jobs")
async def api_jobs() -> dict[str, Any]:
    return {"jobs": JobStore.list_all()}


if __name__ == "__main__":
    import uvicorn
    print(f"[crossfit-judge] starting on port {PORT}")
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
