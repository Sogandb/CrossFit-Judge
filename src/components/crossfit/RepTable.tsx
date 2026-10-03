"use client";

import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { CheckCircle2, XCircle, AlertTriangle, Flag } from "lucide-react";
import type { AnalysisEvent } from "./types";
import { MOVEMENT_LABELS, useLang } from "@/lib/i18n";
import { cn } from "@/lib/utils";

/**
 * v1 RepTable — rep-by-rep breakdown.
 * The Reason column is ALWAYS PERSIAN (engine reason_fa); movement names are
 * always English. Clicking a row seeks the review video to that moment.
 */

function formatTs(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toFixed(1).padStart(4, "0")}`;
}

interface Props {
  events: AnalysisEvent[];
  selectedIdx: number | null;
  onSeek: (ev: AnalysisEvent, idx: number) => void;
}

export function RepTable({ events, selectedIdx, onSeek }: Props) {
  const { t, n, lang } = useLang();

  if (events.length === 0) {
    return (
      <div className="rounded-xl border border-edge bg-panel p-8 text-center">
        <AlertTriangle className="h-8 w-8 text-ink-4 mx-auto mb-3" />
        <p className="text-sm text-ink-2">{t("res.noEvents")}</p>
        <p className="text-xs text-ink-4 mt-1">{t("res.noEventsHint")}</p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-edge bg-panel overflow-hidden">
      <div className="px-4 py-3 border-b border-edge">
        <h3 className="text-sm font-semibold text-ink">{t("res.repTable")}</h3>
        <p className="text-xs text-ink-3 mt-0.5">
          {n(events.length)} {t("res.attempts")} · {t("res.reasonInPersian")}
        </p>
      </div>
      <div className="max-h-[420px] overflow-y-auto scroll-slim">
        <Table>
          <TableHeader>
            <TableRow className="border-edge hover:bg-transparent">
              <TableHead className="text-muted-foreground text-xs">#</TableHead>
              <TableHead className="text-muted-foreground text-xs">{t("res.verdict")}</TableHead>
              <TableHead className="text-muted-foreground text-xs">{t("res.movement")}</TableHead>
              <TableHead className="text-muted-foreground text-xs">{t("res.time")}</TableHead>
              <TableHead className="text-muted-foreground text-xs">{t("res.round")}</TableHead>
              <TableHead className="text-muted-foreground text-xs">{t("res.reason")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {events.map((ev, i) => {
              const isNoRep = ev.outcome === "no_rep";
              const reason = ev.reason_fa; // ALWAYS Persian (product rule)
              const notes = (lang === "fa" ? ev.notes : ev.notes_en) ?? [];
              return (
                <TableRow
                  key={i}
                  onClick={() => onSeek(ev, i)}
                  className={cn(
                    "border-edge/70 cursor-pointer transition-colors",
                    selectedIdx === i
                      ? "bg-brand/10"
                      : "hover:bg-edge/30",
                  )}
                >
                  <TableCell className="font-mono text-xs text-ink-3 tabular-nums">
                    {n(i + 1)}
                  </TableCell>
                  <TableCell>
                    {isNoRep ? (
                      <span className="inline-flex items-center gap-1.5 text-xs font-medium text-brand-fg">
                        <XCircle className="h-3.5 w-3.5" />
                        {t("res.verdictNoRep")}
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1.5 text-xs font-medium text-emerald-600 dark:text-emerald-400">
                        <CheckCircle2 className="h-3.5 w-3.5" />
                        {t("res.verdictGood")}
                      </span>
                    )}
                  </TableCell>
                  <TableCell className="text-xs text-ink-2">
                    {MOVEMENT_LABELS[ev.movement] ?? ev.movement}
                  </TableCell>
                  <TableCell className="text-xs text-ink-3 font-mono tabular-nums">
                    {formatTs(ev.t_start)}
                  </TableCell>
                  <TableCell className="text-xs">
                    {ev.post_cap ? (
                      <span className="rounded bg-chip px-1.5 py-0.5 text-[10px] font-bold uppercase text-ink-3">
                        {t("res.postCap")}
                      </span>
                    ) : ev.block_idx != null ? (
                      <span className="text-ink-3 tabular-nums">{n(ev.block_idx + 1)}</span>
                    ) : (
                      <span className="text-ink-4">—</span>
                    )}
                  </TableCell>
                  <TableCell className="text-xs max-w-[240px]">
                    {isNoRep ? (
                      <span dir="auto" className="text-brand-fg/90 leading-5">{reason}</span>
                    ) : notes.length > 0 ? (
                      <span className="text-ink-4 leading-5">{notes.join(" · ")}</span>
                    ) : ev.review_flags?.length ? (
                      <span className="inline-flex items-center gap-1 text-amber-600 dark:text-amber-400">
                        <Flag className="h-3 w-3" />
                        {t("res.needReview")}
                      </span>
                    ) : (
                      <span className="text-ink-4">—</span>
                    )}
                    {!isNoRep && notes.length > 0 && ev.review_flags?.length > 0 && (
                      <span className="ms-1.5 inline-flex items-center gap-1 text-amber-600 dark:text-amber-400">
                        <Flag className="h-3 w-3" />
                        {t("res.needReview")}
                      </span>
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
