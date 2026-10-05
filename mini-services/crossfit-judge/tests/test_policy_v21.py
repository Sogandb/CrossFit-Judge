"""V2.1 judging-policy tests — benefit-of-the-doubt bands, confidence
model, pattern gates and the self-healing sequencer."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.sequence import WodSequencer
from core.types import REP, Attempt
from judging.policy import (BORDERLINE, FAIL, OK, band, band_bool,
                            norep_confidence, rep_confidence)


# --------------------------------------------------------------------- #
# Band policy
# --------------------------------------------------------------------- #
def test_band_clear_pass():
    verdict, margin = band(0.05, clear_pass=0.02, bod_pass=-0.015,
                           clear_fail=-0.08, bod_fail=-0.06, vis=0.9)
    assert verdict == OK
    assert margin >= 0.0


def test_band_borderline():
    verdict, _ = band(0.005, clear_pass=0.02, bod_pass=-0.015,
                      clear_fail=-0.08, bod_fail=-0.06, vis=0.9)
    assert verdict == BORDERLINE


def test_band_clear_fail():
    verdict, severity = band(-0.09, clear_pass=0.02, bod_pass=-0.015,
                             clear_fail=-0.08, bod_fail=-0.06, vis=0.9)
    assert verdict == FAIL
    assert severity > 0.5


def test_band_low_visibility_never_auto_penalises():
    """A violation inside the soft zone with UNRELIABLE measurement →
    benefit of the doubt (borderline), never an auto no-rep."""
    verdict, _ = band(-0.05, clear_pass=0.02, bod_pass=-0.015,
                      clear_fail=-0.08, bod_fail=-0.06, vis=0.30)
    assert verdict == BORDERLINE


def test_band_bool_none_is_borderline():
    verdict, _ = band_bool(None, vis=0.9)
    assert verdict == BORDERLINE


# --------------------------------------------------------------------- #
# Confidence model
# --------------------------------------------------------------------- #
def test_rep_confidence_ranges_and_caps():
    strong = rep_confidence([1.0, 1.0], vis=0.9, borderline=False)
    assert 0.85 <= strong <= 0.97
    weak = rep_confidence([0.0], vis=0.4, borderline=False)
    assert weak < strong
    capped = rep_confidence([1.0, 1.0], vis=0.9, borderline=True)
    assert capped <= 0.82, "borderline decisions must be confidence-capped"


def test_norep_confidence_scales_with_severity():
    weak = norep_confidence(0.1, vis=0.9)
    strong = norep_confidence(0.9, vis=0.9)
    assert strong > weak
    assert 0.30 <= weak and strong <= 0.97


# --------------------------------------------------------------------- #
# Sequencer: follows the athlete
# --------------------------------------------------------------------- #
def _wod():
    return {"blocks": [
        {"movement": "thruster", "reps": 3},
        {"movement": "bar_facing_burpee", "reps": 3},
        {"movement": "thruster", "reps": 2},
        {"movement": "bar_facing_burpee", "reps": 2},
    ], "time_cap_sec": 600}


def _att(movement, outcome, t, dur=1.0):
    return Attempt(movement=movement, t_start=t, t_end=t + dur,
                   frame_start=0, frame_end=30, outcome=outcome,
                   reason_code=None if outcome == REP else "THR_DEPTH",
                   confidence=0.9)


def test_sequencer_realigns_backward_when_drifted_ahead():
    """The sequencer drifted to the LAST block but the athlete is still
    working through an earlier movement — reps must find their home."""
    seq = WodSequencer(_wod(), t_start=0.0, labels_fa={})
    # simulate: block 0 done, then the sequencer jumps ahead (drift)
    for i in range(3):
        seq.feed([_att("thruster", REP, 1.0 + i)], 1.0 + i)   # block 0 full
    for i in range(3):
        seq.feed([_att("bar_facing_burpee", REP, 10.0 + i)], 10.0 + i)
    # burpee blocks 1 and 3 now complete; natural advance to block 2 (T2)
    assert seq.block_idx == 2
    seq.block_idx = 3  # force a drift-ahead state (as if detection slipped)
    # athlete keeps doing thrusters (they were block 2's reps all along)
    seq.feed([_att("thruster", REP, 30.0)], 30.0)
    seq.feed([_att("thruster", REP, 31.0)], 31.0)
    s = seq.summary()
    assert s["per_movement"]["thruster"]["credited"] == 5, s
    assert any(f["code"] == "SEQ_REALIGN_BACKWARD" for f in seq.flags)


def test_sequencer_same_movement_flow():
    """More reps of the current movement than the block prescribes flow
    into the next block of that SAME movement (credited, flagged for
    order review — via the pending-switch or the flow path)."""
    seq = WodSequencer(_wod(), t_start=0.0, labels_fa={})
    for i in range(5):   # block 0 prescribes 3 — two extra flow forward
        seq.feed([_att("thruster", REP, 1.0 + i)], 1.0 + i)
    s = seq.summary()
    assert s["per_movement"]["thruster"]["credited"] == 5, s
    assert any(f["code"] in ("SEQ_SAME_MOVE_FLOW", "SEQ_ORDER_DEVIATION",
                             "SEQ_BLOCK_INCOMPLETE")
               for f in seq.flags), seq.flags


def test_rep_timeline_maps_overall_rep_numbers():
    seq = WodSequencer(_wod(), t_start=0.0, labels_fa={})
    tl = seq.rep_timeline()
    assert tl[0]["rep_start"] == 1 and tl[0]["rep_end"] == 3
    assert tl[1]["rep_start"] == 4 and tl[1]["rep_end"] == 6
    assert tl[2]["rep_start"] == 7 and tl[2]["rep_end"] == 8
    assert tl[3]["rep_start"] == 9 and tl[3]["rep_end"] == 10


def test_summary_reports_confidence_and_borderline():
    seq = WodSequencer(_wod(), t_start=0.0, labels_fa={})
    a = _att("thruster", REP, 1.0)
    a.confidence = 0.7
    a.borderline = True
    seq.feed([a], 1.0)
    s = seq.summary()
    assert s["analysis_confidence"] == 0.7
    assert s["borderline_reps"] == 1
