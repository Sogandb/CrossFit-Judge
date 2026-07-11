'use client';

import { useState } from 'react';
import { ChevronDown, ChevronRight, Clock } from 'lucide-react';
import type { Workout } from '@/lib/crossfit-api';
import { FORMAT_LABELS } from '@/lib/crossfit-api';
import { cn } from '@/lib/utils';

interface Props {
  workouts: Workout[];
  selected: string | null;
  onSelect: (id: string) => void;
  disabled?: boolean;
  /** Optional content rendered inside the selected workout's category,
   * right below the workout grid. Used to show the upload area inline. */
  children?: React.ReactNode;
}

const FORMAT_ORDER = ['amrap', 'for_time', 'tabata', 'emom', 'max_reps'];
const FORMAT_DESCRIPTIONS: Record<string, string> = {
  amrap: 'As Many Reps As Possible',
  for_time: 'Finish the work as fast as possible',
  tabata: '20s work / 10s rest × 8 rounds',
  emom: 'Every Minute On the Minute',
  max_reps: 'Single movement, maximum reps',
};

export function WorkoutSelector({ workouts, selected, onSelect, disabled, children }: Props) {
  // Default: all categories collapsed. User clicks to expand.
  const [expanded, setExpanded] = useState<Set<string>>(
    () => new Set(),
  );

  const toggle = (format: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(format)) next.delete(format);
      else next.add(format);
      return next;
    });
  };

  const groups: Record<string, Workout[]> = {};
  for (const w of workouts) {
    (groups[w.format] = groups[w.format] || []).push(w);
  }

  // Find which category the selected workout belongs to.
  const selectedFormat = selected
    ? workouts.find((w) => w.id === selected)?.format
    : null;

  return (
    <div className="space-y-2">
      {FORMAT_ORDER.filter((f) => groups[f]).map((format) => {
        const isOpen = expanded.has(format);
        const groupWorkouts = groups[format];
        const hasSelected = groupWorkouts.some((w) => w.id === selected);
        const showInlineUpload = hasSelected && selectedFormat === format && children;

        return (
          <div
            key={format}
            className={cn(
              'rounded-xl border bg-zinc-900/40 transition-colors',
              hasSelected ? 'border-zinc-700' : 'border-zinc-800',
            )}
          >
            {/* Category header (collapsible) */}
            <button
              onClick={() => toggle(format)}
              className="w-full flex items-center gap-3 px-4 py-3 text-left"
            >
              {isOpen ? (
                <ChevronDown className="h-4 w-4 text-zinc-500 shrink-0" />
              ) : (
                <ChevronRight className="h-4 w-4 text-zinc-500 shrink-0" />
              )}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-bold uppercase tracking-wider text-red-400">
                    {FORMAT_LABELS[format] ?? format}
                  </span>
                  <span className="text-[11px] text-zinc-600">
                    ({groupWorkouts.length})
                  </span>
                </div>
                <p className="text-[11px] text-zinc-600 truncate">
                  {FORMAT_DESCRIPTIONS[format]}
                </p>
              </div>
            </button>

            {/* Workouts in this category */}
            {isOpen && (
              <>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5 p-3 pt-0">
                  {groupWorkouts.map((w) => {
                    const active = w.id === selected;
                    return (
                      <button
                        key={w.id}
                        onClick={() => !disabled && onSelect(w.id)}
                        disabled={disabled}
                        className={cn(
                          'text-left rounded-lg border p-3 transition-all duration-200',
                          'disabled:opacity-50 disabled:cursor-not-allowed',
                          active
                            ? 'border-red-500 bg-red-500/10 shadow-lg shadow-red-500/10'
                            : 'border-zinc-800 bg-zinc-900/50 hover:border-zinc-700 hover:bg-zinc-900',
                        )}
                      >
                        <h3 className="font-semibold text-sm text-white leading-tight mb-1.5">
                          {w.name}
                        </h3>
                        <p className="text-[11px] text-zinc-500 line-clamp-2 mb-2 leading-snug">
                          {w.description}
                        </p>
                        <div className="flex items-center gap-1.5 text-[11px] text-zinc-400">
                          <Clock className="h-3 w-3" />
                          {formatTimeCap(w.time_cap_seconds)}
                        </div>
                      </button>
                    );
                  })}
                </div>

                {/* Inline upload area — appears inside the selected
                    category, right below the workout grid. No scrolling
                    needed. */}
                {showInlineUpload && (
                  <div className="px-3 pb-3 pt-1 border-t border-zinc-800/50 mt-1">
                    {children}
                  </div>
                )}
              </>
            )}
          </div>
        );
      })}
    </div>
  );
}

function formatTimeCap(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return s === 0 ? `${m} min` : `${m}m ${s}s`;
}
