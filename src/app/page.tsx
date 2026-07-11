'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import {
  Dumbbell,
  RotateCcw,
  Layers,
  Settings2,
  UploadCloud,
  PlayCircle,
  CheckCircle2,
  Circle,
  XCircle,
  Loader2,
  X,
} from 'lucide-react';
import { Header } from '@/components/crossfit/Header';
import { Footer } from '@/components/crossfit/Footer';
import { WorkoutSelector } from '@/components/crossfit/WorkoutSelector';
import { VideoUploader } from '@/components/crossfit/VideoUploader';
import { CustomWorkoutBuilder } from '@/components/crossfit/CustomWorkoutBuilder';
import { ScoreCard } from '@/components/crossfit/ScoreCard';
import { StatsGrid } from '@/components/crossfit/StatsGrid';
import { RepTable } from '@/components/crossfit/RepTable';
import { AnnotatedVideoPlayer } from '@/components/crossfit/AnnotatedVideoPlayer';
import {
  fetchWorkouts,
  uploadVideo,
  uploadCustomVideo,
  pollStatus,
  fetchResults,
  runDemo,
  FORMAT_LABELS,
  MOVEMENT_LABELS,
  type Workout,
  type JudgeReport,
  type CustomWorkoutParams,
} from '@/lib/crossfit-api';
import { cn } from '@/lib/utils';

type Phase = 'idle' | 'uploading' | 'processing' | 'completed' | 'failed';
type Mode = 'preset' | 'custom';

export default function Home() {
  const [workouts, setWorkouts] = useState<Workout[]>([]);
  const [mode, setMode] = useState<Mode>('preset');
  const [selectedWorkout, setSelectedWorkout] = useState<string | null>(null);
  const [customParams, setCustomParams] = useState<CustomWorkoutParams | null>(null);
  const [phase, setPhase] = useState<Phase>('idle');
  const [progress, setProgress] = useState(0);
  const [statusMsg, setStatusMsg] = useState('');
  const [uploadProgress, setUploadProgress] = useState<{
    received: number;
    total: number;
  } | null>(null);
  const [error, setError] = useState<string | undefined>();
  const [report, setReport] = useState<JudgeReport | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    fetchWorkouts()
      .then(setWorkouts)
      .catch((e) => console.error('Failed to load workouts', e));
  }, []);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const startPolling = useCallback(
    (id: string) => {
      stopPolling();
      const startTime = Date.now();
      const MAX_POLL_MS = 5 * 60 * 1000; // 5-minute hard limit
      let consecutiveErrors = 0;

      pollRef.current = setInterval(async () => {
        // Hard timeout: if we've been polling for 5 minutes, give up.
        if (Date.now() - startTime > MAX_POLL_MS) {
          stopPolling();
          setError(
            'Analysis is taking too long (over 5 minutes). The video may be too long or complex. ' +
              'Try a shorter clip (under 60 seconds).',
          );
          setPhase('failed');
          return;
        }

        try {
          const st = await pollStatus(id);
          consecutiveErrors = 0; // reset on success
          setProgress(st.progress);
          setStatusMsg(st.status_message);
          if (st.status === 'completed') {
            stopPolling();
            try {
              const rpt = await fetchResults(id);
              setReport(rpt);
              setPhase('completed');
            } catch (e) {
              setError(
                e instanceof Error
                  ? `Results fetch failed: ${e.message}`
                  : 'Failed to fetch results',
              );
              setPhase('failed');
            }
          } else if (st.status === 'failed') {
            stopPolling();
            setError(st.error || 'Processing failed');
            setPhase('failed');
          }
        } catch (e) {
          consecutiveErrors++;
          console.error('Polling error', e);
          // If we get 5 consecutive errors, the server is probably down.
          if (consecutiveErrors >= 5) {
            stopPolling();
            setError(
              'Lost connection to the analysis server. It may have crashed during processing. ' +
                'Please try again — if the problem persists, try a shorter or re-encoded video.',
            );
            setPhase('failed');
          }
        }
      }, 2000);
    },
    [stopPolling],
  );

  useEffect(
    () => () => {
      stopPolling();
      abortRef.current?.abort();
    },
    [stopPolling],
  );

  const handleFile = useCallback(
    async (file: File) => {
      const workoutId = mode === 'preset' ? selectedWorkout : null;
      const params = mode === 'custom' ? customParams : null;
      if (!workoutId && !params) {
        setError(
          mode === 'preset'
            ? 'Please select a workout first.'
            : 'Please build a custom workout first.',
        );
        return;
      }
      setError(undefined);
      setPhase('uploading');
      setProgress(0.02);
      setStatusMsg('Uploading video...');
      setUploadProgress({ received: 0, total: file.size });
      abortRef.current = new AbortController();
      try {
        const { job_id } = params
          ? await uploadCustomVideo(
              file,
              params,
              abortRef.current.signal,
              (received, total) =>
                setUploadProgress({ received, total }),
            )
          : await uploadVideo(
              file,
              workoutId!,
              abortRef.current.signal,
              (received, total) =>
                setUploadProgress({ received, total }),
            );
        setJobId(job_id);
        setUploadProgress(null);
        setPhase('processing');
        setProgress(0.1);
        setStatusMsg('Starting analysis...');
        startPolling(job_id);
      } catch (e: unknown) {
        setUploadProgress(null);
        if (e instanceof DOMException && e.name === 'AbortError') {
          setPhase('idle');
          setProgress(0);
          setStatusMsg('');
          return;
        }
        if (e instanceof Error && e.name === 'TimeoutError') {
          setError('Upload timed out. The video may be too large or the server is busy. Please try again.');
        } else {
          setError(e instanceof Error ? e.message : 'Upload failed');
        }
        setPhase('failed');
      }
    },
    [mode, selectedWorkout, customParams, startPolling],
  );

  const handleCancel = useCallback(() => {
    abortRef.current?.abort();
    stopPolling();
    setPhase('idle');
    setProgress(0);
    setStatusMsg('');
    setUploadProgress(null);
    setError(undefined);
  }, [stopPolling]);

  const handleReset = useCallback(() => {
    stopPolling();
    abortRef.current?.abort();
    setPhase('idle');
    setProgress(0);
    setStatusMsg('');
    setUploadProgress(null);
    setError(undefined);
    setReport(null);
    setJobId(null);
  }, [stopPolling]);

  const handleDemo = useCallback(async () => {
    if (!selectedWorkout) {
      setError('Please select a workout first.');
      return;
    }
    setError(undefined);
    setPhase('processing');
    setProgress(0.05);
    setStatusMsg('Generating demo video...');
    try {
      const { job_id } = await runDemo(selectedWorkout);
      setJobId(job_id);
      setProgress(0.15);
      setStatusMsg('Running demo analysis...');
      startPolling(job_id);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Demo failed');
      setPhase('failed');
    }
  }, [selectedWorkout, startPolling]);

  const handleCustomBuild = useCallback((params: CustomWorkoutParams) => {
    setCustomParams(params);
    setMode('custom');
    setError(undefined);
  }, []);

  const canUpload = mode === 'preset' ? !!selectedWorkout : !!customParams;
  const isWorking = phase === 'uploading' || phase === 'processing';

  // Current step: 1=select, 2=upload, 3=results
  const currentStep = phase === 'completed' ? 3 : isWorking ? 2 : 1;

  // Selected workout info for sidebar summary
  const selectedWorkoutInfo = workouts.find((w) => w.id === selectedWorkout);

  return (
    <div className="min-h-screen flex flex-col bg-zinc-950 text-zinc-100">
      <Header />

      <div className="flex-1 mx-auto w-full max-w-7xl flex">
        {/* ===== Sidebar ===== */}
        <aside className="w-72 shrink-0 border-r border-zinc-800 bg-zinc-950 hidden md:flex flex-col">
          <div className="p-5 space-y-5 flex-1 overflow-y-auto">
            {/* Steps indicator */}
            <div className="space-y-3">
              <p className="text-[11px] font-bold uppercase tracking-wider text-zinc-500">
                Workflow
              </p>
              <div className="space-y-2.5">
                <StepIndicator
                  step={1}
                  label="Choose Workout"
                  active={currentStep === 1}
                  done={currentStep > 1}
                />
                <StepIndicator
                  step={2}
                  label="Upload & Analyze"
                  active={currentStep === 2}
                  done={currentStep > 2}
                />
                <StepIndicator
                  step={3}
                  label="Review Results"
                  active={currentStep === 3}
                  done={currentStep > 3}
                />
              </div>
            </div>

            <div className="h-px bg-zinc-800" />

            {/* Mode toggle */}
            <div className="space-y-2">
              <p className="text-[11px] font-bold uppercase tracking-wider text-zinc-500">
                Source
              </p>
              <div className="flex gap-1 rounded-lg bg-zinc-900 border border-zinc-800 p-1">
                <button
                  onClick={() => !isWorking && setMode('preset')}
                  disabled={isWorking}
                  className={cn(
                    'flex-1 flex items-center justify-center gap-1.5 rounded-md px-2 py-1.5 text-xs font-medium transition-all',
                    mode === 'preset'
                      ? 'bg-red-600 text-white'
                      : 'text-zinc-400 hover:text-zinc-200',
                    isWorking && 'opacity-50 cursor-not-allowed',
                  )}
                >
                  <Layers className="h-3.5 w-3.5" />
                  Preset
                </button>
                <button
                  onClick={() => !isWorking && setMode('custom')}
                  disabled={isWorking}
                  className={cn(
                    'flex-1 flex items-center justify-center gap-1.5 rounded-md px-2 py-1.5 text-xs font-medium transition-all',
                    mode === 'custom'
                      ? 'bg-red-600 text-white'
                      : 'text-zinc-400 hover:text-zinc-200',
                    isWorking && 'opacity-50 cursor-not-allowed',
                  )}
                >
                  <Settings2 className="h-3.5 w-3.5" />
                  Custom
                </button>
              </div>
            </div>

            {/* Selection summary */}
            <div className="space-y-2">
              <p className="text-[11px] font-bold uppercase tracking-wider text-zinc-500">
                Selection
              </p>
              {mode === 'preset' && selectedWorkoutInfo ? (
                <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3 space-y-1.5">
                  <p className="text-sm font-semibold text-white leading-tight">
                    {selectedWorkoutInfo.name}
                  </p>
                  <div className="flex items-center gap-2 text-[11px]">
                    <span className="rounded bg-red-500/15 text-red-400 px-1.5 py-0.5 font-bold uppercase">
                      {FORMAT_LABELS[selectedWorkoutInfo.format] ?? selectedWorkoutInfo.format}
                    </span>
                    <span className="text-zinc-500">
                      {formatTimeCap(selectedWorkoutInfo.time_cap_seconds)}
                    </span>
                  </div>
                </div>
              ) : mode === 'custom' && customParams ? (
                <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3 space-y-1.5">
                  <p className="text-sm font-semibold text-white leading-tight">
                    {customParams.workoutName}
                  </p>
                  <div className="flex items-center gap-2 text-[11px]">
                    <span className="rounded bg-red-500/15 text-red-400 px-1.5 py-0.5 font-bold uppercase">
                      {FORMAT_LABELS[customParams.format] ?? customParams.format}
                    </span>
                    <span className="text-zinc-500">
                      {formatTimeCap(customParams.timeCapSeconds)}
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-1 pt-1">
                    {customParams.movements.map((m) => (
                      <span
                        key={m}
                        className="text-[10px] rounded bg-zinc-800 text-zinc-400 px-1.5 py-0.5"
                      >
                        {MOVEMENT_LABELS[m] ?? m}
                      </span>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="rounded-lg border border-dashed border-zinc-800 bg-zinc-900/20 p-3 text-center">
                  <p className="text-xs text-zinc-600">
                    {mode === 'preset'
                      ? 'Select a workout from the list →'
                      : 'Build a custom workout →'}
                  </p>
                </div>
              )}
            </div>

            {/* Quick actions */}
            {!isWorking && phase !== 'completed' && canUpload && (
              <div className="space-y-2">
                <p className="text-[11px] font-bold uppercase tracking-wider text-zinc-500">
                  Quick Actions
                </p>
                <button
                  onClick={handleDemo}
                  className="w-full flex items-center justify-center gap-1.5 rounded-lg border border-red-500/30 bg-red-500/5 px-3 py-2 text-xs font-medium text-red-300 hover:bg-red-500/10 transition-all"
                >
                  <PlayCircle className="h-3.5 w-3.5" />
                  Run Demo
                </button>
              </div>
            )}
          </div>
        </aside>

        {/* ===== Main content ===== */}
        <main className="flex-1 min-w-0 overflow-y-auto">
          <div className="p-5 sm:p-8 space-y-6">
            {/* STEP 1: Choose workout */}
            {phase === 'idle' && (
              <>
                <div>
                  <h2 className="text-xl font-bold text-white mb-1">
                    {mode === 'preset' ? 'Choose a Workout' : 'Build a Custom Workout'}
                  </h2>
                  <p className="text-sm text-zinc-500">
                    {mode === 'preset'
                      ? 'Select a preset workout that matches your competition video.'
                      : 'Define your own workout to analyze any competition footage.'}
                  </p>
                </div>

                {/* Mobile mode toggle (sidebar hidden on mobile) */}
                <div className="flex gap-1 rounded-lg bg-zinc-900 border border-zinc-800 p-1 w-fit md:hidden">
                  <button
                    onClick={() => setMode('preset')}
                    className={cn(
                      'flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-all',
                      mode === 'preset' ? 'bg-red-600 text-white' : 'text-zinc-400',
                    )}
                  >
                    <Layers className="h-3.5 w-3.5" />
                    Preset
                  </button>
                  <button
                    onClick={() => setMode('custom')}
                    className={cn(
                      'flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-all',
                      mode === 'custom' ? 'bg-red-600 text-white' : 'text-zinc-400',
                    )}
                  >
                    <Settings2 className="h-3.5 w-3.5" />
                    Custom
                  </button>
                </div>

                {mode === 'preset' ? (
                  <WorkoutSelector
                    workouts={workouts}
                    selected={selectedWorkout}
                    onSelect={setSelectedWorkout}
                  >
                    {/* Inline upload area — rendered inside the selected
                        workout's category, right below the grid. */}
                    {selectedWorkoutInfo && (
                      <div className="space-y-2 pt-2">
                        <div className="flex items-center gap-2">
                          <UploadCloud className="h-4 w-4 text-red-500" />
                          <h3 className="text-sm font-semibold text-white">
                            Upload Your Video
                          </h3>
                          <span className="text-xs text-zinc-500">
                            for <span className="text-zinc-300">{selectedWorkoutInfo.name}</span>
                          </span>
                        </div>
                        <VideoUploader onFile={handleFile} disabled={false} uploading={false} />
                      </div>
                    )}
                  </WorkoutSelector>
                ) : (
                  <>
                    <CustomWorkoutBuilder onAnalyze={handleCustomBuild} />
                    {/* Upload area for custom workouts */}
                    {canUpload && (
                      <div className="space-y-2 pt-2">
                        <div className="flex items-center gap-2">
                          <UploadCloud className="h-4 w-4 text-red-500" />
                          <h3 className="text-sm font-semibold text-white">
                            Upload Your Video
                          </h3>
                          {customParams && (
                            <span className="text-xs text-zinc-500">
                              for <span className="text-zinc-300">{customParams.workoutName}</span>
                            </span>
                          )}
                        </div>
                        <VideoUploader onFile={handleFile} disabled={false} uploading={false} />
                      </div>
                    )}
                  </>
                )}
              </>
            )}

            {/* STEP 2: Uploading / Processing */}
            {(phase === 'uploading' || phase === 'processing') && (
              <div className="max-w-lg mx-auto py-12 space-y-6">
                <ProcessingPanel
                  phase={phase}
                  progress={progress}
                  message={statusMsg}
                  uploadProgress={uploadProgress}
                  onCancel={handleCancel}
                />
              </div>
            )}

            {/* Failed */}
            {phase === 'failed' && (
              <div className="max-w-lg mx-auto py-12 space-y-6">
                <div className="rounded-xl border border-red-500/30 bg-red-500/5 p-6 space-y-3">
                  <div className="flex items-center gap-3">
                    <XCircle className="h-6 w-6 text-red-400" />
                    <div>
                      <p className="text-sm font-semibold text-white">Analysis Failed</p>
                      <p className="text-xs text-zinc-400 mt-0.5">
                        {error || 'An unexpected error occurred.'}
                      </p>
                    </div>
                  </div>
                </div>
                <Button onClick={handleReset} variant="outline" className="gap-2 w-full">
                  <RotateCcw className="h-4 w-4" />
                  Start Over
                </Button>
              </div>
            )}

            {/* STEP 3: Results */}
            {phase === 'completed' && report && jobId && (
              <div className="space-y-6">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-xl font-bold text-white">Judging Results</h2>
                    <p className="text-sm text-zinc-500 mt-0.5">
                      {report.workout.name}
                    </p>
                  </div>
                  <Button onClick={handleReset} variant="outline" size="sm" className="gap-2">
                    <RotateCcw className="h-4 w-4" />
                    New Analysis
                  </Button>
                </div>

                <ScoreCard report={report} />
                <StatsGrid report={report} />

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                  <AnnotatedVideoPlayer jobId={jobId} />
                  <RepTable reps={report.reps} />
                </div>

                {/* Per-movement breakdown */}
                {Object.keys(report.score.per_movement).length > 1 && (
                  <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4">
                    <h3 className="text-sm font-semibold text-white mb-3">
                      Per-Movement Breakdown
                    </h3>
                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                      {Object.entries(report.score.per_movement).map(([move, stats]) => (
                        <div key={move} className="rounded-lg bg-zinc-800/50 p-3">
                          <p className="text-xs font-medium text-zinc-300 capitalize mb-2">
                            {move.replace(/_/g, ' ')}
                          </p>
                          <div className="flex items-baseline gap-3">
                            <span className="text-xl font-bold text-emerald-400">
                              {stats.valid}
                            </span>
                            <span className="text-xs text-zinc-500">
                              / {stats.total} reps
                            </span>
                          </div>
                          {stats.no_rep > 0 && (
                            <p className="text-xs text-red-400 mt-1">{stats.no_rep} no-rep</p>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </main>
      </div>

      <Footer />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helper components
// ---------------------------------------------------------------------------
function StepIndicator({
  step,
  label,
  active,
  done,
}: {
  step: number;
  label: string;
  active: boolean;
  done: boolean;
}) {
  return (
    <div className="flex items-center gap-2.5">
      <div
        className={cn(
          'flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[11px] font-bold transition-colors',
          done
            ? 'bg-emerald-500 text-white'
            : active
              ? 'bg-red-500 text-white'
              : 'bg-zinc-800 text-zinc-500',
        )}
      >
        {done ? <CheckCircle2 className="h-3.5 w-3.5" /> : step}
      </div>
      <span
        className={cn(
          'text-xs font-medium',
          active ? 'text-white' : done ? 'text-zinc-400' : 'text-zinc-600',
        )}
      >
        {label}
      </span>
    </div>
  );
}

function ProcessingPanel({
  phase,
  progress,
  message,
  uploadProgress,
  onCancel,
}: {
  phase: 'uploading' | 'processing';
  progress: number;
  message: string;
  uploadProgress: { received: number; total: number } | null;
  onCancel: () => void;
}) {
  const isUploading = phase === 'uploading';
  const pct = Math.round(progress * 100);
  const title = isUploading ? 'Uploading Video' : 'Analyzing Movement';

  // Upload-specific progress
  const uploadPct =
    uploadProgress && uploadProgress.total > 0
      ? Math.round((uploadProgress.received / uploadProgress.total) * 100)
      : 0;

  const subtitle = isUploading
    ? uploadProgress
      ? `${formatBytes(uploadProgress.received)} / ${formatBytes(uploadProgress.total)} — sending in chunks`
      : 'Sending your video to the judge engine'
    : message || 'Running pose detection & rep counting';

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-8 space-y-6 text-center">
      <div className="flex justify-center">
        <div className="relative">
          {isUploading ? (
            <div className="flex h-16 w-16 items-center justify-center rounded-full bg-red-500/10">
              <UploadCloud className="h-7 w-7 text-red-400 animate-pulse" />
            </div>
          ) : (
            <div className="flex h-16 w-16 items-center justify-center rounded-full bg-red-500/10">
              <Loader2 className="h-7 w-7 text-red-400 animate-spin" />
            </div>
          )}
        </div>
      </div>

      <div className="space-y-1">
        <h3 className="text-lg font-bold text-white">{title}</h3>
        <p className="text-sm text-zinc-500">{subtitle}</p>
      </div>

      {/* Progress bar */}
      <div className="space-y-2">
        {isUploading ? (
          <div className="h-2 rounded-full bg-zinc-800 overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-red-500 to-orange-500 transition-all duration-300"
              style={{ width: `${uploadPct}%` }}
            />
          </div>
        ) : (
          <div className="h-2 rounded-full bg-zinc-800 overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-red-500 to-orange-500 transition-all duration-500"
              style={{ width: `${pct}%` }}
            />
          </div>
        )}
        <div className="flex items-center justify-between text-xs text-zinc-500">
          <span>{isUploading ? 'Uploading…' : message}</span>
          <span className="tabular-nums">
            {isUploading ? `${uploadPct}%` : `${pct}%`}
          </span>
        </div>
      </div>

      {/* Cancel button — visible during both upload and processing */}
      <Button
        onClick={onCancel}
        variant="outline"
        size="sm"
        className="gap-1.5 text-xs"
      >
        <X className="h-3.5 w-3.5" />
        Cancel
      </Button>
    </div>
  );
}

function formatTimeCap(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return s === 0 ? `${m} min` : `${m}m ${s}s`;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
