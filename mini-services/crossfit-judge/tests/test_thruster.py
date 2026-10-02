"""Thruster FSM unit tests — every Wodx standard rule gets a scenario."""
from __future__ import annotations

from conftest import BAR_X, GY, H, X0, make_frames, run_fsm
from core.mock_pose import gen_thruster_rep
from core.types import NO_REP, REP
from movements.thruster import ThrusterFSM


def _collect(frames, scene):
    fsm = ThrusterFSM()
    return run_fsm(fsm, frames, scene)


def test_good_rack_rep_credited(scene):
    frames = make_frames(lambda out: gen_thruster_rep(out, 0.0, X0, GY, H, 0))
    attempts = _collect(frames, scene)
    assert len(attempts) == 1
    a = attempts[0]
    assert a.outcome == REP, (a.outcome, a.reason_code, a.details)
    assert a.review_flags == []


def test_good_clean_entry_credited(scene):
    frames = make_frames(lambda out: gen_thruster_rep(out, 0.0, X0, GY, H, 0,
                                                      entry="ground"))
    attempts = _collect(frames, scene)
    assert len(attempts) == 1
    assert attempts[0].outcome == REP, (attempts[0].reason_code,
                                        attempts[0].details)
    assert attempts[0].details["entry"] == "ground"


def test_shallow_squat_no_rep(scene):
    frames = make_frames(lambda out: gen_thruster_rep(out, 0.0, X0, GY, H, 0,
                                                      depth_h=0.005))
    attempts = _collect(frames, scene)
    assert len(attempts) == 1
    a = attempts[0]
    assert a.outcome == NO_REP
    assert a.reason_code == "THR_DEPTH"


def test_no_lockout_no_rep(scene):
    frames = make_frames(lambda out: gen_thruster_rep(out, 0.0, X0, GY, H, 0,
                                                      lockout=False))
    attempts = _collect(frames, scene)
    assert len(attempts) == 1
    a = attempts[0]
    assert a.outcome == NO_REP
    assert a.reason_code == "THR_LOCKOUT"


def test_bar_not_overhead_no_rep(scene):
    frames = make_frames(lambda out: gen_thruster_rep(out, 0.0, X0, GY, H, 0,
                                                      overhead=False))
    attempts = _collect(frames, scene)
    assert len(attempts) == 1
    assert attempts[0].outcome == NO_REP
    assert attempts[0].reason_code == "THR_BAR_NOT_OVERHEAD"


def test_jerk_after_pause_not_continuous(scene):
    frames = make_frames(lambda out: gen_thruster_rep(out, 0.0, X0, GY, H, 0,
                                                      jerk=True))
    attempts = _collect(frames, scene)
    # attempt 1: full squat → stand-rack pause → closed as no-rep
    assert any(a.outcome == NO_REP and a.reason_code == "THR_BAR_NOT_OVERHEAD"
               for a in attempts)
    # attempt 2: press-out from standing shortly after → jerk classification
    assert any(a.outcome == NO_REP and a.reason_code == "THR_NOT_CONTINUOUS"
               for a in attempts)
    # and nothing may be credited
    assert not any(a.outcome == REP for a in attempts)


def test_walking_fault_no_rep(scene):
    frames = make_frames(lambda out: gen_thruster_rep(out, 0.0, X0, GY, H, 0,
                                                      walk_h=0.20))
    attempts = _collect(frames, scene)
    assert len(attempts) == 1
    assert attempts[0].outcome == NO_REP
    assert attempts[0].reason_code == "THR_WALKING"


def test_hands_to_legs_review_flag(scene):
    frames = make_frames(lambda out: gen_thruster_rep(out, 0.0, X0, GY, H, 0,
                                                      wrist_to_knees=True))
    attempts = _collect(frames, scene)
    assert len(attempts) == 1
    a = attempts[0]
    assert a.outcome == REP  # review flag, not auto no-rep
    assert "THR_HANDS_TO_LEG" in a.review_flags


def test_consecutive_rack_cycle(scene):
    """Two back-to-back rack reps → both credited, no phantom attempts."""
    def two(out):
        t = gen_thruster_rep(out, 0.0, X0, GY, H, 0)
        gen_thruster_rep(out, t, X0, GY, H, len(out))
    frames = make_frames(two)
    attempts = _collect(frames, scene)
    credited = [a for a in attempts if a.outcome == REP]
    assert len(credited) == 2, [(a.outcome, a.reason_code) for a in attempts]
    assert len(attempts) == 2
