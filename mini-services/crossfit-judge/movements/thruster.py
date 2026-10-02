"""
Thruster judge FSM — encodes the Wodx rulebook (CrossFit Games standards as
the reference):

  * Bar starts on the ground; a squat clean straight into the thruster IS
    allowed (two entry paths: from-ground clean, or cycle from front rack).
  * Front rack: elbows in front of the bar (review-level check in 3/4 view).
  * Depth: hip crease must pass BELOW the knee line (hysteresis on the
    hip-vs-knee vertical signal, margins in fractions of body height H).
  * One continuous motion: squat -> stand-rack PAUSE closes the attempt as a
    no-rep; any press-out from standing shortly after is judged as the jerk
    pattern (THR_NOT_CONTINUOUS), not as a fresh thruster.
  * Lockout: hips, knees and elbows fully extended; bar overhead; feet in
    one line under the body (walking forward during the rep = fault).
  * Hands touching the legs during the movement = fault (review-level).
"""
from __future__ import annotations

import enum
from typing import Optional

from config.settings import THR, VIS_REQUIRED
from core.types import NO_REP, REP, Attempt
from movements.base import FrameContext, MovementFSM
from utils.geometry import angle_at, dist


class Phase(enum.Enum):
    IDLE = "idle"
    ARMING = "arming"      # holding the bar; waiting for a real squat descent
    DESCENT = "descent"    # squatting down with the bar racked
    BOTTOM = "bottom"      # below-parallel latched (hysteresis armed)
    ASCENT = "ascent"      # driving up (toward overhead)
    LOCKING = "locking"    # overhead extension held for the debounce window


class ThrusterFSM(MovementFSM):
    movement_id = "thruster"

    def __init__(self) -> None:
        super().__init__()
        self.phase = Phase.IDLE
        self.attempt: Optional[dict] = None
        self.stand_rack_since: Optional[float] = None
        self._lock_t = 0.0
        self._standrack_close_t = -1e9   # last time an attempt closed on a
        # standing-rack pause (used to classify a following press as a jerk)

    # ------------------------------------------------------------------ #
    # Signals
    # ------------------------------------------------------------------ #
    def _signals(self, ctx: FrameContext) -> Optional[dict]:
        p, s = ctx.pose, ctx.scene
        if not p.person_detected:
            return None
        names = ("left_hip", "right_hip", "left_knee", "right_knee",
                 "left_ankle", "right_ankle", "left_shoulder", "right_shoulder",
                 "left_elbow", "right_elbow", "left_wrist", "right_wrist", "nose")
        if any(p.get(n) is None for n in names):
            return None
        H = s.H or 1.0
        hip = p.mid("left_hip", "right_hip")
        knee = p.mid("left_knee", "right_knee")
        sh = p.mid("left_shoulder", "right_shoulder")
        wrist = p.mid("left_wrist", "right_wrist")
        sh_l, sh_r = p.get("left_shoulder"), p.get("right_shoulder")
        el_l, el_r = p.get("left_elbow"), p.get("right_elbow")
        wr_l, wr_r = p.get("left_wrist"), p.get("right_wrist")
        hip_l, hip_r = p.get("left_hip"), p.get("right_hip")
        knee_l, knee_r = p.get("left_knee"), p.get("right_knee")
        ank_l, ank_r = p.get("left_ankle"), p.get("right_ankle")
        nose = p.get("nose")

        depth = (hip.y - knee.y) / H                       # + = below parallel
        elbow_ang = min(angle_at(sh_l, el_l, wr_l), angle_at(sh_r, el_r, wr_r))
        in_rack = abs(wrist.y - sh.y) / H <= THR["rack_wrist_shoulder_tol_h"] \
            and elbow_ang <= THR["rack_elbow_angle_max_deg"]
        overhead = wrist.y < nose.y                        # bar above the head
        knee_lock = min(angle_at(hip_l, knee_l, ank_l), angle_at(hip_r, knee_r, ank_r))
        hip_lock = min(angle_at(sh_l, hip_l, knee_l), angle_at(sh_r, hip_r, knee_r))
        standing = hip_lock >= THR["lock_hip_deg"] - 10 and \
            knee_lock >= THR["lock_knee_deg"] - 10
        ground_y = s.ground_y_at(wrist.x)
        bar_grounded = ground_y is not None and wrist.y >= ground_y - 0.12 * H
        bent_over = sh.y > hip.y + 0.25 * H
        vis = min(hip.visibility, knee.visibility, sh.visibility, wrist.visibility,
                  el_l.visibility, el_r.visibility, nose.visibility)
        return dict(H=H, hip=hip, knee=knee, sh=sh, wrist=wrist, nose=nose,
                    sh_l=sh_l, sh_r=sh_r, el_l=el_l, el_r=el_r, wr_l=wr_l,
                    wr_r=wr_r, knee_l=knee_l, knee_r=knee_r, ank_l=ank_l,
                    ank_r=ank_r, depth=depth, elbow_ang=elbow_ang,
                    in_rack=in_rack, overhead=overhead, elb_lock=elbow_ang,
                    knee_lock=knee_lock, hip_lock=hip_lock, standing=standing,
                    bar_grounded=bar_grounded, bent_over=bent_over, vis=vis)

    # ------------------------------------------------------------------ #
    # Attempt lifecycle
    # ------------------------------------------------------------------ #
    def _start_attempt(self, ctx: FrameContext, entry: str, g: dict) -> None:
        self.attempt = {
            "t0": ctx.t, "f0": ctx.frame_index, "entry": entry,
            "depth_armed": False, "max_depth": -1.0,
            "elb_lockout": 0.0, "knee_lockout": 0.0, "hip_lockout": 0.0,
            "overhead": False, "wrist_x_end": None, "shoulder_x_end": None,
            "ank_l0": g["ank_l"].x, "ank_r0": g["ank_r"].x,
            "vis_min": g["vis"], "flags": [],
            "saw_overhead": False, "elb_overhead_min": 180.0,
            "min_wr_knee_h": 1e9, "overhead_bad_since": None,
        }
        self.stand_rack_since = None
        self.phase = Phase.ARMING

    def _close(self, ctx: FrameContext, g: Optional[dict], outcome: str,
               reason: Optional[str]) -> None:
        a = self.attempt
        if a is None:
            self.phase = Phase.IDLE
            return
        if reason is None and outcome == NO_REP:
            if not a["depth_armed"]:
                reason = "THR_DEPTH"
            elif a["saw_overhead"] and a["elb_overhead_min"] < THR["lock_elbow_deg"]:
                reason = "THR_LOCKOUT"
            elif not a["overhead"]:
                reason = "THR_BAR_NOT_OVERHEAD"
            else:
                reason = "THR_LOCKOUT"
        details = {
            "entry": a["entry"],
            "max_depth_h": round(a["max_depth"], 3),
            "depth_armed": a["depth_armed"],
            "elb_lock": round(a["elb_lockout"], 1) or None,
            "elb_overhead_min": round(a["elb_overhead_min"], 1)
            if a["saw_overhead"] else None,
            "knee_lock": round(a["knee_lockout"], 1) or None,
            "hip_lock": round(a["hip_lockout"], 1) or None,
            "overhead": a["overhead"],
        }
        flags = list(a["flags"])
        if a["vis_min"] < VIS_REQUIRED:
            flags.append("THR_LOW_VIS")
        if g is not None and a.get("shoulder_x_end") is not None:
            if abs(a["wrist_x_end"] - a["shoulder_x_end"]) / g["H"] > THR["bar_midline_tol_h"]:
                flags.append("THR_BAR_LINE")
        self.emit(Attempt(
            movement=self.movement_id,
            t_start=a["t0"], t_end=ctx.t,
            frame_start=a["f0"], frame_end=ctx.frame_index,
            outcome=outcome, reason_code=reason,
            details=details, review_flags=flags,
        ))
        self.attempt = None
        self.stand_rack_since = None
        self.phase = Phase.IDLE

    # ------------------------------------------------------------------ #
    # FSM core
    # ------------------------------------------------------------------ #
    def process(self, ctx: FrameContext) -> None:
        if not self.enabled:
            return
        g = self._signals(ctx)
        if g is None:
            if self.attempt is not None and \
                    ctx.t - self.attempt["t0"] > THR["attempt_timeout_sec"]:
                self._close(ctx, None, NO_REP, "THR_LOW_VIS")
            return
        self._drive(ctx, g)

    def _drive(self, ctx: FrameContext, g: dict) -> None:
        a = self.attempt
        if a is not None:
            a["vis_min"] = min(a["vis_min"], g["vis"])
            a["max_depth"] = max(a["max_depth"], g["depth"])
            # track the elbow angle whenever the bar is overhead
            if g["overhead"]:
                a["saw_overhead"] = True
                a["elb_overhead_min"] = min(a["elb_overhead_min"], g["elb_lock"])

        # ---------------- IDLE: arm a new attempt ---------------- #
        if self.phase == Phase.IDLE:
            # (a) bent over the bar / catching a clean from the floor.
            #     SPATIAL GUARD: the hands must be AT the bar — a burpee
            #     drop far from the bar is NOT a clean.
            at_bar = True
            if ctx.scene.bar_confidence > 0:
                at_bar = abs(g["wrist"].x - ctx.scene.bar_x) <= 0.55 * g["H"]
            if at_bar and g["bar_grounded"] and (g["bent_over"] or g["depth"] > 0.05) \
                    and not g["standing"]:
                self._start_attempt(ctx, "ground", g)
                if g["depth"] >= THR["depth_enter_margin_h"]:
                    self.attempt["depth_armed"] = True
                    self.phase = Phase.BOTTOM
                return
            # (b) standing with the bar settled in the front rack
            if g["in_rack"] and g["standing"] and g["depth"] < 0.05:
                self._start_attempt(ctx, "rack", g)
                if g["elbow_ang"] > THR["rack_elbow_angle_max_deg"] + 25:
                    self.attempt["flags"].append("THR_RACK_ELBOWS")
                return
            return

        # ---------------- timeout guard ---------------- #
        if ctx.t - a["t0"] > THR["attempt_timeout_sec"]:
            if self.phase == Phase.ARMING:
                # armed but never began a real descent → not an attempt at all
                self.attempt = None
                self.stand_rack_since = None
                self.phase = Phase.IDLE
            else:
                self._close(ctx, g, NO_REP, "THR_LOW_VIS")
            return

        # ---------------- bar back on the ground → close ---------------- #
        if g["bar_grounded"] and ctx.t - a["t0"] > 1.0 and self.phase != Phase.ARMING:
            self._close(ctx, g, NO_REP, None)
            return

        if self.phase == Phase.ARMING:
            # press/jerk straight from standing (no squat in this attempt)
            if g["overhead"] and g["elb_lock"] >= THR["lock_elbow_deg"]:
                if ctx.t - self._standrack_close_t < 4.0:
                    self._close(ctx, g, NO_REP, "THR_NOT_CONTINUOUS")
                else:
                    self._close(ctx, g, NO_REP, "THR_DEPTH")
                return
            if a["entry"] == "rack":
                if g["depth"] > THR["depth_exit_margin_h"] + 0.02 or \
                        g["hip_lock"] < THR["lock_hip_deg"] - 25:
                    self.phase = Phase.DESCENT
            else:  # ground entry (clean)
                if g["depth"] >= THR["depth_enter_margin_h"]:
                    a["depth_armed"] = True
                    self.phase = Phase.ASCENT      # squat-clean catch → drive
                elif g["in_rack"] and g["standing"]:
                    # power-clean catch: NO thruster attempt has begun (the
                    # bar was merely lifted to the rack) → discard silently;
                    # IDLE re-arms a rack attempt on the next frame.
                    self.attempt = None
                    self.stand_rack_since = None
                    self.phase = Phase.IDLE
                elif g["depth"] > 0.02:
                    self.phase = Phase.DESCENT
            return

        if self.phase in (Phase.DESCENT, Phase.BOTTOM):
            # hands-to-legs proximity tracker (review-level, squat phases only)
            d = min(dist(g["wr_l"], g["knee_l"]),
                    dist(g["wr_r"], g["knee_r"])) / g["H"]
            a["min_wr_knee_h"] = min(a["min_wr_knee_h"], d)
            if g["depth"] >= THR["depth_enter_margin_h"]:
                a["depth_armed"] = True
                self.phase = Phase.BOTTOM
            elif self.phase == Phase.BOTTOM and g["depth"] <= THR["depth_exit_margin_h"]:
                self.phase = Phase.ASCENT
            elif self.phase == Phase.DESCENT and g["depth"] <= THR["depth_exit_margin_h"] - 0.10 \
                    and ctx.t - a["t0"] > 1.5:
                # clearly rising without ever approaching depth
                self.phase = Phase.ASCENT
            return

        if self.phase == Phase.ASCENT:
            if g["overhead"] and g["elb_lock"] >= THR["lock_elbow_deg"]:
                self._snapshot_lockout(g, a, ctx)
                self.phase = Phase.LOCKING
                return
            # overhead with clearly bent elbows, sustained → press-out failure
            if g["overhead"] and g["elb_lock"] < THR["lock_elbow_deg"] - 20:
                if a["overhead_bad_since"] is None:
                    a["overhead_bad_since"] = ctx.t
                elif ctx.t - a["overhead_bad_since"] >= THR["min_phase_sec"]:
                    self._close(ctx, g, NO_REP, "THR_LOCKOUT")
                    return
            else:
                a["overhead_bad_since"] = None
            if g["standing"] and g["in_rack"]:
                # bar parked at the shoulders while fully standing →
                # continuity is broken; close after the pause debounce.
                if self.stand_rack_since is None:
                    self.stand_rack_since = ctx.t
                elif ctx.t - self.stand_rack_since >= THR["stand_rack_pause_sec"]:
                    self._standrack_close_t = ctx.t
                    self._close(ctx, g, NO_REP, "THR_BAR_NOT_OVERHEAD")
                return
            self.stand_rack_since = None
            return

        if self.phase == Phase.LOCKING:
            if not g["overhead"] or g["elb_lock"] < THR["lock_elbow_deg"] - 8:
                if g["in_rack"] and g["standing"]:
                    self._close(ctx, g, NO_REP, "THR_LOCKOUT")
                elif g["bar_grounded"]:
                    self._close(ctx, g, NO_REP, None)
                return
            if ctx.t - self._lock_t >= THR["min_phase_sec"]:
                self._judge(ctx, g, a)
            return

    # ------------------------------------------------------------------ #
    def _snapshot_lockout(self, g: dict, a: dict, ctx: FrameContext) -> None:
        a["elb_lockout"] = g["elb_lock"]
        a["knee_lockout"] = g["knee_lock"]
        a["hip_lockout"] = g["hip_lock"]
        a["overhead"] = True
        a["wrist_x_end"] = g["wrist"].x
        a["shoulder_x_end"] = g["sh"].x
        self._lock_t = ctx.t

    def _judge(self, ctx: FrameContext, g: dict, a: dict) -> None:
        reason: Optional[str] = None
        H = g["H"]
        if not a["depth_armed"]:
            reason = "THR_DEPTH"
        if a["elb_overhead_min"] < THR["lock_elbow_deg"] or \
                a["knee_lockout"] < THR["lock_knee_deg"] or \
                a["hip_lockout"] < THR["lock_hip_deg"]:
            reason = reason or "THR_LOCKOUT"
        if not a["overhead"]:
            reason = reason or "THR_BAR_NOT_OVERHEAD"
        # feet must stay in one line under the body (no walking forward)
        ank_drift = max(abs(g["ank_l"].x - a["ank_l0"]),
                        abs(g["ank_r"].x - a["ank_r0"])) / H
        if ank_drift > THR["walk_drift_max_h"]:
            reason = reason or "THR_WALKING"
        # review-level: hands resting on the legs during the squat
        if a["min_wr_knee_h"] < 0.10 and a["max_depth"] > 0.0:
            a["flags"].append("THR_HANDS_TO_LEG")

        if reason is None:
            self._close(ctx, g, REP, None)
        else:
            self._close(ctx, g, NO_REP, reason)

    def force_close(self, t_end: float) -> None:
        """Close any open attempt at stream end (conservative no-rep).
        Attempts still in ARMING never became real attempts → discarded."""
        if self.attempt is None:
            return
        if self.phase == Phase.ARMING:
            self.attempt = None
            self.phase = Phase.IDLE
            return
        from core.types import Attempt as _A
        a = self.attempt
        reason = None
        if not a["depth_armed"]:
            reason = "THR_DEPTH"
        elif a["saw_overhead"] and a["elb_overhead_min"] < THR["lock_elbow_deg"]:
            reason = "THR_LOCKOUT"
        elif not a["overhead"]:
            reason = "THR_BAR_NOT_OVERHEAD"
        else:
            reason = "THR_LOW_VIS"
        self.emit(Attempt(
            movement=self.movement_id, t_start=a["t0"], t_end=t_end,
            frame_start=a["f0"], frame_end=a["f0"], outcome=NO_REP,
            reason_code=reason,
            details={"entry": a["entry"], "max_depth_h": round(a["max_depth"], 3),
                     "depth_armed": a["depth_armed"], "overhead": a["overhead"],
                     "truncated": True},
            review_flags=list(a["flags"]) + ["THR_LOW_VIS"],
        ))
        self.attempt = None
        self.phase = Phase.IDLE
