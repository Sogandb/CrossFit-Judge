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
    """ Wraps MediaPipe Tasks PoseLandmarker (VIDEO mode, single person).

    Motion-gated inference (speed): the landmarker only runs when the frame
    actually CHANGED. A tiny grayscale thumbnail of the last inferred frame
    is compared to the current one; near-identical frames reuse the last
    pose (a static athlete cannot change movement state). A keep-alive
    inference runs after MOTION_KEEPALIVE_SEC of stillness so slow drifts
    (camera shake, lighting) are still tracked, and a short post-motion
    tail keeps inference hot right after movement stops. Workout videos
    are typically still 70-90% of the time -> most frames skip the
    ~11 ms inference entirely."""

    #: thumbnail size for the motion gate (w x h)
    _THUMB = (64, 36)
    #: mean |diff| below this -> frame considered static (0-255 scale)
    MOTION_DIFF_THRESHOLD = 2.5
    #: even while static, re-infer at least this often (seconds)
    MOTION_KEEPALIVE_SEC = 1.0
    #: after motion stops, keep inferring this long (seconds)
    MOTION_TAIL_SEC = 0.5

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
        # motion-gate state (see class docstring)
        self._last_thumb = None      # grayscale thumbnail of last inferred frame
        self._last_pose = None       # last inferred PoseFrame (reuse on static)
        self._last_infer_t = -1e9    # timestamp of last real inference
        self._last_motion_t = -1e9   # timestamp when motion was last seen
        self.stats = {"inferred": 0, "skipped": 0}

    def process_frame(self, bgr: "np.ndarray", frame_index: int,
                      timestamp: float) -> PoseFrame:  # type: ignore[name-defined]
        import cv2  # mediapipe ships with opencv

        # ---- motion gate ------------------------------------------------ #
        thumb = cv2.resize(bgr, self._THUMB, interpolation=cv2.INTER_AREA)
        thumb = cv2.cvtColor(thumb, cv2.COLOR_BGR2GRAY).astype("int16")
        moved = True
        if self._last_thumb is not None:
            diff = float(abs(thumb - self._last_thumb).mean())
            moved = diff >= self.MOTION_DIFF_THRESHOLD
        if moved:
            self._last_motion_t = timestamp
        skip = (
            self._last_pose is not None
            and not moved
            and (timestamp - self._last_infer_t) < self.MOTION_KEEPALIVE_SEC
            and (timestamp - self._last_motion_t) < self.MOTION_TAIL_SEC
        )
        if skip:
            self.stats["skipped"] += 1
            return PoseFrame(points=dict(self._last_pose.points),
                             frame_index=frame_index, timestamp=timestamp,
                             person_detected=self._last_pose.person_detected)

        # ---- real inference --------------------------------------------- #
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        mp_image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        # MediaPipe requires strictly increasing timestamps in VIDEO mode
        ts_ms = int(max(timestamp, self._last_ts + 1e-3) * 1000)
        self._last_ts = ts_ms / 1000.0
        result = self._landmarker.detect_for_video(mp_image, ts_ms)
        self._last_thumb = thumb
        self._last_infer_t = timestamp
        self.stats["inferred"] += 1

        pf = PoseFrame(frame_index=frame_index, timestamp=timestamp)
        if not result.pose_landmarks or not result.pose_landmarks[0]:
            self._last_pose = pf
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
        self._last_pose = pf
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
