"use client";

import { useMemo, useRef, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  Timer, CheckCircle2, XCircle, Flag, ShieldAlert, Play,
  Download, ClipboardCheck,
} from "lucide-react";
import type { AnalysisResult } from "./types";
import { reviewVideoUrl } from "./judge-client";
import { faClock, faDateTime, toFa } from "@/lib/fa";

const MOVEMENT_FA: Record<string, string> = {
  thruster: "تراستر",
  bar_facing_burpee: "بورپی رو به بار",
};

interface Props {
  jobId: string;
  createdAt: number;
  athleteName?: string;
  result: AnalysisResult;
}

export function ResultsView({ jobId, createdAt, athleteName, result }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [selectedEvent, setSelectedEvent] = useState<number | null>(null);
  const events = useMemo(
    () => [...result.events].sort((a, b) => a.t_start - b.t_start),
    [result.events],
  );
  const noRepCount = events.filter((e) => e.outcome === "no_rep" && !e.post_cap).length;
  const reviewFlags = events.filter((e) => e.review_flags?.length);
  const rec = result.reconciliation;

  const seekTo = (t: number, idx: number) => {
    setSelectedEvent(idx);
    if (videoRef.current) {
      videoRef.current.currentTime = Math.max(0, t);
      videoRef.current.play().catch(() => undefined);
    }
  };

  const verdictColor = rec.verdict === "match"
    ? "border-green-600/30 bg-green-50 text-green-800"
    : rec.review_recommended
      ? "border-amber-500/40 bg-amber-50 text-amber-800"
      : "border-zinc-300 bg-zinc-50 text-zinc-700";

  return (
    <div className="space-y-6">
      {/* ---------- score header ---------- */}
      <Card className="border-2 border-zinc-900/10">
        <CardHeader className="pb-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <CardTitle className="text-2xl font-bold">
                نتیجه داوری {athleteName ? `— ${athleteName}` : ""}
              </CardTitle>
              <p className="mt-1 text-sm text-muted-foreground">
                {faDateTime(createdAt)} • شناسه تحلیل {toFa(jobId)}
              </p>
            </div>
            <div className="rounded-xl bg-zinc-900 px-5 py-3 text-center text-white">
              <div className="text-3xl font-black tracking-wider">
                {toFa(result.score_display.score)}
              </div>
              <div className="mt-0.5 text-xs opacity-80">
                {result.score_display.status_fa}
              </div>
            </div>
          </div>
        </CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-3">
          {(["thruster", "bar_facing_burpee"] as const).map((mv) => {
            const m = result.summary.per_movement[mv] || { credited: 0, no_reps: 0, prescribed: 0 };
            return (
              <div key={mv} className="rounded-lg border p-4">
                <div className="flex items-center justify-between">
                  <span className="font-bold">{MOVEMENT_FA[mv] || mv}</span>
                  <Badge variant="secondary">
                    {toFa(m.credited)} / {toFa(m.prescribed)}
                  </Badge>
                </div>
                <Progress className="mt-2 h-2"
                  value={(m.credited / Math.max(1, m.prescribed)) * 100} />
                <div className="mt-2 flex items-center justify-between text-xs text-muted-foreground">
                  <span className="flex items-center gap-1">
                    <CheckCircle2 className="h-3.5 w-3.5 text-green-600" />
                    {toFa(m.credited)} رپ تأیید
                  </span>
                  <span className="flex items-center gap-1">
                    <XCircle className="h-3.5 w-3.5 text-red-600" />
                    {toFa(m.no_reps)} نورپ
                  </span>
                </div>
              </div>
            );
          })}
          <div className="rounded-lg border p-4">
            <div className="flex items-center justify-between">
              <span className="font-bold">شروع وادی</span>
              <Badge variant="outline">
                {result.start_detection.method === "beep" ? "بوق ۳+۱" :
                 result.start_detection.method === "manual" ? "دستی" :
                 result.start_detection.method === "mock" ? "حالت نمایشی" : "ابتدای ویدیو"}
              </Badge>
            </div>
            <div className="mt-2 text-sm text-muted-foreground">
              لحظه شروع: {faClock(result.start_detection.t_start_sec)} از ویدیو
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              مجموع: {toFa(result.summary.total_credited)} رپ از {toFa(result.summary.total_prescribed)}
              {" • "}
              {toFa(noRepCount)} نورپ ثبت شد
            </div>
          </div>
        </CardContent>
      </Card>

      {/* ---------- reconciliation ---------- */}
      <div className={`rounded-xl border-2 p-4 ${verdictColor}`}>
        <div className="flex items-start gap-3">
          <ClipboardCheck className="mt-0.5 h-5 w-5 shrink-0" />
          <div className="flex-1">
            <div className="font-bold">تطبیق با امتیاز ادعایی</div>
            <p className="mt-1 text-sm leading-6">{rec.verdict_fa}</p>
            <div className="mt-2 flex flex-wrap gap-2 text-xs">
              {rec.claimed_reps != null && (
                <span className="rounded-full bg-white/60 px-2.5 py-1">
                  ادعا: {toFa(rec.claimed_reps)} رپ
                </span>
              )}
              <span className="rounded-full bg-white/60 px-2.5 py-1">
                شمارش سیستم: {toFa(rec.counted_reps)} رپ
              </span>
              {rec.claimed_time_sec != null && (
                <span className="rounded-full bg-white/60 px-2.5 py-1">
                  زمان ادعایی: {faClock(rec.claimed_time_sec)}
                </span>
              )}
              {result.summary.finish_time_sec != null && (
                <span className="rounded-full bg-white/60 px-2.5 py-1">
                  زمان سیستم: {faClock(result.summary.finish_time_sec)}
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* ---------- blocks table ---------- */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-lg font-bold">روند رندبه‌رند واد</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="text-right">رند</TableHead>
                <TableHead className="text-right">حرکت</TableHead>
                <TableHead className="text-right">تعداد تعیین‌شده</TableHead>
                <TableHead className="text-right">تأییدشده</TableHead>
                <TableHead className="text-right">وضعیت</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {result.summary.blocks.map((b) => (
                <TableRow key={b.idx}>
                  <TableCell>{toFa(b.idx + 1)}</TableCell>
                  <TableCell className="font-medium">{b.movement_fa}</TableCell>
                  <TableCell>{toFa(b.reps)}</TableCell>
                  <TableCell>
                    <span className={b.complete ? "font-bold text-green-700" : "font-bold"}>
                      {toFa(b.credited)}
                    </span>
                  </TableCell>
                  <TableCell>
                    <Badge variant={b.complete ? "default" : b.credited > 0 ? "secondary" : "outline"}
                      className={b.complete ? "bg-green-600 hover:bg-green-600" : ""}>
                      {b.status_fa}
                    </Badge>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* ---------- video + timeline ---------- */}
      {result.review_video && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-lg font-bold">
              <Play className="h-5 w-5 text-red-600" />
              ویدیوی بازبینی با نشانه‌گذاری رویدادها
            </CardTitle>
            <p className="text-sm text-muted-foreground">
              روی هر رویداد در فهرست پایین کلیک کنید تا ویدیو به همان لحظه برود
              (نوار بالا-راست: شمارنده رپ، بالا-چپ: زمان واد).
            </p>
          </CardHeader>
          <CardContent className="grid gap-4 lg:grid-cols-5">
            <video
              ref={videoRef}
              controls
              playsInline
              className="w-full rounded-lg border bg-black lg:col-span-3"
              src={reviewVideoUrl(jobId)}
            />
            <div className="lg:col-span-2">
              <div className="mb-2 flex items-center justify-between">
                <span className="font-bold">تایم‌لاین رویدادها</span>
                <span className="text-xs text-muted-foreground">
                  {toFa(events.length)} رویداد
                </span>
              </div>
              <div className="max-h-[28rem] space-y-1.5 overflow-y-auto pl-1">
                {events.map((ev, i) => {
                  const isNoRep = ev.outcome === "no_rep";
                  return (
                    <button
                      key={i}
                      onClick={() => seekTo(ev.t_start, i)}
                      className={`w-full rounded-lg border p-2.5 text-right transition-colors
                        ${selectedEvent === i ? "border-red-600 bg-red-50" :
                          isNoRep ? "border-red-200 bg-red-50/40 hover:border-red-400" :
                          ev.post_cap ? "border-zinc-200 bg-zinc-50 opacity-70" :
                          "border-green-200 bg-green-50/40 hover:border-green-500"}`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="flex items-center gap-1.5 text-sm font-semibold">
                          {isNoRep ? (
                            <XCircle className="h-4 w-4 text-red-600" />
                          ) : (
                            <CheckCircle2 className="h-4 w-4 text-green-600" />
                          )}
                          {MOVEMENT_FA[ev.movement] || ev.movement}
                          {ev.rep_no != null && ev.scored && (
                            <span className="text-muted-foreground">رپ {toFa(ev.rep_no)}</span>
                          )}
                          {ev.post_cap && (
                            <Badge variant="outline" className="text-[10px]">بعد از کپ</Badge>
                          )}
                        </span>
                        <span className="flex items-center gap-1 font-mono text-xs text-muted-foreground">
                          <Timer className="h-3 w-3" />
                          {faClock(ev.t_start)}
                        </span>
                      </div>
                      {isNoRep && ev.reason_fa && (
                        <div className="mt-1 text-xs leading-5 text-red-800">
                          دلیل نورپ: {ev.reason_fa}
                        </div>
                      )}
                      {!isNoRep && ev.notes?.length > 0 && (
                        <div className="mt-1 text-xs text-muted-foreground">{ev.notes.join("؛ ")}</div>
                      )}
                      {ev.review_flags?.length > 0 && (
                        <div className="mt-1 flex items-center gap-1 text-xs text-amber-700">
                          <Flag className="h-3 w-3" />
                          نیازمند بازبینی داور
                        </div>
                      )}
                    </button>
                  );
                })}
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* ---------- review queue + warnings ---------- */}
      {(reviewFlags.length > 0 || result.sequencer_flags.length > 0 || result.warnings.length > 0) && (
        <Alert>
          <ShieldAlert className="h-4 w-4" />
          <AlertTitle>موارد نیازمند بازبینی داور انسانی</AlertTitle>
          <AlertDescription>
            <ul className="list-disc space-y-1 pr-5 pt-1">
              {result.warnings.map((w, i) => <li key={`w${i}`}>{w}</li>)}
              {reviewFlags.slice(0, 8).map((ev, i) => (
                <li key={`f${i}`}>
                  {faClock(ev.t_start)} — {MOVEMENT_FA[ev.movement] || ev.movement}:
                  رویدادی با نشانه‌های بازبینی
                  {ev.outcome === "no_rep" && ev.reason_fa ? ` (${ev.reason_fa})` : ""}
                </li>
              ))}
              {result.sequencer_flags.map((f, i) => (
                <li key={`s${i}`}>{faClock(f.t)} — {f.reason_fa}</li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <a
          href={`/api/judge/jobs/${jobId}/result`}
          download={`judge-${jobId}.json`}
          className="inline-flex items-center gap-2 rounded-md border px-4 py-2 text-sm font-medium
                     hover:bg-zinc-100"
        >
          <Download className="h-4 w-4" />
          دانلود گزارش کامل (JSON)
        </a>
        <Separator orientation="vertical" className="h-6" />
        <p className="text-xs leading-5 text-muted-foreground">
          خروجی سیستم توصیه‌ای برای داور است؛ تصمیم نهایی داوری با بازبینی انسانی است.
        </p>
      </div>
    </div>
  );
}
