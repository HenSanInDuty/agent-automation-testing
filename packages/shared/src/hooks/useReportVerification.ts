/**
 * useReportVerification — React Query hook that fetches the 3-component
 * verification result for a pipeline run.
 *
 * Used by ReportVerificationCard + the download-gating logic to disable the
 * Download HTML/DOCX buttons until the report passes verification.
 */
import { useQuery } from "@tanstack/react-query";

import { pipelineApi } from "../api/client";
import type { ReportVerificationResponse } from "../types";

export interface UseReportVerificationOptions {
  /** Run id to query. Pass undefined/null to disable the query. */
  runId: string | undefined | null;
  /** Re-fetch interval (ms). Set null to disable. Default: 5_000 while not verified. */
  refetchInterval?: number | false | null;
  /** Whether to run the query at all. */
  enabled?: boolean;
}

export function useReportVerification({
  runId,
  refetchInterval,
  enabled = true,
}: UseReportVerificationOptions) {
  return useQuery<ReportVerificationResponse>({
    queryKey: ["pipeline", "report-verification", runId],
    queryFn: () => pipelineApi.getReportVerification(String(runId)),
    enabled: Boolean(runId) && enabled,
    refetchInterval: (query) => {
      if (refetchInterval === false || refetchInterval === null) return false;
      const data = query.state.data;
      // Stop polling once we have a definitive verified=true result.
      if (data && data.verified === true) return false;
      return refetchInterval ?? 5_000;
    },
    staleTime: 1_000,
  });
}
