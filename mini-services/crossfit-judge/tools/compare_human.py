"""Compare a result JSON with the HUMAN judge's per-rep record.

Usage:  python tools/compare_human.py result.json human.csv
human.csv  (one line per prescribed rep you checked, header optional):
    rep,verdict            verdict = rep | no_rep | missing
    19,no_rep
    20,rep
Prints agreement, a confusion table and every disagreement with its video
time, so calibration targets the REAL error modes instead of guesses.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter


def load_human(path):
    out = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.reader(f):
            if len(row) < 2 or not row[0].strip().isdigit():
                continue
            out[int(row[0])] = row[1].strip().lower()
    return out


def compare(result: dict, human: dict) -> dict:
    ladder = {r["rep_no"]: r for r in result["summary"]["ladder"]}
    norm = {"rep": "rep", "no_rep": "no_rep", "not_detected": "missing", "not_reached": "missing"}
    conf, diffs = Counter(), []
    for n, h in sorted(human.items()):
        row = ladder.get(n)
        sysv = norm.get(row["verdict"], "missing") if row else "missing"
        conf[(h, sysv)] += 1
        if h != sysv:
            diffs.append({"rep": n, "human": h, "system": sysv,
                          "t": (row or {}).get("t_start"),
                          "reason": (row or {}).get("reason_code")})
    total = sum(conf.values())
    agree = sum(v for (h, s), v in conf.items() if h == s)
    return {"n": total, "agreement": round(agree / total, 3) if total else None,
            "confusion": {f"{h}->{s}": v for (h, s), v in sorted(conf.items())},
            "false_no_reps": conf[("rep", "no_rep")], "missed": conf[("rep", "missing")],
            "missed_no_reps": conf[("no_rep", "rep")], "disagreements": diffs}


if __name__ == "__main__":
    res = json.load(open(sys.argv[1], encoding="utf-8"))
    res = res.get("result", res)
    rep = compare(res, load_human(sys.argv[2]))
    print(json.dumps({k: v for k, v in rep.items() if k != "disagreements"}, indent=2))
    for d in rep["disagreements"]:
        print(f"  rep {d['rep']:>3}: human={d['human']:<8} system={d['system']:<8} t={d['t']} {d['reason'] or ''}")
