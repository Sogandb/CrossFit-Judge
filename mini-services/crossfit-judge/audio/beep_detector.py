"""
Start-signal detector for Wodx timer apps: the "3+1" beep pattern.

Wodx recording apps emit three low countdown beeps (~1/s) followed by a
higher-pitched "GO" beep. The 4th (shrill) beep marks t_start.

Pipeline (pure numpy/scipy — no librosa, keeps server installs light):
  1. ffmpeg extracts mono audio at 22.05 kHz
  2. 4th-order Butterworth band-pass isolates the beep band
  3. smoothed energy envelope → onset peaks
  4. per onset: 160 ms FFT window → dominant frequency + tone purity
  5. scan for the first [low, low, low, high] pattern with sane gaps
     → t_start = onset time of the high (GO) beep

Only the FIRST full pattern after 0:05 counts (guards against stray beeps
in the athlete intro). All thresholds are configurable in settings.py for
calibration against real Wodx sample audio.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from scipy import signal as sps

from config.settings import (
    BEEP_BAND_HZ,
    BEEP_MAX_GAP_SEC,
    BEEP_MIN_GAP_SEC,
    BEEP_MIN_TONE_PURITY,
    BEEP_ONSET_MS,
    BEEP_SAMPLE_RATE,
    BEEP_SPLIT_HZ,
    T_START_MAX_LEAD_SEC,
)


@dataclass
class BeepEvent:
    t: float
    freq: float
    purity: float
    kind: str  # "low" | "high"


@dataclass
class StartDetection:
    t_start: Optional[float] = None
    method: str = "none"          # beep | none
    confidence: float = 0.0
    beeps: list = field(default_factory=list)
    audio_present: bool = False


def extract_audio(video_path: str) -> Optional[np.ndarray]:
    """Decode mono float32 PCM at BEEP_SAMPLE_RATE via ffmpeg; None if no audio."""
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", video_path, "-vn", "-ac", "1",
        "-ar", str(BEEP_SAMPLE_RATE), "-f", "f32le", "pipe:1",
    ]
    try:
        raw = subprocess.run(cmd, capture_output=True, timeout=180).stdout
    except Exception:
        return None
    if not raw:
        return None
    return np.frombuffer(raw, dtype=np.float32)


def detect_beeps(samples: np.ndarray, sr: int = BEEP_SAMPLE_RATE) -> list[BeepEvent]:
    """Find beep-like onsets and classify low/high by dominant frequency."""
    if samples.size < sr // 2:
        return []
    # 1. band-pass isolate the beep band
    lo, hi = BEEP_BAND_HZ
    sos = sps.butter(4, [lo / (sr / 2), hi / (sr / 2)], btype="band", output="sos")
    band = sps.sosfiltfilt(sos, samples.astype(np.float64))

    # 2. energy envelope (20 ms hop)
    hop = max(1, int(sr * 0.02))
    win = hop * 2
    env = np.array([
        float(np.sqrt(np.mean(band[i:i + win] ** 2)))
        for i in range(0, max(1, band.size - win), hop)
    ])
    if env.size == 0:
        return []
    # adaptive threshold: beeps must stand well above the background
    noise_floor = float(np.percentile(env, 40))
    peak_level = float(np.percentile(env, 99.5))
    thr = max(noise_floor * 3.0, noise_floor + 0.25 * (peak_level - noise_floor))
    if peak_level <= thr:
        return []
    min_dist = int(BEEP_MIN_GAP_SEC * 0.6 / 0.02)
    peaks, _ = sps.find_peaks(env, height=thr, distance=min_dist)

    # 3. per onset: FFT window → dominant freq + purity
    nfft = int(sr * BEEP_ONSET_MS / 1000)
    half = nfft // 2
    events: list[BeepEvent] = []
    for p in peaks:
        center = p * hop
        start = max(0, center - half // 2)
        seg = band[start:start + nfft]
        if seg.size < nfft // 2:
            continue
        seg = seg * np.hanning(seg.size)
        spec = np.abs(np.fft.rfft(seg))
        if spec.size == 0 or spec.sum() <= 0:
            continue
        k = int(np.argmax(spec))
        freq = k * sr / (2 * spec.size - 1) if (2 * spec.size - 1) else 0.0
        # purity: energy within ±2 bins of the dominant frequency vs total
        lo_bin = max(0, k - 2)
        hi_bin = min(spec.size, k + 3)
        purity = float(spec[lo_bin:hi_bin].sum() / spec.sum())
        if purity < BEEP_MIN_TONE_PURITY:
            continue
        t = (center + nfft / 4) / sr  # onset ≈ window start + quarter window
        kind = "low" if freq < BEEP_SPLIT_HZ else "high"
        events.append(BeepEvent(t=round(t, 3), freq=round(freq, 1),
                                purity=round(purity, 2), kind=kind))
    # merge duplicate onsets that are < 0.15 s apart (keep the stronger)
    merged: list[BeepEvent] = []
    for ev in events:
        if merged and ev.t - merged[-1].t < 0.15:
            if ev.purity > merged[-1].purity:
                merged[-1] = ev
        else:
            merged.append(ev)
    return merged


def detect_start(video_path: str) -> StartDetection:
    """Full start detection on a video file. Never raises on missing audio."""
    samples = extract_audio(video_path)
    if samples is None or samples.size == 0:
        return StartDetection(method="none", audio_present=False)
    events = detect_beeps(samples)
    det = StartDetection(method="none", audio_present=True, beeps=[
        {"t": e.t, "freq": e.freq, "purity": e.purity, "kind": e.kind}
        for e in events
    ])
    # scan for the first 3+1 pattern with sane gaps
    i = 0
    while i + 3 < len(events):
        quad = events[i:i + 4]
        kinds = [e.kind for e in quad]
        if kinds == ["low", "low", "low", "high"]:
            gaps_ok = all(
                BEEP_MIN_GAP_SEC <= (quad[j + 1].t - quad[j].t) <= BEEP_MAX_GAP_SEC
                for j in range(3)
            )
            # the final (start) beep must not be absurdly early in the video
            lead_ok = quad[3].t <= T_START_MAX_LEAD_SEC + BEEP_MAX_GAP_SEC
            # ignore stray beeps buried in the first second of the container
            not_too_early = quad[0].t >= 1.0
            if gaps_ok and lead_ok and not_too_early:
                det.t_start = quad[3].t
                det.method = "beep"
                det.confidence = min(1.0, float(np.mean([e.purity for e in quad])) + 0.2)
                return det
        i += 1
    return det
