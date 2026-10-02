"""
Bar-Facing Burpee judge FSM — encodes the Wodx rulebook:

  * Athlete must FACE the bar (not parallel) — shoulder line roughly
    parallel to the bar line (≈ horizontal in a 3/4-view image).
  * Feet near the bar but not on it.
  * Sternum must touch the ground.
  * Jump over the bar: two-foot takeoff, OR one-foot takeoff provided the
    trailing foot leaves the ground BEFORE the lead foot lands beyond the
    bar (trailing foot grounded on the start side while the lead foot has
    crossed and landed = fault).
  * Landing: BOTH feet simultaneously, fully beyond the bar.
  * Rotating toward the bar mid-air is allowed (no check — by design).
  * Contact with the bar during the jump = fault (review-level flag: the
    proximity heuristic is not proof of contact — asymmetric error policy).
"""
from __future__ import annotations

import enum
from typing import Optional

from config.settings import BFB, VIS_REQUIRED
from core.types import NO_REP, REP, Attempt
from movements.base import FrameContext, MovementFSM
from utils.geometry import dist, line_tilt_deg


class Phase(enum.Enum):
    IDLE = "idle"
    DESCENT = "descent"      # dropping toward the floor
    FLOOR = "floor"          # chest at / near the ground
    RISE = "rise"            # coming back up, feet gathering
    FLIGHT = "flight"        # crossing the bar (one or both feet airborne)
    JUDGED = "judged"


class _Foot:
    """Per-foot airborne timeline across one attempt."""

    def __init__(self) -> None:
        self.t_airborne: Optional[float] = None   # first lift-off time
        self.t_grounded: Optional[float] = None   # first touch-down after lift
        self.landing_x: Optional[float] = None
        self.min_bar_clearance: Optional[float] = None  # ×H


class _P:
    __slots__ = ("x", "y")

    def __init__(self, x: float, y: float) -> None:
        self.x, self.y = x, y


class BarFacingBurpeeFSM(MovementFSM):
    movement_id = "bar_facing_burpee"

    def __init__(self) -> None:
        super().__init__()
        self.phase = Phase.IDLE
        self.attempt: Optional[dict] = None
        self.foot_l = _Foot()
        self.foot_r = _Foot()
        # rolling standing-sternum baseline (to detect a real drop start)
        self._baseline_sh_y: Optional[float] = None
        self._baseline_t: float = 0.0

    # ------------------------------------------------------------------ #
    # Signals
    # ------------------------------------------------------------------ #
    def _signals(self, ctx: FrameContext) -> Optional[dict]:
        p, s = ctx.pose, ctx.scene
        if not p.person_detected:
            return None
        names = ("left_shoulder", "right_shoulder", "left_hip", "right_hip",
                 "left_ankle", "right_ankle", "left_foot_index",
                 "right_foot_index", "nose")
        if any(p.get(n) is None for n in names):
            return None
        H = s.H or 1.0
        sh = p.mid("left_shoulder", "right_shoulder")
        hip = p.mid("left_hip", "right_hip")
        ank = p.mid("left_ankle", "right_ankle")
        ank_l, ank_r = p.get("left_ankle"), p.get("right_ankle")
        tilt = line_tilt_deg(p.get("left_shoulder"), p.get("right_shoulder"))
        upright = sh.y < hip.y - 0.25 * H
        vis = min(sh.visibility, hip.visibility, ank_l.visibility,
                  ank_r.visibility, p.get("nose").visibility)

        def grounded(pt) -> Optional[bool]:
            gy = s.ground_y_at(pt.x)
            if gy is not None:
                return pt.y >= gy - 0.09 * H
            # fallback without a ground model: the bar itself lies on the floor
            if s.bar_confidence > 0:
                return pt.y >= s.bar_y - 0.12 * H
            return None

        return dict(H=H, sh=sh, hip=hip, ank=ank, ank_l=ank_l, ank_r=ank_r,
                    fi_l=p.get("left_foot_index"), fi_r=p.get("right_foot_index"),
                    tilt=tilt, upright=upright, vis=vis,
                    bar_x=(s.bar_x if s.bar_confidence > 0 else None),
                    bar_y=s.bar_y, bar_conf=s.bar_confidence,
                    g_l=grounded(ank_l), g_r=grounded(ank_r))

    # ------------------------------------------------------------------ #
    # Attempt lifecycle
    # ------------------------------------------------------------------ #
    def _start(self, ctx: FrameContext, g: dict) -> None:
        self.attempt = {
            "t0": ctx.t, "f0": ctx.frame_index,
            "facing_ok": True, "max_tilt": 0.0,
            "baseline_sh_y": g["sh"].y,
            "chest_min_y": g["sh"].y, "chest_ok": False, "chest_drop": 0.0,
            "takeoff_x": None, "bar_contact_min": None,
            "vis_min": g["vis"], "flags": [], "bar_conf": g["bar_conf"],
            "entered_flight": False,
        }
        self.foot_l, self.foot_r = _Foot(), _Foot()
        self.phase = Phase.DESCENT

    def _close(self, ctx: FrameContext, g: Optional[dict], outcome: str,
               reason: Optional[str]) -> None:
        a = self.attempt
        if a is None:
            self.phase = Phase.IDLE
            return
        if reason is None and outcome == NO_REP:
            # never jumped over → the most defensible early-close reason
            if not a["entered_flight"]:
                reason = "BFB_INCOMPLETE_CROSS" if a["chest_ok"] else "BFB_CHEST"
            else:
                reason = "BFB_INCOMPLETE_CROSS"
        details = {
            "max_tilt_deg": round(a["max_tilt"], 1),
            "chest_ok": a["chest_ok"],
            "chest_drop_h": round(a["chest_drop"], 3),
            "bar_confidence": round(a["bar_conf"], 2),
        }
        flags = list(a["flags"])
        if a["vis_min"] < VIS_REQUIRED:
            flags.append("BFB_LOW_VIS")
        if a["bar_contact_min"] is not None and \
                a["bar_contact_min"] < BFB["bar_contact_margin_h"]:
            flags.append("BFB_BAR_CONTACT")
        self.emit(Attempt(
            movement=self.movement_id,
            t_start=a["t0"], t_end=ctx.t,
            frame_start=a["f0"], frame_end=ctx.frame_index,
            outcome=outcome, reason_code=reason,
            details=details, review_flags=flags,
        ))
        self.attempt = None
        self.phase = Phase.IDLE
        self._baseline_sh_y = None

    # ------------------------------------------------------------------ #
    def process(self, ctx: FrameContext) -> None:
        if not self.enabled:
            return
        g = self._signals(ctx)
        if g is None:
            if self.attempt is not None and \
                    ctx.t - self.attempt["t0"] > BFB["attempt_timeout_sec"]:
                self._close(ctx, None, NO_REP, None)
            return
        self._drive(ctx, g)

    def _drive(self, ctx: FrameContext, g: dict) -> None:
        a = self.attempt
        H = g["H"]

        # ---------------- IDLE: real drop begins (baseline breach) -------- #
        if self.phase == Phase.IDLE:
            if g["upright"] and self._near_bar(g, H):
                # the baseline is the HIGHEST standing sternum ever seen
                # (min y) — a descent can never "refresh" it upward, so the
                # 0.10H breach reliably fires on a real drop.
                if self._baseline_sh_y is None:
                    self._baseline_sh_y = g["sh"].y
                    self._baseline_t = ctx.t
                elif g["sh"].y < self._baseline_sh_y:
                    self._baseline_sh_y = g["sh"].y
                    self._baseline_t = ctx.t
                elif g["sh"].y > self._baseline_sh_y + 0.10 * H:
                    self._start(ctx, g)   # still "upright" but clearly dropping
                    a = self.attempt
            elif self._baseline_sh_y is not None and \
                    g["sh"].y > self._baseline_sh_y + 0.10 * H and \
                    ctx.t - self._baseline_t < 3.0:
                self._start(ctx, g)   # sternum dropped → burpee descent begins
                a = self.attempt
            else:
                self._baseline_sh_y = None
            if self.phase == Phase.IDLE:
                return

        # ---------------- timeout ----------------------------------------- #
        if ctx.t - a["t0"] > BFB["attempt_timeout_sec"]:
            self._close(ctx, g, NO_REP, None)
            return

        # ---------------- continuous trackers ----------------------------- #
        a["vis_min"] = min(a["vis_min"], g["vis"])
        a["max_tilt"] = max(a["max_tilt"], g["tilt"])
        if g["sh"].y > a["chest_min_y"]:
            a["chest_min_y"] = g["sh"].y
            a["chest_drop"] = (a["chest_min_y"] - a["baseline_sh_y"]) / H
        ground_y = ctx.scene.ground_y_at(g["sh"].x)
        if ground_y is not None and \
                g["sh"].y >= ground_y - BFB["chest_touch_margin_h"] * H:
            a["chest_ok"] = True

        # ---------------- phase machine ------------------------------------ #
        if self.phase == Phase.DESCENT:
            if g["tilt"] > BFB["facing_shoulder_tilt_deg"]:
                a["facing_ok"] = False  # latched, judged at close
            if ground_y is not None and \
                    g["sh"].y >= ground_y - 0.25 * H and not g["upright"]:
                self.phase = Phase.FLOOR
            return

        if self.phase == Phase.FLOOR:
            if g["sh"].y < a["chest_min_y"] - 0.18 * H:
                self.phase = Phase.RISE
            return

        if self.phase == Phase.RISE:
            airborne_l, airborne_r = g["g_l"] is False, g["g_r"] is False
            if airborne_l or airborne_r:
                a["takeoff_x"] = g["ank"].x
                a["entered_flight"] = True
                self.phase = Phase.FLIGHT
                self._mark_airborne(ctx, g)
            return

        if self.phase == Phase.FLIGHT:
            self._mark_airborne(ctx, g)
            self._bar_proximity(ctx, g, a)
            if g["g_l"] is True and g["g_r"] is True:
                self._judge_landing(ctx, g, a)
            return

    # ------------------------------------------------------------------ #
    def _near_bar(self, g: dict, H: float) -> bool:
        if g["bar_x"] is None:
            return True  # no anchor yet — never block on missing data
        return abs(g["ank"].x - g["bar_x"]) < 1.8 * H

    def _mark_airborne(self, ctx: FrameContext, g: dict) -> None:
        for foot, grounded in ((self.foot_l, g["g_l"]), (self.foot_r, g["g_r"])):
            if grounded is None:
                continue
            if grounded is False:
                if foot.t_airborne is None:
                    foot.t_airborne = ctx.t
                elif foot.t_grounded is not None:
                    # re-armed: this foot touched down and lifted again —
                    # the judged landing will be its FINAL settling point
                    foot.t_grounded = None
            else:
                # record (or re-record) the touch-down time
                if foot.t_airborne is not None and foot.t_grounded is None:
                    foot.t_grounded = ctx.t

    def _bar_proximity(self, ctx: FrameContext, g: dict, a: dict) -> None:
        if g["bar_x"] is None or g["bar_conf"] <= 0:
            return
        bar = _P(g["bar_x"], g["bar_y"])
        H = g["H"]
        for fi in (g["fi_l"], g["fi_r"]):
            d = dist(fi, bar) / H
            if a["bar_contact_min"] is None or d < a["bar_contact_min"]:
                a["bar_contact_min"] = d

    # ------------------------------------------------------------------ #
    def force_close(self, t_end: float) -> None:
        """Close any open attempt at stream end (conservative no-rep)."""
        a = self.attempt
        if a is None:
            return
        reason = None
        if not a["chest_ok"]:
            reason = "BFB_CHEST"
        elif not a["facing_ok"]:
            reason = "BFB_NOT_FACING"
        elif not a["entered_flight"]:
            reason = "BFB_INCOMPLETE_CROSS"
        else:
            reason = "BFB_LOW_VIS"
        self.emit(Attempt(
            movement=self.movement_id, t_start=a["t0"], t_end=t_end,
            frame_start=a["f0"], frame_end=a["f0"], outcome=NO_REP,
            reason_code=reason,
            details={"max_tilt_deg": round(a["max_tilt"], 1),
                     "chest_ok": a["chest_ok"], "truncated": True},
            review_flags=list(a["flags"]) + ["BFB_LOW_VIS"],
        ))
        self.attempt = None
        self.phase = Phase.IDLE

    def _judge_landing(self, ctx: FrameContext, g: dict, a: dict) -> None:
        H = g["H"]
        bar_x = g["bar_x"]
        a["bar_conf"] = g["bar_conf"]
        reason: Optional[str] = None

        # 1. sternum touch
        if not a["chest_ok"]:
            reason = "BFB_CHEST"
        # 2. facing the bar at rep start
        if not a["facing_ok"]:
            reason = reason or "BFB_NOT_FACING"

        if bar_x is not None and g["bar_conf"] > 0.3:
            margin = BFB["bar_cross_margin_h"] * H
            # takeoff sign: which side of the bar the athlete jumped FROM
            takeoff_sign = -1 if a["takeoff_x"] < bar_x else +1
            # at judge time both feet are grounded where they landed
            land_x = {"L": g["ank_l"].x, "R": g["ank_r"].x}
            beyond = {k: ((x - bar_x) * takeoff_sign) < -margin
                      for k, x in land_x.items()}
            # 3. trailing-foot rule FIRST (the specific Wodx تبصره fault:
            #    the lead foot landed beyond the bar while the other foot was
            #    still grounded on the start side)
            tl_air, tr_air = self.foot_l.t_airborne, self.foot_r.t_airborne
            lead = trail = None
            if tl_air is not None and tr_air is not None and \
                    abs(tl_air - tr_air) > BFB["land_simultaneity_sec"]:
                lead, trail = ((self.foot_l, self.foot_r) if tl_air < tr_air
                               else (self.foot_r, self.foot_l))
            elif tl_air is not None and tr_air is None:
                lead, trail = self.foot_l, self.foot_r
            elif tr_air is not None and tl_air is None:
                lead, trail = self.foot_r, self.foot_l
            if lead is not None:
                lead_key = "L" if lead is self.foot_l else "R"
                if beyond.get(lead_key) and (
                        trail.t_airborne is None or
                        (lead.t_grounded is not None and
                         trail.t_airborne > lead.t_grounded)):
                    reason = reason or "BFB_TRAILING_FOOT"
            # 4. complete crossing — both feet land beyond the bar on the
            #    OPPOSITE side (offset with sign opposite to takeoff)
            if not all(beyond.values()):
                reason = reason or "BFB_INCOMPLETE_CROSS"
            # 5. simultaneous two-foot landing
            tl_land, tr_land = self.foot_l.t_grounded, self.foot_r.t_grounded
            if tl_land is not None and tr_land is not None:
                if abs(tl_land - tr_land) > BFB["land_simultaneity_sec"]:
                    reason = reason or "BFB_ONE_FOOT_LANDING"
        else:
            a["flags"].append("SYS_BAR_ANCHOR_LOW_CONF")

        if reason is None:
            self._close(ctx, g, REP, None)
        else:
            self._close(ctx, g, NO_REP, reason)
