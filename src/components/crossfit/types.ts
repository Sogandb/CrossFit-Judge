/** Shared view-model types (mirror of the Python engine's result schema). */

export interface Division {
  id: string;
  label_fa: string;
  label_en: string;
  weight_kg: number | null;
  weights_verified: boolean;
}

export interface DivisionsResponse {
  /** group keys are English ("Men" / "Women") — division terms stay English */
  grouped: Record<string, Division[]>;
  weights_verified: boolean;
}

export interface WodSummary {
  wod_id: string;
  name_fa: string;
  name_en: string;
  format: string;
  format_fa: string;
  format_en: string;
  time_cap_sec: number;
  description_fa: string;
  description_en: string;
  score_fa: string;
  score_en: string;
  blocks: { movement: string; reps: number }[];
}

export interface JobInfo {
  id: string;
  created_at: number;
  status: "queued" | "running" | "done" | "failed";
  stage_key: string;
  stage_fa: string;
  stage_en: string;
  progress: number;
  error_fa: string | null;
  error_en: string | null;
  athlete_name?: string;
  division?: string;
  wod_id?: string;
}

export interface BlockSummary {
  idx: number;
  movement: string;
  movement_fa: string;
  movement_en: string;
  reps: number;
  credited: number;
  complete: boolean;
  rep_start: number;
  rep_end: number;
  status_fa: string;
  status_en: string;
}

export interface RepTimelineEntry {
  block: number;
  movement: string;
  movement_fa: string;
  movement_en: string;
  rep_start: number;
  rep_end: number;
  reps: number;
}

export interface AnalysisEvent {
  t_start: number;
  t_end: number;
  outcome: "rep" | "no_rep";
  reason_code: string | null;
  reason_fa: string | null;
  reason_en: string | null;
  category: string | null;
  block_idx: number | null;
  rep_no: number | null;
  scored: boolean;
  post_cap: boolean;
  movement: string;
  details: Record<string, unknown>;
  review_flags: string[];
  notes: string[];
  notes_en: string[];
  expected_movement: string | null;
  confidence: number;
  confidence_label: "high" | "medium" | "low";
  borderline: boolean;
}

export interface StructuredWarning {
  code: string;
  fa: string;
  en: string;
}

export interface AnalysisResult {
  wod: {
    id: string;
    name_fa: string;
    name_en: string;
    format: string;
    format_fa: string;
    format_en: string;
    time_cap_sec: number;
    description_fa: string;
    description_en: string;
    score_fa: string;
    score_en: string;
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
    analysis_confidence: number | null;
    borderline_reps: number;
    per_movement: Record<string, {
      credited: number; no_reps: number; prescribed: number;
      avg_confidence: number | null; borderline_reps?: number;
    }>;
    blocks: BlockSummary[];
    rep_timeline?: RepTimelineEntry[];
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
    verdict_en: string;
    review_recommended: boolean;
  };
  score_display: {
    score: string;
    score_fa: string;
    score_en: string;
    status_fa: string;
    status_en: string;
    confidence?: number | null;
    confidence_fa?: string | null;
    confidence_en?: string | null;
  };
  events: AnalysisEvent[];
  sequencer_flags: { t: number; code: string; reason_fa: string; reason_en: string }[];
  warnings: StructuredWarning[];
  /** true = review video ready; false = unavailable; "pending" = rendering
   *  in the background (results are final already — UI polls for the swap). */
  review_video: boolean | "pending";
  analysis_window: { start_sec: number; end_sec: number | null };
}
