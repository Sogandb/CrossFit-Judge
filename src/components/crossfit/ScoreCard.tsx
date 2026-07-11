'use client';

import { Trophy, Clock, CheckCircle2, XCircle, Layers } from 'lucide-react';
import type { JudgeReport } from '@/lib/crossfit-api';
import { FORMAT_LABELS } from '@/lib/crossfit-api';

interface Props {
  report: JudgeReport;
}

function formatTime(seconds: number | null): string {
  if (seconds == null) return '—';
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toFixed(1).padStart(4, '0')}`;
}

export function ScoreCard({ report }: Props) {
  const { score, workout, sequence } = report;

  return (
    <div className="relative overflow-hidden rounded-2xl border border-zinc-800 bg-gradient-to-br from-zinc-900 to-zinc-950 p-6 sm:p-8">
      {/* glow */}
      <div className="absolute -top-20 -right-20 h-48 w-48 rounded-full bg-red-500/10 blur-3xl" />

      <div className="relative flex flex-col sm:flex-row sm:items-center sm:justify-between gap-6">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <p className="text-xs font-medium uppercase tracking-wider text-red-400">
              Final Score
            </p>
            <span className="rounded bg-zinc-800 text-zinc-400 px-1.5 py-0.5 text-[10px] font-bold uppercase">
              {FORMAT_LABELS[score.format] ?? score.format}
            </span>
            {score.completed ? (
              <span className="inline-flex items-center gap-1 rounded bg-emerald-500/15 text-emerald-400 px-1.5 py-0.5 text-[10px] font-bold">
                <CheckCircle2 className="h-3 w-3" />
                Finished
              </span>
            ) : score.format === 'for_time' ? (
              <span className="inline-flex items-center gap-1 rounded bg-red-500/15 text-red-400 px-1.5 py-0.5 text-[10px] font-bold">
                <XCircle className="h-3 w-3" />
                DNF
              </span>
            ) : null}
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-5xl sm:text-6xl font-bold tabular-nums text-white">
              {score.score_display}
            </span>
          </div>
          <p className="mt-2 text-sm text-zinc-500">{workout.name}</p>
          {sequence && sequence.rounds_completed > 0 && (
            <p className="mt-1 text-xs text-zinc-600">
              <Layers className="inline h-3 w-3 mr-1" />
              {sequence.rounds_completed} round{sequence.rounds_completed !== 1 ? 's' : ''} completed
            </p>
          )}
        </div>

        <div className="flex gap-6 sm:gap-8">
          <div className="text-center">
            <div className="flex h-12 w-12 mx-auto items-center justify-center rounded-xl bg-emerald-500/10 mb-2">
              <Trophy className="h-6 w-6 text-emerald-400" />
            </div>
            <p className="text-2xl font-bold tabular-nums text-white">
              {score.valid_reps}
            </p>
            <p className="text-xs text-zinc-500">Valid reps</p>
          </div>
          <div className="text-center">
            <div className="flex h-12 w-12 mx-auto items-center justify-center rounded-xl bg-zinc-800 mb-2">
              <Clock className="h-6 w-6 text-zinc-400" />
            </div>
            <p className="text-2xl font-bold tabular-nums text-white">
              {formatTime(score.time_seconds)}
            </p>
            <p className="text-xs text-zinc-500">Time</p>
          </div>
        </div>
      </div>
    </div>
  );
}
