import { api } from "./client";
import type { VisualReviewRequest, VisualReviewResponse } from "@/types/visual-review";

export async function submitVisualReview(data: VisualReviewRequest): Promise<VisualReviewResponse> {
  return api.post("visual-reviews", { json: data, timeout: 300000 }).json();
}
