import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { agentConfigsApi } from "@/lib/api";
import { queryKeys } from "@/lib/queryClient";
import type {
  AgentConfigCreate,
  AgentConfigUpdate,
  AgentConfigGroupedResponse,
  AgentConfigByPipelineResponse,
} from "@/types";

// ─────────────────────────────────────────────────────────────────────────────
// Queries
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Fetch all agent configs grouped by pipeline stage.
 * Shape: { groups: AgentGroupEntry[], total_agents: number }
 */
export function useAgentConfigsGrouped() {
  return useQuery<AgentConfigGroupedResponse>({
    queryKey: queryKeys.agentConfigs.grouped(),
    queryFn: () => agentConfigsApi.listGrouped(),
  });
}

/**
 * Fetch all agent configs grouped by pipeline → stage hierarchy.
 * Shape: { pipelines: PipelineAgentGroup[], total_agents: number }
 */
export function useAgentConfigsByPipeline() {
  return useQuery<AgentConfigByPipelineResponse>({
    queryKey: queryKeys.agentConfigs.byPipeline(),
    queryFn: () => agentConfigsApi.listByPipeline(),
  });
}

/**
 * Fetch a single agent config (full detail including role, goal, backstory).
 * Only runs when `agentId` is defined.
 */
export function useAgentConfig(agentId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.agentConfigs.detail(agentId!),
    queryFn: () => agentConfigsApi.get(agentId!),
    enabled: agentId !== undefined && agentId !== "",
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Mutations
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Update an agent config (partial update – only supplied fields are changed).
 * Invalidates both the grouped list and the specific detail cache on success.
 */
export function useUpdateAgentConfig() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: ({
      agentId,
      payload,
    }: {
      agentId: string;
      payload: AgentConfigUpdate;
    }) => agentConfigsApi.update(agentId, payload),
    onSuccess: (data) => {
      // Refresh the grouped list (displayed in the main table)
      qc.invalidateQueries({ queryKey: queryKeys.agentConfigs.grouped() });
      // Refresh the by-pipeline view
      qc.invalidateQueries({ queryKey: queryKeys.agentConfigs.byPipeline() });
      // Update the cached detail entry immediately so the dialog re-opens with
      // fresh data without an extra network round-trip.
      qc.setQueryData(queryKeys.agentConfigs.detail(data.agent_id), data);
    },
  });
}

/**
 * Reset a single agent config to its seeded default values.
 * Invalidates the grouped list and removes the stale detail entry.
 */
export function useResetAgentConfig() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: (agentId: string) => agentConfigsApi.reset(agentId),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: queryKeys.agentConfigs.grouped() });
      qc.invalidateQueries({ queryKey: queryKeys.agentConfigs.byPipeline() });
      // Store the fresh detail returned by the reset endpoint
      qc.setQueryData(
        queryKeys.agentConfigs.detail(data.agent_id),
        data.config,
      );
    },
  });
}

/**
 * Reset ALL agent configs to their seeded default values.
 * Invalidates the entire agent-configs cache so everything refetches.
 */
export function useResetAllAgentConfigs() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: () => agentConfigsApi.resetAll(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.agentConfigs.all });
    },
  });
}

/**
 * Create a new custom agent config.
 * Invalidates the grouped list so the new agent appears immediately.
 */
export function useCreateAgentConfig() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: (payload: AgentConfigCreate) => agentConfigsApi.create(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.agentConfigs.grouped() });
      qc.invalidateQueries({ queryKey: queryKeys.agentConfigs.byPipeline() });
    },
  });
}

/**
 * Delete a custom agent config.
 * Invalidates the grouped list and removes the stale detail entry.
 */
export function useDeleteAgentConfig() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: (agentId: string) => agentConfigsApi.delete(agentId),
    onSuccess: (_data: void, agentId: string) => {
      qc.invalidateQueries({ queryKey: queryKeys.agentConfigs.grouped() });
      qc.invalidateQueries({ queryKey: queryKeys.agentConfigs.byPipeline() });
      qc.removeQueries({ queryKey: queryKeys.agentConfigs.detail(agentId) });
    },
  });
}
