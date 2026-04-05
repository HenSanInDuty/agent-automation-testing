"use client";

import * as React from "react";
import { Pause, Play, XCircle } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { toast } from "@/components/ui/Toast";
import {
  usePausePipeline,
  useResumePipeline,
  useCancelPipeline,
} from "@/hooks/usePipeline";
import type { PipelineStatus } from "@/types";

// ─────────────────────────────────────────────────────────────────────────────
// Props
// ─────────────────────────────────────────────────────────────────────────────

interface PipelineControlsProps {
  runId: string;
  status: PipelineStatus;
  onPaused?: () => void;
  onResumed?: () => void;
  onCancelled?: () => void;
}

// ─────────────────────────────────────────────────────────────────────────────
// PipelineControls
// ─────────────────────────────────────────────────────────────────────────────

export function PipelineControls({
  runId,
  status,
  onPaused,
  onResumed,
  onCancelled,
}: PipelineControlsProps) {
  const pauseMutation = usePausePipeline();
  const resumeMutation = useResumePipeline();
  const cancelMutation = useCancelPipeline();

  const handlePause = async () => {
    try {
      await pauseMutation.mutateAsync(runId);
      toast.info(
        "Pause requested",
        "Pipeline will pause after the current stage completes.",
      );
      onPaused?.();
    } catch (err) {
      toast.error(
        "Pause failed",
        err instanceof Error ? err.message : "Could not pause the pipeline.",
      );
    }
  };

  const handleResume = async () => {
    try {
      await resumeMutation.mutateAsync(runId);
      toast.success(
        "Pipeline resumed",
        "The pipeline is continuing from where it left off.",
      );
      onResumed?.();
    } catch (err) {
      toast.error(
        "Resume failed",
        err instanceof Error ? err.message : "Could not resume the pipeline.",
      );
    }
  };

  const handleCancel = async () => {
    try {
      await cancelMutation.mutateAsync(runId);
      toast.warning("Pipeline cancelled", "The pipeline run has been stopped.");
      onCancelled?.();
    } catch (err) {
      toast.error(
        "Cancel failed",
        err instanceof Error ? err.message : "Could not cancel the pipeline.",
      );
    }
  };

  if (status === "running") {
    return (
      <div className="flex items-center gap-2">
        <Button
          variant="secondary"
          size="sm"
          loading={pauseMutation.isPending}
          leftIcon={
            !pauseMutation.isPending ? (
              <Pause className="w-3.5 h-3.5" aria-hidden="true" />
            ) : undefined
          }
          onClick={handlePause}
          aria-label="Pause pipeline"
          title="Pause pipeline between stages"
        >
          Pause
        </Button>
        <Button
          variant="danger"
          size="sm"
          loading={cancelMutation.isPending}
          leftIcon={
            !cancelMutation.isPending ? (
              <XCircle className="w-3.5 h-3.5" aria-hidden="true" />
            ) : undefined
          }
          onClick={handleCancel}
          aria-label="Cancel pipeline"
        >
          Cancel
        </Button>
      </div>
    );
  }

  if (status === "paused") {
    return (
      <div className="flex items-center gap-2">
        <Button
          variant="primary"
          size="sm"
          loading={resumeMutation.isPending}
          leftIcon={
            !resumeMutation.isPending ? (
              <Play className="w-3.5 h-3.5" aria-hidden="true" />
            ) : undefined
          }
          onClick={handleResume}
          aria-label="Resume pipeline"
        >
          Resume
        </Button>
        <Button
          variant="danger"
          size="sm"
          loading={cancelMutation.isPending}
          leftIcon={
            !cancelMutation.isPending ? (
              <XCircle className="w-3.5 h-3.5" aria-hidden="true" />
            ) : undefined
          }
          onClick={handleCancel}
          aria-label="Cancel pipeline"
        >
          Cancel
        </Button>
      </div>
    );
  }

  // For any other status (pending, completed, failed, cancelled) render nothing
  return null;
}
