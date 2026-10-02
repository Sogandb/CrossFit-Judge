"use client";

import { useCallback, useRef, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import {
  Select, SelectContent, SelectGroup, SelectItem,
  SelectLabel, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { toast } from "@/hooks/use-toast";
import { Upload, FileVideo, X } from "lucide-react";
import type { Division } from "./types";
import { toFa } from "@/lib/fa";

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
  disabled?: boolean;
}

export function UploadForm({ grouped, weightsVerified, onSubmit, disabled }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [division, setDivision] = useState<string>("");
  const [athleteName, setAthleteName] = useState("");
  const [claimedReps, setClaimedReps] = useState("");
  const [timeMode, setTimeMode] = useState<"time" | "capped" | "none">("time");
  const [claimMin, setClaimMin] = useState("");
  const [claimSec, setClaimSec] = useState("");
  const [manualStart, setManualStart] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadPct, setUploadPct] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const pickFile = useCallback((f: File | null) => {
    if (!f) return;
    if (!/\.(mp4|mov|m4v|webm|mkv)$/i.test(f.name)) {
      toast({ title: "فرمت مجاز نیست", description: "فقط MP4 / MOV / WebM", variant: "destructive" });
      return;
    }
    setFile(f);
  }, []);

  const submit = async () => {
    if (!file) {
      toast({ title: "ویدیو انتخاب نشده است", variant: "destructive" });
      return;
    }
    if (!division) {
      toast({ title: "رده سنی را انتخاب کنید", variant: "destructive" });
      return;
    }
    const reps = claimedReps.trim() === "" ? null : Number(claimedReps);
    if (reps != null && (Number.isNaN(reps) || reps < 0 || reps > 126)) {
      toast({ title: "تعداد رپ ادعایی نامعتبر است", variant: "destructive" });
      return;
    }
    let timeSec: number | null = null;
    if (timeMode === "time") {
      const m = Number(claimMin || 0);
      const s = Number(claimSec || 0);
      if (Number.isNaN(m) || Number.isNaN(s) || m * 60 + s <= 0) {
        toast({ title: "زمان ادعایی را درست وارد کنید", variant: "destructive" });
        return;
      }
      timeSec = m * 60 + s;
    }
    const ms = manualStart.trim() === "" ? null : Number(manualStart);
    if (ms != null && (Number.isNaN(ms) || ms < 0)) {
      toast({ title: "لحظه شروع ویدیو (ثانیه) نامعتبر است", variant: "destructive" });
      return;
    }
    setUploading(true);
    setUploadPct(0);
    try {
      const label =
        Object.values(grouped).flat().find((d) => d.id === division)?.label_fa || division;
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
        title: "خطا در ارسال",
        description: e instanceof Error ? e.message : String(e),
        variant: "destructive",
      });
    } finally {
      setUploading(false);
    }
  };

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-xl font-bold">ارسال ویدیو برای داوری</CardTitle>
        <p className="text-sm text-muted-foreground">
          ویدیوی حداکثر {toFa(15)} دقیقه‌ای واد را همراه با امتیاز ادعایی خود ارسال کنید.
        </p>
      </CardHeader>
      <CardContent className="space-y-5">
        {/* video picker */}
        <div>
          <Label>فایل ویدیو</Label>
          <div
            role="button"
            tabIndex={0}
            onClick={() => inputRef.current?.click()}
            onKeyDown={(e) => e.key === "Enter" && inputRef.current?.click()}
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault(); setDragOver(false);
              pickFile(e.dataTransfer.files?.[0] || null);
            }}
            className={`mt-1.5 flex min-h-28 cursor-pointer flex-col items-center justify-center
              gap-2 rounded-lg border-2 border-dashed p-6 text-center transition-colors
              ${dragOver ? "border-red-600 bg-red-50" : "border-zinc-300 hover:border-red-500/60"}`}
          >
            {file ? (
              <>
                <FileVideo className="h-8 w-8 text-red-600" />
                <div className="font-medium">{file.name}</div>
                <div className="text-xs text-muted-foreground">
                  {(file.size / 1024 / 1024).toFixed(1)} مگابایت
                  {" • "}
                  <button
                    className="text-red-600 underline"
                    onClick={(e) => { e.stopPropagation(); setFile(null); }}
                  >حذف</button>
                </div>
              </>
            ) : (
              <>
                <Upload className="h-8 w-8 text-muted-foreground" />
                <div className="font-medium">ویدیو را اینجا رها کنید یا کلیک کنید</div>
                <div className="text-xs text-muted-foreground">MP4 / MOV / WebM — حداکثر ۱۵ دقیقه</div>
              </>
            )}
          </div>
          <input
            ref={inputRef}
            type="file"
            accept="video/mp4,video/quicktime,video/webm,video/x-matroska"
            className="hidden"
            onChange={(e) => pickFile(e.target.files?.[0] || null)}
          />
        </div>

        {/* division */}
        <div>
          <Label>رده سنی / جنسیت</Label>
          <Select value={division} onValueChange={setDivision}>
            <SelectTrigger className="mt-1.5 w-full">
              <SelectValue placeholder="رده خود را انتخاب کنید" />
            </SelectTrigger>
            <SelectContent>
              {Object.entries(grouped).map(([group, items]) => (
                <SelectGroup key={group}>
                  <SelectLabel>{group}</SelectLabel>
                  {items.map((d) => (
                    <SelectItem key={d.id} value={d.id}>
                      {d.label_fa}
                      {d.weight_kg != null && (
                        <span className="text-xs text-muted-foreground">
                          {" "}({toFa(d.weight_kg)} کیلوگرم)
                        </span>
                      )}
                    </SelectItem>
                  ))}
                </SelectGroup>
              ))}
            </SelectContent>
          </Select>
          {!weightsVerified && (
            <p className="mt-1 text-xs text-amber-600">
              وزن میله‌ها پیش‌فرض است و منتظر تأیید رسمی وادکس.
            </p>
          )}
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <Label htmlFor="athlete">نام ورزشکار (اختیاری)</Label>
            <Input id="athlete" className="mt-1.5" value={athleteName}
              onChange={(e) => setAthleteName(e.target.value)}
              placeholder="مثلاً: علی رضایی" />
          </div>
          <div>
            <Label htmlFor="reps">رپ‌های شمرده‌شده توسط خودم</Label>
            <Input id="reps" className="mt-1.5" inputMode="numeric"
              value={claimedReps} onChange={(e) => setClaimedReps(e.target.value)}
              placeholder="مثلاً: 126" />
          </div>
        </div>

        {/* time claim */}
        <div>
          <Label>وضعیت زمانی من</Label>
          <RadioGroup
            value={timeMode}
            onValueChange={(v) => setTimeMode(v as typeof timeMode)}
            className="mt-2 flex flex-wrap gap-4"
          >
            <label className="flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-sm">
              <RadioGroupItem value="time" /> وادی را زیر زمان مجاز تمام کردم
            </label>
            <label className="flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-sm">
              <RadioGroupItem value="capped" /> در زمان مجاز تمام نشد (کپ)
            </label>
            <label className="flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-sm">
              <RadioGroupItem value="none" /> فعلاً نمی‌گویم
            </label>
          </RadioGroup>
          {timeMode === "time" && (
            <div className="mt-2 flex items-center gap-2">
              <Input className="w-24" inputMode="numeric" placeholder="دقیقه"
                value={claimMin} onChange={(e) => setClaimMin(e.target.value)} />
              <span className="text-muted-foreground">:</span>
              <Input className="w-24" inputMode="numeric" placeholder="ثانیه"
                value={claimSec} onChange={(e) => setClaimSec(e.target.value)} />
              <span className="text-xs text-muted-foreground">زمان پایان من</span>
            </div>
          )}
        </div>

        <div>
          <Label htmlFor="mstart" className="flex items-center gap-1">
            لحظه شروع وادی در ویدیو (اختیاری)
          </Label>
          <Input id="mstart" className="mt-1.5 w-40" inputMode="numeric"
            value={manualStart} onChange={(e) => setManualStart(e.target.value)}
            placeholder="ثانیه؛ خالی = خودکار" />
          <p className="mt-1 text-xs text-muted-foreground">
            اگر خالی بمانید، سیستم با تشخیص بوق ۳+۱ تایمر، لحظه شروع را پیدا می‌کند.
          </p>
        </div>

        {uploading && (
          <div className="space-y-1">
            <div className="flex items-center justify-between text-sm">
              <span>در حال آپلود…</span>
              <span>{toFa(uploadPct)}%</span>
            </div>
            <Progress value={uploadPct} className="h-2" />
          </div>
        )}

        <div className="flex items-center gap-3">
          <Button size="lg" className="bg-red-600 hover:bg-red-700"
            onClick={submit} disabled={disabled || uploading || !file || !division}>
            {uploading ? "در حال ارسال…" : "شروع تحلیل"}
          </Button>
          {file && (
            <Badge variant="outline" className="gap-1">
              <X className="h-3 w-3" /> {file.name.slice(0, 24)}
              {file.name.length > 24 ? "…" : ""}
            </Badge>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
