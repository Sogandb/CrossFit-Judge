"""
Analysis pipeline: ingest → start detection → calibration → FSM loop →
sequencing → scoring → report (→ optional annotated review video).

The analyzer is the V2 "runtime interpreter": it owns the SceneModel
(calibration, ground plane, bar anchor), feeds the movement FSMs on the CFR
timeline, drives the WOD sequencer and produces the final view-model.
"""
from __future__ import annotations

import traceback
from dataclasses import dataclass
from typing import Callable, Optional

from config.settings import (
    ANNOTATE_REVIEW_VIDEO,
    CALIB_WARMUP_SEC,
    CLOCK_FROM_VIDEO_START,
    POST_CAP_TAIL_SEC,
    PREROLL_SEC,
    TARGET_FPS,
)
from core.calibration import calibrate, online_ground_update, online_height_update
from core.frame_source import FrameSource, probe
from core.mock_pose import gen_synthetic_workout
from core.pose_detector import PoseDetector
from core.sequence import WodSequencer
from core.types import PoseFrame, SceneModel
from ingest.validate import validate_video
from judging.scorer import final_overview, reconcile, score_display
from movements.bar_facing_burpee import BarFacingBurpeeFSM
from movements.thruster import ThrusterFSM
from audio.beep_detector import detect_start

MOVEMENT_LABELS_FA = {
    "thruster": "تراستر",
    "bar_facing_burpee": "بورپی رو به بار",
}

MOVEMENT_LABELS_EN = {
    "thruster": "Thruster",
    "bar_facing_burpee": "Bar-Facing Burpee",
}


@dataclass
class AnalysisOutcome:
    ok: bool
    error_fa: Optional[str] = None
    result: Optional[dict] = None
    error_en: Optional[str] = None


class Analyzer:
    def __init__(self, job: dict, progress: Callable[[str, float], None]):
        self.job = job
        self.progress = progress
        self.meta = job.get("meta", {}) or {}

    # ------------------------------------------------------------------ #
    def run(self) -> AnalysisOutcome:
        try:
            return self._run_inner()
        except Exception as e:  # noqa: BLE001 — surface a bilingual error
            traceback.print_exc()
            return AnalysisOutcome(False, f"خطای داخلی پردازش: {e}", None,
                                   f"Internal processing error: {e}")

    # ------------------------------------------------------------------ #
    def _run_inner(self) -> AnalysisOutcome:
        video_path = self.job.get("video_path")
        mock = self.meta.get("pose_source") == "mock"

        # ---------------- 1. ingest validation ---------------- #
        info = None
        if not mock:
            self.progress("validate", 2)
            res = validate_video(video_path)
            if not res.ok:
                return AnalysisOutcome(False, res.error_fa, None, res.error_en)
            info = res.info

        # ---------------- 2. start detection ---------------- #
        self.progress("start_detect", 6)
        manual_start = self.meta.get("manual_start_sec")
        start_det = None
        if manual_start is not None and float(manual_start) >= 0:
            t_start = float(manual_start)
            start_method = "manual"
            start_conf = 1.0
        elif mock:
            t_start = float(self.meta.get("mock_lead_in_sec", 6.0))
            start_method = "mock"
            start_conf = 1.0
        elif CLOCK_FROM_VIDEO_START:
            # v2.1: the workout clock IS the video clock — it starts at the very
            # first frame (t = 0) and stops at the last rep or at the time cap.
            t_start = 0.0
            start_method = "video_clock"
            start_conf = 1.0
        else:
            start_det = detect_start(video_path)
            t_start = start_det.t_start if start_det.t_start is not None else 0.0
            start_method = start_det.method if start_det.t_start is not None else "video_start"
            start_conf = start_det.confidence if start_det.t_start is not None else 0.0

        warnings: list[dict] = []
        if not mock and start_method == "video_start":
            warnings.append(_warning("SYS_START_NOT_FOUND"))

        # ---------------- 3. analysis window ---------------- #
        wod = self.job["wod"]
        cap = float(wod.get("time_cap_sec") or 0)
        if not mock and start_method == "video_start" and cap:
            warnings.append(_warning("SYS_CAP_UNKNOWN_START"))
        # The time cap is only enforceable when the WOD start is KNOWN
        # (beeps or manual). With an undetected start, running the cap clock
        # from t=0 would silently discard real reps at the video tail — the
        # single biggest under-counting source on real phone videos.
        cap_enforced = start_method in ("beep", "manual", "mock", "video_clock")
        window_start = max(0.0, t_start - PREROLL_SEC)
        if mock:
            window_end = None
        elif cap and cap_enforced:
            duration = info.duration_sec
            window_end = min(duration, t_start + cap + POST_CAP_TAIL_SEC)
        else:
            window_end = info.duration_sec   # analyze the WHOLE video
        scene = SceneModel()

        # ---------------- 4. pose source ---------------- #
        detector = None
        src = None
        cache_path = self.meta.get("pose_cache")   # dev/validation replay
        if mock:
            blocks = self._wod_blocks_for_mock()
            frames = gen_synthetic_workout(
                blocks, faults=self.meta.get("mock_faults") or {},
                lead_in_sec=t_start)
            pose_source = _MockDetector(frames)
            frame_iter = _MockFrameIterator(frames)
            total_frames = len(frames)
        elif cache_path:
            import pickle
            with open(cache_path, "rb") as f:
                data = pickle.load(f)
            cached = data["frames"]
            pose_source = _ReplayDetector(cached)
            frame_iter = _ReplayIterator(cached)
            total_frames = max(1, len(cached))
        else:
            detector = PoseDetector()
            src = FrameSource(video_path, start_sec=window_start,
                              end_sec=window_end, fps=TARGET_FPS)
            src.__enter__()          # spawn the ffmpeg CFR decode pipe
            pose_source = detector
            frame_iter = src
            total_frames = max(1, int((window_end - window_start) * TARGET_FPS))

        sequencer = WodSequencer(wod, t_start=t_start,
                                 labels_fa=MOVEMENT_LABELS_FA,
                                 labels_en=MOVEMENT_LABELS_EN,
                                 cap_enforced=cap_enforced)
        fsms = [ThrusterFSM(), BarFacingBurpeeFSM()]

        # ---------------- 5. frame loop ---------------- #
        try:
            self.progress("calibration", 10)
            self._frame_loop(frame_iter, pose_source, window_start, t_start,
                             scene, sequencer, fsms, total_frames)
        finally:
            if src is not None:
                try:
                    src.__exit__(None, None, None)
                except Exception:
                    pass
            if detector is not None:
                try:
                    detector.close()
                except Exception:
                    pass

        # ---------------- 6. scoring ---------------- #
        self.progress("scoring", 96)
        summary = sequencer.summary()
        if not mock and summary["total_credited"] == 0 and \
                summary["total_prescribed"] > 0:
            warnings.append(_warning("SYS_NO_PERSON"))
        rec = reconcile(summary, self.meta.get("claimed"))
        disp = score_display(summary)
        events_d = [e.to_dict() for e in sequencer.events]
        last_frame_t = getattr(self, "_last_frame_t", t_start)
        overview = final_overview(summary, t_start, cap, cap_enforced,
                                  last_frame_t, events_d)
        disp.update({"final_time_sec": overview["stop_time_sec"],
                     "final_time_text": overview["stop_time_text"],
                     "final_time_kind": overview["stop_kind"],
                     "final_reps": overview["reps_counted"]})

        result = {
            "engine_version": "3.0.0",
            "wod": {
                "id": wod.get("wod_id"),
                "name_fa": wod.get("name_fa"),
                "name_en": wod.get("name_en"),
                "format": wod.get("format"),
                "format_fa": wod.get("format_fa"),
                "format_en": wod.get("format_en"),
                "time_cap_sec": wod.get("time_cap_sec"),
                "description_fa": wod.get("description_fa"),
                "description_en": wod.get("description_en"),
                "score_fa": wod.get("score_fa"),
                "score_en": wod.get("score_en"),
                "rep_timeline": summary["rep_timeline"],
            },
            "start_detection": {
                "method": start_method,
                "t_start_sec": round(t_start, 2),
                "confidence": round(start_conf, 2),
                "beeps": (start_det.beeps if start_det else []),
                "audio_present": (start_det.audio_present if start_det else None),
            },
            "summary": summary,
            "reconciliation": rec,
            "score_display": disp,
            "overview": overview,
            "events": events_d,
            "sequencer_flags": sequencer.flags,
            "warnings": warnings,
            "video_info": (None if info is None else {
                "duration_sec": round(info.duration_sec, 1),
                "width": info.width, "height": info.height,
                "fps": round(info.fps, 2), "vfr": info.vfr,
                "has_audio": info.has_audio,
            }),
            "analysis_window": {
                "start_sec": round(window_start, 2),
                "end_sec": (round(window_end, 2) if window_end is not None else None),
            },
        }

        # ---------------- 7. annotated review video ---------------- #
        # Rendered ASYNCHRONOUSLY by the store (background thread): the
        # result below is final immediately — the UI shows the full judging
        # report right away and swaps the review video in via polling once
        # the renderer patches review_video "pending" → True.
        annotate = ANNOTATE_REVIEW_VIDEO and self.meta.get("annotate", True)
        if not mock and annotate and self.job.get("video_path"):
            result["review_video"] = "pending"
        else:
            result["review_video"] = False

        return AnalysisOutcome(True, None, result)

    # ------------------------------------------------------------------ #
    def _frame_loop(self, frame_iter, pose_source, window_start: float,
                    t_start: float, scene: SceneModel, sequencer: WodSequencer,
                    fsms: list, total_frames: int) -> None:
        from movements.base import FrameContext

        preroll: list[PoseFrame] = []
        ground_samples: list[tuple[float, float]] = []
        height_samples: list[float] = []
        bar_candidates: list[float] = []
        calibrated = False
        processed = 0
        warm: list = []

        for idx, t_rel, bgr in frame_iter.frames():
            t_abs = window_start + t_rel
            self._last_frame_t = t_abs
            pf = pose_source.process_frame(bgr, idx, t_rel)
            processed += 1

            # ---- preroll buffering + calibration ---- #
            if t_abs < t_start:
                if pf.person_detected:
                    preroll.append(pf)
                if not calibrated and preroll and \
                        (len(preroll) >= 15 or t_abs > t_start - 1.0):
                    calibrated = calibrate(preroll, scene)
                continue

            # ---- no preroll (clock starts at video start): WARM-UP calibration -- #
            # The first CALIB_WARMUP_SEC seconds are buffered, the scene is
            # calibrated on them, then the buffered frames are judged in order
            # — nothing is skipped and the clock still starts at t = 0.
            if not calibrated:
                warm.append((idx, t_abs, pf))
                if pf.person_detected:
                    preroll.append(pf)
                if (t_abs - warm[0][1]) < CALIB_WARMUP_SEC:
                    continue
                calibrated = self._calibrate_with_fallback(preroll, warm, scene)
                if not calibrated:
                    # keep scanning: slide the warm-up window, retry next frame
                    while warm and (t_abs - warm[0][1]) >= CALIB_WARMUP_SEC:
                        warm.pop(0)
                    if len(preroll) > 60:
                        del preroll[: len(preroll) - 60]
                    if processed % 300 == 0:
                        self.progress("waiting_athlete",
                                      10 + 80 * processed / total_frames)
                    continue
                buffered, warm = list(warm), []
                for bi, bt, bpf in buffered:
                    self._work_frame(bi, bt, bpf, scene, sequencer, fsms,
                                     ground_samples, height_samples,
                                     bar_candidates)
                continue

            self._work_frame(idx, t_abs, pf, scene, sequencer, fsms,
                             ground_samples, height_samples, bar_candidates)
            if processed % 150 == 0:
                self.progress("analyzing", 10 + 85 * processed / total_frames)

        # flush any attempt still open at stream end (with the REAL last
        # frame time — a synthetic huge t_end would falsely mark post-cap)
        last_t = getattr(self, "_last_frame_t", window_start)
        for fsm in fsms:
            fsm.force_close(last_t)
            tail = fsm.collect()
            if tail:
                sequencer.feed(tail, last_t)
        # emit attempts still held by the sequencer (unconfirmed switches)
        sequencer.flush(last_t)

    # ------------------------------------------------------------------ #
    def _calibrate_with_fallback(self, preroll: list, warm: list,
                                 scene: SceneModel) -> bool:
        if calibrate(preroll, scene):
            return True
        # degraded fallback: derive H from any detected person frame
        for _, _, pf in reversed(warm):
            nose = pf.get("nose") if pf.person_detected else None
            ank = pf.mid("left_ankle", "right_ankle") if pf.person_detected else None
            if nose and ank and ank.y > nose.y:
                scene.H = max(50.0, ank.y - nose.y)
                if scene.ground_y_at(ank.x) is None:
                    scene.set_ground(ank.y, 0.0)
                self._warn_fallback_calibration = True
                return True
        return False

    def _work_frame(self, idx: int, t_abs: float, pf: PoseFrame,
                    scene: SceneModel, sequencer: WodSequencer, fsms: list,
                    ground_samples: list, height_samples: list,
                    bar_candidates: list) -> None:
        """One judged frame: online scene updates -> gated FSMs -> sequencer."""
        from movements.base import FrameContext
        online_ground_update(scene, pf, ground_samples)
        online_height_update(scene, pf, height_samples)
        self._track_bar(scene, pf, bar_candidates)
        ctx = FrameContext(t=t_abs, frame_index=idx, pose=pf, scene=scene)
        sequencer.sync_fsms(fsms, t_abs)      # counter-driven: only the expected FSM(s) run
        for fsm in fsms:
            fsm.process(ctx)
        attempts = []
        for fsm in fsms:
            attempts.extend(fsm.collect())
        if attempts:
            sequencer.feed(attempts, t_abs)

    # ------------------------------------------------------------------ #
    def _wod_blocks_for_mock(self) -> list[dict]:
        blocks = self.job["wod"]["blocks"]
        scale = self.meta.get("mock_block_scale")  # shrink blocks for fast tests
        if scale and 0 < float(scale) <= 1:
            return [{"movement": b["movement"],
                     "reps": max(1, int(round(b["reps"] * float(scale))))}
                    for b in blocks]
        return blocks

    def _track_bar(self, scene: SceneModel, pf: PoseFrame,
                   candidates: list[float]) -> None:
        """Online bar-anchor tracking: near-ground wrist contacts close to the
        athlete. Guarded so BFB floor-hand plants (far from the bar) don't
        contaminate the anchor."""
        if scene.H <= 0 or not pf.person_detected:
            return
        wr = pf.mid("left_wrist", "right_wrist")
        ank = pf.mid("left_ankle", "right_ankle")
        if wr is None or ank is None or wr.visibility < 0.5 or ank.visibility < 0.5:
            return
        gy = scene.ground_y_at(wr.x)
        if gy is None or wr.y < gy - 0.12 * scene.H:
            return  # hands not near the floor
        if abs(wr.x - ank.x) > 0.8 * scene.H:
            return  # not at the athlete's station
        if scene.bar_confidence > 0 and abs(wr.x - scene.bar_x) > 0.35 * scene.H:
            return  # far from the known anchor → don't contaminate
        candidates.append(wr.x)
        if len(candidates) > 20:
            del candidates[: len(candidates) - 20]
        if len(candidates) >= 3:
            xs = sorted(candidates)
            bar_x = xs[len(xs) // 2]
            conf = min(1.0, 0.3 + 0.07 * len(candidates))
            scene.set_bar(bar_x, scene.ground_y_at(bar_x) or gy, conf)


def _warning(code: str) -> dict:
    """Structured bilingual warning entry (UI picks fa/en)."""
    from movements.reasons import reason_fa, reason_en
    return {"code": code, "fa": reason_fa(code), "en": reason_en(code)}


class _MockDetector:
    """PoseDetector-shaped adapter over a synthetic frame list."""

    def __init__(self, frames: list[PoseFrame]):
        self.frames = frames

    def process_frame(self, bgr, frame_index: int, timestamp: float) -> PoseFrame:
        f = self.frames[min(frame_index, len(self.frames) - 1)]
        return PoseFrame(points=dict(f.points), frame_index=frame_index,
                         timestamp=timestamp, person_detected=f.person_detected)


class _ReplayDetector:
    """PoseDetector-shaped adapter over a CACHED pose stream (extracted once
    from a real video) — enables fast judging-logic iteration + regression
    tests without re-running pose detection."""

    def __init__(self, frames: list[PoseFrame]):
        self.frames = frames

    def process_frame(self, bgr, frame_index: int, timestamp: float) -> PoseFrame:
        if frame_index < len(self.frames):
            f = self.frames[frame_index]
            return PoseFrame(points=dict(f.points), frame_index=frame_index,
                             timestamp=timestamp,
                             person_detected=f.person_detected)
        return PoseFrame(frame_index=frame_index, timestamp=timestamp)

    def close(self) -> None:  # interface parity with PoseDetector
        pass


class _ReplayIterator:
    """FrameSource-shaped adapter over a cached pose stream."""

    def __init__(self, frames: list[PoseFrame]):
        self._frames = frames

    def frames(self):
        for i, f in enumerate(self._frames):
            yield i, f.timestamp, None


class _MockFrameIterator:
    """FrameSource-shaped adapter producing dummy black frames.

    Timestamps come from the MOCK FRAMES THEMSELVES (they are generated at
    the mock's native fps) — NOT from frame_index/TARGET_FPS. The old
    i/TARGET_FPS remapping ran a 30 fps synthetic stream at half speed,
    inflating a ~345 s workout to ~680 s and blowing the 600 s time cap
    (besides skewing every time-based FSM threshold)."""

    def __init__(self, frames: list[PoseFrame], w: int = 640, h: int = 360):
        import numpy as np
        self._frames = frames
        self.frame = np.zeros((h, w, 3), dtype=np.uint8)

    def frames(self):
        for i, f in enumerate(self._frames):
            yield i, f.timestamp, self.frame
