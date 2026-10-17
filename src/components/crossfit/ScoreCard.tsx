"use client";

import { Trophy, Clock, CheckCircle2, XCircle, Layers } from "lucide-react";
import type { AnalysisResult } from "./types";
import { useLang } from "@/lib/i18n";

/** v1 ScoreCard — gradient hero panel with the final score. */

function fmtTime(seconds: number | null): string {
  if (seconds == null) return "—";
  const total = Math.floor(seconds);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

export function ScoreCard({ result }: { result: AnalysisResult }) {
  const { t, n } = useLang();
  const { summary, score_display, wod } = result;

  return (
    <div className="relative overflow-hidden rounded-2xl border border-edge bg-gradient-to-br from-panel-2 to-app p-6 sm:p-8">
      {/* glow */}
      <div className="absolute -top-20 -right-20 h-48 w-48 rounded-full bg-red-500/10 blur-3xl rtl:scale-x-[-1]" />

      <div className="relative flex flex-col sm:flex-row sm:items-center sm:justify-between gap-6">
        <div>
          <div className="flex flex-wrap items-center gap-2 mb-1">
            <p className="text-xs font-medium uppercase tracking-wider text-brand-fg">
              {t("res.finalScore")}
            </p>
            <span className="rounded bg-chip text-ink-2 px-1.5 py-0.5 text-[10px] font-bold uppercase">
              {t("res.forTime")}
            </span>
            {summary.finished ? (
              <span className="inline-flex items-center gap-1 rounded bg-emerald-500/15 text-emerald-500 dark:text-emerald-400 px-1.5 py-0.5 text-[10px] font-bold">
                <CheckCircle2 className="h-3 w-3" />
                {t("res.finished")}
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 rounded bg-red-500/15 text-brand-fg px-1.5 py-0.5 text-[10px] font-bold">
                <XCircle className="h-3 w-3" />
                {t("res.capStatus")}
              </span>
            )}
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-5xl sm:text-6xl font-bold tabular-nums text-ink">
              {n(score_display.score)}
            </span>
          </div>
          <p className="mt-2 text-sm text-ink-3">
            {wod.name_en ?? wod.name_fa}
          </p>
          <p className="mt-1 text-xs text-ink-4">
            <Layers className="inline h-3 w-3 me-1" />
            {n(summary.total_credited)} / {n(summary.total_prescribed)} {t("res.ofReps")}
          </p>
        </div>

        <div className="flex gap-6 sm:gap-8">
          <div className="text-center">
            <div className="flex h-12 w-12 mx-auto items-center justify-center rounded-xl bg-emerald-500/10 mb-2">
              <Trophy className="h-6 w-6 text-emerald-500 dark:text-emerald-400" />
            </div>
            <p className="text-2xl font-bold tabular-nums text-ink">
              {n(summary.total_credited)}
            </p>
            <p className="text-xs text-ink-3">{t("res.validReps")}</p>
          </div>
          <div className="text-center">
            <div className="flex h-12 w-12 mx-auto items-center justify-center rounded-xl bg-chip mb-2">
              <Clock className="h-6 w-6 text-ink-3" />
            </div>
            <p className="text-2xl font-bold tabular-nums text-ink">
              {summary.finished
                ? n(fmtTime(summary.finish_time_sec))
                : result.overview?.stop_time_sec != null
                  ? n(fmtTime(result.overview.stop_time_sec))
                  : "—"}
            </p>
            <p className="text-xs text-ink-3">
              {summary.finished ? t("res.time") : t("res.capStatus")}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
