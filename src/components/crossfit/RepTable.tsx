'use client';

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { CheckCircle2, XCircle, AlertTriangle } from 'lucide-react';
import type { RepEvent } from '@/lib/crossfit-api';
import { MOVEMENT_LABELS } from '@/lib/crossfit-api';

interface Props {
  reps: RepEvent[];
}

function formatTs(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toFixed(1).padStart(4, '0')}`;
}

function confidenceLevel(c: number): { label: string; color: string } {
  if (c >= 0.8) return { label: 'High', color: 'text-emerald-400' };
  if (c >= 0.5) return { label: 'Medium', color: 'text-orange-400' };
  return { label: 'Low', color: 'text-red-400' };
}

export function RepTable({ reps }: Props) {
  if (reps.length === 0) {
    return (
      <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-8 text-center">
        <AlertTriangle className="h-8 w-8 text-zinc-600 mx-auto mb-3" />
        <p className="text-sm text-zinc-400">No reps were detected in this video.</p>
        <p className="text-xs text-zinc-600 mt-1">
          Make sure the athlete is fully visible from a 45° angle.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 overflow-hidden">
      <div className="px-4 py-3 border-b border-zinc-800">
        <h3 className="text-sm font-semibold text-white">
          Rep-by-Rep Breakdown
        </h3>
        <p className="text-xs text-zinc-500 mt-0.5">
          {reps.length} total attempts · no-rep reasons included
        </p>
      </div>
      <div className="max-h-[420px] overflow-y-auto">
        <Table>
          <TableHeader>
            <TableRow className="border-zinc-800 hover:bg-transparent">
              <TableHead className="text-zinc-400 text-xs">#</TableHead>
              <TableHead className="text-zinc-400 text-xs">Verdict</TableHead>
              <TableHead className="text-zinc-400 text-xs">Movement</TableHead>
              <TableHead className="text-zinc-400 text-xs">Time</TableHead>
              <TableHead className="text-zinc-400 text-xs">Confidence</TableHead>
              <TableHead className="text-zinc-400 text-xs">Reason</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {reps.map((rep) => {
              const conf = confidenceLevel(rep.confidence);
              const reason = rep.no_rep_reason_en || rep.no_rep_reason_fa;
              return (
                <TableRow
                  key={rep.rep_number}
                  className="border-zinc-800/70 hover:bg-zinc-800/30"
                >
                  <TableCell className="font-mono text-xs text-zinc-400">
                    {rep.rep_number}
                  </TableCell>
                  <TableCell>
                    {rep.valid ? (
                      <span className="inline-flex items-center gap-1.5 text-xs font-medium text-emerald-400">
                        <CheckCircle2 className="h-3.5 w-3.5" />
                        Good
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1.5 text-xs font-medium text-red-400">
                        <XCircle className="h-3.5 w-3.5" />
                        No-Rep
                      </span>
                    )}
                  </TableCell>
                  <TableCell className="text-xs text-zinc-300">
                    {MOVEMENT_LABELS[rep.movement] ?? rep.movement}
                  </TableCell>
                  <TableCell className="text-xs text-zinc-400 font-mono">
                    {formatTs(rep.end_time)}
                  </TableCell>
                  <TableCell>
                    <span className={`text-xs font-medium ${conf.color}`}>
                      {conf.label}
                    </span>
                    <span className="text-xs text-zinc-600 ml-1">
                      ({Math.round(rep.confidence * 100)}%)
                    </span>
                  </TableCell>
                  <TableCell className="text-xs text-zinc-400 max-w-xs">
                    {reason ? (
                      <span className="text-red-300/90">{reason}</span>
                    ) : (
                      <span className="text-zinc-600">—</span>
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
