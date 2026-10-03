"use client";

import { Button } from "@/components/ui/button";
import { CheckCircle2, Loader2, UploadCloud, X } from "lucide-react";
import type { JobInfo } from "./types";
import { useLang } from "@/lib/i18n";
import { cn } from "@/lib/utils";

/** v1 ProcessingPanel — upload/analyze progress with the red→orange bar. */

const PIPELINE = ["queued", "validate", "start_detect", "analyzing", "scoring", "done"] as const;

// transient engine stages map onto the compact pipeline above
const ALIASES: Record<string, string> = {
  calibration: "analyzing",
  waiting_athlete: "analyzing",
  review_video: "scoring",
  running: "queued",
};

function stageIndex(job: JobInfo | null): number {
  if (!job) return 0;
  if (job.status === "done") return PIPELINE.length - 1;
  const key = job.stage_key || "queued";
  const mapped = ALIASES[key] ?? key;
  const i = PIPELINE.indexOf(mapped as (typeof PIPELINE)[number]);
  return i < 0 ? 3 : i; // default to "analyzing"
}

interface Props {
  phase: "uploading" | "processing";
  job: JobInfo | null;
  uploadPct: number;
  onCancel: () => void;
}

export function StatusPanel({ phase, job, uploadPct, onCancel }: Props) {
  const { t, lang } = useLang();
  const isUploading = phase === "uploading";
  const pct = isUploading ? uploadPct : Math.round(job?.progress ?? 0);
  const idx = stageIndex(job);

  const stageText = job
    ? (lang === "fa" ? job.stage_fa : job.stage_en) || t("proc.defaultMsg")
    : t("proc.uploadSub");
  const subtitle = isUploading ? t("proc.uploadSub") : stageText;
  const title = isUploading ? t("proc.uploading") : t("proc.analyzing");

  return (
    <div className="rounded-xl border border-edge bg-panel p-8 space-y-6 text-center">
      <div className="flex justify-center">
        <div className="flex h-16 w-16 items-center justify-center rounded-full bg-brand/10">
          {isUploading ? (
            <UploadCloud className="h-7 w-7 text-brand-fg animate-pulse" />
          ) : (
            <Loader2 className="h-7 w-7 text-brand-fg animate-spin" />
          )}
        </div>
      </div>

      <div className="space-y-1">
        <h3 className="text-lg font-bold text-ink">{title}</h3>
        <p className="text-sm text-ink-3">{subtitle}</p>
      </div>

      {/* progress bar — the v1 red→orange gradient */}
      <div className="space-y-2">
        <div className="h-2 rounded-full bg-chip overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-red-500 to-orange-500 transition-all duration-300"
            style={{ width: `${Math.max(2, pct)}%` }}
          />
        </div>
        <div className="flex items-center justify-between text-xs text-ink-3">
          <span>{isUploading ? t("proc.uploadingLabel") : subtitle}</span>
          <span className="tabular-nums">{pct}%</span>
        </div>
      </div>

      {/* pipeline stepper (v1 numbered-circles look, compact) */}
      {!isUploading && (
        <div className="flex flex-wrap items-center justify-center gap-x-2 gap-y-2">
          {PIPELINE.map((s, i) => (
            <span key={s} className="flex items-center gap-2">
              <span className="flex items-center gap-1.5">
                <span
                  className={cn(
                    "flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-bold transition-colors",
                    i < idx
                      ? "bg-emerald-500 text-white"
                      : i === idx
                        ? "bg-brand text-white animate-pulse"
                        : "bg-chip text-ink-4",
                  )}
                >
                  {i < idx ? <CheckCircle2 className="h-3 w-3" /> : i + 1}
                </span>
                <span
                  className={cn(
                    "text-[11px] font-medium",
                    i === idx ? "text-ink" : "text-ink-4",
                  )}
                >
                  {t(`stage.${s}`)}
                </span>
              </span>
              {i < PIPELINE.length - 1 && (
                <span className="text-ink-4 text-[10px]">›</span>
              )}
            </span>
          ))}
        </div>
      )}

      <Button onClick={onCancel} variant="outline" size="sm" className="gap-1.5 text-xs">
        <X className="h-3.5 w-3.5" />
        {t("proc.cancel")}
      </Button>

      {!isUploading && (
        <p className="text-xs leading-relaxed text-ink-4">{t("proc.hint")}</p>
      )}
    </div>
  );
}
