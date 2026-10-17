"""
Job store + bounded worker pool.

Fixes the v1 processing-queue flaws (unlimited concurrency, 300 s subprocess
timeout): the analyzer runs IN-PROCESS inside a ThreadPoolExecutor with a
hard-bounded worker count; per-job progress is written to SQLite so the UI
can poll it. Job artifacts live in data/uploads/<job_id>/.
"""
from __future__ import annotations

import json
import queue
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

from config.settings import (
    DB_PATH,
    STATE_DIR,
    UPLOADS_DIR,
    WORKER_CONCURRENCY,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    status TEXT NOT NULL,          -- queued|running|done|failed
    stage TEXT NOT NULL DEFAULT '',
    progress REAL NOT NULL DEFAULT 0,
    error_fa TEXT,
    error_en TEXT,
    meta_json TEXT NOT NULL,
    result_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at DESC);
"""

# Stage keys → bilingual labels. The `stage` column stores the KEY so the
# web UI can render either language (English by default).
STAGES = {
    "queued":          {"fa": "در صف پردازش",                "en": "Queued"},
    "validate":        {"fa": "اعتبارسنجی ویدیو",            "en": "Validating video"},
    "start_detect":    {"fa": "تشخیص لحظه شروع (بوق ۳+۱)",    "en": "Detecting workout start (3+1 beeps)"},
    "calibration":     {"fa": "کالیبراسیون صحنه",            "en": "Calibrating scene"},
    "waiting_athlete": {"fa": "در انتظار شناسایی ورزشکار…",  "en": "Waiting for athlete detection…"},
    "analyzing":       {"fa": "تحلیل فریم‌ها",                "en": "Analyzing frames"},
    "scoring":         {"fa": "امتیازدهی و تطبیق",            "en": "Scoring & reconciliation"},
    "review_video":    {"fa": "ساخت ویدیوی بازبینی",          "en": "Building review video"},
    "running":         {"fa": "در حال پردازش",                "en": "Processing"},
    "done":            {"fa": "تکمیل شد",                     "en": "Completed"},
    "failed":          {"fa": "خطا",                          "en": "Failed"},
}


def _stage_view(raw: str) -> dict:
    """stage column value → {stage_key, stage_fa, stage_en}. Legacy rows
    (created before stage keys) hold Persian free text — passthrough as fa."""
    if raw in STAGES:
        return {"stage_key": raw,
                "stage_fa": STAGES[raw]["fa"],
                "stage_en": STAGES[raw]["en"]}
    return {"stage_key": "legacy", "stage_fa": raw or "", "stage_en": ""}


class JobStore:
    def __init__(self) -> None:
        UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(SCHEMA)
        # migration for DBs created before the bilingual error columns
        try:
            self._db.execute("ALTER TABLE jobs ADD COLUMN error_en TEXT")
        except sqlite3.OperationalError:
            pass  # column already exists
        self._db.commit()
        # worker pool
        self._q: "queue.Queue[Optional[str]]" = queue.Queue()
        self._workers = []
        for i in range(max(1, WORKER_CONCURRENCY)):
            th = threading.Thread(target=self._worker, name=f"judge-worker-{i}",
                                  daemon=True)
            th.start()
            self._workers.append(th)
        self._recover_orphans()

    def _recover_orphans(self) -> None:
        """Crash recovery at startup — an engine restart (platform reset,
        crash, deploy) must never leave finished work broken or in-flight
        work stuck forever:
          * done + review_video "pending"  → the async review renderer died
            with the old process → re-kick it now (idempotent: the annotator
            re-renders from the stored result).
          * queued/running → the analysis itself was killed mid-run → re-queue
            the whole analysis (the uploaded video is still on disk).
        """
        try:
            rows = self._db.execute(
                "SELECT id, status, result_json FROM jobs "
                "WHERE status IN ('queued', 'running', 'done')").fetchall()
        except sqlite3.OperationalError:
            return
        for job_id, status, result_json in rows:
            updir = UPLOADS_DIR / job_id
            has_video = (updir / "original.mp4").exists()
            if status == "done":
                try:
                    result = json.loads(result_json or "{}")
                except (ValueError, TypeError):
                    continue
                if result.get("review_video") != "pending":
                    continue
                if not has_video:
                    self.patch_result(job_id, {
                        "review_video": False,
                        "review_video_error": "original video missing"})
                    continue
                th = threading.Thread(
                    target=self._render_review,
                    name=f"review-recovery-{job_id}",
                    args=(job_id, str(updir / "original.mp4"),
                          str(updir / "review.mp4"), result),
                    daemon=True)
                th.start()
            elif has_video:
                # killed mid-analysis → restart it from scratch
                self._update(job_id, status="queued", stage="queued",
                             progress=0.0, error_fa=None, error_en=None,
                             result_json=None)
                self._q.put(job_id)
            else:
                self.fail(job_id,
                          "فایل ویدیو یافت نشد (بازیابی پس از راه‌اندازی مجدد)",
                          "Video file missing (post-restart recovery)")

    # ------------------------------------------------------------------ #
    # CRUD
    # ------------------------------------------------------------------ #
    def create(self, meta: dict, video_path: str, review_path: str) -> str:
        job_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
        return self.create_with_id(job_id, meta, video_path, review_path)

    def create_with_id(self, job_id: str, meta: dict, video_path: str,
                        review_path: str) -> str:
        with self._lock:
            self._db.execute(
                "INSERT INTO jobs (id, created_at, status, stage, progress, meta_json) "
                "VALUES (?, ?, 'queued', ?, 0, ?)",
                (job_id, time.time(), "queued", json.dumps(meta, ensure_ascii=False)),
            )
            self._db.commit()
        self._q.put(job_id)
        return job_id

    _JOB_COLS = "id, created_at, status, stage, progress, error_fa, error_en, meta_json"

    def purge_older_than(self, days: float) -> int:
        """Retention janitor: delete finished/failed jobs (DB row + upload dir
        with the 500 MB source video and review video) older than `days`.
        Running/queued jobs are never touched. Returns the number purged."""
        if days <= 0:
            return 0
        import shutil as _sh
        import time as _t
        cutoff = _t.time() - days * 86400.0
        with self._lock:
            rows = self._db.execute(
                "SELECT id FROM jobs WHERE status IN ('done','failed') AND created_at < ?",
                (cutoff,)).fetchall()
            ids = [r[0] for r in rows]
            for jid in ids:
                self._db.execute("DELETE FROM jobs WHERE id = ?", (jid,))
            self._db.commit()
        for jid in ids:
            _sh.rmtree(UPLOADS_DIR / jid, ignore_errors=True)
        return len(ids)

    def get(self, job_id: str) -> Optional[dict]:
        with self._lock:
            row = self._db.execute(
                f"SELECT {self._JOB_COLS} FROM jobs WHERE id = ?",
                (job_id,)).fetchone()
        if not row:
            return None
        stage = _stage_view(row[3])
        return {
            "id": row[0], "created_at": row[1], "status": row[2],
            **stage, "progress": row[4],
            "error_fa": row[5], "error_en": row[6],
            "meta": json.loads(row[7] or "{}"),
        }

    def get_result(self, job_id: str) -> Optional[dict]:
        with self._lock:
            row = self._db.execute(
                "SELECT result_json FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if not row or not row[0]:
            return None
        return json.loads(row[0])

    def list(self, limit: int = 50) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                f"SELECT {self._JOB_COLS} FROM jobs "
                "ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        out = []
        for row in rows:
            meta = json.loads(row[7] or "{}")
            stage = _stage_view(row[3])
            out.append({
                "id": row[0], "created_at": row[1], "status": row[2],
                **stage, "progress": row[4],
                "error_fa": row[5], "error_en": row[6],
                "athlete_name": meta.get("athlete_name") or "",
                "division": meta.get("division") or "",
                "wod_id": meta.get("wod_id") or "",
            })
        return out

    def _update(self, job_id: str, **fields) -> None:
        cols, vals = [], []
        for k, v in fields.items():
            cols.append(f"{k} = ?")
            vals.append(v)
        vals.append(job_id)
        with self._lock:
            self._db.execute(f"UPDATE jobs SET {', '.join(cols)} WHERE id = ?", vals)
            self._db.commit()

    def set_stage(self, job_id: str, stage_key: str, progress: float) -> None:
        self._update(job_id, status="running", stage=stage_key,
                     progress=max(0.0, min(100.0, progress)))

    def finish(self, job_id: str, result: dict) -> None:
        self._update(job_id, status="done", stage="done", progress=100,
                     result_json=json.dumps(result, ensure_ascii=False))

    def patch_result(self, job_id: str, patch: dict) -> None:
        """Merge keys into an existing result (used by the async review-video
        renderer: the result goes out immediately with review_video="pending"
        and is patched to True/False once background rendering finishes)."""
        with self._lock:
            row = self._db.execute(
                "SELECT result_json FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if not row or not row[0]:
                return
            result = json.loads(row[0])
            result.update(patch)
            self._db.execute(
                "UPDATE jobs SET result_json = ? WHERE id = ?",
                (json.dumps(result, ensure_ascii=False), job_id))
            self._db.commit()

    def fail(self, job_id: str, error_fa: str, error_en: Optional[str] = None) -> None:
        self._update(job_id, status="failed", stage="failed",
                     error_fa=error_fa, error_en=error_en)

    def retry(self, job_id: str) -> bool:
        """Re-queue a FAILED job for analysis — the video is already on the
        server, so a transient failure (e.g. an environment hiccup) never
        costs the athlete another upload. Returns False when the job cannot
        be retried (missing, not failed, or video deleted)."""
        job = self.get(job_id)
        if job is None or job["status"] != "failed":
            return False
        if not (UPLOADS_DIR / job_id / "original.mp4").exists():
            return False
        self._update(job_id, status="queued", stage="queued", progress=0.0,
                     error_fa=None, error_en=None, result_json=None)
        self._q.put(job_id)
        return True

    def reanalyze(self, job_id: str, meta_patch: Optional[dict] = None) -> bool:
        """Re-run the analysis of a DONE or FAILED job with updated meta
        (e.g. a manual WOD start time) — WITHOUT re-uploading the video.

        The primary use case: the beep start-detection failed
        (SYS_START_NOT_FOUND), so the user supplies the real workout-start
        timecode from the results page and the whole judging is re-run with
        a known t_start (cap clock, preroll calibration, warmup exclusion).
        """
        job = self.get(job_id)
        if job is None or job["status"] not in ("done", "failed"):
            return False
        if not (UPLOADS_DIR / job_id / "original.mp4").exists():
            return False
        meta = dict(job["meta"])
        if meta_patch:
            meta.update(meta_patch)
        with self._lock:
            self._db.execute(
                "UPDATE jobs SET status='queued', stage='queued', progress=0, "
                "error_fa=NULL, error_en=NULL, result_json=NULL, meta_json=? "
                "WHERE id = ?",
                (json.dumps(meta, ensure_ascii=False), job_id))
            self._db.commit()
        self._q.put(job_id)
        return True

    # ------------------------------------------------------------------ #
    # Worker
    # ------------------------------------------------------------------ #
    def _worker(self) -> None:
        while True:
            job_id = self._q.get()
            if job_id is None:
                return
            try:
                self._run_job(job_id)
            except Exception as e:  # noqa: BLE001
                import traceback
                traceback.print_exc()
                self.fail(job_id, f"خطای غیرمنتظره: {e}", f"Unexpected error: {e}")

    def _run_job(self, job_id: str) -> None:
        job = self.get(job_id)
        if job is None:
            return
        meta = job["meta"]
        wod = self._load_wod(meta.get("wod_id"))
        if wod is None:
            self.fail(job_id, "واد مورد نظر یافت نشد", "Workout not found")
            return
        updir = UPLOADS_DIR / job_id
        video_path = str(updir / "original.mp4")
        review_path = str(updir / "review.mp4")
        from core.analyzer import Analyzer  # late import (heavy deps)

        def progress(stage: str, pct: float) -> None:
            self.set_stage(job_id, stage, pct)

        job_doc = {"video_path": video_path, "review_path": review_path,
                   "wod": wod, "meta": meta}
        outcome = Analyzer(job_doc, progress).run()
        if outcome.ok:
            self.finish(job_id, outcome.result)
            # Async review video: the result is already final and visible;
            # the annotated render happens in the background and patches
            # review_video: "pending" → True/False when done (the UI polls).
            if outcome.result.get("review_video") == "pending":
                th = threading.Thread(
                    target=self._render_review, name=f"review-{job_id}",
                    args=(job_id, video_path, review_path,
                          dict(outcome.result)), daemon=True)
                th.start()
        else:
            self.fail(job_id, outcome.error_fa or "خطای نامشخص",
                      outcome.error_en or "Unknown error")

    def _render_review(self, job_id: str, video_path: str,
                       review_path: str, result: dict) -> None:
        import traceback
        try:
            from reporting.video_annotator import annotate_video
            annotate_video(video_path, review_path, result)
            self.patch_result(job_id, {"review_video": True})
        except Exception as e:  # noqa: BLE001 — non-fatal
            traceback.print_exc()
            self.patch_result(job_id, {"review_video": False,
                                       "review_video_error": str(e)})

    @staticmethod
    def _load_wod(wod_id: Optional[str]) -> Optional[dict]:
        from config.settings import WODS_DIR
        if not wod_id:
            wod_id = "wodx_ladder_wod1"
        path = Path(WODS_DIR) / f"{wod_id}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
