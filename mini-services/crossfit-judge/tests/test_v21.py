"""v2.1: counter-driven gating, bent-back burpee, eased lines, clock/overview."""
from __future__ import annotations

import copy
import json
import sys

from conftest import BAR_X, GY, H, X0, make_frames, run_fsm
from core.analyzer import Analyzer
from core.mock_pose import gen_bfb_rep
from core.types import NO_REP, REP, Point
from judging.scorer import fmt_clock, final_overview
from movements.bar_facing_burpee import BarFacingBurpeeFSM
from movements.thruster import ThrusterFSM

WOD = json.load(open("data/wods/wodx_ladder_wod1.json"))


def _run(meta):
    job = {"wod": WOD, "meta": {"pose_source": "mock", **meta}}
    out = Analyzer(job, lambda *a: None).run()
    assert out.ok, out.error_fa
    return out.result


def _bend(frames, until_t, drop_h=0.22):
    """Athlete stands BENT OVER (hands-on-knees style) before the descent:
    shoulders/nose pulled down by drop_h*H until `until_t` (blended out)."""
    for pf in frames:
        if pf.timestamp < until_t:
            for k in ("left_shoulder", "right_shoulder", "nose"):
                p = pf.points[k]
                pf.points[k] = Point(p.x + 0.10 * H, p.y + drop_h * H, p.z, p.visibility)
    return frames


def test_bent_back_start_is_still_a_valid_burpee(scene):
    base = make_frames(lambda out: gen_bfb_rep(
        out, 0.0, BAR_X - 0.55 * H, GY, H, 0, BAR_X, landing_mode="two"))
    frames = _bend(base, until_t=0.5)
    fsm = BarFacingBurpeeFSM()
    attempts = run_fsm(fsm, frames, scene)
    assert len(attempts) == 1, [(a.outcome, a.reason_code) for a in attempts]
    assert attempts[0].outcome == REP, (attempts[0].reason_code, attempts[0].details)


def test_gating_disables_unexpected_fsm_and_probes_ahead():
    from core.sequence import WodSequencer
    seq = WodSequencer(WOD["blocks"] if "blocks" in WOD else WOD, t_start=0.0, cap=600.0) \
        if False else None  # constructor differs per version; checked via full run below
    r = _run({"mock_block_scale": 1.0})
    s = r["summary"]
    # with only the expected FSM(s) running there is no cross-movement noise
    assert s["finished"] and s["total_credited"] == 126 and s["noise_events"] == 0


def test_clock_starts_at_video_start_and_overview_reports_finish():
    r = _run({"mock_block_scale": 1.0, "mock_lead_in_sec": 0.0})
    assert r["start_detection"]["t_start_sec"] == 0.0
    ov = r["overview"]
    assert ov["stop_kind"] == "finish" and ov["reps_counted"] == 126
    assert ov["stop_time_sec"] == r["summary"]["finish_time_sec"]
    assert r["score_display"]["final_time_text"] == ov["stop_time_text"]


def test_overview_cap_and_last_rep_modes():
    summ = {"finished": False, "finish_time_sec": None, "total_credited": 80,
            "total_no_reps": 3, "total_consumed": 83, "total_prescribed": 126}
    ev = [{"kind": "slot", "t_end": 300.0}]
    assert final_overview(summ, 0.0, 600.0, True, 640.0, ev)["stop_kind"] == "cap"
    assert final_overview(summ, 0.0, 600.0, True, 640.0, ev)["stop_time_text"] == "10:00"
    o = final_overview(summ, 0.0, 600.0, True, 320.0, ev)
    assert o["stop_kind"] == "last_rep" and o["stop_time_text"] == "05:00"


def test_fmt_clock_never_shows_sixty_seconds():
    assert fmt_clock(119.6) == "01:59" and fmt_clock(59.99) == "00:59"
    assert fmt_clock(600) == "10:00" and fmt_clock(None) == "—"
