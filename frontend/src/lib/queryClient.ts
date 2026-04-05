import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Cache data for 60 seconds before considering it stale
      staleTime: 60_000,
      // Keep unused data in cache for 5 minutes
      gcTime: 5 * 60_000,
      // Retry failed requests up to 2 times
      retry: 2,
      // Retry with exponential backoff, capped at 10 seconds
      retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 10_000),
      // Refetch on window focus in production, not in development
      refetchOnWindowFocus: process.env.NODE_ENV === "production",
    },
    mutations: {
      // Retry mutations once on failure
      retry: 1,
    },
  },
});

// ─────────────────────────────────────────────────────────────────────────────
// Query key factories
// Centralised query keys to avoid magic strings and enable precise invalidation
// ─────────────────────────────────────────────────────────────────────────────

export const queryKeys = {
  // LLM Profiles
  llmProfiles: {
    all: ["llm-profiles"] as const,
    lists: () => [...queryKeys.llmProfiles.all, "list"] as const,
    list: (params?: { skip?: number; limit?: number }) =>
      [...queryKeys.llmProfiles.lists(), params] as const,
    details: () => [...queryKeys.llmProfiles.all, "detail"] as const,
    detail: (id: number) => [...queryKeys.llmProfiles.details(), id] as const,
  },

  // Agent Configs
  agentConfigs: {
    all: ["agent-configs"] as const,
    lists: () => [...queryKeys.agentConfigs.all, "list"] as const,
    grouped: () => [...queryKeys.agentConfigs.all, "grouped"] as const,
    details: () => [...queryKeys.agentConfigs.all, "detail"] as const,
    detail: (agentId: string) =>
      [...queryKeys.agentConfigs.details(), agentId] as const,
  },

  // Stage Configs
  stageConfigs: {
    all: ["stage-configs"] as const,
    lists: () => [...queryKeys.stageConfigs.all, "list"] as const,
    list: () => [...queryKeys.stageConfigs.lists()] as const,
    details: () => [...queryKeys.stageConfigs.all, "detail"] as const,
    detail: (stageId: string) =>
      [...queryKeys.stageConfigs.details(), stageId] as const,
  },

  // Pipeline Runs
  pipelineRuns: {
    all: ["pipeline-runs"] as const,
    lists: () => [...queryKeys.pipelineRuns.all, "list"] as const,
    list: (params?: { skip?: number; limit?: number }) =>
      [...queryKeys.pipelineRuns.lists(), params] as const,
    details: () => [...queryKeys.pipelineRuns.all, "detail"] as const,
    detail: (runId: string) =>
      [...queryKeys.pipelineRuns.details(), runId] as const,
  },

  // Pipeline Stage Results
  stageResults: {
    all: ["stage-results"] as const,
    byRun: (runId: string) => [...queryKeys.stageResults.all, runId] as const,
    byStage: (runId: string, stage: string) =>
      [...queryKeys.stageResults.byRun(runId), stage] as const,
  },

  // Health
  health: ["health"] as const,
} as const;
