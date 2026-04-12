import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { pipelineApi } from "@/lib/api";
import { queryKeys } from "@/lib/queryClient";
import type { PipelineRunResponse, PipelineActionResponse } from "@/types";

// ─────────────────────────────────────────────────────────────────────────────
// Queries
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Fetch all pipeline runs (paginated).
 * Defaults to fetching up to 100 runs.
 */
export function usePipelineRuns(params?: {
  skip?: number;
  limit?: number;
  template_id?: string;
  status?: string;
  page?: number;
  page_size?: number;
}) {
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
 * Start a V3 DAG pipeline run from a template.
 * Accepts an optional file and LLM profile override.
 * Invalidates the pipeline runs list on success.
 */
export function useStartDagPipeline() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: ({
      templateId,
      file,
      llmProfileId,
      runParams,
    }: {
      templateId: string;
      file?: File | null;
      llmProfileId?: number | null;
      runParams?: Record<string, unknown>;
    }) => pipelineApi.createRun(templateId, file, llmProfileId, runParams),
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
    onSuccess: (_data: PipelineActionResponse, runId: string) => {
      // Refresh the run detail so the status reflects "cancelled"
      qc.invalidateQueries({
        queryKey: queryKeys.pipelineRuns.detail(runId),
      });
      qc.invalidateQueries({ queryKey: queryKeys.pipelineRuns.lists() });
    },
  });
}

/**
 * Pause a running pipeline.
 * Invalidates the specific run detail on success.
 */
export function usePausePipeline() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: (runId: string) => pipelineApi.pauseRun(runId),
    onSuccess: (_data, runId) => {
      qc.invalidateQueries({ queryKey: queryKeys.pipelineRuns.detail(runId) });
      qc.invalidateQueries({ queryKey: queryKeys.pipelineRuns.lists() });
    },
  });
}

/**
 * Resume a paused pipeline.
 * Invalidates the specific run detail on success.
 */
export function useResumePipeline() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: (runId: string) => pipelineApi.resumeRun(runId),
    onSuccess: (_data, runId) => {
      qc.invalidateQueries({ queryKey: queryKeys.pipelineRuns.detail(runId) });
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

/**
 * Fetch results for a specific stage of a pipeline run.
 * Enabled only when both runId and stage are provided.
 */
export function useStageResults(
  runId: string | undefined,
  stage: string | undefined,
) {
  return useQuery({
    queryKey:
      runId && stage
        ? queryKeys.stageResults.byStage(runId, stage)
        : ["stage-results", "disabled"],
    queryFn: () =>
      pipelineApi.getRunResults(runId!, stage ? { stage } : undefined),
    enabled: !!runId && !!stage,
    staleTime: 5 * 60_000, // stage results don't change once saved
  });
}

/**
 * Fetch the result for a specific node in a V3 pipeline run.
 */
export function useNodeResult(
  runId: string | undefined,
  nodeId: string | undefined,
) {
  return useQuery({
    queryKey:
      runId && nodeId
        ? ["node-result", runId, nodeId]
        : ["node-result", "disabled"],
    queryFn: () => pipelineApi.getNodeResult(runId!, nodeId!),
    enabled: !!runId && !!nodeId,
    staleTime: 5 * 60_000,
  });
}
