"use client";

import {
  useQuery,
  useMutation,
  useQueryClient,
  type UseQueryOptions,
} from "@tanstack/react-query";
import { pipelineTemplatesApi } from "@/lib/api";
import type {
  PipelineTemplate,
  PipelineTemplateCreate,
  PipelineTemplateUpdate,
  PipelineTemplateListResponse,
  DAGValidationResult,
  TemplateExportEnvelope,
} from "@/types";

// ─────────────────────────────────────────────────────────────────────────────
// Query keys
// ─────────────────────────────────────────────────────────────────────────────

export const templateKeys = {
  all: ["pipeline-templates"] as const,
  lists: () => [...templateKeys.all, "list"] as const,
  list: (params?: object) => [...templateKeys.lists(), params] as const,
  details: () => [...templateKeys.all, "detail"] as const,
  detail: (id: string) => [...templateKeys.details(), id] as const,
};

// ─────────────────────────────────────────────────────────────────────────────
// List templates
// ─────────────────────────────────────────────────────────────────────────────

export function usePipelineTemplates(params?: {
  skip?: number;
  limit?: number;
  include_archived?: boolean;
  tag?: string;
}) {
  return useQuery<PipelineTemplateListResponse, Error>({
    queryKey: templateKeys.list(params),
    queryFn: () => pipelineTemplatesApi.list(params),
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Get single template
// ─────────────────────────────────────────────────────────────────────────────

export function usePipelineTemplate(
  templateId: string | null,
  options?: Partial<UseQueryOptions<PipelineTemplate, Error>>,
) {
  return useQuery<PipelineTemplate, Error>({
    queryKey: templateKeys.detail(templateId ?? ""),
    queryFn: () => pipelineTemplatesApi.get(templateId!),
    enabled: !!templateId,
    ...options,
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Create template
// ─────────────────────────────────────────────────────────────────────────────

export function useCreateTemplate() {
  const queryClient = useQueryClient();
  return useMutation<PipelineTemplate, Error, PipelineTemplateCreate>({
    mutationFn: (payload) => pipelineTemplatesApi.create(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: templateKeys.lists() });
    },
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Update template
// ─────────────────────────────────────────────────────────────────────────────

export function useUpdateTemplate(templateId: string) {
  const queryClient = useQueryClient();
  return useMutation<PipelineTemplate, Error, PipelineTemplateUpdate>({
    mutationFn: (payload) => pipelineTemplatesApi.update(templateId, payload),
    onSuccess: (updated) => {
      queryClient.setQueryData(templateKeys.detail(templateId), updated);
      queryClient.invalidateQueries({ queryKey: templateKeys.lists() });
    },
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Clone template
// ─────────────────────────────────────────────────────────────────────────────

export function useCloneTemplate() {
  const queryClient = useQueryClient();
  return useMutation<
    PipelineTemplate,
    Error,
    { templateId: string; newTemplateId: string; newName: string }
  >({
    mutationFn: ({ templateId, newTemplateId, newName }) =>
      pipelineTemplatesApi.clone(templateId, newTemplateId, newName),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: templateKeys.lists() });
    },
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Delete template
// ─────────────────────────────────────────────────────────────────────────────

export function useDeleteTemplate() {
  const queryClient = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (templateId) => pipelineTemplatesApi.delete(templateId),
    onSuccess: (_data, templateId) => {
      queryClient.removeQueries({ queryKey: templateKeys.detail(templateId) });
      queryClient.invalidateQueries({ queryKey: templateKeys.lists() });
    },
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Archive template
// ─────────────────────────────────────────────────────────────────────────────

export function useArchiveTemplate() {
  const queryClient = useQueryClient();
  return useMutation<PipelineTemplate, Error, string>({
    mutationFn: (templateId) => pipelineTemplatesApi.archive(templateId),
    onSuccess: (updated) => {
      queryClient.setQueryData(
        templateKeys.detail(updated.template_id),
        updated,
      );
      queryClient.invalidateQueries({ queryKey: templateKeys.lists() });
    },
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Validate template DAG
// ─────────────────────────────────────────────────────────────────────────────

export function useValidateTemplate() {
  return useMutation<DAGValidationResult, Error, string>({
    mutationFn: (templateId) => pipelineTemplatesApi.validate(templateId),
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Export template
// ─────────────────────────────────────────────────────────────────────────────

export function useExportTemplate() {
  return useMutation<TemplateExportEnvelope, Error, string>({
    mutationFn: (templateId) => pipelineTemplatesApi.exportTemplate(templateId),
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Import template
// ─────────────────────────────────────────────────────────────────────────────

export function useImportTemplate() {
  const queryClient = useQueryClient();
  return useMutation<PipelineTemplate, Error, PipelineTemplate>({
    mutationFn: (templateData) =>
      pipelineTemplatesApi.importTemplate(templateData),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: templateKeys.lists() });
    },
  });
}
