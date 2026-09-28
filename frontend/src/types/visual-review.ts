export interface VisualReviewRequest {
  target_langs: string[];
  base_url?: string;
  url_path?: string;
  reference_lang?: string;
  scroll_positions?: number;
  review_model?: string;
  sandbox_resolution?: string;
}

export interface VisualIssue {
  issue_type: string;
  severity: "critical" | "major" | "minor";
  location: string;
  description: string;
  suggestion: string;
}

export interface VisualLanguageReview {
  lang_code: string;
  lang_name: string;
  overall_score: number;
  layout_score: number;
  text_rendering_score: number;
  translation_completeness_score: number;
  expression_accuracy_score: number;
  passed: boolean;
  issues: VisualIssue[];
  screenshots_count: number;
  feedback: string;
}

export interface VisualReviewResponse {
  reviews: VisualLanguageReview[];
  reference_lang: string;
  total_languages: number;
  passed_count: number;
  failed_count: number;
  total_latency_ms: number;
  sandbox_error: string | null;
}
