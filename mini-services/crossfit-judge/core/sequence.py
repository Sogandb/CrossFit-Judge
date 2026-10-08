"""
WOD orchestrator — the Runtime Interpreter of the agreed 3-layer design.

STRICT REP-RANGE STATE MACHINE (user spec, v2.4):

The WOD is a fixed ladder of blocks. For the Wodx ladder WOD-1:

    Round 1 (18+18):  Thruster 1-18   | Burpee 19-36
    Round 2 (15+15):  Thruster 37-51  | Burpee 52-66
    Round 3 (12+12):  Thruster 67-78  | Burpee 79-90
    Round 4 ( 9+ 9):  Thruster 91-99  | Burpee 100-108
    Round 5 ( 6+ 6):  Thruster 109-114| Burpee 115-120
    Round 6 ( 3+ 3):  Thruster 121-123| Burpee 124-126

Rules the sequencer implements EXACTLY:

  * The current block defines the EXPECTED movement and its rep slots.
  * EVERY attempt of the expected movement consumes one rep slot — whether
    it is judged REP (credited) or NO_REP (fault with reason + confidence).
    Rep quality NEVER blocks progression: a block that has consumed all its
    slots is COMPLETE and the sequencer switches to the next block at the
    very next rep number.
  * The overall rep number (1..126) is anchored to the WOD prescription:
    the burpee block always starts at rep 19, the second thruster block at
    37, and so on — regardless of no-reps along the way.
  * Each consumed attempt is judged independently: standard-compliant →
    credited (scored), or faulty → no-rep with a reason and a decision
    confidence percentage.
  * Attempts of a DIFFERENT movement do NOT consume slots:
      - sporadic (isolated cross-detections / order noise) → logged as
        movement-mismatch, not scored;
      - a sustained stream of another prescribed movement while the
        current block has gone quiet → the FSM has under-detected the
        current block and the athlete has moved on → REALIGN to the
        matching block (forward, or backward to the earliest incomplete
        one), flag skipped blocks SEQ_BLOCK_INCOMPLETE (review), and
        continue counting from that block's anchored rep number.
  * Attempts ending after t_start + time_cap are logged but NOT scored
    and do not consume slots (the workout is over).
  * Excess attempts once every block is complete → logged, not scored.
  * Workout completion: all blocks' slots consumed → finished; finish
    time = end of the last consumed attempt − t_start.
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
    rep_no: Optional[int]        # OVERALL rep number (1..126) for slot-consuming attempts
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
    reps: int                    # prescribed rep SLOTS in this block
    attempts: int = 0            # slots consumed (reps + no-reps)
    credited: int = 0            # of which judged good reps
    complete: bool = False       # all slots consumed
    excess_flagged: bool = False
    rep_start: int = 1           # overall rep number this block starts at
    rep_end: int = 0             # overall rep number this block ends at

    @property
    def no_reps(self) -> int:
        return self.attempts - self.credited

    @property
    def partial(self) -> bool:
        return 0 < self.attempts < self.reps

    def to_dict(self, idx: int, label_fa: str, label_en: str = "") -> dict:
        if self.complete:
            status_fa = "کامل" if self.credited >= self.reps else \
                f"کامل ({self.credited}/{self.reps} تأییدشده)"
            status_en = "Complete" if self.credited >= self.reps else \
                f"Complete ({self.credited}/{self.reps} credited)"
        elif self.partial:
            status_fa = "ناقص"
            status_en = "Partial"
        else:
            status_fa = "شروع نشده"
            status_en = "Not started"
        return {
            "idx": idx,
            "movement": self.movement,
            "movement_fa": label_fa,
            "movement_en": label_en or self.movement,
            "reps": self.reps,
            "attempts": self.attempts,
            "credited": self.credited,
            "no_reps": self.no_reps,
            "complete": self.complete,
            "rep_start": self.rep_start,
            "rep_end": self.rep_end,
            "status_fa": status_fa,
            "status_en": status_en,
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
        self.last_attempt_t: dict[str, float] = {}   # per-movement last attempt end
        self.pending: dict[str, list[Attempt]] = {}  # non-expected movement attempts
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
            self.last_attempt_t[a.movement] = max(
                self.last_attempt_t.get(a.movement, 0.0), a.t_end)
            self._attribute(a, t_now)

    def _next_block_of(self, movement: str, from_idx: int) -> Optional[int]:
        for j in range(from_idx, len(self.blocks)):
            if self.blocks[j].movement == movement:
                return j
        return None

    # ------------------------------------------------------------------ #
    # Realignment — RECOVERY ONLY (the primary mechanism is strict counting).
    # Fires when a sustained stream of another prescribed movement arrives
    # while the current block has gone quiet: the FSM under-detected the
    # current block and the athlete has verifiably moved on.
    # ------------------------------------------------------------------ #
    def _maybe_realign(self, movement: str, t_now: float) -> bool:
        pend = self.pending.get(movement, [])
        if len(pend) < SEQ["realign_stream"]:
            return False
        cur_mv = self.current_movement
        # the current movement must have gone quiet (active work on it means
        # these attempts are cross-detection noise, not a progression)
        quiet = t_now - self.last_attempt_t.get(cur_mv, -1e9)
        if quiet < SEQ["realign_quiet_sec"]:
            return False

        # forward: the next prescribed block of this movement …
        j = self._next_block_of(movement, self.block_idx + 1)
        realigned_backward = False
        if j is None:
            # … or backward to the earliest incomplete block of it (the
            # sequencer had drifted ahead of the athlete)
            j = next((i for i, b in enumerate(self.blocks)
                      if b.movement == movement and not b.complete), None)
            if j is None:
                return False   # every block of this movement is complete
            realigned_backward = True
        if realigned_backward:
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
                            "attempts": self.blocks[k].attempts,
                            "reps": self.blocks[k].reps})
        if skipped and not realigned_backward:
            self._flag("SEQ_ORDER_DEVIATION", t_now,
                       {"from_block": self.block_idx, "to_block": j})
        self.block_idx = j
        # re-attribute the attempts held while the realignment was confirming
        held = list(pend)
        self.pending.pop(movement, None)
        for a in held:
            self._attribute(a, t_now)
        return True

    # ------------------------------------------------------------------ #
    def _attribute(self, a: Attempt, t_now: float) -> None:
        post_cap = self.cap and a.t_end > self.cap_abs + SEQ["cap_grace_sec"]

        # ---- every block already complete: excess rep ---- #
        if self.block_idx >= len(self.blocks):
            self.events.append(ScoredEvent(
                attempt=a, block_idx=None, rep_no=None, scored=False,
                post_cap=post_cap, block_movement=None,
                notes=["رپ اضافه — وادی پیش‌تر کامل شده بود"],
                notes_en=["Excess rep — the WOD was already complete"]))
            if not any(f["code"] == "SEQ_EXCESS_REPS" for f in self.flags):
                self._flag("SEQ_EXCESS_REPS", a.t_end, {})
            return

        cur = self.blocks[self.block_idx]

        # ---- attempt of a DIFFERENT movement than expected ---- #
        if a.movement != cur.movement and not self.finished:
            nxt = self._next_block_of(a.movement, self.block_idx + 1)
            earliest_inc = next((i for i, b in enumerate(self.blocks)
                                 if b.movement == a.movement
                                 and not b.complete), None)
            if nxt is not None or earliest_inc is not None:
                # a prescribed movement (forward or backward-realign) — hold
                # it while the realignment is being confirmed
                self.pending.setdefault(a.movement, []).append(a)
                # bound the hold: pathological detection noise must not grow
                # the buffer indefinitely (realignment uses the tail)
                pend = self.pending[a.movement]
                if len(pend) > 30:
                    drop = pend.pop(0)
                    self._log_mismatch(drop, cur, post_cap)
                self._maybe_realign(a.movement, t_now)
                return
            # genuinely no prescribed capacity left for this movement
            self._log_mismatch(a, cur, post_cap)
            return
        if a.movement != cur.movement and self.finished:
            # the whole WOD is done — any further attempt is excess
            if not any(f["code"] == "SEQ_EXCESS_REPS" for f in self.flags):
                self._flag("SEQ_EXCESS_REPS", a.t_end,
                           {"movement": a.movement})
            self.events.append(ScoredEvent(
                attempt=a, block_idx=None, rep_no=None, scored=False,
                post_cap=post_cap, block_movement=None,
                notes=["رپ اضافه — وادی پیش‌تر کامل شده بود"],
                notes_en=["Excess rep — the WOD was already complete"]))
            return

        # ---- attempt of the EXPECTED movement, but after the time cap ---- #
        if post_cap:
            self.events.append(ScoredEvent(
                attempt=a, block_idx=self.block_idx, rep_no=None, scored=False,
                post_cap=True, block_movement=cur.movement,
                notes=["پس از پایان زمان مجاز — شمرده نشد"],
                notes_en=["After the time cap — not scored"]))
            return

        # ---- EXPECTED movement, inside the cap: consume a rep slot ------- #
        # (rep OR no-rep — the user spec: quality never blocks progression)
        if cur.attempts < cur.reps:
            cur.attempts += 1
            overall_rep = cur.rep_start + cur.attempts - 1
            if a.outcome == REP:
                cur.credited += 1
                self.events.append(ScoredEvent(
                    attempt=a, block_idx=self.block_idx, rep_no=overall_rep,
                    scored=True, block_movement=cur.movement))
            else:
                self.events.append(ScoredEvent(
                    attempt=a, block_idx=self.block_idx, rep_no=overall_rep,
                    scored=False, block_movement=cur.movement,
                    notes=["نورپ — رپ شمرده شد اما امتیاز نگرفت"],
                    notes_en=["No-rep — the slot was consumed but not scored"]))
            if cur.attempts >= cur.reps:
                cur.complete = True
                self._check_finished()
                if not self.finished and self.block_idx + 1 < len(self.blocks):
                    self.block_idx += 1   # natural advance to the next block
            return

        # ---- this block's slots are all consumed already ---- -------------- #
        # (the last block filled but the workout did not advance, or the
        # athlete keeps doing the current movement beyond prescription)
        if not cur.complete:
            cur.complete = True
            self._check_finished()
            if not self.finished and self.block_idx + 1 < len(self.blocks):
                self.block_idx += 1
            self._attribute(a, t_now)
            return
        if not cur.excess_flagged:
            cur.excess_flagged = True
            self._flag("SEQ_EXCESS_REPS", a.t_end,
                       {"block": self.block_idx,
                        "movement": cur.movement})
        self.events.append(ScoredEvent(
            attempt=a, block_idx=self.block_idx, rep_no=None, scored=False,
            post_cap=post_cap, block_movement=cur.movement,
            notes=["رپ اضافه — بیش از تعداد تعیین‌شده این رند"],
            notes_en=["Excess rep — beyond this round's prescription"]))

    def _log_mismatch(self, a: Attempt, cur: BlockState, post_cap: bool) -> None:
        self._flag("SEQ_MOVEMENT_MISMATCH", a.t_end,
                   {"movement": a.movement, "expected": cur.movement})
        self.events.append(ScoredEvent(
            attempt=a, block_idx=self.block_idx, rep_no=None, scored=False,
            post_cap=post_cap, block_movement=cur.movement,
            notes=["خارج از ترتیب واد — در این نقطه حرکت دیگری منتظر بود"],
            notes_en=["Out of WOD order — a different movement was expected here"]))

    # ------------------------------------------------------------------ #
    def flush(self, t_end: float) -> None:
        """Stream end: emit any attempts still held in pending as
        out-of-order events so the log is complete."""
        for movement, held in list(self.pending.items()):
            for a in held:
                cur = (self.blocks[self.block_idx]
                       if self.block_idx < len(self.blocks) else None)
                self._flag("SEQ_MOVEMENT_MISMATCH", a.t_end,
                           {"movement": movement,
                            "expected": cur.movement if cur else None})
                self.events.append(ScoredEvent(
                    attempt=a, block_idx=None, rep_no=None, scored=False,
                    block_movement=cur.movement if cur else None,
                    notes=["خارج از ترتیب واد — در این نقطه حرکت دیگری منتظر بود"],
                    notes_en=["Out of WOD order — a different movement was expected here"]))
            self.pending[movement] = []

    def _check_finished(self) -> None:
        if all(b.complete for b in self.blocks):
            self.finished = True
            consumed = [e for e in self.events if e.rep_no is not None]
            last = max((e.attempt.t_end for e in consumed), default=self.t_start)
            self.finish_time = max(0.0, last - self.t_start)

    # ------------------------------------------------------------------ #
    def sync_fsms(self, fsms: list, t_now: float) -> list:
        """Expected-sequence constraint. All FSMs STAY ENABLED so the engine
        never goes blind when the sequencer drifts from the athlete's real
        position (observed: whole movements disappearing when a drifted
        sequencer disabled their FSM). Cross-movement interference is
        prevented by the per-movement PATTERN gates, not by disabling."""
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
                "attempted": 0, "credited": 0, "no_reps": 0, "prescribed": 0,
                "complete_blocks": 0, "avg_confidence": None,
                "borderline_reps": 0})
            m["attempted"] += b.attempts
            m["credited"] += b.credited
            m["no_reps"] += b.no_reps
            m["prescribed"] += b.reps
            m["complete_blocks"] += 1 if b.complete else 0
        credited_confs: list[float] = []
        borderline_total = 0
        for e in self.events:
            if e.attempt.outcome == NO_REP and e.rep_no is not None:
                per_movement.setdefault(e.attempt.movement, {
                    "attempted": 0, "credited": 0, "no_reps": 0, "prescribed": 0,
                    "complete_blocks": 0, "avg_confidence": None,
                    "borderline_reps": 0})
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
            (i for i, b in enumerate(self.blocks) if b.attempts > 0),
            default=None)
        return {
            "finished": self.finished,
            "finish_time_sec": round(self.finish_time, 2) if self.finished else None,
            "capped": (not self.finished) and self.cap > 0,
            "total_credited": sum(b.credited for b in self.blocks),
            "total_attempted": sum(b.attempts for b in self.blocks),
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
