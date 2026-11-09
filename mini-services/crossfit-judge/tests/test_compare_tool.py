import sys
sys.path.insert(0, "tools")
from compare_human import compare


def test_compare_counts_error_modes():
    res = {"summary": {"ladder": [
        {"rep_no": 1, "verdict": "rep"}, {"rep_no": 2, "verdict": "no_rep", "t_start": 5.0, "reason_code": "THR_DEPTH"},
        {"rep_no": 3, "verdict": "not_detected"}, {"rep_no": 4, "verdict": "rep"}]}}
    out = compare(res, {1: "rep", 2: "rep", 3: "rep", 4: "no_rep"})
    assert out["false_no_reps"] == 1 and out["missed"] == 1 and out["missed_no_reps"] == 1
    assert out["agreement"] == 0.25
