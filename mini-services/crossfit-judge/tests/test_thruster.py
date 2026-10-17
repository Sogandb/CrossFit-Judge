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


def test_shallow_dip_borderline_credited_with_review(scene):
    """A 0.005H dip + full press: the dip is inside the depth uncertainty
    band — credited with a THR_DEPTH_REVIEW flag (benefit of the doubt),
    never a silent discard and never an auto no-rep."""
    frames = make_frames(lambda out: gen_thruster_rep(out, 0.0, X0, GY, H, 0,
                                                      depth_h=0.005))
    attempts = _collect(frames, scene)
    assert len(attempts) == 1, [(a.outcome, a.reason_code) for a in attempts]
    a = attempts[0]
    assert a.outcome == REP, (a.outcome, a.reason_code, a.details)
    assert "THR_DEPTH_REVIEW" in a.review_flags
    assert a.borderline is True


def test_high_pull_without_squat_no_rep(scene):
    """Hips stay above the knees (−0.05H), bar still pressed overhead →
    a real attempted thruster with NO squat depth → clear no-rep."""
    frames = make_frames(lambda out: gen_thruster_rep(out, 0.0, X0, GY, H, 0,
                                                      depth_h=-0.05))
    attempts = _collect(frames, scene)
    assert len(attempts) >= 1
    assert any(a.outcome == NO_REP and a.reason_code == "THR_DEPTH"
               for a in attempts), [(a.outcome, a.reason_code) for a in attempts]


def test_borderline_depth_credited_with_review(scene):
    """Depth just short of parallel (0.010H) — inside the uncertainty band →
    credited to the athlete with a review flag and capped confidence."""
    frames = make_frames(lambda out: gen_thruster_rep(out, 0.0, X0, GY, H, 0,
                                                      depth_h=0.010))
    attempts = _collect(frames, scene)
    assert len(attempts) == 1
    a = attempts[0]
    assert a.outcome == REP, (a.outcome, a.reason_code, a.details)
    assert a.borderline is True
    assert "THR_DEPTH_REVIEW" in a.review_flags
    assert a.confidence <= 0.82


def test_no_lockout_borderline_credited_with_review(scene):
    """Elbow 140° at lockout — inside the 2D-measurement uncertainty band →
    credited with a review flag (benefit of the doubt)."""
    frames = make_frames(lambda out: gen_thruster_rep(out, 0.0, X0, GY, H, 0,
                                                      lockout=False))
    attempts = _collect(frames, scene)
    assert len(attempts) == 1
    a = attempts[0]
    assert a.outcome == REP, (a.outcome, a.reason_code, a.details)
    assert "THR_LOCKOUT_REVIEW" in a.review_flags


def test_clearly_bent_lockout_no_rep(scene):
    """Elbow 95° (below the eased 128° clear line) → a clear press-out failure."""
    frames = make_frames(lambda out: gen_thruster_rep(out, 0.0, X0, GY, H, 0,
                                                      lockout=95.0))
    attempts = _collect(frames, scene)
    assert len(attempts) == 1
    a = attempts[0]
    assert a.outcome == NO_REP, (a.outcome, a.reason_code, a.details)
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
                                                      walk_h=0.36))
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


def test_v21_eased_walk_and_elbow_are_credited(scene):
    """v2.1 leniency (EASE=.5): 0.20H drift and a 135 deg elbow used to be
    no-reps; they are now credited (with review flags), not penalised."""
    f1 = make_frames(lambda out: gen_thruster_rep(out, 0.0, X0, GY, H, 0, walk_h=0.20))
    a = _collect(f1, scene)[0]
    assert a.outcome == REP and "THR_WALKING_REVIEW" in a.review_flags
    f2 = make_frames(lambda out: gen_thruster_rep(out, 0.0, X0, GY, H, 0, lockout=135.0))
    a = _collect(f2, scene)[0]
    assert a.outcome == REP and a.borderline


def test_v21_ease_zero_restores_rulebook_lines():
    import importlib, os, config.settings as st
    os.environ["JUDGE_EASE"] = "0"
    try:
        importlib.reload(st)
        assert st.THR["lock_elbow_clear_deg"] == 158.0 and st.THR["walk_drift_max_h"] == 0.15
    finally:
        del os.environ["JUDGE_EASE"]
        importlib.reload(st)
