"""
The main coordinator. Runs a workout video through pose detection, movement
analysis, judging and reporting, producing the annotated video, timeline and
JSON report.

For multi-movement AMRAP workouts every movement detector runs simultaneously
on each frame, and a rep from any detector counts toward the score (provided
it is within the time cap). This keeps the implementation simple while still
being correct for the common online-competition formats.
"""
from __future__ import annotations

import json
import os
from typing import Any, Callable

import cv2

from config.settings import RESULTS_DIR, TARGET_FPS
from core.pose_detector import PoseDetector
from core.video_processor import VideoProcessor, VideoWriter, transcode_to_h264
from core.timer import WorkoutTimer
from core.sequence import MovementSequence
from movements import get_movement_class
from movements.base_movement import BaseMovement, RepEvent
from judging.scorer import Scorer
from reporting.video_annotator import VideoAnnotator
from reporting.timeline import render_timeline
from reporting.report_generator import build_report


ProgressCallback = Callable[[float, str], None]


class WorkoutAnalyzer:
    def __init__(self, video_path: str, workout: dict[str, Any],
                 job_id: str, progress_callback: ProgressCallback | None = None,
                 pose_detector=None):
        """
        ``pose_detector``: optional pre-built PoseDetector (or mock). If None a
        real PoseDetector is created. Tests inject a mock that returns
        synthetic poses so the full pipeline can be exercised without relying
        on MediaPipe's ability to detect a rendered figure.
        """
        self.video_path = video_path
        self.workout = workout
        self.workout["id"] = workout.get("id", "custom")
        self.job_id = job_id
        self.progress = progress_callback or (lambda p, msg: None)
        self._pose_detector = pose_detector

        self.result_dir = RESULTS_DIR / job_id
        self.result_dir.mkdir(parents=True, exist_ok=True)
        self.annotated_video_path = str(self.result_dir / "annotated.mp4")
        self.timeline_path = str(self.result_dir / "timeline.png")
        self.report_path = str(self.result_dir / "report.json")

    def run(self) -> dict[str, Any]:
        self.progress(0.02, "Opening video...")
        with VideoProcessor(self.video_path, TARGET_FPS) as vp:
            info = vp.info
            total_frames_est = max(1, int(info.duration_seconds * TARGET_FPS))

            # Initialise one detector per movement in the workout.
            movements: list[BaseMovement] = []
            for m_def in self.workout["movements"]:
                cls = get_movement_class(m_def["name"])
                det = cls(standards=m_def.get("standards", {}))
                movements.append(det)

            # Movement sequencer — only runs the CURRENT expected movement's
            # detector. This prevents cross-detection (e.g., a burpee
            # triggering the squat detector in a multi-movement workout).
            sequence = MovementSequence(
                movements=self.workout["movements"])

            timer = WorkoutTimer(
                time_cap_seconds=float(self.workout["time_cap_seconds"]),
                video_duration_seconds=info.duration_seconds,
            )
            scorer = Scorer(self.workout)
            annotator = VideoAnnotator((info.width, info.height))
            writer = VideoWriter(self.annotated_video_path, TARGET_FPS,
                                 (info.width, info.height))

            all_events: list[RepEvent] = []
            last_event: RepEvent | None = None
            frame_idx = 0

            self.progress(0.05, "Detecting pose...")
            detector = self._pose_detector
            detector_owned = False
            if detector is None:
                detector = PoseDetector()
                detector_owned = True
            try:
                for frame, idx, ts in vp.frames():
                    frame_idx = idx
                    pose = detector.process_frame(frame, idx, ts)

                    # Calibrate ground line on first detected frame.
                    if idx == 0 and pose.person_detected:
                        ankles = [pose.get("left_ankle"), pose.get("right_ankle")]
                        ankles = [a for a in ankles if a]
                        if ankles:
                            ground_y = sum(a.y for a in ankles) / len(ankles)
                            for m in movements:
                                if hasattr(m, "calibrate"):
                                    m.calibrate(ground_y)

                    # --- Only run the CURRENT movement's detector ------------
                    # This is the key fix: instead of feeding ALL detectors,
                    # we only feed the one that matches the current expected
                    # movement in the workout's rep scheme.
                    current_det = movements[sequence.current_index]
                    movement_active = False
                    event = current_det.update(pose)
                    if event:
                        if timer.within_cap(ts):
                            all_events.append(event)
                            last_event = event
                            # Record the rep in the sequence — this may
                            # advance to the next movement.
                            sequence.record_rep(event.valid)
                        else:
                            event.valid = False
                            event.no_rep_reason_en = "After time cap"
                            event.no_rep_reason_fa = None
                            all_events.append(event)
                            last_event = event
                    if current_det.phase.value != "idle":
                        movement_active = True

                    timer.maybe_start(ts, movement_active)
                    if timer.started and timer.elapsed(ts) >= timer.time_cap_seconds \
                            and timer.end_time is None:
                        timer.stop(ts)

                    elapsed = timer.elapsed(ts)
                    within = timer.within_cap(ts)

                    # HUD: show the current movement name + phase.
                    hud_name = sequence.current_movement_name
                    hud_phase = current_det.phase.value

                    valid_reps = sum(1 for e in all_events if e.valid)
                    total_reps = len(all_events)

                    annotated = annotator.annotate(
                        frame, pose, hud_name, valid_reps, total_reps,
                        last_event, elapsed, within, hud_phase)
                    writer.write(annotated)

                    if idx % 5 == 0:
                        pct = 0.05 + 0.85 * (idx / total_frames_est)
                        self.progress(min(0.9, pct),
                                      f"Processing frame {idx}...")
            finally:
                if detector_owned:
                    detector.close()

            writer.release()
            timer.stop(frame_idx / TARGET_FPS)

        # Transcode annotated video to H.264 for browser playback.
        self.progress(0.90, "Transcoding video for playback...")
        try:
            transcode_to_h264(self.annotated_video_path)
        except Exception as e:  # noqa: BLE001
            print(f"[analyzer] transcode failed: {e}")

        self.progress(0.92, "Scoring & generating report...")
        score = scorer.score(all_events, timer.started, timer.final_time(),
                             sequence)

        self.progress(0.95, "Rendering timeline...")
        render_timeline(all_events,
                        float(self.workout["time_cap_seconds"]),
                        self.timeline_path,
                        workout_name=self.workout["name"])

        report = build_report(
            workout=self.workout,
            video_name=os.path.basename(self.video_path),
            video_duration=info.duration_seconds,
            events=all_events,
            score=score,
            annotated_video=self.annotated_video_path,
            timeline_image=self.timeline_path,
        )
        # Add sequence info to the report.
        report["sequence"] = sequence.to_dict()

        with open(self.report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        self.progress(1.0, "Done")
        return report
