"""Verify suspected KB-swing hysteresis units bug + For Time trailing-footage scoring."""
import sys, os
sys.path.insert(0, "/home/z/my-project/repo-review/mini-services/crossfit-judge")

from core.pose_detector import PoseFrame
from utils.geometry import Point
from movements.kettlebell_swing import KettlebellSwing
from movements.pullup import Pullup
from movements.burpee import Burpee
from movements.pushup import Pushup
from movements.thruster import Thruster
from judging.scorer import Scorer
from movements.base_movement import RepEvent


def pf(**kw):
    """Build a PoseFrame from named (x, y) pairs."""
    p = PoseFrame(person_detected=True)
    for k, (x, y) in kw.items():
        p.points[k] = Point(x, y, 0.0, 1.0)
    return p


def kb_pose(t):
    """KB swing cycle: t=0 standing top (wrist high), 0.5 bell between legs (wrist low)."""
    # athlete: shoulders y=0.30, hips y=0.50, knees 0.70, ankles 0.95
    wrist_y = 0.30 + 0.35 * (0.5 - 0.5 * __import__('math').cos(2 * 3.14159 * t))
    return pf(
        nose=(0.5, 0.15),
        left_shoulder=(0.42, 0.30), right_shoulder=(0.58, 0.30),
        left_elbow=(0.40, 0.35), right_elbow=(0.60, 0.35),
        left_wrist=(0.40, wrist_y), right_wrist=(0.60, wrist_y),
        left_hip=(0.44, 0.50), right_hip=(0.56, 0.50),
        left_knee=(0.44, 0.70), right_knee=(0.56, 0.70),
        left_ankle=(0.44, 0.95), right_ankle=(0.56, 0.95),
        left_heel=(0.42, 0.97), right_heel=(0.58, 0.97),
        left_foot_index=(0.45, 0.99), right_foot_index=(0.55, 0.99),
    )


def feed(det, pose_fn, cycles=6, fpc=30):
    events = []
    idx = 0
    import math
    for c in range(cycles):
        for i in range(fpc):
            t = i / fpc
            ev = det.update(pose_fn(t))
            if ev: events.append(ev)
            idx += 1
        for _ in range(6):
            ev = det.update(pose_fn(0.0))
            if ev: events.append(ev)
            idx += 1
    return events


print("=" * 62)
print("[T1] Kettlebell swing — 6 full swings (wrist 0.30 <-> 0.65)")
print("     start_threshold=0.35, bottom_threshold=0.50 (ratio),")
print("     but base _classify_phase applies HYSTERESIS_MARGIN=4.0 (degrees)")
det = KettlebellSwing()
evs = feed(det, kb_pose)
print(f"     -> events counted: {len(evs)}, valid: {sum(1 for e in evs if e.valid)}")
print(f"     -> final phase: {det.phase}  (expected to be stuck in IDLE)")
print(f"     VERDICT: {'BUG CONFIRMED — no reps ever counted' if not evs else 'works'}")

print()
print("[T2] Same magnitude test with Burpee (overridden classifier) — sanity")
def burp_pose(t):
    import math
    if t < 0.5:
        k = t / 0.5
        chest_y = 0.20 + 0.60 * k
        wrist_y = 0.30 + 0.4 * k
        ankle_y = 0.95
    else:
        k = (t - 0.5) / 0.5
        chest_y = 0.80 - 0.60 * k
        wrist_y = 0.70 - 0.62 * k
        ankle_y = 0.95 - 0.05 * math.sin(math.pi * k)
    return pf(
        nose=(0.5, chest_y - 0.05),
        left_shoulder=(0.42, chest_y), right_shoulder=(0.58, chest_y),
        left_elbow=(0.40, chest_y + 0.08), right_elbow=(0.60, chest_y + 0.08),
        left_wrist=(0.40, wrist_y), right_wrist=(0.60, wrist_y),
        left_hip=(0.44, min(0.92, chest_y + 0.15)), right_hip=(0.56, min(0.92, chest_y + 0.15)),
        left_knee=(0.44, min(0.95, chest_y + 0.30)), right_knee=(0.56, min(0.95, chest_y + 0.30)),
        left_ankle=(0.44, ankle_y), right_ankle=(0.56, ankle_y),
        left_heel=(0.42, min(0.97, ankle_y + 0.02)), right_heel=(0.58, min(0.97, ankle_y + 0.02)),
        left_foot_index=(0.45, min(0.99, ankle_y + 0.04)), right_foot_index=(0.55, min(0.99, ankle_y + 0.04)),
    )
det2 = Burpee()
evs2 = feed(det2, burp_pose)
print(f"     -> events: {len(evs2)}, valid: {sum(1 for e in evs2 if e.valid)} (phase={det2.phase})")

print()
print("[T3] For Time scoring — finish time uses FULL video duration")
workout = {
    "name": "T", "format": "for_time", "time_cap_seconds": 300,
    "movements": [
        {"name": "squat", "reps_per_round": 5},
        {"name": "pushup", "reps_per_round": 10},
    ],
    "scoring": "time_to_complete",
}
sc = Scorer(workout)
events = []
for i in range(15):
    events.append(RepEvent(rep_number=i+1, movement="squat", start_time=0,
                           end_time=100.0 + i, valid=True, confidence=0.9))
score = sc.score(events, True, final_time=600.0)  # video runs 10 min, work done at ~114s
print(f"     work finished at ~114s, video is 600s")
print(f"     -> score_display: {score.score_display}, completed={score.completed}")
print(f"     VERDICT: {'BUG — finish time = trailing video duration' if score.score_display == '10:00' else 'check'}")

print()
print("[T4] Tabata — reps during REST intervals count toward score")
workout2 = {
    "name": "T2", "format": "tabata", "time_cap_seconds": 240,
    "movements": [{"name": "squat", "reps_per_round": 1}],
    "scoring": "reps_completed",
}
sc2 = Scorer(workout2)
evs3 = []
# 10 reps during work window (0-20s), 10 reps during rest (20-30s)
for i in range(10):
    evs3.append(RepEvent(rep_number=i+1, movement="squat", start_time=i*2,
                         end_time=i*2+1, valid=True, confidence=0.9))
for i in range(10):
    evs3.append(RepEvent(rep_number=i+11, movement="squat", start_time=20+i,
                         end_time=20+i+0.9, valid=True, confidence=0.9))
s2 = sc2.score(evs3, True, final_time=240.0)
print(f"     10 work-window reps + 10 rest-window reps -> score_display: {s2.score_display}")
print(f"     VERDICT: rest reps counted = scoring bug vs Tabata standard")
