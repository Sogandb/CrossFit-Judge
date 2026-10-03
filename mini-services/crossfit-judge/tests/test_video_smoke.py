"""Video-path smoke tests: CFR frame source + annotated review video."""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def vfr_mp4(tmp_path_factory) -> Path:
    """A 6s 30fps clip with a moving box + tone audio."""
    p = tmp_path_factory.mktemp("media") / "clip.mp4"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi",
         "-i", "testsrc=size=640x360:rate=30:duration=6",
         "-f", "lavfi", "-i", "sine=frequency=880:duration=6",
         "-c:v", "libx264", "-preset", "ultrafast",
         "-c:a", "aac", "-shortest", str(p)],
        check=True, capture_output=True)
    return p


def test_frame_source_cfr_timeline(vfr_mp4):
    from config.settings import TARGET_FPS
    from core.frame_source import FrameSource, probe
    info = probe(str(vfr_mp4))
    assert info is not None and 5.5 < info.duration_sec < 7
    with FrameSource(str(vfr_mp4), start_sec=0, end_sec=None) as src:
        h, w = src.frame_shape
        assert (h, w) == (360, 640)
        n, last_t = 0, -1
        for idx, t, frame in src.frames():
            assert frame.shape == (h, w, 3)
            assert t > last_t          # strictly increasing
            assert abs(t - idx / TARGET_FPS) < 1e-6   # CFR by construction
            last_t = t
            n += 1
        assert 170 <= n <= 185, n      # ~6s × 30fps


def test_annotate_video_keeps_audio(vfr_mp4, tmp_path):
    from reporting.video_annotator import annotate_video
    dst = tmp_path / "review.mp4"
    result = {
        "analysis_window": {"start_sec": 0.0, "end_sec": 6.0},
        "start_detection": {"t_start_sec": 1.0},
        "events": [
            {"t_start": 1.2, "t_end": 2.0, "outcome": "rep", "scored": True,
             "movement": "thruster", "rep_no": 1},
            {"t_start": 3.0, "t_end": 3.8, "outcome": "no_rep", "scored": False,
             "post_cap": False, "movement": "thruster", "reason_code": "THR_DEPTH"},
        ],
    }
    annotate_video(str(vfr_mp4), str(dst), result)
    assert dst.exists() and dst.stat().st_size > 10_000
    # audio stream must survive (the v1 `-an` bug regression test)
    probe_cmd = ["ffprobe", "-hide_banner", "-loglevel", "error",
                 "-print_format", "json", "-show_streams", str(dst)]
    data = __import__("json").loads(subprocess.run(
        probe_cmd, capture_output=True, check=True).stdout)
    types = {s.get("codec_type") for s in data.get("streams", [])}
    assert "video" in types and "audio" in types, types
