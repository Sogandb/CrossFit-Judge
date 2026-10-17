"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  ClipboardCheck, ShieldAlert, Download, Flag, Video, TimerReset, Loader2,
} from "lucide-react";
import type { AnalysisResult, AnalysisEvent, LadderEntry } from "./types";
import { ScoreCard } from "./ScoreCard";
import { StatsGrid } from "./StatsGrid";
import { RepTable } from "./RepTable";
import { AnnotatedVideoPlayer } from "./AnnotatedVideoPlayer";
import { fetchResult, reanalyzeJob } from "./judge-client";
import { MOVEMENT_LABELS, useLang } from "@/lib/i18n";
import { cn } from "@/lib/utils";

interface Props {
  jobId: string;
  createdAt: number;
  athleteName?: string;
  result: AnalysisResult;
  /** Re-queue this job for analysis (manual-start re-run) — the page
   *  switches back to the processing view and polls. */
  onReanalyze?: (jobId: string) => void;
}

export function ResultsView({ jobId, createdAt, athleteName, result, onReanalyze }: Props) {
  const { t, n, clock, dateTime, lang } = useLang();
  const videoRef = useRef<HTMLVideoElement>(null);
  const [selectedRep, setSelectedRep] = useState<number | null>(null);
  const [reMin, setReMin] = useState("");
  const [reSec, setReSec] = useState("");
  const [reBusy, setReBusy] = useState(false);
  const [reError, setReError] = useState<string | null>(null);

  // ---- async review video: poll "pending" → ready, then swap in ------- //
  // The judging result is FINAL the moment this view renders; only the
  // annotated video renders in the background. Poll every 8 s until the
  // store patches review_video to true/false.
  const [review, setReview] = useState<boolean | "pending">(result.review_video);
  const resultReview = result.review_video;
  useEffect(() => {
    // sync from a NEW result document (e.g. retry or history re-open) in a
    // microtask — keeps the render that created this state pure.
    const id = setTimeout(() => setReview(resultReview), 0);
    return () => clearTimeout(id);
  }, [resultReview]);
  useEffect(() => {
    if (review !== "pending") return;
    const id = setInterval(() => {
      fetchResult(jobId)
        .then((r) => {
          if (r.review_video !== "pending") setReview(r.review_video);
        })
        .catch(() => undefined); // transient poll failures are fine
    }, 8000);
    return () => clearInterval(id);
  }, [review, jobId]);

  // only slot attempts participate in the flagged-for-review list
  const events = useMemo(
    () => [...result.events].sort((a, b) => a.t_start - b.t_start),
    [result.events],
  );
  const reviewFlagged = events.filter(
    (e: AnalysisEvent) => (e.kind ?? "slot") === "slot" && e.review_flags?.length,
  );
  const rec = result.reconciliation;
  const startNotFound = result.start_detection.method === "video_start";

  const seekTo = (row: LadderEntry) => {
    setSelectedRep(row.rep_no);
    if (videoRef.current && row.t_start != null) {
      videoRef.current.currentTime = Math.max(0, row.t_start - 0.5);
      videoRef.current.play().catch(() => undefined);
    }
  };

  const submitReanalyze = async () => {
    setReError(null);
    const m = Number(reMin || 0);
    const s = Number(reSec || 0);
    const total = m * 60 + s;
    if (Number.isNaN(m) || Number.isNaN(s) || total <= 0) {
      setReError(t("res.reanalyzeErrTime"));
      return;
    }
    setReBusy(true);
    try {
      await reanalyzeJob(jobId, total);
      onReanalyze?.(jobId);
    } catch {
      setReError(t("res.reanalyzeErrGeneric"));
      setReBusy(false);
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

      {/* workout-start correction — the honest fix for SYS_START_NOT_FOUND */}
      {startNotFound && onReanalyze && (
        <div className="rounded-xl border border-amber-500/40 bg-amber-500/5 p-4">
          <h3 className="flex items-center gap-2 text-sm font-bold text-ink">
            <TimerReset className="h-4 w-4 text-amber-500" />
            {t("res.startFixTitle")}
          </h3>
          <p className="mt-1 text-[13px] leading-6 text-ink-2">
            {t("res.startFixHint")}
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <input
              inputMode="numeric"
              value={reMin}
              onChange={(e) => setReMin(e.target.value.replace(/\D/g, "").slice(0, 2))}
              placeholder="mm"
              className="w-14 rounded-lg border border-edge bg-panel px-2 py-1.5 text-center text-sm tabular-nums outline-none focus:border-brand"
              aria-label="minutes"
            />
            <span className="text-ink-4">:</span>
            <input
              inputMode="numeric"
              value={reSec}
              onChange={(e) => setReSec(e.target.value.replace(/\D/g, "").slice(0, 2))}
              placeholder="ss"
              className="w-14 rounded-lg border border-edge bg-panel px-2 py-1.5 text-center text-sm tabular-nums outline-none focus:border-brand"
              aria-label="seconds"
            />
            <button
              type="button"
              onClick={submitReanalyze}
              disabled={reBusy}
              className={cn(
                "inline-flex items-center gap-2 rounded-lg bg-ink text-panel px-4 py-2",
                "text-sm font-semibold transition-opacity hover:opacity-90",
                reBusy && "opacity-60 cursor-wait",
              )}
            >
              {reBusy && <Loader2 className="h-4 w-4 animate-spin" />}
              {t("res.reanalyzeBtn")}
            </button>
            {reError && <span className="text-xs text-brand-fg">{reError}</span>}
          </div>
        </div>
      )}

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

      {/* per-movement breakdown */}
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
                {m.not_detected ? (
                  <p className="text-xs text-amber-600 dark:text-amber-400 mt-1 tabular-nums">
                    {n(m.not_detected)} {t("res.notDetectedShort")}
                  </p>
                ) : null}
                <p className="text-[10px] text-ink-4 mt-1 tabular-nums">
                  {t("res.countedLabel")}: {n(m.attempted)} / {n(m.prescribed)}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* review video + THE ladder (user's exact 1..126 count) */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-start">
        {review === true ? (
          <AnnotatedVideoPlayer jobId={jobId} videoRef={videoRef} />
        ) : review === "pending" ? (
          <div className="rounded-xl border border-edge bg-panel-2/50 aspect-video flex flex-col items-center justify-center gap-3 text-center px-6">
            <div className="h-10 w-10 rounded-full border-2 border-edge border-t-brand-fg animate-spin" />
            <div className="space-y-1">
              <p className="text-sm font-semibold text-ink flex items-center gap-2 justify-center">
                <Video className="h-4 w-4 text-ink-3" />
                {t("res.reviewPending")}
              </p>
              <p className="text-xs text-ink-3 leading-relaxed">
                {t("res.reviewPendingHint")}
              </p>
            </div>
          </div>
        ) : (
          <div className="hidden lg:block" />
        )}
        <RepTable result={result} selectedRep={selectedRep} onSeek={seekTo} />
      </div>

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
                <span className="tabular-nums text-ink-3">
                  {ev.rep_no != null ? `#${n(ev.rep_no)} · ` : ""}
                  {clock(ev.t_start)}
                </span>
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
