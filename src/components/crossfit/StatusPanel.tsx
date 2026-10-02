"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Loader2, CheckCircle2, XCircle, AlertTriangle } from "lucide-react";
import type { JobInfo } from "./types";
import { toFa } from "@/lib/fa";

const STEPS = [
  { key: "queue", label: "در صف" },
  { key: "validate", label: "اعتبارسنجی" },
  { key: "start", label: "تشخیص شروع" },
  { key: "analyze", label: "تحلیل فریم‌ها" },
  { key: "score", label: "امتیازدهی" },
  { key: "done", label: "آماده" },
];

function stageIndex(job: JobInfo | null): number {
  if (!job) return 0;
  if (job.status === "failed") return 5;
  if (job.status === "done") return 5;
  const s = job.stage_fa || "";
  if (s.includes("صف")) return 0;
  if (s.includes("اعتبارسنجی")) return 1;
  if (s.includes("شروع")) return 2;
  if (s.includes("فریم") || s.includes("ورزشکار")) return 3;
  if (s.includes("امتیاز") || s.includes("بازبینی")) return 4;
  return 3;
}

interface Props {
  job: JobInfo | null;
  resultReady: boolean;
}

export function StatusPanel({ job, resultReady }: Props) {
  const idx = stageIndex(job);
  const failed = job?.status === "failed";
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-xl font-bold">
          {failed ? (
            <XCircle className="h-5 w-5 text-red-600" />
          ) : resultReady ? (
            <CheckCircle2 className="h-5 w-5 text-green-600" />
          ) : (
            <Loader2 className="h-5 w-5 animate-spin text-red-600" />
          )}
          وضعیت تحلیل
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {failed ? (
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertTitle>تحلیل با خطا متوقف شد</AlertTitle>
            <AlertDescription>{job?.error_fa}</AlertDescription>
          </Alert>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-1.5">
              {STEPS.map((s, i) => (
                <span key={s.key} className="flex items-center gap-1.5">
                  <Badge
                    variant={i < idx ? "default" : i === idx ? "secondary" : "outline"}
                    className={
                      i < idx
                        ? "bg-green-600 hover:bg-green-600"
                        : i === idx
                          ? "animate-pulse border-red-600/40 bg-red-50 text-red-700"
                          : "text-muted-foreground"
                    }
                  >
                    {s.label}
                  </Badge>
                  {i < STEPS.length - 1 && (
                    <span className="text-muted-foreground">›</span>
                  )}
                </span>
              ))}
            </div>
            <div className="space-y-1">
              <div className="flex items-center justify-between text-sm text-muted-foreground">
                <span>{job?.stage_fa || "در انتظار…"}</span>
                <span>{toFa(Math.round(job?.progress || 0))}%</span>
              </div>
              <Progress value={job?.progress || 0} className="h-2" />
            </div>
            <p className="text-xs text-muted-foreground">
              تحلیل یک ویدیوی ۱۲ تا ۱۵ دقیقه‌ای روی سرور معمولی چند دقیقه طول می‌کشد؛
              این صفحه خودکار به‌روز می‌شود.
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}
