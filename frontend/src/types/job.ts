import type { TranslationResponse } from "./translation";

export type JobStatus = "pending" | "in_progress" | "completed" | "failed" | "cancelled";

export interface JobProgress {
  total_languages: number;
  completed_languages: number;
  current_phase: string;
  current_language: string | null;
  retry_count: number;
  total_consistency_pairs: number;
  completed_consistency_pairs: number;
  current_consistency_pair: string | null;
}

export interface JobSubmitResponse {
  job_id: string;
  status: JobStatus;
  message: string;
}

export interface JobStatusResponse {
  job_id: string;
  status: JobStatus;
  progress: JobProgress;
  response: TranslationResponse | null;
  error: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}
