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
DATA_DIR = SERVICE_ROOT / "data"                 # read-only reference data (shipped)
MODELS_DIR = DATA_DIR / "models"
WODS_DIR = DATA_DIR / "wods"
# Runtime STATE (uploads, review videos, results DB). In Docker this is a
# volume (JUDGE_STATE_DIR=/state) so reference data never gets shadowed.
STATE_DIR = Path(os.environ.get("JUDGE_STATE_DIR") or DATA_DIR)
UPLOADS_DIR = STATE_DIR / "uploads"
DB_PATH = STATE_DIR / "judge_v2.db"
# Videos + results older than this are deleted automatically (0 = keep forever).
RETENTION_DAYS = float(os.environ.get("JUDGE_RETENTION_DAYS", "30"))

# --------------------------------------------------------------------------- #
# Service
# --------------------------------------------------------------------------- #
SERVICE_PORT = int(os.environ.get("JUDGE_PORT", "8001"))
MAX_UPLOAD_BYTES = int(os.environ.get("JUDGE_MAX_UPLOAD_BYTES", 500 * 1024 * 1024))  # 500 MB (Wodx requirement)
WORKER_CONCURRENCY = int(os.environ.get("JUDGE_WORKERS", "2"))  # bounded pool (fixes v1 unlimited concurrency)

# --------------------------------------------------------------------------- #
# Video ingest gates
# --------------------------------------------------------------------------- #
TARGET_FPS = 15.0            # analysis frame rate (CFR, fixes v1 VFR drift).
                              # 15 fps halves the pose-inference budget; all
                              # movement thresholds are TIME-based (ctx.t), so
                              # judging behavior is fps-agnostic by design.
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
# JUDGING POLICY — "benefit of the doubt goes to the athlete"
#
# CrossFit video-review standard: an automatic no-rep requires a CLEAR,
# high-confidence violation. Everything inside the measurement-uncertainty
# band (borderline) is CREDITED with a review flag + reduced confidence.
# This two-band policy (clear / borderline) is applied to every check below.
# --------------------------------------------------------------------------- #
JUDGE = {
    "borderline_cap": 0.82,   # max confidence credited via a borderline band
    "low_vis_cap": 0.60,      # max confidence when landmark visibility is poor
    "vis_soft": 0.55,         # below this, confidence starts degrading
    "vis_floor": 0.35,        # below this, measurement is unreliable
}

# --------------------------------------------------------------------------- #
# v2.1 — LENIENCY KNOB ("حداقل ۵۰٪ آسان‌تر از آیین‌نامه") and CLOCK MODE
#
# EASE widens every automatic NO-REP line by (EASE x a reference slack) on top
# of the benefit-of-the-doubt bands. EASE = 0.5 -> every no-rep line sits 50 %
# of its reference slack further from the rulebook ideal. 0 = rulebook-strict.
# One knob, retunable from the environment WITHOUT touching judging code:
#     JUDGE_EASE=0.35 python main.py
# CALIBRATE on the golden dataset (real Wodx videos): the number to optimise
# is "false no-reps on valid reps", not accuracy.
# --------------------------------------------------------------------------- #
EASE = max(0.0, min(1.0, float(os.environ.get("JUDGE_EASE", "0.5"))))

# Workout clock: starts at the VIDEO START (t = 0) and stops at the last rep
# or at the time cap, whichever comes first. A manual start (UI field) still
# overrides; beep detection is opt-in (JUDGE_USE_BEEP=1) because the clock the
# athlete uploads is, by Wodx protocol, the clock of the video itself.
CLOCK_FROM_VIDEO_START = os.environ.get("JUDGE_USE_BEEP", "0") != "1"
CALIB_WARMUP_SEC = 2.0     # first seconds buffered for calibration when no preroll exists
POST_CAP_TAIL_SEC = 20.0   # analysed after the cap only to LOG post-cap reps

# --------------------------------------------------------------------------- #
# Thruster standards (Wodx rulebook / CrossFit reference)
# --------------------------------------------------------------------------- #
THR = {
    # Depth: hip-crease line must pass below knee-top line (image-y comparison,
    # calibrated 3/4 view). Hysteresis in units of body height H.
    "depth_enter_margin_h": 0.020,   # hip_y − knee_y ≥ +0.020H → valid depth reached
    # v2.1: hip may sit up to 0.14H*EASE (=0.07H, ~12 cm) ABOVE the knee line
    # and the rep is still credited (review-flagged). Rulebook: below parallel.
    "depth_bod_margin_h": -0.14 * EASE,
    "depth_exit_margin_h": 0.000,    # must rise above knee line to close the squat phase
    # Pattern gate: a REAL thruster attempt must show at least this squat
    # descent (fractions of H) — anything less is transition noise, not judged.
    "min_squat_h": 0.060,
    # ...and at the deepest squat moment the hands must be holding the bar
    # at least this high above the floor (×H) — hands still at floor level
    # at depth = burpee crouch / hand-plant, NOT a thruster.
    "bar_held_h": 0.220,
    # Rack position (front rack): wrists at shoulder height, elbows bent.
    "rack_wrist_shoulder_tol_h": 0.16,
    "rack_elbow_angle_max_deg": 135.0,
    # Lockout: hips / knees / elbows extended + bar overhead.
    # 2D elbow angle is UNRELIABLE when the bar is overhead (foreshortening +
    # far-arm occlusion in 3/4 view) — so the hard no-rep only fires on CLEAR
    # violations; the nominal standard band becomes borderline (credit+review).
    "lock_elbow_deg": 158.0,         # nominal standard
    "lock_elbow_clear_deg": 158.0 - 60.0 * EASE,   # 128 deg at EASE .5 (was 138)
    "lock_knee_deg": 158.0,
    "lock_knee_clear_deg": 158.0 - 50.0 * EASE,    # 133 deg (was 140)
    "lock_hip_deg": 158.0,
    "lock_hip_clear_deg": 158.0 - 50.0 * EASE,     # 133 deg (was 142)
    # Robust 2D overhead evidence: wrists clearly above the shoulder line
    # (works in front AND side view, immune to elbow foreshortening).
    "overhead_reach_min_h": 0.060,
    "overhead_bod_floor_h": 0.030 * (1.0 - EASE),   # 0.015H: bar barely above shoulder still credited (was 0.030)
    # Mid-line: bar over the middle of the body at lockout (review flag only —
    # 3/4-view x-projection makes this a soft check).
    "bar_midline_tol_h": 0.14,
    # Chest must stay above the floor for a thruster attempt to arm
    # (posture gate — burpee floor work keeps the chest under ~0.15H; a
    # clean-pull setup keeps it above ~0.2H).
    "chest_floor_gate_h": 0.180,
    # Continuity: no pause in standing-rack between squat and overhead press.
    # NOT eased: this value is also the CLOSING trigger of an attempt whose
    # bar returned to the rack (easing it left such attempts open until the
    # 12 s timeout). Jerk strictness is relaxed in the sequencer-free way below.
    "stand_rack_pause_sec": 0.60,
    # No walking / feet must stay in one line under the body (clear fault only).
    "walk_drift_max_h": 0.150 * (1.0 + 2.0 * EASE),      # 0.30H (was 0.15H)
    "walk_drift_review_h": 0.090 * (1.0 + 2.0 * EASE),   # beyond this → review flag
    # Phase debounce
    "min_phase_sec": 0.20,
    "attempt_timeout_sec": 12.0,
}

# --------------------------------------------------------------------------- #
# Bar-facing burpee standards (Wodx rulebook / CrossFit 22.2 reference)
# --------------------------------------------------------------------------- #
BFB = {
    # Chest (sternum) must touch the ground. The SHOULDER landmark sits
    # ~0.10-0.15H above the floor even when the chest IS down (body thickness
    # + shoulder joint geometry) — the old 0.07H margin no-repped valid reps.
    "chest_touch_margin_h": 0.20,     # sternum_y ≥ ground_y − margin → touched
    # 0.20-0.33H -> borderline (credit + review). NOTE: a plank-top shoulder
    # sits ~0.30-0.35H above the floor, so this is deliberately NOT eased
    # further: relaxing past it would credit burpees with no descent at all.
    "chest_bod_margin_h": 0.30 + 0.06 * EASE,
    "chest_plausible_h": 0.35,        # never within 0.35H → not a burpee at all (discard)
    # Facing: shoulder-line tilt is a camera-geometry assumption (unreliable in
    # side view). Auto no-rep ONLY on a clearly parallel body (sustained steep
    # tilt); everything else is at most a review flag.
    "facing_shoulder_tilt_deg": 42.0,     # nominal band (review flag only)
    "facing_clear_tilt_deg": 68.0 + 12.0 * EASE,    # 74 deg
    "facing_min_frac": 0.28,              # fraction of attempt frames steeply tilted
    # Jump & landing
    "bar_cross_margin_h": 0.035,     # feet must clear bar anchor by this margin
    # no-jump fault needs this many single-foot airborne frames (was 4)
    "no_jump_one_air_frames": int(round(4 * (1.0 + 2.0 * EASE))),
    "bar_cross_clear_h": 0.120 * (1.0 + EASE),   # 0.18H (was 0.12H)
    "land_simultaneity_sec": 0.18 * (1.0 + EASE),   # 0.27 s
    "land_clear_sec": 0.28 * (1.0 + EASE),          # 0.42 s
    "foot_ground_vel_tol_h": 0.25,   # ankle y-velocity threshold for "grounded"
    "trailing_check_window_sec": 0.35,
    # Bar contact risk (review flag only — asymmetric error policy)
    "bar_contact_margin_h": 0.035,
    # Phase debounce
    "min_phase_sec": 0.15,
    "attempt_timeout_sec": 15.0,
    # Descent fraction: chest must come down to ground, not just halfway
    # (sanity gate for a REAL burpee pattern).
    "min_descent_h": 0.450,          # sternum drop from standing, × H
    "descent_max_sec": 6.0,          # a drop that never reaches the floor in 6s = not a burpee
    "next_drop_dist_h": 0.160,       # chest within this of the floor AND sinking = next descent began
    # v2.1: the sequencer KNOWS a burpee is expected, so the descent may start
    # from a bent-over / hands-on-knees stance (energy saving). Arm on a
    # sternum drop measured from the highest sternum seen in the last N s,
    # whatever the posture.
    "bent_baseline_window_sec": 6.0,
    "bent_clear_floor_h": 0.45,   # sternum above this = not floor work (plank-top is ~0.30-0.35H)
    "arm_drop_h": 0.10,
}

# --------------------------------------------------------------------------- #
# Orchestrator (WOD sequencer v3) — the USER'S EXACT state machine:
# global counter 1..126, every expected-movement ATTEMPT consumes a slot
# (rep or no-rep), switch exactly at the prescribed counts. These parameters
# only govern the STALL RECOVERY: when the FSM under-detected the tail of a
# phase and the athlete has verifiably moved on to the NEXT movement.
# --------------------------------------------------------------------------- #
SEQ = {
    "switch_stream": 2,          # held next-movement attempts confirming the athlete moved on
    "switch_quiet_sec": 4.0,     # expected movement quiet this long before recovering
    "probe_quiet_sec": 3.0,      # v2.1: expected FSM quiet this long -> arm the next FSM as a probe
    "hold_buffer_max": 15,       # bound on held noise (pathological detection)
    "dup_overlap_tol_sec": 1.0,  # held attempt may start this early before the last slot's end
                                 # and still count as the next phase's first real attempt
    "cap_grace_sec": 0.0,        # reps must end ≤ t_start + cap (no grace — rulebook)
}

# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #
ANNOTATE_REVIEW_VIDEO = os.environ.get("JUDGE_ANNOTATE", "1") == "1"
REPORT_ENCODING = "utf-8"
