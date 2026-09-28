export type TermSource = "manual" | "ai_extracted" | "imported";
export type TermStatus = "active" | "inactive" | "pending";
export type CandidateStatus = "pending" | "approved" | "rejected" | "migrated";

export interface GlossaryTermResponse {
  term_id: string;
  term_en: string;
  definition: string;
  part_of_speech: string;
  do_not_translate: boolean;
  translations: Record<string, string>;
  source: TermSource;
  status: TermStatus;
  created_at: string | null;
  updated_at: string | null;
}

export interface GlossaryTermListResponse {
  total: number;
  items: GlossaryTermResponse[];
  page: number;
  page_size: number;
}

export interface GlossaryTermCreate {
  term_en: string;
  definition?: string;
  part_of_speech?: string;
  do_not_translate?: boolean;
  translations?: Record<string, string>;
  source?: TermSource;
}

export interface GlossaryTermUpdate {
  definition?: string;
  part_of_speech?: string;
  do_not_translate?: boolean;
  status?: TermStatus;
}

export interface TranslationUpdate {
  translation: string;
}

export interface GlossaryCandidateResponse {
  id: number;
  term_id: string;
  term_en: string;
  definition: string;
  part_of_speech: string;
  do_not_translate: boolean;
  translations: Record<string, string>;
  source: string;
  status: string;
  migrated_to_match_glossary: boolean;
  migrated_to_business_glossary: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface GlossaryCandidateListResponse {
  total: number;
  items: GlossaryCandidateResponse[];
  page: number;
  page_size: number;
}

export interface CandidateReviewRequest {
  action: CandidateStatus;
  translations?: Record<string, string>;
  migrate_to_match?: boolean;
  migrate_to_business?: boolean;
}

export interface GlossaryImportRequest {
  terms: GlossaryTermCreate[];
  overwrite?: boolean;
}

export interface GlossaryImportResponse {
  imported: number;
  skipped: number;
  errors: string[];
}

export interface GlossaryExportResponse {
  terms: GlossaryTermResponse[];
  exported_at: string;
  total: number;
}

export interface GlossaryExtractRequest {
  source_text: string;
  human_translation: string;
  target_lang: string;
  translation_job_id?: string;
}

export interface ExtractedTerm {
  term_en: string;
  suggested_translation: string;
  confidence: number;
  context: string;
}

export interface GlossaryExtractResponse {
  extracted_terms: ExtractedTerm[];
  candidates_created: number;
}

export interface MatchGlossaryLookupResponse {
  term_en: string;
  target_lang: string;
  translation: string | null;
  found: boolean;
}
