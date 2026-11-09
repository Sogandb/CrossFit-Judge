"""Global alignment of detected rep EVIDENCE to the prescribed ladder.

WHY (measured on real videos, v2.3): an online counter that advances on a
clock ("nothing seen for N s -> skip") ran ahead of a tired athlete, declared
the WOD finished at 7:05 of a 10:00 attempt and ignored the rest. Here the
whole video is analysed first, then the ordered candidate events are aligned
to the known 1..126 schedule with ONE dynamic programme:

    * a candidate may be MATCHED to the next slots in order (types must agree),
    * a candidate may be DROPPED (rest, bar set-down, bending, noise),
    * a slot may be SKIPPED ("not detected") — but only if the elapsed time
      could physically contain the skipped reps.

This is the ordered-transcript alignment idea used for weakly supervised
action segmentation (Richard et al., "NeuralNetwork-Viterbi", CVPR 2018; the
outlier-dropping DTW of Dvornik et al., "Drop-DTW", NeurIPS 2021) specialised
to a schedule that is known exactly. One missed rep can no longer shift the
rest of the workout, and a spurious event can no longer burn a slot.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

INF = float("inf")

# conservative LOWER bounds (s) for one rep of each movement
MIN_DT = {"thruster": 1.0, "bar_facing_burpee": 1.3}
SWITCH_EXTRA = 0.8          # extra seconds needed to switch movement (bar down, turn, ...)
SKIP_COST = 1.0             # one slot declared "not detected"
DROP_BASE, DROP_K = 0.3, 1.7  # dropping evidence of strength s costs base + k*s
MATCH_K = 0.8               # matching weak evidence costs k*(1-s)
PACE_K = 6.0                # penalty for fitting reps into a gap that is too short
PACE_MIN = 0.8              # a rep needs >= 80 % of the athlete's own typical pace


@dataclass
class AlignResult:
    slot_of: dict[int, int]      # candidate index -> slot index
    dropped: list[int]           # candidate indices not matched
    cost: float


def align(cands: list[dict], slot_types: list[str], t_start: float = 0.0,
          max_skip: int = 48, max_back: int = 8) -> AlignResult:
    """cands: [{type, t, s}] sorted by t. slot_types: movement id per slot."""
    N, M = len(cands), len(slot_types)
    if N == 0 or M == 0:
        return AlignResult({}, list(range(N)), 0.0)
    d = np.array([MIN_DT.get(s, 1.2) for s in slot_types], float)
    sw = np.zeros(M)
    for k in range(1, M):
        if slot_types[k] != slot_types[k - 1]:
            sw[k] = SWITCH_EXTRA
    cum = np.cumsum(d + sw)                       # time to complete slots 0..k
    # athlete's OWN typical pace per movement (median spacing of same-type
    # neighbours, rests excluded) — a skipped slot is only believable where the
    # gap actually holds that many reps at this pace.
    tau_by = {}
    for ty in set(slot_types):
        g = [cands[k + 1]["t"] - cands[k]["t"] for k in range(N - 1)
             if cands[k]["type"] == ty and cands[k + 1]["type"] == ty
             and cands[k]["s"] >= 0.7 and cands[k + 1]["s"] >= 0.7]
        g = [x for x in g if x < 12.0]
        tau_by[ty] = float(np.median(g)) if len(g) >= 3 else 3.0
    tau = np.array([tau_by[s] for s in slot_types], float)
    cum_tau = np.cumsum(tau)
    cum_sw = np.cumsum(sw)
    drop = np.array([DROP_BASE + DROP_K * c["s"] for c in cands])
    pref = np.concatenate([[0.0], np.cumsum(drop)])
    match = np.array([MATCH_K * (1.0 - c["s"]) for c in cands])
    ts = np.array([c["t"] for c in cands])

    best = np.full((N, M), INF)
    back = np.full((N, M, 2), -2, dtype=np.int32)     # (-1,-1) = chain start
    for i in range(N):
        for j in range(M):
            if slot_types[j] != cands[i]["type"]:
                continue
            # chain start: every earlier candidate dropped, slots < j skipped
            c0 = pref[i] + SKIP_COST * j + match[i]
            if j > 0 and (ts[i] - t_start) < cum[j - 1]:
                c0 = INF
            bc, bp = c0, (-1, -1)
            qlo = max(0, j - max_skip - 1)
            qs = np.arange(qlo, j)
            for p in range(max(0, i - max_back), i):
                prev = best[p, qlo:j]
                if not np.isfinite(prev).any():
                    continue
                T = ts[i] - ts[p]
                reqs = cum[j] - cum[qs]
                t_eff = np.maximum(T - (cum_sw[j] - cum_sw[qs]), 0.05)
                ratio = t_eff / (cum_tau[j] - cum_tau[qs])
                pace = PACE_K * np.maximum(0.0, PACE_MIN - ratio)
                cost = (prev + (pref[i] - pref[p + 1]) + SKIP_COST * (j - qs - 1)
                        + match[i] + pace)
                cost = np.where(T >= reqs, cost, INF)
                k = int(np.argmin(cost))
                if cost[k] < bc:
                    bc, bp = float(cost[k]), (p, qlo + k)
            best[i, j] = bc
            back[i, j] = bp

    tail = pref[N] - pref[np.arange(N) + 1]           # drop everything after i
    total = best + tail[:, None]
    idx = np.unravel_index(int(np.argmin(total)), total.shape)
    if not np.isfinite(total[idx]) or total[idx] >= pref[N]:
        return AlignResult({}, list(range(N)), float(pref[N]))
    slot_of: dict[int, int] = {}
    i, j = int(idx[0]), int(idx[1])
    while i >= 0:
        slot_of[i] = j
        p, q = back[i, j]
        if p < 0:
            break
        i, j = int(p), int(q)
    dropped = [k for k in range(N) if k not in slot_of]
    return AlignResult(slot_of, dropped, float(total[idx]))
