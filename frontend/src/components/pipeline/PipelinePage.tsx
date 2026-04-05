"use client";

import * as React from "react";
import { Zap, History, PlayCircle, StopCircle } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { toast } from "@/components/ui/Toast";
import {
  useStartPipeline,
  useCancelPipeline,
  usePipelineRun,
} from "@/hooks/usePipeline";
import { usePipelineWebSocket } from "@/hooks/usePipelineWebSocket";
import { cn } from "@/lib/utils";
import type { PipelineRunResponse, PipelineStatus, WSEvent } from "@/types";

import { DocumentUpload } from "./DocumentUpload";
import { LLMProfileSelector } from "./LLMProfileSelector";
import { PipelineProgress } from "./PipelineProgress";
import { ResultsViewer } from "./ResultsViewer";
import { RunHistory } from "./RunHistory";

// ─────────────────────────────────────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────────────────────────────────────

const TERMINAL_STATUSES: PipelineStatus[] = [
  "completed",
  "failed",
  "cancelled",
];

// ─────────────────────────────────────────────────────────────────────────────
// Empty right-panel placeholder
// ─────────────────────────────────────────────────────────────────────────────

function RightPanelPlaceholder() {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center",
        "rounded-2xl border border-dashed border-[#2b3b55]",
        "bg-[#18202F]/50 py-20 px-6 text-center",
        "min-h-[18rem]",
      )}
    >
      <div
        className={cn(
          "w-14 h-14 rounded-2xl mb-4",
          "bg-[#135bec]/10 border border-[#135bec]/20",
          "flex items-center justify-center",
        )}
        aria-hidden="true"
      >
        <Zap className="w-6 h-6 text-[#135bec]" />
      </div>

      <p className="text-sm font-medium text-[#92a4c9]">No active run</p>
      <p className="mt-1.5 text-xs text-[#3d5070] leading-relaxed max-w-xs">
        Upload a document and click "Run Pipeline" to start the multi-agent
        analysis, or select a past run from the history panel below.
      </p>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// PipelinePage
// ─────────────────────────────────────────────────────────────────────────────

export function PipelinePage() {
  // ── UI / selection state ───────────────────────────────────────────────────
  const [file, setFile] = React.useState<File | null>(null);
  const [llmProfileId, setLlmProfileId] = React.useState<number | null>(null);
  const [activeRunId, setActiveRunId] = React.useState<string | null>(null);
  const [selectedHistoryRun, setSelectedHistoryRun] =
    React.useState<PipelineRunResponse | null>(null);
  const [showHistory, setShowHistory] = React.useState(false);

  // Ref used to scroll the results section into view when a history run is
  // selected or when the active run reaches a terminal state.
  const resultsRef = React.useRef<HTMLDivElement>(null);

  // ── Data / mutations ───────────────────────────────────────────────────────
  const startMutation = useStartPipeline();
  const cancelMutation = useCancelPipeline();

  // Fetch the active run so we always have the authoritative status after WS
  // events trigger a refetch.
  const { data: activeRun, refetch: refetchActiveRun } = usePipelineRun(
    activeRunId ?? undefined,
  );

  // ── WebSocket ──────────────────────────────────────────────────────────────
  const {
    status: wsStatus,
    events,
    agentStatuses,
    agentProgress,
    currentStage,
    isTerminal,
    logMessages,
  } = usePipelineWebSocket({
    runId: activeRunId ?? undefined,
    enabled: !!activeRunId,
    onEvent: (event: WSEvent) => {
      switch (event.event) {
        case "run.completed":
          // Pull the fresh run object so the ResultsViewer has final data
          refetchActiveRun();
          toast.success(
            "Pipeline completed",
            "Your pipeline run finished successfully.",
          );
          // Scroll to results once data arrives (slight delay for refetch)
          setTimeout(() => {
            resultsRef.current?.scrollIntoView({
              behavior: "smooth",
              block: "start",
            });
          }, 400);
          break;

        case "run.failed":
          refetchActiveRun();
          toast.error(
            "Pipeline failed",
            "Your pipeline run encountered an error.",
          );
          break;

        default:
          break;
      }
    },
  });

  // ── Derived state ──────────────────────────────────────────────────────────

  // Is the current active run still in a live (non-terminal) state?
  const isRunning =
    !!activeRun &&
    (activeRun.status === "running" || activeRun.status === "pending");

  // The run whose results we show in the right panel.
  // Priority: explicitly selected history run > active run (if terminal).
  const displayRun: PipelineRunResponse | null =
    selectedHistoryRun ??
    (activeRun && TERMINAL_STATUSES.includes(activeRun.status)
      ? activeRun
      : null);

  const showProgress = !!activeRunId;
  const showResults = displayRun !== null;

  // ── Handlers ───────────────────────────────────────────────────────────────

  const handleStartPipeline = async () => {
    if (!file) return;

    try {
      const run = await startMutation.mutateAsync({ file, llmProfileId });

      // Wire up the new run and clear any previously-viewed history selection
      setActiveRunId(run.id);
      setSelectedHistoryRun(null);

      toast.success("Pipeline started", `Processing "${file.name}"…`);
    } catch (err) {
      toast.error(
        "Failed to start pipeline",
        err instanceof Error ? err.message : "Please try again.",
      );
    }
  };

  const handleCancelPipeline = async () => {
    if (!activeRunId) return;
    try {
      await cancelMutation.mutateAsync(activeRunId);
      toast.warning("Pipeline cancelled", "The pipeline run has been stopped.");
    } catch {
      toast.error(
        "Cancel failed",
        "Could not cancel the pipeline run. Please try again.",
      );
    }
  };

  const handleSelectHistoryRun = (run: PipelineRunResponse) => {
    setSelectedHistoryRun(run);

    // Scroll the results panel into view (useful on mobile where the right
    // column is stacked below the left column / history panel).
    setTimeout(() => {
      resultsRef.current?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    }, 100);
  };

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col gap-6">
      {/* ── Page header ────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div
            className={cn(
              "shrink-0 w-9 h-9 rounded-xl",
              "bg-[#135bec]/10 border border-[#135bec]/20",
              "flex items-center justify-center",
            )}
            aria-hidden="true"
          >
            <Zap className="w-5 h-5 text-[#135bec]" />
          </div>

          <div>
            <h1 className="text-lg font-semibold text-white leading-snug">
              Pipeline
            </h1>
            <p className="text-xs text-[#92a4c9]">
              Upload a requirements document and run the multi-agent analysis
            </p>
          </div>
        </div>

        {/* Run History toggle */}
        <Button
          variant={showHistory ? "secondary" : "outline"}
          size="sm"
          leftIcon={<History className="w-4 h-4" aria-hidden="true" />}
          onClick={() => setShowHistory((prev) => !prev)}
          aria-expanded={showHistory}
          aria-controls="run-history-panel"
        >
          {showHistory ? "Hide History" : "Run History"}
        </Button>
      </div>

      {/* ── Two-column layout ─────────────────────────────────────────────── */}
      {/*   Left (2fr): controls   Right (3fr): progress + results            */}
      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)] gap-6 items-start">
        {/* ── LEFT: Controls ──────────────────────────────────────────────── */}
        <div className="flex flex-col gap-4">
          {/* Document upload */}
          <DocumentUpload file={file} onChange={setFile} />

          {/* LLM profile selector */}
          <LLMProfileSelector value={llmProfileId} onChange={setLlmProfileId} />

          {/* Action buttons */}
          <div className="flex items-center gap-3">
            <Button
              variant="primary"
              size="md"
              fullWidth
              loading={startMutation.isPending}
              disabled={!file || startMutation.isPending}
              leftIcon={
                !startMutation.isPending ? (
                  <PlayCircle className="w-4 h-4" aria-hidden="true" />
                ) : undefined
              }
              onClick={handleStartPipeline}
            >
              {startMutation.isPending ? "Starting…" : "Run Pipeline"}
            </Button>

            {/* Cancel button — visible only while a run is live */}
            {isRunning && (
              <Button
                variant="danger"
                size="md"
                loading={cancelMutation.isPending}
                leftIcon={
                  !cancelMutation.isPending ? (
                    <StopCircle className="w-4 h-4" aria-hidden="true" />
                  ) : undefined
                }
                onClick={handleCancelPipeline}
                title="Cancel the running pipeline"
                aria-label="Cancel pipeline"
              >
                Cancel
              </Button>
            )}
          </div>

          {/* Start-pipeline error feedback (non-toast fallback) */}
          {startMutation.isError && (
            <p
              role="alert"
              className="text-xs text-[#f87171] bg-[#ef4444]/5 border border-[#ef4444]/20 rounded-lg px-3 py-2 leading-relaxed"
            >
              {startMutation.error instanceof Error
                ? startMutation.error.message
                : "Failed to start the pipeline. Please try again."}
            </p>
          )}
        </div>

        {/* ── RIGHT: Progress + Results ────────────────────────────────────── */}
        <div className="flex flex-col gap-4">
          {/* Pipeline progress (always rendered when a run is active so the
              WS status / event stream is visible during execution) */}
          {showProgress && (
            <PipelineProgress
              run={activeRun ?? null}
              wsEvents={events}
              agentStatuses={agentStatuses}
              agentProgress={agentProgress}
              currentStage={currentStage}
              wsConnected={wsStatus === "connected"}
              logMessages={logMessages}
            />
          )}

          {/* Results viewer — shown once a terminal run is available */}
          {showResults && displayRun && (
            <div ref={resultsRef}>
              <ResultsViewer run={displayRun} />
            </div>
          )}

          {/* Placeholder when nothing is active or selected */}
          {!showProgress && !showResults && <RightPanelPlaceholder />}
        </div>
      </div>

      {/* ── Run History panel (collapsible) ───────────────────────────────── */}
      {showHistory && (
        <section id="run-history-panel" aria-label="Run history">
          <RunHistory
            onSelectRun={handleSelectHistoryRun}
            selectedRunId={selectedHistoryRun?.id ?? activeRunId}
          />
        </section>
      )}
    </div>
  );
}

export default PipelinePage;
