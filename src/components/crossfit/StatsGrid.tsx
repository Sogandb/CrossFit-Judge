'use client';

import { CheckCircle2, XCircle, Percent, Activity } from 'lucide-react';
import type { JudgeReport } from '@/lib/crossfit-api';

interface Props {
  report: JudgeReport;
}

export function StatsGrid({ report }: Props) {
  const { summary, score } = report;
  const noRepRate =
    summary.total_reps > 0
      ? (summary.no_rep_count / summary.total_reps) * 100
      : 0;

  const stats = [
    {
      label: 'Valid Reps',
      value: summary.valid_reps,
      icon: CheckCircle2,
      color: 'text-emerald-400',
      bg: 'bg-emerald-500/10',
    },
    {
      label: 'No-Reps',
      value: summary.no_rep_count,
      icon: XCircle,
      color: 'text-red-400',
      bg: 'bg-red-500/10',
    },
    {
      label: 'Avg Confidence',
      value: `${Math.round(summary.avg_confidence * 100)}%`,
      icon: Percent,
      color: 'text-orange-400',
      bg: 'bg-orange-500/10',
    },
    {
      label: 'No-Rep Rate',
      value: `${noRepRate.toFixed(0)}%`,
      icon: Activity,
      color: 'text-zinc-300',
      bg: 'bg-zinc-800',
    },
  ];

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      {stats.map((s) => (
        <div
          key={s.label}
          className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4"
        >
          <div className={`flex h-9 w-9 items-center justify-center rounded-lg ${s.bg} mb-3`}>
            <s.icon className={`h-4 w-4 ${s.color}`} />
          </div>
          <p className="text-2xl font-bold tabular-nums text-white">{s.value}</p>
          <p className="text-xs text-zinc-500 mt-0.5">{s.label}</p>
        </div>
      ))}
    </div>
  );
}
