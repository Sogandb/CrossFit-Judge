"""
Global configuration for the CrossFit AI Judge.
All thresholds are tuned for a 45-degree camera angle (online competition standard).
"""
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
WORKOUTS_DIR = DATA_DIR / "workouts"
RESULTS_DIR = DATA_DIR / "results"
UPLOADS_DIR = DATA_DIR / "uploads"

for _d in (WORKOUTS_DIR, RESULTS_DIR, UPLOADS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Pose detection
# ---------------------------------------------------------------------------
POSE_MODEL_COMPLEXITY = 1          # 0=light, 1=full, 2=heavy
POSE_MIN_DETECTION_CONFIDENCE = 0.5
POSE_MIN_TRACKING_CONFIDENCE = 0.5
POSE_SMOOTHING = True

# A landmark is considered "visible enough" above this presence value.
LANDMARK_PRESENCE_THRESHOLD = 0.5

# ---------------------------------------------------------------------------
# Signal processing
# ---------------------------------------------------------------------------
# Moving-average window (in frames) for smoothing joint angles. Smaller = more
# responsive to fast movements (competition pace). 3 is a good balance.
SMOOTHING_WINDOW = 3

# ---------------------------------------------------------------------------
# Rep counting state machine
# ---------------------------------------------------------------------------
# Hysteresis margins (in degrees) to prevent flicker at the boundary.
HYSTERESIS_MARGIN = 4.0

# Number of consecutive frames a state must hold before it is committed.
# Lower = more responsive to fast reps; higher = more stable.
STATE_MIN_FRAMES = 2

# ---------------------------------------------------------------------------
# Timer / scoring
# ---------------------------------------------------------------------------
# Frames are processed at this target FPS. 15 is a good balance: fast enough
# to catch competition-paced reps, slow enough to keep processing time
# reasonable (a 60s video = 900 frames, ~2-3 min to process).
TARGET_FPS = 15

# When False, the workout timer starts at frame zero (the video start) so the
# reported time always equals the full video duration. This matches how online
# competition videos are reviewed (the whole clip is the workout evidence).
AUTO_START_TIMER = False

# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------
# The competition standard for online CrossFit events is a 45-degree angle.
CAMERA_ANGLE_DEGREES = 45

# ---------------------------------------------------------------------------
# Visualization
# ---------------------------------------------------------------------------
SKELETON_COLOR = (0, 255, 255)      # yellow
GOOD_REP_COLOR = (0, 255, 0)        # green
NO_REP_COLOR = (0, 0, 255)          # red
TEXT_COLOR = (255, 255, 255)        # white
TIMELINE_BG = (30, 30, 30)
