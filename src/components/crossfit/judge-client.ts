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

/** Re-run analysis on the ALREADY-UPLOADED video (no re-upload) after a
 *  transient failure — e.g. an engine restart or environment hiccup. */
export function retryJob(id: string): Promise<{ job_id: string; status: string }> {
  return json(`/api/judge/jobs/${id}/retry`, { method: "POST" });
}

/** Fetch just the result document (used to poll the async review video:
 *  the result is final immediately, review_video swaps "pending" → true). */
export function fetchResult(id: string): Promise<AnalysisResult> {
  return json(`/api/judge/jobs/${id}/result`);
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
/** Parallel upload streams (only when the server advertises sparse mode).
 *  5 — enough to overcome per-connection throttling / packet loss on
 *  long-haul links, while leaving a browser connection slot free for
 *  probes (HTTP/1.1: 6 per origin). */
const PARALLEL_STREAMS = 5;
/** Work-splitting granularity: a fresh upload is ONE giant byte range.
 *  Without splitting it into PIECES, the first stream shifts the whole
 *  range and every other stream exits instantly (the "fake parallelism"
 *  bug — real uploads ran single-stream). Pieces are pulled from a shared
 *  queue so all streams truly share the load; a stalled stream only holds
 *  back its own small piece. */
const PIECE_MULT = 8;                 // pieces per stream (balancing)
const PIECE_MIN_BYTES = 512 * 1024;
const PIECE_MAX_BYTES = 8 * 1024 * 1024;
/** No upload-progress event for this long (body incomplete) → stalled. */
const PROGRESS_STALL_MS = 15_000;
/** Whole body sent but no response for this long → stalled response. */
const RESPONSE_WAIT_MS = 45_000;
/** Retries for transient chunk failures (network errors / response waits). */
const CHUNK_MAX_ATTEMPTS = 5;
/** Consecutive stalls at the FLOOR size before declaring the transport dead. */
const FLOOR_STALL_LIMIT = 3;
/** Cap on server-truth resyncs per upload. */
const MAX_RESYNCS = 12;

/** Live transfer telemetry reported alongside the percentage. */
export interface UploadProgressInfo {
  /** Effective transfer speed in bytes/sec (EMA over the last ~12 s). */
  bytesPerSec: number;
  /** Estimated seconds to finish (null until a stable estimate exists). */
  etaSec: number | null;
}

export interface UploadPayload {
  file: File;
  division: string;
  divisionLabel?: string;
  athleteName?: string;
  claimedReps?: number | null;
  claimedTimeSec?: number | null;
  claimedCapped?: boolean;
  manualStartSec?: number | null;
  mockMode?: boolean;
  signal?: AbortSignal;
  onProgress?: (pct: number, info?: UploadProgressInfo) => void;
}

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
// Byte-range math (mirror of the server's sparse bookkeeping)
// --------------------------------------------------------------------------- //

type Range = [number, number];

function rangesNormalize(ranges: Range[]): Range[] {
  const out: Range[] = [];
  for (const [s, e] of ranges.filter(([a, b]) => b > a).sort((a, b) => a[0] - b[0])) {
    if (out.length && s <= out[out.length - 1][1]) {
      out[out.length - 1][1] = Math.max(out[out.length - 1][1], e);
    } else {
      out.push([s, e]);
    }
  }
  return out;
}

function rangesCovered(ranges: Range[]): number {
  return ranges.reduce((n, [s, e]) => n + (e - s), 0);
}

function rangesPrefix(ranges: Range[]): number {
  let prefix = 0;
  for (const [s, e] of rangesNormalize(ranges)) {
    if (s > prefix) break;
    prefix = Math.max(prefix, e);
  }
  return prefix;
}

function missingFrom(ranges: Range[], size: number): Range[] {
  const holes: Range[] = [];
  let cur = 0;
  for (const [s, e] of rangesNormalize(ranges)) {
    if (s > cur) holes.push([cur, s]);
    cur = Math.max(cur, e);
    if (cur >= size) break;
  }
  if (cur < size) holes.push([cur, size]);
  return holes;
}

// --------------------------------------------------------------------------- //
// Upload — public entry point (adaptive multi-stream chunked upload)
// --------------------------------------------------------------------------- //

export function uploadJob(payload: UploadPayload): Promise<{ job_id: string }> {
  return uploadChunked(payload);
}

async function uploadChunked(payload: UploadPayload): Promise<{ job_id: string }> {
  const file = payload.file;
  const size = file.size;
  const signal = payload.signal;

  // --- speed meter (EMA over recent progress samples) -------------------- //
  const samples: Array<{ t: number; bytes: number }> = [];
  let speedEma = 0;
  let lastReportT = 0;

  const speedInfo = (uploadedBytes: number): UploadProgressInfo => {
    const now = Date.now();
    samples.push({ t: now, bytes: uploadedBytes });
    while (samples.length > 2 && now - samples[0].t > 12_000) samples.shift();
    if (samples.length >= 2) {
      const a = samples[0];
      const b = samples[samples.length - 1];
      const dt = (b.t - a.t) / 1000;
      if (dt >= 1) {
        const bps = Math.max(0, (b.bytes - a.bytes) / dt);
        speedEma = speedEma === 0 ? bps : speedEma * 0.7 + bps * 0.3;
      }
    }
    const remaining = Math.max(0, size - uploadedBytes);
    return {
      bytesPerSec: speedEma,
      etaSec: speedEma > 2048 && remaining > 0 ? Math.round(remaining / speedEma) : null,
    };
  };

  const report = (uploadedBytes: number) => {
    if (!payload.onProgress) return;
    const pct = size > 0
      ? Math.min(100, Math.round((uploadedBytes / size) * 100)) : 100;
    const now = Date.now();
    if (now - lastReportT >= 250 || pct >= 100) {
      lastReportT = now;
      payload.onProgress(pct, speedInfo(uploadedBytes));
    } else {
      payload.onProgress(pct);
    }
  };

  // --- resume: reuse an unfinished session for the same file ------------- //
  const storeKey = `cfj-upload-${file.name}|${size}|${file.lastModified}`;
  const sizeKey = `cfj-chunk-bytes-${file.name}|${size}|${file.lastModified}`;
  let jobId: string | null = null;
  let covered: Range[] = [];            // server-truth covered ranges
  let sparse = false;
  try {
    const saved = localStorage.getItem(storeKey);
    if (saved) {
      const probe = await fetch(`/api/judge/jobs/${saved}/session`, { signal });
      if (probe.ok) {
        const s = await probe.json();
        if (!s.complete && s.registered === false &&
            (s.total_bytes == null || s.total_bytes === size)) {
          jobId = saved;
          sparse = !!s.sparse;
          covered = Array.isArray(s.ranges)
            ? (s.ranges as Range[]) : [[0, typeof s.received === "number" ? s.received : 0]];
        }
      }
    }
  } catch { /* unreachable session → fresh upload */ }

  // --- init --------------------------------------------------------------- //
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
    const r = await fetch("/api/judge/jobs/init", { method: "POST", body: form, signal });
    if (!r.ok) throw new Error(await errorDetail(r, `Server error (${r.status})`));
    const j = await r.json();
    jobId = j.job_id as string;
    sparse = !!j.sparse;
    try { localStorage.setItem(storeKey, jobId); } catch { /* private mode */ }
  }

  // --- shared upload plan --------------------------------------------------- //
  const missing: Range[] = missingFrom(covered, size);
  let ackedBytes = size - missing.reduce((n, [a, b]) => n + (b - a), 0);

  // TRUE work-splitting: chop every missing range into PIECES that ALL
  // streams pull from this shared queue (atomic — JS is single-threaded
  // between awaits). This is what makes the parallel streams real.
  const pieceBytes = Math.max(PIECE_MIN_BYTES,
    Math.min(PIECE_MAX_BYTES,
      Math.ceil(size / (PARALLEL_STREAMS * PIECE_MULT)) || PIECE_MIN_BYTES));
  const pieces: Range[] = [];
  for (const [s0, e0] of missing) {
    for (let p = s0; p < e0; p += pieceBytes) {
      pieces.push([p, Math.min(p + pieceBytes, e0)]);
    }
  }

  const inflight: number[] = [];        // per-stream in-flight loaded bytes
  const bestSize = (() => {
    try {
      const v = Number(localStorage.getItem(sizeKey));
      if (Number.isFinite(v) && v >= CHUNK_MIN_BYTES && v <= CHUNK_MAX_BYTES) return v;
    } catch { /* noop */ }
    return 0;
  })();

  let fatal: unknown = null;            // first permanent/terminal error
  let resyncs = 0;

  /** Server-truth probe → refill the piece queue with any holes (bounded). */
  const resyncFromServer = async (): Promise<boolean> => {
    if (++resyncs > MAX_RESYNCS) return false;
    try {
      const probe = await fetch(`/api/judge/jobs/${jobId}/session`, { signal });
      if (!probe.ok) return probe.status === 404
        ? Boolean(fatal = new PermanentUploadError(
            "Upload session expired — please start the upload again."))
        : false;
      const s = await probe.json();
      if (Array.isArray(s.ranges)) covered = s.ranges as Range[];
      else if (typeof s.received === "number") covered = [[0, s.received]];
      const holes = missingFrom(covered, size);
      ackedBytes = size - holes.reduce((n, [a, b]) => n + (b - a), 0);
      for (const h of holes) {
        for (let p = h[0]; p < h[1]; p += pieceBytes) {
          pieces.push([p, Math.min(p + pieceBytes, h[1])]);
        }
      }
      return true;
    } catch {
      return false;
    }
  };

  const stream = async (streamId: number) => {
    let size2 = Math.max(bestSize || CHUNK_START_BYTES, CHUNK_MIN_BYTES);
    let floorStalls = 0;
    let lastResetAcked = ackedBytes;
    inflight[streamId] = 0;

    while (!fatal) {
      if (signal?.aborted) return;
      // ANY global progress forgives this stream's stall counters — an edge
      // glitch on ONE connection must never kill a healthy parallel upload.
      if (ackedBytes > lastResetAcked) {
        floorStalls = 0;
        lastResetAcked = ackedBytes;
      }
      // take the next piece from the SHARED queue (true parallelism)
      const task: Range | null = pieces.length > 0 ? (pieces.shift() as Range) : null;
      if (!task) return;                 // nothing left for this stream

      const [start, end] = task;
      let off = start;
      while (off < end && !fatal) {
        if (signal?.aborted) return;
        const want = Math.min(size2, end - off);
        const blob = file.slice(off, off + want);

        let attempt = 0;
        let advanced = false;
        while (!advanced && !fatal) {
          if (signal?.aborted) return;
          attempt++;
          try {
            const form = new FormData();
            form.append("offset", String(off));
            form.append("total_bytes", String(size));
            form.append("blob", blob, "chunk");

            const res = await xhrJson({
              url: `/api/judge/jobs/${jobId}/chunk`,
              body: form,
              signal,
              onUploadProgress: (loaded) => {
                inflight[streamId] = Math.min(loaded, want);
                report(ackedBytes + inflight.reduce((n: number, v: number) => n + (v || 0), 0));
              },
            });

            if (res.status >= 200 && res.status < 300) {
              const b = res.body || {};
              const accepted = typeof b.accepted === "number" ? b.accepted : want;
              if (accepted <= 0 && want > 0) {
                // ZERO-ADVANCE 200 — the edge stripped/emptied the body.
                // Learn nothing from it; shrink hard and let the retry
                // re-deliver (the sparse server stored nothing, so this is
                // a pure idempotent re-send).
                size2 = Math.max(CHUNK_MIN_BYTES, Math.floor(want / 2));
                if (size2 <= CHUNK_MIN_BYTES) floorStalls++;
                if (floorStalls >= FLOOR_STALL_LIMIT) {
                  fatal = new PermanentUploadError(
                    "The connection to the server is not accepting video data " +
                    "(every attempt stalls). — اتصال به سرور اجازهٔ انتقال ویدیو " +
                    "نمی‌دهد. Please check your network / try again in a few minutes.");
                  return;
                }
                advanced = true;         // re-enter with a smaller chunk
                break;
              }
              if (accepted < want) {
                // SHORT ACK — the transport truncated the body; the server
                // stored exactly `accepted` bytes at `off` (sparse!). Learn
                // the real per-request limit and send the remainder next.
                size2 = Math.max(CHUNK_MIN_BYTES, accepted);
                off += accepted;
                ackedBytes += accepted;
              } else {
                off += want;
                ackedBytes += want;
                size2 = Math.min(size2 * 2, CHUNK_MAX_BYTES);   // healthy → ramp
                try { localStorage.setItem(sizeKey, String(size2)); } catch { /* noop */ }
              }
              floorStalls = 0;
              inflight[streamId] = 0;
              report(ackedBytes);
              advanced = true;
              break;
            }

            const b = res.body || {};
            if (res.status === 404) {
              fatal = new PermanentUploadError(
                "Upload session expired — please start the upload again.");
              return;
            }
            if (res.status === 413) {
              fatal = new PermanentUploadError(
                (b.detail as string) || "File exceeds the maximum allowed size");
              return;
            }
            if ([400, 415, 422].includes(res.status)) {
              fatal = new PermanentUploadError(
                (b.detail as string) || `Server error (${res.status})`);
              return;
            }
            throw new Error((b.detail as string) || `Server error (${res.status})`);
          } catch (e) {
            if (fatal) return;
            if (e instanceof PermanentUploadError) { fatal = e; return; }
            const aborted = e instanceof DOMException && e.name === "AbortError";
            if (aborted && signal?.aborted) {
              fatal = new DOMException("Aborted", "AbortError");
              return;
            }

            if (e instanceof StallError && e.message === "Upload stalled") {
              // Body stalled mid-transfer → this size is beyond what the
              // transport allows right now. Back off; the stalled chunk
              // may have partially landed — server truth decides.
              size2 = Math.max(CHUNK_MIN_BYTES, Math.floor(want / 2));
              if (size2 <= CHUNK_MIN_BYTES) floorStalls++;
              if (floorStalls >= FLOOR_STALL_LIMIT) {
                fatal = new PermanentUploadError(
                  "The connection to the server is not accepting video data " +
                  "(every attempt stalls). — اتصال به سرور اجازهٔ انتقال ویدیو " +
                  "نمی‌دهد. Please check your network / try again in a few minutes.");
                return;
              }
              await resyncFromServer();
              advanced = true;           // re-enter with a smaller chunk
              break;
            }

            // Network error / response-wait stall / 5xx → retry the chunk.
            if (attempt >= CHUNK_MAX_ATTEMPTS) {
              // Last resort: server truth, then one more round.
              if (await resyncFromServer()) {
                attempt = 0;
                continue;
              }
              fatal = new Error(
                `Upload failed at ${off} of ${size} bytes ` +
                `(${Math.round(off / 1048576)} of ${Math.round(size / 1048576)} MB). ` +
                `Check your connection — the upload will resume from where it stopped.`);
              return;
            }
            await sleep(800 * 2 ** (attempt - 1), signal);
          }
        }
      }
    }
  };

  const nStreams = sparse && pieces.length > 1
    ? Math.min(PARALLEL_STREAMS, pieces.length) : 1;
  await Promise.all(Array.from({ length: nStreams }, (_, i) => stream(i)));

  if (fatal) throw fatal;

  // --- reconcile pass: paranoid hole check before complete ------------------ //
  if (sparse && (await resyncFromServer()) && pieces.length > 0) {
    // stray holes (should not happen — the sparse protocol is exact) →
    // finish them single-stream
    await Promise.all(Array.from({ length: 1 }, () => stream(0)));
    if (fatal) throw fatal;
  }

  // --- complete -------------------------------------------------------------- //
  const r2 = await fetch(`/api/judge/jobs/${jobId}/complete`, {
    method: "POST", signal,
  });
  if (!r2.ok) throw new Error(await errorDetail(r2, `Server error (${r2.status})`));
  try {
    localStorage.removeItem(storeKey);
    localStorage.removeItem(sizeKey);
  } catch { /* noop */ }
  report(size);
  return { job_id: jobId };
}

export function reviewVideoUrl(jobId: string): string {
  return `/api/judge/jobs/${jobId}/video?variant=review`;
}
