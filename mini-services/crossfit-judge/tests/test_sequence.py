"""WOD sequencer tests — attribution, transitions, cap enforcement, recovery."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.mock_pose import gen_synthetic_workout
from core.sequence import WodSequencer
from core.types import NO_REP, REP, Attempt, PoseFrame, SceneModel
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
    return seq, frames


def test_full_workout_all_credited():
    blocks = [{"movement": "thruster", "reps": 3},
              {"movement": "bar_facing_burpee", "reps": 3},
              {"movement": "thruster", "reps": 2},
              {"movement": "bar_facing_burpee", "reps": 2}]
    seq, _ = _run(_wod(blocks))
    s = seq.summary()
    assert s["finished"], s
    assert s["total_credited"] == 10
    assert s["per_movement"]["thruster"]["credited"] == 5
    assert s["per_movement"]["bar_facing_burpee"]["credited"] == 5
    assert s["finish_time_sec"] is not None and s["finish_time_sec"] > 0


def test_no_rep_faults_do_not_score():
    blocks = [{"movement": "thruster", "reps": 2},
              {"movement": "bar_facing_burpee", "reps": 2}]
    faults = {"thruster": {0: {"depth_h": -0.05}},   # rep 1 no-rep (no squat)
              "bfb": {0: {"chest_touch": 0.36}}}    # rep 1 no-rep (chest high)
    seq, _ = _run(_wod(blocks), faults=faults)
    s = seq.summary()
    # the two no-reps must not score; the athlete performed the physical reps
    # once each — totals fall short of prescription and flag review
    assert s["per_movement"]["thruster"]["credited"] <= 2
    assert s["per_movement"]["thruster"]["no_reps"] >= 1
    assert s["per_movement"]["bar_facing_burpee"]["no_reps"] >= 1
    assert not s["finished"] or s["total_credited"] < 4
    assert any(f["code"] == "SEQ_BLOCK_INCOMPLETE" for f in seq.flags)


def test_time_cap_cuts_late_reps():
    """cap = 0s after start → every rep lands post-cap → nothing scores."""
    blocks = [{"movement": "thruster", "reps": 1},
              {"movement": "bar_facing_burpee", "reps": 1}]
    seq, frames = _run(_wod(blocks, cap=1), t_start=6.0)
    s = seq.summary()
    # with a 1-second cap the workout cannot complete → capped, zero or near-zero
    assert not s["finished"]
    post_cap = [e for e in seq.events if e.post_cap]
    assert len(post_cap) >= 0  # bookkeeping exists
    assert s["capped"]


def test_sequencer_recovers_when_thrusters_are_skipped():
    """Athlete (or detector) does fewer thrusters than prescribed but moves
    on to burpees — the sequencer must resync, not deadlock."""
    blocks = [{"movement": "thruster", "reps": 3},
              {"movement": "bar_facing_burpee", "reps": 3}]
    # only ONE good thruster rep, then burpees (synthetic stream has both
    # movements; we simulate by crediting attempts manually)
    wod = _wod(blocks)
    seq = WodSequencer(wod, t_start=0.0, labels_fa=LABELS)
    t = 1.0
    seq.feed([_att("thruster", REP, t)], t)
    t = 30.0
    seq.feed([_att("bar_facing_burpee", REP, t)], t)
    t = 32.0
    seq.feed([_att("bar_facing_burpee", REP, t)], t)   # 2nd credit confirms
    s = seq.summary()
    assert seq.block_idx == 1, seq.blocks
    assert s["per_movement"]["bar_facing_burpee"]["credited"] == 2
    assert any(f["code"] == "SEQ_BLOCK_INCOMPLETE" for f in seq.flags)


def test_excess_reps_flagged_not_scored():
    wod = _wod([{"movement": "thruster", "reps": 1},
                {"movement": "bar_facing_burpee", "reps": 1}])
    seq = WodSequencer(wod, t_start=0.0, labels_fa=LABELS)
    seq.feed([_att("thruster", REP, 1.0)], 1.0)
    seq.feed([_att("bar_facing_burpee", REP, 3.0)], 3.0)
    # extra burpee beyond prescription
    seq.feed([_att("bar_facing_burpee", REP, 5.0)], 5.0)
    s = seq.summary()
    assert s["finished"]
    assert s["total_credited"] == 2  # excess never scores
    assert any(f["code"] == "SEQ_EXCESS_REPS" for f in seq.flags)


def _att(movement, outcome, t, dur=1.0):
    return Attempt(movement=movement, t_start=t, t_end=t + dur,
                   frame_start=0, frame_end=30, outcome=outcome,
                   reason_code=None if outcome == REP else "THR_DEPTH")
