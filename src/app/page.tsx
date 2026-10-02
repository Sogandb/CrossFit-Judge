"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Dumbbell, Cpu, Eye, ShieldCheck } from "lucide-react";
import { WodCard } from "@/components/crossfit/WodCard";
import { UploadForm, type SubmitPayload } from "@/components/crossfit/UploadForm";
import { StatusPanel } from "@/components/crossfit/StatusPanel";
import { ResultsView } from "@/components/crossfit/ResultsView";
import { HistoryList } from "@/components/crossfit/HistoryList";
import {
  fetchDivisions, fetchJob, fetchJobs, uploadJob,
} from "@/components/crossfit/judge-client";
import type {
  AnalysisResult, DivisionsResponse, JobInfo,
} from "@/components/crossfit/types";
import { toast } from "@/hooks/use-toast";

type Phase = "form" | "processing" | "result";

export default function Home() {
  const [divisions, setDivisions] = useState<DivisionsResponse | null>(null);
  const [jobs, setJobs] = useState<JobInfo[]>([]);
  const [phase, setPhase] = useState<Phase>("form");
  const [job, setJob] = useState<JobInfo | null>(null);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const resultRef = useRef<HTMLDivElement>(null);

  // bootstrap: catalog + history
  useEffect(() => {
    fetchDivisions().then(setDivisions).catch(() =>
      toast({ title: "سرویس تحلیل در دسترس نیست", variant: "destructive" }));
    fetchJobs().then((r) => setJobs(r.jobs)).catch(() => undefined);
    const t = setInterval(() => {
      if (phase === "processing") fetchJobs().then((r) => setJobs(r.jobs)).catch(() => undefined);
    }, 10000);
    return () => clearInterval(t);
  }, [phase]);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  useEffect(() => stopPolling, [stopPolling]);

  const poll = useCallback((id: string) => {
    stopPolling();
    pollRef.current = setInterval(async () => {
      try {
        const body = await fetchJob(id);
        setJob(body.job);
        if (body.job.status === "done") {
          stopPolling();
          setResult(body.result);
          setPhase("result");
          fetchJobs().then((r) => setJobs(r.jobs)).catch(() => undefined);
          setTimeout(() =>
            resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 150);
        } else if (body.job.status === "failed") {
          stopPolling();
          setPhase("result"); // status panel shows the error
        }
      } catch { /* transient network errors — keep polling */ }
    }, 2500);
  }, [stopPolling]);

  const onSubmit = useCallback(async (p: SubmitPayload, onProgress: (pct: number) => void) => {
    const r = await uploadJob({
      file: p.file,
      division: p.division,
      athleteName: p.athleteName,
      claimedReps: p.claimedReps,
      claimedTimeSec: p.claimedTimeSec,
      claimedCapped: p.claimedCapped,
      manualStartSec: p.manualStartSec,
      onProgress,
    });
    setJob({
      id: r.job_id, created_at: Date.now() / 1000, status: "queued",
      stage_fa: "در صف پردازش", progress: 0, error_fa: null,
      athlete_name: p.athleteName, division: p.divisionLabel,
    });
    setResult(null);
    setPhase("processing");
    poll(r.job_id);
    toast({ title: "ویدیو دریافت شد", description: "تحلیل آغاز شد — این صفحه را باز نگه دارید" });
  }, [poll]);

  const openJob = useCallback(async (id: string) => {
    try {
      const body = await fetchJob(id);
      setJob(body.job);
      if (body.job.status === "done" && body.result) {
        setResult(body.result);
        setPhase("result");
        setTimeout(() =>
          resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 150);
      } else if (body.job.status === "failed") {
        setPhase("result");
      } else {
        setResult(null);
        setPhase("processing");
        poll(id);
      }
    } catch {
      toast({ title: "بازکردن تحلیل ناموفق بود", variant: "destructive" });
    }
  }, [poll]);

  return (
    <div className="flex min-h-screen flex-col bg-zinc-50">
      {/* ---------- header ---------- */}
      <header className="border-b bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-3">
          <div className="flex items-center gap-2.5">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-red-600 text-white">
              <Dumbbell className="h-5 w-5" />
            </span>
            <div>
              <h1 className="text-lg font-black leading-5">داور هوشمند کراس‌فیت</h1>
              <p className="text-xs text-muted-foreground">
                دستیار داوری ویدیویی مسابقات آنلاین
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="border-red-600/30 text-red-700">
              نسخه ۲ • نمونه اولیه وادکس
            </Badge>
          </div>
        </div>
      </header>

      {/* ---------- body ---------- */}
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6">
        {/* hero */}
        <section className="mb-6 grid gap-3 sm:grid-cols-3">
          {[
            { icon: Cpu, title: "تشخیص حرکت با هوش مصنوعی",
              desc: "شمارش رپ و بررسی استانداردها با تحلیل ۳۳ نقطه بدن در هر فریم" },
            { icon: Eye, title: "بازبینی شفاف",
              desc: "ویدیوی نشانه‌گذاری‌شده و تایم‌لاین کلیک‌شود برای هر رپ و نورپ" },
            { icon: ShieldCheck, title: "داور انسانی در تصمیم نهایی",
              desc: "سیستم توصیه می‌دهد؛ موارد مشکوک به صف بازبینی داور می‌رود" },
          ].map((f) => (
            <div key={f.title} className="flex gap-3 rounded-xl border bg-white p-4">
              <f.icon className="mt-0.5 h-5 w-5 shrink-0 text-red-600" />
              <div>
                <div className="font-bold">{f.title}</div>
                <p className="mt-0.5 text-sm leading-6 text-muted-foreground">{f.desc}</p>
              </div>
            </div>
          ))}
        </section>

        <div className="grid gap-6 lg:grid-cols-3">
          <div className="space-y-6 lg:col-span-2">
            <WodCard />

            {phase === "form" && (
              divisions ? (
                <UploadForm
                  grouped={divisions.grouped}
                  weightsVerified={divisions.weights_verified}
                  onSubmit={onSubmit}
                />
              ) : (
                <div className="rounded-xl border bg-white p-8 text-center text-sm text-muted-foreground">
                  در حال اتصال به سرویس تحلیل…
                </div>
              )
            )}

            {phase === "processing" && (
              <StatusPanel job={job} resultReady={false} />
            )}

            <div ref={resultRef}>
              {phase === "result" && job && job.status === "failed" && (
                <StatusPanel job={job} resultReady={false} />
              )}
              {phase === "result" && result && job && (
                <ResultsView
                  jobId={job.id}
                  createdAt={job.created_at}
                  athleteName={job.athlete_name}
                  result={result}
                />
              )}
            </div>

            {phase !== "form" && (
              <button
                onClick={() => { stopPolling(); setPhase("form"); setJob(null); setResult(null); }}
                className="text-sm text-red-700 underline"
              >
                ← ارسال ویدیوی جدید
              </button>
            )}
          </div>

          {/* sidebar */}
          <aside className="space-y-6">
            <HistoryList jobs={jobs} onSelect={openJob} activeId={job?.id} />
            <Alert>
              <ShieldCheck className="h-4 w-4" />
              <AlertTitle>نکته داوری</AlertTitle>
              <AlertDescription className="leading-6">
                دقت سیستم روی حرکات این واد (تراستر و بورپی رو به بار) کالیبره شده است.
                رپ‌های مبهم به‌جای حذف، با برچسب «نیازمند بازبینی» به داور انسانی ارجاع می‌شوند.
              </AlertDescription>
            </Alert>
          </aside>
        </div>
      </main>

      {/* ---------- footer (sticky bottom) ---------- */}
      <footer className="mt-auto border-t bg-white">
        <div className="mx-auto max-w-6xl px-4 py-4 text-center text-xs leading-6 text-muted-foreground">
          معماری سه‌لایه: کتابخانه حرکات (FSM) ← مفسر واد (DSL) ← موتور تحلیل ویدیو •
          استانداردها بر پایه آیین‌نامه کراس‌فیت گیمز و قوانین وادکس
        </div>
      </footer>
    </div>
  );
}
