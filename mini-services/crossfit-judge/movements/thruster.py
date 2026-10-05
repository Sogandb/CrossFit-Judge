"""
Thruster judge FSM — Wodx rulebook (CrossFit Games standards as the
reference), rewritten around the "benefit of the doubt" judging policy:

  * CrossFit video-review standard: an automatic no-rep requires a CLEAR
    violation. Measurements inside the uncertainty band are credited with a
    review flag and capped confidence.
  * 2D elbow angle is UNRELIABLE at overhead lockout (foreshortening +
    far-arm occlusion in 3/4 view): the engine therefore judges overhead
    extension primarily from robust evidence (wrist clearly above the
    shoulder line / above the head), treats the best-arm elbow angle as a
    soft signal, and auto no-reps only clearly-bent positions.

Movement pattern (Wodx rulebook):
  * Bar starts on the ground; a squat clean straight into the thruster IS
    allowed (two entry paths: from-ground clean, or cycle from front rack).
  * Depth: hip crease passes below the knee-top line (borderline band
    credited with review).
  * One continuous motion: squat -> stand-rack PAUSE closes the attempt as a
    no-rep (THR_NOT_CONTINUOUS / THR_BAR_NOT_OVERHEAD); a press-out shortly
    after a stand-rack close is judged as the jerk pattern.
  * Lockout: bar overhead, hips/knees/elbows extended, feet in one line.
  * PATTERN GATE: an attempt that never descended into a real squat and
    never reached overhead is NOT a thruster attempt (transition noise —
    e.g. burpee floor work, re-gripping) and is discarded silently. Only
    genuine thruster-shaped attempts are judged and emitted.
"""
from __future__ import annotations

import enum
from typing import Optional

from config.settings import THR, VIS_REQUIRED
from core.types import NO_REP, REP, Attempt
from judging.policy import rep_confidence, norep_confidence
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
        # CORE set (must exist): torso + arms + head. The ANKLES are
        # optional (occluded by the bar/plates on the far side for whole
        # stretches) — knee-lock and the walking check then degrade to
        # review-level instead of blinding the FSM.
        core = ("left_hip", "right_hip", "left_knee", "right_knee",
                "left_shoulder", "right_shoulder",
                "left_elbow", "right_elbow", "left_wrist", "right_wrist",
                "nose")
        if any(p.get(n) is None for n in core):
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
        elb_l = angle_at(sh_l, el_l, wr_l)
        elb_r = angle_at(sh_r, el_r, wr_r)
        # best-arm elbow: the far arm is frequently hallucinated by the 2D
        # model in 3/4 view — benefit of the doubt goes to the better arm.
        elb_best = max(elb_l, elb_r)
        # per-arm evidence quality (min of the 3 joints' visibility)
        arm_vis_l = min(sh_l.visibility, el_l.visibility, wr_l.visibility)
        arm_vis_r = min(sh_r.visibility, el_r.visibility, wr_r.visibility)
        arm_vis = max(arm_vis_l, arm_vis_r)
        in_rack = abs(wrist.y - sh.y) / H <= THR["rack_wrist_shoulder_tol_h"] \
            and min(elb_l, elb_r) <= THR["rack_elbow_angle_max_deg"]
        # robust overhead evidence (both work in front/side view):
        overhead = wrist.y < nose.y                       # bar above the head
        reach = (sh.y - wrist.y) / H                      # + = bar above shoulders
        knee_lock = (min(angle_at(hip_l, knee_l, ank_l), angle_at(hip_r, knee_r, ank_r))
                     if (ank_l is not None and ank_r is not None) else None)
        hip_lock = min(angle_at(sh_l, hip_l, knee_l), angle_at(sh_r, hip_r, knee_r))
        standing = hip_lock >= THR["lock_hip_deg"] - 10 and \
            (knee_lock is None or knee_lock >= THR["lock_knee_deg"] - 10)
        ground_y = s.ground_y_at(wrist.x)
        bar_grounded = ground_y is not None and wrist.y >= ground_y - 0.12 * H
        # wrist height above the ground (×H) — distinguishes "bar held at
        # the rack during a squat" (≥ ~0.3H) from "hands on the floor"
        # (burpee crouch / hand-plant, ≈ 0-0.2H)
        wr_h = (ground_y - wrist.y) / H if ground_y is not None else None
        # posture gate: chest well above the floor (burpee floor work must
        # never arm a thruster attempt)
        sh_ground_y = s.ground_y_at(sh.x)
        chest_above_floor = sh_ground_y is None or \
            sh.y < sh_ground_y - THR["chest_floor_gate_h"] * H
        bent_over = sh.y > hip.y + 0.25 * H
        vis_terms = [hip.visibility, knee.visibility, sh.visibility,
                     wrist.visibility, el_l.visibility, el_r.visibility,
                     nose.visibility]
        vis_terms += [a.visibility for a in (ank_l, ank_r) if a is not None]
        vis = min(vis_terms) if vis_terms else 0.0
        return dict(H=H, hip=hip, knee=knee, sh=sh, wrist=wrist, nose=nose,
                    sh_l=sh_l, sh_r=sh_r, el_l=el_l, el_r=el_r, wr_l=wr_l,
                    wr_r=wr_r, knee_l=knee_l, knee_r=knee_r, ank_l=ank_l,
                    ank_r=ank_r, depth=depth, elbow_ang=min(elb_l, elb_r),
                    elb_best=elb_best, arm_vis=arm_vis, reach=reach,
                    in_rack=in_rack, overhead=overhead, wr_h=wr_h,
                    knee_lock=knee_lock, hip_lock=hip_lock, standing=standing,
                    bar_grounded=bar_grounded, bent_over=bent_over,
                    chest_above_floor=chest_above_floor, vis=vis)

    # ------------------------------------------------------------------ #
    # Attempt lifecycle
    # ------------------------------------------------------------------ #
    def _start_attempt(self, ctx: FrameContext, entry: str, g: dict) -> None:
        self.attempt = {
            "t0": ctx.t, "f0": ctx.frame_index, "entry": entry,
            "depth_armed": False, "max_depth": -1.0,
            "wr_h_at_max_depth": None,
            # lockout evidence (best moment over time — benefit of the doubt:
            # a clearly seen extension at any overhead instant credits the rep)
            "elb_lock_best": 0.0, "knee_lock_best": 0.0, "hip_lock_best": 0.0,
            "reach_best": -1.0,
            "overhead": False, "wrist_x_end": None, "shoulder_x_end": None,
            "ank_l0": (g["ank_l"].x if g["ank_l"] is not None else 0.0),
            "ank_r0": (g["ank_r"].x if g["ank_r"] is not None else 0.0),
            "vis_min": g["vis"], "arm_vis_min": g["arm_vis"], "flags": [],
            "saw_overhead": False, "min_wr_knee_h": 1e9,
            "overhead_bad_since": None,
        }
        self.stand_rack_since = None
        self.phase = Phase.ARMING

    def _discard(self) -> None:
        """Silently drop the open attempt — it never matched the movement
        pattern (transition noise), so it must not appear as a no-rep."""
        self.attempt = None
        self.stand_rack_since = None
        self.phase = Phase.IDLE

    def _is_thruster_pattern(self, a: dict) -> bool:
        """Pattern gate: did this attempt even look like a thruster?

        * rack entry: a real squat descent OR a press to overhead suffices
          (arming in the front rack already implies the bar is in hand).
        * ground entry: must show a REAL squat descent AND, at the deepest
          squat moment, the hands must be holding the bar up at rack height —
          hands still at floor level at depth = burpee crouch / hand-plant,
          not a thruster.
        """
        if a["entry"] == "rack":
            # the bar is in hand (armed in the front rack): ANY real descent
            # (≥0.025H) or a press to overhead makes it a judged attempt —
            # shallow squats are real no-rep-able thruster attempts
            return a["max_depth"] >= 0.025 or a["saw_overhead"]
        wr_h = a["wr_h_at_max_depth"]
        return a["max_depth"] >= THR["min_squat_h"] and \
            wr_h is not None and wr_h >= THR["bar_held_h"]

    def _close(self, ctx: FrameContext, g: Optional[dict], outcome: str,
               reason: Optional[str], confidence: float = 1.0,
               borderline: bool = False) -> None:
        a = self.attempt
        if a is None:
            self.phase = Phase.IDLE
            return
        # pattern gate — noise attempts are discarded, never no-repped
        if outcome == NO_REP and not self._is_thruster_pattern(a):
            self._discard()
            return
        if reason is None and outcome == NO_REP:
            if not a["depth_armed"]:
                reason = "THR_DEPTH"
            elif not a["overhead"]:
                reason = "THR_BAR_NOT_OVERHEAD"
            else:
                reason = "THR_LOCKOUT"
        details = {
            "entry": a["entry"],
            "max_depth_h": round(a["max_depth"], 3),
            "depth_armed": a["depth_armed"],
            "elb_lock": round(a["elb_lock_best"], 1) or None,
            "reach_h": round(a["reach_best"], 3),
            "knee_lock": round(a["knee_lock_best"], 1) or None,
            "hip_lock": round(a["hip_lock_best"], 1) or None,
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
            confidence=confidence, borderline=borderline,
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
            a["arm_vis_min"] = min(a["arm_vis_min"], g["arm_vis"])
            if g["depth"] > a["max_depth"]:
                a["max_depth"] = g["depth"]
                a["wr_h_at_max_depth"] = g["wr_h"]
            # lockout evidence: best values at overhead moments
            if g["overhead"] or g["reach"] > 0:
                a["saw_overhead"] = True
                a["elb_lock_best"] = max(a["elb_lock_best"], g["elb_best"])
                a["knee_lock_best"] = max(a["knee_lock_best"], g["knee_lock"])
                a["hip_lock_best"] = max(a["hip_lock_best"], g["hip_lock"])
                a["reach_best"] = max(a["reach_best"], g["reach"])

        # ---------------- IDLE: arm a new attempt ---------------- #
        if self.phase == Phase.IDLE:
            # (a) bent over the bar / catching a clean from the floor.
            #     SPATIAL + POSTURE GUARD: hands at the bar AND chest well
            #     above the floor — burpee floor work never arms a thruster.
            at_bar = True
            if ctx.scene.bar_confidence > 0:
                at_bar = abs(g["wrist"].x - ctx.scene.bar_x) <= 0.55 * g["H"]
            if at_bar and g["bar_grounded"] and g["chest_above_floor"] \
                    and (g["bent_over"] or g["depth"] > 0.05) \
                    and not g["standing"]:
                self._start_attempt(ctx, "ground", g)
                if g["depth"] >= THR["depth_enter_margin_h"]:
                    self.attempt["depth_armed"] = True
                    self.phase = Phase.BOTTOM
                return
            # (b) standing with the bar settled in the front rack,
            #     OR mid-descent with the bar racked (a squat-clean catch
            #     flowing straight into the thruster squat never passes
            #     through a full stand — the rulebook allows it, so it must
            #     arm; observed miss: the first rep of every cluster)
            if g["in_rack"] and g["chest_above_floor"] and (
                    (g["standing"] and g["depth"] < 0.05)
                    or g["depth"] >= THR["min_squat_h"] - 0.01):
                self._start_attempt(ctx, "rack", g)
                if g["elbow_ang"] > THR["rack_elbow_angle_max_deg"] + 25:
                    self.attempt["flags"].append("THR_RACK_ELBOWS")
                return
            return

        # ---------------- timeout guard ---------------- #
        if ctx.t - a["t0"] > THR["attempt_timeout_sec"]:
            if self.phase == Phase.ARMING:
                self._discard()
            else:
                self._close(ctx, g, NO_REP, "THR_LOW_VIS")
            return

        # ---------------- bar back on the ground → close ---------------- #
        if g["bar_grounded"] and ctx.t - a["t0"] > 1.0 and self.phase != Phase.ARMING:
            self._judge_close(ctx, g, "grounded")
            return

        if self.phase == Phase.ARMING:
            # press/jerk straight from standing (no squat in this attempt)
            if g["overhead"] and g["elb_best"] >= THR["lock_elbow_deg"]:
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
                    self._discard()
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
            if g["overhead"] and g["elb_best"] >= THR["lock_elbow_deg"]:
                self._snapshot_lockout(g, a, ctx)
                self.phase = Phase.LOCKING
                return
            # overhead with CLEARLY bent elbows, sustained → press-out failure
            # (only a clear violation no-reps — borderline elbows keep waiting)
            if g["overhead"] and g["elb_best"] < THR["lock_elbow_clear_deg"] \
                    and g["reach"] < 0.10:
                if a["overhead_bad_since"] is None:
                    a["overhead_bad_since"] = ctx.t
                elif ctx.t - a["overhead_bad_since"] >= THR["min_phase_sec"]:
                    self._close(ctx, g, NO_REP, "THR_LOCKOUT",
                                norep_confidence(0.6, g["arm_vis"]))
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
                    self._judge_close(ctx, g, "stand_rack")
                return
            self.stand_rack_since = None
            return

        if self.phase == Phase.LOCKING:
            # keep refreshing the best lockout evidence while holding overhead
            if g["overhead"] or g["reach"] > 0:
                a["elb_lock_best"] = max(a["elb_lock_best"], g["elb_best"])
                a["knee_lock_best"] = max(a["knee_lock_best"], g["knee_lock"])
                a["hip_lock_best"] = max(a["hip_lock_best"], g["hip_lock"])
                a["reach_best"] = max(a["reach_best"], g["reach"])
            if not g["overhead"] and g["reach"] < -0.05:
                if g["in_rack"] and g["standing"]:
                    self._judge_close(ctx, g, "stand_rack_after_lock")
                elif g["bar_grounded"]:
                    self._judge_close(ctx, g, "grounded")
                return
            if g["elb_best"] < THR["lock_elbow_clear_deg"] - 8 and g["reach"] < 0.10:
                # clearly lost the lockout again
                self._judge_close(ctx, g, "lost_lock")
                return
            if ctx.t - self._lock_t >= THR["min_phase_sec"]:
                self._judge(ctx, g, a)
            return

    # ------------------------------------------------------------------ #
    def _snapshot_lockout(self, g: dict, a: dict, ctx: FrameContext) -> None:
        a["overhead"] = True
        a["wrist_x_end"] = g["wrist"].x
        a["shoulder_x_end"] = g["sh"].x
        self._lock_t = ctx.t

    # ------------------------------------------------------------------ #
    def _judge_close(self, ctx: FrameContext, g: dict, cause: str) -> None:
        """Close from a non-completion cause (bar grounded / parked at the
        rack / lost lockout) — route through the full judge so pattern-gated,
        banded decisions apply (no more raw THR_DEPTH no-reps on noise)."""
        a = self.attempt
        if a is None:
            self.phase = Phase.IDLE
            return
        if cause.startswith("stand_rack") and ctx.t - a["t0"] > 1.2:
            self._standrack_close_t = ctx.t
        self._judge(ctx, g, a, cause=cause)

    def _judge(self, ctx: FrameContext, g: dict, a: dict,
               cause: str = "completed") -> None:
        """Full Wodx-standard evaluation with the benefit-of-the-doubt bands.

        Check verdicts: OK / BORDERLINE (credit + review flag) / FAIL (no-rep).
        """
        H = g["H"]
        flags = a["flags"]
        fail_reason: Optional[str] = None
        fail_severity = 0.6
        borderline = False
        margins: list[float] = []

        # ---- 1. squat depth (hip crease vs knee line, in H units) ---- #
        if not a["depth_armed"]:
            d = a["max_depth"]
            if d >= THR["depth_bod_margin_h"]:
                # borderline depth — benefit of the doubt to the athlete
                borderline = True
                flags.append("THR_DEPTH_REVIEW")
                margins.append(0.15)
            elif d > -0.06 and a["arm_vis_min"] < 0.5:
                borderline = True
                flags.append("THR_DEPTH_REVIEW")
                margins.append(0.0)
            else:
                fail_reason = "THR_DEPTH"
                fail_severity = min(1.0, (-0.015 - d) / 0.08)
        else:
            margins.append(min(1.0, (a["max_depth"] - THR["depth_enter_margin_h"]) / 0.03))

        # ---- 2. overhead position (robust 2D evidence) ---- #
        # Three tiers: clearly overhead / borderline (credit + review) /
        # clearly not overhead. When the press phase was INVISIBLE to the
        # tracker (no overhead frames at all) the benefit of the doubt
        # credits the rep with a review flag — UNLESS the attempt closed on
        # a deliberate stand-rack pause (the athlete visibly parked the bar
        # at the shoulders: a conscious abort, a clear fault).
        deliberate_park = cause.startswith("stand_rack")
        if not a["saw_overhead"]:
            if deliberate_park:
                fail_reason = fail_reason or "THR_BAR_NOT_OVERHEAD"
            else:
                borderline = True
                flags.append("THR_OVERHEAD_REVIEW")
                margins.append(0.0)
        elif a["overhead"] or a["reach_best"] >= THR["overhead_reach_min_h"]:
            margins.append(min(1.0, max(0.35, a["reach_best"] / 0.12)))
        elif a["reach_best"] >= 0.030:
            # bar rose just above the shoulders but short of clear
            # overhead — inside the measurement uncertainty band
            borderline = True
            flags.append("THR_OVERHEAD_REVIEW")
            margins.append(0.1)
        elif deliberate_park:
            fail_reason = fail_reason or "THR_BAR_NOT_OVERHEAD"
        else:
            # the bar was seen rising but stayed clearly below the
            # shoulders → clear fault
            fail_reason = fail_reason or "THR_BAR_NOT_OVERHEAD"

        # ---- 3. elbow lockout (SOFT: 2D angle unreliable overhead — the
        #         best-arm angle at the best moment is advisory) ---- #
        elb = a["elb_lock_best"]
        if elb < THR["lock_elbow_clear_deg"] and \
                (a["reach_best"] < 0.10 or a["arm_vis_min"] >= 0.6):
            # clearly bent elbows — with the bar barely up (weak reach), OR
            # solidly-tracked arms with the bar decisively overhead (a real
            # visible press-out) → fault
            fail_reason = fail_reason or "THR_LOCKOUT"
            fail_severity = max(fail_severity,
                                (THR["lock_elbow_clear_deg"] - elb) / 40.0)
        elif elb < THR["lock_elbow_deg"]:
            # inside the uncertainty band — credit, flag, cap confidence
            borderline = True
            flags.append("THR_LOCKOUT_REVIEW")
            margins.append(0.25)
        else:
            margins.append(min(1.0, (elb - THR["lock_elbow_deg"]) / 15.0))

        # ---- 4. knee / hip extension at lockout ---- #
        if a["knee_lock_best"] > 0 and a["hip_lock_best"] > 0:
            if a["knee_lock_best"] < THR["lock_knee_clear_deg"]:
                fail_reason = fail_reason or "THR_LOCKOUT"
            elif a["knee_lock_best"] < THR["lock_knee_deg"]:
                borderline = True
                flags.append("THR_LOCKOUT_REVIEW")
                margins.append(0.25)
            else:
                margins.append(min(1.0, (a["knee_lock_best"] - THR["lock_knee_deg"]) / 12.0))
            if a["hip_lock_best"] < THR["lock_hip_clear_deg"]:
                fail_reason = fail_reason or "THR_LOCKOUT"
            elif a["hip_lock_best"] < THR["lock_hip_deg"]:
                borderline = True
                flags.append("THR_LOCKOUT_REVIEW")
                margins.append(0.25)
            else:
                margins.append(min(1.0, (a["hip_lock_best"] - THR["lock_hip_deg"]) / 12.0))
        else:
            # knee/hip extension unmeasurable (ankles occluded through the
            # whole attempt) → doubt favors the athlete, flag for review
            borderline = True
            flags.append("THR_LOCKOUT_REVIEW")
            margins.append(0.1)

        # ---- 5. feet in one line (clear fault only; skipped → review when
        #      the ankles are occluded) ---- #
        if g["ank_l"] is not None and g["ank_r"] is not None:
            ank_drift = max(abs(g["ank_l"].x - a["ank_l0"]),
                            abs(g["ank_r"].x - a["ank_r0"])) / H
            if ank_drift > THR["walk_drift_max_h"]:
                fail_reason = fail_reason or "THR_WALKING"
            elif ank_drift > THR["walk_drift_review_h"]:
                flags.append("THR_WALKING_REVIEW")
        else:
            flags.append("THR_WALKING_REVIEW")

        # review-level: hands resting on the legs during the squat
        if a["min_wr_knee_h"] < 0.10 and a["max_depth"] > 0.0:
            a["flags"].append("THR_HANDS_TO_LEG")

        if fail_reason is not None:
            self._close(ctx, g, NO_REP, fail_reason,
                        norep_confidence(fail_severity, a["vis_min"]))
        else:
            conf = rep_confidence(margins or [0.5], a["vis_min"], borderline)
            self._close(ctx, g, REP, None, conf, borderline)

    # ------------------------------------------------------------------ #
    def force_close(self, t_end: float) -> None:
        """Close any open attempt at stream end (conservative no-rep).
        Attempts still in ARMING never became real attempts → discarded."""
        if self.attempt is None:
            return
        if self.phase == Phase.ARMING or not self._is_thruster_pattern(self.attempt):
            self._discard()
            return
        from core.types import Attempt as _A
        a = self.attempt
        reason = None
        if not a["depth_armed"]:
            reason = "THR_DEPTH"
        elif not a["saw_overhead"]:
            reason = "THR_BAR_NOT_OVERHEAD"
        else:
            reason = "THR_LOW_VIS"
        self.emit(_A(
            movement=self.movement_id, t_start=a["t0"], t_end=t_end,
            frame_start=a["f0"], frame_end=a["f0"], outcome=NO_REP,
            reason_code=reason,
            details={"entry": a["entry"], "max_depth_h": round(a["max_depth"], 3),
                     "depth_armed": a["depth_armed"],
                     "overhead": a["overhead"],
                     "truncated": True},
            review_flags=list(a["flags"]) + ["THR_LOW_VIS"],
            confidence=0.45, borderline=True,
        ))
        self.attempt = None
        self.phase = Phase.IDLE
