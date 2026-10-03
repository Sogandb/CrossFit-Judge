"use client";

import { CheckCircle2, XCircle, ListOrdered, Clock } from "lucide-react";
import type { AnalysisResult } from "./types";
import { useLang } from "@/lib/i18n";

/** v1 StatsGrid — the four KPI cards. */

export function StatsGrid({ result }: { result: AnalysisResult }) {
  const { t, n } = useLang();
  const { summary } = result;

  const noRepCount = result.events.filter(
    (e) => e.outcome === "no_rep" && !e.post_cap,
  ).length;

  const stats = [
    {
      label: t("res.validReps"),
      value: n(summary.total_credited),
      icon: CheckCircle2,
      color: "text-emerald-500 dark:text-emerald-400",
      bg: "bg-emerald-500/10",
    },
    {
      label: t("res.noReps"),
      value: n(noRepCount),
      icon: XCircle,
      color: "text-brand-fg",
      bg: "bg-red-500/10",
    },
    {
      label: t("res.prescribed"),
      value: n(summary.total_prescribed),
      icon: ListOrdered,
      color: "text-orange-400 dark:text-orange-400",
      bg: "bg-orange-500/10",
    },
    {
      label: summary.finished ? t("res.time") : t("res.capStatus"),
      value: summary.finished
        ? n(fmtTime(summary.finish_time_sec))
        : t("res.capStatus"),
      icon: Clock,
      color: "text-ink-2",
      bg: "bg-chip",
    },
  ];

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      {stats.map((s) => (
        <div
          key={s.label}
          className="rounded-xl border border-edge bg-panel p-4"
        >
          <div className={`flex h-9 w-9 items-center justify-center rounded-lg ${s.bg} mb-3`}>
            <s.icon className={`h-4 w-4 ${s.color}`} />
          </div>
          <p className="text-2xl font-bold tabular-nums text-ink">{s.value}</p>
          <p className="text-xs text-ink-3 mt-0.5">{s.label}</p>
        </div>
      ))}
    </div>
  );
}

function fmtTime(seconds: number | null): string {
  if (seconds == null) return "—";
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}
