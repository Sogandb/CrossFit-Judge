'use client';

import { useState } from 'react';
import { Play, Video, Image as ImageIcon, Download } from 'lucide-react';
import { annotatedVideoUrl, timelineUrl } from '@/lib/crossfit-api';
import { cn } from '@/lib/utils';

interface Props {
  jobId: string;
}

export function AnnotatedVideoPlayer({ jobId }: Props) {
  const [tab, setTab] = useState<'video' | 'timeline'>('video');
  const videoSrc = annotatedVideoUrl(jobId);
  const timelineSrc = timelineUrl(jobId);

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
        <h3 className="text-sm font-semibold text-white">Review Output</h3>
        <div className="flex gap-1 rounded-lg bg-zinc-800/50 p-0.5">
          <button
            onClick={() => setTab('video')}
            className={cn(
              'flex items-center gap-1.5 rounded-md px-3 py-1 text-xs font-medium transition-colors',
              tab === 'video'
                ? 'bg-zinc-700 text-white'
                : 'text-zinc-400 hover:text-zinc-200',
            )}
          >
            <Video className="h-3.5 w-3.5" />
            Video
          </button>
          <button
            onClick={() => setTab('timeline')}
            className={cn(
              'flex items-center gap-1.5 rounded-md px-3 py-1 text-xs font-medium transition-colors',
              tab === 'timeline'
                ? 'bg-zinc-700 text-white'
                : 'text-zinc-400 hover:text-zinc-200',
            )}
          >
            <ImageIcon className="h-3.5 w-3.5" />
            Timeline
          </button>
        </div>
      </div>

      <div className="p-4 bg-black/30">
        {tab === 'video' ? (
          <div className="space-y-3">
            <video
              src={videoSrc}
              controls
              className="w-full rounded-lg bg-black"
              preload="metadata"
            />
            <p className="text-xs text-zinc-500 flex items-center gap-1.5">
              <Play className="h-3 w-3" />
              Annotated with skeleton overlay, live counter, and per-rep verdicts
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            <img
              src={timelineSrc}
              alt="Rep timeline"
              className="w-full rounded-lg bg-zinc-950"
            />
            <p className="text-xs text-zinc-500 flex items-center gap-1.5">
              <ImageIcon className="h-3 w-3" />
              Green = good rep · Red = no-rep · Dashed line = time cap
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
