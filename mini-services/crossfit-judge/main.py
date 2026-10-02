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

import re
import shutil
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

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
                "format_fa": d.get("format_fa"),
                "time_cap_sec": d.get("time_cap_sec"),
                "description_fa": d.get("description_fa"),
                "blocks": d.get("blocks"),
            })
        except Exception:
            continue
    return {"wods": catalog}


@app.get("/api/divisions")
def divisions():
    from config.settings import DATA_DIR
    data = json_load(Path(DATA_DIR) / "divisions.json")
    grouped: dict[str, list] = {"آقایان": [], "بانوان": []}
    for d in data["divisions"]:
        key = "آقایان" if d["sex"] == "M" else "بانوان"
        grouped[key].append({
            "id": d["id"], "label_fa": d["label_fa"],
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
        raise HTTPException(503, "سرویس آماده نیست")
    ext = Path(video.filename or "").suffix.lower()
    if ext not in _ALLOWED_EXT:
        raise HTTPException(415, "فرمت فایل مجاز نیست (MP4/MOV/WebM)")
    # validate the division against the registry
    from config.settings import DATA_DIR
    divisions = json_load(Path(DATA_DIR) / "divisions.json")["divisions"]
    if not any(d["id"] == division for d in divisions):
        raise HTTPException(422, "رده سنی انتخاب‌شده معتبر نیست")

    job_id = None
    updir: Optional[Path] = None
    try:
        import time as _t, uuid as _u
        job_id = _t.strftime("%Y%m%d-%H%M%S") + "-" + _u.uuid4().hex[:8]
        updir = UPLOADS_DIR / job_id
        updir.mkdir(parents=True, exist_ok=True)
        dst = updir / "original.mp4"
        size = 0
        with open(dst, "wb") as f:
            while chunk := await video.read(4 * 1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        413, f"حجم فایل بیش از سقف مجاز "
                             f"({MAX_UPLOAD_BYTES // (1024**3)} گیگابایت) است")
                f.write(chunk)
    except HTTPException:
        if updir and updir.exists():
            shutil.rmtree(updir, ignore_errors=True)
        raise
    except Exception as e:
        if updir and updir.exists():
            shutil.rmtree(updir, ignore_errors=True)
        raise HTTPException(500, f"خطا در ذخیره فایل: {e}")
    finally:
        await video.close()

    claimed = None
    if claimed_reps is not None or claimed_time_min is not None \
            or claimed_time_sec is not None or claimed_capped is not None:
        tsec = None
        if claimed_time_min is not None or claimed_time_sec is not None:
            tsec = (claimed_time_min or 0) * 60 + (claimed_time_sec or 0)
        claimed = {
            "reps": claimed_reps,
            "time_sec": tsec,
            "capped": bool(claimed_capped) if claimed_capped is not None else None,
        }
    meta = {
        "wod_id": wod_id,
        "division": division,
        "athlete_name": athlete_name,
        "claimed": claimed,
        "manual_start_sec": manual_start_sec,
        "filename": video.filename,
    }
    if pose_source == "mock":
        meta["pose_source"] = "mock"
        if mock_block_scale is not None:
            meta["mock_block_scale"] = mock_block_scale
        if mock_faults:
            try:
                import json as _j
                meta["mock_faults"] = _j.loads(mock_faults)
            except Exception:
                pass

    # NOTE: the upload folder already carries this id (files were saved
    # there) — register the job with the SAME id.
    actual_id = store.create_with_id(job_id, meta, str(updir / "original.mp4"),
                                     str(updir / "review.mp4"))
    return {"job_id": actual_id}


# --------------------------------------------------------------------------- #
# Jobs
# --------------------------------------------------------------------------- #
@app.get("/api/jobs")
def list_jobs():
    if store is None:
        raise HTTPException(503, "سرویس آماده نیست")
    return {"jobs": store.list()}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    if store is None:
        raise HTTPException(503, "سرویس آماده نیست")
    job = store.get(job_id)
    if job is None:
        raise HTTPException(404, "تحلیل یافت نشد")
    result = None
    if job["status"] == "done":
        result = store.get_result(job_id)
    return {"job": job, "result": result}


@app.get("/api/jobs/{job_id}/result")
def job_result(job_id: str):
    if store is None:
        raise HTTPException(503, "سرویس آماده نیست")
    if store.get(job_id) is None:
        raise HTTPException(404, "تحلیل یافت نشد")
    result = store.get_result(job_id)
    if result is None:
        raise HTTPException(409, "نتیجه هنوز آماده نیست")
    return result


_RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")


@app.get("/api/jobs/{job_id}/video")
def job_video(job_id: str, variant: str = "review"):
    if store is None:
        raise HTTPException(503, "سرویس آماده نیست")
    name = "review.mp4" if variant == "review" else "original.mp4"
    path = UPLOADS_DIR / job_id / name
    if not path.exists():
        raise HTTPException(404, "ویدیو یافت نشد")
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
