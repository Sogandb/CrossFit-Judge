"""
Central configuration for the CrossFit Judge V2 engine.

Every threshold here is expressed either:
  - as a fraction of the athlete's calibrated body height (scale-invariant),
  - in degrees (joint angles), or
  - in seconds (temporal debounce / hysteresis windows).

This file is the single tuning surface for the whole engine. Values marked
"CALIBRATE" should be refined on the golden dataset (real Wodx videos).
"""
from __future__ import annotations

import os
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = SERVICE_ROOT / "data"
MODELS_DIR = DATA_DIR / "models"
UPLOADS_DIR = DATA_DIR / "uploads"
WODS_DIR = DATA_DIR / "wods"
DB_PATH = DATA_DIR / "judge_v2.db"

# --------------------------------------------------------------------------- #
# Service
# --------------------------------------------------------------------------- #
SERVICE_PORT = int(os.environ.get("JUDGE_PORT", "8001"))
MAX_UPLOAD_BYTES = int(os.environ.get("JUDGE_MAX_UPLOAD_BYTES", 3 * 1024 * 1024 * 1024))  # 3 GB
WORKER_CONCURRENCY = int(os.environ.get("JUDGE_WORKERS", "2"))  # bounded pool (fixes v1 unlimited concurrency)

# --------------------------------------------------------------------------- #
# Video ingest gates
# --------------------------------------------------------------------------- #
TARGET_FPS = 30.0            # analysis frame rate (CFR, fixes v1 VFR drift)
MAX_ANALYSIS_WIDTH = 1280    # downscale for pose estimation speed
MAX_VIDEO_DURATION_SEC = 900  # 15 minutes — hard gate per Wodx requirement
MIN_VIDEO_DURATION_SEC = 10   # shorter videos are almost certainly wrong uploads
REVIEW_VIDEO_MAX_HEIGHT = 720  # annotated review video output height

# --------------------------------------------------------------------------- #
# Pose estimation
# --------------------------------------------------------------------------- #
MODEL_FILENAME = "pose_landmarker_full.task"
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
    "pose_landmarker_full/float16/latest/pose_landmarker_full.task"
)
POSE_MIN_DETECTION_CONFIDENCE = 0.5
POSE_MIN_TRACKING_CONFIDENCE = 0.5
# Visibility gate for landmarks used in *scoring* decisions (v1 used 0.15 →
# too low; low-visibility landmarks must flag "review", not silently pass).
VIS_REQUIRED = 0.55   # below this, a scoring check is unreliable → review flag
VIS_MIN_PRESENCE = 0.25  # below this the landmark is considered absent

# --------------------------------------------------------------------------- #
# Start detection (beep detector 3+1) — calibrated for Wodx timer app.
# CALIBRATE: refine bands/gaps once on real Wodx sample audio.
# --------------------------------------------------------------------------- #
BEEP_SAMPLE_RATE = 22050
BEEP_BAND_HZ = (600.0, 6000.0)      # band-pass for tone isolation
BEEP_MIN_TONE_PURITY = 0.30         # 5-bin peak concentration / total
BEEP_SPLIT_HZ = 1300.0              # f0 < split → "low" countdown beep; else "high" GO beep
BEEP_MIN_GAP_SEC = 0.55             # allowed gap between consecutive beeps
BEEP_MAX_GAP_SEC = 2.50
BEEP_ONSET_MS = 160                 # FFT window per onset
PREROLL_SEC = 8.0                   # analysis window starts t_start − preroll (clamped ≥ 0)
T_START_MAX_LEAD_SEC = 240.0        # ignore beep patterns implausibly early (intro > 4 min)

# --------------------------------------------------------------------------- #
# Calibration (from preroll standing frames — fixes v1 "first frame" bug)
# --------------------------------------------------------------------------- #
CALIB_MIN_VIS = 0.5
CALIB_TORSO_UPRIGHT_DEG = 155.0     # hip-shoulder line vs vertical, standing
GROUND_MARGIN_H = 0.05              # "touching ground" tolerance, × body height

# --------------------------------------------------------------------------- #
# Thruster standards (Wodx rulebook)
# --------------------------------------------------------------------------- #
THR = {
    # Depth: hip-crease line must pass below knee-top line (image-y comparison,
    # calibrated 3/4 view). Hysteresis in units of body height H.
    "depth_enter_margin_h": 0.020,   # hip_y − knee_y ≥ +0.020H → valid depth reached
    "depth_exit_margin_h": 0.000,    # must rise above knee line to close the squat phase
    # Rack position (front rack): wrists at shoulder height, elbows bent.
    "rack_wrist_shoulder_tol_h": 0.16,
    "rack_elbow_angle_max_deg": 135.0,
    # Lockout: full extension of hips / knees / elbows + bar overhead.
    "lock_elbow_deg": 158.0,
    "lock_knee_deg": 158.0,
    "lock_hip_deg": 158.0,
    "overhead_wrist_above_nose_h": 0.00,  # wrist must be above nose (bar overhead)
    "bar_midline_tol_h": 0.14,       # |wrist_mid_x − shoulder_mid_x| ≤ tol (else review)
    # Continuity: no pause in standing-rack between squat and overhead press.
    "stand_rack_pause_sec": 0.35,    # bar parked at shoulders while fully standing ≥ this → break
    # No walking / feet must stay in one line under the body.
    "walk_drift_max_h": 0.09,        # ankle-mid x drift during one rep (beyond → no-rep)
    # Phase debounce
    "min_phase_sec": 0.20,
    "attempt_timeout_sec": 12.0,
}

# --------------------------------------------------------------------------- #
# Bar-facing burpee standards (Wodx rulebook)
# --------------------------------------------------------------------------- #
BFB = {
    # Chest (sternum) must touch the ground.
    "chest_touch_margin_h": 0.07,    # sternum_y ≥ ground_y − margin → touched
    # Facing: shoulder line must be roughly parallel to the bar (≈ horizontal
    # in image). Steep shoulder line = body parallel to bar = fault.
    "facing_shoulder_tilt_deg": 42.0,
    # Jump & landing
    "bar_cross_margin_h": 0.035,     # feet must clear bar anchor by this margin
    "land_simultaneity_sec": 0.13,   # both ankles grounded within this window
    "foot_ground_vel_tol_h": 0.25,   # ankle y-velocity threshold for "grounded"
    "trailing_check_window_sec": 0.35,
    # Bar contact risk (review flag only — asymmetric error policy)
    "bar_contact_margin_h": 0.035,
    # Phase debounce
    "min_phase_sec": 0.15,
    "attempt_timeout_sec": 15.0,
    # Descent fraction: chest must come down to ground, not just halfway
    "min_descent_h": 0.45,           # sternum drop from standing, × H (sanity gate)
}

# --------------------------------------------------------------------------- #
# Orchestrator (WOD sequencer) — TRANSITION guards & recovery
# --------------------------------------------------------------------------- #
SEQ = {
    "transition_confirm_reps": 2,     # credits of the next movement that confirm a block switch
    "transition_confirm_sec": 2.0,    # ... or 1 credit + this much inactivity of the old movement
    "stale_block_sec": 45.0,          # no activity at all for this long → flag review
    "cap_grace_sec": 0.0,             # reps must end ≤ t_start + cap (no grace — rulebook)
}

# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #
ANNOTATE_REVIEW_VIDEO = os.environ.get("JUDGE_ANNOTATE", "1") == "1"
REPORT_ENCODING = "utf-8"
