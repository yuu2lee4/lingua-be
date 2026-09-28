import { api } from "./client";
import type {
  GlossaryTermResponse,
  GlossaryTermListResponse,
  GlossaryTermCreate,
  GlossaryTermUpdate,
  TranslationUpdate,
  GlossaryCandidateListResponse,
  GlossaryCandidateResponse,
  CandidateReviewRequest,
  GlossaryImportRequest,
  GlossaryImportResponse,
  GlossaryExportResponse,
} from "@/types/glossary";

export async function getTerms(params: {
  page?: number;
  page_size?: number;
  status?: string;
  search?: string;
}): Promise<GlossaryTermListResponse> {
  const searchParams = new URLSearchParams();
  if (params.page) searchParams.set("page", String(params.page));
  if (params.page_size) searchParams.set("page_size", String(params.page_size));
  if (params.status) searchParams.set("status", params.status);
  if (params.search) searchParams.set("search", params.search);
  return api.get("glossary/terms", { searchParams }).json();
}

export async function getTerm(termId: string): Promise<GlossaryTermResponse> {
  return api.get(`glossary/terms/${termId}`).json();
}

export async function createTerm(data: GlossaryTermCreate): Promise<GlossaryTermResponse> {
  return api.post("glossary/terms", { json: data }).json();
}

export async function updateTerm(termId: string, data: GlossaryTermUpdate): Promise<GlossaryTermResponse> {
  return api.patch(`glossary/terms/${termId}`, { json: data }).json();
}

export async function deleteTerm(termId: string): Promise<void> {
  await api.delete(`glossary/terms/${termId}`);
}

export async function updateTermTranslation(
  termId: string,
  langCode: string,
  data: TranslationUpdate
): Promise<Record<string, string>> {
  return api.put(`glossary/terms/${termId}/translations/${langCode}`, { json: data }).json();
}

export async function searchTerms(keyword: string, limit?: number): Promise<GlossaryTermResponse[]> {
  const searchParams = new URLSearchParams({ keyword });
  if (limit) searchParams.set("limit", String(limit));
  return api.get("glossary/terms/search", { searchParams }).json();
}

export async function getCandidates(params: {
  page?: number;
  page_size?: number;
  status?: string;
}): Promise<GlossaryCandidateListResponse> {
  const searchParams = new URLSearchParams();
  if (params.page) searchParams.set("page", String(params.page));
  if (params.page_size) searchParams.set("page_size", String(params.page_size));
  if (params.status) searchParams.set("status", params.status);
  return api.get("glossary/candidates", { searchParams }).json();
}

export async function reviewCandidate(
  candidateId: number,
  data: CandidateReviewRequest
): Promise<GlossaryCandidateResponse> {
  return api.post(`glossary/candidates/${candidateId}/review`, { json: data }).json();
}

export async function importTerms(data: GlossaryImportRequest): Promise<GlossaryImportResponse> {
  return api.post("glossary/import", { json: data }).json();
}

export async function exportTerms(): Promise<GlossaryExportResponse> {
  return api.get("glossary/export").json();
}
