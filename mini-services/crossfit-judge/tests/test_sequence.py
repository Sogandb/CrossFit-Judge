"""WOD sequencer v3 tests — THE USER'S EXACT STATE MACHINE (spec 2026-10-09).

  * Global counter 1..126: every ATTEMPT of the expected movement consumes
    one slot — rep or no-rep, quality never blocks progression.
  * Current state THRUSTER|BURPEE switches at the EXACT prescribed counts:
    Thruster 1-18 | 37-51 | 67-78 | 91-99 | 109-114 | 121-123
    Burpee   19-36 | 52-66 | 79-90 | 100-108 | 115-120 | 124-126
  * Wrong-movement attempts are DETECTION NOISE — counted, never numbered,
    never rendered in the ladder.
  * Stall recovery (FSM under-detected a phase tail): remaining slots are
    marked NOT_DETECTED — visible rows, no invented verdicts — and numbering
    stays anchored. No jumps, no dashes, no backward switches.
  * The time cap is only enforced when the start was detected; post-cap
    attempts never consume slots.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.mock_pose import gen_synthetic_workout
from core.sequence import WodSequencer
from core.types import NO_REP, REP, Attempt, SceneModel
from movements.bar_facing_burpee import BarFacingBurpeeFSM
from movements.base import FrameContext
from movements.thruster import ThrusterFSM

GY, H, X0 = 800.0, 500.0, 600.0
LABELS = {"thruster": "تراستر", "bar_facing_burpee": "بورپی رو به بار"}
T, B = "thruster", "bar_facing_burpee"

# The user's EXACT 126-entry table (verbatim spec):
#   Thruster 1-18 | 37-51 | 67-78 | 91-99 | 109-114 | 121-123
#   Burpee   19-36 | 52-66 | 79-90 | 100-108 | 115-120 | 124-126
THRUSTER_RANGES = [(1, 18), (37, 51), (67, 78), (91, 99), (109, 114), (121, 123)]
BURPEE_RANGES = [(19, 36), (52, 66), (79, 90), (100, 108), (115, 120), (124, 126)]


def _user_table() -> dict[int, str]:
    """{rep_no: movement} for all 126 reps — the user's verbatim table."""
    table: dict[int, str] = {}
    for a, b in THRUSTER_RANGES:
        for n in range(a, b + 1):
            table[n] = T
    for a, b in BURPEE_RANGES:
        for n in range(a, b + 1):
            table[n] = B
    assert len(table) == 126
    return table


def _ladder_blocks():
    out = []
    for (t, b) in zip(THRUSTER_RANGES, BURPEE_RANGES):
        out.append({"movement": T, "reps": t[1] - t[0] + 1})
        out.append({"movement": B, "reps": b[1] - b[0] + 1})
    return out


def _wod(blocks, cap=600):
    return {"blocks": blocks, "time_cap_sec": cap}


def _run(wod, faults=None, t_start=6.0, lead_in=6.0):
    """Full pipeline on a synthetic stream (no MediaPipe)."""
    frames = gen_synthetic_workout(wod["blocks"], faults=faults or {},
                                   x0=X0, gy=GY, H=H, lead_in_sec=lead_in)
    scene = SceneModel()
    scene.H = H
    scene.set_ground(GY, 0.0)
    scene.set_bar(X0, GY, 1.0)
    seq = WodSequencer(wod, t_start=t_start, labels_fa=LABELS)
    fsms = [ThrusterFSM(), BarFacingBurpeeFSM()]
    for pf in frames:
        ctx = FrameContext(t=pf.timestamp, frame_index=pf.frame_index,
                           pose=pf, scene=scene)
        for fsm in fsms:
            fsm.process(ctx)
        attempts = []
        for fsm in fsms:
            attempts.extend(fsm.collect())
        if attempts:
            seq.feed(attempts, pf.timestamp)
            closed = seq.sync_fsms(fsms, pf.timestamp)
            if closed:
                seq.feed(closed, pf.timestamp)
    for fsm in fsms:
        fsm.force_close(frames[-1].timestamp)
        seq.feed(fsm.collect(), frames[-1].timestamp)
    seq.flush(frames[-1].timestamp)
    return seq, frames


def _att(movement, outcome, t, dur=1.0, reason=None):
    return Attempt(movement=movement, t_start=t, t_end=t + dur,
                   frame_start=0, frame_end=30, outcome=outcome,
                   reason_code=reason or (None if outcome == REP else "THR_DEPTH"))


# --------------------------------------------------------------------------- #
# THE USER'S TABLE — verbatim
# --------------------------------------------------------------------------- #
def test_rep_ranges_match_user_table():
    seq = WodSequencer(_wod(_ladder_blocks()), t_start=0.0, labels_fa=LABELS)
    s = seq.summary()
    got_t = [(x["rep_start"], x["rep_end"]) for x in s["rep_timeline"]
             if x["movement"] == T]
    got_b = [(x["rep_start"], x["rep_end"]) for x in s["rep_timeline"]
             if x["movement"] == B]
    assert got_t == THRUSTER_RANGES
    assert got_b == BURPEE_RANGES
    assert s["total_prescribed"] == 126


def test_full_126_ladder_matches_user_table_exactly():
    """THE core acceptance test: a synthetic athlete performs the FULL
    126-rep WOD (with faults sprinkled in). The produced ladder must be
    EXACTLY the user's list: rep 1..126, each with its prescribed movement,
    every number in its prescribed range — '۱: تراستر … ۱۹: بورپی …
    ۱۲۶: بورپی'."""
    faults = {
        "thruster": {0: {"depth_h": -0.05}, 40: {"depth_h": -0.05}},
        "bfb": {2: {"chest_touch": 0.36}, 30: {"chest_touch": 0.36}},
    }
    seq, _ = _run(_wod(_ladder_blocks()), faults=faults)
    s = seq.summary()
    assert s["finished"], (s["total_consumed"], s["total_not_detected"])
    assert s["total_consumed"] == 126
    assert s["total_not_detected"] == 0
    ladder = s["ladder"]
    assert len(ladder) == 126
    table = _user_table()
    for i, row in enumerate(ladder):
        assert row["rep_no"] == i + 1, f"numbers must be contiguous 1..126: {i}"
        assert row["movement"] == table[i + 1], \
            f"rep {i + 1}: expected {table[i + 1]}, got {row['movement']}"
        assert row["verdict"] in ("rep", "no_rep")
    # the first burpee is EXACTLY rep 19; second thruster block starts at 37
    assert ladder[18]["movement"] == B and ladder[18]["rep_no"] == 19
    assert ladder[36]["movement"] == T and ladder[36]["rep_no"] == 37
    assert ladder[123]["movement"] == B and ladder[123]["rep_no"] == 124
    # faults → no-reps that STILL consumed their slots
    no_reps = [r for r in ladder if r["verdict"] == "no_rep"]
    assert len(no_reps) >= 2
    assert all(r["reason_fa"] for r in no_reps)
    assert s["finish_time_sec"] is not None and s["finish_time_sec"] > 0


def test_user_state_machine_variables():
    """The sequencer exposes the user's exact state variables: current state
    (THRUSTER|BURPEE), round counter (18/15/12/9/6/3), round progress, and
    the global counter — with the user's transition logic between them."""
    seq = WodSequencer(_wod(_ladder_blocks()), t_start=0.0, labels_fa=LABELS)
    assert seq.current_state == T and seq.round_no == 1 and seq.round_target == 18
    assert seq.round_progress == 0 and seq.global_counter == 1
    # 18 thruster attempts consumed → switch to BURPEE, SAME round; the
    # round progress now counts the round's BURPEES (fresh from 0)
    for i in range(18):
        seq.feed([_att(T, REP, 1.0 + i)], 2.0 + i)
    assert seq.current_state == B and seq.round_no == 1
    assert seq.round_progress == 0 and seq.global_counter == 19
    # 18 burpees → next ROUND, target 15, back to THRUSTER
    for i in range(18):
        seq.feed([_att(B, REP, 30.0 + i)], 31.0 + i)
    assert seq.current_state == T and seq.round_no == 2 and seq.round_target == 15
    assert seq.round_progress == 0 and seq.global_counter == 37
    # last round: 3 thrusters + 3 burpees → WOD COMPLETE, counting stops
    seq2 = WodSequencer(_wod([{"movement": T, "reps": 3},
                              {"movement": B, "reps": 3}]), t_start=0.0,
                        labels_fa=LABELS)
    for i in range(3):
        seq2.feed([_att(T, REP, 1.0 + i)], 2.0 + i)
    for i in range(3):
        seq2.feed([_att(B, REP, 5.0 + i)], 6.0 + i)
    assert seq2.finished
    s = seq2.summary()
    assert s["total_consumed"] == 6 and s["finished"]
    # after completion nothing else is ever counted again
    seq2.feed([_att(B, REP, 20.0)], 21.0)
    assert seq2.summary()["total_consumed"] == 6
    assert seq2.summary()["excess_events"] == 1


# --------------------------------------------------------------------------- #
# Counting semantics
# --------------------------------------------------------------------------- #
def test_no_reps_consume_slots_and_advance():
    """USER SPEC: 'چه رپ باشه چه نورپ' — no-reps count toward the prescribed
    count; the switch to the next movement happens anyway."""
    blocks = [{"movement": T, "reps": 3}, {"movement": B, "reps": 3}]
    faults = {"thruster": {0: {"depth_h": -0.05}, 1: {"depth_h": -0.05}},
              "bfb": {0: {"chest_touch": 0.36}}}
    seq, _ = _run(_wod(blocks), faults=faults)
    s = seq.summary()
    assert s["blocks"][0]["attempts"] == 3
    assert s["blocks"][0]["credited"] <= 2
    assert s["blocks"][0]["no_reps"] >= 1
    assert s["blocks"][0]["complete"] is True        # ← the user's core rule
    assert s["blocks"][1]["attempts"] == 3
    assert s["finished"]
    assert s["total_credited"] < s["total_consumed"]
    # the ladder rows for the no-reps carry the verdict, still numbered 1..6
    ladder = s["ladder"]
    assert [r["rep_no"] for r in ladder] == [1, 2, 3, 4, 5, 6]
    assert [r["movement"] for r in ladder] == [T, T, T, B, B, B]
    assert sum(1 for r in ladder if r["verdict"] == "no_rep") >= 3


def test_full_workout_all_credited():
    blocks = [{"movement": T, "reps": 3}, {"movement": B, "reps": 3},
              {"movement": T, "reps": 2}, {"movement": B, "reps": 2}]
    seq, _ = _run(_wod(blocks))
    s = seq.summary()
    assert s["finished"], s
    assert s["total_credited"] == 10
    assert s["total_consumed"] == 10
    assert s["per_movement"][T]["credited"] == 5
    assert s["per_movement"][B]["credited"] == 5
    assert s["finish_time_sec"] is not None and s["finish_time_sec"] > 0


# --------------------------------------------------------------------------- #
# Detection noise — suppressed, never numbered
# --------------------------------------------------------------------------- #
def test_sporadic_wrong_movement_is_noise():
    """Isolated cross-detections during an ACTIVE phase are noise: they
    consume no slot, never appear in the ladder, and never switch state."""
    blocks = [{"movement": T, "reps": 3}, {"movement": B, "reps": 3}]
    seq = WodSequencer(_wod(blocks), t_start=0.0, labels_fa=LABELS)
    seq.feed([_att(T, REP, 1.0)], 2.0)
    seq.feed([_att(T, REP, 3.0)], 4.0)
    seq.feed([_att(B, REP, 4.5)], 5.5)     # spurious burpee mid-thrusters
    seq.feed([_att(T, REP, 6.0)], 7.0)     # thruster phase completes
    seq.feed([_att(B, REP, 12.0)], 13.0)
    seq.feed([_att(B, REP, 14.0)], 15.0)
    seq.feed([_att(B, REP, 16.0)], 17.0)
    seq.flush(20.0)
    s = seq.summary()
    assert s["total_consumed"] == 6
    assert s["finished"]
    assert s["noise_events"] == 1          # counted, but …
    # … never in the ladder and never numbered
    numbered = [e for e in seq.events if e.rep_no is not None]
    assert len(numbered) == 6
    assert all(e.attempt.movement == e.expected_movement for e in numbered)
    ladder_moves = [r["movement"] for r in s["ladder"]]
    assert ladder_moves == [T, T, T, B, B, B]


# --------------------------------------------------------------------------- #
# Stall recovery — the honest replacement for realign
# --------------------------------------------------------------------------- #
def test_stall_recovery_marks_not_detected_and_anchors_numbering():
    """FSM saw only 1 of 3 thrusters; the athlete moved on to burpees.
    The remaining thruster slots (2, 3) become NOT_DETECTED rows — visible,
    no invented verdicts — the burpees consume EXACTLY 4, 5, 6, and no rep
    number ever jumps or dashes."""
    blocks = [{"movement": T, "reps": 3}, {"movement": B, "reps": 3}]
    seq = WodSequencer(_wod(blocks), t_start=0.0, labels_fa=LABELS)
    seq.feed([_att(T, REP, 1.0)], 2.0)               # 1 of 3 detected
    seq.feed([_att(B, REP, 30.0, dur=2.0)], 32.0)    # athlete moved on
    seq.feed([_att(B, REP, 32.0, dur=2.0)], 34.0)    # stream confirms → recovery
    seq.feed([_att(B, REP, 34.0, dur=2.0)], 36.0)
    s = seq.summary()
    assert s["finished"]
    assert any(f["code"] == "SEQ_SLOTS_NOT_DETECTED" for f in seq.flags)
    ladder = s["ladder"]
    assert [r["rep_no"] for r in ladder] == [1, 2, 3, 4, 5, 6]
    assert ladder[0]["verdict"] == "rep"                       # detected thruster
    assert ladder[1]["verdict"] == "not_detected"              # missed slot 2
    assert ladder[2]["verdict"] == "not_detected"              # missed slot 3
    assert [r["verdict"] for r in ladder[3:]] == ["rep", "rep", "rep"]
    assert s["total_not_detected"] == 2
    assert s["total_consumed"] == 4
    assert s["total_credited"] == 4   # not_detected rows never score
    assert s["per_movement"][B]["credited"] == 3


def test_stall_recovery_whole_phase_missed():
    """The video begins mid-WOD at the burpees (the whole first thruster
    phase was never on camera): all 18 thruster slots are not_detected and
    the burpees are numbered 19..36 — anchored, never renumbered."""
    blocks = [{"movement": T, "reps": 18}, {"movement": B, "reps": 18}]
    seq = WodSequencer(_wod(blocks), t_start=0.0, labels_fa=LABELS)
    for i in range(18):
        seq.feed([_att(B, REP, 10.0 + 2 * i, dur=1.5)], 12.0 + 2 * i)
    s = seq.summary()
    assert s["total_not_detected"] == 18
    assert s["total_consumed"] == 18
    bfb_rows = [r for r in s["ladder"] if r["verdict"] in ("rep", "no_rep")]
    assert [r["rep_no"] for r in bfb_rows] == list(range(19, 37))


def test_recovery_inherits_only_recent_held_attempts():
    """Held next-movement attempts that started WHILE the expected movement
    was still being consumed are cross-detection duplicates — they must NOT
    consume slots of the next phase. Only attempts starting at/after the
    last real slot (minus the overlap tolerance) are inherited."""
    blocks = [{"movement": T, "reps": 3}, {"movement": B, "reps": 3}]
    seq = WodSequencer(_wod(blocks), t_start=0.0, labels_fa=LABELS)
    seq.feed([_att(T, REP, 1.0)], 2.0)
    # thruster 2 runs t=3..4; a burpee cross-detection starts at t=2.8
    # (overlapping ACTIVE thruster work) → duplicate, must become noise
    seq.feed([_att(T, REP, 3.0)], 4.0)
    seq.feed([_att(B, REP, 2.8, dur=1.0)], 4.0)   # dup: started during thruster
    seq.feed([_att(T, REP, 5.0)], 6.0)            # thruster 3 ends t=6 → phase done
    # now burpees are expected; real burpees:
    seq.feed([_att(B, REP, 8.0, dur=1.5)], 10.0)
    seq.feed([_att(B, REP, 10.0, dur=1.5)], 12.0)
    seq.feed([_att(B, REP, 12.0, dur=1.5)], 14.0)
    seq.flush(16.0)
    s = seq.summary()
    assert s["finished"]
    assert s["total_consumed"] == 6
    assert s["noise_events"] == 1          # the duplicate was noise, not a slot


# --------------------------------------------------------------------------- #
# Time cap — honest semantics
# --------------------------------------------------------------------------- #
def test_time_cap_cuts_late_reps_when_start_known():
    """cap=1s with a KNOWN start → attempts after the cap never consume
    slots (the workout is over); they are logged as post-cap events."""
    blocks = [{"movement": T, "reps": 1}, {"movement": B, "reps": 1}]
    seq = WodSequencer(_wod(blocks, cap=1), t_start=6.0, labels_fa=LABELS,
                       cap_enforced=True)
    seq.feed([_att(T, REP, 6.5)], 7.0)     # post-cap (ends after t_start+1)
    seq.feed([_att(B, REP, 8.0)], 9.0)
    seq.flush(10.0)
    s = seq.summary()
    assert not s["finished"]
    assert s["cap_enforced"] and s["capped"] and s["cap_hit"]
    assert s["total_consumed"] == 0        # post-cap never consumes
    assert s["post_cap_events"] == 2
    assert all(e.kind == "post_cap" and e.rep_no is None
               for e in seq.events)


def test_cap_not_enforced_when_start_unknown():
    """The user's exact failure mode: beeps were not found → t_start=0 →
    enforcing the 600s cap from video start would silently discard the
    video tail. With cap_enforced=False every attempt counts."""
    blocks = [{"movement": T, "reps": 2}, {"movement": B, "reps": 2}]
    seq = WodSequencer(_wod(blocks, cap=600), t_start=0.0, labels_fa=LABELS,
                       cap_enforced=False)
    for i in range(2):
        seq.feed([_att(T, REP, 700.0 + i)], 701.0 + i)   # WAY past 600s
    for i in range(2):
        seq.feed([_att(B, REP, 710.0 + i)], 711.0 + i)
    seq.flush(720.0)
    s = seq.summary()
    assert s["finished"]
    assert s["total_consumed"] == 4
    assert not s["capped"]
    assert s["cap_enforced"] is False


# --------------------------------------------------------------------------- #
# Excess & stream end
# --------------------------------------------------------------------------- #
def test_excess_reps_flagged_not_scored():
    wod = _wod([{"movement": T, "reps": 1}, {"movement": B, "reps": 1}])
    seq = WodSequencer(wod, t_start=0.0, labels_fa=LABELS)
    seq.feed([_att(T, REP, 1.0)], 1.0)
    seq.feed([_att(B, REP, 3.0)], 3.0)
    seq.feed([_att(B, REP, 5.0)], 5.0)     # excess after the WOD completed
    s = seq.summary()
    assert s["finished"]
    assert s["total_credited"] == 2        # excess never scores
    assert s["total_consumed"] == 2
    assert s["excess_events"] == 1
    assert any(f["code"] == "SEQ_EXCESS_REPS" for f in seq.flags)


def test_video_end_leaves_not_reached_rows():
    """The video ends before the WOD does: unconsumed slots appear as
    not_reached rows — the ladder ALWAYS has all 126 numbers."""
    seq = WodSequencer(_wod(_ladder_blocks()), t_start=0.0, labels_fa=LABELS)
    for i in range(10):
        seq.feed([_att(T, REP, 1.0 + i)], 2.0 + i)
    seq.flush(20.0)
    s = seq.summary()
    assert not s["finished"]
    assert s["total_consumed"] == 10
    assert s["total_not_reached"] == 116
    ladder = s["ladder"]
    assert len(ladder) == 126
    assert [r["verdict"] for r in ladder[:10]] == ["rep"] * 10
    assert all(r["verdict"] == "not_reached" for r in ladder[10:])
    assert all(r["movement"] == _user_table()[r["rep_no"]] for r in ladder)
