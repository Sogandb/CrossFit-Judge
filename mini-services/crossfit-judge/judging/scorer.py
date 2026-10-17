"""Final scoring + claimed-score reconciliation (confirm-or-flag policy)."""
from __future__ import annotations

from typing import Optional

REP_TOLERANCE = 0      # exact match required for "تطبیق کامل"
REP_TOLERANCE_MINOR = 2  # ≤ 2 reps off → minor discrepancy note
TIME_TOLERANCE_SEC = 5.0


def reconcile(sequencer_summary: dict, claimed: Optional[dict]) -> dict:
    """Compare system results against the athlete's declared score.

    claimed: {"reps": int|None, "time_sec": float|None, "capped": bool}
    """
    out = {
        "claimed_reps": None, "claimed_time_sec": None, "claimed_capped": None,
        "counted_reps": sequencer_summary["total_credited"],
        "reps_delta": None, "time_delta_sec": None,
        "verdict": "no_claim",
        "verdict_fa": "امتیازی ادعا نشده بود",
        "verdict_en": "No score was claimed",
        "review_recommended": False,
    }
    if not claimed:
        return out
    out["claimed_reps"] = claimed.get("reps")
    out["claimed_time_sec"] = claimed.get("time_sec")
    out["claimed_capped"] = claimed.get("capped")

    counted = sequencer_summary["total_credited"]
    if out["claimed_reps"] is not None:
        out["reps_delta"] = counted - int(out["claimed_reps"])
        d = out["reps_delta"]
        if d == REP_TOLERANCE:
            out["verdict"] = "match"
            out["verdict_fa"] = "تطبیق کامل — امتیاز ادعایی با شمارش سیستم همخوانی دارد"
            out["verdict_en"] = "Exact match — the claimed score agrees with the system count"
        elif abs(d) <= REP_TOLERANCE_MINOR:
            out["verdict"] = "minor_diff"
            out["verdict_fa"] = f"اختلاف جزئی ({d:+d} رپ) — بازبینی سبک توصیه می‌شود"
            out["verdict_en"] = f"Minor discrepancy ({d:+d} reps) — light review recommended"
            out["review_recommended"] = True
        else:
            out["verdict"] = "diff"
            out["verdict_fa"] = f"اختلاف محسوس ({d:+d} رپ) — بازبینی کامل توصیه می‌شود"
            out["verdict_en"] = f"Significant discrepancy ({d:+d} reps) — full review recommended"
            out["review_recommended"] = True

    # time check only meaningful when both sides finished under the cap
    if sequencer_summary["finished"] and claimed.get("time_sec") is not None \
            and not claimed.get("capped"):
        td = sequencer_summary["finish_time_sec"] - float(claimed["time_sec"])
        out["time_delta_sec"] = round(td, 1)
        if abs(td) > TIME_TOLERANCE_SEC and out["verdict"] == "match":
            out["verdict"] = "time_diff"
            out["verdict_fa"] = (f"تعداد رپ‌ها همخوان است اما زمان "
                                 f"({td:+.0f} ثانیه) متفاوت است — بازبینی توصیه می‌شود")
            out["verdict_en"] = (f"Rep count matches but the finish time "
                                 f"({td:+.0f}s) differs — review recommended")
            out["review_recommended"] = True
    elif sequencer_summary["capped"] and not claimed.get("capped"):
        if out["verdict"] == "match":
            out["verdict"] = "status_diff"
            out["verdict_fa"] = ("ورزشکار ادعای اتمام زیر زمان داشته اما سیستم "
                                 "وادی را کامل‌شده تشخیص نداد — بازبینی توصیه می‌شود")
            out["verdict_en"] = ("The athlete claimed a finish under the cap but the "
                                 "system did not detect workout completion — review recommended")
            out["review_recommended"] = True
    return out


def score_display(summary: dict) -> dict:
    """Human-friendly score line (bilingual) + overall analysis confidence."""
    conf = summary.get("analysis_confidence")
    conf_pct = f"{int(round(conf * 100))}%" if conf is not None else None
    if summary["finished"]:
        ft = summary["finish_time_sec"] or 0
        mm, ss = int(ft // 60), int(ft) % 60
        return {
            "score": f"{mm:02d}:{ss:02d}",
            "score_fa": f"زمان پایان: {mm:02d}:{ss:02d}",
            "score_en": f"Finish time: {mm:02d}:{ss:02d}",
            "status_fa": "وادی کامل شد",
            "status_en": "Finished — the time is the score",
            "confidence": conf,
            "confidence_fa": (f"میانگین اطمینان تصمیم‌ها: {conf_pct}"
                             if conf_pct else None),
            "confidence_en": (f"Average decision confidence: {conf_pct}"
                              if conf_pct else None),
        }
    total = summary["total_credited"]
    out = {
        "score": f"{total} reps",
        "confidence": conf,
        "confidence_fa": (f"میانگین اطمینان تصمیم‌ها: {conf_pct}"
                         if conf_pct else None),
        "confidence_en": (f"Average decision confidence: {conf_pct}"
                          if conf_pct else None),
    }
    if summary.get("cap_enforced", True):
        out.update({
            "score_fa": f"{total} رپ در زمان مجاز",
            "score_en": f"{total} reps within the time cap",
            "status_fa": "در زمان مجاز کامل نشد (کپ)",
            "status_en": "Not completed within the time cap (capped)",
        })
    else:
        out.update({
            "score_fa": f"{total} رپ تا پایان ویدیو",
            "score_en": f"{total} reps by the end of the video",
            "status_fa": "وادی تا پایان ویدیو کامل نشد (شروع واد پیدا نشد؛ محدودیت زمانی اعمال نشد)",
            "status_en": ("The workout was not completed by the end of the video "
                          "(start not detected; the time cap was not enforced)"),
        })
    return out


def fmt_clock(seconds) -> str:
    """mm:ss with FLOOR seconds (never rounds 59.6 s up to '01:60')."""
    if seconds is None:
        return "—"
    t = max(0, int(seconds))
    return f"{t // 60:02d}:{t % 60:02d}"


def final_overview(summary: dict, t_start: float, cap: float, cap_enforced: bool,
                   last_frame_t: float, events: list[dict]) -> dict:
    """THE headline the athlete sees: how many reps and at what time.

    The clock runs from the VIDEO START (t_start = 0 by default) and STOPS at
    whichever comes first:
      * the last rep of the WOD (finished)  -> time of the 126th rep
      * the time cap (10:00)                -> athlete was still working
      * the last credited attempt           -> athlete stopped early / video ended
    """
    slots = [e for e in events if e.get("kind") == "slot"]
    last_slot_t = max((e["t_end"] for e in slots), default=None)
    last_rep_rel = None if last_slot_t is None else max(0.0, last_slot_t - t_start)
    elapsed_video = max(0.0, last_frame_t - t_start)
    if summary["finished"]:
        stop, kind = summary["finish_time_sec"], "finish"
    elif cap and cap_enforced and (summary.get("cap_hit") or elapsed_video >= cap - 1.0):
        stop, kind = float(cap), "cap"
    else:
        stop, kind = last_rep_rel, "last_rep"
    credited = summary["total_credited"]
    kind_fa = {"finish": "زمان پایان واد", "cap": "تایم‌کپ", "last_rep": "زمان آخرین تکرار"}[kind]
    kind_en = {"finish": "Finish time", "cap": "Time cap reached", "last_rep": "Time of the last rep"}[kind]
    return {
        "reps_counted": credited,
        "no_reps": summary["total_no_reps"],
        "attempts": summary["total_consumed"],
        "prescribed": summary["total_prescribed"],
        "stop_time_sec": None if stop is None else round(float(stop), 2),
        "stop_time_text": fmt_clock(stop),
        "stop_kind": kind,
        "stop_kind_fa": kind_fa,
        "stop_kind_en": kind_en,
        "clock_start_sec": round(t_start, 2),
        "line_fa": f"{credited} رپ معتبر از {summary['total_prescribed']} — {kind_fa}: {fmt_clock(stop)}",
        "line_en": f"{credited} valid reps of {summary['total_prescribed']} — {kind_en}: {fmt_clock(stop)}",
    }
