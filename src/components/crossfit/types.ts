/** Shared view-model types (mirror of the Python engine's result schema). */

export interface Division {
  id: string;
  label_fa: string;
  weight_kg: number | null;
  weights_verified: boolean;
}

export interface DivisionsResponse {
  grouped: Record<string, Division[]>;
  weights_verified: boolean;
}

export interface WodSummary {
  wod_id: string;
  name_fa: string;
  format_fa: string;
  time_cap_sec: number;
  description_fa: string;
  blocks: { movement: string; reps: number }[];
}

export interface JobInfo {
  id: string;
  created_at: number;
  status: "queued" | "running" | "done" | "failed";
  stage_fa: string;
  progress: number;
  error_fa: string | null;
  athlete_name?: string;
  division?: string;
  wod_id?: string;
}

export interface BlockSummary {
  idx: number;
  movement: string;
  movement_fa: string;
  reps: number;
  credited: number;
  complete: boolean;
  status_fa: string;
}

export interface AnalysisEvent {
  t_start: number;
  t_end: number;
  outcome: "rep" | "no_rep";
  reason_code: string | null;
  reason_fa: string | null;
  category: string | null;
  block_idx: number | null;
  rep_no: number | null;
  scored: boolean;
  post_cap: boolean;
  movement: string;
  details: Record<string, unknown>;
  review_flags: string[];
  notes: string[];
}

export interface AnalysisResult {
  wod: {
    id: string;
    name_fa: string;
    time_cap_sec: number;
    description_fa: string;
  };
  start_detection: {
    method: string;
    t_start_sec: number;
    confidence: number;
    audio_present: boolean | null;
  };
  summary: {
    finished: boolean;
    finish_time_sec: number | null;
    capped: boolean;
    total_credited: number;
    total_prescribed: number;
    per_movement: Record<string, {
      credited: number; no_reps: number; prescribed: number;
    }>;
    blocks: BlockSummary[];
  };
  reconciliation: {
    claimed_reps: number | null;
    claimed_time_sec: number | null;
    claimed_capped: boolean | null;
    counted_reps: number;
    reps_delta: number | null;
    time_delta_sec: number | null;
    verdict: string;
    verdict_fa: string;
    review_recommended: boolean;
  };
  score_display: { score: string; score_fa: string; status_fa: string };
  events: AnalysisEvent[];
  sequencer_flags: { t: number; code: string; reason_fa: string }[];
  warnings: string[];
  review_video: boolean;
  analysis_window: { start_sec: number; end_sec: number | null };
}
