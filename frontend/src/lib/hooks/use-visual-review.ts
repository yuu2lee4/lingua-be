"use client";

import { useMutation } from "@tanstack/react-query";
import { submitVisualReview } from "@/lib/api/visual-review";
import type { VisualReviewRequest } from "@/types/visual-review";

export function useSubmitVisualReview() {
  return useMutation({
    mutationFn: (data: VisualReviewRequest) => submitVisualReview(data),
  });
}
