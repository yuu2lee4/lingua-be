"use client";

import { useQuery, useMutation } from "@tanstack/react-query";
import { submitTranslation, getJobStatus, cancelJob } from "@/lib/api/translation";
import type { TranslationRequest } from "@/types/translation";

export function useSubmitTranslation() {
  return useMutation({
    mutationFn: (data: TranslationRequest) => submitTranslation(data),
  });
}

export function useJobStatus(jobId: string | null) {
  return useQuery({
    queryKey: ["job", jobId],
    queryFn: () => getJobStatus(jobId!),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "in_progress" || status === "pending" ? 2000 : false;
    },
  });
}

export function useCancelJob() {
  return useMutation({
    mutationFn: (jobId: string) => cancelJob(jobId),
  });
}
