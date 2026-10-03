/**
 * API client for the judge engine (via the Next streaming proxy).
 * Upload uses XHR for progress events; polling uses fetch.
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

export function uploadJob(payload: UploadPayload): Promise<{ job_id: string }> {
  return new Promise((resolve, reject) => {
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

    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/judge/jobs");
    if (payload.signal) {
      if (payload.signal.aborted) {
        reject(new DOMException("Aborted", "AbortError"));
        return;
      }
      payload.signal.addEventListener("abort", () => xhr.abort(), { once: true });
    }
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && payload.onProgress) {
        payload.onProgress(Math.round((e.loaded / e.total) * 100));
      }
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText));
        } catch {
          reject(new Error("Invalid response from the server"));
        }
      } else {
        let detail = `Server error (${xhr.status})`;
        try {
          const b = JSON.parse(xhr.responseText);
          detail = b.detail || detail;
        } catch { /* noop */ }
        reject(new Error(detail));
      }
    };
    xhr.onerror = () => reject(new Error("Network error while uploading the video"));
    xhr.onabort = () => reject(new DOMException("Aborted", "AbortError"));
    xhr.send(form);
  });
}

export function reviewVideoUrl(jobId: string): string {
  return `/api/judge/jobs/${jobId}/video?variant=review`;
}
