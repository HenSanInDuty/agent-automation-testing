import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { agentConfigsApi } from "@/lib/api";
import { queryKeys } from "@/lib/queryClient";
import type { AgentConfigUpdate } from "@/types";

// ─────────────────────────────────────────────────────────────────────────────
// Queries
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Fetch all agent configs grouped by pipeline stage.
 * Shape: { ingestion: [...], testcase: [...], execution: [...], reporting: [...] }
 */
export function useAgentConfigsGrouped() {
  return useQuery({
    queryKey: queryKeys.agentConfigs.grouped(),
    queryFn: () => agentConfigsApi.listGrouped(),
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
      // Store the fresh detail returned by the reset endpoint
      qc.setQueryData(
        queryKeys.agentConfigs.detail(data.agent_id),
        data.config
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
