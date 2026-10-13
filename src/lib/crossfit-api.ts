/**
 * API client for the CrossFit Judge Python backend.
 *
 * ALL requests go through the Next.js proxy at /api/judge/* which uses
 * raw HTTP pipe (node:http) to stream to Python. This is zero-memory for
 * large uploads and works from any origin (preview panel, localhost).
 */

function apiUrl(path: string): string {
  const clean = path.startsWith('/api/') ? path.slice(4) : path;
  return `/api/judge${clean}`;
}

// Keep directUrl as an alias for apiUrl — all requests go through the
// same proxy now. This simplifies the code and makes it more robust.
function directUrl(path: string): string {
  return apiUrl(path);
}

export interface Workout {
  id: string;
  name: string;
  format: string;
  time_cap_seconds: number;
  description: string;
  movements?: string[];
}

export interface RepEvent {
  rep_number: number;
  movement: string;
  start_time: number;
  end_time: number;
  duration: number;
  valid: boolean;
  confidence: number;
  no_rep_reason_en: string | null;
  no_rep_reason_fa: string | null;
  peak_signals: Record<string, number>;
}

export interface ScoreBreakdown {
  format: string;
  total_reps: number;
  valid_reps: number;
  no_reps: number;
  score: number;
  score_label: string;
  score_display: string;
  time_seconds: number | null;
  completed: boolean;
  rounds_completed: number;
  per_movement: Record<string, { total: number; valid: number; no_rep: number }>;
  extra: Record<string, unknown>;
}

export interface SequenceInfo {
  current_movement: string;
  current_index: number;
  current_round: number;
  reps_in_current_movement: number;
  current_reps_target: number;
  total_reps_completed: number;
  rounds_completed: number;
  movement_reps: Record<string, number>;
}

export interface JudgeReport {
  workout: {
    id: string;
    name: string;
    format: string;
    time_cap_seconds: number;
    description: string;
  };
  video: {
    name: string;
    duration_seconds: number;
  };
  score: ScoreBreakdown;
  reps: RepEvent[];
  no_reps: RepEvent[];
  summary: {
    total_reps: number;
    valid_reps: number;
    no_rep_count: number;
    avg_confidence: number;
  };
  assets: {
    annotated_video: string | null;
    timeline_image: string | null;
  };
  sequence?: SequenceInfo;
}

export interface JobStatus {
  job_id: string;
  status: 'processing' | 'completed' | 'failed';
  progress: number;
  status_message: string;
  error?: string;
}

export const MOVEMENT_LABELS: Record<string, string> = {
  squat: 'Squat',
  pushup: 'Push-up',
  burpee: 'Burpee',
  thruster: 'Thruster',
  pullup: 'Pull-up',
  kettlebell_swing: 'KB Swing',
};

export const FORMAT_LABELS: Record<string, string> = {
  amrap: 'AMRAP',
  for_time: 'For Time',
  max_reps: 'Max Reps',
  tabata: 'Tabata',
  emom: 'EMOM',
};

export async function fetchWorkouts(): Promise<Workout[]> {
  const res = await fetch(apiUrl('/api/workouts'));
  if (!res.ok) throw new Error('Failed to fetch workouts');
  const data = await res.json();
  return data.workouts;
}

export async function fetchMovements(): Promise<string[]> {
  const res = await fetch(apiUrl('/api/movements'));
  if (!res.ok) throw new Error('Failed to fetch movements');
  const data = await res.json();
  return data.movements;
}

export async function uploadVideo(
  file: File,
  workoutId: string,
  signal?: AbortSignal,
  onProgress?: (received: number, total: number) => void,
): Promise<{ job_id: string }> {
  // Use chunked upload for all videos — it's more reliable and bypasses
  // the gateway's 32MB body limit.
  return uploadChunked(file, { workoutId }, signal, onProgress);
}

interface ChunkedUploadParams {
  workoutId?: string;
  custom?: CustomWorkoutParams;
}

async function uploadChunked(
  file: File,
  params: ChunkedUploadParams,
  signal: AbortSignal | undefined,
  onProgress?: (received: number, total: number) => void,
): Promise<{ job_id: string }> {
  const CHUNK_SIZE = 5 * 1024 * 1024; // 5 MB
  const totalSize = file.size;
  const totalChunks = Math.ceil(totalSize / CHUNK_SIZE);

  // Helper: combine the user's abort signal with a timeout signal.
  const withTimeout = (ms: number): AbortSignal | undefined => {
    const timeout = AbortSignal.timeout(ms);
    return signal ? AbortSignal.any([signal, timeout]) : timeout;
  };

  // 1. Initialize the upload session.
  const initForm = new FormData();
  initForm.append('filename', file.name);
  initForm.append('total_size', String(totalSize));
  if (params.workoutId) {
    initForm.append('workout_id', params.workoutId);
  } else if (params.custom) {
    initForm.append('workout_id', 'custom');
    initForm.append('workout_name', params.custom.workoutName);
    initForm.append('format', params.custom.format);
    initForm.append('time_cap_seconds', String(params.custom.timeCapSeconds));
    initForm.append('movements', params.custom.movements.join(','));
  }

  const initRes = await fetch(directUrl('/api/upload/init'), {
    method: 'POST',
    body: initForm,
    signal: withTimeout(30000), // 30s for init
  });
  if (!initRes.ok) throw new Error('Failed to start upload');
  const { upload_id } = await initRes.json();

  // 2. Upload each chunk.
  let received = 0;
  for (let i = 0; i < totalChunks; i++) {
    if (signal?.aborted) throw new DOMException('Aborted', 'AbortError');

    const start = i * CHUNK_SIZE;
    const end = Math.min(start + CHUNK_SIZE, totalSize);
    const chunk = file.slice(start, end);

    const chunkForm = new FormData();
    chunkForm.append('chunk_index', String(i));
    chunkForm.append('file', chunk, file.name);

    // 120s per chunk — allows for slow connections with large 5MB chunks.
    const chunkRes = await fetch(directUrl(`/api/upload/${upload_id}/chunk`), {
      method: 'POST',
      body: chunkForm,
      signal: withTimeout(120000),
    });
    if (!chunkRes.ok) throw new Error(`Chunk ${i} upload failed`);

    received = end;
    onProgress?.(received, totalSize);
  }

  // 3. Complete the upload.
  const completeRes = await fetch(directUrl(`/api/upload/${upload_id}/complete`), {
    method: 'POST',
    signal: withTimeout(30000),
  });
  if (!completeRes.ok) throw new Error('Failed to complete upload');
  return completeRes.json();
}

export interface CustomWorkoutParams {
  workoutName: string;
  format: string;
  timeCapSeconds: number;
  movements: string[];
}

export async function uploadCustomVideo(
  file: File,
  params: CustomWorkoutParams,
  signal?: AbortSignal,
  onProgress?: (received: number, total: number) => void,
): Promise<{ job_id: string }> {
  return uploadChunked(file, { custom: params }, signal, onProgress);
}

export async function runDemo(workoutId: string): Promise<{ job_id: string }> {
  const res = await fetch(apiUrl(`/api/demo/${workoutId}`), { method: 'POST' });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(err || 'Demo failed');
  }
  return res.json();
}

export async function pollStatus(jobId: string): Promise<JobStatus> {
  const res = await fetch(apiUrl(`/api/status/${jobId}`), {
    signal: AbortSignal.timeout(10000),
  });
  if (!res.ok) {
    if (res.status === 404) {
      // Job not found — server probably restarted. Return a failed status.
      return {
        job_id: jobId,
        status: 'failed',
        progress: 0,
        status_message: 'Job not found',
        error: 'The analysis job was lost (server may have restarted). Please try uploading again.',
      };
    }
    throw new Error(`Status check failed (HTTP ${res.status})`);
  }
  return res.json();
}

export async function fetchResults(jobId: string): Promise<JudgeReport> {
  const res = await fetch(apiUrl(`/api/results/${jobId}`));
  if (!res.ok) throw new Error('Failed to fetch results');
  return res.json();
}

export function annotatedVideoUrl(jobId: string): string {
  // Use the Next.js proxy for video/timeline (GET requests, no large body,
  // so no OOM risk). This works from any origin.
  return apiUrl(`/api/video/${jobId}`);
}

export function timelineUrl(jobId: string): string {
  return apiUrl(`/api/timeline/${jobId}`);
}
