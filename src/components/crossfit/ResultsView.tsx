"use client";

import { useMemo, useRef, useState } from "react";
import {
  ClipboardCheck, ShieldAlert, Download, Flag,
} from "lucide-react";
import type { AnalysisResult, AnalysisEvent } from "./types";
import { ScoreCard } from "./ScoreCard";
import { StatsGrid } from "./StatsGrid";
import { BlocksTable } from "./BlocksTable";
import { RepTable } from "./RepTable";
import { AnnotatedVideoPlayer } from "./AnnotatedVideoPlayer";
import { MOVEMENT_LABELS, useLang } from "@/lib/i18n";
import { cn } from "@/lib/utils";

interface Props {
  jobId: string;
  createdAt: number;
  athleteName?: string;
  result: AnalysisResult;
}

export function ResultsView({ jobId, createdAt, athleteName, result }: Props) {
  const { t, n, clock, dateTime, lang } = useLang();
  const videoRef = useRef<HTMLVideoElement>(null);
  const [selectedEvent, setSelectedEvent] = useState<number | null>(null);

  const events = useMemo(
    () => [...result.events].sort((a, b) => a.t_start - b.t_start),
    [result.events],
  );
  const reviewFlagged = events.filter((e) => e.review_flags?.length);
  const rec = result.reconciliation;

  const seekTo = (ev: AnalysisEvent, idx: number) => {
    setSelectedEvent(idx);
    if (videoRef.current) {
      videoRef.current.currentTime = Math.max(0, ev.t_start - 0.5);
      videoRef.current.play().catch(() => undefined);
    }
  };

  const startLabel =
    result.start_detection.method === "beep" ? t("res.startBeep")
      : result.start_detection.method === "manual" ? t("res.startManual")
        : result.start_detection.method === "mock" ? t("res.startMock")
          : t("res.startVideo");

  const verdictTone =
    rec.verdict === "match"
      ? "border-emerald-500/30 bg-emerald-500/5"
      : rec.review_recommended
        ? "border-amber-500/40 bg-amber-500/5"
        : "border-edge bg-panel";

  return (
    <div className="space-y-6">
      {/* meta strip */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-ink-3">
        {athleteName && (
          <span>
            {t("res.athlete")}: <span className="font-medium text-ink-2">{athleteName}</span>
          </span>
        )}
        <span>
          {t("res.analysisId")}: <span className="font-mono text-ink-4">{jobId}</span>
        </span>
        <span>{dateTime(createdAt)}</span>
        <span className="flex flex-wrap items-center gap-1">
          {t("res.startDetection")}: <span className="text-ink-2">{startLabel}</span>
          <span className="text-ink-4">·</span>
          {t("res.startAt")} <span className="tabular-nums text-ink-2">{clock(result.start_detection.t_start_sec)}</span>
        </span>
      </div>

      <ScoreCard result={result} />

      {/* claimed-score reconciliation */}
      <div className={`rounded-xl border p-4 ${verdictTone}`}>
        <div className="flex items-start gap-3">
          <ClipboardCheck className="mt-0.5 h-5 w-5 shrink-0 text-ink-2" />
          <div className="flex-1 min-w-0">
            <div className="text-sm font-bold text-ink">{t("res.recon")}</div>
            <p className="mt-1 text-sm leading-6 text-ink-2">
              {lang === "fa" ? rec.verdict_fa : rec.verdict_en}
            </p>
            <div className="mt-2 flex flex-wrap gap-2 text-[11px]">
              {rec.claimed_reps != null && (
                <span className="rounded-full bg-chip px-2.5 py-1 text-ink-2">
                  {t("res.claimedReps")}: <span className="tabular-nums">{n(rec.claimed_reps)}</span> {t("res.ofReps")}
                </span>
              )}
              <span className="rounded-full bg-chip px-2.5 py-1 text-ink-2">
                {t("res.systemCount")}: <span className="tabular-nums">{n(rec.counted_reps)}</span> {t("res.ofReps")}
              </span>
              {rec.claimed_time_sec != null && (
                <span className="rounded-full bg-chip px-2.5 py-1 text-ink-2">
                  {t("res.claimedTime")}: <span className="tabular-nums">{clock(rec.claimed_time_sec)}</span>
                </span>
              )}
              {result.summary.finish_time_sec != null && (
                <span className="rounded-full bg-chip px-2.5 py-1 text-ink-2">
                  {t("res.systemTime")}: <span className="tabular-nums">{clock(result.summary.finish_time_sec)}</span>
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      <StatsGrid result={result} />

      {/* per-movement breakdown (v1) */}
      {Object.keys(result.summary.per_movement).length > 1 && (
        <div className="rounded-xl border border-edge bg-panel p-4">
          <h3 className="text-sm font-semibold text-ink mb-3">{t("res.perMovement")}</h3>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {Object.entries(result.summary.per_movement).map(([move, m]) => (
              <div key={move} className="rounded-lg bg-chip/50 p-3">
                <p className="text-xs font-medium text-ink-2 mb-2">
                  {MOVEMENT_LABELS[move] ?? move}
                </p>
                <div className="flex items-baseline gap-3">
                  <span className="text-xl font-bold tabular-nums text-emerald-500 dark:text-emerald-400">
                    {n(m.credited)}
                  </span>
                  <span className="text-xs text-ink-4">
                    / {n(m.prescribed)} {t("res.ofReps")}
                  </span>
                </div>
                {m.no_reps > 0 && (
                  <p className="text-xs text-brand-fg mt-1 tabular-nums">
                    {n(m.no_reps)} {t("res.noRepShort")}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* review video + rep table (v1 two-column grid) */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-start">
        {result.review_video ? (
          <AnnotatedVideoPlayer jobId={jobId} videoRef={videoRef} />
        ) : (
          <div className="hidden lg:block" />
        )}
        <RepTable events={events} selectedIdx={selectedEvent} onSeek={seekTo} />
      </div>

      <BlocksTable result={result} />

      {/* flagged for human review */}
      {(result.warnings.length > 0 || reviewFlagged.length > 0 ||
        result.sequencer_flags.length > 0) && (
        <div className="rounded-xl border border-amber-500/40 bg-amber-500/5 p-4">
          <h3 className="flex items-center gap-2 text-sm font-bold text-ink">
            <ShieldAlert className="h-4 w-4 text-amber-500" />
            {t("res.flaggedTitle")}
          </h3>
          <ul className="mt-2 list-disc space-y-1.5 ps-5 text-[13px] leading-6 text-ink-2">
            {result.warnings.map((w, i) => (
              <li key={`w${i}`}>{lang === "fa" ? w.fa : w.en}</li>
            ))}
            {reviewFlagged.slice(0, 8).map((ev, i) => (
              <li key={`f${i}`}>
                <span className="tabular-nums text-ink-3">{clock(ev.t_start)}</span>
                {" — "}
                {MOVEMENT_LABELS[ev.movement] ?? ev.movement}
                <span className="inline-flex items-center gap-1 ms-1.5 text-amber-600 dark:text-amber-400">
                  <Flag className="h-3 w-3" />
                  {t("res.needReview")}
                </span>
                {ev.outcome === "no_rep" && ev.reason_fa && (
                  <span dir="auto" className="text-ink-3"> ({ev.reason_fa})</span>
                )}
              </li>
            ))}
            {result.sequencer_flags.map((f, i) => (
              <li key={`s${i}`}>
                <span className="tabular-nums text-ink-3">{clock(f.t)}</span>
                {" — "}
                {lang === "fa" ? f.reason_fa : f.reason_en}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* footer: JSON + disclaimer */}
      <div className="flex flex-wrap items-center gap-3 pb-2">
        <a
          href={`/api/judge/jobs/${jobId}/result`}
          download={`judge-${jobId}.json`}
          className={cn(
            "inline-flex items-center gap-2 rounded-lg border border-edge px-4 py-2",
            "text-sm font-medium text-ink-2 transition-colors hover:border-edge-2 hover:text-ink",
          )}
        >
          <Download className="h-4 w-4" />
          {t("res.downloadJson")}
        </a>
        <p className="text-xs leading-5 text-ink-4">{t("res.disclaimer")}</p>
      </div>
    </div>
  );
}
