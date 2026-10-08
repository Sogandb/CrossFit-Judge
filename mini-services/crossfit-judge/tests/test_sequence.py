"""WOD sequencer tests — strict rep-range state machine (user spec v2.4).

The sequencer OWNS the WOD structure:
  * blocks advance on ATTEMPT COUNT (rep or no-rep both consume a slot)
  * the overall rep number is anchored to the WOD prescription
    (thruster 1-18, burpee 19-36, thruster 37-51, …)
  * per-attempt judging (rep / no-rep + confidence) never blocks progression
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
# THE USER SPEC — exact WOD ladder numbering (Wodx WOD-1, first two rounds)
# --------------------------------------------------------------------------- #
def test_rep_numbering_anchored_to_ladder():
    """Thruster 1-18 | Burpee 19-36 | Thruster 37-51 | Burpee 52-66 — even
    with no-reps sprinkled in, block switches happen at the EXACT counts and
    every consumed attempt carries its prescribed overall rep number."""
    blocks = [{"movement": "thruster", "reps": 18},
              {"movement": "bar_facing_burpee", "reps": 18},
              {"movement": "thruster", "reps": 15},
              {"movement": "bar_facing_burpee", "reps": 15}]
    faults = {  # a mix of good and bad reps — counting must not care
        "thruster": {0: {"depth_h": -0.05}, 5: {"lockout": False}},
        "bfb": {2: {"chest_touch": 0.36}},
    }
    seq, _ = _run(_wod(blocks), faults=faults)
    s = seq.summary()
    tl = s["rep_timeline"]
    assert [(b["rep_start"], b["rep_end"]) for b in tl] == \
        [(1, 18), (19, 36), (37, 51), (52, 66)]
    # all four blocks fully consumed → the workout progressed end to end
    assert all(b["attempts"] == b["reps"] for b in s["blocks"]), s["blocks"]
    # every slot-consuming event carries the prescribed overall number
    consumed = [e for e in seq.events if e.rep_no is not None]
    assert [e.rep_no for e in consumed] == list(range(1, 67))
    # block boundaries: the first burpee event is EXACTLY rep 19; the second
    # thruster block starts EXACTLY at rep 37; second burpee block at 52
    first_bfb = next(e for e in consumed if e.attempt.movement == "bar_facing_burpee")
    assert first_bfb.rep_no == 19
    second_thr = next(e for e in consumed
                      if e.attempt.movement == "thruster" and e.rep_no > 36)
    assert second_thr.rep_no == 37
    second_bfb = next(e for e in consumed
                      if e.attempt.movement == "bar_facing_burpee" and e.rep_no > 51)
    assert second_bfb.rep_no == 52
    # quality: the faulty reps are no-reps but STILL consumed their slot
    # (thruster depth no-rep + bfb chest no-rep; the lockout fault lands in
    # the borderline band → credited with a review flag, by design)
    no_reps = [e for e in consumed if e.attempt.outcome == NO_REP]
    assert len(no_reps) == 2
    assert all(e.rep_no is not None for e in no_reps)
    assert sum(1 for e in consumed if e.attempt.borderline) >= 1
    assert s["total_attempted"] == 66
    assert s["total_credited"] == 66 - len(no_reps)


def test_no_reps_consume_slots_and_advance():
    """USER SPEC: 'چه رپ باشه چه نورپ' — no-reps count toward the block's
    prescribed count; the switch to the next movement happens anyway."""
    blocks = [{"movement": "thruster", "reps": 3},
              {"movement": "bar_facing_burpee", "reps": 3}]
    faults = {"thruster": {0: {"depth_h": -0.05},   # rep 1 no-rep
                           1: {"depth_h": -0.05}},  # rep 2 no-rep
              "bfb": {0: {"chest_touch": 0.36}}}    # rep 4 no-rep
    seq, _ = _run(_wod(blocks), faults=faults)
    s = seq.summary()
    # the thruster block still consumed all 3 slots and ADVANCED to burpees
    assert s["blocks"][0]["attempts"] == 3
    assert s["blocks"][0]["credited"] <= 2          # at least the no-reps lost
    assert s["blocks"][0]["no_reps"] >= 1
    assert s["blocks"][0]["complete"] is True       # ← the user's core rule
    # burpees were reached and consumed their 3 slots too (workout finished)
    assert s["blocks"][1]["attempts"] == 3
    assert s["finished"]
    # no-reps never score
    assert s["total_credited"] < s["total_attempted"]
    assert s["per_movement"]["thruster"]["no_reps"] >= 1


def test_full_workout_all_credited():
    blocks = [{"movement": "thruster", "reps": 3},
              {"movement": "bar_facing_burpee", "reps": 3},
              {"movement": "thruster", "reps": 2},
              {"movement": "bar_facing_burpee", "reps": 2}]
    seq, _ = _run(_wod(blocks))
    s = seq.summary()
    assert s["finished"], s
    assert s["total_credited"] == 10
    assert s["total_attempted"] == 10
    assert s["per_movement"]["thruster"]["credited"] == 5
    assert s["per_movement"]["bar_facing_burpee"]["credited"] == 5
    assert s["finish_time_sec"] is not None and s["finish_time_sec"] > 0


def test_time_cap_cuts_late_reps():
    """cap = 1s after start → every rep lands post-cap → nothing scores and
    no slot is consumed after the cap."""
    blocks = [{"movement": "thruster", "reps": 1},
              {"movement": "bar_facing_burpee", "reps": 1}]
    seq, frames = _run(_wod(blocks, cap=1), t_start=6.0)
    s = seq.summary()
    assert not s["finished"]
    post_cap = [e for e in seq.events if e.post_cap]
    assert all(e.rep_no is None for e in post_cap)   # post-cap ≠ slot
    assert s["capped"]
    assert s["total_attempted"] == 0 or s["total_credited"] == 0


def test_sequencer_realigned_when_thrusters_under_detected():
    """The FSM detected fewer thrusters than performed; the athlete moved on
    to burpees. The sequencer must realign to the burpee block, flag the
    thruster block incomplete, and — critically — anchor the burpee reps at
    their PRESCRIBED numbers (4..6 here, since 3 thruster slots precede)."""
    blocks = [{"movement": "thruster", "reps": 3},
              {"movement": "bar_facing_burpee", "reps": 3}]
    seq = WodSequencer(_wod(blocks), t_start=0.0, labels_fa=LABELS)
    seq.feed([_att("thruster", REP, 1.0)], 2.0)          # 1 of 3 detected
    seq.feed([_att("bar_facing_burpee", REP, 30.0)], 31.0)   # athlete moved on
    seq.feed([_att("bar_facing_burpee", REP, 32.0)], 33.0)   # 2nd confirms
    seq.feed([_att("bar_facing_burpee", REP, 34.0)], 35.0)
    s = seq.summary()
    assert seq.block_idx == 1
    assert any(f["code"] == "SEQ_BLOCK_INCOMPLETE" for f in seq.flags)
    bfb = [e for e in seq.events if e.attempt.movement == "bar_facing_burpee"
           and e.rep_no is not None]
    assert [e.rep_no for e in bfb] == [4, 5, 6]       # anchored to the timeline
    assert s["per_movement"]["bar_facing_burpee"]["credited"] == 3


def test_sporadic_wrong_movement_not_counted():
    """Isolated cross-detections during an ACTIVE block are logged as
    mismatches — they consume no slot and trigger no realignment."""
    blocks = [{"movement": "thruster", "reps": 3},
              {"movement": "bar_facing_burpee", "reps": 3}]
    seq = WodSequencer(_wod(blocks), t_start=0.0, labels_fa=LABELS)
    seq.feed([_att("thruster", REP, 1.0)], 2.0)
    seq.feed([_att("thruster", REP, 3.0)], 4.0)
    # spurious burpee while thrusters are ACTIVE → noise
    seq.feed([_att("bar_facing_burpee", REP, 4.5)], 5.5)
    seq.feed([_att("thruster", REP, 6.0)], 7.0)       # thruster block completes
    # burpees now expected; the athlete does all 3
    seq.feed([_att("bar_facing_burpee", REP, 12.0)], 13.0)
    seq.feed([_att("bar_facing_burpee", REP, 14.0)], 15.0)
    seq.feed([_att("bar_facing_burpee", REP, 16.0)], 17.0)
    seq.flush(20.0)
    s = seq.summary()
    assert s["blocks"][0]["attempts"] == 3            # only the 3 thrusters
    assert s["blocks"][1]["attempts"] == 3            # only the 3 late burpees
    assert s["total_attempted"] == 6
    assert s["finished"]
    assert any(f["code"] == "SEQ_MOVEMENT_MISMATCH" for f in seq.flags)


def test_excess_reps_flagged_not_scored():
    wod = _wod([{"movement": "thruster", "reps": 1},
                {"movement": "bar_facing_burpee", "reps": 1}])
    seq = WodSequencer(wod, t_start=0.0, labels_fa=LABELS)
    seq.feed([_att("thruster", REP, 1.0)], 1.0)
    seq.feed([_att("bar_facing_burpee", REP, 3.0)], 3.0)
    # extra burpee beyond prescription (both blocks already complete)
    seq.feed([_att("bar_facing_burpee", REP, 5.0)], 5.0)
    s = seq.summary()
    assert s["finished"]
    assert s["total_credited"] == 2  # excess never scores
    assert s["total_attempted"] == 2
    assert any(f["code"] == "SEQ_EXCESS_REPS" for f in seq.flags)


def test_backward_realign_when_sequencer_drifted_ahead():
    """Block 0 was left incomplete by a forward realign; at the END of the
    WOD (last block, no later thruster block exists) further thruster
    attempts arrive → the sequencer realigns BACKWARD to the earliest
    incomplete thruster block, fills it, and the workout completes."""
    blocks = [{"movement": "thruster", "reps": 3},
              {"movement": "bar_facing_burpee", "reps": 3},
              {"movement": "thruster", "reps": 2},
              {"movement": "bar_facing_burpee", "reps": 2}]
    seq = WodSequencer(_wod(blocks), t_start=0.0, labels_fa=LABELS)
    # only 1 of 3 thrusters detected before the athlete moves on
    seq.feed([_att("thruster", REP, 1.0)], 2.0)
    # burpee stream (2+, thrusters quiet) → forward realign to block 1,
    # block 0 flagged incomplete (1/3)
    seq.feed([_att("bar_facing_burpee", REP, 10.0)], 11.0)
    seq.feed([_att("bar_facing_burpee", REP, 12.0)], 13.0)   # realign fires
    assert seq.block_idx == 1
    assert seq.blocks[1].attempts == 2                 # held burpees consumed
    seq.feed([_att("bar_facing_burpee", REP, 14.0)], 15.0)   # block 1 done
    assert seq.block_idx == 2
    seq.feed([_att("thruster", REP, 20.0)], 21.0)      # block 2 done (2/2)
    seq.feed([_att("thruster", REP, 22.0)], 23.0)
    assert seq.block_idx == 3
    seq.feed([_att("bar_facing_burpee", REP, 30.0)], 31.0)   # block 3 done
    seq.feed([_att("bar_facing_burpee", REP, 32.0)], 33.0)
    assert not seq.finished                            # block 0 still 1/3
    # late thruster attempts: no LATER thruster block exists, but block 0
    # is still incomplete → BACKWARD realign fills it (reps 2 and 3)
    seq.feed([_att("thruster", REP, 40.0)], 41.0)
    seq.feed([_att("thruster", REP, 42.0)], 43.0)      # backward realign fires
    assert any(f["code"] == "SEQ_REALIGN_BACKWARD" for f in seq.flags)
    s = seq.summary()
    assert s["finished"]                               # all blocks now full
    assert s["blocks"][0]["attempts"] == 3
    assert s["total_attempted"] == 10
    assert s["total_credited"] == 10


def test_rep_ranges_match_user_table():
    """The REAL Wodx ladder (18/18/15/15/12/12/9/9/6/6/3/3 = 126) produces
    EXACTLY the user's table:
      Thruster 1-18 | 37-51 | 67-78 | 91-99 | 109-114 | 121-123
      Burpee   19-36 | 52-66 | 79-90 | 100-108 | 115-120 | 124-126
    """
    t, b = "thruster", "bar_facing_burpee"
    blocks = [{t: 18, b: 18, t: 15, b: 15, t: 12, b: 12,
               t: 9, b: 9, t: 6, b: 6, t: 3, b: 3} for _ in range(0)]  # noqa
    blocks = []
    for mv, n in [(t, 18), (b, 18), (t, 15), (b, 15), (t, 12), (b, 12),
                  (t, 9), (b, 9), (t, 6), (b, 6), (t, 3), (b, 3)]:
        blocks.append({"movement": mv, "reps": n})
    seq = WodSequencer(_wod(blocks), t_start=0.0, labels_fa=LABELS)
    s = seq.summary()
    got_t = [(x["rep_start"], x["rep_end"]) for x in s["rep_timeline"]
             if x["movement"] == t]
    got_b = [(x["rep_start"], x["rep_end"]) for x in s["rep_timeline"]
             if x["movement"] == b]
    assert got_t == [(1, 18), (37, 51), (67, 78), (91, 99), (109, 114), (121, 123)]
    assert got_b == [(19, 36), (52, 66), (79, 90), (100, 108), (115, 120), (124, 126)]
    assert s["total_prescribed"] == 126
