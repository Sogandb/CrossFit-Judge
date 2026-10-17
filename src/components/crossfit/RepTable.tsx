"use client";

import { useMemo } from "react";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  CheckCircle2, XCircle, AlertTriangle, Flag, HelpCircle, MinusCircle,
} from "lucide-react";
import type { AnalysisResult, LadderEntry } from "./types";
import { MOVEMENT_LABELS, useLang } from "@/lib/i18n";
import { cn } from "@/lib/utils";

/**
 * THE WOD COUNT — the user's exact table (2026-10-09 spec):
 *
 *   1..18   thruster    19..36  burpee
 *   37..51  thruster    52..66  burpee
 *   67..78  thruster    79..90  burpee
 *   91..99  thruster    100..108 burpee
 *   109..114 thruster   115..120 burpee
 *   121..123 thruster   124..126 burpee
 *
 * One row per prescribed rep number, always in this exact order:
 *   # → movement → verdict (rep / no-rep / not-detected / not-reached)
 *   → confidence → time → reason.
 * No round grouping — the count advances strictly by the global counter.
 * The 126-cell strip above the table shows the whole WOD at a glance.
 */

function formatTs(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toFixed(1).padStart(4, "0")}`;
}

function verdictClasses(v: LadderEntry["verdict"]) {
  switch (v) {
    case "rep":
      return "bg-emerald-500/70 hover:bg-emerald-500";
    case "no_rep":
      return "bg-rose-500/70 hover:bg-rose-500";
    case "not_detected":
      return "bg-amber-500/50 hover:bg-amber-500/70";
    default:
      return "bg-edge-2 hover:bg-edge-3";
  }
}

interface Props {
  result: AnalysisResult;
  selectedRep: number | null;
  onSeek: (row: LadderEntry) => void;
}

export function RepTable({ result, selectedRep, onSeek }: Props) {
  const { t, n, lang } = useLang();
  const summary = result.summary;
  const ladder = useMemo(() => summary.ladder ?? [], [summary.ladder]);

  if (ladder.length === 0) {
    return (
      <div className="rounded-xl border border-edge bg-panel p-8 text-center">
        <AlertTriangle className="h-8 w-8 text-ink-4 mx-auto mb-3" />
        <p className="text-sm text-ink-2">{t("res.noEvents")}</p>
        <p className="text-xs text-ink-4 mt-1">{t("res.noEventsHint")}</p>
      </div>
    );
  }

  const counted = ladder.filter((r) => r.verdict === "rep" || r.verdict === "no_rep").length;

  return (
    <div className="rounded-xl border border-edge bg-panel overflow-hidden">
      <div className="px-4 py-3 border-b border-edge">
        <h3 className="text-sm font-semibold text-ink">{t("res.ladderTitle")}</h3>
        <p className="text-xs text-ink-3 mt-0.5">
          <span className="tabular-nums">
            {t("res.ladderCountedPrefix")} {n(counted)} / {n(ladder.length)}
          </span>
          {result.summary.post_cap_events > 0 && (
            <span>{" · "}{t("res.postCapNotePrefix")} {n(result.summary.post_cap_events)}</span>
          )}
          {result.summary.noise_events > 0 && (
            <span>{" · "}{t("res.noiseNotePrefix")} {n(result.summary.noise_events)}</span>
          )}
        </p>
      </div>

      {/* ---- 126-cell at-a-glance strip ---- */}
      <div className="px-4 pt-3 pb-1 border-b border-edge/60">
        <div className="flex flex-wrap gap-[3px]">
          {ladder.map((row) => (
            <button
              key={row.rep_no}
              type="button"
              disabled={row.verdict === "not_reached"}
              onClick={() => row.t_start != null && onSeek(row)}
              title={
                row.verdict === "not_detected" || row.verdict === "not_reached"
                  ? `${n(row.rep_no)} · ${MOVEMENT_LABELS[row.movement] ?? row.movement} · ${t(`res.verdict_${row.verdict}`)}`
                  : `${n(row.rep_no)} · ${MOVEMENT_LABELS[row.movement] ?? row.movement} · ${t(`res.verdict_${row.verdict}`)}${row.t_start != null ? ` · ${formatTs(row.t_start)}` : ""}`
              }
              className={cn(
                "h-4 w-4 rounded-[3px] transition-colors",
                verdictClasses(row.verdict),
                selectedRep === row.rep_no && "ring-2 ring-brand-fg ring-offset-1 ring-offset-panel",
                row.verdict === "not_reached" && "cursor-default opacity-50",
              )}
              aria-label={`Rep ${row.rep_no}`}
            />
          ))}
        </div>
        <div className="mt-2 mb-1 flex flex-wrap gap-x-4 gap-y-1 text-[10px] text-ink-4">
          <span className="inline-flex items-center gap-1">
            <i className="h-2.5 w-2.5 rounded-[2px] bg-emerald-500/70 inline-block" />
            {t("res.verdict_rep")}
          </span>
          <span className="inline-flex items-center gap-1">
            <i className="h-2.5 w-2.5 rounded-[2px] bg-rose-500/70 inline-block" />
            {t("res.verdict_no_rep")}
          </span>
          <span className="inline-flex items-center gap-1">
            <i className="h-2.5 w-2.5 rounded-[2px] bg-amber-500/50 inline-block" />
            {t("res.verdict_not_detected")}
          </span>
          <span className="inline-flex items-center gap-1">
            <i className="h-2.5 w-2.5 rounded-[2px] bg-edge-3 inline-block" />
            {t("res.verdict_not_reached")}
          </span>
        </div>
      </div>

      {/* ---- the full ladder table: 1..126, exact order ---- */}
      <div className="max-h-[420px] overflow-y-auto scroll-slim">
        <Table>
          <TableHeader className="sticky top-0 bg-panel z-10">
            <TableRow className="border-edge hover:bg-transparent">
              <TableHead className="text-muted-foreground text-xs">#</TableHead>
              <TableHead className="text-muted-foreground text-xs">{t("res.movement")}</TableHead>
              <TableHead className="text-muted-foreground text-xs">{t("res.verdict")}</TableHead>
              <TableHead className="text-muted-foreground text-xs">{t("res.confidence")}</TableHead>
              <TableHead className="text-muted-foreground text-xs">{t("res.time")}</TableHead>
              <TableHead className="text-muted-foreground text-xs">{t("res.reason")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {ladder.map((row) => {
              const isNoRep = row.verdict === "no_rep";
              const isDetected = row.verdict === "rep" || row.verdict === "no_rep";
              const notes = (lang === "fa" ? row.notes : row.notes_en) ?? [];
              return (
                <TableRow
                  key={row.rep_no}
                  onClick={() => row.t_start != null && onSeek(row)}
                  className={cn(
                    "border-edge/70 transition-colors",
                    row.t_start != null && "cursor-pointer",
                    selectedRep === row.rep_no
                      ? "bg-brand/10"
                      : "hover:bg-edge/30",
                    !isDetected && "opacity-80",
                  )}
                >
                  <TableCell className="font-mono text-xs text-ink-3 tabular-nums">
                    {n(row.rep_no)}
                  </TableCell>
                  <TableCell className="text-xs text-ink-2">
                    {MOVEMENT_LABELS[row.movement] ?? row.movement}
                  </TableCell>
                  <TableCell>
                    {row.verdict === "rep" && (
                      <span className="inline-flex items-center gap-1.5 text-xs font-medium text-emerald-600 dark:text-emerald-400">
                        <CheckCircle2 className="h-3.5 w-3.5" />
                        {t("res.verdictGood")}
                      </span>
                    )}
                    {row.verdict === "no_rep" && (
                      <span className="inline-flex items-center gap-1.5 text-xs font-medium text-brand-fg">
                        <XCircle className="h-3.5 w-3.5" />
                        {t("res.verdictNoRep")}
                      </span>
                    )}
                    {row.verdict === "not_detected" && (
                      <span className="inline-flex items-center gap-1.5 text-xs font-medium text-amber-600 dark:text-amber-400">
                        <HelpCircle className="h-3.5 w-3.5" />
                        {t("res.verdict_not_detected")}
                      </span>
                    )}
                    {row.verdict === "not_reached" && (
                      <span className="inline-flex items-center gap-1.5 text-xs font-medium text-ink-4">
                        <MinusCircle className="h-3.5 w-3.5" />
                        {t("res.verdict_not_reached")}
                      </span>
                    )}
                  </TableCell>
                  <TableCell>
                    {row.confidence != null ? (
                      <span
                        className={cn(
                          "inline-flex items-center rounded px-1.5 py-0.5 text-[11px] font-bold tabular-nums",
                          row.confidence_label === "high" || row.confidence >= 0.85
                            ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400"
                            : row.confidence >= 0.65
                              ? "bg-amber-500/15 text-amber-600 dark:text-amber-400"
                              : "bg-red-500/10 text-brand-fg",
                        )}
                        title={row.borderline ? t("res.borderlineHint") : undefined}
                      >
                        {n(Math.round(row.confidence * 100))}%
                      </span>
                    ) : (
                      <span className="text-ink-4">—</span>
                    )}
                  </TableCell>
                  <TableCell className="text-xs text-ink-3 font-mono tabular-nums">
                    {row.t_start != null ? formatTs(row.t_start) : "—"}
                  </TableCell>
                  <TableCell className="text-xs max-w-[240px]">
                    {isNoRep ? (
                      <span dir="auto" className="text-brand-fg/90 leading-5">{row.reason_fa}</span>
                    ) : row.verdict === "rep" ? (
                      notes.length > 0 ? (
                        <span className="text-ink-4 leading-5">{notes.join(" · ")}</span>
                      ) : row.review_flags?.length ? (
                        <span className="inline-flex items-center gap-1 text-amber-600 dark:text-amber-400">
                          <Flag className="h-3 w-3" />
                          {t("res.needReview")}
                        </span>
                      ) : (
                        <span className="text-ink-4">—</span>
                      )
                    ) : (
                      <span className="text-ink-4 leading-5">
                        {t(row.verdict === "not_detected"
                          ? "res.notDetectedHint" : "res.notReachedHint")}
                      </span>
                    )}
                    {row.verdict === "rep" && notes.length > 0 && row.review_flags?.length ? (
                      <span className="ms-1.5 inline-flex items-center gap-1 text-amber-600 dark:text-amber-400">
                        <Flag className="h-3 w-3" />
                        {t("res.needReview")}
                      </span>
                    ) : null}
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
