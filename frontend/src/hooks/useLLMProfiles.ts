import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { llmProfilesApi } from "@/lib/api";
import { queryKeys } from "@/lib/queryClient";
import type {
  LLMProfileCreate,
  LLMProfileUpdate,
  LLMTestRequest,
} from "@/types";

// ─────────────────────────────────────────────────────────────────────────────
// Queries
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Fetch all LLM profiles (paginated).
 * Defaults to fetching up to 100 profiles.
 */
export function useLLMProfiles(params?: { skip?: number; limit?: number }) {
  return useQuery({
    queryKey: queryKeys.llmProfiles.list(params),
    queryFn: () => llmProfilesApi.list(params),
  });
}

/**
 * Fetch a single LLM profile by ID.
 * Only runs when `id` is defined.
 */
export function useLLMProfile(id: number | undefined) {
  return useQuery({
    queryKey: queryKeys.llmProfiles.detail(id!),
    queryFn: () => llmProfilesApi.get(id!),
    enabled: id !== undefined,
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Mutations
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Create a new LLM profile.
 * Invalidates the profiles list on success.
 */
export function useCreateLLMProfile() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: (payload: LLMProfileCreate) => llmProfilesApi.create(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.llmProfiles.lists() });
    },
  });
}

/**
 * Update an existing LLM profile.
 * Invalidates the list and the specific detail on success.
 */
export function useUpdateLLMProfile() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: LLMProfileUpdate }) =>
      llmProfilesApi.update(id, payload),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: queryKeys.llmProfiles.lists() });
      qc.setQueryData(queryKeys.llmProfiles.detail(data.id), data);
    },
  });
}

/**
 * Delete an LLM profile by ID.
 * Removes the cached detail entry and invalidates the list.
 */
export function useDeleteLLMProfile() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: (id: number) => llmProfilesApi.delete(id),
    onSuccess: (_data, id) => {
      qc.removeQueries({ queryKey: queryKeys.llmProfiles.detail(id) });
      qc.invalidateQueries({ queryKey: queryKeys.llmProfiles.lists() });
    },
  });
}

/**
 * Set a profile as the global default.
 * Invalidates all profiles because `is_default` changes on multiple rows.
 */
export function useSetDefaultLLMProfile() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: (id: number) => llmProfilesApi.setDefault(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.llmProfiles.all });
    },
  });
}

/**
 * Test LLM connectivity for a given profile ID.
 * This mutation does NOT invalidate any cache — it is a read-only test call.
 */
export function useTestLLMProfile() {
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body?: LLMTestRequest }) =>
      llmProfilesApi.test(id, body),
    // No cache invalidation needed — purely a connectivity test
    retry: 0,
  });
}
