"use client";

import * as React from "react";
import { Zap, History, PlayCircle, Hand } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { toast } from "@/components/ui/Toast";
import {
  useStartPipeline,
  usePipelineRun,
  usePausePipeline,
} from "@/hooks/usePipeline";
import { usePipelineStore } from "@/store/pipelineStore";
import { cn } from "@/lib/utils";
import type { PipelineRunResponse, PipelineStatus } from "@/types";

import { DocumentUpload } from "./DocumentUpload";
import { LLMProfileSelector } from "./LLMProfileSelector";
import { PipelineControls } from "./PipelineControls";
import { PipelineProgress } from "./PipelineProgress";
import { ResultsViewer } from "./ResultsViewer";
import { RunHistory } from "./RunHistory";
import { StageResultsPanel } from "./StageResultsPanel";

// ─────────────────────────────────────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────────────────────────────────────

const TERMINAL_STATUSES: PipelineStatus[] = [
  "completed",
  "failed",
  "cancelled",
];

// ─────────────────────────────────────────────────────────────────────────────
// StageModeToggle
// ─────────────────────────────────────────────────────────────────────────────

type StageMode = "auto" | "manual";

interface StageModeToggleProps {
  value: StageMode;
  onChange: (mode: StageMode) => void;
  disabled?: boolean;
}

function StageModeToggle({ value, onChange, disabled }: StageModeToggleProps) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-xs font-medium text-[#92a4c9]">Stage Mode</span>
      <div
        className={cn(
          "inline-flex rounded-lg border border-[#2b3b55] bg-[#111827] p-0.5 gap-0.5",
          disabled && "opacity-50 pointer-events-none",
        )}
        role="radiogroup"
        aria-label="Stage execution mode"
      >
        {/* Auto button */}
        <button
          type="button"
          role="radio"
          aria-checked={value === "auto"}
          onClick={() => onChange("auto")}
          disabled={disabled}
          className={cn(
            "flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-md",
            "text-xs font-medium transition-all duration-150",
            value === "auto"
              ? "bg-[#135bec] text-white shadow-sm"
              : "text-[#92a4c9] hover:text-white hover:bg-[#1e2a3d]",
          )}
          title="Run all stages automatically without stopping"
        >
          <Zap className="w-3 h-3" aria-hidden="true" />
          Auto
        </button>

        {/* Manual button */}
        <button
          type="button"
          role="radio"
          aria-checked={value === "manual"}
          onClick={() => onChange("manual")}
          disabled={disabled}
          className={cn(
            "flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-md",
            "text-xs font-medium transition-all duration-150",
            value === "manual"
              ? "bg-[#1e2a3d] text-white border border-[#2b3b55] shadow-sm"
              : "text-[#92a4c9] hover:text-white hover:bg-[#1e2a3d]",
          )}
          title="Pause between stages and advance manually"
        >
          <Hand className="w-3 h-3" aria-hidden="true" />
          Manual
        </button>
      </div>

      {/* Helper text */}
      <p className="text-[11px] text-[#3d5070] leading-relaxed">
        {value === "auto"
          ? "All stages run automatically end-to-end."
          : "Pipeline pauses after each stage — you advance manually."}
      </p>
    </div>
  );
}

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
  // ── Local UI state ─────────────────────────────────────────────────────────
  const [file, setFile] = React.useState<File | null>(null);
  const [llmProfileId, setLlmProfileId] = React.useState<number | null>(null);
  const [selectedHistoryRun, setSelectedHistoryRun] =
    React.useState<PipelineRunResponse | null>(null);
  const [showHistory, setShowHistory] = React.useState(false);
  const [stageMode, setStageMode] = React.useState<StageMode>("auto");

  const resultsRef = React.useRef<HTMLDivElement>(null);

  // Tracks the number of events already processed for auto-pause logic
  const lastEventsLenRef = React.useRef(0);

  // ── Global pipeline store ──────────────────────────────────────────────────
  const {
    activeRunId,
    activeRunStatus,
    agentStatuses,
    agentProgress,
    currentStage,
    completedStages,
    stageSummaries,
    logMessages,
    stageLogMessages,
    events,
    isTerminal,
    wsStatus,
    startSession,
    clearSession,
    connectWebSocket,
    syncRunStatus,
  } = usePipelineStore();

  // ── Rehydration: reconnect WS if returning to page with an active session ──
  React.useEffect(() => {
    if (activeRunId && !isTerminal && wsStatus === "disconnected") {
      connectWebSocket(activeRunId);
    }
  }, [activeRunId, isTerminal, wsStatus, connectWebSocket]);

  // ── Data / mutations ───────────────────────────────────────────────────────
  const startMutation = useStartPipeline();
  const pauseMutation = usePausePipeline();

  const { data: activeRun, refetch: refetchActiveRun } = usePipelineRun(
    activeRunId ?? undefined,
  );

  // Poll for run status while running or paused (as a fallback to WS)
  React.useEffect(() => {
    if (activeRunStatus === "running" || activeRunStatus === "paused") {
      const id = setInterval(() => {
        refetchActiveRun();
      }, 5000);
      return () => clearInterval(id);
    }
  }, [activeRunStatus, refetchActiveRun]);

  // Sync store status from polled run data; auto-scroll to results
  React.useEffect(() => {
    if (!activeRun) return;
    const isNowTerminal = TERMINAL_STATUSES.includes(activeRun.status);
    if (isNowTerminal && !isTerminal) {
      syncRunStatus(activeRun.status, undefined);
      setTimeout(() => {
        resultsRef.current?.scrollIntoView({
          behavior: "smooth",
          block: "start",
        });
      }, 400);
    }
  }, [activeRun, isTerminal, syncRunStatus]);

  // ── Auto-pause logic (manual mode) ────────────────────────────────────────
  // When manual mode is active, automatically request a pause whenever a new
  // stage.completed event arrives (so the pipeline halts before the next stage).
  React.useEffect(() => {
    // Keep the ref in sync even when mode is "auto" so we don't re-process
    // old events if the user switches to manual mid-run.
    if (stageMode !== "manual") {
      lastEventsLenRef.current = events.length;
      return;
    }

    if (events.length <= lastEventsLenRef.current) return;

    const newEvents = events.slice(lastEventsLenRef.current);
    lastEventsLenRef.current = events.length;

    const hasStageCompleted = newEvents.some(
      (e) => e.event === "stage.completed",
    );

    if (
      hasStageCompleted &&
      activeRunId &&
      activeRunStatus === "running" &&
      !pauseMutation.isPending
    ) {
      pauseMutation.mutateAsync(activeRunId).catch(() => {
        // Silently ignore — the stage may have been the last one and the run
        // might have already transitioned to "completed" before we could pause.
      });
    }
  }, [events, stageMode, activeRunId, activeRunStatus, pauseMutation]);

  // ── Derived state ──────────────────────────────────────────────────────────
  const effectiveStatus = activeRun?.status ?? activeRunStatus;

  const isRunning =
    effectiveStatus === "running" || effectiveStatus === "pending";

  const isPaused = effectiveStatus === "paused";

  /** Show PipelineControls whenever the run is running or paused */
  const showControls = (isRunning || isPaused) && !!activeRunId;

  const isActiveRunTerminal =
    !!effectiveStatus &&
    TERMINAL_STATUSES.includes(effectiveStatus as PipelineStatus);

  // The run to display in ResultsViewer
  const displayRun: PipelineRunResponse | null =
    selectedHistoryRun ?? (activeRun && isActiveRunTerminal ? activeRun : null);

  const showProgress = !!activeRunId && !isActiveRunTerminal;
  const showStageResults =
    !!activeRunId && completedStages.length > 0 && !isActiveRunTerminal;
  const showResults = displayRun !== null;

  // Whether the pipeline is actively in-progress (disable mode toggle)
  const pipelineActive = isRunning || isPaused;

  // ── Handlers ───────────────────────────────────────────────────────────────

  /** Called by PipelineControls after a successful cancel. */
  const handleCancelled = () => {
    clearSession();
  };

  const handleStartPipeline = async () => {
    if (!file) return;

    try {
      const run = await startMutation.mutateAsync({ file, llmProfileId });

      // Reset event counter so auto-pause logic starts fresh
      lastEventsLenRef.current = 0;

      // Start global session (resets state + connects WS)
      startSession(run.id);
      setSelectedHistoryRun(null);

      toast.success("Pipeline started", `Processing "${file.name}"…`);
    } catch (err) {
      toast.error(
        "Failed to start pipeline",
        err instanceof Error ? err.message : "Please try again.",
      );
    }
  };

  const handleSelectHistoryRun = (run: PipelineRunResponse) => {
    setSelectedHistoryRun(run);
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
      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)] gap-6 items-start">
        {/* ── LEFT: Controls ──────────────────────────────────────────────── */}
        <div className="flex flex-col gap-4">
          <DocumentUpload file={file} onChange={setFile} />
          <LLMProfileSelector value={llmProfileId} onChange={setLlmProfileId} />

          {/* Stage mode toggle */}
          <StageModeToggle
            value={stageMode}
            onChange={setStageMode}
            disabled={pipelineActive}
          />

          {/* Run button */}
          <Button
            variant="primary"
            size="md"
            fullWidth
            loading={startMutation.isPending}
            disabled={!file || startMutation.isPending || isRunning || isPaused}
            leftIcon={
              !startMutation.isPending ? (
                <PlayCircle className="w-4 h-4" aria-hidden="true" />
              ) : undefined
            }
            onClick={handleStartPipeline}
          >
            {startMutation.isPending ? "Starting…" : "Run Pipeline"}
          </Button>

          {/* Pipeline controls (Pause / Resume / Cancel) */}
          {showControls && activeRunId && effectiveStatus && (
            <PipelineControls
              runId={activeRunId}
              status={effectiveStatus as PipelineStatus}
              stageMode={stageMode}
              onCancelled={handleCancelled}
            />
          )}

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

        {/* ── RIGHT: Progress + Per-Stage Results + Final Results ──────────── */}
        <div className="flex flex-col gap-4">
          {/* Live progress panel (running or paused) */}
          {showProgress && (
            <PipelineProgress
              run={activeRun ?? null}
              wsEvents={events}
              agentStatuses={agentStatuses}
              agentProgress={agentProgress}
              currentStage={currentStage}
              completedStages={completedStages}
              wsConnected={wsStatus === "connected"}
              logMessages={logMessages}
              stageLogMessages={stageLogMessages}
            />
          )}

          {/* Per-stage progressive results */}
          {showStageResults && activeRunId && (
            <StageResultsPanel
              runId={activeRunId}
              completedStages={completedStages}
              stageSummaries={stageSummaries}
              currentStage={currentStage}
            />
          )}

          {/* Final results viewer */}
          {showResults && displayRun && (
            <div ref={resultsRef}>
              <ResultsViewer run={displayRun} />
            </div>
          )}

          {/* Placeholder */}
          {!showProgress && !showStageResults && !showResults && (
            <RightPanelPlaceholder />
          )}
        </div>
      </div>

      {/* ── Run History panel (collapsible) ───────────────────────────────── */}
      {showHistory && (
        <section id="run-history-panel" aria-label="Run history">
          <RunHistory
            onSelectRun={handleSelectHistoryRun}
            selectedRunId={selectedHistoryRun?.id ?? activeRunId ?? undefined}
          />
        </section>
      )}
    </div>
  );
}

export default PipelinePage;
