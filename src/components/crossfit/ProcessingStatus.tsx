'use client';

import { Loader2, CheckCircle2, XCircle } from 'lucide-react';
import { Progress } from '@/components/ui/progress';

interface Props {
  status: 'uploading' | 'processing' | 'completed' | 'failed';
  progress: number;
  message: string;
  error?: string;
}

export function ProcessingStatus({ status, progress, message, error }: Props) {
  const icon =
    status === 'completed' ? (
      <CheckCircle2 className="h-6 w-6 text-emerald-400" />
    ) : status === 'failed' ? (
      <XCircle className="h-6 w-6 text-red-400" />
    ) : (
      <Loader2 className="h-6 w-6 text-red-400 animate-spin" />
    );

  const title =
    status === 'uploading'
      ? 'Uploading video...'
      : status === 'processing'
        ? message || 'Analyzing movement...'
        : status === 'completed'
          ? 'Analysis complete'
          : 'Analysis failed';

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6 space-y-4">
      <div className="flex items-center gap-3">
        {icon}
        <div className="flex-1">
          <p className="text-sm font-medium text-white">{title}</p>
          <p className="text-xs text-zinc-500">
            {status === 'processing'
              ? 'Running pose detection & movement analysis'
              : status === 'uploading'
                ? 'Sending video to the judge engine'
                : status === 'failed'
                  ? error || 'An error occurred'
                  : 'Results are ready below'}
          </p>
        </div>
        <span className="text-2xl font-bold tabular-nums text-zinc-300">
          {Math.round(progress * 100)}%
        </span>
      </div>
      {(status === 'uploading' || status === 'processing') && (
        <Progress value={progress * 100} className="h-2 bg-zinc-800" />
      )}
    </div>
  );
}
