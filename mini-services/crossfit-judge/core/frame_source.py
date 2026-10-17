"""Video frame source.

Decodes via an ffmpeg pipe into a CONSTANT frame rate raw BGR stream
(`-vf fps=30`), which fixes the v1 OpenCV VFR-drift bug by construction:
frame n always corresponds to timestamp n / TARGET_FPS, regardless of the
container's variable frame rate. Frames are downscaled to MAX_ANALYSIS_WIDTH
for pose-estimation speed.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Iterator, Optional

import numpy as np

from config.settings import MAX_ANALYSIS_WIDTH, TARGET_FPS


@dataclass
class VideoInfo:
    duration_sec: float
    width: int
    height: int
    fps: float
    avg_fps: float
    vfr: bool
    codec: str
    has_audio: bool
    size_bytes: int


class ToolMissing(RuntimeError):
    """ffmpeg/ffprobe is not installed (or not on PATH) — NOT a bad video."""


def tools_status() -> dict:
    import shutil
    return {"ffmpeg": shutil.which("ffmpeg") is not None,
            "ffprobe": shutil.which("ffprobe") is not None}


def _rotation_deg(video: dict) -> int:
    """Display rotation from the container (phones record portrait video as a
    landscape stream + a rotation flag). ffmpeg auto-applies it on decode, so
    all downstream geometry must use the DISPLAYED size."""
    try:
        r = video.get("tags", {}).get("rotate")
        if r is not None:
            return int(float(r)) % 360
        for sd in video.get("side_data_list", []) or []:
            if "rotation" in sd:
                return int(round(float(sd["rotation"]))) % 360
    except Exception:
        pass
    return 0


def probe(path: str) -> Optional[VideoInfo]:
    cmd = [
        "ffprobe", "-hide_banner", "-loglevel", "error",
        "-print_format", "json", "-show_streams", "-show_format", path,
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, timeout=120).stdout
        data = json.loads(out or b"{}")
    except FileNotFoundError as e:
        raise ToolMissing("ffprobe") from e
    except Exception:
        return None
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if video is None:
        return None
    audio = any(s.get("codec_type") == "audio" for s in streams)
    fmt = data.get("format", {})

    def parse_fps(s: Optional[str]) -> float:
        try:
            num, den = s.split("/")
            return float(num) / float(den) if float(den) else 0.0
        except Exception:
            return 0.0

    r_fps = parse_fps(video.get("r_frame_rate"))
    avg_fps = parse_fps(video.get("avg_frame_rate"))
    duration = 0.0
    try:
        duration = float(fmt.get("duration") or video.get("duration") or 0)
    except Exception:
        duration = 0.0
    if duration <= 0:
        # MediaRecorder-style WebM/MKV carry no duration header: read it from
        # the stream tags or the last packet timestamp.
        try:
            tag = (video.get("tags") or {}).get("DURATION") or (fmt.get("tags") or {}).get("DURATION")
            if tag:
                h, m, sec = str(tag).split(":")
                duration = int(h) * 3600 + int(m) * 60 + float(sec)
        except Exception:
            duration = 0.0
    if duration <= 0:
        duration = _duration_by_scan(path)
    w, h = int(video.get("width") or 0), int(video.get("height") or 0)
    if _rotation_deg(video) in (90, 270):
        w, h = h, w          # use the DISPLAYED (auto-rotated) geometry
    return VideoInfo(
        duration_sec=duration,
        width=w,
        height=h,
        fps=r_fps or avg_fps or 25.0,
        avg_fps=avg_fps or r_fps or 25.0,
        vfr=bool(r_fps and avg_fps and abs(r_fps - avg_fps) > 0.5),
        codec=video.get("codec_name", ""),
        has_audio=audio,
        size_bytes=int(fmt.get("size") or 0),
    )


def _duration_by_scan(path: str) -> float:
    """Last-resort duration: timestamp of the final video packet."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "packet=pts_time", "-of", "csv=p=0", path],
            capture_output=True, timeout=300).stdout.decode().split()
        vals = [float(x) for x in out if x.replace(".", "", 1).isdigit()]
        return max(vals) if vals else 0.0
    except Exception:
        return 0.0


class FrameSource:
    """Streams CFR BGR frames from ffmpeg. Use as a context manager."""

    def __init__(self, path: str, start_sec: float = 0.0,
                 end_sec: Optional[float] = None,
                 width: int = MAX_ANALYSIS_WIDTH, fps: float = TARGET_FPS):
        self.path = path
        self.start_sec = max(0.0, start_sec)
        self.end_sec = end_sec
        self.width = width
        self.fps = fps
        self._proc: Optional[subprocess.Popen] = None
        self._w = 0
        self._h = 0

    def __enter__(self) -> "FrameSource":
        vf = f"scale='min({self.width},iw)':-2,fps={self.fps}"
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{self.start_sec:.3f}",
        ]
        if self.end_sec is not None:
            cmd += ["-t", f"{max(0.0, self.end_sec - self.start_sec):.3f}"]
        cmd += [
            "-i", self.path, "-vf", vf,
            "-f", "rawvideo", "-pix_fmt", "bgr24", "pipe:1",
        ]
        # discover output size from the probe (scale=-2 keeps even height)
        info = probe(self.path)
        if info is None or info.width == 0:
            raise RuntimeError("ffprobe failed on " + self.path)
        self._w = min(self.width, info.width)
        self._h = int(round(info.height * (self._w / info.width) / 2) * 2)
        self._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                      stderr=subprocess.DEVNULL,
                                      bufsize=10 ** 8)
        return self

    def __exit__(self, *exc) -> None:
        if self._proc and self._proc.stdout:
            try:
                self._proc.stdout.close()
            except Exception:
                pass
        if self._proc:
            try:
                self._proc.terminate()
            except Exception:
                pass
            self._proc = None

    @property
    def frame_shape(self) -> tuple[int, int]:
        return self._h, self._w

    def frames(self) -> Iterator[tuple[int, float, np.ndarray]]:
        """Yield (frame_index, t_seconds_from_window_start, BGR array).

        frame_index counts frames of the ANALYSIS window (t=0 at the window
        start). Callers map to absolute video time via window_start."""
        assert self._proc and self._proc.stdout
        nbytes = self._h * self._w * 3
        idx = 0
        read = self._proc.stdout.read
        while True:
            buf = read(nbytes)
            if not buf or len(buf) < nbytes:
                break
            frame = np.frombuffer(buf, dtype=np.uint8).reshape(self._h, self._w, 3)
            yield idx, idx / self.fps, frame
            idx += 1

    def frames_from(self, frame_index: int) -> Iterator[tuple[int, float, np.ndarray]]:
        for idx, t, frame in self.frames():
            if idx >= frame_index:
                yield idx, t, frame
