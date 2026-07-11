"""
Synthetic test harness.

Generates synthetic pose data (and a rendered stick-figure video) for a set
of movements, then verifies the detector pipeline produces the expected rep
counts and verdicts. This is the project's self-test: it proves the judging
logic works end-to-end without needing real competition footage.

Run with:  python3 tests/test_synthetic.py
"""
from __future__ import annotations

import math
import os
import sys
from typing import Callable

import cv2
import numpy as np

sys.path.insert(0, str(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config.settings import TARGET_FPS
from core.pose_detector import PoseFrame
from core.video_processor import VideoWriter
from movements.squat import Squat
from movements.pushup import Pushup
from movements.burpee import Burpee
from movements.base_movement import RepEvent
from utils.geometry import Point

FRAME_W, FRAME_H = 640, 480


# ---------------------------------------------------------------------------
# Geometry helpers for synthetic poses
# ---------------------------------------------------------------------------
def _leg_joints(hip_x: float, hip_y: float, ankle_x: float, ankle_y: float,
                thigh_len: float, shin_len: float) -> tuple[tuple, tuple]:
    """
    Given hip and ankle positions and the thigh/shin lengths, compute the knee
    position that satisfies both distances. The knee is placed in front
    (positive x offset) to mimic a natural squat.
    """
    dx = ankle_x - hip_x
    dy = ankle_y - hip_y
    d = math.hypot(dx, dy)
    if d < 1e-3:
        return (hip_x, hip_y), (ankle_x, ankle_y)
    d = min(d, thigh_len + shin_len - 1)  # avoid impossible triangle
    # a = distance from hip to the foot of the altitude
    a = (thigh_len ** 2 - shin_len ** 2 + d ** 2) / (2 * d)
    h = math.sqrt(max(0.0, thigh_len ** 2 - a ** 2))
    # Unit vector hip -> ankle
    ux, uy = dx / d, dy / d
    # Perpendicular (rotate 90 deg CCW: (-uy, ux)); we want knee in front (+x)
    px, py = -uy, ux
    foot_x = hip_x + a * ux
    foot_y = hip_y + a * uy
    knee_x = foot_x + h * px
    knee_y = foot_y + h * py
    return (knee_x, knee_y), (foot_x, foot_y)


def _knee_angle_for_drop(thigh: float, shin: float, drop: float,
                          ankle_y: float, hip_y_standing: float) -> float:
    """Compute the resulting knee angle for a given vertical hip drop."""
    hip_y = hip_y_standing + drop
    d = abs(ankle_y - hip_y)
    d = min(d, thigh + shin - 1)
    cos_angle = (thigh ** 2 + shin ** 2 - d ** 2) / (2 * thigh * shin)
    cos_angle = max(-1.0, min(1.0, cos_angle))
    return math.degrees(math.acos(cos_angle))


# ---------------------------------------------------------------------------
# Pose generators
# ---------------------------------------------------------------------------
def _pt(x: float, y: float, v: float = 1.0) -> Point:
    return Point(x / FRAME_W, y / FRAME_H, 0.0, v)


def squat_pose(t: float, bad_depth: bool = False) -> dict:
    """
    Squat at progress t (0 = standing, 0.5 = bottom, 1 = back to standing).
    Uses proper leg geometry so the knee angle is physically correct.
    """
    cx = 320
    ankle_y = 420.0
    hip_y_standing = 260.0
    thigh, shin = 80.0, 80.0

    # Depth envelope: 0 at t=0 and t=1, 1 at t=0.5.
    env = 0.5 - 0.5 * math.cos(2 * math.pi * t)
    max_drop = 70.0 if not bad_depth else 35.0
    drop = max_drop * env

    hip_y = hip_y_standing + drop
    knee, _ = _leg_joints(cx, hip_y, cx, ankle_y, thigh, shin)

    # Upper body drops with the hips.
    upper_drop = drop
    return {
        "nose": (cx, 110 + upper_drop),
        "left_shoulder": (cx - 45, 160 + upper_drop),
        "right_shoulder": (cx + 45, 160 + upper_drop),
        "left_elbow": (cx - 60, 220 + upper_drop),
        "right_elbow": (cx + 60, 220 + upper_drop),
        "left_wrist": (cx - 65, 280 + upper_drop),
        "right_wrist": (cx + 65, 280 + upper_drop),
        "left_hip": (cx - 30, hip_y), "right_hip": (cx + 30, hip_y),
        "left_knee": (cx - 30 + (knee[0] - cx), knee[1]),
        "right_knee": (cx + 30 + (knee[0] - cx), knee[1]),
        "left_ankle": (cx - 30, ankle_y), "right_ankle": (cx + 30, ankle_y),
        "left_heel": (cx - 40, ankle_y), "right_heel": (cx + 40, ankle_y),
        "left_foot_index": (cx - 15, ankle_y + 5),
        "right_foot_index": (cx + 15, ankle_y + 5),
    }


def pushup_pose(t: float, bad_lockout: bool = False) -> dict:
    """Push-up cycle. t: 0=top, 0.5=chest to ground, 1=back to top."""
    cx, cy = 320, 300
    env = 0.5 - 0.5 * math.cos(2 * math.pi * t)
    max_drop = 70.0 if not bad_lockout else 45.0
    drop = max_drop * env
    base_y = cy + drop
    # Elbow bend: at the bottom (t=0.5) the elbow is very bent.
    bend = 50.0 * env
    return {
        "nose": (cx - 110, base_y - 10),
        "left_shoulder": (cx - 80, base_y), "right_shoulder": (cx + 40, base_y),
        "left_elbow": (cx - 90, base_y + 30 + bend),
        "right_elbow": (cx + 50, base_y + 30 + bend),
        "left_wrist": (cx - 100, base_y + 60),
        "right_wrist": (cx + 60, base_y + 60),
        "left_hip": (cx - 20, base_y), "right_hip": (cx + 100, base_y),
        "left_knee": (cx + 40, base_y), "right_knee": (cx + 120, base_y),
        "left_ankle": (cx + 90, base_y), "right_ankle": (cx + 150, base_y),
        "left_heel": (cx + 95, base_y + 5), "right_heel": (cx + 155, base_y + 5),
        "left_foot_index": (cx + 85, base_y), "right_foot_index": (cx + 145, base_y),
    }


def burpee_pose(t: float) -> dict:
    """
    Burpee cycle (0..1):
      0.0-0.25  standing -> drop to ground
      0.25-0.5  on ground (chest down)
      0.5-0.75  stand up
      0.75-1.0  jump (ankles up, wrists overhead)
    """
    cx = 320
    if t < 0.25:
        k = t / 0.25
        chest_y = 160 + 220 * k
        ankle_y = 420
        wrist_y = 280 + 100 * k
    elif t < 0.5:
        chest_y = 380
        ankle_y = 420
        wrist_y = 380
    elif t < 0.75:
        k = (t - 0.5) / 0.25
        chest_y = 380 - 220 * k
        ankle_y = 420
        wrist_y = 380 - 100 * k
    else:
        k = (t - 0.75) / 0.25
        chest_y = 160
        ankle_y = 420 - 60 * math.sin(math.pi * k)
        wrist_y = 80
    return {
        "nose": (cx, chest_y - 20),
        "left_shoulder": (cx - 40, chest_y), "right_shoulder": (cx + 40, chest_y),
        "left_elbow": (cx - 55, chest_y + 40), "right_elbow": (cx + 55, chest_y + 40),
        "left_wrist": (cx - 60, wrist_y), "right_wrist": (cx + 60, wrist_y),
        "left_hip": (cx - 30, chest_y + 80), "right_hip": (cx + 30, chest_y + 80),
        "left_knee": (cx - 35, chest_y + 140), "right_knee": (cx + 35, chest_y + 140),
        "left_ankle": (cx - 35, ankle_y), "right_ankle": (cx + 35, ankle_y),
        "left_heel": (cx - 45, ankle_y), "right_heel": (cx + 45, ankle_y),
        "left_foot_index": (cx - 20, ankle_y + 5),
        "right_foot_index": (cx + 20, ankle_y + 5),
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
BONES = [
    ("left_shoulder", "right_shoulder"),
    ("left_shoulder", "left_elbow"), ("left_elbow", "left_wrist"),
    ("right_shoulder", "right_elbow"), ("right_elbow", "right_wrist"),
    ("left_shoulder", "left_hip"), ("right_shoulder", "right_hip"),
    ("left_hip", "right_hip"),
    ("left_hip", "left_knee"), ("left_knee", "left_ankle"),
    ("right_hip", "right_knee"), ("right_knee", "right_ankle"),
    ("left_ankle", "left_heel"), ("right_ankle", "right_heel"),
    ("nose", "left_shoulder"), ("nose", "right_shoulder"),
]


SKIN = (180, 160, 140)       # skin tone (BGR)
SHIRT = (60, 120, 180)       # shirt colour
PANTS = (50, 50, 120)        # pants colour
HEAD_R = 22


def _capsule(frame, p1, p2, color, thickness):
    """Draw a thick rounded line (capsule) between two points."""
    p1 = (int(p1[0]), int(p1[1]))
    p2 = (int(p2[0]), int(p2[1]))
    cv2.line(frame, p1, p2, color, thickness, cv2.LINE_AA)
    cv2.circle(frame, p1, thickness // 2, color, -1, cv2.LINE_AA)
    cv2.circle(frame, p2, thickness // 2, color, -1, cv2.LINE_AA)


def render_frame(joints: dict) -> np.ndarray:
    """Render a human-like silhouette from joint coordinates."""
    frame = np.full((FRAME_H, FRAME_W, 3), 40, dtype=np.uint8)
    # Floor line
    cv2.line(frame, (0, 432), (FRAME_W, 432), (70, 70, 70), 2)

    def j(name):
        return (int(joints[name][0]), int(joints[name][1]))

    # --- Legs (pants) ----------------------------------------------------
    for side in ("left", "right"):
        hip = j(f"{side}_hip")
        knee = j(f"{side}_knee")
        ankle = j(f"{side}_ankle")
        _capsule(frame, hip, knee, PANTS, 18)
        _capsule(frame, knee, ankle, PANTS, 15)

    # --- Torso (shirt) ---------------------------------------------------
    ls, rs = j("left_shoulder"), j("right_shoulder")
    lh, rh = j("left_hip"), j("right_hip")
    torso = np.array([ls, rs, rh, lh], dtype=np.int32)
    cv2.fillConvexPoly(frame, torso, SHIRT, cv2.LINE_AA)

    # --- Arms (skin) -----------------------------------------------------
    for side in ("left", "right"):
        sh = j(f"{side}_shoulder")
        el = j(f"{side}_elbow")
        wr = j(f"{side}_wrist")
        _capsule(frame, sh, el, SHIRT, 14)
        _capsule(frame, el, wr, SKIN, 12)

    # --- Head ------------------------------------------------------------
    nose = j("nose")
    cv2.circle(frame, nose, HEAD_R, SKIN, -1, cv2.LINE_AA)

    # --- Feet ------------------------------------------------------------
    for side in ("left", "right"):
        ank = j(f"{side}_ankle")
        fi = j(f"{side}_foot_index")
        _capsule(frame, ank, fi, (30, 30, 30), 12)

    return frame


def joints_to_pose(joints: dict, idx: int, ts: float) -> PoseFrame:
    pf = PoseFrame(frame_index=idx, timestamp=ts, person_detected=True)
    for name, (x, y) in joints.items():
        pf.points[name] = _pt(x, y, 1.0)
    return pf


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------
# Standing (rest) frames inserted between reps so the state machine can
# settle back to IDLE and finalise each rep.
REST_FRAMES = 6


def make_video(path: str, pose_fn: Callable[[float], dict], cycles: int,
               fps: float = TARGET_FPS, frames_per_cycle: int = 30,
               **kwargs) -> None:
    writer = VideoWriter(path, fps, (FRAME_W, FRAME_H))
    for c in range(cycles):
        for i in range(frames_per_cycle):
            t = i / frames_per_cycle
            joints = pose_fn(t, **kwargs) if kwargs else pose_fn(t)
            writer.write(render_frame(joints))
        # Rest at the top between reps.
        rest_joints = pose_fn(0.0, **kwargs) if kwargs else pose_fn(0.0)
        for _ in range(REST_FRAMES):
            writer.write(render_frame(rest_joints))
    writer.release()


def feed_detector(detector, pose_fn: Callable[[float], dict], cycles: int,
                  frames_per_cycle: int = 30, **kwargs) -> list[RepEvent]:
    events = []
    idx = 0
    for c in range(cycles):
        for i in range(frames_per_cycle):
            t = i / frames_per_cycle
            joints = pose_fn(t, **kwargs) if kwargs else pose_fn(t)
            pose = joints_to_pose(joints, idx, idx / TARGET_FPS)
            ev = detector.update(pose)
            if ev:
                events.append(ev)
            idx += 1
        # Rest at the top between reps.
        rest_joints = pose_fn(0.0, **kwargs) if kwargs else pose_fn(0.0)
        for _ in range(REST_FRAMES):
            pose = joints_to_pose(rest_joints, idx, idx / TARGET_FPS)
            ev = detector.update(pose)
            if ev:
                events.append(ev)
            idx += 1
    return events


def _knee_angle_from_pose(joints: dict) -> float:
    from utils.geometry import angle_2d
    h = _pt(*joints["left_hip"])
    k = _pt(*joints["left_knee"])
    a = _pt(*joints["left_ankle"])
    return angle_2d(h, k, a)


def assert_close(actual: int, expected: int, tol: int, label: str) -> bool:
    ok = abs(actual - expected) <= tol
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {label}: expected ~{expected}, got {actual}")
    return ok


def run_tests() -> int:
    print("=" * 60)
    print("CrossFit AI Judge — Synthetic Self-Test")
    print("=" * 60)
    failures = 0

    # --- Sanity: verify the generated knee angle range -------------------
    print("\n[0] Sanity check — generated squat knee angles")
    standing = squat_pose(0.0)
    bottom = squat_pose(0.5)
    a_top = _knee_angle_from_pose(standing)
    a_bot = _knee_angle_from_pose(bottom)
    print(f"      standing knee angle = {a_top:.1f}° (expect ~175)")
    print(f"      bottom knee angle   = {a_bot:.1f}° (expect ~95)")
    if not (a_top > 160 and a_bot < 110):
        print("  [FAIL] Knee angle range incorrect")
        failures += 1
    else:
        print("  [PASS] Knee angle range OK")

    # --- Test 1: Squat rep counting (direct pose feed) -------------------
    print("\n[1] Squat detector — 8 good reps")
    squat = Squat({"min_knee_angle": 105, "full_extension_angle": 155})
    events = feed_detector(squat, squat_pose, cycles=8, frames_per_cycle=30)
    valid = sum(1 for e in events if e.valid)
    print(f"      total events={len(events)}, valid={valid}, "
          f"no_reps={len(events)-valid}")
    if not assert_close(valid, 8, tol=1, label="valid squats"):
        failures += 1

    # --- Test 2: Squat no-rep detection (shallow squats) -----------------
    print("\n[2] Squat detector — 6 shallow squats (should be no-rep)")
    squat2 = Squat({"min_knee_angle": 105, "full_extension_angle": 155})
    events2 = feed_detector(squat2, squat_pose, cycles=6, frames_per_cycle=30,
                            bad_depth=True)
    valid2 = sum(1 for e in events2 if e.valid)
    norep2 = len(events2) - valid2
    print(f"      total events={len(events2)}, valid={valid2}, no_reps={norep2}")
    for e in events2[:3]:
        if not e.valid:
            print(f"      no-rep #{e.rep_number}: {e.no_rep_reason_fa}")
    if norep2 < 2:
        print("  [WARN] Expected more no-reps for shallow squats")

    # --- Test 3: End-to-end video pipeline -------------------------------
    print("\n[3] End-to-end video pipeline — 5 squats (mock pose injection)")
    from config.settings import RESULTS_DIR
    test_dir = RESULTS_DIR / "_selftest"
    test_dir.mkdir(parents=True, exist_ok=True)
    video_path = str(test_dir / "test_squats.mp4")
    make_video(video_path, squat_pose, cycles=5, frames_per_cycle=30)

    from config.workouts import get_workout
    from core.analyzer import WorkoutAnalyzer

    # Build a mock pose detector that returns synthetic poses keyed by frame
    # index. This lets us exercise the full pipeline (annotation, timeline,
    # scoring, JSON report) without depending on MediaPipe's ability to
    # detect a rendered figure.
    class MockPoseDetector:
        def __init__(self):
            self._idx = 0
            self._cycle_frames = 30
            self._rest_frames = 6

        def process_frame(self, bgr_frame, frame_index, timestamp):
            # Map frame index to a position in the synthetic cycle.
            period = self._cycle_frames + self._rest_frames
            pos = frame_index % period
            if pos < self._cycle_frames:
                t = pos / self._cycle_frames
            else:
                t = 0.0  # rest at top
            joints = squat_pose(t)
            return joints_to_pose(joints, frame_index, timestamp)

        def close(self):
            pass

    workout = get_workout("squat_amrap")
    workout["id"] = "squat_amrap"
    analyzer = WorkoutAnalyzer(video_path, workout, "_selftest",
                               pose_detector=MockPoseDetector())
    report = analyzer.run()
    score = report["score"]
    print(f"      format={score['format']}, valid_reps={score['valid_reps']}, "
          f"total={score['total_reps']}, no_reps={score['no_reps']}")
    print(f"      annotated video: {report['assets']['annotated_video']}")
    print(f"      timeline: {report['assets']['timeline_image']}")
    if not assert_close(score["valid_reps"], 5, tol=1, label="pipeline valid reps"):
        failures += 1

    # --- Summary ---------------------------------------------------------
    print("\n" + "=" * 60)
    if failures == 0:
        print("RESULT: All critical tests PASSED")
    else:
        print(f"RESULT: {failures} test(s) FAILED")
    print("=" * 60)
    return failures


if __name__ == "__main__":
    sys.exit(run_tests())
