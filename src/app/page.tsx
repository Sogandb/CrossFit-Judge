"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { CheckCircle2, RotateCcw, UploadCloud, XCircle } from "lucide-react";
import { Header } from "@/components/crossfit/Header";
import { Footer } from "@/components/crossfit/Footer";
import { WodCard } from "@/components/crossfit/WodCard";
import { UploadForm, type SubmitPayload } from "@/components/crossfit/UploadForm";
import { StatusPanel } from "@/components/crossfit/StatusPanel";
import { ResultsView } from "@/components/crossfit/ResultsView";
import { HistoryList } from "@/components/crossfit/HistoryList";
import {
  fetchDivisions, fetchJob, fetchJobs, retryJob, uploadJob,
} from "@/components/crossfit/judge-client";
import type {
  AnalysisResult, DivisionsResponse, JobInfo,
} from "@/components/crossfit/types";
import { toast } from "@/hooks/use-toast";
import { useLang } from "@/lib/i18n";
import { cn } from "@/lib/utils";

type Phase = "idle" | "uploading" | "processing" | "completed" | "failed";

export default function Home() {
  const { t, lang } = useLang();
  const [divisions, setDivisions] = useState<DivisionsResponse | null>(null);
  const [serviceError, setServiceError] = useState(false);
  const [jobs, setJobs] = useState<JobInfo[]>([]);
  const [phase, setPhase] = useState<Phase>("idle");
  const [job, setJob] = useState<JobInfo | null>(null);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploadPct, setUploadPct] = useState(0);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const resultRef = useRef<HTMLDivElement>(null);

  // bootstrap: catalog + history (once)
  useEffect(() => {
    let cancelled = false;
    fetchDivisions()
      .then((d) => { if (!cancelled) setDivisions(d); })
      .catch(() => { if (!cancelled) setServiceError(true); });
    fetchJobs()
      .then((r) => { if (!cancelled) setJobs(r.jobs); })
      .catch(() => undefined);
    return () => { cancelled = true; };
  }, []);

  // refresh history while a job is in flight
  useEffect(() => {
    const id = setInterval(() => {
      if (phase === "uploading" || phase === "processing") {
        fetchJobs().then((r) => setJobs(r.jobs)).catch(() => undefined);
      }
    }, 10000);
    return () => clearInterval(id);
  }, [phase]);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  useEffect(() => stopPolling, [stopPolling]);

  const refreshJobs = useCallback(() => {
    fetchJobs().then((r) => setJobs(r.jobs)).catch(() => undefined);
  }, []);

  const poll = useCallback((id: string) => {
    stopPolling();
    let consecutiveErrors = 0;
    pollRef.current = setInterval(async () => {
      try {
        const body = await fetchJob(id);
        consecutiveErrors = 0;
        setJob(body.job);
        if (body.job.status === "done") {
          stopPolling();
          setResult(body.result);
          setPhase("completed");
          refreshJobs();
          setTimeout(() =>
            resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 150);
        } else if (body.job.status === "failed") {
          stopPolling();
          setError(null); // the failed view reads job.error_fa/_en
          setPhase("failed");
          refreshJobs();
        }
      } catch {
        consecutiveErrors += 1;
        if (consecutiveErrors >= 5) {
          stopPolling();
          setError(t("fail.lostConnection"));
          setPhase("failed");
        }
      }
    }, 2500);
  }, [stopPolling, refreshJobs, t]);

  const onSubmit = useCallback(async (p: SubmitPayload, onProgress: (pct: number) => void) => {
    setError(null);
    setResult(null);
    setUploadPct(0);
    setPhase("uploading");
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const r = await uploadJob({
        file: p.file,
        division: p.division,
        athleteName: p.athleteName,
        claimedReps: p.claimedReps,
        claimedTimeSec: p.claimedTimeSec,
        claimedCapped: p.claimedCapped,
        manualStartSec: p.manualStartSec,
        signal: controller.signal,
        // Drive the PAGE's uploadPct (StatusPanel stays mounted during upload;
        // the form's own setter alone would never move the visible bar).
        onProgress: (pct) => {
          setUploadPct(pct);
          onProgress?.(pct);
        },
      });
      setJob({
        id: r.job_id, created_at: Date.now() / 1000, status: "queued",
        stage_key: "queued", stage_fa: "در صف پردازش", stage_en: "Queued",
        progress: 0, error_fa: null, error_en: null,
        athlete_name: p.athleteName, division: p.divisionLabel,
      });
      setPhase("processing");
      poll(r.job_id);
      toast({ title: t("form.uploadReceived"), description: t("form.uploadStarted") });
    } catch (e) {
      abortRef.current = null;
      setPhase("idle");
      if (e instanceof DOMException && e.name === "AbortError") {
        toast({ title: t("proc.cancelled") });
        return; // user-initiated cancel — already handled
      }
      throw e; // UploadForm shows the error toast
    }
  }, [poll, t]);

  const handleCancel = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    stopPolling();
    setPhase("idle");
    setJob(null);
    setResult(null);
    setError(null);
    setUploadPct(0);
  }, [stopPolling]);

  const handleReset = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    stopPolling();
    setPhase("idle");
    setJob(null);
    setResult(null);
    setError(null);
    setUploadPct(0);
  }, [stopPolling]);

  /** Retry a failed analysis WITHOUT re-uploading — the video is already
   *  on the server; only the engine re-runs (transient failures such as
   *  engine restarts / environment hiccups are exactly this case). */
  const handleRetry = useCallback(async () => {
    if (!job) return;
    const jobId = job.id;
    try {
      await retryJob(jobId);
      setError(null);
      setResult(null);
      setPhase("processing");
      poll(jobId);
    } catch {
      toast({ title: t("fail.retryUnavailable"), variant: "destructive" });
    }
  }, [job, poll, t]);

  const openJob = useCallback(async (id: string) => {
    try {
      const body = await fetchJob(id);
      setJob(body.job);
      setError(null);
      if (body.job.status === "done" && body.result) {
        setResult(body.result);
        setPhase("completed");
        setTimeout(() =>
          resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 150);
      } else if (body.job.status === "failed") {
        setPhase("failed");
      } else {
        setResult(null);
        setPhase("processing");
        poll(id);
      }
    } catch {
      toast({ title: t("form.serviceDown"), variant: "destructive" });
    }
  }, [poll, t]);

  const isWorking = phase === "uploading" || phase === "processing";
  const currentStep = phase === "completed" ? 3 : isWorking ? 2 : 1;
  const failedMessage =
    error ??
    (job ? (lang === "fa" ? job.error_fa : job.error_en) : null) ??
    t("fail.fallback");

  return (
    <div className="min-h-screen flex flex-col bg-app text-ink">
      <Header />

      <div className="flex-1 mx-auto w-full max-w-7xl flex">
        {/* ===== Sidebar (v1) ===== */}
        <aside className="w-72 shrink-0 border-e border-edge bg-app hidden md:flex flex-col">
          <div className="p-5 space-y-5 flex-1 overflow-y-auto scroll-slim">
            {/* steps */}
            <div className="space-y-3">
              <p className="text-[11px] font-bold uppercase tracking-wider text-ink-3">
                {t("side.workflow")}
              </p>
              <div className="space-y-2.5">
                <StepIndicator step={1} label={t("side.step1")} active={currentStep === 1} done={currentStep > 1} />
                <StepIndicator step={2} label={t("side.step2")} active={currentStep === 2} done={currentStep > 2} />
                <StepIndicator step={3} label={t("side.step3")} active={currentStep === 3} done={currentStep > 3} />
              </div>
            </div>

            <div className="h-px bg-edge" />

            {/* workout summary (the fixed WOD) */}
            <div className="space-y-2">
              <p className="text-[11px] font-bold uppercase tracking-wider text-ink-3">
                {t("side.workout")}
              </p>
              <div className="rounded-lg border border-edge bg-panel-2/50 p-3 space-y-1.5">
                <p className="text-sm font-semibold text-ink leading-tight">
                  Thruster &amp; Bar-Facing Burpee Ladder
                </p>
                <div className="flex items-center gap-2 text-[11px]">
                  <span className="rounded bg-brand/15 text-brand-fg px-1.5 py-0.5 font-bold uppercase">
                    For Time
                  </span>
                  <span className="text-ink-3">{t("wod.timeCap")}</span>
                </div>
                <div className="flex flex-wrap gap-1 pt-1">
                  <span className="text-[10px] rounded bg-chip text-ink-3 px-1.5 py-0.5">Thruster</span>
                  <span className="text-[10px] rounded bg-chip text-ink-3 px-1.5 py-0.5">Bar-Facing Burpee</span>
                </div>
              </div>
            </div>

            <div className="h-px bg-edge" />

            <HistoryList jobs={jobs} onSelect={openJob} activeId={job?.id} />

            <div className="h-px bg-edge" />

            <div className="space-y-1.5">
              <p className="text-[11px] font-bold uppercase tracking-wider text-ink-3">
                {t("side.noteTitle")}
              </p>
              <p className="text-[11px] leading-5 text-ink-3">{t("side.noteBody")}</p>
            </div>
          </div>
        </aside>

        {/* ===== Main ===== */}
        <main className="flex-1 min-w-0">
          <div className="p-5 sm:p-8 space-y-6">
            {/* STEP 1: workout + upload */}
            {phase === "idle" && (
              <>
                <div>
                  <h2 className="text-xl font-bold text-ink mb-1">{t("main.workoutTitle")}</h2>
                  <p className="text-sm text-ink-3">{t("main.workoutSub")}</p>
                </div>

                <WodCard />

                <div className="rounded-xl border border-edge bg-panel p-4 sm:p-5">
                  {divisions ? (
                    <UploadForm
                      grouped={divisions.grouped}
                      weightsVerified={divisions.weights_verified}
                      onSubmit={onSubmit}
                      onCancelUpload={handleCancel}
                    />
                  ) : (
                    <div className="p-8 text-center text-sm text-ink-3">
                      {serviceError ? t("form.serviceDown") : t("form.connecting")}
                    </div>
                  )}
                </div>

                {/* mobile history (sidebar hidden on small screens) */}
                <div className="md:hidden">
                  <HistoryList jobs={jobs} onSelect={openJob} activeId={job?.id} />
                </div>
              </>
            )}

            {/* STEP 2: uploading / processing */}
            {isWorking && (
              <div className="max-w-lg mx-auto py-12">
                <StatusPanel
                  phase={phase === "uploading" ? "uploading" : "processing"}
                  job={job}
                  uploadPct={uploadPct}
                  onCancel={handleCancel}
                />
              </div>
            )}

            {/* Failed */}
            {phase === "failed" && (
              <div className="max-w-lg mx-auto py-12 space-y-6">
                <div className="rounded-xl border border-red-500/30 bg-red-500/5 p-6 space-y-3">
                  <div className="flex items-center gap-3">
                    <XCircle className="h-6 w-6 text-brand-fg shrink-0" />
                    <div>
                      <p className="text-sm font-semibold text-ink">{t("fail.title")}</p>
                      <p className="text-xs text-ink-3 mt-0.5 leading-relaxed">{failedMessage}</p>
                    </div>
                  </div>
                </div>
                <div className="flex flex-col sm:flex-row gap-3">
                  <Button onClick={handleRetry} className="gap-2 flex-1">
                    <RotateCcw className="h-4 w-4" />
                    {t("fail.retryAnalysis")}
                  </Button>
                  <Button onClick={handleReset} variant="outline" className="gap-2 flex-1">
                    <UploadCloud className="h-4 w-4" />
                    {t("fail.startOver")}
                  </Button>
                </div>
              </div>
            )}

            {/* STEP 3: results */}
            {phase === "completed" && result && job && (
              <div ref={resultRef} className="space-y-6 scroll-mt-20">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h2 className="text-xl font-bold text-ink">{t("res.title")}</h2>
                    <p className="text-sm text-ink-3 mt-0.5">
                      Thruster &amp; Bar-Facing Burpee Ladder
                    </p>
                  </div>
                  <Button onClick={handleReset} variant="outline" size="sm" className="gap-2">
                    <RotateCcw className="h-4 w-4" />
                    {t("res.new")}
                  </Button>
                </div>

                <ResultsView
                  jobId={job.id}
                  createdAt={job.created_at}
                  athleteName={job.athlete_name}
                  result={result}
                />
              </div>
            )}
          </div>
        </main>
      </div>

      <Footer />
    </div>
  );
}

// ---------------------------------------------------------------------------
// v1 helper components
// ---------------------------------------------------------------------------
function StepIndicator({
  step, label, active, done,
}: {
  step: number;
  label: string;
  active: boolean;
  done: boolean;
}) {
  return (
    <div className="flex items-center gap-2.5">
      <div
        className={cn(
          "flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[11px] font-bold transition-colors",
          done
            ? "bg-emerald-500 text-white"
            : active
              ? "bg-brand text-white"
              : "bg-chip text-ink-4",
        )}
      >
        {done ? <CheckCircle2 className="h-3.5 w-3.5" /> : step}
      </div>
      <span
        className={cn(
          "text-xs font-medium",
          active ? "text-ink" : done ? "text-ink-2" : "text-ink-4",
        )}
      >
        {label}
      </span>
    </div>
  );
}
