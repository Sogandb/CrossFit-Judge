"use client";

import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import type { AnalysisResult } from "./types";
import { MOVEMENT_LABELS, useLang } from "@/lib/i18n";
import { cn } from "@/lib/utils";

/** Round-by-round table — the 12 prescribed blocks of the ladder (v1 card style). */
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
              <TableHead className="text-muted-foreground text-xs">{t("res.prescribed")}</TableHead>
              <TableHead className="text-muted-foreground text-xs">{t("res.credited")}</TableHead>
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
                <TableCell className="text-xs text-ink-3 tabular-nums">{n(b.reps)}</TableCell>
                <TableCell>
                  <span
                    className={cn(
                      "text-xs font-bold tabular-nums",
                      b.complete
                        ? "text-emerald-600 dark:text-emerald-400"
                        : "text-ink",
                    )}
                  >
                    {n(b.credited)}
                  </span>
                </TableCell>
                <TableCell>
                  <span
                    className={cn(
                      "inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-bold uppercase",
                      b.complete
                        ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400"
                        : b.credited > 0
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
