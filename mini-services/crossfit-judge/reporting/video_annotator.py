"""
Draws the pose skeleton, live rep counter, timer and per-rep verdicts onto
each video frame to produce the annotated review video.
"""
from __future__ import annotations

from typing import Iterable

import cv2
import numpy as np

from config.settings import (
    GOOD_REP_COLOR,
    NO_REP_COLOR,
    SKELETON_COLOR,
    TEXT_COLOR,
)
from core.pose_detector import PoseFrame, LM
from movements.base_movement import RepEvent

# Pairs of landmark names that form the skeleton bones.
SKELETON_CONNECTIONS = [
    ("left_shoulder", "right_shoulder"),
    ("left_shoulder", "left_elbow"), ("left_elbow", "left_wrist"),
    ("right_shoulder", "right_elbow"), ("right_elbow", "right_wrist"),
    ("left_shoulder", "left_hip"), ("right_shoulder", "right_hip"),
    ("left_hip", "right_hip"),
    ("left_hip", "left_knee"), ("left_knee", "left_ankle"),
    ("right_hip", "right_knee"), ("right_knee", "right_ankle"),
    ("left_ankle", "left_heel"), ("right_ankle", "right_heel"),
    ("left_heel", "left_foot_index"), ("right_heel", "right_foot_index"),
    ("nose", "left_shoulder"), ("nose", "right_shoulder"),
]


class VideoAnnotator:
    def __init__(self, frame_size: tuple[int, int]):
        self.w, self.h = frame_size

    def annotate(self, frame: np.ndarray, pose: PoseFrame,
                 movement_name: str, valid_reps: int, total_reps: int,
                 last_event: RepEvent | None, elapsed: float,
                 within_cap: bool, phase: str) -> np.ndarray:
        out = frame.copy()

        # --- Skeleton -------------------------------------------------------
        if pose.person_detected:
            for a_name, b_name in SKELETON_CONNECTIONS:
                a = pose.get(a_name)
                b = pose.get(b_name)
                if a and b:
                    cv2.line(out,
                             (int(a.x * self.w), int(a.y * self.h)),
                             (int(b.x * self.w), int(b.y * self.h)),
                             SKELETON_COLOR, 3, cv2.LINE_AA)
            for name in LM:
                p = pose.get(name)
                if p:
                    cv2.circle(out,
                               (int(p.x * self.w), int(p.y * self.h)),
                               4, SKELETON_COLOR, -1, cv2.LINE_AA)

        # --- HUD: rep counter + timer + movement ---------------------------
        self._draw_panel(out, movement_name, valid_reps, total_reps,
                         elapsed, within_cap, phase, last_event)
        return out

    def _draw_panel(self, out: np.ndarray, movement_name: str,
                    valid_reps: int, total_reps: int, elapsed: float,
                    within_cap: bool, phase: str,
                    last_event: RepEvent | None) -> None:
        # Semi-transparent top-left panel.
        panel_h = 150
        panel_w = 360
        overlay = out.copy()
        cv2.rectangle(overlay, (0, 0), (panel_w, panel_h), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.55, out, 0.45, 0, out)
        cv2.rectangle(out, (0, 0), (panel_w, panel_h), (80, 80, 80), 1)

        # Movement name
        cv2.putText(out, movement_name.upper().replace("_", " "),
                    (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, TEXT_COLOR, 2)
        # Rep counter
        color = GOOD_REP_COLOR if within_cap else (0, 140, 255)
        rep_text = f"REPS: {valid_reps}/{total_reps}"
        cv2.putText(out, rep_text, (12, 62),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)
        # Timer
        m = int(elapsed // 60)
        s = elapsed % 60
        cv2.putText(out, f"TIME: {m:02d}:{s:05.2f}",
                    (12, 96), cv2.FONT_HERSHEY_SIMPLEX, 0.7, TEXT_COLOR, 2)
        # Phase
        cv2.putText(out, f"PHASE: {phase}", (12, 128),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (180, 180, 180), 1)

        # Last verdict badge (bottom-left).
        if last_event is not None:
            badge_color = GOOD_REP_COLOR if last_event.valid else NO_REP_COLOR
            label = f"REP {last_event.rep_number}: {'GOOD' if last_event.valid else 'NO-REP'}"
            cv2.rectangle(out, (0, self.h - 50), (300, self.h), badge_color, -1)
            cv2.putText(out, label, (12, self.h - 18),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
