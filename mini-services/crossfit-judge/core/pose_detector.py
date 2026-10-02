"""
MediaPipe Pose Landmarker wrapper (Tasks API, VIDEO running mode) with
automatic model download. Produces PoseFrame objects on the CFR timeline.

Key fixes vs v1:
  * visibility gating is done by the consumer per-check (VIS_REQUIRED for
    scoring decisions, VIS_MIN_PRESENCE for mere presence) instead of one
    too-low global 0.15 cut;
  * landmarks are converted to PIXEL coordinates (v1 kept normalized ones
    and mixed the two) — everything downstream works in pixels with H-scaled
    thresholds.
"""
from __future__ import annotations

import os
import sys
import urllib.request
from typing import Optional

from config.settings import (
    MODELS_DIR,
    MODEL_FILENAME,
    MODEL_URL,
    POSE_MIN_DETECTION_CONFIDENCE,
    POSE_MIN_TRACKING_CONFIDENCE,
    VIS_MIN_PRESENCE,
)
from core.types import LM_INDEX, PoseFrame
from utils.geometry import Point


def ensure_model() -> str:
    """Download the pose landmarker model if missing; returns local path."""
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    path = MODELS_DIR / MODEL_FILENAME
    if not path.exists():
        print(f"[model] downloading {MODEL_URL} …", file=sys.stderr)
        tmp = path.with_suffix(".part")
        urllib.request.urlretrieve(MODEL_URL, tmp)
        os.replace(tmp, path)
    return str(path)


class PoseDetector:
    """ Wraps MediaPipe Tasks PoseLandmarker (VIDEO mode, single person)."""

    def __init__(self, model_path: Optional[str] = None):
        import mediapipe as mp
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision

        path = model_path or ensure_model()
        options = vision.PoseLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=path),
            running_mode=vision.RunningMode.VIDEO,
            min_pose_detection_confidence=POSE_MIN_DETECTION_CONFIDENCE,
            min_pose_presence_confidence=POSE_MIN_DETECTION_CONFIDENCE,
            min_tracking_confidence=POSE_MIN_TRACKING_CONFIDENCE,
            num_poses=1,
        )
        self._landmarker = vision.PoseLandmarker.create_from_options(options)
        self._mp = mp
        self._last_ts = -1.0

    def process_frame(self, bgr: "np.ndarray", frame_index: int,
                      timestamp: float) -> PoseFrame:  # type: ignore[name-defined]
        import cv2  # mediapipe ships with opencv
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        mp_image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        # MediaPipe requires strictly increasing timestamps in VIDEO mode
        ts_ms = int(max(timestamp, self._last_ts + 1e-3) * 1000)
        self._last_ts = ts_ms / 1000.0
        result = self._landmarker.detect_for_video(mp_image, ts_ms)

        pf = PoseFrame(frame_index=frame_index, timestamp=timestamp)
        if not result.pose_landmarks or not result.pose_landmarks[0]:
            return pf
        pf.person_detected = True
        lms = result.pose_landmarks[0]
        h, w = bgr.shape[:2]
        for name, idx in LM_INDEX.items():
            if idx >= len(lms):
                continue
            lm = lms[idx]
            vis = float(getattr(lm, "visibility", 1.0))
            if vis < VIS_MIN_PRESENCE:
                continue
            pf.points[name] = Point(x=lm.x * w, y=lm.y * h, z=lm.z * w,
                                    visibility=vis)
        return pf

    def close(self) -> None:
        self._landmarker.close()

    def __enter__(self) -> "PoseDetector":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


class MockPoseSource:
    """Replays a synthetic PoseFrame stream (tests / demo without video)."""

    def __init__(self, frames: list[PoseFrame]):
        self.frames = frames

    def process_frame(self, bgr, frame_index: int, timestamp: float) -> PoseFrame:
        idx = min(frame_index, len(self.frames) - 1)
        f = self.frames[idx]
        return PoseFrame(points=dict(f.points), frame_index=frame_index,
                         timestamp=timestamp, person_detected=f.person_detected)
