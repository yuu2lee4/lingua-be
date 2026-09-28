"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getTerms,
  getTerm,
  createTerm,
  updateTerm,
  deleteTerm,
  updateTermTranslation,
  getCandidates,
  reviewCandidate,
  importTerms,
  exportTerms,
} from "@/lib/api/glossary";
import type {
  GlossaryTermCreate,
  GlossaryTermUpdate,
  TranslationUpdate,
  CandidateReviewRequest,
  GlossaryImportRequest,
} from "@/types/glossary";

export function useTerms(params: {
  page?: number;
  page_size?: number;
  status?: string;
  search?: string;
}) {
  return useQuery({
    queryKey: ["glossary", "terms", params],
    queryFn: () => getTerms(params),
  });
}

export function useTerm(termId: string) {
  return useQuery({
    queryKey: ["glossary", "terms", termId],
    queryFn: () => getTerm(termId),
    enabled: !!termId,
  });
}

export function useCreateTerm() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: GlossaryTermCreate) => createTerm(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["glossary", "terms"] });
    },
  });
}

export function useUpdateTerm() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ termId, data }: { termId: string; data: GlossaryTermUpdate }) =>
      updateTerm(termId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["glossary", "terms"] });
    },
  });
}

export function useDeleteTerm() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (termId: string) => deleteTerm(termId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["glossary", "terms"] });
    },
  });
}

export function useUpdateTermTranslation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      termId,
      langCode,
      data,
    }: {
      termId: string;
      langCode: string;
      data: TranslationUpdate;
    }) => updateTermTranslation(termId, langCode, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["glossary", "terms"] });
    },
  });
}

export function useCandidates(params: {
  page?: number;
  page_size?: number;
  status?: string;
}) {
  return useQuery({
    queryKey: ["glossary", "candidates", params],
    queryFn: () => getCandidates(params),
  });
}

export function useReviewCandidate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      candidateId,
      data,
    }: {
      candidateId: number;
      data: CandidateReviewRequest;
    }) => reviewCandidate(candidateId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["glossary", "candidates"] });
      queryClient.invalidateQueries({ queryKey: ["glossary", "terms"] });
    },
  });
}

export function useImportTerms() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: GlossaryImportRequest) => importTerms(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["glossary", "terms"] });
    },
  });
}

export function useExportTerms() {
  return useQuery({
    queryKey: ["glossary", "export"],
    queryFn: () => exportTerms(),
    enabled: false,
  });
}
