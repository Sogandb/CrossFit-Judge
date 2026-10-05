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
# Chunked / resumable upload (byte-offset protocol, multipart + raw)
# --------------------------------------------------------------------------- #
_OCTET = {"content-type": "application/octet-stream"}


def _chunk_multipart(client, job_id, offset, data, total=None):
    """Send one chunk exactly the way the browser does (multipart)."""
    files = {"blob": ("chunk", data)}
    fields = {"offset": str(offset)}
    if total is not None:
        fields["total_bytes"] = str(total)
    return client.post(f"/api/jobs/{job_id}/chunk", data=fields, files=files)


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
    assert init["received"] == 0 and init["chunk_size"] > 0

    # gap: chunk that starts beyond received → 409 + server truth
    r = _chunk_multipart(client, job_id, 100, data[:10])
    assert r.status_code == 409
    assert r.json()["received"] == 0

    # mixed variable sizes: quarter → half of the remainder → rest
    q1 = len(data) // 4
    r = _chunk_multipart(client, job_id, 0, data[:q1], total=len(data))
    assert r.status_code == 200, r.text
    assert r.json()["received"] == q1

    # retried duplicate (same offset) → idempotent ack, no extra bytes
    r = _chunk_multipart(client, job_id, 0, data[:q1], total=len(data))
    assert r.status_code == 200 and r.json().get("duplicate") is True
    assert r.json()["received"] == q1

    # overlapping retry (older offset) → still idempotent
    r = _chunk_multipart(client, job_id, q1 // 2, data[:8])
    assert r.status_code == 200 and r.json().get("duplicate") is True
    assert r.json()["received"] == q1

    # premature complete → 400 (missing bytes)
    r = client.post(f"/api/jobs/{job_id}/complete")
    assert r.status_code == 400

    # resume probe reflects the session state
    r = client.get(f"/api/jobs/{job_id}/session")
    assert r.status_code == 200
    st = r.json()
    assert st["complete"] is False and st["registered"] is False
    assert st["received"] == q1 and st["total_bytes"] == len(data)

    # second chunk — different size (protocol allows per-request sizes)
    q2 = q1 + (len(data) - q1) // 2
    r = _chunk_multipart(client, job_id, q1, data[q1:q2])
    assert r.status_code == 200, r.text
    assert r.json()["received"] == q2

    # raw octet-stream shape (curl / scripts) also works
    r = client.post(f"/api/jobs/{job_id}/chunk", params={"offset": q2},
                    content=data[q2:], headers=_OCTET)
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


def test_chunked_partial_write_rollback(client, tiny_mp4):
    """A raw attempt that dies mid-write must not corrupt the stream: the
    next chunk truncates back to the acknowledged size."""
    from config.settings import UPLOADS_DIR
    data = tiny_mp4.read_bytes()
    r = client.post("/api/jobs/init", data={
        "filename": "sample.mp4", "total_bytes": str(len(data)),
        "division": "m_18_34_rx", "claimed_reps": "10",
        "pose_source": "mock", "mock_block_scale": "0.15",
    })
    assert r.status_code == 200, r.text
    job_id = r.json()["job_id"]

    half = len(data) // 2
    assert _chunk_multipart(client, job_id, 0, data[:half]).status_code == 200

    # simulate a torn raw write: garbage appended beyond `received`
    part = UPLOADS_DIR / job_id / "original.mp4.part"
    with open(part, "ab") as f:
        f.write(b"\xde\xad\xbe\xef" * 100)

    # next chunk at the server-truth offset → truncates the garbage first
    r = client.post(f"/api/jobs/{job_id}/chunk", params={"offset": half},
                    content=data[half:], headers=_OCTET)
    assert r.status_code == 200, r.text
    assert r.json()["received"] == len(data)

    r = client.post(f"/api/jobs/{job_id}/complete")
    assert r.status_code == 200, r.text
    assert (UPLOADS_DIR / job_id / "original.mp4").read_bytes() == data


def test_chunked_protocol_validation(client):
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
    r = client.post("/api/jobs/does-not-exist/chunk",
                    params={"offset": 0}, content=b"x", headers=_OCTET)
    assert r.status_code == 404
    r = client.post("/api/jobs/does-not-exist/complete")
    assert r.status_code == 404

    # known session, malformed requests
    r = client.post("/api/jobs/init",
                    data={"filename": "clip.mp4", "division": "m_18_34_rx"})
    assert r.status_code == 200, r.text
    job_id = r.json()["job_id"]
    # raw without offset → 422
    r = client.post(f"/api/jobs/{job_id}/chunk", content=b"x", headers=_OCTET)
    assert r.status_code == 422
    # multipart without the blob file part → 422
    r = client.post(f"/api/jobs/{job_id}/chunk",
                    data={"offset": "0"})
    assert r.status_code == 422
    # multipart with a non-integer offset → 422
    r = client.post(f"/api/jobs/{job_id}/chunk", data={"offset": "abc"},
                    files={"blob": ("c", b"x")})
    assert r.status_code == 422
    # negative offset → 422
    r = client.post(f"/api/jobs/{job_id}/chunk", params={"offset": -3},
                    content=b"x", headers=_OCTET)
    assert r.status_code == 422
