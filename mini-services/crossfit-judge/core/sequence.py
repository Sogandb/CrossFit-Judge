"""
WOD orchestrator — the Runtime Interpreter of the agreed 3-layer design.

Consumes movement attempts and attributes them to the expected block
sequence with TRANSITION guards and desynchronisation recovery (fixes the
v1 fragility where one missed rep desynchronised everything):

  * Reps are credited against the CURRENT block only.
  * A movement switch is confirmed after `transition_confirm_reps` credits
    of the new movement (or 1 credit + inactivity) — then the sequencer
    jumps forward to the next block of that movement and flags any skipped
    block as SEQ_BLOCK_INCOMPLETE (review).
  * Excess reps beyond a block's prescription do not score (SEQ_EXCESS_REPS).
  * Attempts ending after t_start + time_cap are logged but NOT scored.
  * Workout completion: all blocks filled → finished, finish time = last
    scored rep end − t_start.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from config.settings import SEQ
from core.types import NO_REP, REP, Attempt
from movements.reasons import reason_category


@dataclass
class ScoredEvent:
    attempt: Attempt
    block_idx: Optional[int]
    rep_no: Optional[int]        # within-block credited rep number
    scored: bool                 # counted toward the score
    post_cap: bool = False
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "movement": self.attempt.movement,
            "t_start": round(self.attempt.t_start, 2),
            "t_end": round(self.attempt.t_end, 2),
            "outcome": self.attempt.outcome,
            "reason_code": self.attempt.reason_code,
            "reason_fa": _reason_fa(self.attempt.reason_code),
            "reason_en": _reason_en(self.attempt.reason_code),
            "category": _category(self.attempt.reason_code),
            "block_idx": self.block_idx,
            "rep_no": self.rep_no,
            "scored": self.scored,
            "post_cap": self.post_cap,
            "details": self.attempt.details,
            "review_flags": self.attempt.review_flags,
            "notes": self.notes,
        }


def _reason_fa(code):  # local import bouncer
    from movements.reasons import reason_fa
    return reason_fa(code) if code else None


def _reason_en(code):
    from movements.reasons import reason_en
    return reason_en(code) if code else None


def _category(code):
    from movements.reasons import reason_category
    return reason_category(code) if code else None


@dataclass
class BlockState:
    movement: str
    reps: int
    credited: int = 0
    complete: bool = False
    excess_flagged: bool = False

    def to_dict(self, idx: int, label_fa: str) -> dict:
        return {
            "idx": idx,
            "movement": self.movement,
            "movement_fa": label_fa,
            "reps": self.reps,
            "credited": self.credited,
            "complete": self.complete,
            "status_fa": ("کامل" if self.complete else
                          ("ناقص" if self.credited > 0 else "شروع نشده")),
        }


class WodSequencer:
    def __init__(self, wod: dict, t_start: float, labels_fa: dict[str, str]):
        self.wod = wod
        self.t_start = t_start
        self.cap = float(wod.get("time_cap_sec") or 0)
        self.labels_fa = labels_fa
        self.blocks = [BlockState(movement=b["movement"], reps=int(b["reps"]))
                       for b in wod["blocks"]]
        self.block_idx = 0
        self.events: list[ScoredEvent] = []
        self.flags: list[dict] = []
        self.finished = False
        self.finish_time: Optional[float] = None
        self.last_credit_t: dict[str, float] = {}
        self.pending: dict[str, list[Attempt]] = {}
        self.last_activity_t = t_start

    # ------------------------------------------------------------------ #
    @property
    def cap_abs(self) -> float:
        return self.t_start + self.cap if self.cap else float("inf")

    def _flag(self, code: str, t: float, extra: Optional[dict] = None) -> None:
        self.flags.append({"t": round(t, 2), "code": code,
                           "reason_fa": _reason_fa(code), **(extra or {})})

    # ------------------------------------------------------------------ #
    def feed(self, attempts: list[Attempt], t_now: float) -> None:
        for a in attempts:
            self.last_activity_t = max(self.last_activity_t, a.t_end)
            if a.outcome == REP:
                self.last_credit_t[a.movement] = a.t_end
            self._attribute(a, t_now)

    def _next_block_of(self, movement: str, from_idx: int) -> Optional[int]:
        for j in range(from_idx, len(self.blocks)):
            if self.blocks[j].movement == movement:
                return j
        return None

    def _maybe_advance(self, movement: str, t_now: float) -> bool:
        """Transition guard: has the athlete verifiably moved on to this
        movement? Requires confirm credits, or 1 credit + inactivity."""
        cur = self.blocks[self.block_idx]
        if movement == cur.movement:
            return False
        pend = self.pending.get(movement, [])
        credits = sum(1 for p in pend if p.outcome == REP)
        inactivity = t_now - self.last_credit_t.get(cur.movement, -1e9)
        confirmed = credits >= SEQ["transition_confirm_reps"] or \
            (credits >= 1 and inactivity >= SEQ["transition_confirm_sec"])
        if not confirmed:
            return False
        # jump to the next prescribed block of this movement
        j = self._next_block_of(movement, self.block_idx + 1)
        if j is None:
            return False
        # flag every skipped-in-between block as incomplete (review)
        skipped = False
        for k in range(self.block_idx, j):
            if not self.blocks[k].complete:
                skipped = True
                self._flag("SEQ_BLOCK_INCOMPLETE", t_now,
                           {"block": k, "movement": self.blocks[k].movement,
                            "credited": self.blocks[k].credited,
                            "reps": self.blocks[k].reps})
        if skipped:
            self._flag("SEQ_ORDER_DEVIATION", t_now,
                       {"from_block": self.block_idx, "to_block": j})
        self.block_idx = j
        # re-attribute the attempts held while confirming the switch
        held = list(pend)
        self.pending.clear()
        for a in held:
            self._attribute(a, t_now)
        return True

    def _attribute(self, a: Attempt, t_now: float) -> None:
        post_cap = self.cap and a.t_end > self.cap_abs + SEQ["cap_grace_sec"]

        # movement-switch confirmation (only for credited reps)
        if a.outcome == REP and a.movement != self.blocks[self.block_idx].movement:
            self.pending.setdefault(a.movement, []).append(a)
            # if the switch confirms, _maybe_advance re-attributes every held
            # attempt (including this one) to the new block — done either way
            self._maybe_advance(a.movement, t_now)
            return

        block = self.blocks[self.block_idx]

        # ---- post-cap attempts: logged, never scored ---- #
        if post_cap:
            self.events.append(ScoredEvent(
                attempt=a, block_idx=None, rep_no=None, scored=False,
                post_cap=True, notes=["پس از پایان زمان مجاز — شمرده نشد"]))
            return

        # ---- wrong-movement attempt inside the current block ---- #
        if a.movement != block.movement:
            self.events.append(ScoredEvent(
                attempt=a, block_idx=None, rep_no=None, scored=False,
                notes=["خارج از ترتیب واد"]))
            return

        # ---- no-rep of the current movement: logged with reason ---- #
        if a.outcome == NO_REP:
            self.events.append(ScoredEvent(
                attempt=a, block_idx=self.block_idx, rep_no=None, scored=False))
            return

        # ---- credited rep ---- #
        if block.credited < block.reps:
            block.credited += 1
            self.events.append(ScoredEvent(
                attempt=a, block_idx=self.block_idx, rep_no=block.credited,
                scored=True))
            if block.credited >= block.reps:
                block.complete = True
                self._check_finished()
                if not self.finished and self.block_idx + 1 < len(self.blocks):
                    self.block_idx += 1  # natural advance to the next block
                    self.pending.clear()
        else:
            # excess reps beyond prescription — not scored
            if not block.excess_flagged:
                block.excess_flagged = True
                self._flag("SEQ_EXCESS_REPS", a.t_end,
                           {"block": self.block_idx,
                            "movement": block.movement})
            self.events.append(ScoredEvent(
                attempt=a, block_idx=self.block_idx, rep_no=None, scored=False,
                notes=["رپ اضافه — بیش از تعداد تعیین‌شده این رند"]))

    def _check_finished(self) -> None:
        if all(b.complete for b in self.blocks):
            self.finished = True
            scored = [e for e in self.events if e.scored]
            last = max((e.attempt.t_end for e in scored), default=self.t_start)
            self.finish_time = max(0.0, last - self.t_start)

    # ------------------------------------------------------------------ #
    def sync_fsms(self, fsms: list, t_now: float) -> list:
        """Expected-sequence constraint: enable only the movements prescribed
        for the current (and next) block; force-close + collect the ones
        being disabled so cross-movement interference is impossible."""
        expected = {self.blocks[self.block_idx].movement}
        if self.block_idx + 1 < len(self.blocks):
            expected.add(self.blocks[self.block_idx + 1].movement)
        closed = []
        for fsm in fsms:
            want = fsm.movement_id in expected
            if want and not fsm.enabled:
                fsm.enabled = True
            elif not want and fsm.enabled:
                fsm.enabled = False
                fsm.force_close(t_now)
                closed.extend(fsm.collect())
        return closed

    def summary(self) -> dict:
        per_movement: dict[str, dict] = {}
        for b in self.blocks:
            m = per_movement.setdefault(b.movement, {"credited": 0, "no_reps": 0,
                                                     "prescribed": 0, "complete_blocks": 0})
            m["credited"] += b.credited
            m["prescribed"] += b.reps
            m["complete_blocks"] += 1 if b.complete else 0
        for e in self.events:
            if e.attempt.outcome == NO_REP and not e.post_cap:
                m = per_movement.setdefault(e.attempt.movement,
                                            {"credited": 0, "no_reps": 0,
                                             "prescribed": 0, "complete_blocks": 0})
                m["no_reps"] += 1
        return {
            "finished": self.finished,
            "finish_time_sec": round(self.finish_time, 2) if self.finished else None,
            "capped": (not self.finished) and self.cap > 0,
            "total_credited": sum(b.credited for b in self.blocks),
            "total_prescribed": sum(b.reps for b in self.blocks),
            "per_movement": per_movement,
            "blocks": [b.to_dict(i, self.labels_fa.get(b.movement, b.movement))
                       for i, b in enumerate(self.blocks)],
        }
