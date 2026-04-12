import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { stageConfigsApi } from "@/lib/api";
import { queryKeys } from "@/lib/queryClient";
import type {
  StageConfig,
  StageConfigCreate,
  StageConfigUpdate,
} from "@/types";

/** Fetch all stage configs sorted by order, optionally filtered by pipeline template. */
export function useStageConfigs(
  enabledOnly = false,
  templateId?: string,
  noFallback = false,
) {
  return useQuery<StageConfig[]>({
    queryKey: templateId
      ? queryKeys.stageConfigs.listForTemplate(templateId)
      : queryKeys.stageConfigs.list({ enabled_only: enabledOnly }),
    queryFn: () => stageConfigsApi.list(enabledOnly, templateId, noFallback),
    staleTime: 5 * 60 * 1000,
  });
}

/** Fetch a single stage config by stage_id. */
export function useStageConfig(stageId: string | undefined) {
  return useQuery<StageConfig>({
    queryKey: queryKeys.stageConfigs.detail(stageId!),
    queryFn: () => stageConfigsApi.get(stageId!),
    enabled: !!stageId,
  });
}

/** Create a new (custom) stage config. */
export function useCreateStageConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: StageConfigCreate) => stageConfigsApi.create(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.stageConfigs.all });
      qc.invalidateQueries({ queryKey: queryKeys.agentConfigs.all });
      qc.invalidateQueries({ queryKey: queryKeys.agentConfigs.byPipeline() });
    },
  });
}

/** Update an existing stage config. */
export function useUpdateStageConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      stageId,
      data,
    }: {
      stageId: string;
      data: StageConfigUpdate;
    }) => stageConfigsApi.update(stageId, data),
    onSuccess: (result) => {
      qc.invalidateQueries({ queryKey: queryKeys.stageConfigs.all });
      qc.invalidateQueries({ queryKey: queryKeys.agentConfigs.all });
      qc.invalidateQueries({ queryKey: queryKeys.agentConfigs.byPipeline() });
      qc.setQueryData(queryKeys.stageConfigs.detail(result.stage_id), result);
    },
  });
}

/** Delete a custom stage config. Agents are reassigned to "custom". */
export function useDeleteStageConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (stageId: string) => stageConfigsApi.delete(stageId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.stageConfigs.all });
      qc.invalidateQueries({ queryKey: queryKeys.agentConfigs.all });
      qc.invalidateQueries({ queryKey: queryKeys.agentConfigs.byPipeline() });
    },
  });
}

/** Reorder stages by providing an ordered list of stage_ids. */
export function useReorderStages() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (stageIds: string[]) => stageConfigsApi.reorder(stageIds),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.stageConfigs.all });
      qc.invalidateQueries({ queryKey: queryKeys.agentConfigs.byPipeline() });
    },
  });
}
