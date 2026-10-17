"""Beep detector (3+1 start pattern) tests — synthetic audio fixtures."""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import numpy as np

from audio.beep_detector import detect_beeps, detect_start
from config import settings


def _beep(t0: float, freq: float, dur: float, sr: int, amp: float = 0.8):
    n = int(dur * sr)
    t = np.arange(n) / sr
    tone = amp * np.sin(2 * np.pi * freq * t) * np.exp(-t * 8)
    out = np.zeros(int((t0 + dur + 0.4) * sr))
    i = int(t0 * sr)
    out[i:i + n] += tone[: len(out) - i]
    return out


def _mix(*tracks, sr: int, noise: float = 0.02):
    n = max(len(x) for x in tracks)
    out = np.zeros(n)
    for x in tracks:
        out[: len(x)] += x
    rng = np.random.default_rng(42)
    out += noise * rng.standard_normal(n)
    return (out * (0.8 / max(1e-6, np.abs(out).max()))).astype(np.float32)


def test_detects_3plus1_pattern():
    sr = settings.BEEP_SAMPLE_RATE
    # intro noise (t=0..8), then 3 low beeps + 1 high GO beep at ~10s
    track = _mix(
        _beep(8.0, 880.0, 0.15, sr),
        _beep(9.0, 880.0, 0.15, sr),
        _beep(10.0, 880.0, 0.15, sr),
        _beep(11.0, 1760.0, 0.18, sr),   # GO
        sr=sr,
    )
    events = detect_beeps(track, sr)
    kinds = [e.kind for e in events]
    assert kinds.count("low") >= 3 and kinds.count("high") >= 1, events

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        import wave
        wav_path = f.name
    # write via scipy to also exercise a real container
    from scipy.io import wavfile
    wavfile.write(wav_path, sr, track)

    det = _detect_on_wav(wav_path)
    assert det.method == "beep", det
    assert det.t_start is not None
    assert 10.5 <= det.t_start <= 11.6, det.t_start  # the GO beep
    Path(wav_path).unlink(missing_ok=True)


def _detect_on_wav(path: str):
    """detect_start expects a video path — wrap the wav in a silent video via
    ffmpeg so we exercise the real extraction path."""
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        mp4 = f.name
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "color=c=black:s=64x64:d=13",
         "-i", path, "-map", "0:v", "-map", "1:a",
         "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", mp4],
        check=True, capture_output=True,
    )
    try:
        return detect_start(mp4)
    finally:
        Path(mp4).unlink(missing_ok=True)


def test_no_pattern_in_plain_noise():
    sr = settings.BEEP_SAMPLE_RATE
    rng = np.random.default_rng(7)
    noise = (0.2 * rng.standard_normal(sr * 15)).astype(np.float32)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav_path = f.name
    from scipy.io import wavfile
    wavfile.write(wav_path, sr, noise)
    det = _detect_on_wav(wav_path)
    assert det.t_start is None
    assert det.method == "none"
    Path(wav_path).unlink(missing_ok=True)


def test_stray_single_beeps_do_not_trigger():
    sr = settings.BEEP_SAMPLE_RATE
    # isolated low beeps at random spots — no 3+1 pattern
    track = _mix(
        _beep(3.0, 880.0, 0.15, sr),
        _beep(30.0, 880.0, 0.15, sr),
        _beep(120.0, 1760.0, 0.15, sr),
        sr=sr, noise=0.03,
    )
    events = detect_beeps(track, sr)
    kinds = "".join(e.kind[0] for e in events)
    assert "lllh" not in kinds
