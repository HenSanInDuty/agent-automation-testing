import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { stageConfigsApi } from "@/lib/api";
import { queryKeys } from "@/lib/queryClient";
import type { StageConfigCreate, StageConfigUpdate, StageReorderRequest } from "@/types";

// ─────────────────────────────────────────────────────────────────────────────
// Queries
// ─────────────────────────────────────────────────────────────────────────────

/** Fetch all stage configs sorted by order. */
export function useStageConfigs() {
  return useQuery({
    queryKey: queryKeys.stageConfigs.list(),
    queryFn: () => stageConfigsApi.list(),
  });
}

/** Fetch a single stage config by stage_id. */
export function useStageConfig(stageId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.stageConfigs.detail(stageId!),
    queryFn: () => stageConfigsApi.get(stageId!),
    enabled: !!stageId,
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Mutations
// ─────────────────────────────────────────────────────────────────────────────

/** Create a new (custom) stage config. */
export function useCreateStageConfig() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: (payload: StageConfigCreate) => stageConfigsApi.create(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.stageConfigs.all });
    },
  });
}

/** Update an existing stage config. */
export function useUpdateStageConfig() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: ({
      stageId,
      payload,
    }: {
      stageId: string;
      payload: StageConfigUpdate;
    }) => stageConfigsApi.update(stageId, payload),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: queryKeys.stageConfigs.list() });
      qc.setQueryData(queryKeys.stageConfigs.detail(data.stage_id), data);
    },
  });
}

/** Delete a custom stage config. */
export function useDeleteStageConfig() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: (stageId: string) => stageConfigsApi.delete(stageId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.stageConfigs.all });
    },
  });
}

/** Reorder stages (batch update). */
export function useReorderStages() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: (payload: StageReorderRequest) =>
      stageConfigsApi.reorder(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.stageConfigs.list() });
    },
  });
}
