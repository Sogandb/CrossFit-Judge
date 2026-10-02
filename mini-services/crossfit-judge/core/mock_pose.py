"""
Synthetic pose-stream generator for tests and pipeline smoke runs.

Builds PoseFrame timelines that drive the movement FSMs through exact,
controlled signal patterns (depth margins, rack/overhead geometry, foot
airborne timelines). This is how the judging logic is regression-tested
without real videos — MediaPipe is exercised separately on real footage.

Coordinate system: y grows DOWNWARD (image space). gy = ground line.
"""
from __future__ import annotations

from typing import Optional

from core.types import PoseFrame
from utils.geometry import Point

VIS = 0.92


def _pt(x: float, y: float) -> Point:
    return Point(x, y, 0.0, VIS)


def _elbow_at(sh: tuple, wr: tuple, target_deg: float) -> tuple:
    """Place an elbow so that angle(sh, elbow, wr) == target_deg.
    Used for exact control of the elbow-angle signal in tests."""
    import math
    mx, my = (sh[0] + wr[0]) / 2.0, (sh[1] + wr[1]) / 2.0
    L = math.hypot(wr[0] - sh[0], wr[1] - sh[1]) or 1e-6
    half = L / 2.0
    if target_deg >= 179.0:
        return (mx, my)
    d = half / math.tan(math.radians(target_deg / 2.0))
    dx, dy = wr[0] - sh[0], wr[1] - sh[1]
    n = math.hypot(dx, dy) or 1.0
    px, py = -dy / n, dx / n
    # bulge downward/forward in image space (elbows under the bar in rack)
    if py * (1 if sh[1] < wr[1] else -1) < 0:
        px, py = -px, -py
    return (mx + px * d, my + py * d)


def _lerp(a: float, b: float, u: float) -> float:
    return a + (b - a) * max(0.0, min(1.0, u))


def _ease(u: float) -> float:
    u = max(0.0, min(1.0, u))
    return u * u * (3 - 2 * u)  # smoothstep


class SkeletonBuilder:
    """Parametric standing-forward skeleton facing the camera's 3/4 view."""

    def __init__(self, x: float, gy: float, H: float):
        self.x, self.gy, self.H = x, gy, H

    def build(
        self,
        sh_y: Optional[float] = None,
        hip_y: Optional[float] = None,
        knee_y: Optional[float] = None,
        ankle_y: Optional[float] = None,
        ankle_x_offset: float = 0.0,
        wrist_mode: str = "hang",       # hang | rack | overhead | ground | free
        wrist_y: Optional[float] = None,
        tilt_deg: float = 0.0,          # shoulder-line tilt (facing check)
        foot_y: Optional[tuple] = None,  # (left_y, right_y) explicit
        foot_x: Optional[tuple] = None,  # (left_x, right_x) explicit
        elbow_straight: bool = False,
        sh_x_offset: float = 0.0,       # torso lean (bent-over poses)
        body_x_offset: float = 0.0,     # whole-body lateral shift (walking)
        overhead_elbow_deg: float = 176.0,  # precise elbow angle when overhead
    ) -> dict[str, Point]:
        H = self.H
        x = self.x
        sh_y = sh_y if sh_y is not None else self.gy - 0.82 * H
        hip_y = hip_y if hip_y is not None else self.gy - 0.50 * H
        knee_y = knee_y if knee_y is not None else self.gy - 0.26 * H
        ankle_y = ankle_y if ankle_y is not None else self.gy
        tilt = tilt_deg
        dx_sh = 0.07 * H
        # shoulder tilt: raise L, lower R (positive tilt)
        sh_l = (x - dx_sh + sh_x_offset, sh_y - (0.5 * (tilt / 45.0)) * 0.5 * H)
        sh_r = (x + dx_sh + sh_x_offset, sh_y + (0.5 * (tilt / 45.0)) * 0.5 * H)
        hip_l = (x - 0.055 * H, hip_y)
        hip_r = (x + 0.055 * H, hip_y)
        knee_l = (x - 0.05 * H, knee_y)
        knee_r = (x + 0.05 * H, knee_y)
        if foot_y is not None:
            ank_l = (foot_x[0] if foot_x else x - 0.06 * H, foot_y[0])
            ank_r = (foot_x[1] if foot_x else x + 0.06 * H, foot_y[1])
        else:
            ank_l = (x - 0.06 * H + ankle_x_offset, ankle_y)
            ank_r = (x + 0.06 * H + ankle_x_offset, ankle_y)
        heel_l = (ank_l[0] + 0.02 * H, ank_l[1])
        heel_r = (ank_r[0] + 0.02 * H, ank_r[1])
        fi_l = (ank_l[0] - 0.03 * H, ank_l[1] + 0.005 * H)
        fi_r = (ank_r[0] + 0.03 * H, ank_r[1] + 0.005 * H)
        nose = (x, sh_y - 0.18 * H)

        wr_l = wr_r = el_l = el_r = None
        if wrist_mode == "hang":
            el_l = (x - 0.10 * H, sh_y + 0.14 * H)
            el_r = (x + 0.10 * H, sh_y + 0.14 * H)
            wr_l = (x - 0.09 * H, sh_y + 0.26 * H)
            wr_r = (x + 0.09 * H, sh_y + 0.26 * H)
        elif wrist_mode == "rack":
            # wrists at shoulder height, elbows at a precise ~95° (front rack)
            wr_l = (x - 0.045 * H, sh_y + 0.015 * H)
            wr_r = (x + 0.045 * H, sh_y + 0.015 * H)
            el_l = _elbow_at(sh_l, wr_l, 95.0)
            el_r = _elbow_at(sh_r, wr_r, 95.0)
        elif wrist_mode == "overhead":
            wy = wrist_y if wrist_y is not None else nose[1] - 0.10 * H
            wr_l = (x - 0.025 * H, wy)
            wr_r = (x + 0.025 * H, wy)
            target = 176.0 if (elbow_straight or overhead_elbow_deg >= 170) \
                else overhead_elbow_deg
            el_l = _elbow_at(sh_l, wr_l, target)
            el_r = _elbow_at(sh_r, wr_r, target)
        elif wrist_mode == "ground":
            gy = self.gy
            wr_l = (x - 0.045 * H, gy - 0.04 * H)
            wr_r = (x + 0.045 * H, gy - 0.04 * H)
            el_l = _elbow_at(sh_l, wr_l, 120.0)
            el_r = _elbow_at(sh_r, wr_r, 120.0)
        elif wrist_mode == "free":
            el_l = (x - 0.10 * H, (wrist_y or sh_y) - 0.10 * H)
            el_r = (x + 0.10 * H, (wrist_y or sh_y) - 0.10 * H)
            wr_l = (x - 0.09 * H, wrist_y if wrist_y is not None else sh_y)
            wr_r = (x + 0.09 * H, wrist_y if wrist_y is not None else sh_y)

        pts = {
            "nose": _pt(nose[0] + body_x_offset, nose[1]),
            "left_shoulder": _pt(sh_l[0] + body_x_offset, sh_l[1]),
            "right_shoulder": _pt(sh_r[0] + body_x_offset, sh_r[1]),
            "left_elbow": _pt(el_l[0] + body_x_offset, el_l[1]) if el_l else None,
            "right_elbow": _pt(el_r[0] + body_x_offset, el_r[1]) if el_r else None,
            "left_wrist": _pt(wr_l[0] + body_x_offset, wr_l[1]) if wr_l else None,
            "right_wrist": _pt(wr_r[0] + body_x_offset, wr_r[1]) if wr_r else None,
            "left_hip": _pt(hip_l[0] + body_x_offset, hip_l[1]),
            "right_hip": _pt(hip_r[0] + body_x_offset, hip_r[1]),
            "left_knee": _pt(knee_l[0] + body_x_offset, knee_l[1]),
            "right_knee": _pt(knee_r[0] + body_x_offset, knee_r[1]),
            "left_ankle": _pt(ank_l[0] + body_x_offset, ank_l[1]),
            "right_ankle": _pt(ank_r[0] + body_x_offset, ank_r[1]),
            "left_heel": _pt(heel_l[0] + body_x_offset, heel_l[1]),
            "right_heel": _pt(heel_r[0] + body_x_offset, heel_r[1]),
            "left_foot_index": _pt(fi_l[0] + body_x_offset, fi_l[1]),
            "right_foot_index": _pt(fi_r[0] + body_x_offset, fi_r[1]),
        }
        return {k: v for k, v in pts.items() if v is not None}


def pose_frame(points: dict[str, Point], t: float, idx: int,
               person: bool = True) -> PoseFrame:
    return PoseFrame(points=points, frame_index=idx, timestamp=t,
                     person_detected=person)


# --------------------------------------------------------------------------- #
# Thruster rep generator
# --------------------------------------------------------------------------- #
def gen_thruster_rep(out: list, t0: float, x: float, gy: float, H: float,
                     idx0: int, fps: float = 30.0,
                     depth_h: float = 0.035,
                     lockout: bool = True,
                     overhead: bool = True,
                     jerk: bool = False,
                     walk_h: float = 0.0,
                     entry: str = "rack",
                     wrist_to_knees: bool = False,
                     end_mode: str = "rack") -> float:
    """Emit one thruster rep; returns the end time."""
    sb = SkeletonBuilder(x, gy, H)
    dt = 1.0 / fps
    t = t0
    idx = idx0
    knee_y = gy - 0.26 * H
    hip_bottom = knee_y + depth_h * H
    hip_top = gy - 0.50 * H
    walk_dx = walk_h * H

    def emit(**kw) -> float:
        nonlocal t, idx
        out.append(pose_frame(sb.build(**kw), t, idx))
        t += dt
        idx += 1
        return t

    def emit_many(n: int, **kw) -> None:
        for _ in range(n):
            emit(**kw)

    # ---- entry ----
    if entry == "ground":
        # bend over the bar (shoulders forward & below hips), pull from floor
        for u in np_linspace(0, 1, 8):
            emit(hip_y=_lerp(hip_top, gy - 0.46 * H, u),
                 sh_y=_lerp(gy - 0.82 * H, gy - 0.20 * H, u),
                 sh_x_offset=0.25 * H,
                 knee_y=knee_y, ankle_y=gy, wrist_mode="ground")
        emit_many(3, hip_y=gy - 0.46 * H, sh_y=gy - 0.20 * H,
                  sh_x_offset=0.25 * H, knee_y=knee_y, ankle_y=gy,
                  wrist_mode="ground")
        # catch directly at the bottom (squat clean)
        for u in np_linspace(0, 1, 8):
            emit(hip_y=hip_bottom, sh_y=hip_bottom - 0.32 * H,
                 knee_y=knee_y, ankle_y=gy, wrist_mode="rack")
        emit_many(4, hip_y=hip_bottom, sh_y=hip_bottom - 0.32 * H, knee_y=knee_y,
                  ankle_y=gy, wrist_mode="rack")
    else:
        # settle in the rack, standing
        emit_many(6, hip_y=hip_top, knee_y=knee_y, ankle_y=gy, wrist_mode="rack")
        # descent
        for u in np_linspace(0, 1, 16):
            emit(hip_y=_lerp(hip_top, hip_bottom, _ease(u)),
                 sh_y=_lerp(hip_top, hip_bottom, _ease(u)) - 0.32 * H,
                 knee_y=knee_y, ankle_y=gy, wrist_mode="rack",
                 body_x_offset=walk_dx * u)
        # bottom hold
        emit_many(4, hip_y=hip_bottom, sh_y=hip_bottom - 0.32 * H,
                  knee_y=knee_y, ankle_y=gy, wrist_mode="rack",
                  body_x_offset=walk_dx)
        if wrist_to_knees:
            # fault rehearsal: wrists resting near the knees at the bottom
            emit_many(4, hip_y=hip_bottom, sh_y=hip_bottom - 0.32 * H,
                      knee_y=knee_y, ankle_y=gy, wrist_mode="free",
                      wrist_y=knee_y + 0.02 * H, body_x_offset=walk_dx)

    # ---- ascent ----
    nose_y_top = (hip_top - 0.32 * H) - 0.18 * H
    if jerk:
        # full squat up to standing with the bar parked at the shoulders
        for u in np_linspace(0, 1, 14):
            emit(hip_y=_lerp(hip_bottom, hip_top, _ease(u)),
                 sh_y=_lerp(hip_bottom - 0.32 * H, hip_top - 0.32 * H, _ease(u)),
                 knee_y=knee_y, ankle_y=gy, wrist_mode="rack",
                 body_x_offset=walk_dx)
        emit_many(16, hip_y=hip_top, sh_y=hip_top - 0.32 * H, knee_y=knee_y,
                  ankle_y=gy, wrist_mode="rack", body_x_offset=walk_dx)  # PAUSE
        # re-dip and jerk the bar overhead
        for u in np_linspace(0, 1, 6):
            emit(hip_y=_lerp(hip_top, hip_top + 0.06 * H, u),
                 sh_y=hip_top - 0.32 * H + 0.06 * H * u, knee_y=knee_y,
                 ankle_y=gy, wrist_mode="rack", body_x_offset=walk_dx)
        for u in np_linspace(0, 1, 8):
            wy = _lerp(hip_top - 0.32 * H + 0.02 * H, nose_y_top - 0.10 * H, u)
            emit(hip_y=_lerp(hip_top + 0.06 * H, hip_top, u),
                 sh_y=hip_top - 0.32 * H, knee_y=knee_y, ankle_y=gy,
                 wrist_mode="overhead", wrist_y=wy, overhead_elbow_deg=176.0,
                 body_x_offset=walk_dx)
        emit_many(8, hip_y=hip_top, sh_y=hip_top - 0.32 * H, knee_y=knee_y,
                  ankle_y=gy, wrist_mode="overhead", wrist_y=nose_y_top - 0.10 * H,
                  overhead_elbow_deg=176.0, body_x_offset=walk_dx)
    else:
        # continuous drive: squat → overhead in one motion
        nose_y = nose_y_top
        for u in np_linspace(0, 1, 20):
            hu = _ease(u)
            hip_y = _lerp(hip_bottom, hip_top, hu)
            sh_y = hip_y - 0.32 * H
            if u < 0.55:
                emit(hip_y=hip_y, sh_y=sh_y, knee_y=knee_y, ankle_y=gy,
                     wrist_mode="rack", body_x_offset=walk_dx * u)
            else:
                wu = (u - 0.55) / 0.45
                wy = _lerp(sh_y + 0.015 * H,
                           nose_y - (0.10 * H if overhead else -0.05 * H),
                           _ease(wu))
                emit(hip_y=hip_y, sh_y=sh_y, knee_y=knee_y, ankle_y=gy,
                     wrist_mode="overhead", wrist_y=wy,
                     overhead_elbow_deg=176.0 if lockout else 140.0,
                     body_x_offset=walk_dx * u)
        # lockout hold
        emit_many(8, hip_y=hip_top, sh_y=hip_top - 0.32 * H, knee_y=knee_y,
                  ankle_y=gy, wrist_mode="overhead",
                  wrist_y=nose_y - (0.10 * H if overhead else -0.05 * H),
                  overhead_elbow_deg=176.0 if lockout else 140.0,
                  body_x_offset=walk_dx)
    # ---- exit ----
    if end_mode == "drop":
        for u in np_linspace(0, 1, 6):
            emit(hip_y=hip_top, sh_y=hip_top - 0.32 * H, knee_y=knee_y,
                 ankle_y=gy, wrist_mode="ground", body_x_offset=walk_dx)
        emit_many(4, hip_y=hip_top, sh_y=hip_top - 0.32 * H, knee_y=knee_y,
                  ankle_y=gy, wrist_mode="hang", body_x_offset=walk_dx)
    else:
        for u in np_linspace(0, 1, 8):
            emit(hip_y=hip_top, sh_y=hip_top - 0.32 * H, knee_y=knee_y,
                 ankle_y=gy, wrist_mode="rack", body_x_offset=walk_dx)
    return t


# --------------------------------------------------------------------------- #
# Bar-facing burpee rep generator
# --------------------------------------------------------------------------- #
def gen_bfb_rep(out: list, t0: float, x: float, gy: float, H: float,
                idx0: int, bar_x: float, fps: float = 30.0,
                chest_touch: bool = True,
                facing: bool = True,
                landing_mode: str = "two",
                #  "two"            — two-foot takeoff & landing (default)
                #  "stagger_takeoff" — legal one-foot takeoff, simultaneous landing
                #  "stagger_landing" — simultaneous takeoff, staggered landing (fault)
                #  "trailing"       — lead lands while trail still grounded (fault)
                cross: bool = True,
                jump_arc_h: float = 0.30) -> float:
    """Emit one bar-facing burpee from side (x); returns the end time.

    The athlete starts at x (on one side of the bar), does a burpee and
    jumps over to the other side. Bar sits at bar_x on the ground.
    """
    sb = SkeletonBuilder(x, gy, H)
    dt = 1.0 / fps
    t = t0
    idx = idx0
    side = -1 if x < bar_x else +1
    land_x = bar_x - side * 0.55 * H   # opposite side of the bar
    if not cross:
        land_x = x + side * 0.05 * H   # barely moves — no crossing

    def emit(**kw) -> float:
        nonlocal t, idx
        out.append(pose_frame(sb.build(**kw), t, idx))
        t += dt
        idx += 1
        return t

    def emit_many(n: int, **kw) -> None:
        for _ in range(n):
            emit(**kw)

    hip_top = gy - 0.50 * H
    knee_y = gy - 0.26 * H
    # ---- stand facing the bar (shoulders horizontal → tilt ≈ 0) ----
    emit_many(5, hip_y=hip_top, knee_y=knee_y, ankle_y=gy, wrist_mode="hang")
    # ---- descent to the floor ----
    tilt = 0.0 if facing else 55.0
    stern_floor = gy - 0.02 * H if chest_touch else gy - 0.13 * H
    for u in np_linspace(0, 1, 22):
        su = _ease(u)
        sh_y = _lerp(gy - 0.82 * H, stern_floor, su)
        hip_y = _lerp(hip_top, gy - 0.28 * H, su)
        emit(hip_y=hip_y, sh_y=sh_y, knee_y=_lerp(knee_y, gy - 0.12 * H, su),
             ankle_y=gy, wrist_mode="hang", tilt_deg=tilt * (1.0 if u > 0.25 else 0))
    # ---- floor hold (chest down) ----
    emit_many(5, hip_y=gy - 0.28 * H, sh_y=stern_floor, knee_y=gy - 0.12 * H,
              ankle_y=gy, wrist_mode="hang", tilt_deg=tilt)
    # ---- rise ----
    for u in np_linspace(0, 1, 18):
        su = _ease(u)
        emit(hip_y=_lerp(gy - 0.28 * H, hip_top, su),
             sh_y=_lerp(stern_floor, gy - 0.80 * H, su),
             knee_y=_lerp(gy - 0.12 * H, knee_y, su),
             ankle_y=gy, wrist_mode="hang", tilt_deg=tilt * (1 - su))
    emit_many(3, hip_y=hip_top, sh_y=gy - 0.80 * H, knee_y=knee_y, ankle_y=gy,
              wrist_mode="hang")
    # ---- jump & cross ----
    air_y = gy - jump_arc_h * H
    n_arc = 12

    def arc_y(u: float) -> float:
        return _lerp(gy, air_y, min(1.0, u * 2 if u < 0.5 else (1 - u) * 2))

    def emit_stand(feet_x: float) -> None:
        emit_many(6, hip_y=hip_top, sh_y=gy - 0.80 * H, knee_y=knee_y,
                  ankle_y=gy, ankle_x_offset=feet_x - x, wrist_mode="hang")

    if landing_mode == "two":
        # both feet lift and land together
        for i in range(n_arc):
            u = i / (n_arc - 1)
            fy, fx = arc_y(u), _lerp(x, land_x, _ease(u))
            emit(hip_y=hip_top, sh_y=gy - 0.80 * H, knee_y=knee_y,
                 wrist_mode="hang", foot_y=(fy, fy),
                 foot_x=(fx - 0.06 * H, fx + 0.06 * H))
        emit_stand(land_x)
    elif landing_mode == "stagger_takeoff":
        # L lifts 4 frames early (one-foot takeoff), R joins mid-air,
        # both land on the same frame
        for i in range(n_arc):
            u = i / (n_arc - 1)
            fy, fx = arc_y(u), _lerp(x, land_x, _ease(u))
            l_up = fy < gy - 0.09 * H
            if i < 4:
                emit(hip_y=hip_top, sh_y=gy - 0.80 * H, knee_y=knee_y,
                     wrist_mode="hang", foot_y=(fy, gy),
                     foot_x=(fx - 0.06 * H, x + 0.06 * H))
            else:
                emit(hip_y=hip_top, sh_y=gy - 0.80 * H, knee_y=knee_y,
                     wrist_mode="hang", foot_y=(fy, fy),
                     foot_x=(fx - 0.06 * H, fx + 0.06 * H))
        emit_stand(land_x)
    elif landing_mode == "stagger_landing":
        # both lift together; L lands at the end of the arc while R is STILL
        # AIRBORNE, then R drops ~0.30 s later (one-foot landing fault)
        for i in range(n_arc):
            u = i / (n_arc - 1)
            fy, fx = arc_y(u), _lerp(x, land_x, _ease(u))
            emit(hip_y=hip_top, sh_y=gy - 0.80 * H, knee_y=knee_y,
                 wrist_mode="hang", foot_y=(fy, gy - 0.16 * H),
                 foot_x=(fx - 0.06 * H, _lerp(x, land_x, 0.85) + 0.06 * H))
        # L down at land_x; R descends late
        for i in range(int(0.30 * fps)):
            emit(hip_y=hip_top, sh_y=gy - 0.80 * H, knee_y=knee_y,
                 wrist_mode="hang",
                 foot_y=(gy, gy - 0.16 * H + (0.16 * H) * (i / max(1, int(0.30 * fps) - 1))),
                 foot_x=(land_x - 0.05 * H, _lerp(x, land_x, 0.9) + 0.06 * H))
        emit_stand(land_x)
    else:  # "trailing": lead (L) crosses & lands while R stays grounded
        for i in range(n_arc):
            u = i / (n_arc - 1)
            fy, fx = arc_y(u), _lerp(x, land_x, _ease(u))
            emit(hip_y=hip_top, sh_y=gy - 0.80 * H, knee_y=knee_y,
                 wrist_mode="hang", foot_y=(fy, gy),
                 foot_x=(fx - 0.05 * H, x + 0.06 * H))
        # pause: L landed beyond the bar, R STILL on the start side
        for _ in range(int(0.22 * fps)):
            emit(hip_y=hip_top, sh_y=gy - 0.80 * H, knee_y=knee_y,
                 wrist_mode="hang", foot_y=(gy, gy),
                 foot_x=(land_x - 0.05 * H, x + 0.06 * H))
        # R finally jumps over
        for i in range(n_arc):
            u = i / (n_arc - 1)
            fy, fx = arc_y(u), _lerp(x, land_x, _ease(u))
            emit(hip_y=hip_top, sh_y=gy - 0.80 * H, knee_y=knee_y,
                 wrist_mode="hang", foot_y=(gy, fy),
                 foot_x=(land_x - 0.05 * H, fx + 0.06 * H))
        emit_stand(land_x)
    # ---- stand on the far side ----
    emit_many(4, hip_y=hip_top, sh_y=gy - 0.80 * H, knee_y=knee_y, ankle_y=gy,
              ankle_x_offset=land_x - x, wrist_mode="hang")
    return t


def np_linspace(a: float, b: float, n: int) -> list[float]:
    """numpy-free linspace (keeps the generator dependency-light)."""
    if n <= 1:
        return [a]
    step = (b - a) / (n - 1)
    return [a + i * step for i in range(n)]


# --------------------------------------------------------------------------- #
# Full synthetic workout (pipeline smoke + demo)
# --------------------------------------------------------------------------- #
def gen_synthetic_workout(blocks: list[dict], faults: Optional[dict] = None,
                          x0: float = 600.0, gy: float = 800.0,
                          H: float = 500.0, fps: float = 30.0,
                          lead_in_sec: float = 6.0) -> list[PoseFrame]:
    """Compose a full WOD pose stream. blocks: [{movement, reps}].

    Geometry: the barbell lives at x0 on the ground. Thrusters happen at x0;
    each BFB starts on one side (x0 − 0.55H), jumps over the bar, and ends on
    the opposite side. faults: {"thruster": {rep_idx: {fault kwargs...}},
    "bfb": {rep_idx: {...}}} — rep_idx counts within that movement from 0.
    """
    faults = faults or {}
    out: list[PoseFrame] = []
    t = 0.0
    idx = 0
    dt = 1.0 / fps
    # preroll: athlete standing at the bar, hands resting on it
    for _ in range(int(lead_in_sec * fps)):
        out.append(pose_frame(
            SkeletonBuilder(x0, gy, H).build(wrist_mode="ground"), t, idx))
        t += dt
        idx += 1
    bar_x = x0
    side = -1  # which side of the bar the athlete is on before each BFB
    t_count, b_count = 0, 0
    for block in blocks:
        mv, reps = block["movement"], block["reps"]
        if mv == "bar_facing_burpee":
            # walk from the bar to the starting side of the burpees
            start_x = bar_x + side * 0.55 * H
            for u in np_linspace(0, 1, 10):
                out.append(pose_frame(
                    SkeletonBuilder(_lerp(bar_x, start_x, u), gy, H).build(
                        hip_y=gy - 0.50 * H, knee_y=gy - 0.26 * H,
                        ankle_y=gy, wrist_mode="hang"), t, idx))
                t += dt
                idx += 1
        for _ in range(reps):
            if mv == "thruster":
                kw = dict(faults.get("thruster", {}).get(t_count, {}))
                if "entry" not in kw:
                    kw["entry"] = "ground" if t_count == 0 else "rack"
                t = gen_thruster_rep(out, t, bar_x, gy, H, idx, fps=fps, **kw)
                t_count += 1
            else:
                kw = dict(faults.get("bfb", {}).get(b_count, {}))
                start_x = bar_x + side * 0.55 * H
                t = gen_bfb_rep(out, t, start_x, gy, H, idx, bar_x, fps=fps, **kw)
                b_count += 1
                # the athlete ends on the opposite side
                if kw.get("cross", True):
                    side = -side
            idx = len(out)
        # between blocks: brief rest, then walk back to the bar if needed
        for _ in range(int(0.8 * fps)):
            cur_x = bar_x + side * 0.55 * H if mv == "bar_facing_burpee" else bar_x
            out.append(pose_frame(
                SkeletonBuilder(cur_x, gy, H).build(hip_y=gy - 0.50 * H,
                                                     knee_y=gy - 0.26 * H,
                                                     ankle_y=gy, wrist_mode="hang"),
                t, idx))
            t += dt
            idx += 1
        if mv == "bar_facing_burpee":
            cur_x = bar_x + side * 0.55 * H
            for u in np_linspace(0, 1, 10):
                out.append(pose_frame(
                    SkeletonBuilder(_lerp(cur_x, bar_x, u), gy, H).build(
                        hip_y=gy - 0.50 * H, knee_y=gy - 0.26 * H,
                        ankle_y=gy, wrist_mode="hang"), t, idx))
                t += dt
                idx += 1
    # tail
    for _ in range(int(1.5 * fps)):
        out.append(pose_frame(
            SkeletonBuilder(bar_x, gy, H).build(wrist_mode="hang"), t, idx))
        t += dt
        idx += 1
    return out
