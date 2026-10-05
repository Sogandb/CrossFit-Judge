/**
 * API client for the judge engine (via the Next streaming proxy).
 *
 * Upload strategy — CHUNKED, ADAPTIVE, RESUMABLE (all files):
 *  - The video is sent as a sequence of small multipart/form-data requests
 *    (init → chunk → chunk → … → complete), the SAME wire shape that passes
 *    through strict reverse proxies / preview tunnels (a single giant POST
 *    was observed stalling at 0-1% forever inside such layers).
 *  - The chunk size is not fixed: the client ramps up while the transport
 *    is healthy and backs off when a chunk stalls, auto-discovering whatever
 *    per-request body limit the tunnel in front of the app enforces.
 *  - Two watchdogs kill stuck transfers fast: (a) no upload progress for
 *    PROGRESS_STALL_MS while the body is incomplete, (b) no response for
 *    RESPONSE_WAIT_MS after the whole body was sent.
 *  - Everything is byte-offset based and idempotent: after any failure the
 *    client re-syncs to the server's authoritative byte count and continues.
 *    An unfinished session survives page reloads (jobId in localStorage).
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
// Tuning knobs
// --------------------------------------------------------------------------- //

/** Initial chunk size — small enough for almost any tunnel (matches the
 *  server's suggestion; ramps up quickly when the transport is healthy). */
const CHUNK_START_BYTES = 256 * 1024;
/** Chunk size ceiling — large enough for full local/LAN throughput. */
const CHUNK_MAX_BYTES = 8 * 1024 * 1024;
/** Floor — below this a "constrained tunnel" diagnosis is more likely than
 *  a size problem. */
const CHUNK_MIN_BYTES = 64 * 1024;
/** No upload-progress event for this long (body incomplete) → stalled. */
const PROGRESS_STALL_MS = 15_000;
/** Whole body sent but no response for this long → stalled response. */
const RESPONSE_WAIT_MS = 45_000;
/** Retries for transient chunk failures (network errors / response waits). */
const CHUNK_MAX_ATTEMPTS = 5;
/** Consecutive stalls at the FLOOR size before declaring the transport dead. */
const FLOOR_STALL_LIMIT = 3;
/** Cap on server-truth resyncs (409s) per upload. */
const MAX_RESYNCS = 12;

// --------------------------------------------------------------------------- //
// Low-level XHR helper with stall watchdogs (progress needs XHR, not fetch)
// --------------------------------------------------------------------------- //

interface XhrResult {
  status: number;
  body: Record<string, unknown> | undefined;
}

/** Thrown by the watchdogs — means "connection made no observable progress",
 *  not necessarily a network error. */
class StallError extends Error {
  constructor(kind: "progress" | "response") {
    super(kind === "progress" ? "Upload stalled" : "No response from server");
  }
}

function xhrJson(opts: {
  url: string;
  method?: string;
  body?: XMLHttpRequestBodyInit;
  headers?: Record<string, string>;
  signal?: AbortSignal;
  onUploadProgress?: (loaded: number, total: number) => void;
}): Promise<XhrResult> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(opts.method || "POST", opts.url);
    for (const [k, v] of Object.entries(opts.headers || {})) {
      xhr.setRequestHeader(k, v);
    }

    let settled = false;
    let lastActivity = Date.now();
    let loaded = 0;
    let bodyTotal = 0;
    let watchdog: ReturnType<typeof setInterval> | null = null;

    const finish = () => {
      if (watchdog) clearInterval(watchdog);
      watchdog = null;
      opts.signal?.removeEventListener("abort", onAbort);
    };
    const onAbort = () => xhr.abort();

    const settle = (fn: () => void) => {
      if (settled) return;
      settled = true;
      finish();
      fn();
    };

    // Watchdog #1 — body incomplete and no progress event for a while.
    // Watchdog #2 — body fully sent but no response for a while.
    watchdog = setInterval(() => {
      if (settled) return;
      if (loaded < bodyTotal && Date.now() - lastActivity > PROGRESS_STALL_MS) {
        settle(() => reject(new StallError("progress")));
        xhr.abort();
      } else if (loaded >= bodyTotal && bodyTotal > 0 &&
                 Date.now() - lastActivity > RESPONSE_WAIT_MS) {
        settle(() => reject(new StallError("response")));
        xhr.abort();
      }
    }, 1000);

    if (opts.signal) {
      if (opts.signal.aborted) {
        settle(() => reject(new DOMException("Aborted", "AbortError")));
        return;
      }
      opts.signal.addEventListener("abort", onAbort, { once: true });
    }

    xhr.upload.onprogress = (e) => {
      lastActivity = Date.now();
      loaded = e.loaded;
      bodyTotal = e.lengthComputable ? e.total : bodyTotal;
      opts.onUploadProgress?.(loaded, bodyTotal);
    };
    xhr.onload = () => {
      let body: Record<string, unknown> | undefined;
      try { body = JSON.parse(xhr.responseText); } catch { /* non-JSON */ }
      settle(() => resolve({ status: xhr.status, body }));
    };
    xhr.onerror = () => {
      settle(() => reject(new Error("Network error while uploading the video")));
    };
    xhr.onabort = () => {
      settle(() => reject(new DOMException("Aborted", "AbortError")));
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

/** Error that must NOT be retried (bad request / too large / expired session). */
class PermanentUploadError extends Error {}

// --------------------------------------------------------------------------- //
// Upload — public entry point (single adaptive chunked path for all files)
// --------------------------------------------------------------------------- //

export function uploadJob(payload: UploadPayload): Promise<{ job_id: string }> {
  return uploadChunked(payload);
}

async function uploadChunked(payload: UploadPayload): Promise<{ job_id: string }> {
  const file = payload.file;
  const size = file.size;
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
  let offset = 0;
  try {
    const saved = localStorage.getItem(storeKey);
    if (saved) {
      const probe = await fetch(`/api/judge/jobs/${saved}/session`,
        { signal: payload.signal });
      if (probe.ok) {
        const s = await probe.json();
        if (!s.complete && s.registered === false &&
            typeof s.received === "number" && s.received <= size &&
            (s.total_bytes == null || s.total_bytes === size)) {
          jobId = saved;
          offset = s.received;
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

  // --- adaptive chunk loop --------------------------------------------------- //
  let chunkSize = Math.max(CHUNK_START_BYTES,
    Math.min(CHUNK_MIN_BYTES, Math.ceil(size / 64)));
  let maxSize = CHUNK_MAX_BYTES;        // shrinks when a size stalls
  let floorStalls = 0;                  // consecutive stalls at CHUNK_MIN
  let resyncs = 0;
  report(offset);

  while (offset < size) {
    if (payload.signal?.aborted) throw new DOMException("Aborted", "AbortError");
    const want = Math.min(chunkSize, size - offset);
    const blob = file.slice(offset, offset + want);

    let attempt = 0;
    let advanced = false;
    while (!advanced) {
      if (payload.signal?.aborted) throw new DOMException("Aborted", "AbortError");
      attempt++;
      try {
        const form = new FormData();
        form.append("offset", String(offset));
        form.append("total_bytes", String(size));
        form.append("blob", blob, "chunk");

        const res = await xhrJson({
          url: `/api/judge/jobs/${jobId}/chunk`,
          body: form,
          signal: payload.signal,
          onUploadProgress: (loaded) => report(offset + Math.min(loaded, want)),
        });

        if (res.status >= 200 && res.status < 300) {
          // Server byte count is the truth (duplicate re-acks advance us too).
          const ack = typeof res.body?.received === "number"
            ? res.body.received : offset + want;
          offset = Math.max(offset, Math.min(ack, size));
          if (chunkSize < maxSize) chunkSize = Math.min(chunkSize * 2, maxSize);
          floorStalls = 0;
          advanced = true;
          break;
        }

        const b = res.body || {};
        if (res.status === 409 && typeof b.received === "number") {
          // Server is the source of truth — jump to where it is.
          if (++resyncs > MAX_RESYNCS) {
            throw new PermanentUploadError(
              "Upload session out of sync — please try again.");
          }
          const target = b.received as number;
          if (target > size) {
            throw new PermanentUploadError(
              "Upload session state is invalid — please try again.");
          }
          offset = target;
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

        if (e instanceof StallError && e.message === "Upload stalled") {
          // Body stalled mid-transfer → this size is beyond what the
          // transport allows right now. Back off; server truth decides
          // where the next chunk starts.
          maxSize = Math.max(CHUNK_MIN_BYTES, Math.floor(want / 2));
          chunkSize = Math.max(CHUNK_MIN_BYTES, Math.floor(want / 2));
          if (chunkSize <= CHUNK_MIN_BYTES) floorStalls++;
          if (floorStalls >= FLOOR_STALL_LIMIT) {
            throw new PermanentUploadError(
              "The connection to the server is not accepting video data " +
              "(every attempt stalls). — اتصال به سرور اجازهٔ انتقال ویدیو " +
              "نمی‌دهد. Please check your network / try again in a few minutes.");
          }
          // Re-sync: the stalled chunk may have partially landed.
          try {
            const probe = await fetch(`/api/judge/jobs/${jobId}/session`,
              { signal: payload.signal });
            if (probe.ok) {
              const s = await probe.json();
              if (typeof s.received === "number") offset = s.received;
            }
          } catch { /* keep local offset */ }
          advanced = true; // re-enter the outer loop with a smaller size
          break;
        }

        // Network error / response-wait stall / 5xx → retry the same chunk.
        if (attempt >= CHUNK_MAX_ATTEMPTS) {
          throw new Error(
            `Upload failed at ${offset} of ${size} bytes ` +
            `(${Math.round(offset / 1048576)} of ${Math.round(size / 1048576)} MB). ` +
            `Check your connection — the upload will resume from where it stopped.`);
        }
        await sleep(800 * 2 ** (attempt - 1), payload.signal);
      }
    }
    report(offset);
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
