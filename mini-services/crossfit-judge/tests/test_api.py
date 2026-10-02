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
