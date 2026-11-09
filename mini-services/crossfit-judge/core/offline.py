"""Offline, whole-video EVIDENCE detection (no counter, no state machine).

An attempt exists only where the movement leaves its signature:
  * BURPEE   = chest/hands reach the floor (sternum low)  AND  the athlete
               then goes over the bar (both feet airborne, or a clear step
               across). Bending over to breathe, hinging with hands on the
               bar, sitting or lying down to rest NEVER qualify.
  * THRUSTER = a squat bottom (hip near/below knee) with the bar in the hands
               (wrists at the shoulders) and/or pressed overhead. Hands on
               knees, sitting, bar set-down NEVER qualify.
Everything is scale-normalised by the athlete's height H, smoothed, and
computed non-causally over the full signal so no fast phase can be "missed"
by a state machine that was looking elsewhere.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.signal import find_peaks

from core.types import PoseFrame, SceneModel

# ---- evidence thresholds (fractions of body height H) --------------------- #
FLOOR_SH_H = 0.42        # sternum this low = floor work (plank-top ~0.30-0.35)
JUMP_MIN_H = 0.03        # lower ankle lifted  >=  this ...
JUMP_MAX_H = 0.08        # ... and higher ankle >= this  => both feet airborne
JUMP_MIN_DISP = 0.20     # horizontal travel during flight (crossing, not a hop)
STEP_DISP = 0.30         # step-over without flight: travel after the floor phase
BURPEE_PAIR_WINDOW = 3.8
THR_PROM = 0.10          # hip-depth peak prominence
THR_MIN_GAP = 0.9
THR_MIN_PEAK = -0.15     # a squat must at least approach parallel
RACK_REL = -0.10         # wrists within 0.10H below the shoulders = racked
OVERHEAD_REL = 0.20      # wrists >= 0.20H above shoulders = pressed


@dataclass
class Series:
    t: np.ndarray
    sh_h: np.ndarray
    wr_h: np.ndarray
    wr_rel: np.ndarray
    hip_depth: np.ndarray
    ank_l: np.ndarray
    ank_r: np.ndarray
    ank_x: np.ndarray
    fps: float
    H: float

    def idx(self, t: float) -> int:
        return int(np.clip(np.searchsorted(self.t, t), 0, len(self.t) - 1))


def _smooth(a: np.ndarray, k: int = 3) -> np.ndarray:
    m = ~np.isnan(a)
    x = np.where(m, a, 0.0)
    w = np.ones(k)
    num, den = np.convolve(x, w, "same"), np.convolve(m.astype(float), w, "same")
    out = np.where(den > 0, num / np.maximum(den, 1e-9), np.nan)
    out[~m] = np.nan
    return out


def _fill(a: np.ndarray, fps: float, max_gap_s: float = 0.5) -> np.ndarray:
    n = len(a)
    isn = np.isnan(a)
    if isn.all() or not isn.any():
        return a
    idx = np.arange(n)
    full = np.interp(idx, idx[~isn], a[~isn])
    out = a.copy()
    i = 0
    while i < n:
        if isn[i]:
            j = i
            while j < n and isn[j]:
                j += 1
            if i > 0 and j < n and (j - i) / fps <= max_gap_s:
                out[i:j] = full[i:j]
            i = j
        else:
            i += 1
    return out


def build_series(frames: list[tuple[float, PoseFrame]], scene: SceneModel,
                 fps: float) -> Series:
    n, H = len(frames), max(scene.H, 1.0)
    nan = lambda: np.full(n, np.nan)
    t, sh_h, wr_h, wr_rel, hd = np.zeros(n), nan(), nan(), nan(), nan()
    al, ar, ax = nan(), nan(), nan()

    def gy(x: float) -> float:
        g = scene.ground_y_at(x)
        return g if g is not None else scene.ground_a

    def pts(pf, a, b, vmin=0.3):
        v = [p for p in (pf.get(a), pf.get(b)) if p is not None and p.visibility >= vmin]
        if not v:
            return None
        return (sum(p.x for p in v) / len(v), sum(p.y for p in v) / len(v))

    for i, (ti, pf) in enumerate(frames):
        t[i] = ti
        if not pf.person_detected:
            continue
        sh = pts(pf, "left_shoulder", "right_shoulder")
        hip = pts(pf, "left_hip", "right_hip")
        knee = pts(pf, "left_knee", "right_knee")
        wr = pts(pf, "left_wrist", "right_wrist")
        if sh:
            sh_h[i] = (gy(sh[0]) - sh[1]) / H
        if wr:
            wr_h[i] = (gy(wr[0]) - wr[1]) / H
            if sh:
                wr_rel[i] = (sh[1] - wr[1]) / H
        if hip and knee:
            hd[i] = (hip[1] - knee[1]) / H
        pl, pr = pf.get("left_ankle"), pf.get("right_ankle")
        if pl is not None and pl.visibility >= 0.3:
            al[i] = (gy(pl.x) - pl.y) / H
        if pr is not None and pr.visibility >= 0.3:
            ar[i] = (gy(pr.x) - pr.y) / H
        a = pts(pf, "left_ankle", "right_ankle")
        if a:
            ax[i] = a[0]
    # feet-on-ground baseline (ankle joint sits above the sole): subtract it
    low = np.fmin(al, ar)
    if (~np.isnan(low)).sum() > 10:
        base = float(np.nanpercentile(low, 10))
        al, ar = al - base, ar - base
    sm = lambda a: _smooth(_fill(a, fps), 3)
    return Series(t, sm(sh_h), sm(wr_h), sm(wr_rel), sm(hd), sm(al), sm(ar),
                  _fill(ax, fps), fps, H)


def _episodes(mask: np.ndarray, fps: float, min_s: float, merge_s: float):
    runs, i, n = [], 0, len(mask)
    while i < n:
        if mask[i]:
            j = i
            while j + 1 < n and mask[j + 1]:
                j += 1
            runs.append([i, j])
            i = j + 1
        else:
            i += 1
    merged: list[list[int]] = []
    for r in runs:
        if merged and (r[0] - merged[-1][1]) / fps <= merge_s:
            merged[-1][1] = r[1]
        else:
            merged.append(r)
    return [(a, b) for a, b in merged if (b - a + 1) / fps >= min_s]


# --------------------------------------------------------------------------- #
def find_burpee_candidates(S: Series) -> tuple[list[dict], list[dict]]:
    """Returns (candidates, ambiguous_floor_events)."""
    fps = S.fps
    floor_mask = np.nan_to_num(S.sh_h, nan=9.0) <= FLOOR_SH_H
    floors = _episodes(floor_mask, fps, 0.12, 0.35)
    both_up = (np.nan_to_num(np.fmin(S.ank_l, S.ank_r), nan=-1.0) >= JUMP_MIN_H) & \
              (np.nan_to_num(np.fmax(S.ank_l, S.ank_r), nan=-1.0) >= JUMP_MAX_H)
    jumps = []
    for a, b in _episodes(both_up, fps, 0.06, 0.12):
        x0 = np.nanmedian(S.ank_x[max(0, a - 4):a + 1])
        x1 = np.nanmedian(S.ank_x[b:min(len(S.t), b + 5)])
        if np.isnan(x0) or np.isnan(x1):
            continue
        disp = abs(x1 - x0) / S.H
        jumps.append(dict(a=a, b=b, disp=disp, x_mid=(x0 + x1) / 2.0))
    used: set[int] = set()
    cands: list[dict] = []
    ambiguous: list[dict] = []
    for fa, fb in floors:
        k = fa + int(np.nanargmin(np.where(np.isnan(S.sh_h[fa:fb + 1]), 9, S.sh_h[fa:fb + 1])))
        tf, tend = float(S.t[k]), float(S.t[fb])
        jm = None
        for ji, j in enumerate(jumps):
            tj = float(S.t[j["a"]])
            if ji in used or j["disp"] < JUMP_MIN_DISP:
                continue
            if tend - 0.3 <= tj <= tend + BURPEE_PAIR_WINDOW:
                jm = ji
                break
        if jm is not None:
            used.add(jm)
            j = jumps[jm]
            cands.append(dict(type="bar_facing_burpee", t=tf, s=1.0, kind="floor+jump",
                              t0=tf - 2.6, t1=float(S.t[j["b"]]) + 1.5, x_mid=j["x_mid"]))
            continue
        # step-over: clear horizontal travel after the floor phase, no flight
        e = S.idx(tend + 3.0)
        xs = S.ank_x
        x_before = np.nanmedian(xs[max(0, k - 8):k + 1])
        x_after = np.nanmedian(xs[S.idx(tend + 0.8):e + 1]) if e > S.idx(tend + 0.8) else np.nan
        if not np.isnan(x_before) and not np.isnan(x_after) and \
                abs(x_after - x_before) / S.H >= STEP_DISP:
            cands.append(dict(type="bar_facing_burpee", t=tf, s=0.7, kind="floor+step",
                              t0=tf - 2.6, t1=tend + 3.5,
                              x_mid=float((x_before + x_after) / 2)))
        else:
            ambiguous.append(dict(t=tf, why="floor_without_crossing"))
    for ji, j in enumerate(jumps):
        if ji in used or j["disp"] < JUMP_MIN_DISP:
            continue
        ta = float(S.t[j["a"]])
        lo = S.idx(ta - 3.0)
        seg = S.sh_h[lo:j["a"] + 1]
        if seg.size and np.nanmin(np.where(np.isnan(seg), 9, seg)) <= 0.62:
            cands.append(dict(type="bar_facing_burpee", t=ta - 1.0, s=0.5, kind="jump_only",
                              t0=ta - 3.0, t1=float(S.t[j["b"]]) + 1.5, x_mid=j["x_mid"]))
    cands.sort(key=lambda c: c["t"])
    return cands, ambiguous


def find_thruster_candidates(S: Series) -> list[dict]:
    hd = np.nan_to_num(S.hip_depth, nan=-0.5)
    peaks, _ = find_peaks(hd, prominence=THR_PROM, height=THR_MIN_PEAK,
                          distance=max(1, int(THR_MIN_GAP * S.fps)))
    out = []
    for p in peaks:
        tb = float(S.t[p])
        a, b = S.idx(tb - 0.7), S.idx(tb + 0.2)
        rack_seg = S.wr_rel[a:b + 1]
        rack = rack_seg.size > 0 and np.isfinite(rack_seg).any() and \
            float(np.nanmedian(rack_seg)) >= RACK_REL
        o_seg = S.wr_rel[p:S.idx(tb + 1.8) + 1]
        over = o_seg.size > 0 and np.isfinite(o_seg).any() and \
            float(np.nanmax(o_seg)) >= OVERHEAD_REL
        if not (rack or over):
            continue                      # hands on knees / sitting / bar set-down
        s = 1.0 if (rack and over) else (0.8 if over else 0.55)
        out.append(dict(type="thruster", t=tb, s=s, kind="squat+bar",
                        t0=tb - 2.2, t1=tb + 2.4, rack=bool(rack), over=bool(over)))
    return out
