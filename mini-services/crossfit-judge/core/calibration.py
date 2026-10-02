"""
Scene calibration from the preroll window [t_start − PREROLL, t_start).

Fixes the v1 "calibrate on first detected frame" bug: during the seconds
before the GO signal the athlete stands ready at the bar — the cleanest
calibration frames in the whole video. We pick the best upright, visible,
standing frame and derive:

  * H        — body height in pixels (scale reference for ALL thresholds)
  * ground   — linear y = a + b·x model fitted from standing foot contacts
  * bar hint — if the wrists rest near the floor (gripping the bar), seed
               the bar anchor
"""
from __future__ import annotations

from typing import Optional

from config.settings import CALIB_MIN_VIS, GROUND_MARGIN_H
from core.types import PoseFrame, SceneModel
from utils.geometry import midpoint


def _upright(p: PoseFrame) -> bool:
    sh_l, sh_r = p.get("left_shoulder"), p.get("right_shoulder")
    hip_l, hip_r = p.get("left_hip"), p.get("right_hip")
    if None in (sh_l, sh_r, hip_l, hip_r):
        return False
    sh, hip = midpoint(sh_l, sh_r), midpoint(hip_l, hip_r)
    if sh is None or hip is None:
        return False
    # torso near-vertical: shoulders almost directly above hips
    dx, dy = abs(sh.x - hip.x), (hip.y - sh.y)
    return dy > 0 and (dx / max(dy, 1e-6)) < 0.45


def calibrate(preroll_frames: list[PoseFrame], scene: SceneModel) -> bool:
    """Fill `scene` from preroll frames. Returns True on success."""
    candidates = [
        f for f in preroll_frames
        if f.person_detected and _upright(f) and _min_vis(f) >= CALIB_MIN_VIS
    ]
    if not candidates:
        return False

    # best frame = highest average visibility of the skeleton
    best = max(candidates, key=_min_vis)
    nose = best.get("nose")
    ank = best.mid("left_ankle", "right_ankle")
    if nose is None or ank is None:
        return False
    H = max(50.0, ank.y - nose.y)  # standing height in px
    scene.H = H

    # ground model: collect foot-contact samples across the preroll
    xs, ys = [], []
    for f in candidates:
        for side in ("left", "right"):
            heel, ank_l, fi = f.get(f"{side}_heel"), f.get(f"{side}_ankle"), f.get(f"{side}_foot_index")
            pts = [q for q in (heel, ank_l, fi) if q is not None and q.visibility >= CALIB_MIN_VIS]
            if not pts:
                continue
            y = max(q.y for q in pts)   # lowest point of the foot
            x = sum(q.x for q in pts) / len(pts)
            xs.append(x)
            ys.append(y)
    if len(xs) >= 2 and (max(xs) - min(xs)) > 0.15 * H:
        # enough horizontal spread → fit a sloped line
        n = len(xs)
        mx, my = sum(xs) / n, sum(ys) / n
        denom = sum((x - mx) ** 2 for x in xs) or 1e-9
        b = sum((xs[i] - mx) * (ys[i] - my) for i in range(n)) / denom
        scene.set_ground(my - b * mx, b)
    elif xs:
        scene.set_ground(sum(ys) / len(ys), 0.0)
    else:
        # last resort: ground under the standing feet of the best frame
        gy = max(best.get("left_heel").y, best.get("right_heel").y)
        scene.set_ground(gy, 0.0)

    # bar hint: wrists resting near the ground (athlete gripping the bar)
    wr = best.mid("left_wrist", "right_wrist")
    if wr is not None and wr.visibility >= CALIB_MIN_VIS:
        gy = scene.ground_y_at(wr.x)
        if gy is not None and wr.y >= gy - 0.15 * H:
            scene.set_bar(wr.x, gy, confidence=0.4)
    return True


def _min_vis(p: PoseFrame) -> float:
    keys = ("nose", "left_shoulder", "right_shoulder", "left_hip", "right_hip",
            "left_knee", "right_knee", "left_ankle", "right_ankle")
    vals = [p.points[k].visibility for k in keys if k in p.points]
    return min(vals) if vals else 0.0


def online_ground_update(scene: SceneModel, p: PoseFrame, samples: list[tuple[float, float]],
                         max_samples: int = 240) -> None:
    """Analyzer hook: accumulate fresh foot-contact samples and refit the
    ground line (people move along the floor; perspective changes ground y)."""
    if not p.person_detected:
        return
    if scene.H <= 0:
        return
    for side in ("left", "right"):
        ank, heel = p.get(f"{side}_ankle"), p.get(f"{side}_heel")
        if ank is None or heel is None or ank.visibility < 0.5:
            continue
        if abs(ank.y - heel.y) > 0.12 * scene.H:   # foot lifted → not a contact
            continue
        samples.append((ank.x, max(ank.y, heel.y)))
    if len(samples) > max_samples:
        del samples[: len(samples) - max_samples]
    if len(samples) >= 6:
        n = len(samples)
        xs = [s[0] for s in samples]
        ys = [s[1] for s in samples]
        mx, my = sum(xs) / n, sum(ys) / n
        if max(xs) - min(xs) > 0.2 * scene.H:
            denom = sum((x - mx) ** 2 for x in xs) or 1e-9
            b = sum((xs[i] - mx) * (ys[i] - my) for i in range(n)) / denom
            scene.set_ground(my - b * mx, b)
        else:
            scene.set_ground(my, 0.0)
