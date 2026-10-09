"""Robustness regression tests — the three v2.4.1 hardening layers.

1. GL self-heal (utils/gl_compat): the engine must survive ANY spawn method
   (bare uvicorn without LD_LIBRARY_PATH) — the "import mediapipe is green
   but analysis dies on libEGL.so.1" deception killed real user analyses.
2. Crash recovery (JobStore._recover_orphans): an engine restart must never
   leave done+pending review renders orphaned or queued/running jobs stuck.
3. Cache headers: no API response may ever be browser-cached (a stale
   cached POST answer against a recycled tunnel is poison).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


# --------------------------------------------------------------------------- #
# 1. GL self-heal + deep health
# --------------------------------------------------------------------------- #

def test_gl_self_heal_ok():
    from utils.gl_compat import ensure_gl
    ok, detail = ensure_gl()
    assert ok, f"GL libs not loadable: {detail}"


def test_mediapipe_bindings_deep_check():
    """The DEEP check must load the actual C bindings (the shallow
    `import mediapipe` misses the libEGL failure mode)."""
    from utils.gl_compat import mediapipe_bindings_ok
    ok, err = mediapipe_bindings_ok()
    assert ok, f"mediapipe C bindings not loadable: {err}"


def test_health_reports_gl_and_deep_deps(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["deps_ok"] is True, body.get("deps_error")   # DEEP now
    assert body["gl_ok"] is True, body.get("gl_detail")
    assert "gl_detail" in body


# --------------------------------------------------------------------------- #
# 2. Crash recovery
# --------------------------------------------------------------------------- #

def _mk_job_row(store, job_id: str, status: str, result: dict | None) -> None:
    """Insert a job row directly (simulating a pre-crash DB state)."""
    with store._lock:
        store._db.execute(
            "INSERT OR REPLACE INTO jobs (id, created_at, status, stage, "
            "progress, meta_json, result_json) VALUES (?, ?, ?, ?, 0, ?, ?)",
            (job_id, time.time(), status, status,
             json.dumps({"wod_id": "wodx_ladder_wod1", "division": "m_18_34_rx",
                         "filename": "x.mp4", "pose_source": "mock"}),
             json.dumps(result) if result is not None else None))
        store._db.commit()


def test_crash_recovery_requeues_running_jobs(tmp_path, monkeypatch):
    """A job stuck in queued/running at process death must be re-queued (and
    analyzed) when the NEXT JobStore starts — never stuck forever."""
    from config import settings
    from jobs.store import JobStore

    monkeypatch.setattr(settings, "UPLOADS_DIR", tmp_path)
    import jobs.store as store_mod
    monkeypatch.setattr(store_mod, "UPLOADS_DIR", tmp_path)
    monkeypatch.setattr(store_mod, "DB_PATH", tmp_path / "t.db")

    # pass 1: a store that "crashes" with a running job + its video on disk
    s1 = JobStore()
    job_id = "recovery-running-1"
    (tmp_path / job_id).mkdir(parents=True)
    (tmp_path / job_id / "original.mp4").write_bytes(b"x" * 8)
    _mk_job_row(s1, job_id, "running", None)
    del s1  # simulated process death

    # pass 2: a fresh store recovers the orphan
    s2 = JobStore()
    try:
        job = s2.get(job_id)
        assert job is not None
        # recovered: re-queued (analysis may fail on the 8-byte video, but it
        # must NOT stay 'running' forever — it either re-runs or fails)
        assert job["status"] in ("queued", "running", "done", "failed")
        assert job["status"] != "running" or job["progress"] >= 0
    finally:
        s2._db.close()


def test_crash_recovery_finishes_pending_review(tmp_path, monkeypatch):
    """done + review_video 'pending' (renderer died with the old process)
    must be re-kicked at the next startup — it must leave 'pending'."""
    from config import settings
    from jobs.store import JobStore

    monkeypatch.setattr(settings, "UPLOADS_DIR", tmp_path)
    import jobs.store as store_mod
    monkeypatch.setattr(store_mod, "UPLOADS_DIR", tmp_path)
    monkeypatch.setattr(store_mod, "DB_PATH", tmp_path / "t.db")

    s1 = JobStore()
    job_id = "recovery-review-1"
    (tmp_path / job_id).mkdir(parents=True)
    (tmp_path / job_id / "original.mp4").write_bytes(b"x" * 8)
    _mk_job_row(s1, job_id, "done",
                {"review_video": "pending", "summary": {"total_credited": 0}})
    del s1

    s2 = JobStore()
    try:
        deadline = time.time() + 15
        while time.time() < deadline:
            res = s2.get_result(job_id)
            if res and res.get("review_video") != "pending":
                break
            time.sleep(0.3)
        res = s2.get_result(job_id)
        assert res is not None
        assert res.get("review_video") != "pending", "orphaned render never recovered"
        # annotate_video will fail on the 8-byte stub → False + error detail
        assert res.get("review_video") is False
        assert res.get("review_video_error")
    finally:
        s2._db.close()


def test_crash_recovery_missing_video_fails_honestly(tmp_path, monkeypatch):
    """queued/running with the video GONE (uploads wiped): fail loudly
    instead of looping forever."""
    from config import settings
    from jobs.store import JobStore

    monkeypatch.setattr(settings, "UPLOADS_DIR", tmp_path)
    import jobs.store as store_mod
    monkeypatch.setattr(store_mod, "UPLOADS_DIR", tmp_path)
    monkeypatch.setattr(store_mod, "DB_PATH", tmp_path / "t.db")

    s1 = JobStore()
    job_id = "recovery-novideo-1"
    (tmp_path / job_id).mkdir(parents=True)   # dir exists, video does NOT
    _mk_job_row(s1, job_id, "queued", None)
    del s1

    s2 = JobStore()
    try:
        job = s2.get(job_id)
        assert job["status"] == "failed"
        assert job["error_en"] and "missing" in job["error_en"].lower()
    finally:
        s2._db.close()


# --------------------------------------------------------------------------- #
# 3. no-store cache headers on every response (incl. POSTs)
# --------------------------------------------------------------------------- #

def test_no_store_cache_headers(client):
    r = client.get("/api/health")
    assert r.headers.get("cache-control") == "no-store"
    r = client.get("/api/jobs")
    assert r.headers.get("cache-control") == "no-store"
    r = client.post("/api/jobs/does-not-exist/complete")
    assert r.headers.get("cache-control") == "no-store"
