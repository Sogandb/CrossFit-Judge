"use client";

import { useCallback, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import {
  Select, SelectContent, SelectGroup, SelectItem,
  SelectLabel, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { toast } from "@/hooks/use-toast";
import { UploadCloud, FileVideo, X } from "lucide-react";
import type { Division } from "./types";
import { useLang } from "@/lib/i18n";
import { cn } from "@/lib/utils";

export interface SubmitPayload {
  file: File;
  division: string;
  divisionLabel: string;
  athleteName: string;
  claimedReps: number | null;
  claimedTimeSec: number | null;
  claimedCapped: boolean;
  manualStartSec: number | null;
}

interface Props {
  grouped: Record<string, Division[]>;
  weightsVerified: boolean;
  onSubmit: (p: SubmitPayload, onProgress: (pct: number) => void) => Promise<void>;
  onCancelUpload?: () => void;
  disabled?: boolean;
}

type TimeMode = "time" | "capped" | "none";

const MAX_UPLOAD_MB = 500;   // Wodx: videos up to 500 MB
const MAX_VIDEO_MIN = 15;    // ... and 15 minutes

export function UploadForm({ grouped, weightsVerified, onSubmit, onCancelUpload, disabled }: Props) {
  const { t } = useLang();
  const [file, setFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [division, setDivision] = useState<string>("");
  const [athleteName, setAthleteName] = useState("");
  const [claimedReps, setClaimedReps] = useState("");
  const [timeMode, setTimeMode] = useState<TimeMode>("time");
  const [claimMin, setClaimMin] = useState("");
  const [claimSec, setClaimSec] = useState("");
  const [manualStartMin, setManualStartMin] = useState("");
  const [manualStartSec, setManualStartSec] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadPct, setUploadPct] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const pickFile = useCallback((f: File | null) => {
    if (!f) return;
    if (!/\.(mp4|mov|m4v|webm|mkv)$/i.test(f.name)) {
      toast({ title: t("form.errFile"), variant: "destructive" });
      return;
    }
    if (f.size > MAX_UPLOAD_MB * 1024 * 1024) {
      toast({
        title: t("form.errSize"),
        description: `${(f.size / 1048576).toFixed(0)} MB > ${MAX_UPLOAD_MB} MB`,
        variant: "destructive",
      });
      return;
    }
    setFile(f);
    // Best-effort duration check (browsers that cannot decode the codec just
    // skip it; the server re-validates authoritatively).
    try {
      const url = URL.createObjectURL(f);
      const v = document.createElement("video");
      v.preload = "metadata";
      v.onloadedmetadata = () => {
        URL.revokeObjectURL(url);
        if (isFinite(v.duration) && v.duration > MAX_VIDEO_MIN * 60 + 1) {
          setFile(null);
          toast({
            title: t("form.errDuration"),
            description: `${(v.duration / 60).toFixed(1)} min > ${MAX_VIDEO_MIN} min`,
            variant: "destructive",
          });
        }
      };
      v.onerror = () => URL.revokeObjectURL(url);
      v.src = url;
    } catch { /* ignore */ }
  }, [t]);

  const submit = async () => {
    if (!file) {
      toast({ title: t("form.errFile"), variant: "destructive" });
      return;
    }
    if (!division) {
      toast({ title: t("form.errDivision"), variant: "destructive" });
      return;
    }
    const reps = claimedReps.trim() === "" ? null : Number(claimedReps);
    if (reps != null && (Number.isNaN(reps) || reps < 0 || reps > 126)) {
      toast({ title: t("form.errReps"), variant: "destructive" });
      return;
    }
    let timeSec: number | null = null;
    if (timeMode === "time") {
      const m = Number(claimMin || 0);
      const s = Number(claimSec || 0);
      if (Number.isNaN(m) || Number.isNaN(s) || m * 60 + s <= 0) {
        toast({ title: t("form.errTime"), variant: "destructive" });
        return;
      }
      timeSec = m * 60 + s;
    }
    const mMin = Number(manualStartMin || 0);
    const mSec = Number(manualStartSec || 0);
    const ms = (manualStartMin.trim() === "" && manualStartSec.trim() === "")
      ? null
      : mMin * 60 + mSec;
    if (ms != null && (Number.isNaN(mMin) || Number.isNaN(mSec) || ms < 0)) {
      toast({ title: t("form.errManualStart"), variant: "destructive" });
      return;
    }
    setUploading(true);
    setUploadPct(0);
    try {
      const label =
        Object.values(grouped).flat().find((d) => d.id === division)?.label_en || division;
      await onSubmit(
        {
          file, division, divisionLabel: label, athleteName,
          claimedReps: reps,
          claimedTimeSec: timeMode === "time" ? timeSec : null,
          claimedCapped: timeMode === "capped",
          manualStartSec: ms,
        },
        setUploadPct,
      );
    } catch (e) {
      toast({
        title: t("form.uploadFailed"),
        description: e instanceof Error ? e.message : String(e),
        variant: "destructive",
      });
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="space-y-5">
      {/* v1 uploader heading */}
      <div className="flex flex-wrap items-center gap-2">
        <UploadCloud className="h-4 w-4 text-brand" />
        <h3 className="text-sm font-semibold text-ink">{t("form.uploadTitle")}</h3>
        <span className="text-xs text-ink-3">
          for <span className="text-ink-2">Thruster &amp; Bar-Facing Burpee Ladder</span>
        </span>
      </div>

      {/* v1 dropzone */}
      <div
        role="button"
        tabIndex={0}
        aria-label={t("form.dropHere")}
        onClick={() => !disabled && !uploading && inputRef.current?.click()}
        onKeyDown={(e) => e.key === "Enter" && !disabled && !uploading && inputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); if (!disabled && !uploading) setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          if (!disabled && !uploading) pickFile(e.dataTransfer.files?.[0] || null);
        }}
        className={cn(
          "relative min-h-[180px] flex flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed p-8 text-center transition-all cursor-pointer",
          dragOver
            ? "border-brand bg-brand/10"
            : "border-edge-2 bg-panel-2/50 hover:border-ink-4",
          (disabled || uploading) && "opacity-60 cursor-not-allowed",
        )}
      >
        <input
          ref={inputRef}
          type="file"
          accept="video/mp4,video/quicktime,video/webm,video/x-matroska"
          className="hidden"
          onChange={(e) => pickFile(e.target.files?.[0] || null)}
        />
        {file ? (
          <>
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-emerald-500/15">
              <FileVideo className="h-6 w-6 text-emerald-500" />
            </div>
            <div className="space-y-1">
              <p className="text-sm font-medium text-ink">{file.name}</p>
              <p className="text-xs text-ink-3">
                {(file.size / 1024 / 1024).toFixed(1)} MB
                {" — "}
                <button
                  className="text-brand-fg underline underline-offset-2"
                  onClick={(e) => { e.stopPropagation(); setFile(null); }}
                >
                  {t("form.remove")}
                </button>
              </p>
            </div>
          </>
        ) : (
          <>
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-chip">
              <UploadCloud className="h-6 w-6 text-ink-3" />
            </div>
            <div className="space-y-1">
              <p className="text-sm font-medium text-ink-2">{t("form.dropHere")}</p>
              <p className="text-xs text-ink-3">{t("form.dropHint")}</p>
            </div>
          </>
        )}
      </div>

      {/* division */}
      <div className="space-y-1.5">
        <Label className="text-xs font-semibold text-ink-2">{t("form.division")}</Label>
        <Select value={division} onValueChange={setDivision} disabled={disabled || uploading}>
          <SelectTrigger className="w-full bg-panel">
            <SelectValue placeholder={t("form.divisionPlaceholder")} />
          </SelectTrigger>
          <SelectContent>
            {Object.entries(grouped).map(([group, items]) => (
              <SelectGroup key={group}>
                <SelectLabel>{group}</SelectLabel>
                {items.map((d) => (
                  <SelectItem key={d.id} value={d.id}>
                    {d.label_en}
                    {d.weight_kg != null && (
                      <span className="text-xs text-muted-foreground">
                        {" "}({d.weight_kg} kg)
                      </span>
                    )}
                  </SelectItem>
                ))}
              </SelectGroup>
            ))}
          </SelectContent>
        </Select>
        {!weightsVerified && (
          <p className="text-xs text-amber-500">{t("form.weightsNote")}</p>
        )}
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="athlete" className="text-xs font-semibold text-ink-2">
            {t("form.athlete")}
          </Label>
          <Input
            id="athlete"
            className="bg-panel"
            value={athleteName}
            onChange={(e) => setAthleteName(e.target.value)}
            placeholder={t("form.athletePlaceholder")}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="reps" className="text-xs font-semibold text-ink-2">
            {t("form.claimedReps")}
          </Label>
          <Input
            id="reps"
            className="bg-panel"
            inputMode="numeric"
            value={claimedReps}
            onChange={(e) => setClaimedReps(e.target.value)}
            placeholder={t("form.claimedRepsPlaceholder")}
          />
        </div>
      </div>

      {/* time claim */}
      <div className="space-y-2">
        <Label className="text-xs font-semibold text-ink-2">{t("form.timeClaim")}</Label>
        <RadioGroup
          value={timeMode}
          onValueChange={(v) => setTimeMode(v as TimeMode)}
          className="grid gap-2 sm:grid-cols-3"
        >
          {(["time", "capped", "none"] as const).map((mode) => (
            <label
              key={mode}
              className={cn(
                "flex cursor-pointer items-center gap-2.5 rounded-lg border px-3 py-2.5 text-[13px] transition-all",
                timeMode === mode
                  ? "border-brand bg-brand/10 text-ink"
                  : "border-edge bg-panel text-ink-2 hover:border-edge-2",
              )}
            >
              <RadioGroupItem value={mode} />
              {t(mode === "time" ? "form.timeFinished" : mode === "capped" ? "form.timeCapped" : "form.timeNone")}
            </label>
          ))}
        </RadioGroup>
        {timeMode === "time" && (
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <Input
              className="w-24 bg-panel text-center tabular-nums"
              inputMode="numeric"
              placeholder={t("form.minutes")}
              aria-label={t("form.minutes")}
              value={claimMin}
              onChange={(e) => setClaimMin(e.target.value)}
            />
            <span className="text-ink-3">:</span>
            <Input
              className="w-24 bg-panel text-center tabular-nums"
              inputMode="numeric"
              placeholder={t("form.seconds")}
              aria-label={t("form.seconds")}
              value={claimSec}
              onChange={(e) => setClaimSec(e.target.value)}
            />
          </div>
        )}
      </div>

      {/* manual start */}
      <div className="space-y-1.5">
        <Label htmlFor="mstart-m" className="text-xs font-semibold text-ink-2">
          {t("form.manualStart")}
        </Label>
        <div className="flex items-center gap-2">
          <Input
            id="mstart-m"
            className="w-20 bg-panel text-center tabular-nums"
            inputMode="numeric"
            value={manualStartMin}
            onChange={(e) => setManualStartMin(e.target.value.replace(/\D/g, "").slice(0, 2))}
            placeholder="mm"
            aria-label={t("form.minutes")}
          />
          <span className="text-ink-3">:</span>
          <Input
            id="mstart-s"
            className="w-20 bg-panel text-center tabular-nums"
            inputMode="numeric"
            value={manualStartSec}
            onChange={(e) => setManualStartSec(e.target.value.replace(/\D/g, "").slice(0, 2))}
            placeholder="ss"
            aria-label={t("form.seconds")}
          />
        </div>
        <p className="text-xs text-ink-3">{t("form.manualStartHint")}</p>
      </div>

      {uploading && (
        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs text-ink-3">
            <span>{t("proc.uploadingLabel")}</span>
            <span className="tabular-nums">
              {uploadPct}%{file ? ` · ${((uploadPct / 100) * file.size / 1048576).toFixed(1)} / ${(file.size / 1048576).toFixed(1)} MB` : ""}
            </span>
          </div>
          <Progress value={uploadPct} className="h-2" />
          <p className="text-[11px] leading-relaxed text-ink-4">
            {t("proc.uploadChunkHint")}
          </p>
          {onCancelUpload && (
            <Button
              onClick={onCancelUpload}
              variant="outline"
              size="sm"
              className="gap-1.5 text-xs"
            >
              <X className="h-3.5 w-3.5" />
              {t("proc.cancel")}
            </Button>
          )}
        </div>
      )}

      <Button
        size="lg"
        className="w-full gap-2 bg-brand text-white hover:bg-brand/90 sm:w-auto"
        onClick={submit}
        disabled={disabled || uploading || !file || !division}
      >
        {uploading ? (
          <><span className="h-4 w-4 animate-pulse" />{t("form.submitting")}</>
        ) : (
          <><UploadCloud className="h-4 w-4" />{t("form.start")}</>
        )}
      </Button>
    </div>
  );
}
