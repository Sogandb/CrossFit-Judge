'use client';

import { Dumbbell } from 'lucide-react';

export function Footer() {
  return (
    <footer className="mt-auto border-t border-zinc-800 bg-zinc-950">
      <div className="mx-auto max-w-7xl w-full px-4 sm:px-6 py-4 flex items-center justify-center gap-2 text-xs text-zinc-600">
        <Dumbbell className="h-3.5 w-3.5 text-red-500" />
        <span>CrossFit Judge</span>
      </div>
    </footer>
  );
}
