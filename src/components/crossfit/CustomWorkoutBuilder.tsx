'use client';

import { useEffect, useState } from 'react';
import { Settings2, Plus, Check } from 'lucide-react';
import type { CustomWorkoutParams } from '@/lib/crossfit-api';
import { fetchMovements, FORMAT_LABELS, MOVEMENT_LABELS } from '@/lib/crossfit-api';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

interface Props {
  onAnalyze: (params: CustomWorkoutParams) => void;
  disabled?: boolean;
}

const FORMATS = ['amrap', 'for_time', 'tabata', 'emom', 'max_reps'];

export function CustomWorkoutBuilder({ onAnalyze, disabled }: Props) {
  const [movements, setMovements] = useState<string[]>([]);
  const [selected, setSelected] = useState<string[]>(['squat']);
  const [name, setName] = useState('My Custom Workout');
  const [format, setFormat] = useState('amrap');
  const [timeCap, setTimeCap] = useState(60);

  useEffect(() => {
    fetchMovements()
      .then(setMovements)
      .catch(() => setMovements(['squat', 'pushup', 'burpee', 'thruster', 'pullup', 'kettlebell_swing']));
  }, []);

  const toggleMovement = (m: string) => {
    setSelected((prev) =>
      prev.includes(m) ? prev.filter((x) => x !== m) : [...prev, m],
    );
  };

  const handleSubmit = () => {
    if (selected.length === 0) return;
    onAnalyze({
      workoutName: name || 'Custom Workout',
      format,
      timeCapSeconds: timeCap,
      movements: selected,
    });
  };

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-5 space-y-4">
      <div className="flex items-center gap-2 text-sm font-medium text-zinc-300">
        <Settings2 className="h-4 w-4 text-red-500" />
        Custom Workout Builder
      </div>
      <p className="text-xs text-zinc-500 -mt-2">
        Define your own workout to analyse any competition footage.
      </p>

      {/* Name + format + time cap */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="space-y-1.5">
          <label className="text-[11px] font-medium text-zinc-400">Workout Name</label>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="My Custom Workout"
            className="bg-zinc-950 border-zinc-800 text-sm"
            disabled={disabled}
          />
        </div>
        <div className="space-y-1.5">
          <label className="text-[11px] font-medium text-zinc-400">Format</label>
          <Select value={format} onValueChange={setFormat} disabled={disabled}>
            <SelectTrigger className="bg-zinc-950 border-zinc-800 text-sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {FORMATS.map((f) => (
                <SelectItem key={f} value={f}>
                  {FORMAT_LABELS[f] ?? f}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <label className="text-[11px] font-medium text-zinc-400">Time Cap (seconds)</label>
          <Input
            type="number"
            min={10}
            max={3600}
            value={timeCap}
            onChange={(e) => setTimeCap(Math.max(10, Math.min(3600, Number(e.target.value) || 60)))}
            className="bg-zinc-950 border-zinc-800 text-sm"
            disabled={disabled}
          />
        </div>
      </div>

      {/* Movement selection */}
      <div className="space-y-2">
        <label className="text-[11px] font-medium text-zinc-400">
          Movements ({selected.length} selected)
        </label>
        <div className="flex flex-wrap gap-2">
          {movements.map((m) => {
            const active = selected.includes(m);
            return (
              <button
                key={m}
                onClick={() => !disabled && toggleMovement(m)}
                disabled={disabled}
                className={cn(
                  'inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition-all',
                  active
                    ? 'border-red-500 bg-red-500/15 text-red-300'
                    : 'border-zinc-700 bg-zinc-800/50 text-zinc-400 hover:border-zinc-600',
                  disabled && 'opacity-50 cursor-not-allowed',
                )}
              >
                {active && <Check className="h-3 w-3" />}
                {MOVEMENT_LABELS[m] ?? m}
              </button>
            );
          })}
        </div>
      </div>

      <Button
        onClick={handleSubmit}
        disabled={disabled || selected.length === 0}
        className="w-full gap-2 bg-red-600 hover:bg-red-700 text-white"
      >
        <Plus className="h-4 w-4" />
        Build & Upload Video
      </Button>
    </div>
  );
}
