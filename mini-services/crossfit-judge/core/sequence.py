"""
WOD orchestrator — the Runtime Interpreter of the agreed 3-layer design.

The WOD is defined as an ORDERED list of blocks (e.g. the Wodx ladder:
18 thruster → 18 bar-facing burpee → 15 thruster → 15 burpee → …). The
sequencer OWNS the "which movement is expected right now?" knowledge:

  * `rep_timeline` maps every overall rep number to its block/movement
    (reps 1-18 → thruster, 19-36 → burpee, 37-51 → thruster, …) so both
    the engine and the UI can state exactly what the athlete should be
    doing at any point in the workout.
  * Reps are credited against the CURRENT block only. A movement switch is
    confirmed once the athlete verifiably starts the next prescribed
    movement (credits, or a sustained stream of its attempts) — then the
    sequencer jumps to the next block OF THAT MOVEMENT, flags any skipped
    block as SEQ_BLOCK_INCOMPLETE (review) and continues tracking.
  * Attempts of a different movement while a block is open are HELD while
    the switch is being confirmed, then attributed to the new block (or
    logged as out-of-order if the switch never confirms).
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
    notes_en: list[str] = field(default_factory=list)
    block_movement: Optional[str] = None   # the movement EXPECTED at this point

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
            "notes_en": self.notes_en,
            "expected_movement": self.block_movement,
            "confidence": round(self.attempt.confidence, 2),
            "confidence_label": _conf_label(self.attempt.confidence),
            "borderline": self.attempt.borderline,
        }


def _conf_label(c: float) -> str:
    if c >= 0.85:
        return "high"
    if c >= 0.65:
        return "medium"
    return "low"


def _reason_fa(code):
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
    rep_start: int = 1   # overall rep number this block starts at
    rep_end: int = 0     # overall rep number this block ends at

    def to_dict(self, idx: int, label_fa: str, label_en: str = "") -> dict:
        return {
            "idx": idx,
            "movement": self.movement,
            "movement_fa": label_fa,
            "movement_en": label_en or self.movement,
            "reps": self.reps,
            "credited": self.credited,
            "complete": self.complete,
            "rep_start": self.rep_start,
            "rep_end": self.rep_end,
            "status_fa": ("کامل" if self.complete else
                          ("ناقص" if self.credited > 0 else "شروع نشده")),
            "status_en": ("Complete" if self.complete else
                          ("Partial" if self.credited > 0 else "Not started")),
        }


class WodSequencer:
    def __init__(self, wod: dict, t_start: float, labels_fa: dict[str, str],
                 labels_en: Optional[dict[str, str]] = None):
        self.wod = wod
        self.t_start = t_start
        self.cap = float(wod.get("time_cap_sec") or 0)
        self.labels_fa = labels_fa
        self.labels_en = labels_en or {}
        self.blocks = [BlockState(movement=b["movement"], reps=int(b["reps"]))
                       for b in wod["blocks"]]
        # overall rep numbering: block 0 → reps 1..18, block 1 → 19..36, …
        cum = 0
        for b in self.blocks:
            b.rep_start = cum + 1
            cum += b.reps
            b.rep_end = cum
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

    @property
    def current_movement(self) -> str:
        return self.blocks[self.block_idx].movement if self.blocks else ""

    def rep_timeline(self) -> list[dict]:
        """The WOD's prescribed sequence in overall-rep terms — the
        machine-readable answer to 'which movement should be expected at
        rep N?'."""
        return [{
            "block": i,
            "movement": b.movement,
            "movement_fa": self.labels_fa.get(b.movement, b.movement),
            "movement_en": self.labels_en.get(b.movement, b.movement),
            "rep_start": b.rep_start,
            "rep_end": b.rep_end,
            "reps": b.reps,
        } for i, b in enumerate(self.blocks)]

    def _flag(self, code: str, t: float, extra: Optional[dict] = None) -> None:
        self.flags.append({"t": round(t, 2), "code": code,
                           "reason_fa": _reason_fa(code),
                           "reason_en": _reason_en(code), **(extra or {})})

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
        movement? Requires confirmed credits — or a sustained stream of
        that movement's attempts with the current movement gone quiet.

        The sequencer FOLLOWS THE ATHLETE: it can jump forward to the next
        prescribed block of the movement, or — when it had drifted ahead —
        realign BACKWARD to the earliest incomplete block of that movement
        (flagged for review). Judging never goes blind: every movement's
        FSM keeps running; only attribution changes."""
        cur = self.blocks[self.block_idx]
        if movement == cur.movement:
            return False
        pend = self.pending.get(movement, [])
        credits = sum(1 for p in pend if p.outcome == REP)
        attempts = len(pend)
        inactivity = t_now - self.last_credit_t.get(cur.movement, -1e9)
        confirmed = (
            credits >= SEQ["transition_confirm_reps"]
            or (credits >= 1 and inactivity >= SEQ["transition_confirm_sec"])
            # degraded path: a stream of the new movement's attempts with at
            # least one credit and the current movement quiet — the athlete
            # has clearly moved on; follow them and flag for review.
            or (attempts >= 4 and credits >= 1 and inactivity >= 6.0)
        )
        if not confirmed:
            return False
        # forward: the next prescribed block of this movement
        j = self._next_block_of(movement, self.block_idx + 1)
        realigned = False
        if j is None:
            # no later block of this movement — but if EARLIER blocks of it
            # are still incomplete, the sequencer had drifted ahead of the
            # athlete: realign backward to the earliest incomplete one.
            j = next((i for i, b in enumerate(self.blocks)
                      if b.movement == movement and not b.complete), None)
            if j is None:
                return False   # every block of this movement is complete
            realigned = True
        if realigned:
            self._flag("SEQ_REALIGN_BACKWARD", t_now,
                       {"from_block": self.block_idx, "to_block": j,
                        "movement": movement})
        # flag every skipped-in-between block as incomplete (review)
        skipped = False
        for k in range(self.block_idx, j):
            if not self.blocks[k].complete:
                skipped = True
                self._flag("SEQ_BLOCK_INCOMPLETE", t_now,
                           {"block": k, "movement": self.blocks[k].movement,
                            "credited": self.blocks[k].credited,
                            "reps": self.blocks[k].reps})
        if skipped and not realigned:
            self._flag("SEQ_ORDER_DEVIATION", t_now,
                       {"from_block": self.block_idx, "to_block": j})
        self.block_idx = j
        # re-attribute the attempts held while confirming the switch
        held = list(pend)
        self.pending.pop(movement, None)
        for a in held:
            self._attribute(a, t_now)
        return True

    def _attribute(self, a: Attempt, t_now: float) -> None:
        post_cap = self.cap and a.t_end > self.cap_abs + SEQ["cap_grace_sec"]
        cur = self.blocks[self.block_idx]

        # ---- wrong-movement attempt: hold while a switch is confirming ---- #
        if a.movement != cur.movement:
            nxt = self._next_block_of(a.movement, self.block_idx + 1)
            if nxt is None:
                # no LATER block of this movement — but earlier blocks may
                # still be incomplete (the sequencer had drifted ahead of
                # the athlete because of missed detections). Route through
                # the pending/realign path so those reps find their home.
                earliest_inc = next((i for i, b in enumerate(self.blocks)
                                     if b.movement == a.movement
                                     and not b.complete), None)
                if earliest_inc is None:
                    # genuinely no prescribed capacity left → excess of a
                    # completed movement (not scored)
                    self.events.append(ScoredEvent(
                        attempt=a, block_idx=None, rep_no=None, scored=False,
                        post_cap=post_cap,
                        block_movement=cur.movement,
                        notes=["خارج از ترتیب واد"], notes_en=["Out of WOD order"]))
                    return
            # a prescribed movement (forward or backward-realign) — hold it
            # while the switch confirms
            self.pending.setdefault(a.movement, []).append(a)
            self._maybe_advance(a.movement, t_now)
            return

        block = self.blocks[self.block_idx]

        # ---- post-cap attempts: logged, never scored ---- #
        if post_cap:
            self.events.append(ScoredEvent(
                attempt=a, block_idx=None, rep_no=None, scored=False,
                post_cap=True, block_movement=block.movement,
                notes=["پس از پایان زمان مجاز — شمرده نشد"],
                notes_en=["After the time cap — not scored"]))
            return

        # ---- no-rep of the current movement: logged with reason ---- #
        if a.outcome == NO_REP:
            self.events.append(ScoredEvent(
                attempt=a, block_idx=self.block_idx, rep_no=None, scored=False,
                block_movement=block.movement))
            return

        # ---- credited rep ---- #
        if block.credited < block.reps:
            block.credited += 1
            self.events.append(ScoredEvent(
                attempt=a, block_idx=self.block_idx, rep_no=block.credited,
                scored=True, block_movement=block.movement))
            if block.credited >= block.reps:
                block.complete = True
                self._check_finished()
                if not self.finished and self.block_idx + 1 < len(self.blocks):
                    self.block_idx += 1  # natural advance to the next block
                    self._absorb_pending()
        else:
            # this block is full — the rep still has a home if a LATER block
            # of the SAME movement has room (the engine may have under-
            # credited the current set due to missed detections; the athlete
            # continuing the movement flows into the next round of it —
            # flagged for order review, benefit of the doubt preserved)
            nxt = self._next_block_of(a.movement, self.block_idx + 1)
            if nxt is None:
                # no later block — fall back to the EARLIEST INCOMPLETE block
                # of this movement (the sequencer had drifted ahead)
                nxt = next((i for i, b in enumerate(self.blocks)
                            if b.movement == a.movement
                            and not b.complete), None)
                if nxt is not None and nxt != self.block_idx:
                    self._flag("SEQ_REALIGN_BACKWARD", t_now,
                               {"from_block": self.block_idx, "to_block": nxt,
                                "movement": a.movement})
            if nxt is not None and nxt != self.block_idx and not post_cap:
                skipped_between = [
                    k for k in range(min(self.block_idx, nxt),
                                     max(self.block_idx, nxt) + 1)
                    if not self.blocks[k].complete]
                if skipped_between:
                    self._flag("SEQ_SAME_MOVE_FLOW", t_now,
                               {"from_block": self.block_idx, "to_block": nxt,
                                "movement": a.movement})
                self.block_idx = nxt
                self._attribute(a, t_now)   # re-attribute into the next block
                return
            # no remaining capacity → excess (not scored)
            if not block.excess_flagged:
                block.excess_flagged = True
                self._flag("SEQ_EXCESS_REPS", a.t_end,
                           {"block": self.block_idx,
                            "movement": block.movement})
            self.events.append(ScoredEvent(
                attempt=a, block_idx=self.block_idx, rep_no=None, scored=False,
                block_movement=block.movement,
                notes=["رپ اضافه — بیش از تعداد تعیین‌شده این رند"],
                notes_en=["Excess rep — beyond this round's prescription"]))

    def _absorb_pending(self) -> None:
        """After a natural advance, re-attribute any held attempts that
        belong to the new current block (they were performed slightly
        before the switch was bookkeeping-visible)."""
        cur = self.current_movement
        held = self.pending.pop(cur, None)
        if not held:
            return
        # attribute held attempts of the NEW current movement, but never
        # let them double-score: they are credited only within block limits
        for a in held:
            self._attribute(a, self.last_activity_t)

    def flush(self, t_end: float) -> None:
        """Stream end: emit any attempts still held in pending as
        out-of-order events so the log is complete."""
        for movement, held in list(self.pending.items()):
            for a in held:
                self.events.append(ScoredEvent(
                    attempt=a, block_idx=None, rep_no=None, scored=False,
                    block_movement=self.current_movement,
                    notes=["خارج از ترتیب واد"], notes_en=["Out of WOD order"]))
            self.pending[movement] = []

    def _check_finished(self) -> None:
        if all(b.complete for b in self.blocks):
            self.finished = True
            scored = [e for e in self.events if e.scored]
            last = max((e.attempt.t_end for e in scored), default=self.t_start)
            self.finish_time = max(0.0, last - self.t_start)

    # ------------------------------------------------------------------ #
    def sync_fsms(self, fsms: list, t_now: float) -> list:
        """Expected-sequence constraint. All FSMs STAY ENABLED so the engine
        never goes blind when the sequencer drifts from the athlete's real
        position (observed: whole movements disappearing when a drifted
        sequencer disabled their FSM). Cross-movement interference is
        prevented by the per-movement PATTERN gates, not by disabling. The
        only task left here: force-close FSMs that are disabled for other
        reasons (none currently) — kept for interface stability."""
        closed = []
        for fsm in fsms:
            if not fsm.enabled:
                fsm.enabled = True
        return closed

    # ------------------------------------------------------------------ #
    def summary(self) -> dict:
        per_movement: dict[str, dict] = {}
        for b in self.blocks:
            m = per_movement.setdefault(b.movement, {
                "credited": 0, "no_reps": 0, "prescribed": 0,
                "complete_blocks": 0, "avg_confidence": None,
                "borderline_reps": 0})
            m["credited"] += b.credited
            m["prescribed"] += b.reps
            m["complete_blocks"] += 1 if b.complete else 0
        credited_confs: list[float] = []
        borderline_total = 0
        for e in self.events:
            if e.attempt.outcome == NO_REP and not e.post_cap:
                m = per_movement.setdefault(e.attempt.movement, {
                    "credited": 0, "no_reps": 0, "prescribed": 0,
                    "complete_blocks": 0, "avg_confidence": None,
                    "borderline_reps": 0})
                m["no_reps"] += 1
            if e.scored:
                credited_confs.append(e.attempt.confidence)
                if e.attempt.borderline:
                    borderline_total += 1
                if e.attempt.movement in per_movement:
                    pm = per_movement[e.attempt.movement]
                    pm.setdefault("_confs", []).append(e.attempt.confidence)
                    if e.attempt.borderline:
                        pm["borderline_reps"] += 1
        for m in per_movement.values():
            confs = m.pop("_confs", None) or []
            m["avg_confidence"] = (round(sum(confs) / len(confs), 2)
                                   if confs else None)
        last_block = max(
            (i for i, b in enumerate(self.blocks) if b.credited > 0),
            default=None)
        return {
            "finished": self.finished,
            "finish_time_sec": round(self.finish_time, 2) if self.finished else None,
            "capped": (not self.finished) and self.cap > 0,
            "total_credited": sum(b.credited for b in self.blocks),
            "total_prescribed": sum(b.reps for b in self.blocks),
            "per_movement": per_movement,
            "blocks": [b.to_dict(i, self.labels_fa.get(b.movement, b.movement),
                                 self.labels_en.get(b.movement, b.movement))
                       for i, b in enumerate(self.blocks)],
            "rep_timeline": self.rep_timeline(),
            "analysis_confidence": (round(sum(credited_confs) / len(credited_confs), 2)
                                    if credited_confs else None),
            "borderline_reps": borderline_total,
            "last_block_idx": last_block,
        }
