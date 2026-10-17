"""Bar-facing burpee FSM unit tests — every Wodx standard rule gets a scenario."""
from __future__ import annotations

from conftest import BAR_X, GY, H, X0, make_frames, run_fsm
from core.mock_pose import gen_bfb_rep
from core.types import NO_REP, REP
from movements.bar_facing_burpee import BarFacingBurpeeFSM


def _collect(frames, scene):
    fsm = BarFacingBurpeeFSM()
    return run_fsm(fsm, frames, scene)


def _start_x() -> float:
    return BAR_X - 0.55 * H  # left side of the bar


def test_good_two_foot_burpee_credited(scene):
    frames = make_frames(lambda out: gen_bfb_rep(
        out, 0.0, _start_x(), GY, H, 0, BAR_X, landing_mode="two"))
    attempts = _collect(frames, scene)
    assert len(attempts) == 1, [(a.outcome, a.reason_code) for a in attempts]
    a = attempts[0]
    assert a.outcome == REP, (a.outcome, a.reason_code, a.details)
    assert a.review_flags == []


def test_legal_one_foot_takeoff_credited(scene):
    """The تبصره: one-foot takeoff with the trailing foot following mid-air,
    simultaneous two-foot landing — LEGAL."""
    frames = make_frames(lambda out: gen_bfb_rep(
        out, 0.0, _start_x(), GY, H, 0, BAR_X, landing_mode="stagger_takeoff"))
    attempts = _collect(frames, scene)
    assert len(attempts) == 1
    a = attempts[0]
    assert a.outcome == REP, (a.outcome, a.reason_code, a.details)


def test_chest_not_touching_no_rep(scene):
    """Chest clearly off the floor (0.36H) → clear fault."""
    frames = make_frames(lambda out: gen_bfb_rep(
        out, 0.0, _start_x(), GY, H, 0, BAR_X, chest_touch=0.36))
    attempts = _collect(frames, scene)
    assert len(attempts) == 1
    a = attempts[0]
    assert a.outcome == NO_REP
    assert a.reason_code == "BFB_CHEST"


def test_chest_borderline_credited_with_review(scene):
    """Chest 0.25H above the floor — inside the uncertainty band →
    credited to the athlete (benefit of the doubt) with a review flag."""
    frames = make_frames(lambda out: gen_bfb_rep(
        out, 0.0, _start_x(), GY, H, 0, BAR_X, chest_touch=0.25))
    attempts = _collect(frames, scene)
    assert len(attempts) == 1
    a = attempts[0]
    assert a.outcome == REP, (a.outcome, a.reason_code, a.details)
    assert a.borderline is True
    assert "BFB_CHEST_REVIEW" in a.review_flags
    assert a.confidence <= 0.82


def test_parallel_to_bar_no_rep(scene):
    """Body clearly parallel to the bar (sustained ~72° measured tilt) → fault.
    NOTE: the mock's facing parameter maps to a steeper MEASURED shoulder
    line (facing=40 → ~72° measured)."""
    frames = make_frames(lambda out: gen_bfb_rep(
        out, 0.0, _start_x(), GY, H, 0, BAR_X, facing=50.0))
    attempts = _collect(frames, scene)
    assert len(attempts) == 1
    a = attempts[0]
    assert a.outcome == NO_REP
    assert a.reason_code == "BFB_NOT_FACING"


def test_facing_borderline_credited_with_review(scene):
    """Shoulder tilt ~60° measured — camera-geometry band → credited + review
    flag (a correctly-facing athlete shows a steep shoulder line in side
    view)."""
    frames = make_frames(lambda out: gen_bfb_rep(
        out, 0.0, _start_x(), GY, H, 0, BAR_X, facing=22.0))
    attempts = _collect(frames, scene)
    assert len(attempts) == 1
    a = attempts[0]
    assert a.outcome == REP, (a.outcome, a.reason_code, a.details)
    assert "BFB_FACING_REVIEW" in a.review_flags


def test_staggered_landing_no_rep(scene):
    """Simultaneous takeoff but staggered landing → one-foot landing fault."""
    frames = make_frames(lambda out: gen_bfb_rep(
        out, 0.0, _start_x(), GY, H, 0, BAR_X, landing_mode="stagger_landing"))
    attempts = _collect(frames, scene)
    assert len(attempts) == 1
    a = attempts[0]
    assert a.outcome == NO_REP
    assert a.reason_code == "BFB_ONE_FOOT_LANDING", (a.reason_code, a.details)


def test_trailing_foot_grounded_no_rep(scene):
    """Lead foot crosses & lands while the trailing foot stays grounded on the
    start side → the exact fault described in the Wodx تبصره."""
    frames = make_frames(lambda out: gen_bfb_rep(
        out, 0.0, _start_x(), GY, H, 0, BAR_X, landing_mode="trailing"))
    attempts = _collect(frames, scene)
    assert len(attempts) == 1
    a = attempts[0]
    assert a.outcome == NO_REP
    assert a.reason_code == "BFB_TRAILING_FOOT", (a.reason_code, a.details)


def test_incomplete_crossing_no_rep(scene):
    frames = make_frames(lambda out: gen_bfb_rep(
        out, 0.0, _start_x(), GY, H, 0, BAR_X, cross=False))
    attempts = _collect(frames, scene)
    assert len(attempts) == 1
    a = attempts[0]
    assert a.outcome == NO_REP
    assert a.reason_code == "BFB_INCOMPLETE_CROSS", (a.reason_code, a.details)


def test_consecutive_burpees_alternating_sides(scene):
    """Two reps back-to-back: the athlete ends on the far side and starts the
    next rep facing back — both credited, no phantoms."""
    def two(out):
        t = gen_bfb_rep(out, 0.0, _start_x(), GY, H, 0, BAR_X, landing_mode="two")
        # next rep starts from the FAR side (bar + 0.55H)
        gen_bfb_rep(out, t, BAR_X + 0.55 * H, GY, H, len(out), BAR_X,
                    landing_mode="two")
    frames = make_frames(two)
    attempts = _collect(frames, scene)
    credited = [a for a in attempts if a.outcome == REP]
    assert len(credited) == 2, [(a.outcome, a.reason_code) for a in attempts]
    assert len(attempts) == 2
