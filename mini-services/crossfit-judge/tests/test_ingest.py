"""Upload gates with REAL videos: readable, 480p+, <= 15 min, <= 500 MB,
rotation-aware geometry, missing-ffmpeg message. (pose_source is NOT mock, so
the authoritative early validation runs.)"""
from __future__ import annotations

import subprocess

import pytest
from fastapi.testclient import TestClient

from main import app
from config.settings import MAX_UPLOAD_BYTES
from core.frame_source import FrameSource, probe
from ingest.validate import validate_video


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _no_real_jobs(monkeypatch, client):
    """Validation is under test, not analysis: don't queue real jobs (they would
    occupy the single worker and slow unrelated tests)."""
    import main
    monkeypatch.setattr(main.store, "create_with_id",
                        lambda jid, meta, vp, rp: jid)


def _mk(path, secs, size="854x480", fps=5, extra=()):
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", f"testsrc=s={size}:d={secs}:r={fps}",
         *extra, "-c:v", "libx264", "-preset", "ultrafast", "-crf", "35",
         "-pix_fmt", "yuv420p", str(path)], check=True, capture_output=True)
    return path


def _upload(client, path, name="clip.mp4"):
    data = path.read_bytes()
    r = client.post("/api/jobs/init", data={
        "filename": name, "total_bytes": str(len(data)),
        "division": "m_18_34_rx", "wod_id": "wodx_ladder_wod1"})
    assert r.status_code == 200, r.text
    jid = r.json()["job_id"]
    cs = 1024 * 1024
    for off in range(0, len(data), cs):
        rr = client.post(f"/api/jobs/{jid}/chunk",
                         data={"offset": str(off)},
                         files={"blob": ("c", data[off:off + cs])})
        assert rr.status_code == 200, rr.text
    return client.post(f"/api/jobs/{jid}/complete")


def test_good_video_upload_completes(client, tmp_path):
    r = _upload(client, _mk(tmp_path / "ok.mp4", 90))
    assert r.status_code == 200, r.text and r.json()["job_id"]


def test_exactly_15_minutes_is_accepted(client, tmp_path):
    r = _upload(client, _mk(tmp_path / "f15.mp4", 900))
    assert r.status_code == 200, r.text


def test_over_15_minutes_rejected_at_upload(client, tmp_path):
    r = _upload(client, _mk(tmp_path / "long.mp4", 960))
    assert r.status_code == 422
    assert "exceeds" in r.json()["detail"] and "دقیقه" in r.json()["detail"]


def test_over_500mb_rejected_at_init(client):
    r = client.post("/api/jobs/init", data={
        "filename": "big.mp4", "total_bytes": str(MAX_UPLOAD_BYTES + 1),
        "division": "m_18_34_rx"})
    assert r.status_code == 413 and "500 MB" in r.json()["detail"]
    assert MAX_UPLOAD_BYTES == 500 * 1024 * 1024


def test_garbage_file_rejected_with_readable_message(client, tmp_path):
    p = tmp_path / "bad.mp4"
    p.write_bytes(b"this is not a video" * 5000)
    r = _upload(client, p)
    assert r.status_code == 422 and "not readable" in r.json()["detail"]


def test_low_resolution_rejected(client, tmp_path):
    r = _upload(client, _mk(tmp_path / "lo.mp4", 60, size="320x240"))
    assert r.status_code == 422 and "resolution" in r.json()["detail"].lower()


def test_phone_portrait_rotation_uses_displayed_geometry(tmp_path):
    """iPhone clips are stored landscape + a rotation flag; ffmpeg auto-rotates
    on decode. Geometry must follow the DISPLAYED size or frames get garbled."""
    p = _mk(tmp_path / "rot.mp4", 12, size="1280x720", fps=10,
            extra=("-display_rotation", "90")) if False else None
    base = _mk(tmp_path / "base.mp4", 12, size="1280x720", fps=10)
    rot = tmp_path / "rot.mp4"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-display_rotation", "90", "-i", str(base), "-c", "copy", str(rot)],
                   check=True, capture_output=True)
    info = probe(str(rot))
    assert (info.width, info.height) == (720, 1280)
    with FrameSource(str(rot), fps=10) as fs:
        shape = fs.frame_shape
        n = sum(1 for _ in fs.frames())
    assert shape == (1280, 720) and n >= 100


def test_missing_ffprobe_gives_actionable_message(tmp_path, monkeypatch):
    p = _mk(tmp_path / "x.mp4", 5)
    monkeypatch.setenv("PATH", "")
    res = validate_video(str(p))
    assert not res.ok and "brew install ffmpeg" in res.error_en


def test_health_reports_ffmpeg_and_limit(client):
    h = client.get("/api/health").json()
    assert h["ffmpeg_ok"] and h["ffprobe_ok"] and h["max_upload_mb"] == 500
