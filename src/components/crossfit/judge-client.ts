/**
 * API client for the judge engine (via the Next streaming proxy).
 *
 * Upload strategy:
 *  - small files (≤ 16 MB): single multipart POST (XHR → progress events)
 *  - large files: CHUNKED upload (init → sequential octet-stream chunks →
 *    complete). Each chunk is a small request, so reverse proxies / tunnels
 *    that cap or buffer large request bodies never stall the transfer, and a
 *    dropped connection only retries one chunk instead of the whole video.
 *    An unfinished session can be RESUMED after a page reload (jobId kept in
 *    localStorage keyed by file signature).
 */

import type {
  AnalysisResult, DivisionsResponse, JobInfo, WodSummary,
} from "./types";

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || body.error || JSON.stringify(body);
    } catch { /* keep statusText */ }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export function fetchDivisions(): Promise<DivisionsResponse> {
  return json<DivisionsResponse>("/api/judge/divisions");
}

export function fetchWods(): Promise<{ wods: WodSummary[] }> {
  return json<{ wods: WodSummary[] }>("/api/judge/wods");
}

export function fetchJobs(): Promise<{ jobs: JobInfo[] }> {
  return json<{ jobs: JobInfo[] }>("/api/judge/jobs");
}

export function fetchJob(id: string): Promise<{ job: JobInfo; result: AnalysisResult | null }> {
  return json(`/api/judge/jobs/${id}`);
}

export interface UploadPayload {
  file: File;
  division: string;
  athleteName?: string;
  claimedReps?: number | null;
  claimedTimeSec?: number | null;
  claimedCapped?: boolean;
  manualStartSec?: number | null;
  mockMode?: boolean;
  signal?: AbortSignal;
  onProgress?: (pct: number) => void;
}

// --------------------------------------------------------------------------- //
// Low-level XHR helper (progress events need XHR; fetch has no upload progress)
// --------------------------------------------------------------------------- //

interface XhrResult {
  status: number;
  body: Record<string, unknown> | undefined;
}

function xhrJson(opts: {
  url: string;
  method?: string;
  body?: XMLHttpRequestBodyInit;
  headers?: Record<string, string>;
  signal?: AbortSignal;
  onUploadProgress?: (loaded: number) => void;
  timeoutMs?: number;
}): Promise<XhrResult> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(opts.method || "POST", opts.url);
    for (const [k, v] of Object.entries(opts.headers || {})) {
      xhr.setRequestHeader(k, v);
    }
    let timedOut = false;
    const timer = opts.timeoutMs
      ? setTimeout(() => { timedOut = true; xhr.abort(); }, opts.timeoutMs)
      : null;
    const cleanup = () => { if (timer) clearTimeout(timer); };

    if (opts.signal) {
      if (opts.signal.aborted) {
        cleanup();
        reject(new DOMException("Aborted", "AbortError"));
        return;
      }
      opts.signal.addEventListener("abort", () => xhr.abort(), { once: true });
    }

    xhr.upload.onprogress = (e) => opts.onUploadProgress?.(e.loaded);
    xhr.onload = () => {
      cleanup();
      let body: Record<string, unknown> | undefined;
      try { body = JSON.parse(xhr.responseText); } catch { /* non-JSON */ }
      resolve({ status: xhr.status, body });
    };
    xhr.onerror = () => {
      cleanup();
      reject(new Error("Network error while uploading the video"));
    };
    xhr.onabort = () => {
      cleanup();
      reject(new DOMException(
        timedOut ? "Chunk timed out" : "Aborted",
        timedOut ? "TimeoutError" : "AbortError"));
    };
    xhr.send(opts.body);
  });
}

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) { reject(new DOMException("Aborted", "AbortError")); return; }
    const t = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    const onAbort = () => { clearTimeout(t); reject(new DOMException("Aborted", "AbortError")); };
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

async function errorDetail(res: Response, fallback: string): Promise<string> {
  try {
    const b = await res.json();
    return (b && (b.detail || b.error)) || fallback;
  } catch {
    return fallback;
  }
}

// --------------------------------------------------------------------------- //
// Upload — public entry point
// --------------------------------------------------------------------------- //

/** Files larger than this are uploaded in chunks. */
const CHUNK_THRESHOLD_BYTES = 16 * 1024 * 1024;
const CHUNK_MIN = 2 * 1024 * 1024;
const CHUNK_MAX = 8 * 1024 * 1024;
/** Aim for at least this many progress steps → smooth bar even for 3 GB files. */
const CHUNK_TARGET_STEPS = 400;
/** Per-chunk attempt timeout (slow links: 8 MB @ ~110 KB/s ≈ 75 s). */
const CHUNK_TIMEOUT_MS = 10 * 60 * 1000;
const CHUNK_MAX_ATTEMPTS = 4;
const MAX_RESYNCS = 5;

function chunkSizeFor(totalBytes: number): number {
  const bySteps = Math.ceil(totalBytes / CHUNK_TARGET_STEPS);
  return Math.min(CHUNK_MAX, Math.max(CHUNK_MIN, bySteps));
}

/** Error that must NOT be retried (bad request / too large / expired session). */
class PermanentUploadError extends Error {}

export function uploadJob(payload: UploadPayload): Promise<{ job_id: string }> {
  return payload.file.size > CHUNK_THRESHOLD_BYTES
    ? uploadChunked(payload)
    : uploadSingle(payload);
}

// --------------------------------------------------------------------------- //
// Path A — single multipart POST (small files; original behavior)
// --------------------------------------------------------------------------- //

async function uploadSingle(payload: UploadPayload): Promise<{ job_id: string }> {
  const form = new FormData();
  form.append("video", payload.file, payload.file.name);
  form.append("division", payload.division);
  form.append("wod_id", "wodx_ladder_wod1");
  if (payload.athleteName) form.append("athlete_name", payload.athleteName);
  if (payload.claimedReps != null)
    form.append("claimed_reps", String(payload.claimedReps));
  if (payload.claimedTimeSec != null) {
    form.append("claimed_time_min", String(Math.floor(payload.claimedTimeSec / 60)));
    form.append("claimed_time_sec", String(payload.claimedTimeSec % 60));
  }
  if (payload.claimedCapped) form.append("claimed_capped", "true");
  if (payload.manualStartSec != null && payload.manualStartSec >= 0)
    form.append("manual_start_sec", String(payload.manualStartSec));
  if (payload.mockMode) {
    form.append("pose_source", "mock");
    form.append("mock_block_scale", "0.15");
  }

  const res = await xhrJson({
    url: "/api/judge/jobs",
    body: form,
    signal: payload.signal,
    onUploadProgress: (loaded) => {
      if (payload.onProgress) {
        const total = payload.file.size || 1;
        payload.onProgress(Math.min(100, Math.round((loaded / total) * 100)));
      }
    },
  });
  if (res.status >= 200 && res.status < 300 && res.body?.job_id) {
    return { job_id: String(res.body.job_id) };
  }
  const detail = (res.body?.detail as string) || `Server error (${res.status})`;
  throw new Error(detail);
}

// --------------------------------------------------------------------------- //
// Path B — chunked & resumable upload (large files)
// --------------------------------------------------------------------------- //

async function uploadChunked(payload: UploadPayload): Promise<{ job_id: string }> {
  const file = payload.file;
  const size = file.size;
  const chunkSize = chunkSizeFor(size);
  const totalChunks = Math.ceil(size / chunkSize);
  const report = (uploadedBytes: number) => {
    if (payload.onProgress) {
      payload.onProgress(size > 0
        ? Math.min(100, Math.round((uploadedBytes / size) * 100))
        : 100);
    }
  };

  // --- resume: reuse an unfinished session for the same file --------------- //
  const storeKey = `cfj-upload-${file.name}|${size}|${file.lastModified}`;
  let jobId: string | null = null;
  let startChunk = 0;
  try {
    const saved = localStorage.getItem(storeKey);
    if (saved) {
      const probe = await fetch(`/api/judge/jobs/${saved}/session`,
        { signal: payload.signal });
      if (probe.ok) {
        const s = await probe.json();
        if (!s.complete && s.registered === false && s.total_bytes === size) {
          jobId = saved;
          startChunk = s.expected_index;
        }
      }
    }
  } catch { /* unreachable session → fresh upload */ }

  // --- init ----------------------------------------------------------------- //
  if (jobId === null) {
    const form = new FormData();
    form.append("filename", file.name);
    form.append("total_bytes", String(size));
    form.append("division", payload.division);
    form.append("wod_id", "wodx_ladder_wod1");
    if (payload.athleteName) form.append("athlete_name", payload.athleteName);
    if (payload.claimedReps != null)
      form.append("claimed_reps", String(payload.claimedReps));
    if (payload.claimedTimeSec != null) {
      form.append("claimed_time_min", String(Math.floor(payload.claimedTimeSec / 60)));
      form.append("claimed_time_sec", String(payload.claimedTimeSec % 60));
    }
    if (payload.claimedCapped) form.append("claimed_capped", "true");
    if (payload.manualStartSec != null && payload.manualStartSec >= 0)
      form.append("manual_start_sec", String(payload.manualStartSec));
    if (payload.mockMode) {
      form.append("pose_source", "mock");
      form.append("mock_block_scale", "0.15");
    }
    const r = await fetch("/api/judge/jobs/init", {
      method: "POST", body: form, signal: payload.signal,
    });
    if (!r.ok) throw new Error(await errorDetail(r, `Server error (${r.status})`));
    jobId = (await r.json()).job_id as string;
    try { localStorage.setItem(storeKey, jobId); } catch { /* private mode */ }
  }

  // --- chunks (sequential, per-chunk retry, server-truth resync) ------------ //
  let uploaded = startChunk * chunkSize;
  let chunkIdx = startChunk;
  let resyncs = 0;
  report(uploaded);

  while (chunkIdx < totalChunks) {
    if (payload.signal?.aborted) throw new DOMException("Aborted", "AbortError");
    const blob = file.slice(chunkIdx * chunkSize, Math.min((chunkIdx + 1) * chunkSize, size));

    let attempt = 0;
    let advanced = false;
    while (!advanced) {
      attempt++;
      try {
        const res = await xhrJson({
          url: `/api/judge/jobs/${jobId}/chunk?index=${chunkIdx}&total=${totalChunks}`,
          body: blob,
          headers: { "Content-Type": "application/octet-stream" },
          signal: payload.signal,
          timeoutMs: CHUNK_TIMEOUT_MS,
          onUploadProgress: (loaded) => report(uploaded + Math.min(loaded, blob.size)),
        });
        if (res.status >= 200 && res.status < 300) {
          chunkIdx++;
          uploaded = chunkIdx * chunkSize;
          advanced = true;
          break;
        }
        const b = res.body || {};
        if (res.status === 409 && typeof b.expected_index === "number") {
          // Server is the source of truth — jump to where it is.
          resyncs++;
          if (resyncs > MAX_RESYNCS) {
            throw new PermanentUploadError(
              "Upload session out of sync — please try again.");
          }
          const target = b.expected_index as number;
          if (target > totalChunks) {
            throw new PermanentUploadError(
              "Upload session state is invalid — please try again.");
          }
          chunkIdx = target;
          uploaded = target * chunkSize;
          advanced = true;
          break;
        }
        if (res.status === 404) {
          throw new PermanentUploadError(
            "Upload session expired — please start the upload again.");
        }
        if (res.status === 413) {
          throw new PermanentUploadError(
            (b.detail as string) || "File exceeds the maximum allowed size");
        }
        // 400/415/422 → permanent; 5xx → retryable
        if ([400, 415, 422].includes(res.status)) {
          throw new PermanentUploadError(
            (b.detail as string) || `Server error (${res.status})`);
        }
        throw new Error((b.detail as string) || `Server error (${res.status})`);
      } catch (e) {
        if (e instanceof PermanentUploadError) throw e;
        const aborted = e instanceof DOMException && e.name === "AbortError";
        if (aborted && payload.signal?.aborted) {
          throw new DOMException("Aborted", "AbortError");
        }
        if (attempt >= CHUNK_MAX_ATTEMPTS) {
          throw new Error(
            `Upload failed at chunk ${chunkIdx + 1}/${totalChunks} ` +
            `(uploaded ${Math.round(uploaded / 1048576)} of ` +
            `${Math.round(size / 1048576)} MB). Check your connection — ` +
            `the upload will resume from where it stopped.`);
        }
        await sleep(800 * 2 ** (attempt - 1), payload.signal);
      }
    }
    report(Math.min(uploaded, size));
  }

  // --- complete -------------------------------------------------------------- //
  const r2 = await fetch(`/api/judge/jobs/${jobId}/complete`, {
    method: "POST", signal: payload.signal,
  });
  if (!r2.ok) throw new Error(await errorDetail(r2, `Server error (${r2.status})`));
  try { localStorage.removeItem(storeKey); } catch { /* noop */ }
  report(size);
  return { job_id: jobId };
}

export function reviewVideoUrl(jobId: string): string {
  return `/api/judge/jobs/${jobId}/video?variant=review`;
}
