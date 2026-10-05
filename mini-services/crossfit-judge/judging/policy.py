"""Shared judging policy helpers — the "benefit of the doubt" engine.

Every movement standard check evaluates into one of THREE verdicts:

  OK          — measurement is clearly past the standard → pass, full credit
  BORDERLINE  — measurement is inside the uncertainty band → pass, but the
                rep is flagged for human review and its confidence is capped
                (the CrossFit video-review standard: when the evidence is not
                CLEAR, the athlete gets the benefit of the doubt)
  FAIL        — measurement is clearly in violation (and visibility/anchor
                quality is good enough to trust) → automatic no-rep

Additionally, every check computes a per-rep CONFIDENCE (0..1) from how far
past the decisive threshold the measurement was, and from the quality of the
input (landmark visibility). Low-visibility measurements never auto-penalise:
they degrade to BORDERLINE (credit + review) — an unreliable measurement can
never cost the athlete a rep, only flag it for a human.
"""
from __future__ import annotations

from config.settings import JUDGE

# Verdict constants
OK = "ok"
BORDERLINE = "borderline"
FAIL = "fail"


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def vis_quality(vis: float) -> float:
    """Map landmark visibility to a 0..1 quality factor.

    ≥ JUDGE.vis_soft (0.55) → 1.0 (fully trusted)
    ≤ JUDGE.vis_floor (0.35) → 0.0 (measurement unreliable)
    """
    return _clamp((vis - JUDGE["vis_floor"]) /
                  (JUDGE["vis_soft"] - JUDGE["vis_floor"]), 0.0, 1.0)


def band(value: float, clear_pass: float, bod_pass: float,
         clear_fail: float, bod_fail: float, vis: float) -> tuple[str, float]:
    """Evaluate one continuous check against the three-band policy.

    Values must be oriented so that LARGER = better compliance.

      clear_pass   ≥ this → OK
      bod_pass     ≥ this (but < clear_pass) → BORDERLINE
      bod_fail     ≥ this (but < bod_pass)   → BORDERLINE only if the
                    measurement is weak (low visibility) — with good
                    visibility this is a FAIL
      clear_fail   < this  → FAIL regardless of visibility

    Returns (verdict, margin) where margin ∈ 0..1 is how decisively the
    verdict was reached (used for confidence).
    """
    vq = vis_quality(vis)
    if value >= clear_pass:
        # margin: distance from the clear-pass line, normalised over the
        # borderline band width (0 at the line, 1 one band-width further in)
        width = max(clear_pass - bod_pass, 1e-6)
        return OK, _clamp((value - clear_pass) / width, 0.0, 1.0)
    if value >= bod_pass:
        return BORDERLINE, _clamp((value - bod_pass) /
                                  max(clear_pass - bod_pass, 1e-6), 0.0, 1.0)
    # below bod_pass → violation; how SEVERE?
    if value > bod_fail and vq < 0.5:
        # violation but the measurement itself is unreliable → doubt favors
        # the athlete
        return BORDERLINE, 0.0
    if value <= clear_fail:
        severity = _clamp((bod_pass - value) /
                          max(bod_pass - clear_fail, 1e-6), 0.0, 1.0)
        return FAIL, severity
    # between bod_fail and bod_pass with decent visibility → a real but
    # not overwhelming violation: FAIL with modest severity
    severity = _clamp((bod_pass - value) /
                      max(bod_pass - clear_fail, 1e-6), 0.0, 1.0)
    return FAIL, severity


def band_bool(condition: bool | None, vis: float) -> tuple[str, float]:
    """Boolean check under the same policy. condition=None means "cannot
    measure" → BORDERLINE (benefit of the doubt) with zero margin."""
    if condition is None:
        return BORDERLINE, 0.0
    if condition:
        return OK, 1.0
    if vis_quality(vis) < 0.5:
        return BORDERLINE, 0.0
    return FAIL, 0.6


def rep_confidence(margins: list[float], vis: float, borderline: bool) -> float:
    """Confidence for a CREDITED rep.

    margins — the decisive check margins (0 = exactly at the clear line,
              1 = decisively past it)
    vis     — worst landmark visibility used by the decisive checks
    """
    m = min(margins) if margins else 0.5
    base = 0.60 + 0.35 * _clamp(m, 0.0, 1.0)
    vq = vis_quality(vis)
    c = 0.5 + (base - 0.5) * (0.7 + 0.3 * vq)
    if borderline:
        c = min(c, JUDGE["borderline_cap"])
    if vq <= 0.0:
        c = min(c, JUDGE["low_vis_cap"])
    return round(_clamp(c, 0.30, 0.97), 2)


def norep_confidence(severity: float, vis: float) -> float:
    """Confidence for a NO-REP decision.

    severity — how far into the violation band the measurement was (0..1)
    vis      — visibility of the joints the decision rests on
    """
    base = 0.55 + 0.40 * _clamp(severity, 0.0, 1.0)
    vq = vis_quality(vis)
    c = 0.5 + (base - 0.5) * (0.7 + 0.3 * vq)
    return round(_clamp(c, 0.30, 0.97), 2)
