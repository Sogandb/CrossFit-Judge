"""
CrossFit Judge V2 — FastAPI service.

Endpoints (all under /api, consumed by the Next.js proxy):
  GET  /api/health            — liveness + model presence
  GET  /api/wods              — WOD catalog (for the upload form)
  GET  /api/divisions         — division registry (grouped for the select)
  POST /api/jobs              — multipart upload (video + form fields)
  GET  /api/jobs              — recent jobs (history)
  GET  /api/jobs/{id}         — status/progress polling
  GET  /api/jobs/{id}/result  — full analysis view-model
  GET  /api/jobs/{id}/video   — original/review video with HTTP Range
"""
from __future__ import annotations

import json
import re
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from config.settings import (
    MAX_UPLOAD_BYTES,
    SERVICE_PORT,
    UPLOADS_DIR,
)
from jobs.store import JobStore

app = FastAPI(title="CrossFit Judge V2 Engine", version="2.0.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
    allow_headers=["*"],
)

store: Optional[JobStore] = None


@app.on_event("startup")
def _startup() -> None:
    global store
    store = JobStore()


# --------------------------------------------------------------------------- #
# Catalog
# --------------------------------------------------------------------------- #
@app.get("/api/health")
def health():
    from config.settings import MODELS_DIR, MODEL_FILENAME
    return {
        "ok": True,
        "service": "crossfit-judge",
        "version": "2.0.0",
        "model_present": (MODELS_DIR / MODEL_FILENAME).exists(),
    }


@app.get("/api/wods")
def wods():
    from config.settings import WODS_DIR
    catalog = []
    for p in sorted(Path(WODS_DIR).glob("*.json")):
        try:
            d = json_load(p)
            catalog.append({
                "wod_id": d["wod_id"], "name_fa": d.get("name_fa"),
                "name_en": d.get("name_en"),
                "format": d.get("format"),
                "format_fa": d.get("format_fa"),
                "format_en": d.get("format_en"),
                "time_cap_sec": d.get("time_cap_sec"),
                "description_fa": d.get("description_fa"),
                "description_en": d.get("description_en"),
                "score_fa": d.get("score_fa"),
                "score_en": d.get("score_en"),
                "blocks": d.get("blocks"),
            })
        except Exception:
            continue
    return {"wods": catalog}


@app.get("/api/divisions")
def divisions():
    from config.settings import DATA_DIR
    data = json_load(Path(DATA_DIR) / "divisions.json")
    grouped: dict[str, list] = {"Men": [], "Women": []}
    for d in data["divisions"]:
        key = "Men" if d["sex"] == "M" else "Women"
        grouped[key].append({
            "id": d["id"], "label_fa": d["label_fa"],
            "label_en": d.get("label_en") or d["label_fa"],
            "weight_kg": d.get("weight_kg"),
            "weights_verified": data.get("weights_verified", False),
        })
    return {"grouped": grouped,
            "weights_verified": data.get("weights_verified", False)}


def json_load(path: Path) -> dict:
    import json
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# Upload
# --------------------------------------------------------------------------- #
_ALLOWED_EXT = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}


@app.post("/api/jobs")
async def create_job(
    video: UploadFile = File(...),
    wod_id: str = Form("wodx_ladder_wod1"),
    division: str = Form(...),
    athlete_name: Optional[str] = Form(None),
    claimed_reps: Optional[int] = Form(None),
    claimed_time_min: Optional[int] = Form(None),
    claimed_time_sec: Optional[int] = Form(None),
    claimed_capped: Optional[bool] = Form(None),
    manual_start_sec: Optional[float] = Form(None),
    pose_source: Optional[str] = Form(None),   # "mock" — testing only
    mock_block_scale: Optional[float] = Form(None),
    mock_faults: Optional[str] = Form(None),
):
    if store is None:
        raise HTTPException(503, "Service is not ready")
    ext = Path(video.filename or "").suffix.lower()
    if ext not in _ALLOWED_EXT:
        raise HTTPException(415, "Unsupported file format (allowed: MP4 / MOV / WebM)")
    _validate_division(division)

    job_id = None
    updir: Optional[Path] = None
    try:
        job_id = _new_job_id()
        updir = UPLOADS_DIR / job_id
        updir.mkdir(parents=True, exist_ok=True)
        dst = updir / "original.mp4"
        size = 0
        with open(dst, "wb") as f:
            while chunk := await video.read(4 * 1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        413, f"File exceeds the maximum allowed size "
                             f"({MAX_UPLOAD_BYTES // (1024**3)} GB)")
                f.write(chunk)
    except HTTPException:
        if updir and updir.exists():
            shutil.rmtree(updir, ignore_errors=True)
        raise
    except Exception as e:
        if updir and updir.exists():
            shutil.rmtree(updir, ignore_errors=True)
        raise HTTPException(500, f"Failed to store the file: {e}")
    finally:
        await video.close()

    claimed = _claimed_from(claimed_reps, claimed_time_min,
                            claimed_time_sec, claimed_capped)
    meta = _build_meta(wod_id, division, athlete_name, claimed,
                       manual_start_sec, video.filename, pose_source,
                       mock_block_scale, mock_faults)

    # NOTE: the upload folder already carries this id (files were saved
    # there) — register the job with the SAME id.
    actual_id = store.create_with_id(job_id, meta, str(updir / "original.mp4"),
                                     str(updir / "review.mp4"))
    return {"job_id": actual_id}


# --------------------------------------------------------------------------- #
# Chunked / resumable upload (large videos through constrained proxies)
#
# A single giant multipart POST can stall inside reverse proxies / tunnels
# that cap or buffer large request bodies (observed: upload frozen at 0%).
# The client therefore splits the video into small sequential chunks:
#   POST /api/jobs/init               → form fields, creates the session
#   POST /api/jobs/{id}/chunk?index=N → raw octet-stream body, appended
#   GET  /api/jobs/{id}/session       → resume probe (received/expected)
#   POST /api/jobs/{id}/complete      → finalize + register the job
# Chunks are strictly in-order (idempotent re-ack for retried ones); the
# part file is truncated back to the acknowledged size before every append,
# so a failed/timed-out attempt never corrupts the stream.
# --------------------------------------------------------------------------- #
_SESSION_NAME = "session.json"
_PART_NAME = "original.mp4.part"
_STALE_SESSION_SEC = 24 * 3600
_SWEEP_INTERVAL_SEC = 600
CHUNK_SUGGEST_BYTES = 8 * 1024 * 1024

_sess_locks: "dict[str, threading.Lock]" = {}
_sess_locks_guard = threading.Lock()
_sweep_ts = [0.0]


def _new_job_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]


def _validate_division(division: str) -> None:
    from config.settings import DATA_DIR
    divisions = json_load(Path(DATA_DIR) / "divisions.json")["divisions"]
    if not any(d["id"] == division for d in divisions):
        raise HTTPException(422, "Selected division is not valid")


def _claimed_from(claimed_reps: Optional[int], claimed_time_min: Optional[int],
                   claimed_time_sec: Optional[int],
                   claimed_capped: Optional[bool]) -> Optional[dict]:
    if claimed_reps is None and claimed_time_min is None \
            and claimed_time_sec is None and claimed_capped is None:
        return None
    tsec = None
    if claimed_time_min is not None or claimed_time_sec is not None:
        tsec = (claimed_time_min or 0) * 60 + (claimed_time_sec or 0)
    return {
        "reps": claimed_reps,
        "time_sec": tsec,
        "capped": bool(claimed_capped) if claimed_capped is not None else None,
    }


def _build_meta(wod_id: str, division: str, athlete_name: Optional[str],
                claimed: Optional[dict], manual_start_sec: Optional[float],
                filename: Optional[str], pose_source: Optional[str],
                mock_block_scale: Optional[float],
                mock_faults: Optional[str]) -> dict:
    meta = {
        "wod_id": wod_id,
        "division": division,
        "athlete_name": athlete_name,
        "claimed": claimed,
        "manual_start_sec": manual_start_sec,
        "filename": filename,
    }
    if pose_source == "mock":
        meta["pose_source"] = "mock"
        if mock_block_scale is not None:
            meta["mock_block_scale"] = mock_block_scale
        if mock_faults:
            try:
                meta["mock_faults"] = json.loads(mock_faults)
            except Exception:
                pass
    return meta


def _sess_dir(job_id: str) -> Path:
    return UPLOADS_DIR / job_id


def _sess_lock(job_id: str) -> threading.Lock:
    with _sess_locks_guard:
        lk = _sess_locks.get(job_id)
        if lk is None:
            lk = threading.Lock()
            _sess_locks[job_id] = lk
        return lk


def _sess_load(job_id: str) -> Optional[dict]:
    p = _sess_dir(job_id) / _SESSION_NAME
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _sess_save(job_id: str, sess: dict) -> None:
    p = _sess_dir(job_id) / _SESSION_NAME
    p.write_text(json.dumps(sess, ensure_ascii=False), encoding="utf-8")


def _sweep_stale_sessions() -> None:
    """Best-effort cleanup of upload sessions abandoned > 24 h ago."""
    now = time.time()
    if now - _sweep_ts[0] < _SWEEP_INTERVAL_SEC:
        return
    _sweep_ts[0] = now
    try:
        entries = list(UPLOADS_DIR.iterdir())
    except OSError:
        return
    for d in entries:
        if not d.is_dir():
            continue
        s = d / _SESSION_NAME
        if not s.exists():
            continue
        try:
            if now - s.stat().st_mtime > _STALE_SESSION_SEC:
                if store is None or store.get(d.name) is None:
                    shutil.rmtree(d, ignore_errors=True)
        except OSError:
            continue


@app.post("/api/jobs/init")
async def init_upload(
    filename: str = Form(...),
    total_bytes: Optional[int] = Form(None),
    wod_id: str = Form("wodx_ladder_wod1"),
    division: str = Form(...),
    athlete_name: Optional[str] = Form(None),
    claimed_reps: Optional[int] = Form(None),
    claimed_time_min: Optional[int] = Form(None),
    claimed_time_sec: Optional[int] = Form(None),
    claimed_capped: Optional[bool] = Form(None),
    manual_start_sec: Optional[float] = Form(None),
    pose_source: Optional[str] = Form(None),
    mock_block_scale: Optional[float] = Form(None),
    mock_faults: Optional[str] = Form(None),
):
    if store is None:
        raise HTTPException(503, "Service is not ready")
    if not filename or not Path(filename).suffix.lower() in _ALLOWED_EXT:
        raise HTTPException(415, "Unsupported file format (allowed: MP4 / MOV / WebM)")
    _validate_division(division)
    if total_bytes is not None and total_bytes > MAX_UPLOAD_BYTES:
        raise HTTPException(
            413, f"File exceeds the maximum allowed size "
                 f"({MAX_UPLOAD_BYTES // (1024**3)} GB)")
    _sweep_stale_sessions()

    job_id = _new_job_id()
    updir = _sess_dir(job_id)
    updir.mkdir(parents=True, exist_ok=True)
    claimed = _claimed_from(claimed_reps, claimed_time_min,
                            claimed_time_sec, claimed_capped)
    meta = _build_meta(wod_id, division, athlete_name, claimed,
                       manual_start_sec, filename, pose_source,
                       mock_block_scale, mock_faults)
    _sess_save(job_id, {
        "job_id": job_id,
        "filename": filename,
        "total_bytes": total_bytes,
        "received": 0,
        "expected_index": 0,
        "meta": meta,
    })
    return {"job_id": job_id, "chunk_size": CHUNK_SUGGEST_BYTES,
            "received": 0, "expected_index": 0}


@app.post("/api/jobs/{job_id}/chunk")
async def upload_chunk(job_id: str, index: int, total: int, request: Request):
    if store is None:
        raise HTTPException(503, "Service is not ready")
    sess = _sess_load(job_id)
    if sess is None:
        raise HTTPException(404, "Upload session not found (expired or already finished)")
    if index < sess["expected_index"]:
        # Retried chunk the server already stored — DRAIN the body first so the
        # client never sees a connection reset on an early response, then ack
        # idempotently (no extra bytes written).
        async for _ in request.stream():
            pass
        return {"job_id": job_id, "received": sess["received"],
                "expected_index": sess["expected_index"], "duplicate": True}
    if index > sess["expected_index"]:
        async for _ in request.stream():
            pass
        return JSONResponse(status_code=409, content={
            "detail": "Out-of-order chunk", "expected_index": sess["expected_index"]})

    part = _sess_dir(job_id) / _PART_NAME
    received = sess["received"]
    limit_hit = False
    with _sess_lock(job_id):
        # Rewind any partial write left by a failed attempt → retries are
        # byte-identical (idempotent at the file level).
        with open(part, "r+b" if part.exists() else "wb") as f:
            f.truncate(received)
            f.seek(received)
            written = 0
            async for data in request.stream():
                written += len(data)
                if received + written > MAX_UPLOAD_BYTES:
                    limit_hit = True
                    break
                f.write(data)
        if limit_hit:
            with open(part, "r+b") as f:
                f.truncate(received)
            raise HTTPException(
                413, f"File exceeds the maximum allowed size "
                      f"({MAX_UPLOAD_BYTES // (1024**3)} GB)")
        _sess_save(job_id, {**sess, "received": received + written,
                            "expected_index": index + 1})
    return {"job_id": job_id, "received": received + written,
            "expected_index": index + 1, "duplicate": False}


@app.get("/api/jobs/{job_id}/session")
def upload_session_state(job_id: str):
    sess = _sess_load(job_id)
    if sess is None:
        job = store.get(job_id) if store else None
        if job is not None:
            return {"job_id": job_id, "complete": True, "registered": True}
        raise HTTPException(404, "Upload session not found")
    return {"job_id": job_id, "complete": False, "registered": False,
            "received": sess["received"],
            "expected_index": sess["expected_index"],
            "total_bytes": sess.get("total_bytes")}


@app.post("/api/jobs/{job_id}/complete")
def complete_upload(job_id: str):
    if store is None:
        raise HTTPException(503, "Service is not ready")
    sess = _sess_load(job_id)
    if sess is None:
        raise HTTPException(404, "Upload session not found (expired or already finished)")
    total = sess.get("total_bytes")
    if total is not None and sess["received"] != total:
        raise HTTPException(
            400, f"Upload incomplete: received {sess['received']} of {total} bytes "
                 f"(next expected chunk index is {sess['expected_index']})")
    updir = _sess_dir(job_id)
    part = updir / _PART_NAME
    if not part.exists() or part.stat().st_size == 0:
        raise HTTPException(400, "No data uploaded for this session")
    dst = updir / "original.mp4"
    part.rename(dst)
    (updir / _SESSION_NAME).unlink(missing_ok=True)
    with _sess_locks_guard:
        _sess_locks.pop(job_id, None)
    actual_id = store.create_with_id(job_id, sess["meta"], str(dst),
                                     str(updir / "review.mp4"))
    return {"job_id": actual_id}


# --------------------------------------------------------------------------- #
# Jobs
# --------------------------------------------------------------------------- #
@app.get("/api/jobs")
def list_jobs():
    if store is None:
        raise HTTPException(503, "Service is not ready")
    return {"jobs": store.list()}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    if store is None:
        raise HTTPException(503, "Service is not ready")
    job = store.get(job_id)
    if job is None:
        raise HTTPException(404, "Analysis not found")
    result = None
    if job["status"] == "done":
        result = store.get_result(job_id)
    return {"job": job, "result": result}


@app.get("/api/jobs/{job_id}/result")
def job_result(job_id: str):
    if store is None:
        raise HTTPException(503, "Service is not ready")
    if store.get(job_id) is None:
        raise HTTPException(404, "Analysis not found")
    result = store.get_result(job_id)
    if result is None:
        raise HTTPException(409, "Result is not ready yet")
    return result


_RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")


@app.get("/api/jobs/{job_id}/video")
def job_video(job_id: str, variant: str = "review"):
    if store is None:
        raise HTTPException(503, "Service is not ready")
    name = "review.mp4" if variant == "review" else "original.mp4"
    path = UPLOADS_DIR / job_id / name
    if not path.exists():
        raise HTTPException(404, "Video not found")
    return FileRangeResponse(path)


class FileRangeResponse(Response):
    """Minimal HTTP-Range file response so browsers can seek the review video."""

    def __init__(self, path: Path, chunk: int = 1024 * 512):
        self.path, self.chunk = path, chunk
        self.size = path.stat().st_size
        super().__init__(content=None, status_code=200, media_type="video/mp4")

    async def __call__(self, scope, receive, send):
        headers = {k.decode().lower(): v.decode()
                   for k, v in scope.get("headers", [])}
        rng = headers.get("range")
        start, end, status = 0, self.size - 1, 200
        if rng:
            m = _RANGE_RE.match(rng)
            if m and m.group(1):
                start = int(m.group(1))
                if m.group(2):
                    end = min(int(m.group(2)), self.size - 1)
                status = 206
            elif m and m.group(2):  # suffix range: bytes=-N
                n = int(m.group(2))
                start, end = max(0, self.size - n), self.size - 1
                status = 206
        length = end - start + 1
        hdrs = [
            (b"content-type", b"video/mp4"),
            (b"accept-ranges", b"bytes"),
            (b"content-length", str(length).encode()),
        ]
        if status == 206:
            hdrs.append((b"content-range",
                         f"bytes {start}-{end}/{self.size}".encode()))
        await send({"type": "http.response.start", "status": status,
                    "headers": hdrs})
        with open(self.path, "rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                data = f.read(min(self.chunk, remaining))
                if not data:
                    break
                remaining -= len(data)
                await send({"type": "http.response.body", "body": data,
                            "more_body": remaining > 0})
        await send({"type": "http.response.body", "body": b"",
                    "more_body": False})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=SERVICE_PORT, log_level="warning")
