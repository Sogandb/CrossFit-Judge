"use client";

import { Loader2, CheckCircle2, XCircle } from "lucide-react";
import type { JobInfo } from "./types";
import { useLang } from "@/lib/i18n";
import { cn } from "@/lib/utils";

/** Sidebar "Recent Analyses" — compact v1-styled list. */
export function HistoryList({ jobs, onSelect, activeId }: {
  jobs: JobInfo[];
  onSelect: (id: string) => void;
  activeId?: string;
}) {
  const { t, dateTime, lang } = useLang();

  return (
    <div className="space-y-2">
      <p className="text-[11px] font-bold uppercase tracking-wider text-ink-3">
        {t("side.recent")}
      </p>
      {jobs.length === 0 ? (
        <div className="rounded-lg border border-dashed border-edge bg-panel-2/20 p-3 text-center">
          <p className="text-xs text-ink-4">{t("side.recentEmpty")}</p>
        </div>
      ) : (
        <ul className="space-y-1.5 max-h-72 overflow-y-auto scroll-slim pe-0.5">
          {jobs.map((j) => (
            <li key={j.id}>
              <button
                onClick={() => onSelect(j.id)}
                className={cn(
                  "w-full flex items-center justify-between gap-2.5 rounded-lg border px-2.5 py-2 text-start transition-colors",
                  activeId === j.id
                    ? "border-brand bg-brand/10"
                    : "border-edge bg-panel hover:border-edge-2",
                )}
              >
                <div className="min-w-0">
                  <div className="truncate text-xs font-medium text-ink">
                    {j.athlete_name || j.id}
                  </div>
                  <div className="text-[10px] text-ink-4">{dateTime(j.created_at)}</div>
                </div>
                {j.status === "done" ? (
                  <span className="flex items-center gap-1 text-[10px] font-bold text-emerald-500 dark:text-emerald-400 shrink-0">
                    <CheckCircle2 className="h-3 w-3" />
                    {lang === "fa" ? "تکمیل" : "Done"}
                  </span>
                ) : j.status === "failed" ? (
                  <span className="flex items-center gap-1 text-[10px] font-bold text-brand-fg shrink-0">
                    <XCircle className="h-3 w-3" />
                    {lang === "fa" ? "خطا" : "Failed"}
                  </span>
                ) : (
                  <span className="flex items-center gap-1 text-[10px] text-ink-3 shrink-0">
                    <Loader2 className="h-3 w-3 animate-spin" />
                    {lang === "fa" ? j.stage_fa : j.stage_en}
                  </span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
