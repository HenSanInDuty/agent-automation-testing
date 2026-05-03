import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { toolsApi } from "@/lib/api";
import type { ToolListResponse, AgentToolsResponse } from "@/types";

// ─────────────────────────────────────────────────────────────────────────────
// Query keys
// ─────────────────────────────────────────────────────────────────────────────

export const toolQueryKeys = {
  all: ["tools"] as const,
  list: () => [...toolQueryKeys.all, "list"] as const,
  agentTools: (agentId: string) =>
    [...toolQueryKeys.all, "agent", agentId] as const,
};

// ─────────────────────────────────────────────────────────────────────────────
// Queries
// ─────────────────────────────────────────────────────────────────────────────

/** Fetch all registered tools from the ToolRegistry. */
export function useTools() {
  return useQuery<ToolListResponse>({
    queryKey: toolQueryKeys.list(),
    queryFn: () => toolsApi.list(),
    staleTime: 5 * 60 * 1000, // tool list rarely changes
  });
}

/** Fetch the tool_names assigned to a specific agent. */
export function useAgentTools(agentId: string | undefined) {
  return useQuery<AgentToolsResponse>({
    queryKey: toolQueryKeys.agentTools(agentId ?? ""),
    queryFn: () => toolsApi.getAgentTools(agentId!),
    enabled: !!agentId,
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Mutations
// ─────────────────────────────────────────────────────────────────────────────

/** Replace the tool_names list for an agent. */
export function useUpdateAgentTools() {
  const queryClient = useQueryClient();

  return useMutation<
    AgentToolsResponse,
    Error,
    { agentId: string; toolNames: string[] }
  >({
    mutationFn: ({ agentId, toolNames }) =>
      toolsApi.updateAgentTools(agentId, toolNames),
    onSuccess: (data, { agentId }) => {
      // Invalidate both agent-tools cache and the agent config cache
      queryClient.invalidateQueries({
        queryKey: toolQueryKeys.agentTools(agentId),
      });
      queryClient.invalidateQueries({ queryKey: ["agentConfigs"] });
    },
  });
}
