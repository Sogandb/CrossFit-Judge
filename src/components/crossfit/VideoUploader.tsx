'use client';

import { useCallback, useRef, useState } from 'react';
import { UploadCloud, FileVideo } from 'lucide-react';
import { cn } from '@/lib/utils';

interface Props {
  onFile: (file: File) => void;
  disabled?: boolean;
  uploading?: boolean;
}

export function VideoUploader({ onFile, disabled }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [file, setFile] = useState<File | null>(null);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      if (disabled) return;
      const f = e.dataTransfer.files?.[0];
      if (f && f.type.startsWith('video/')) {
        setFile(f);
        onFile(f);
      }
    },
    [onFile, disabled],
  );

  const handleSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const f = e.target.files?.[0];
      if (f) {
        setFile(f);
        onFile(f);
      }
    },
    [onFile],
  );

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      onClick={() => !disabled && inputRef.current?.click()}
      className={cn(
        'relative rounded-xl border-2 border-dashed p-8 text-center transition-all cursor-pointer',
        'min-h-[180px] flex flex-col items-center justify-center gap-3',
        dragging
          ? 'border-red-500 bg-red-500/10'
          : 'border-zinc-700 bg-zinc-900/50 hover:border-zinc-600',
        disabled && 'opacity-50 cursor-not-allowed',
      )}
    >
      <input
        ref={inputRef}
        type="file"
        accept="video/*"
        className="hidden"
        onChange={handleSelect}
        disabled={disabled}
      />
      {file ? (
        <>
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-emerald-500/20">
            <FileVideo className="h-6 w-6 text-emerald-400" />
          </div>
          <div className="space-y-1">
            <p className="text-sm font-medium text-white">{file.name}</p>
            <p className="text-xs text-zinc-500">
              {(file.size / (1024 * 1024)).toFixed(1)} MB — click to start analysis
            </p>
          </div>
        </>
      ) : (
        <>
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-zinc-800">
            <UploadCloud className="h-6 w-6 text-zinc-400" />
          </div>
          <div className="space-y-1">
            <p className="text-sm font-medium text-zinc-200">
              Drop your video here, or click to browse
            </p>
            <p className="text-xs text-zinc-500">
              MP4, MOV, or AVI — 45° camera angle recommended
            </p>
          </div>
        </>
      )}
    </div>
  );
}
