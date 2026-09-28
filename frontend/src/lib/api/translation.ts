import { api } from "./client";
import type { TranslationRequest } from "@/types/translation";
import type { JobSubmitResponse, JobStatusResponse } from "@/types/job";

export async function submitTranslation(data: TranslationRequest): Promise<JobSubmitResponse> {
  return api.post("translations", { json: data }).json();
}

export async function getJobStatus(jobId: string): Promise<JobStatusResponse> {
  return api.get(`translations/${jobId}`).json();
}

export async function cancelJob(jobId: string): Promise<void> {
  await api.delete(`translations/${jobId}`);
}
