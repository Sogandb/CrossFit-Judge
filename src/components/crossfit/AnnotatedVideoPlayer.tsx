"use client";

import type { RefObject } from "react";
import { Play, Video } from "lucide-react";
import { reviewVideoUrl } from "./judge-client";
import { useLang } from "@/lib/i18n";

/** v1 AnnotatedVideoPlayer — the "Review Output" card (single video tab). */

interface Props {
  jobId: string;
  videoRef: RefObject<HTMLVideoElement | null>;
}

export function AnnotatedVideoPlayer({ jobId, videoRef }: Props) {
  const { t } = useLang();

  return (
    <div className="rounded-xl border border-edge bg-panel overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-edge">
        <h3 className="text-sm font-semibold text-ink flex items-center gap-2">
          <Video className="h-4 w-4 text-brand" />
          {t("res.reviewOutput")}
        </h3>
      </div>
      <div className="p-4 bg-black/30 space-y-3">
        <video
          ref={videoRef}
          src={reviewVideoUrl(jobId)}
          controls
          playsInline
          preload="metadata"
          className="w-full rounded-lg bg-black"
        />
        <p className="text-xs text-ink-3 flex items-start gap-1.5 leading-relaxed">
          <Play className="h-3 w-3 mt-0.5 shrink-0" />
          {t("res.reviewHint")}
        </p>
      </div>
    </div>
  );
}
