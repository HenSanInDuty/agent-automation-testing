import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { pipelineApi } from "@/lib/api";
import { queryKeys } from "@/lib/queryClient";
import type { PipelineRunResponse } from "@/types";

// ─────────────────────────────────────────────────────────────────────────────
// Queries
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Fetch all pipeline runs (paginated).
 * Defaults to fetching up to 100 runs.
 */
export function usePipelineRuns(params?: { skip?: number; limit?: number }) {
  return useQuery({
    queryKey: queryKeys.pipelineRuns.list(params),
    queryFn: () => pipelineApi.listRuns(params),
  });
}

/**
 * Fetch a single pipeline run by ID.
 * Only runs when `runId` is defined.
 */
export function usePipelineRun(runId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.pipelineRuns.detail(runId!),
    queryFn: () => pipelineApi.getRun(runId!),
    enabled: runId !== undefined && runId !== "",
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Mutations
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Start a new pipeline run by uploading a document file.
 * Accepts an optional LLM profile ID to override the default.
 * Invalidates the pipeline runs list on success.
 */
export function useStartPipeline() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: ({
      file,
      llmProfileId,
    }: {
      file: File;
      llmProfileId?: number | null;
    }) => pipelineApi.run(file, llmProfileId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.pipelineRuns.lists() });
    },
  });
}

/**
 * Cancel an in-progress pipeline run.
 * Invalidates the specific run detail and the runs list on success.
 */
export function useCancelPipeline() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: (runId: string) => pipelineApi.cancelRun(runId),
    onSuccess: (_data: PipelineRunResponse, runId: string) => {
      // Refresh the run detail so the status reflects "cancelled"
      qc.invalidateQueries({
        queryKey: queryKeys.pipelineRuns.detail(runId),
      });
      qc.invalidateQueries({ queryKey: queryKeys.pipelineRuns.lists() });
    },
  });
}

/**
 * Delete a pipeline run record.
 * Removes the cached detail entry and invalidates the runs list on success.
 */
export function useDeletePipelineRun() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: (runId: string) => pipelineApi.deleteRun(runId),
    onSuccess: (_data: void, runId: string) => {
      qc.removeQueries({ queryKey: queryKeys.pipelineRuns.detail(runId) });
      qc.invalidateQueries({ queryKey: queryKeys.pipelineRuns.lists() });
    },
  });
}
