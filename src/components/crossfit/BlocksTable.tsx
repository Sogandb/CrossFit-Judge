"use client";

import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import type { AnalysisResult } from "./types";
import { MOVEMENT_LABELS, useLang } from "@/lib/i18n";
import { cn } from "@/lib/utils";

/** Round-by-round table — the 12 prescribed blocks of the ladder (v1 card
 * style). Under the strict rep-range model every block shows BOTH the
 * progression count (attempted slots — reps + no-reps) and the judged count
 * (credited): 18/18 attempted with 16 credited = the athlete moved through
 * the block, 2 of its reps were no-reps. */
export function BlocksTable({ result }: { result: AnalysisResult }) {
  const { t, n, lang } = useLang();

  return (
    <div className="rounded-xl border border-edge bg-panel overflow-hidden">
      <div className="px-4 py-3 border-b border-edge">
        <h3 className="text-sm font-semibold text-ink">{t("res.roundByRound")}</h3>
      </div>
      <div className="max-h-[420px] overflow-y-auto scroll-slim">
        <Table>
          <TableHeader>
            <TableRow className="border-edge hover:bg-transparent">
              <TableHead className="text-muted-foreground text-xs">{t("res.round")}</TableHead>
              <TableHead className="text-muted-foreground text-xs">{t("res.movement")}</TableHead>
              <TableHead className="text-muted-foreground text-xs">{t("res.repsRange")}</TableHead>
              <TableHead className="text-muted-foreground text-xs">{t("res.prescribed")}</TableHead>
              <TableHead className="text-muted-foreground text-xs">{t("res.attempted")}</TableHead>
              <TableHead className="text-muted-foreground text-xs">{t("res.credited")}</TableHead>
              <TableHead className="text-muted-foreground text-xs">{t("res.noReps")}</TableHead>
              <TableHead className="text-muted-foreground text-xs">{t("res.status")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {result.summary.blocks.map((b) => (
              <TableRow key={b.idx} className="border-edge/70 hover:bg-edge/30">
                <TableCell className="font-mono text-xs text-ink-3 tabular-nums">
                  {n(b.idx + 1)}
                </TableCell>
                <TableCell className="text-xs text-ink-2">
                  {MOVEMENT_LABELS[b.movement] ?? b.movement_en ?? b.movement}
                </TableCell>
                <TableCell className="text-xs text-ink-3 font-mono tabular-nums">
                  {b.rep_start != null && b.rep_end != null
                    ? `${n(b.rep_start)}–${n(b.rep_end)}`
                    : "—"}
                </TableCell>
                <TableCell className="text-xs text-ink-3 tabular-nums">{n(b.reps)}</TableCell>
                <TableCell className="text-xs tabular-nums">
                  <span className={cn(
                    "font-mono",
                    b.attempts >= b.reps ? "text-emerald-600 dark:text-emerald-400" : "text-ink",
                  )}>
                    {n(b.attempts)}
                  </span>
                </TableCell>
                <TableCell>
                  <span
                    className={cn(
                      "text-xs font-bold tabular-nums",
                      b.credited >= b.reps
                        ? "text-emerald-600 dark:text-emerald-400"
                        : b.credited > 0
                          ? "text-ink"
                          : "text-ink-4",
                    )}
                  >
                    {n(b.credited)}
                  </span>
                </TableCell>
                <TableCell className="text-xs tabular-nums">
                  {b.no_reps > 0 ? (
                    <span className="text-amber-600 dark:text-amber-400 font-mono">
                      {n(b.no_reps)}
                    </span>
                  ) : (
                    <span className="text-ink-4 font-mono">0</span>
                  )}
                </TableCell>
                <TableCell>
                  <span
                    className={cn(
                      "inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-bold uppercase",
                      b.complete && b.credited >= b.reps
                        ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400"
                        : b.complete
                          ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
                          : b.attempts > 0
                            ? "bg-amber-500/15 text-amber-600 dark:text-amber-400"
                            : "bg-chip text-ink-3",
                    )}
                  >
                    {lang === "fa" ? b.status_fa : b.status_en}
                  </span>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
