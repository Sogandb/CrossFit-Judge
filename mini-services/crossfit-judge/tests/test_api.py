"""End-to-end API tests: upload (mock pose source) → poll → result."""
from __future__ import annotations

import subprocess
import tempfile
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def tiny_mp4(tmp_path_factory) -> Path:
    """A 4-second black mp4 with a sine audio track (mock mode ignores it,
    but the extension and container must be valid)."""
    p = tmp_path_factory.mktemp("media") / "sample.mp4"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=4:r=30",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
         "-c:v", "libx264", "-preset", "ultrafast",
         "-c:a", "aac", "-shortest", str(p)],
        check=True, capture_output=True)
    return p


def _wait_done(client, job_id, timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = client.get(f"/api/jobs/{job_id}")
        assert r.status_code == 200, r.text
        body = r.json()
        status = body["job"]["status"]
        if status == "done":
            return body
        if status == "failed":
            raise AssertionError(f"job failed: {body['job']['error_fa']}")
        time.sleep(0.5)
    raise AssertionError("job did not finish in time")


def test_health_and_catalog(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["ok"]
    r = client.get("/api/wods")
    assert r.status_code == 200
    wods = r.json()["wods"]
    assert any(w["wod_id"] == "wodx_ladder_wod1" for w in wods)
    r = client.get("/api/divisions")
    assert r.status_code == 200
    grouped = r.json()["grouped"]
    total = sum(len(v) for v in grouped.values())
    assert total == 32, total


def test_full_mock_pipeline(client, tiny_mp4):
    with open(tiny_mp4, "rb") as f:
        r = client.post(
            "/api/jobs",
            data={
                "wod_id": "wodx_ladder_wod1",
                "division": "m_18_34_rx",
                "athlete_name": "تست ورزشکار",
                "claimed_reps": "10",
                "claimed_time_min": "4",
                "claimed_time_sec": "30",
                "pose_source": "mock",
                "mock_block_scale": "0.15",
                "mock_lead_in_sec": "6",
            },
            files={"video": ("sample.mp4", f, "video/mp4")},
        )
    assert r.status_code == 200, r.text
    job_id = r.json()["job_id"]

    body = _wait_done(client, job_id)
    result = body["result"]
    assert result is not None
    # score structure
    assert result["summary"]["total_prescribed"] > 0
    assert result["reconciliation"]["claimed_reps"] == 10
    assert result["score_display"]["score"]
    assert result["start_detection"]["method"] == "mock"
    # Persian no-rep reasons are present for any no-rep event
    for ev in result["events"]:
        if ev["outcome"] == "no_rep":
            assert ev["reason_fa"], ev
            assert ev["reason_code"] in ("THR_DEPTH", "THR_LOCKOUT", "THR_BAR_NOT_OVERHEAD",
                                         "THR_NOT_CONTINUOUS", "THR_WALKING", "THR_LOW_VIS",
                                         "BFB_CHEST", "BFB_NOT_FACING", "BFB_ONE_FOOT_LANDING",
                                         "BFB_TRAILING_FOOT", "BFB_INCOMPLETE_CROSS",
                                         "BFB_LOW_VIS")
    # blocks breakdown is present and in Persian
    assert len(result["summary"]["blocks"]) == 12
    assert result["summary"]["blocks"][0]["movement_fa"] == "تراستر"


def test_invalid_division_rejected(client, tiny_mp4):
    with open(tiny_mp4, "rb") as f:
        r = client.post(
            "/api/jobs",
            data={"division": "nonexistent", "wod_id": "wodx_ladder_wod1"},
            files={"video": ("sample.mp4", f, "video/mp4")},
        )
    assert r.status_code == 422


def test_history(client):
    r = client.get("/api/jobs")
    assert r.status_code == 200
    jobs = r.json()["jobs"]
    assert isinstance(jobs, list) and len(jobs) >= 1


# --------------------------------------------------------------------------- #
# Chunked / resumable upload
# --------------------------------------------------------------------------- #
_OCTET = {"content-type": "application/octet-stream"}


def test_chunked_upload_flow(client, tiny_mp4):
    from config.settings import UPLOADS_DIR
    data = tiny_mp4.read_bytes()
    r = client.post("/api/jobs/init", data={
        "filename": "sample.mp4",
        "total_bytes": str(len(data)),
        "division": "m_18_34_rx",
        "wod_id": "wodx_ladder_wod1",
        "athlete_name": "chunk test",
        "claimed_reps": "10",
        "pose_source": "mock",
        "mock_block_scale": "0.15",
    })
    assert r.status_code == 200, r.text
    init = r.json()
    job_id = init["job_id"]
    assert init["expected_index"] == 0 and init["chunk_size"] > 0

    # out-of-order chunk (index 1 before 0) → 409 + expected_index
    r = client.post(f"/api/jobs/{job_id}/chunk", params={"index": 1, "total": 2},
                    content=data[:10], headers=_OCTET)
    assert r.status_code == 409
    assert r.json()["expected_index"] == 0

    half = len(data) // 2
    r = client.post(f"/api/jobs/{job_id}/chunk", params={"index": 0, "total": 2},
                    content=data[:half], headers=_OCTET)
    assert r.status_code == 200, r.text
    assert r.json()["received"] == half

    # retried duplicate of chunk 0 → idempotent ack, no extra bytes
    r = client.post(f"/api/jobs/{job_id}/chunk", params={"index": 0, "total": 2},
                    content=data[:half], headers=_OCTET)
    assert r.status_code == 200 and r.json().get("duplicate") is True
    assert r.json()["received"] == half

    # premature complete → 400 (missing bytes)
    r = client.post(f"/api/jobs/{job_id}/complete")
    assert r.status_code == 400

    # resume probe reflects the session state
    r = client.get(f"/api/jobs/{job_id}/session")
    assert r.status_code == 200
    st = r.json()
    assert st["complete"] is False and st["registered"] is False
    assert st["expected_index"] == 1 and st["received"] == half

    r = client.post(f"/api/jobs/{job_id}/chunk", params={"index": 1, "total": 2},
                    content=data[half:], headers=_OCTET)
    assert r.status_code == 200, r.text
    assert r.json()["received"] == len(data)

    r = client.post(f"/api/jobs/{job_id}/complete")
    assert r.status_code == 200, r.text
    assert r.json()["job_id"] == job_id

    # session file removed after completion
    assert not (UPLOADS_DIR / job_id / "session.json").exists()

    body = _wait_done(client, job_id)
    assert body["result"] is not None
    assert body["result"]["reconciliation"]["claimed_reps"] == 10
    # the reassembled file is byte-identical to the source
    assert (UPLOADS_DIR / job_id / "original.mp4").read_bytes() == data


def test_chunked_init_validation(client):
    r = client.post("/api/jobs/init",
                    data={"filename": "clip.avi", "division": "m_18_34_rx"})
    assert r.status_code == 415
    r = client.post("/api/jobs/init",
                    data={"filename": "clip.mp4", "division": "nonexistent"})
    assert r.status_code == 422
    r = client.post("/api/jobs/init", data={
        "filename": "clip.mp4", "division": "m_18_34_rx",
        "total_bytes": str(999 * 1024 ** 3)})
    assert r.status_code == 413
    # unknown session → 404 everywhere
    r = client.get("/api/jobs/does-not-exist/session")
    assert r.status_code == 404
    r = client.post("/api/jobs/does-not-exist/chunk", params={"index": 0, "total": 1},
                    content=b"x", headers=_OCTET)
    assert r.status_code == 404
    r = client.post("/api/jobs/does-not-exist/complete")
    assert r.status_code == 404
