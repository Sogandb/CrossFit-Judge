"""
MediaPipe Pose wrapper (Tasks API). Produces a normalised, frame-by-frame
stream of landmark points for the downstream movement analysers.

Uses the MediaPipe Tasks Vision API with the pose_landmarker model.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

import cv2
import mediapipe as mp
import numpy as np

from config.settings import (
    LANDMARK_PRESENCE_THRESHOLD,
    POSE_MIN_DETECTION_CONFIDENCE,
    POSE_MIN_TRACKING_CONFIDENCE,
)
from utils.geometry import Point, to_point

# MediaPipe Pose landmark indices (subset we care about).
LM = {
    "nose": 0,
    "left_shoulder": 11, "right_shoulder": 12,
    "left_elbow": 13, "right_elbow": 14,
    "left_wrist": 15, "right_wrist": 16,
    "left_hip": 23, "right_hip": 24,
    "left_knee": 25, "right_knee": 26,
    "left_ankle": 27, "right_ankle": 28,
    "left_heel": 29, "right_heel": 30,
    "left_foot_index": 31, "right_foot_index": 32,
}

# Default model path relative to the service root.
MODEL_PATH = Path(__file__).resolve().parent.parent / "data" / "models" / "pose_landmarker.task"


@dataclass
class PoseFrame:
    """All landmarks + helper lookups for a single frame."""
    points: dict[str, Point] = field(default_factory=dict)
    frame_index: int = 0
    timestamp: float = 0.0
    person_detected: bool = False

    def get(self, name: str) -> Point | None:
        return self.points.get(name)

    def avg(self, *names: str) -> Point | None:
        """Average of several landmarks (e.g. both hips for the hip center)."""
        pts = [self.points[n] for n in names if n in self.points]
        if not pts:
            return None
        x = sum(p.x for p in pts) / len(pts)
        y = sum(p.y for p in pts) / len(pts)
        z = sum(p.z for p in pts) / len(pts)
        v = min(p.visibility for p in pts)
        return Point(x, y, z, v)

    def __getitem__(self, name: str) -> Point:
        return self.points[name]


class PoseDetector:
    """
    Wraps MediaPipe Pose Landmarker (Tasks API). Iterate over frames of a
    video to receive PoseFrame objects.

    Usage:
        detector = PoseDetector()
        for pose_frame in detector.process(video_frames, fps):
            ...
    """

    def __init__(self, model_path: str | None = None):
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision

        path = model_path or str(MODEL_PATH)
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"Pose landmarker model not found at {path}. "
                f"Download it from "
                f"https://storage.googleapis.com/mediapipe-models/"
                f"pose_landmarker/pose_landmarker_full/float16/1/"
                f"pose_landmarker_full.task"
            )

        base_options = mp_python.BaseOptions(model_asset_path=path)
        options = vision.PoseLandmarkerOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.VIDEO,
            min_pose_detection_confidence=POSE_MIN_DETECTION_CONFIDENCE,
            min_pose_presence_confidence=POSE_MIN_DETECTION_CONFIDENCE,
            min_tracking_confidence=POSE_MIN_TRACKING_CONFIDENCE,
            num_poses=1,
        )
        self._landmarker = vision.PoseLandmarker.create_from_options(options)
        self._mp = mp

    def process_frame(self, bgr_frame: np.ndarray, frame_index: int = 0,
                      timestamp: float = 0.0) -> PoseFrame:
        rgb = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2RGB)
        mp_image = self._mp.Image(
            image_format=self._mp.ImageFormat.SRGB, data=rgb)
        ts_ms = int(timestamp * 1000)
        result = self._landmarker.detect_for_video(mp_image, ts_ms)

        pf = PoseFrame(frame_index=frame_index, timestamp=timestamp)
        if not result.pose_landmarks or not result.pose_landmarks[0]:
            return pf

        pf.person_detected = True
        landmarks = result.pose_landmarks[0]
        for name, idx in LM.items():
            if idx >= len(landmarks):
                continue
            lm = landmarks[idx]
            # In the Tasks API, each landmark has x, y, z, visibility.
            visibility = float(getattr(lm, "visibility", 1.0))
            if visibility >= LANDMARK_PRESENCE_THRESHOLD * 0.3:
                pf.points[name] = to_point(lm)
        return pf

    def close(self) -> None:
        self._landmarker.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
