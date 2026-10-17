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
# Chunked / resumable upload (SPARSE byte-range protocol, multipart + raw)
# --------------------------------------------------------------------------- #
_OCTET = {"content-type": "application/octet-stream"}


def _chunk_multipart(client, job_id, offset, data, total=None):
    """Send one chunk exactly the way the browser does (multipart)."""
    files = {"blob": ("chunk", data)}
    fields = {"offset": str(offset)}
    if total is not None:
        fields["total_bytes"] = str(total)
    return client.post(f"/api/jobs/{job_id}/chunk", data=fields, files=files)


def _init(client, **over):
    fields = {
        "filename": "sample.mp4",
        "division": "m_18_34_rx",
        "wod_id": "wodx_ladder_wod1",
        "athlete_name": "chunk test",
        "claimed_reps": "10",
        "pose_source": "mock",
        "mock_block_scale": "0.15",
    }
    fields.update(over)
    return client.post("/api/jobs/init", data=fields)


def test_chunked_upload_flow(client, tiny_mp4):
    """Sparse protocol: out-of-order is ACCEPTED, duplicates are idempotent
    acks, complete verifies FULL coverage, reassembly is byte-identical."""
    from config.settings import UPLOADS_DIR
    data = tiny_mp4.read_bytes()
    r = _init(client, total_bytes=str(len(data)))
    assert r.status_code == 200, r.text
    init = r.json()
    job_id = init["job_id"]
    assert init["received"] == 0 and init["chunk_size"] > 0
    assert init.get("sparse") is True

    q1 = len(data) // 4
    q2 = q1 + (len(data) - q1) // 2

    # OUT-OF-ORDER: the tail chunk FIRST (sparse v2 — parallel streams)
    r = _chunk_multipart(client, job_id, q2, data[q2:], total=len(data))
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["covered"] == len(data) - q2
    assert j["accepted"] == len(data) - q2
    assert j["received"] == 0          # prefix still at zero (hole below)

    # premature complete → 400 (coverage incomplete: [q1..q2) missing)
    r = client.post(f"/api/jobs/{job_id}/complete")
    assert r.status_code == 400

    # middle chunk
    r = _chunk_multipart(client, job_id, q1, data[q1:q2])
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["received"] == 0          # STILL holed at the front
    assert j["covered"] == len(data) - q1

    # duplicate retry of the same range → idempotent, accepted == 0
    r = _chunk_multipart(client, job_id, q2, data[q2:], total=len(data))
    assert r.status_code == 200
    j = r.json()
    assert j["accepted"] == 0 and j.get("duplicate") is True

    # resume probe exposes ranges (client refills only the holes)
    r = client.get(f"/api/jobs/{job_id}/session")
    assert r.status_code == 200
    st = r.json()
    assert st["complete"] is False and st["registered"] is False
    assert st["covered"] == len(data) - q1
    assert st["sparse"] is True
    assert st["ranges"] == [[q1, len(data)]]

    # first chunk closes the last hole (raw octet-stream shape, like curl)
    r = client.post(f"/api/jobs/{job_id}/chunk", params={"offset": 0},
                    content=data[:q1], headers=_OCTET)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["received"] == len(data) and j["covered"] == len(data)

    r = client.post(f"/api/jobs/{job_id}/complete")
    assert r.status_code == 200, r.text
    assert r.json()["job_id"] == job_id

    assert not (UPLOADS_DIR / job_id / "session.json").exists()

    body = _wait_done(client, job_id)
    assert body["result"] is not None
    assert body["result"]["reconciliation"]["claimed_reps"] == 10
    # the reassembled file is byte-identical to the source
    assert (UPLOADS_DIR / job_id / "original.mp4").read_bytes() == data


def test_chunked_sparse_never_corrupts(client, tiny_mp4):
    """A buggy retry sending WRONG bytes at an already-covered offset must
    never corrupt the stored file (only missing sub-intervals are written)."""
    from config.settings import UPLOADS_DIR
    data = tiny_mp4.read_bytes()
    r = _init(client, total_bytes=str(len(data)))
    job_id = r.json()["job_id"]
    half = len(data) // 2

    assert _chunk_multipart(client, job_id, 0, data[:half]).status_code == 200
    # garbage "retry" over the covered range
    r = _chunk_multipart(client, job_id, 0, b"\xde\xad\xbe\xef" * (half // 4))
    assert r.status_code == 200 and r.json()["accepted"] == 0

    # a torn raw write appended garbage beyond covered ranges → ignored:
    # the next in-order chunk writes only the missing hole; complete trims
    part = UPLOADS_DIR / job_id / "original.mp4.part"
    with open(part, "ab") as f:
        f.write(b"\xde\xad\xbe\xef" * 100)
    r = client.post(f"/api/jobs/{job_id}/chunk", params={"offset": half},
                    content=data[half:], headers=_OCTET)
    assert r.status_code == 200, r.text
    assert r.json()["received"] == len(data)
    r = client.post(f"/api/jobs/{job_id}/complete")
    assert r.status_code == 200, r.text
    assert (UPLOADS_DIR / job_id / "original.mp4").read_bytes() == data


def test_five_stream_true_parallel_upload(client, tiny_mp4):
    """5 browser streams hit the chunk endpoint SIMULTANEOUSLY (one piece
    each, then round after round of chunks). Guards the
    buffering-outside-the-session-lock design: under real concurrency the
    endpoint must neither deadlock, drop bytes, nor corrupt the range
    bookkeeping — and the reassembled file must be byte-identical."""
    from concurrent.futures import ThreadPoolExecutor

    from config.settings import UPLOADS_DIR

    rng = __import__("random").Random(20261008)
    data = bytearray(rng.randbytes(3 * 1024 * 1024))   # 3 MB, incompressible
    data[0:8] = b"\x00\x00\x00\x18ftyp"             # plausible mp4 magic
    data = bytes(data)

    r = _init(client, filename="parallel.mp4", total_bytes=str(len(data)))
    assert r.status_code == 200, r.text
    job_id = r.json()["job_id"]

    n = 5
    piece = (len(data) + n - 1) // n
    pieces = [(i * piece, min((i + 1) * piece, len(data)))
              for i in range(n) if i * piece < len(data)]

    def stream(bounds):
        start, end = bounds
        off = start
        while off < end:
            want = min(256 * 1024, end - off)   # small chunks → many requests
            rr = _chunk_multipart(client, job_id, off,
                                  data[off:off + want], total=len(data))
            assert rr.status_code == 200, rr.text
            accepted = rr.json()["accepted"]
            assert accepted == want, (off, accepted, want)
            off += accepted
        return True

    with ThreadPoolExecutor(max_workers=n) as ex:
        assert all(ex.map(stream, pieces))

    r = client.get(f"/api/jobs/{job_id}/session")
    st = r.json()
    assert st["covered"] == len(data) and st["received"] == len(data)
    assert st["ranges"] == [[0, len(data)]]

    r = client.post(f"/api/jobs/{job_id}/complete")
    assert r.status_code == 200, r.text
    stored = (UPLOADS_DIR / job_id / "original.mp4").read_bytes()
    assert stored == data, "parallel reassembly must be byte-identical"


def test_retry_failed_job_without_reupload(client, tiny_mp4):
    """retry re-queues a FAILED job whose video is still on the server —
    the exact recovery path for transient analysis failures (e.g. a wiped
    venv). No re-upload; 409 when the job is not failed."""
    r = _init(client, claimed_reps="5")
    job_id = r.json()["job_id"]
    data = tiny_mp4.read_bytes()
    assert _chunk_multipart(client, job_id, 0, data, total=len(data)).status_code == 200
    assert client.post(f"/api/jobs/{job_id}/complete").status_code == 200
    _wait_done(client, job_id)

    # a DONE job cannot be retried
    r = client.post(f"/api/jobs/{job_id}/retry")
    assert r.status_code == 409

    # force-fail the job row, then retry → re-queued → done again
    import main as main_mod
    main_mod.store.fail(job_id, "خطای تست", "test failure")
    r = client.post(f"/api/jobs/{job_id}/retry")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "queued"
    body = _wait_done(client, job_id)
    assert body["job"]["status"] == "done"
    # unknown job → 404
    assert client.post("/api/jobs/does-not-exist/retry").status_code == 404


def test_reanalyze_with_manual_start_without_reupload(client, tiny_mp4):
    """reanalyze re-runs a DONE job with a manual WOD-start override — the
    exact recovery path for SYS_START_NOT_FOUND videos: the user supplies
    the start timecode from the results page, no re-upload, and the new
    analysis reports start method 'manual' with the cap clock running from
    the correct t_start."""
    r = _init(client, claimed_reps="5")
    job_id = r.json()["job_id"]
    data = tiny_mp4.read_bytes()
    assert _chunk_multipart(client, job_id, 0, data, total=len(data)).status_code == 200
    assert client.post(f"/api/jobs/{job_id}/complete").status_code == 200
    body = _wait_done(client, job_id)
    assert body["result"]["start_detection"]["method"] == "mock"

    # reanalyze with a manual start → re-queued → done with method=manual
    r = client.post(f"/api/jobs/{job_id}/reanalyze",
                    json={"manual_start_sec": 12.5})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "queued"
    assert r.json()["meta_patch"] == {"manual_start_sec": 12.5}
    body = _wait_done(client, job_id)
    assert body["job"]["status"] == "done"
    sd = body["result"]["start_detection"]
    assert sd["method"] == "manual" and sd["t_start_sec"] == 12.5

    # validation: negative or non-numeric start → 400
    r = client.post(f"/api/jobs/{job_id}/reanalyze", json={"manual_start_sec": -3})
    assert r.status_code == 400
    r = client.post(f"/api/jobs/{job_id}/reanalyze", json={"manual_start_sec": "abc"})
    assert r.status_code == 400
    # unknown job → 404
    assert client.post("/api/jobs/does-not-exist/reanalyze",
                       json={"manual_start_sec": 1}).status_code == 404
    # a QUEUED job cannot be re-analyzed (409)
    r = _init(client, claimed_reps="5")
    j2 = r.json()["job_id"]
    d2 = tiny_mp4.read_bytes()
    _chunk_multipart(client, j2, 0, d2, total=len(d2))
    client.post(f"/api/jobs/{j2}/complete")
    r = client.post(f"/api/jobs/{j2}/reanalyze", json={"manual_start_sec": 5})
    assert r.status_code in (200, 409)   # may already be running/done — 409 while queued


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
