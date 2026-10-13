'use client';

import { Dumbbell } from 'lucide-react';

export function Header() {
  return (
    <header className="border-b border-zinc-800 bg-zinc-950/80 backdrop-blur-sm sticky top-0 z-50">
      <div className="mx-auto max-w-7xl w-full px-4 sm:px-6 py-3.5 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-red-500 to-orange-600 shadow-lg shadow-red-500/20">
            <Dumbbell className="h-4.5 w-4.5 text-white" />
          </div>
          <div>
            <h1 className="text-base font-bold tracking-tight text-white leading-none">
              CrossFit Judge
            </h1>
            <p className="text-[11px] text-zinc-500 mt-0.5">
              Automated competition judging
            </p>
          </div>
        </div>
        <div className="hidden sm:flex items-center gap-2 text-xs text-zinc-500">
          <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
          Engine online
        </div>
      </div>
    </header>
  );
}
