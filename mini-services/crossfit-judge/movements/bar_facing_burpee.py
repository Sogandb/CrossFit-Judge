"""
Bar-Facing Burpee judge FSM — Wodx rulebook (CrossFit 22.2 standards as the
reference), rewritten around the "benefit of the doubt" judging policy:

  * An automatic no-rep requires a CLEAR violation (CrossFit video-review
    standard). Borderline measurements are credited with a review flag and
    capped confidence.
  * PATTERN GATE: an attempt that never brought the chest near the floor and
    never entered flight is NOT a burpee (thruster squat, bar pickup,
    transition noise) and is discarded silently — never shown as a no-rep.
  * The shoulder-tilt "facing" check is a camera-geometry assumption that
    breaks in side-view filming (a correctly-facing athlete shows a steeply
    tilted shoulder line in profile). It is therefore a REVIEW flag unless
    the body was CLEARLY parallel to the bar (sustained extreme tilt).
  * Chest touch uses a realistic margin (the shoulder landmark rides
    ~0.10-0.15H above the floor even when the chest IS down).

Rulebook (22.2 reference):
  * Athlete faces the bar; chest AND thighs touch the ground.
  * A two-foot takeoff and jump over the bar is REQUIRED — stepping over is
    a no-rep; both feet must be off the ground while passing over the bar.
  * Both feet must land beyond the bar (simultaneously — clearly staggered
    one-foot landing is a fault).
  * Bar contact during the jump: review-level flag only (proximity is not
    proof of contact).
"""
from __future__ import annotations

import enum
from typing import Optional

from config.settings import BFB, VIS_REQUIRED
from core.types import NO_REP, REP, Attempt
from judging.policy import rep_confidence, norep_confidence
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
        self.t_grounded: Optional[float] = None   # debounced touch-down after lift
        self.landing_x: Optional[float] = None
        self.min_bar_clearance: Optional[float] = None  # ×H
        self.air_frames = 0                      # frames with this foot airborne
        self._ground_streak = 0


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
        # CORE set (must exist): torso + head — the burpee's descent/floor/
        # rise phases are fully judgeable without the feet. The FEET are
        # optional: on the far side of the bar they are frequently occluded
        # by the plates (observed 76-94% missing for whole stretches); the
        # flight checks then degrade to "unmeasurable" (benefit of the
        # doubt) instead of blinding the FSM entirely.
        core = ("left_shoulder", "right_shoulder", "left_hip", "right_hip",
                "nose")
        if any(p.get(n) is None for n in core):
            return None
        H = s.H or 1.0
        sh = p.mid("left_shoulder", "right_shoulder")
        hip = p.mid("left_hip", "right_hip")
        ank_l, ank_r = p.get("left_ankle"), p.get("right_ankle")
        fi_l = p.get("left_foot_index")
        fi_r = p.get("right_foot_index")
        ank = p.mid("left_ankle", "right_ankle") if (ank_l and ank_r) else None
        tilt = line_tilt_deg(p.get("left_shoulder"), p.get("right_shoulder"))
        upright = sh.y < hip.y - 0.25 * H
        vis_terms = [sh.visibility, hip.visibility, p.get("nose").visibility]
        vis_terms += [a.visibility for a in (ank_l, ank_r) if a is not None]
        vis = min(vis_terms) if vis_terms else 0.0

        def grounded(pt) -> Optional[bool]:
            if pt is None:
                return None
            gy = s.ground_y_at(pt.x)
            if gy is not None:
                return pt.y >= gy - 0.09 * H
            # fallback without a ground model: the bar itself lies on the floor
            if s.bar_confidence > 0:
                return pt.y >= s.bar_y - 0.12 * H
            return None

        # sternum height above the ground (×H) — the pattern discriminator
        sh_ground_y = s.ground_y_at(sh.x)
        sh_ground_dist = ((sh_ground_y - sh.y) / H
                          if sh_ground_y is not None else None)

        return dict(H=H, sh=sh, hip=hip, ank=ank, ank_l=ank_l, ank_r=ank_r,
                    fi_l=fi_l, fi_r=fi_r,
                    tilt=tilt, upright=upright, vis=vis,
                    sh_ground_dist=sh_ground_dist,
                    bar_x=(s.bar_x if s.bar_confidence > 0 else None),
                    bar_y=s.bar_y, bar_conf=s.bar_confidence,
                    g_l=grounded(ank_l), g_r=grounded(ank_r))

    # ------------------------------------------------------------------ #
    # Attempt lifecycle
    # ------------------------------------------------------------------ #
    def _start(self, ctx: FrameContext, g: dict) -> None:
        self.attempt = {
            "t0": ctx.t, "f0": ctx.frame_index,
            "facing_ok": True, "max_tilt": 0.0, "tilt_sum": 0.0, "tilt_n": 0,
            "tilt_steep_n": 0,
            "baseline_sh_y": g["sh"].y,
            "chest_min_y": g["sh"].y, "chest_ok": False, "chest_drop": 0.0,
            "sh_ground_dist_min": (g["sh_ground_dist"]
                                   if g["sh_ground_dist"] is not None else 1e9),
            "takeoff_x": None, "bar_contact_min": None,
            "vis_min": g["vis"], "flags": [], "bar_conf": g["bar_conf"],
            "entered_flight": False,
            "side_start": None,          # grounded side (vs bar) BEFORE the descent
            "flight_x": [],           # ankle-mid x path during flight
            "both_air_frames": 0,     # frames with BOTH feet airborne (jump!)
            "one_air_frames": 0,      # frames with one foot airborne, other solidly grounded
            "unmeasurable_frames": 0,
            "stable_land_frames": 0,
            "land_judged": False,
        }
        self.foot_l, self.foot_r = _Foot(), _Foot()
        self.phase = Phase.DESCENT

    def _discard(self) -> None:
        """Silently drop the open attempt — not a burpee pattern."""
        self.attempt = None
        self.phase = Phase.IDLE
        self._baseline_sh_y = None

    def _is_burpee_pattern(self, a: dict) -> bool:
        """Chest came near the floor (within the plausibility margin) OR a
        real airborne crossing happened — everything else (thruster squat,
        bar pickup, tie-shoe) is discarded, never no-repped."""
        near_floor = a["sh_ground_dist_min"] <= BFB["chest_plausible_h"]
        return near_floor or a["entered_flight"]

    def _close(self, ctx: FrameContext, g: Optional[dict], outcome: str,
               reason: Optional[str], confidence: float = 1.0,
               borderline: bool = False) -> None:
        a = self.attempt
        if a is None:
            self.phase = Phase.IDLE
            return
        # pattern gate — noise attempts are discarded, never no-repped
        if outcome == NO_REP and not self._is_burpee_pattern(a):
            self._discard()
            return
        if reason is None and outcome == NO_REP:
            # never jumped over → the most defensible early-close reason
            if not a["entered_flight"]:
                reason = "BFB_INCOMPLETE_CROSS" if a["chest_ok"] else "BFB_CHEST"
            else:
                reason = "BFB_INCOMPLETE_CROSS"
        tilt_avg = a["max_tilt"] if a["tilt_n"] == 0 else a["tilt_sum"] / a["tilt_n"]
        details = {
            "max_tilt_deg": round(a["max_tilt"], 1),
            "avg_tilt_deg": round(tilt_avg, 1),
            "chest_ok": a["chest_ok"],
            "chest_drop_h": round(a["chest_drop"], 3),
            "chest_floor_dist_h": (round(a["sh_ground_dist_min"], 3)
                                   if a["sh_ground_dist_min"] < 1e8 else None),
            "bar_confidence": round(a["bar_conf"], 2),
        }
        if g is not None:
            details["dbg"] = {
                "H": round(g["H"], 0),
                "takeoff_x": (round(a["takeoff_x"], 0)
                              if a["takeoff_x"] is not None else None),
                "bar_x": (round(g["bar_x"], 0)
                          if g["bar_x"] is not None else None),
                "land_l_x": (round(g["ank_l"].x, 0)
                             if g["ank_l"] is not None else None),
                "land_r_x": (round(g["ank_r"].x, 0)
                             if g["ank_r"] is not None else None),
                "side": getattr(self, "_dbg_side", None),
                "both_air": a["both_air_frames"],
                "one_air": a["one_air_frames"],
                "unmeas": a["unmeasurable_frames"],
                "air_l": self.foot_l.t_airborne, "air_r": self.foot_r.t_airborne,
                "grnd_l": self.foot_l.t_grounded, "grnd_r": self.foot_r.t_grounded,
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
            confidence=confidence, borderline=borderline,
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
            # judge with whatever evidence exists (side transit may still
            # prove the crossing) instead of a blanket no-rep
            if self.phase in (Phase.RISE, Phase.FLIGHT) and a["chest_ok"]:
                self._judge_landing(ctx, g, a)
            else:
                self._close(ctx, g, NO_REP, None)
            return

        # ---------------- continuous trackers ----------------------------- #
        a["vis_min"] = min(a["vis_min"], g["vis"])
        a["max_tilt"] = max(a["max_tilt"], g["tilt"])
        a["tilt_sum"] += g["tilt"]
        a["tilt_n"] += 1
        if g["tilt"] >= BFB["facing_clear_tilt_deg"]:
            a["tilt_steep_n"] += 1
        if g["sh"].y > a["chest_min_y"]:
            a["chest_min_y"] = g["sh"].y
            a["chest_drop"] = (a["chest_min_y"] - a["baseline_sh_y"]) / H
        if g["sh_ground_dist"] is not None:
            a["sh_ground_dist_min"] = min(a["sh_ground_dist_min"],
                                          g["sh_ground_dist"])
        # remember the grounded side BEFORE the descent (crossing reference)
        if a["side_start"] is None and g["bar_x"] is not None and \
                (g["g_l"] is True and g["g_r"] is True):
            pos_x = g["ank"].x if g["ank"] is not None else g["hip"].x
            a["side_start"] = pos_x - g["bar_x"]
        ground_y = ctx.scene.ground_y_at(g["sh"].x)
        if ground_y is not None and \
                g["sh"].y >= ground_y - BFB["chest_touch_margin_h"] * H:
            a["chest_ok"] = True

        # ---------------- phase machine ------------------------------------ #
        if self.phase == Phase.DESCENT:
            # not-a-burpee recovery: person back upright with the chest never
            # approaching the floor (thruster squat recovery, bar pickup).
            # NOTE: chest_drop is measured from the arming breach (≈0.10H
            # below standing), so the effective bound is slightly under
            # min_descent_h.
            if a["tilt_n"] > 10 and g["upright"] and \
                    a["sh_ground_dist_min"] > BFB["chest_plausible_h"] and \
                    a["chest_drop"] < 0.32:
                self._discard()
                return
            # a drop that never reaches the floor within the sane window is
            # not a burpee (thruster squat etc.)
            if ctx.t - a["t0"] > BFB["descent_max_sec"] and \
                    a["sh_ground_dist_min"] > BFB["chest_plausible_h"] and \
                    not a["entered_flight"]:
                self._discard()
                return
            if ground_y is not None and \
                    g["sh"].y >= ground_y - 0.25 * H and not g["upright"]:
                self.phase = Phase.FLOOR
            elif g["sh"].y < a["chest_min_y"] - 0.18 * H and \
                    a["chest_drop"] >= 0.30:
                # the chest never reached the FLOOR zone but is rising again
                # from a deep descent (chest not touching = the fault case)
                self.phase = Phase.RISE
            return

        if self.phase == Phase.FLOOR:
            if g["sh"].y < a["chest_min_y"] - 0.18 * H:
                self.phase = Phase.RISE
            return

        if self.phase == Phase.RISE:
            # foot-status trackers run during RISE too (an occluded jump that
            # the detector never sees airborne must still count as
            # unmeasurable, not as "always grounded")
            if g["g_l"] is None or g["g_r"] is None:
                a["unmeasurable_frames"] += 1
            elif (g["g_l"] is False and g["g_r"] is False):
                a["both_air_frames"] += 1
            elif g["g_l"] is False or g["g_r"] is False:
                a["one_air_frames"] += 1
            airborne_l, airborne_r = g["g_l"] is False, g["g_r"] is False
            if airborne_l or airborne_r:
                a["takeoff_x"] = (g["ank"].x if g["ank"] is not None
                                   else g["hip"].x)
                a["entered_flight"] = True
                self.phase = Phase.FLIGHT
                self._mark_airborne(ctx, g)
                return
            # stuck in RISE for too long (feet never detected airborne, or
            # feet occluded) → judge with whatever evidence exists (the side
            # transit may still prove the crossing via hips/ankles)
            feet_settled = (g["g_l"] is True and g["g_r"] is True) or \
                a["unmeasurable_frames"] >= 8
            if ctx.t - a["t0"] > 6.0 and a["chest_ok"] and feet_settled:
                self._judge_landing(ctx, g, a)
            return

        if self.phase == Phase.FLIGHT:
            self._mark_airborne(ctx, g)
            self._bar_proximity(ctx, g, a)
            # flight-path + jump-quality trackers (across ALL hops); the path
            # follows the ankle-mid when the feet are visible, otherwise the
            # hip-mid (a robust proxy for the athlete's lateral position)
            pos_x = g["ank"].x if g["ank"] is not None else g["hip"].x
            a["flight_x"].append(pos_x)
            if g["g_l"] is None or g["g_r"] is None:
                a["unmeasurable_frames"] += 1
            elif g["g_l"] is False and g["g_r"] is False:
                a["both_air_frames"] += 1
            elif g["g_l"] is False or g["g_r"] is False:
                a["one_air_frames"] += 1

            # --- the next burpee's descent begins → judge NOW ------------- -- #
            # (chest near the FLOOR **and actually sinking** — two frames of
            # sustained downward sternum motion; a jump-prep crouch is high
            # and brief and must NOT close the flight)
            if g["sh_ground_dist"] is not None and \
                    g["sh_ground_dist"] < BFB["next_drop_dist_h"]:
                a["drop_streak"] = a.get("drop_streak", 0) + 1 \
                    if g["sh"].y > a.get("sh_y_prev", -1e9) else 0
                if a["drop_streak"] >= 2:
                    self._judge_landing(ctx, g, a)
                    return
            else:
                a["drop_streak"] = 0
            a["sh_y_prev"] = g["sh"].y

            # --- stable landing → judge ONLY when the side actually --- #
            # --- flipped (multi-hop crossings stay open)             --- #
            # Per-foot positions: BOTH feet must be settled past the bar
            # (an ankle-mid check would fire while the trailing foot is
            # still on the start side — exactly the trailing-foot fault
            # scenario, which must keep flying until it resolves)
            if g["g_l"] is True and g["g_r"] is True:
                a["stable_land_frames"] += 1
                if a["stable_land_frames"] >= 2 and not a["land_judged"]:
                    bar_x = g["bar_x"]
                    if bar_x is None or g["bar_conf"] <= 0.3 or \
                            a["side_start"] is None:
                        # no anchor / unknown start side → judge on whatever
                        # evidence exists (path) or benefit of the doubt
                        self._judge_landing(ctx, g, a)
                        return
                    side_then = a["side_start"]
                    side_l = (g["ank_l"].x - bar_x) if g["ank_l"] else None
                    side_r = (g["ank_r"].x - bar_x) if g["ank_r"] else None
                    sides = [s for s in (side_l, side_r) if s is not None]
                    if not sides:
                        sides = [g["hip"].x - bar_x]
                    # flipped only when BOTH feet are settled past the bar
                    both_past = all(s * side_then < 0 for s in sides)
                    near_bar = min(abs(s) for s in sides) < \
                        BFB["bar_cross_clear_h"] * H
                    settled = a["stable_land_frames"] >= 18   # ~0.6s
                    if both_past or near_bar or settled:
                        self._judge_landing(ctx, g, a)
                        return
                    # same side, clearly short of the bar, not yet settled →
                    # keep flying: the athlete may hop again (observed
                    # hop-hop crossings); stable_land_frames keeps counting
                    # so a genuinely settled same-side landing judges at 0.6s
            else:
                a["stable_land_frames"] = 0
            return

    # ------------------------------------------------------------------ #
    def _near_bar(self, g: dict, H: float) -> bool:
        if g["bar_x"] is None:
            return True  # no anchor yet — never block on missing data
        pos_x = g["ank"].x if g["ank"] is not None else g["hip"].x
        return abs(pos_x - g["bar_x"]) < 1.8 * H

    def _mark_airborne(self, ctx: FrameContext, g: dict) -> None:
        for foot, grounded in ((self.foot_l, g["g_l"]), (self.foot_r, g["g_r"])):
            if grounded is None:
                foot._ground_streak = 0
                continue
            if grounded is False:
                foot.air_frames += 1
                foot._ground_streak = 0
                if foot.t_airborne is None:
                    foot.t_airborne = ctx.t
                elif foot.t_grounded is not None:
                    # re-armed: this foot touched down and lifted again —
                    # the judged landing will be its FINAL settling point
                    foot.t_grounded = None
            else:
                # debounced touch-down: 2 consecutive grounded frames
                foot._ground_streak += 1
                if foot.t_airborne is not None and foot.t_grounded is None \
                        and foot._ground_streak >= 2:
                    foot.t_grounded = ctx.t

    def _bar_proximity(self, ctx: FrameContext, g: dict, a: dict) -> None:
        if g["bar_x"] is None or g["bar_conf"] <= 0:
            return
        bar = _P(g["bar_x"], g["bar_y"])
        H = g["H"]
        for fi in (g["fi_l"], g["fi_r"]):
            if fi is None:
                continue
            d = dist(fi, bar) / H
            if a["bar_contact_min"] is None or d < a["bar_contact_min"]:
                a["bar_contact_min"] = d

    # ------------------------------------------------------------------ #
    def force_close(self, t_end: float) -> None:
        """Close any open attempt at stream end (conservative no-rep)."""
        a = self.attempt
        if a is None:
            return
        if not self._is_burpee_pattern(a):
            self._discard()
            return
        reason = None
        if not a["chest_ok"]:
            reason = "BFB_CHEST"
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
            confidence=0.45, borderline=True,
        ))
        self.attempt = None
        self.phase = Phase.IDLE

    # ------------------------------------------------------------------ #
    def _judge_landing(self, ctx: FrameContext, g: dict, a: dict) -> None:
        """Full rulebook evaluation with benefit-of-the-doubt bands."""
        H = g["H"]
        bar_x = g["bar_x"]
        a["bar_conf"] = g["bar_conf"]
        flags = a["flags"]
        fail_reason: Optional[str] = None
        fail_severity = 0.6
        borderline = False
        margins: list[float] = []

        # ---- 1. sternum touch ---- #
        chest_dist = a["sh_ground_dist_min"]
        if a["chest_ok"]:
            margins.append(min(1.0, max(0.3,
                (BFB["chest_touch_margin_h"] - chest_dist) / 0.10)))
        elif chest_dist <= BFB["chest_bod_margin_h"]:
            # inside the uncertainty band → credit + review
            borderline = True
            flags.append("BFB_CHEST_REVIEW")
            margins.append(0.1)
        elif chest_dist > 1e8 or g["vis"] < 0.45:
            # cannot measure → benefit of the doubt
            borderline = True
            flags.append("BFB_LOW_VIS")
            margins.append(0.0)
        else:
            fail_reason = "BFB_CHEST"
            fail_severity = min(1.0,
                (chest_dist - BFB["chest_bod_margin_h"]) / 0.15)

        # ---- 2. facing the bar (camera-geometry sensitive → soft check) -- #
        tilt_avg = a["tilt_sum"] / max(1, a["tilt_n"])
        steep_frac = a.get("tilt_steep_n", 0) / max(1, a["tilt_n"])
        if steep_frac >= BFB["facing_min_frac"] and \
                a["max_tilt"] >= BFB["facing_clear_tilt_deg"] and \
                g["vis"] >= 0.6:
            fail_reason = fail_reason or "BFB_NOT_FACING"
        elif tilt_avg >= BFB["facing_shoulder_tilt_deg"] or steep_frac > 0 or \
                a["max_tilt"] >= BFB["facing_shoulder_tilt_deg"]:
            flags.append("BFB_FACING_REVIEW")

        # ---- 3. jump / crossing / landing ---- #
        if bar_x is not None and g["bar_conf"] > 0.3:
            margin = BFB["bar_cross_margin_h"] * H
            # ---- 3a. SIDE-TRANSIT crossing evidence (primary): the
            #      athlete's grounded position flipped sides of the bar
            #      between the start of this rep and the final landing.
            #      Robust to multi-hop crossings, premature landing
            #      glitches and mid-flight measurement noise. Position:
            #      ankle-mid when the feet are visible, else hip-mid.
            pos_now = (g["ank"].x if g["ank"] is not None else g["hip"].x)
            side_then = a["side_start"]
            if side_then is None and a["takeoff_x"] is not None:
                side_then = a["takeoff_x"] - bar_x
            side_now = pos_now - bar_x
            self._dbg_side = {"then": round(side_then / H, 3) if side_then is not None else None,
                              "now": round(side_now / H, 3)}
            # ---- 3b. PATH crossing evidence (supporting): the trajectory
            #      reached the far side of the bar while airborne
            xs = [x for x in a["flight_x"] if x is not None]
            if a["takeoff_x"] is not None:
                xs.append(a["takeoff_x"])
            xs.append(pos_now)
            path_min, path_max = min(xs), max(xs)
            if side_then is not None and side_then > 0:
                path_crossed = path_min <= bar_x - margin
            elif side_then is not None:
                path_crossed = path_max >= bar_x + margin
            else:
                path_crossed = False

            # ---- 3c. trailing-foot rule (Wodx footnote fault) — only on
            #      CLEAR evidence (solid single-foot crossing with the other
            #      foot solidly grounded throughout)
            tl_air, tr_air = self.foot_l.t_airborne, self.foot_r.t_airborne
            if tl_air is not None and tr_air is not None and \
                    abs(tl_air - tr_air) > BFB["land_simultaneity_sec"] and \
                    a["both_air_frames"] == 0 and \
                    a["unmeasurable_frames"] <= 1:
                lead_is_l = tl_air <= tr_air
                lead_foot = self.foot_l if lead_is_l else self.foot_r
                lead_land = (g["ank_l"] if lead_is_l else g["ank_r"])
                if lead_land is not None:
                    lead_land_x = lead_land.x
                    sgn = 1 if (side_then is not None and side_then > 0) else -1
                    lead_beyond = ((lead_land_x - bar_x) * sgn) < -margin
                    if lead_beyond and lead_foot.t_grounded is not None:
                        fail_reason = fail_reason or "BFB_TRAILING_FOOT"

            # ---- 3d. complete crossing ---- #
            if side_then is None:
                # start side unknown (no anchor early / never grounded) →
                # benefit of the doubt, flag for review
                borderline = True
                flags.append("BFB_CROSS_REVIEW")
                margins.append(0.0)
            else:
                flipped = side_now * side_then < 0
                crossed = flipped or path_crossed
                if crossed:
                    depth = min(abs(side_now), abs(side_then))
                    margins.append(min(1.0, max(0.3, depth / (0.25 * H))))
                elif abs(side_now) <= BFB["bar_cross_clear_h"] * H or \
                        a["unmeasurable_frames"] > 2:
                    # near the bar line or poorly measurable → doubt favors
                    # the athlete
                    borderline = True
                    flags.append("BFB_CROSS_REVIEW")
                    margins.append(0.1)
                else:
                    # still clearly on the takeoff side → clear fault
                    fail_reason = fail_reason or "BFB_INCOMPLETE_CROSS"
                    fail_severity = min(1.0, abs(side_now) / (0.25 * H))

            # ---- 3e. jump requirement (22.2: must JUMP over — stepping is
            #      a fault); verified from the airborne-frame statistics
            if a["both_air_frames"] >= 2:
                margins.append(min(1.0, a["both_air_frames"] / 6))   # real jump
            elif a["unmeasurable_frames"] >= 3 or g["vis"] < 0.5:
                # cannot verify the takeoff → benefit of the doubt
                borderline = True
                flags.append("BFB_JUMP_REVIEW")
                margins.append(0.0)
            elif a["one_air_frames"] >= 4 and a["both_air_frames"] == 0:
                fail_reason = fail_reason or "BFB_NO_JUMP"
            else:
                borderline = True
                flags.append("BFB_JUMP_REVIEW")
                margins.append(0.1)
            # 3f. simultaneous two-foot landing (only when both measured)
            tl_land, tr_land = self.foot_l.t_grounded, self.foot_r.t_grounded
            if tl_land is not None and tr_land is not None:
                gap = abs(tl_land - tr_land)
                if gap > BFB["land_clear_sec"]:
                    fail_reason = fail_reason or "BFB_ONE_FOOT_LANDING"
                elif gap > BFB["land_simultaneity_sec"]:
                    borderline = True
                    flags.append("BFB_LANDING_REVIEW")
                    margins.append(0.15)
                else:
                    margins.append(min(1.0, gap / BFB["land_clear_sec"]))
            # 3g. never airborne at all — a clear step-over only when the
            # feet were measurable throughout; otherwise benefit of the doubt
            if not a["entered_flight"] and a["chest_ok"]:
                if a["unmeasurable_frames"] <= 1 and g["vis"] >= 0.6:
                    fail_reason = fail_reason or "BFB_NO_JUMP"
                else:
                    borderline = True
                    flags.append("BFB_JUMP_REVIEW")
                    margins.append(0.0)
        else:
            a["flags"].append("SYS_BAR_ANCHOR_LOW_CONF")

        if fail_reason is not None:
            self._close(ctx, g, NO_REP, fail_reason,
                        norep_confidence(fail_severity, a["vis_min"]))
        else:
            conf = rep_confidence(margins or [0.5], a["vis_min"], borderline)
            self._close(ctx, g, REP, None, conf, borderline)
