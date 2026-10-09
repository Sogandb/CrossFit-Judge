"""
WOD sequencer v3.0 — THE USER'S EXACT STATE MACHINE (spec 2026-10-09).

State variables (exactly as prescribed):

  * Global Counter (شمارنده کل)  : 1 .. 126 — advances ONE slot per ATTEMPT
    of the expected movement, whether the verdict is REP or NO-REP. Quality
    never blocks progression: «چه رپ باشه چه نورپ».
  * Current State (حالت جاری)    : THRUSTER | BURPEE — the movement that is
    EXPECTED right now. The system knows, on every count, which movement is
    about to be attempted and judges exactly that.
  * Round Counter (شماره دور)    : rounds 1..6 with target 18/15/12/9/6/3.
  * Round Progress (پیشروی دور)  : attempts consumed in the current round
    phase.

Transition logic (user spec, verbatim):

  * In THRUSTER: when round progress reaches the round target (18/15/12/9/6)
    → switch to BURPEE.
  * In BURPEE: when round progress reaches the round target → go to the next
    round, set the new round target, switch to THRUSTER.
  * Last round (3): when the 3rd burpee is consumed → THE WOD IS COMPLETE.

Overall rep numbers are ANCHORED to the prescription — they never skip, never
jump, never reorder:

    Thruster 1-18   | 37-51  | 67-78  | 91-99  | 109-114 | 121-123
    Burpee   19-36  | 52-66  | 79-90  | 100-108| 115-120 | 124-126

Attribution rules:

  * Expected-movement attempt → consumes the next global slot. Verdict:
    REP (credited) or NO_REP (reason + decision confidence %). Every
    consumed slot is one row in the ladder: number → movement → verdict.
  * Other-movement attempt → DETECTION NOISE. The athlete follows the WOD;
    a cross-detection is the machine's error, not the athlete's. Noise is
    counted, never numbered, never rendered in the ladder, and never
    switches the state on its own.
  * STALL RECOVERY (the honest replacement for the old "realign"): when a
    sustained stream of the NEXT movement arrives while the expected
    movement has gone quiet, the FSM under-detected the tail of the current
    phase → its REMAINING slots are marked NOT_DETECTED (visible rows with
    no verdict — the engine never invents reps), the state advances, and
    the genuinely-held attempts of the new movement consume the next
    anchored slots. Numbering stays exactly anchored either way — no
    forward jumps, no backward jumps, no dashes.
  * Attempts after the time cap — ONLY enforced when the WOD start was
    actually detected (beeps or manual). They are logged as post-cap
    events (visible as a footnote count) but do not consume slots: the
    workout is over at the cap. When the start was NOT detected the cap
    clock is unknown and enforcing it from t=0 would silently discard real
    reps — so it is NOT enforced and the analysis says so honestly.
  * Excess attempts after rep 126 → logged, not scored, not numbered.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from config.settings import SEQ
from core.types import NO_REP, REP, Attempt
from movements.reasons import reason_category


# ladder row verdicts
V_REP = "rep"
V_NO_REP = "no_rep"
V_NOT_DETECTED = "not_detected"
V_NOT_REACHED = "not_reached"


@dataclass
class ScoredEvent:
    """One attempt as the engine attributes it.

    kind:
      slot     — consumed a WOD slot (rep_no set) — the only kind that
                 appears in the ladder
      post_cap — after the enforced time cap; logged, not scored, no slot
      noise    — detection noise / out-of-order; suppressed from the ladder
      excess   — after the WOD was already complete
    """
    attempt: Attempt
    phase_idx: Optional[int]
    rep_no: Optional[int]        # OVERALL rep number (1..126) for slot events
    scored: bool                 # counted toward the score
    kind: str = "slot"
    notes: list[str] = field(default_factory=list)
    notes_en: list[str] = field(default_factory=list)
    expected_movement: Optional[str] = None

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
            "phase_idx": self.phase_idx,
            "rep_no": self.rep_no,
            "scored": self.scored,
            "kind": self.kind,
            "details": self.attempt.details,
            "review_flags": self.attempt.review_flags,
            "notes": self.notes,
            "notes_en": self.notes_en,
            "expected_movement": self.expected_movement,
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
class PhaseState:
    """One phase of the ladder = one movement run inside one round
    (e.g. round 1 = THRUSTER phase 18 slots, then BURPEE phase 18 slots)."""
    movement: str
    reps: int                    # prescribed rep SLOTS in this phase
    attempts: int = 0            # slots CONSUMED by real attempts (rep+no-rep)
    credited: int = 0            # of which judged good reps
    not_detected: int = 0        # slots abandoned as undetected (stall recovery)
    consumed: list = field(default_factory=list)   # ScoredEvents, in order
    rep_start: int = 1           # anchored overall rep number this phase starts at
    rep_end: int = 0

    @property
    def slots_filled(self) -> int:
        return self.attempts + self.not_detected

    @property
    def complete(self) -> bool:
        return self.slots_filled >= self.reps

    @property
    def no_reps(self) -> int:
        return self.attempts - self.credited

    def to_dict(self, idx: int, label_fa: str, label_en: str = "") -> dict:
        if self.complete and self.not_detected == 0:
            status_fa = "کامل" if self.credited >= self.reps else \
                f"کامل ({self.credited}/{self.reps} تأییدشده)"
            status_en = "Complete" if self.credited >= self.reps else \
                f"Complete ({self.credited}/{self.reps} credited)"
        elif self.complete:
            status_fa = (f"پیش رفت ({self.not_detected} رپ تشخیص داده نشد)")
            status_en = (f"Advanced ({self.not_detected} reps not detected)")
        elif self.attempts > 0:
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
            "not_detected": self.not_detected,
            "complete": self.complete,
            "rep_start": self.rep_start,
            "rep_end": self.rep_end,
            "status_fa": status_fa,
            "status_en": status_en,
        }


class WodSequencer:
    """The user's global-counter state machine over the prescribed ladder."""

    def __init__(self, wod: dict, t_start: float, labels_fa: dict[str, str],
                 labels_en: Optional[dict[str, str]] = None,
                 cap_enforced: bool = True):
        self.wod = wod
        self.t_start = t_start
        self.cap = float(wod.get("time_cap_sec") or 0)
        self.cap_enforced = cap_enforced and self.cap > 0
        self.labels_fa = labels_fa
        self.labels_en = labels_en or {}
        self.phases = [PhaseState(movement=b["movement"], reps=int(b["reps"]))
                       for b in wod["blocks"]]
        # anchored overall rep numbering: phase 0 → 1..18, phase 1 → 19..36 …
        cum = 0
        for p in self.phases:
            p.rep_start = cum + 1
            cum += p.reps
            p.rep_end = cum
        self.total_reps = cum
        self.phase_idx = 0
        self.events: list[ScoredEvent] = []
        self.flags: list[dict] = []
        self.finished = False
        self.finish_time: Optional[float] = None
        self.last_attempt_t: dict[str, float] = {}   # per-movement last attempt END
        self.noise_events = 0
        self.post_cap_events = 0
        self.excess_events = 0
        self.cap_hit = False
        # other-movement attempts held while confirming a possible stall
        self.held: dict[str, list[Attempt]] = {}
        self.phase_enter_t: dict[int, float] = {}

    # ------------------------------------------------------------------ #
    # user-spec state snapshot (rounds expressed over phase pairs)
    # ------------------------------------------------------------------ #
    @property
    def current_state(self) -> str:
        """THRUSTER | BURPEE — the EXPECTED movement right now."""
        return self.phases[self.phase_idx].movement if self.phase_idx < len(self.phases) else ""

    @property
    def round_no(self) -> int:
        """Round counter 1..6 (each round = thruster phase + burpee phase)."""
        return self.phase_idx // 2 + 1 if self.phase_idx < len(self.phases) else 0

    @property
    def round_target(self) -> int:
        """The current round's number (18/15/12/9/6/3)."""
        return self.phases[self.phase_idx].reps if self.phase_idx < len(self.phases) else 0

    @property
    def round_progress(self) -> int:
        """Attempts consumed in the current round phase."""
        return self.phases[self.phase_idx].slots_filled if self.phase_idx < len(self.phases) else 0

    @property
    def global_counter(self) -> int:
        """The next overall rep number to be assigned (1-based)."""
        if self.phase_idx >= len(self.phases):
            return self.total_reps + 1
        return self.phases[self.phase_idx].rep_start + self.phases[self.phase_idx].slots_filled

    @property
    def cap_abs(self) -> float:
        return self.t_start + self.cap if self.cap else float("inf")

    def rep_timeline(self) -> list[dict]:
        """The prescribed sequence in overall-rep terms — machine-readable
        'which movement is expected at rep N?'."""
        return [{
            "block": i,
            "movement": p.movement,
            "movement_fa": self.labels_fa.get(p.movement, p.movement),
            "movement_en": self.labels_en.get(p.movement, p.movement),
            "rep_start": p.rep_start,
            "rep_end": p.rep_end,
            "reps": p.reps,
        } for i, p in enumerate(self.phases)]

    def _flag(self, code: str, t: float, extra: Optional[dict] = None) -> None:
        self.flags.append({"t": round(t, 2), "code": code,
                           "reason_fa": _reason_fa(code),
                           "reason_en": _reason_en(code), **(extra or {})})

    # ------------------------------------------------------------------ #
    def feed(self, attempts: list[Attempt], t_now: float) -> None:
        for a in attempts:
            self._attribute(a, t_now)

    # ------------------------------------------------------------------ #
    def _attribute(self, a: Attempt, t_now: float) -> None:
        # ---- WOD already complete: excess attempt ------------------------ #
        if self.finished or self.phase_idx >= len(self.phases):
            self.excess_events += 1
            self.events.append(ScoredEvent(
                attempt=a, phase_idx=None, rep_no=None, scored=False,
                kind="excess", expected_movement=None,
                notes=["رپ اضافه — وادی پیش‌تر کامل شده بود"],
                notes_en=["Excess rep — the WOD was already complete"]))
            if not any(f["code"] == "SEQ_EXCESS_REPS" for f in self.flags):
                self._flag("SEQ_EXCESS_REPS", a.t_end, {"movement": a.movement})
            return

        phase = self.phases[self.phase_idx]

        # ---- after the enforced time cap: the workout is over --------- #
        # (checked BEFORE movement matching: past the cap nothing matters
        # any more — no slots, no state switches, no recovery)
        if self.cap_enforced and a.t_end > self.cap_abs + SEQ["cap_grace_sec"]:
            self.post_cap_events += 1
            self.cap_hit = True
            self.events.append(ScoredEvent(
                attempt=a, phase_idx=self.phase_idx, rep_no=None, scored=False,
                kind="post_cap", expected_movement=phase.movement,
                notes=["پس از پایان زمان مجاز — شمرده نشد"],
                notes_en=["After the time cap — not scored"]))
            if not any(f["code"] == "SEQ_TIME_CAP" for f in self.flags):
                self._flag("SEQ_TIME_CAP", a.t_end,
                           {"t_start": self.t_start, "cap": self.cap})
            return

        # ---- attempt of a DIFFERENT movement: detection noise ------------ #
        # (possibly the start of the next phase's stream — hold briefly)
        if a.movement != phase.movement:
            self.held.setdefault(a.movement, []).append(a)
            buf = self.held[a.movement]
            if len(buf) > SEQ["hold_buffer_max"]:
                buf.pop(0)
                self.noise_events += 1
            self._maybe_stall_advance(a.movement, t_now)
            return

        # ---- EXPECTED movement, inside the cap: CONSUME A SLOT ----------- #
        # (rep OR no-rep — the user spec: quality never blocks progression)
        self._consume(a, phase)

    def _consume(self, a: Attempt, phase: PhaseState) -> None:
        rep_no = phase.rep_start + phase.slots_filled
        phase.attempts += 1
        if a.outcome == REP:
            phase.credited += 1
            ev = ScoredEvent(attempt=a, phase_idx=self.phase_idx,
                             rep_no=rep_no, scored=True, kind="slot",
                             expected_movement=phase.movement)
        else:
            ev = ScoredEvent(
                attempt=a, phase_idx=self.phase_idx, rep_no=rep_no,
                scored=False, kind="slot", expected_movement=phase.movement,
                notes=["نورپ — رپ شمرده شد اما امتیاز نگرفت"],
                notes_en=["No-rep — the slot was consumed but not scored"])
        phase.consumed.append(ev)
        self.events.append(ev)
        self.last_attempt_t[a.movement] = max(
            self.last_attempt_t.get(a.movement, 0.0), a.t_end)
        if phase.complete:
            self._advance(a.t_end)

    # ------------------------------------------------------------------ #
    def _advance(self, t_now: float) -> None:
        """Phase complete (all slots consumed or marked not-detected):
        apply the user's transition logic and move to the next phase."""
        done_mv = self.phases[self.phase_idx].movement
        self.phase_idx += 1
        self.phase_enter_t[self.phase_idx] = t_now
        if self.phase_idx >= len(self.phases):
            self._finish()
            return
        # attempts of the NEW expected movement that were held while the
        # previous phase was finishing: re-attribute the recent ones (they
        # are the first real attempts of this phase — the athlete can start
        # the next movement within a second of finishing the last slot);
        # older held ones duplicate already-consumed reps → noise.
        new_mv = self.phases[self.phase_idx].movement
        self._inherit_held(new_mv, cutoff=self._last_end_of(done_mv))

    def _inherit_held(self, movement: str, cutoff: Optional[float]) -> None:
        """Hand recently-held attempts of `movement` over to the new phase.
        Attempts starting at/after (cutoff − tolerance) are real; earlier
        ones are cross-detection duplicates of consumed reps."""
        held = self.held.pop(movement, [])
        if not held:
            return
        tol = SEQ["dup_overlap_tol_sec"]
        real, dups = [], []
        for a in held:
            if cutoff is None or a.t_start >= cutoff - tol:
                real.append(a)
            else:
                dups.append(a)
        self.noise_events += len(dups)
        for a in real:
            self._attribute(a, a.t_end)

    def _last_end_of(self, movement: str) -> Optional[float]:
        return self.last_attempt_t.get(movement)

    # ------------------------------------------------------------------ #
    # Stall recovery — the honest replacement for the old realign.
    # Fires when the NEXT movement shows a sustained stream while the
    # expected movement has gone quiet: the FSM under-detected the tail of
    # the current phase. Remaining slots are marked NOT_DETECTED (visible,
    # never invented), the state advances, held attempts consume slots.
    # Numbering stays anchored. FORWARD-ONLY — the athlete never goes back.
    # ------------------------------------------------------------------ #
    def _maybe_stall_advance(self, movement: str, t_now: float) -> None:
        if self.finished or self.phase_idx >= len(self.phases) - 1:
            return                                   # last phase: nothing to advance to
        nxt = self.phases[self.phase_idx + 1]
        if nxt.movement != movement:
            return                                   # not the next prescribed movement
        held = self.held.get(movement, [])
        if len(held) < SEQ["switch_stream"]:
            return
        cur = self.phases[self.phase_idx]
        # the expected movement must have gone quiet (active work on it
        # means these held attempts are cross-detection noise)
        last_expected = self.last_attempt_t.get(cur.movement)
        if last_expected is None:
            quiet_ref = self.phase_enter_t.get(self.phase_idx, self.t_start)
        else:
            quiet_ref = last_expected
        if t_now - quiet_ref < SEQ["switch_quiet_sec"]:
            return

        remaining = cur.reps - cur.slots_filled
        if remaining > 0:
            cur.not_detected = remaining
            self._flag("SEQ_SLOTS_NOT_DETECTED", t_now, {
                "phase": self.phase_idx, "movement": cur.movement,
                "from_rep": cur.rep_start + cur.slots_filled,
                "to_rep": cur.rep_end,
                "count": remaining,
            })
        # advance past the current phase (user transition logic) and let
        # the genuinely-held attempts consume the next anchored slots
        self._advance(t_now)

    # ------------------------------------------------------------------ #
    def _finish(self) -> None:
        self.finished = True
        consumed = [e for e in self.events if e.kind == "slot"]
        last = max((e.attempt.t_end for e in consumed), default=self.t_start)
        self.finish_time = max(0.0, last - self.t_start)

    def flush(self, t_end: float) -> None:
        """Stream end: everything still held is honest detection noise."""
        for movement, held in list(self.held.items()):
            self.noise_events += len(held)
            self.held[movement] = []

    # ------------------------------------------------------------------ #
    def sync_fsms(self, fsms: list, t_now: float) -> list:
        """All FSMs STAY ENABLED — the sequencer OWNS attribution. A drifted
        or under-detecting FSM can never make the engine go blind; wrong-
        movement output is absorbed as noise by the state machine."""
        for fsm in fsms:
            if not fsm.enabled:
                fsm.enabled = True
        return []

    # ------------------------------------------------------------------ #
    def ladder(self) -> list[dict]:
        """THE result the user asked for: one row per prescribed rep,
        1..126, each with its prescribed movement and its verdict.

        verdict: rep | no_rep | not_detected | not_reached
        """
        rows: list[dict] = []
        for phase in self.phases:
            mv_fa = self.labels_fa.get(phase.movement, phase.movement)
            for i in range(phase.reps):
                rep_no = phase.rep_start + i
                base = {
                    "rep_no": rep_no,
                    "movement": phase.movement,
                    "movement_fa": mv_fa,
                    "movement_en": self.labels_en.get(phase.movement, phase.movement),
                }
                if i < len(phase.consumed):
                    ev = phase.consumed[i]
                    base.update({
                        "verdict": ev.attempt.outcome,     # rep | no_rep
                        "t_start": round(ev.attempt.t_start, 2),
                        "t_end": round(ev.attempt.t_end, 2),
                        "scored": ev.scored,
                        "confidence": round(ev.attempt.confidence, 2),
                        "confidence_label": _conf_label(ev.attempt.confidence),
                        "borderline": ev.attempt.borderline,
                        "reason_code": ev.attempt.reason_code,
                        "reason_fa": _reason_fa(ev.attempt.reason_code),
                        "reason_en": _reason_en(ev.attempt.reason_code),
                        "review_flags": list(ev.attempt.review_flags),
                        "notes": list(ev.notes),
                        "notes_en": list(ev.notes_en),
                    })
                elif i < phase.slots_filled:
                    base.update({"verdict": V_NOT_DETECTED})
                else:
                    base.update({"verdict": V_NOT_REACHED})
                rows.append(base)
        return rows

    # ------------------------------------------------------------------ #
    def summary(self) -> dict:
        per_movement: dict[str, dict] = {}
        for p in self.phases:
            m = per_movement.setdefault(p.movement, {
                "attempted": 0, "credited": 0, "no_reps": 0, "prescribed": 0,
                "not_detected": 0, "complete_blocks": 0,
                "avg_confidence": None, "borderline_reps": 0})
            m["attempted"] += p.attempts
            m["credited"] += p.credited
            m["no_reps"] += p.no_reps
            m["prescribed"] += p.reps
            m["not_detected"] += p.not_detected
            m["complete_blocks"] += 1 if p.complete else 0
        credited_confs: list[float] = []
        borderline_total = 0
        for e in self.events:
            if e.scored:
                credited_confs.append(e.attempt.confidence)
                if e.attempt.borderline:
                    borderline_total += 1
                pm = per_movement.get(e.attempt.movement)
                if pm is not None:
                    pm.setdefault("_confs", []).append(e.attempt.confidence)
                    if e.attempt.borderline:
                        pm["borderline_reps"] += 1
        for m in per_movement.values():
            confs = m.pop("_confs", None) or []
            m["avg_confidence"] = (round(sum(confs) / len(confs), 2)
                                   if confs else None)
        total_consumed = sum(p.attempts for p in self.phases)
        total_not_detected = sum(p.not_detected for p in self.phases)
        last_phase = max(
            (i for i, p in enumerate(self.phases) if p.slots_filled > 0),
            default=None)
        return {
            "finished": self.finished,
            "finish_time_sec": round(self.finish_time, 2) if self.finished else None,
            "capped": (not self.finished) and self.cap_enforced,
            "cap_enforced": self.cap_enforced,
            "cap_hit": self.cap_hit,
            "total_credited": sum(p.credited for p in self.phases),
            "total_consumed": total_consumed,
            "total_attempted": total_consumed,     # legacy alias
            "total_no_reps": total_consumed - sum(p.credited for p in self.phases),
            "total_not_detected": total_not_detected,
            "total_not_reached": self.total_reps - total_consumed - total_not_detected,
            "total_prescribed": self.total_reps,
            "noise_events": self.noise_events,
            "post_cap_events": self.post_cap_events,
            "excess_events": self.excess_events,
            "per_movement": per_movement,
            "blocks": [p.to_dict(i, self.labels_fa.get(p.movement, p.movement),
                                 self.labels_en.get(p.movement, p.movement))
                       for i, p in enumerate(self.phases)],
            "rep_timeline": self.rep_timeline(),
            "ladder": self.ladder(),
            "analysis_confidence": (round(sum(credited_confs) / len(credited_confs), 2)
                                    if credited_confs else None),
            "borderline_reps": borderline_total,
            "last_block_idx": last_phase,
        }
