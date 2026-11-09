"""v2.4 engine: whole-video evidence -> global alignment -> per-rep judging.

1. offline evidence detectors find every plausible attempt (no counter);
2. a single dynamic programme aligns them to the 1..N ladder (core.aligner);
3. each aligned attempt is JUDGED by replaying the proven movement FSM on a
   narrow window around the anchor, with a bar position estimated LOCALLY
   from where the athlete actually jumped in that block (the bar moves
   between blocks — a single global anchor went stale by up to 0.9 H);
4. the sequencer is filled with exact slot positions.
"""
from __future__ import annotations

import copy
import statistics
from typing import Optional

from core.aligner import align
from core.offline import (build_series, find_burpee_candidates,
                          find_thruster_candidates)
from core.sequence import WodSequencer
from core.types import NO_REP, REP, Attempt, PoseFrame, SceneModel
from movements.bar_facing_burpee import BarFacingBurpeeFSM
from movements.base import FrameContext
from movements.thruster import ThrusterFSM


def _replay(fsm, frames, lo_t: float, hi_t: float, scene: SceneModel):
    for i, (t, pf) in enumerate(frames):
        if t < lo_t:
            continue
        if t > hi_t:
            break
        fsm.process(FrameContext(t=t, frame_index=pf.frame_index or i, pose=pf, scene=scene))
    fsm.force_close(hi_t)
    return fsm.collect()


def _pick(attempts: list[Attempt], anchor: float, tol: float = 3.0) -> Optional[Attempt]:
    best, bd = None, tol
    for a in attempts:
        mid = (a.t_start + a.t_end) / 2.0
        d = min(abs(mid - anchor), abs(a.t_end - anchor), abs(a.t_start - anchor))
        if d < bd:
            best, bd = a, d
    return best


def _local_bar(cands: list[dict], k: int, scene: SceneModel) -> SceneModel:
    """Bar x for burpee candidate k = median jump midpoint of its neighbours
    in the same block (|dt| < 25 s) — the bar the athlete really crossed."""
    xs = [c["x_mid"] for c in cands
          if c["type"] == "bar_facing_burpee" and c.get("x_mid") is not None
          and abs(c["t"] - cands[k]["t"]) < 25.0 and c["s"] >= 0.7]
    sc = copy.copy(scene)
    if len(xs) >= 2:
        bx = float(statistics.median(xs))
        sc.bar_x = bx
        gy = scene.ground_y_at(bx)
        sc.bar_y = gy if gy is not None else scene.bar_y
        sc.bar_confidence = 1.0
    return sc


def run_aligned(frames: list[tuple[float, PoseFrame]], scene: SceneModel,
                sequencer: WodSequencer, t_start: float, cap_abs: Optional[float],
                fps: float) -> dict:
    if not frames:
        sequencer.load_aligned({})
        return {"candidates": 0}
    S = build_series(frames, scene, fps)
    bcands, ambiguous = find_burpee_candidates(S)
    tcands = find_thruster_candidates(S)
    allc = sorted(bcands + tcands, key=lambda c: c["t"])
    post_cap = [c for c in allc if cap_abs is not None and c["t"] > cap_abs]
    cands = [c for c in allc if c not in post_cap and c["t"] >= t_start - 0.5]
    slot_types = [ph.movement for ph in sequencer.phases for _ in range(ph.reps)]
    res = align(cands, slot_types, t_start=t_start)

    slot_attempts: dict[int, Attempt] = {}
    for ci, sl in res.slot_of.items():
        c = cands[ci]
        if c["type"] == "thruster":
            fsm, sc = ThrusterFSM(), scene
        else:
            fsm, sc = BarFacingBurpeeFSM(), _local_bar(cands, ci, scene)
        outs = _replay(fsm, frames, c["t0"], c["t1"], sc)
        a = _pick(outs, c["t"])
        if a is None:       # seen, but not judgeable -> credit + flag (never silently dropped)
            a = Attempt(movement=c["type"], t_start=c["t0"] + 1.5, t_end=c["t"] + 1.0,
                        frame_start=0, frame_end=0, outcome=REP,
                        details={"unjudged": True, "evidence": c["kind"]},
                        review_flags=["UNJUDGED_REVIEW"], confidence=0.35, borderline=True)
        a.details = dict(a.details or {})
        a.details["evidence"] = c["kind"]
        a.details["evidence_strength"] = round(c["s"], 2)
        slot_attempts[sl] = a

    sequencer.load_aligned(slot_attempts, post_cap=len(post_cap),
                           noise=len(res.dropped), t_end_video=frames[-1][0])
    for amb in ambiguous[:25]:
        sequencer._flag("SEQ_AMBIGUOUS_EVENT", amb["t"], {"why": amb["why"]})
    return {"candidates": len(cands), "matched": len(slot_attempts),
            "dropped": len(res.dropped), "post_cap": len(post_cap),
            "ambiguous": len(ambiguous),
            # for the judge: events the engine SAW but did not count, with time
            "dropped_events": [{"t": round(cands[i]["t"], 1), "type": cands[i]["type"],
                                "kind": cands[i]["kind"], "strength": round(cands[i]["s"], 2)}
                               for i in res.dropped][:60],
            "ambiguous_events": [{"t": round(a["t"], 1), "why": a["why"]} for a in ambiguous][:60]}
