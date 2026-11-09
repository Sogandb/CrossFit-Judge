"""v2.4 aligned engine — scenarios taken from REAL failures on the Arian /
Payam videos: fatigue bends, bar set-down hinge, sitting/lying rests, the
bar moving between blocks, pose drop-outs, and a video that ends before the
ladder does. Ground truth = what the generator performed."""
from __future__ import annotations

import json

import pytest

from core.analyzer import Analyzer
from core.mock_pose import (SkeletonBuilder, gen_bfb_rep, gen_thruster_rep,
                            pose_frame)
from core.types import Point

WOD = json.load(open("data/wods/wodx_ladder_wod1.json"))
GY, H, FPS = 800.0, 500.0, 30.0
BLOCKS = [(b["movement"], b["reps"]) for b in WOD["blocks"]]


def rest(out, t, x, kind, dur):
    for _ in range(int(dur * FPS)):
        sb = SkeletonBuilder(x, GY, H)
        if kind == "stand":
            b = sb.build(hip_y=GY - .5 * H, knee_y=GY - .26 * H, ankle_y=GY, wrist_mode="hang")
        elif kind == "hands_on_knees":
            b = sb.build(sh_y=GY - .62 * H, hip_y=GY - .5 * H, knee_y=GY - .26 * H, ankle_y=GY,
                         wrist_mode="free", wrist_y=GY - .28 * H, sh_x_offset=.1 * H)
        elif kind == "bar_hinge":
            b = sb.build(sh_y=GY - .58 * H, hip_y=GY - .52 * H, knee_y=GY - .28 * H, ankle_y=GY,
                         wrist_mode="ground", sh_x_offset=.15 * H)
        elif kind == "sit":
            b = sb.build(sh_y=GY - .48 * H, hip_y=GY - .12 * H, knee_y=GY - .30 * H, ankle_y=GY,
                         wrist_mode="ground")
        elif kind == "lie":
            b = sb.build(sh_y=GY - .07 * H, hip_y=GY - .07 * H, knee_y=GY - .08 * H,
                         ankle_y=GY - .04 * H, wrist_mode="ground")
        out.append(pose_frame(b, t, len(out)))
        t += 1 / FPS
    return t


def workout(bar_x_by_block=None, rests=None, thr_faults=None, bfb_faults=None,
            upto=126, dropout=None):
    """rests: {global_rep_index_before_which: [(kind, seconds), ...]}"""
    bar_x_by_block = bar_x_by_block or {}
    rests, thr_faults, bfb_faults = rests or {}, thr_faults or {}, bfb_faults or {}
    out, t, n_thr, n_bfb, g = [], 0.0, 0, 0, 0
    t = rest(out, t, 600.0, "stand", 2.0)
    side = -1
    for bi, (mv, reps) in enumerate(BLOCKS):
        bar_x = bar_x_by_block.get(bi, 600.0)
        for k in range(reps):
            if g >= upto:
                break
            for kind, sec in rests.get(g, []):
                t = rest(out, t, bar_x + (0 if mv == "thruster" else side * .55 * H), kind, sec)
            if mv == "thruster":
                kw = dict(thr_faults.get(n_thr, {}))
                kw.setdefault("entry", "ground" if k == 0 else "rack")
                t = gen_thruster_rep(out, t, bar_x, GY, H, len(out), fps=FPS, **kw)
                n_thr += 1
            else:
                kw = dict(bfb_faults.get(n_bfb, {}))
                t = gen_bfb_rep(out, t, bar_x + side * .55 * H, GY, H, len(out), bar_x,
                                fps=FPS, **kw)
                n_bfb += 1
                if kw.get("cross", True):
                    side = -side
            g += 1
        t = rest(out, t, bar_x, "stand", 0.8)
    t = rest(out, t, 600.0, "stand", 1.5)
    if dropout:
        for lo, hi in dropout:
            for pf in out:
                if lo <= pf.timestamp <= hi:
                    pf.points, pf.person_detected = {}, False
    return out


def analyse(frames, **meta):
    job = {"wod": WOD, "meta": {"pose_source": "mock", "mock_lead_in_sec": 0.0,
                                "_mock_frames": frames, **meta}}
    out = Analyzer(job, lambda *a: None).run()
    assert out.ok, out.error_fa
    return out.result


def ladder(r):
    return {row["rep_no"]: row for row in r["summary"]["ladder"]}


def verdicts(r, lo, hi):
    L = ladder(r)
    return [L[i]["verdict"] for i in range(lo, hi + 1)]


def test_clean_full_workout_exact_ladder():
    r = analyse(workout())
    s = r["summary"]
    assert s["finished"] and s["total_credited"] == 126 and s["total_not_detected"] == 0
    assert s["noise_events"] == 0
    assert r["overview"]["stop_kind"] == "finish"


def test_bar_setdown_hinge_is_not_burpee_19():
    # hands on the bar, bend, release, stand — between the 18th thruster and the first burpee
    r = analyse(workout(rests={18: [("bar_hinge", 2.0), ("stand", 0.6)]}))
    L = ladder(r)
    assert L[19]["verdict"] == "rep" and L[19]["movement"] == "bar_facing_burpee"
    assert r["summary"]["total_no_reps"] == 0 and r["summary"]["total_credited"] == 126


def test_fatigue_bends_and_rests_never_become_attempts():
    rests = {0: [("hands_on_knees", 2.5)],            # bend before the very first thruster
             8: [("sit", 4.0), ("stand", 1.0)],       # sit down to breathe mid-block
             18: [("hands_on_knees", 3.0)],           # bend after the bar is down
             25: [("lie", 5.0), ("stand", 2.0)],      # lie on the floor mid burpee block
             36: [("hands_on_knees", 2.0), ("sit", 3.0)],
             60: [("stand", 25.0)]}                   # a 25 s rest
    r = analyse(workout(rests=rests))
    s = r["summary"]
    assert s["total_credited"] == 126 and s["total_no_reps"] == 0
    assert s["total_not_detected"] == 0 and s["finished"]
    assert s["noise_events"] + len([f for f in r["sequencer_flags"] if f["code"] == "SEQ_AMBIGUOUS_EVENT"]) >= 1


def test_bar_moves_between_blocks_burpees_still_judged_correctly():
    bar = {1: 760.0, 3: 520.0, 5: 700.0, 7: 640.0, 9: 800.0, 11: 560.0, 0: 600.0,
           2: 600.0, 4: 600.0, 6: 600.0, 8: 600.0, 10: 600.0}
    r = analyse(workout(bar_x_by_block=bar))
    s = r["summary"]
    assert s["total_credited"] == 126 and s["total_no_reps"] == 0 and s["finished"]


def test_detection_dropout_marks_exact_slots_and_does_not_shift_the_rest():
    base = workout()
    # find the time of burpee #25 (global rep 25) from the clean run and black out 3 burpees
    r0 = analyse(base)
    t25 = ladder(r0)[25]["t_start"]; t27 = ladder(r0)[27]["t_end"]
    r = analyse(workout(dropout=[(t25 - 0.2, t27 + 0.2)]))
    L = ladder(r)
    assert [L[i]["verdict"] for i in (25, 26, 27)] == ["not_detected"] * 3
    assert all(L[i]["verdict"] == "rep" for i in (24, 28, 29, 36, 37, 60, 100, 126))
    assert r["summary"]["finished"] and r["summary"]["total_credited"] == 123


def test_video_ends_early_never_declares_finish():
    r = analyse(workout(upto=112))
    s = r["summary"]
    assert not s["finished"] and s["total_credited"] == 112
    assert verdicts(r, 113, 126) == ["not_reached"] * 14
    assert r["overview"]["stop_kind"] in ("last_rep", "cap")


def test_no_rep_lands_on_the_right_slot():
    r = analyse(workout(thr_faults={19: dict(depth_h=-0.12)}))   # 20th thruster: clearly above parallel
    L = ladder(r)
    thr_slots = [k for k, v in L.items() if v["movement"] == "thruster"]
    bad = [k for k in thr_slots if L[k]["verdict"] == "no_rep"]
    assert len(bad) == 1, bad
    assert r["summary"]["total_credited"] == 125 and r["summary"]["total_not_detected"] == 0
