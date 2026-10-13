"""
Video input handling. Reads frames at a controlled FPS so the rest of the
pipeline is deterministic regardless of the source video's framerate.
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from typing import Iterator

import cv2
import numpy as np

from config.settings import TARGET_FPS


@dataclass
class VideoInfo:
    width: int
    height: int
    fps: float
    frame_count: int
    duration_seconds: float


class VideoProcessor:
    """OpenCV video reader with optional resampling to TARGET_FPS."""

    def __init__(self, path: str, target_fps: float = TARGET_FPS):
        self.path = path
        self.target_fps = target_fps
        self._cap = cv2.VideoCapture(path)
        if not self._cap.isOpened():
            raise IOError(f"Cannot open video: {path}")
        self.info = self._read_info()

    def _read_info(self) -> VideoInfo:
        w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = self._cap.get(cv2.CAP_PROP_FPS) or 30.0
        n = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))
        return VideoInfo(w, h, fps, n, n / fps if fps else 0.0)

    def frames(self) -> Iterator[tuple[np.ndarray, int, float]]:
        """
        Yield (frame_bgr, frame_index, timestamp_seconds) tuples sampled at
        target_fps.
        """
        src_fps = self.info.fps or 30.0
        step = max(1, int(round(src_fps / self.target_fps)))
        idx = 0
        out_idx = 0
        while True:
            ok, frame = self._cap.read()
            if not ok:
                break
            if idx % step == 0:
                ts = out_idx / self.target_fps
                yield frame, out_idx, ts
                out_idx += 1
            idx += 1

    def release(self) -> None:
        self._cap.release()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.release()


class VideoWriter:
    """Thin wrapper around cv2.VideoWriter for annotated output."""

    def __init__(self, path: str, fps: float, size: tuple[int, int]):
        self.path = path
        self.fps = fps
        self._writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"),
                                       fps, size)

    def write(self, frame: np.ndarray) -> None:
        self._writer.write(frame)

    def release(self) -> None:
        self._writer.release()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.release()


def transcode_to_h264(input_path: str, output_path: str | None = None) -> str:
    """
    Transcode a video to H.264 MP4 for browser compatibility. OpenCV writes
    MPEG-4 Part 2 (mp4v) which browsers cannot play; ffmpeg remuxes to H.264.
    Returns the path to the transcoded file.
    """
    out = output_path or (os.path.splitext(input_path)[0] + "_h264.mp4")
    # -y: overwrite, -loglevel error: quiet, -movflags +faststart: web streaming
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", input_path,
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-movflags", "+faststart",
        "-an",  # no audio
        out,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # If transcoding fails, keep the original (better than nothing).
        print(f"[transcode] ffmpeg failed: {result.stderr}")
        return input_path
    # Replace the original with the transcoded version.
    os.replace(out, input_path)
    return input_path
