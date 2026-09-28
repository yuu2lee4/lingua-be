export interface TranslationRequest {
  source_text_1: string;
  source_lang_1?: string;
  source_text_2?: string;
  source_lang_2?: string;
  key?: string;
  target_langs: string[];
  glossary_path?: string;
  translation_model?: string;
  review_model?: string;
  quality_threshold?: number;
  max_retries?: number;
}

export interface TranslationItem {
  target_lang: string;
  translated_text: string;
  quality_score: number | null;
  quality_feedback: string | null;
  review_input?: string | null;
  retry_count: number;
  latency_ms: number;
  glossary_terms_found: string[];
  glossary_terms_matched: string[];
  glossary_l1_direct_matches: Record<string, string>;
  placeholder_issues: string[];
}

export interface ConsistencyPairResult {
  lang1: string;
  lang2: string;
  passed: boolean;
  feedback: string;
  checked_terms_count: number;
  inconsistent_terms_count: number;
}

export interface TranslationResponse {
  source_text_1: string;
  source_lang_1: string;
  source_text_2?: string | null;
  source_lang_2?: string | null;
  source_text: string;
  source_lang: string;
  translations: TranslationItem[];
  consistency_passed: boolean;
  consistency_feedback: string | null;
  consistency_pair_results: ConsistencyPairResult[];
  total_latency_ms: number;
}
