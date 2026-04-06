"use client";

import * as React from "react";
import Link from "next/link";
import {
  ArrowLeft,
  Play,
  History,
  Layers,
  ChevronDown,
  ChevronUp,
  Terminal,
  Wifi,
  WifiOff,
  Loader2,
  AlertCircle,
  CheckCircle2,
  XCircle,
  Clock,
  SkipForward,
  Circle,
  FileText,
  RefreshCw,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { usePipelineTemplate } from "@/hooks/usePipelineTemplates";
import { useStartDagPipeline, usePipelineRun } from "@/hooks/usePipeline";
import { usePipelineStore } from "@/store/pipelineStore";
import { DocumentUpload } from "@/components/pipeline/DocumentUpload";
import { LLMProfileSelector } from "@/components/pipeline/LLMProfileSelector";
import { PipelineRunView } from "@/components/pipeline/PipelineRunView";
import { PipelineControls } from "@/components/pipeline/PipelineControls";
import { Button } from "@/components/ui/Button";
import { toast } from "@/components/ui/Toast";
import type { PipelineNodeConfig, PipelineStatus } from "@/types";

// ─────────────────────────────────────────────────────────────────────────────
// Sub-components
// ─────────────────────────────────────────────────────────────────────────────

/** Coloured dot + label for a node execution status */
function NodeStatusBadge({
  status,
  isCurrentNode = false,
}: {
  status: string;
  isCurrentNode?: boolean;
}) {
  switch (status) {
    case "running":
      return (
        <span
          className={cn(
            "inline-flex items-center gap-1.5 text-xs font-medium text-blue-400",
            isCurrentNode && "font-semibold",
          )}
        >
          <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" />
          running
        </span>
      );
    case "completed":
      return (
        <span className="inline-flex items-center gap-1.5 text-xs font-medium text-green-400">
          <CheckCircle2 className="w-3.5 h-3.5" />
          completed
        </span>
      );
    case "failed":
      return (
        <span className="inline-flex items-center gap-1.5 text-xs font-medium text-red-400">
          <XCircle className="w-3.5 h-3.5" />
          failed
        </span>
      );
    case "skipped":
      return (
        <span className="inline-flex items-center gap-1.5 text-xs font-medium text-zinc-400">
          <SkipForward className="w-3.5 h-3.5" />
          skipped
        </span>
      );
    default:
      return (
        <span className="inline-flex items-center gap-1.5 text-xs font-medium text-zinc-500">
          <Circle className="w-3 h-3" />
          idle
        </span>
      );
  }
}

/** WS connection status pill */
function WsStatusIndicator({
  status,
}: {
  status: "disconnected" | "connecting" | "connected" | "error";
}) {
  if (status === "connected") {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs text-green-400">
        <Wifi className="w-3.5 h-3.5" />
        Live
      </span>
    );
  }
  if (status === "connecting") {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs text-yellow-400">
        <Loader2 className="w-3.5 h-3.5 animate-spin" />
        Connecting…
      </span>
    );
  }
  if (status === "error") {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs text-red-400">
        <WifiOff className="w-3.5 h-3.5" />
        WS error
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-[#3d5070]">
      <WifiOff className="w-3.5 h-3.5" />
      Disconnected
    </span>
  );
}

/** Shown when no run is active yet */
function NoRunPlaceholder() {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-[#2b3b55] bg-[#18202F] py-16 px-8 text-center">
      <div className="flex items-center justify-center w-12 h-12 rounded-xl bg-[#1e2a3d] border border-[#2b3b55]">
        <Layers className="w-6 h-6 text-[#3d5070]" aria-hidden="true" />
      </div>
      <div>
        <p className="text-sm font-medium text-[#92a4c9]">No active run</p>
        <p className="mt-1 text-xs text-[#3d5070]">
          Configure options on the left and press &ldquo;Run Pipeline&rdquo; to
          start.
        </p>
      </div>
    </div>
  );
}

/** Node progress per execution layer */
function NodeProgressSection({
  executionLayers,
  nodeStatuses,
  currentNode,
  templateNodes,
}: {
  executionLayers: string[][];
  nodeStatuses: Record<string, string>;
  currentNode: string | null;
  templateNodes: PipelineNodeConfig[];
}) {
  // Build a label map for quick lookup
  const labelMap = React.useMemo(() => {
    const m: Record<string, string> = {};
    templateNodes.forEach((n) => {
      m[n.node_id] = n.label;
    });
    return m;
  }, [templateNodes]);

  if (executionLayers.length === 0) {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-[#2b3b55] bg-[#18202F] p-4 text-sm text-[#92a4c9]">
        <Loader2 className="w-4 h-4 animate-spin text-blue-400" />
        Preparing execution plan…
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-[#2b3b55] bg-[#18202F] overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-[#2b3b55]">
        <Layers className="w-4 h-4 text-[#92a4c9]" aria-hidden="true" />
        <h3 className="text-sm font-semibold text-white">Node Progress</h3>
        <span className="ml-auto text-xs text-[#3d5070]">
          {executionLayers.length}{" "}
          {executionLayers.length === 1 ? "layer" : "layers"}
        </span>
      </div>
      <div className="divide-y divide-[#2b3b55]">
        {executionLayers.map((layer, layerIdx) => (
          <div key={layerIdx} className="px-4 py-3">
            <p className="mb-2 text-xs font-medium text-[#3d5070] uppercase tracking-wider">
              Layer {layerIdx + 1}
            </p>
            <div className="flex flex-col gap-1.5">
              {layer.map((nodeId) => {
                const status = nodeStatuses[nodeId] ?? "idle";
                const isActive = nodeId === currentNode;
                return (
                  <div
                    key={nodeId}
                    className={cn(
                      "flex items-center justify-between rounded-lg px-3 py-2",
                      "border transition-colors duration-150",
                      isActive
                        ? "border-blue-500/30 bg-blue-500/5"
                        : "border-[#2b3b55] bg-[#1e2a3d]",
                    )}
                  >
                    <span
                      className={cn(
                        "text-xs font-mono truncate max-w-[180px]",
                        isActive ? "text-blue-300" : "text-[#92a4c9]",
                      )}
                      title={nodeId}
                    >
                      {labelMap[nodeId] ?? nodeId}
                    </span>
                    <NodeStatusBadge status={status} isCurrentNode={isActive} />
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/** Compact summary card shown after terminal run */
function TerminalSummaryCard({
  status,
  runId,
  nodeStatuses,
  templateId,
  runData,
}: {
  status: PipelineStatus;
  runId: string;
  nodeStatuses: Record<string, string>;
  templateId: string;
  runData?: { duration_seconds?: number | null; error_message?: string | null };
}) {
  const completed = Object.values(nodeStatuses).filter(
    (s) => s === "completed",
  ).length;
  const failed = Object.values(nodeStatuses).filter(
    (s) => s === "failed",
  ).length;
  const total = Object.keys(nodeStatuses).length;

  const isSuccess = status === "completed";
  const isFailed = status === "failed";
  const isCancelled = status === "cancelled";

  return (
    <div
      className={cn(
        "rounded-xl border p-5",
        isSuccess
          ? "border-green-500/30 bg-green-500/5"
          : isFailed
            ? "border-red-500/30 bg-red-500/5"
            : "border-[#2b3b55] bg-[#18202F]",
      )}
    >
      <div className="flex items-start gap-3">
        <div
          className={cn(
            "flex items-center justify-center w-10 h-10 rounded-lg shrink-0",
            isSuccess
              ? "bg-green-500/10"
              : isFailed
                ? "bg-red-500/10"
                : "bg-[#1e2a3d]",
          )}
        >
          {isSuccess ? (
            <CheckCircle2
              className="w-5 h-5 text-green-400"
              aria-hidden="true"
            />
          ) : isFailed ? (
            <XCircle className="w-5 h-5 text-red-400" aria-hidden="true" />
          ) : (
            <AlertCircle
              className="w-5 h-5 text-zinc-400"
              aria-hidden="true"
            />
          )}
        </div>
        <div className="flex-1 min-w-0">
          <h3
            className={cn(
              "text-sm font-semibold",
              isSuccess
                ? "text-green-400"
                : isFailed
                  ? "text-red-400"
                  : "text-[#92a4c9]",
            )}
          >
            {isSuccess
              ? "Pipeline completed successfully"
              : isFailed
                ? "Pipeline failed"
                : isCancelled
                  ? "Pipeline cancelled"
                  : `Run ${status}`}
          </h3>
          <p className="mt-0.5 text-xs text-[#3d5070] font-mono">
            Run ID: {runId.slice(0, 8)}…
          </p>

          {/* Stats row */}
          {total > 0 && (
            <div className="mt-3 flex flex-wrap gap-3">
              <span className="inline-flex items-center gap-1 text-xs text-green-400">
                <CheckCircle2 className="w-3.5 h-3.5" />
                {completed} completed
              </span>
              {failed > 0 && (
                <span className="inline-flex items-center gap-1 text-xs text-red-400">
                  <XCircle className="w-3.5 h-3.5" />
                  {failed} failed
                </span>
              )}
              {runData?.duration_seconds != null && (
                <span className="inline-flex items-center gap-1 text-xs text-[#92a4c9]">
                  <Clock className="w-3.5 h-3.5" />
                  {runData.duration_seconds.toFixed(1)}s
                </span>
              )}
            </div>
          )}

          {/* Error message */}
          {runData?.error_message && (
            <p className="mt-2 text-xs text-red-400 bg-red-500/10 rounded-lg px-3 py-2 font-mono leading-relaxed">
              {runData.error_message}
            </p>
          )}

          {/* Link to history */}
          <div className="mt-4">
            <Link
              href={`/pipelines/${templateId}/runs`}
              className="inline-flex items-center gap-1.5 text-xs text-[#92a4c9] hover:text-white transition-colors"
            >
              <History className="w-3.5 h-3.5" />
              View full run history
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}

/** Collapsible log messages panel */
function LogsPanel({
  logs,
  open,
  onToggle,
  logsEndRef,
}: {
  logs: string[];
  open: boolean;
  onToggle: () => void;
  logsEndRef: React.RefObject<HTMLDivElement | null>;
}) {
  const lastLogs = logs.slice(-20);

  return (
    <div className="rounded-xl border border-[#2b3b55] bg-[#18202F] overflow-hidden">
      <button
        type="button"
        onClick={onToggle}
        className="w-full flex items-center gap-2 px-4 py-3 text-left hover:bg-[#1e2a3d] transition-colors"
        aria-expanded={open}
      >
        <Terminal className="w-4 h-4 text-[#92a4c9]" aria-hidden="true" />
        <span className="text-sm font-semibold text-white">Log Messages</span>
        {logs.length > 0 && (
          <span className="ml-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-[#2b3b55] text-[#92a4c9]">
            {logs.length}
          </span>
        )}
        <span className="ml-auto text-[#3d5070]">
          {open ? (
            <ChevronUp className="w-4 h-4" />
          ) : (
            <ChevronDown className="w-4 h-4" />
          )}
        </span>
      </button>

      {open && (
        <div className="border-t border-[#2b3b55]">
          {lastLogs.length === 0 ? (
            <p className="px-4 py-3 text-xs text-[#3d5070] italic">
              No log messages yet.
            </p>
          ) : (
            <div className="max-h-64 overflow-y-auto font-mono text-[11px] leading-relaxed">
              {lastLogs.map((msg, i) => (
                <div
                  key={i}
                  className={cn(
                    "px-4 py-1 border-b border-[#2b3b55]/50 last:border-0",
                    "text-[#92a4c9] hover:bg-[#1e2a3d] transition-colors",
                  )}
                >
                  <span className="text-[#3d5070] mr-2 select-none">
                    {String(lastLogs.length - lastLogs.length + i + 1).padStart(
                      2,
                      "0",
                    )}
                  </span>
                  {msg}
                </div>
              ))}
              <div ref={logsEndRef} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/** Template loading skeleton */
function LoadingTemplate() {
  return (
    <div className="flex flex-col gap-6 animate-pulse">
      <div className="flex items-center gap-3">
        <div className="h-8 w-8 rounded-lg bg-[#2b3b55]" />
        <div className="flex flex-col gap-2">
          <div className="h-5 w-48 rounded bg-[#2b3b55]" />
          <div className="h-3 w-72 rounded bg-[#2b3b55]" />
        </div>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-[380px,1fr] gap-6">
        <div className="flex flex-col gap-4">
          <div className="h-40 rounded-xl bg-[#18202F] border border-[#2b3b55]" />
          <div className="h-24 rounded-xl bg-[#18202F] border border-[#2b3b55]" />
          <div className="h-10 rounded-xl bg-[#2b3b55]" />
        </div>
        <div className="h-80 rounded-xl bg-[#18202F] border border-[#2b3b55]" />
      </div>
    </div>
  );
}

/** Template error state */
function ErrorTemplate({ error }: { error: Error | null }) {
  return (
    <div className="flex flex-col items-center justify-center gap-4 py-20">
      <div className="flex items-center justify-center w-12 h-12 rounded-xl bg-red-500/10 border border-red-500/25">
        <AlertCircle className="w-6 h-6 text-red-400" aria-hidden="true" />
      </div>
      <div className="text-center">
        <p className="text-sm font-semibold text-white">
          Failed to load pipeline template
        </p>
        <p className="mt-1 text-xs text-[#92a4c9]">
          {error?.message ?? "An unexpected error occurred."}
        </p>
      </div>
      <Button
        variant="secondary"
        size="sm"
        leftIcon={<RefreshCw className="w-3.5 h-3.5" />}
        onClick={() => window.location.reload()}
      >
        Reload page
      </Button>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Main component
// ─────────────────────────────────────────────────────────────────────────────

export interface PipelineRunPageProps {
  templateId: string;
}

export function PipelineRunPage({ templateId }: PipelineRunPageProps) {
  // ── Local state ────────────────────────────────────────────────────────────
  const [file, setFile] = React.useState<File | null>(null);
  const [llmProfileId, setLlmProfileId] = React.useState<number | null>(null);
  const [logsOpen, setLogsOpen] = React.useState(false);
  const logsEndRef = React.useRef<HTMLDivElement | null>(null);

  // ── Template ───────────────────────────────────────────────────────────────
  const {
    data: template,
    isLoading: templateLoading,
    error: templateError,
  } = usePipelineTemplate(templateId);

  // ── Pipeline store ─────────────────────────────────────────────────────────
  const activeRunId = usePipelineStore((s) => s.activeRunId);
  const activeRunStatus = usePipelineStore((s) => s.activeRunStatus);
  const nodeStatuses = usePipelineStore((s) => s.nodeStatuses);
  const currentNode = usePipelineStore((s) => s.currentNode);
  const executionLayers = usePipelineStore((s) => s.executionLayers);
  const isTerminal = usePipelineStore((s) => s.isTerminal);
  const wsStatus = usePipelineStore((s) => s.wsStatus);
  const logMessages = usePipelineStore((s) => s.logMessages);
  const activeTemplateId = usePipelineStore((s) => s.activeTemplateId);
  const startSession = usePipelineStore((s) => s.startSession);
  const syncRunStatus = usePipelineStore((s) => s.syncRunStatus);
  const connectWebSocket = usePipelineStore((s) => s.connectWebSocket);

  // ── Mutations ──────────────────────────────────────────────────────────────
  const startMutation = useStartDagPipeline();

  // ── Live run data (HTTP polling fallback) ──────────────────────────────────
  const runBelongsHere =
    !!activeRunId && activeTemplateId === templateId;

  const { data: runData } = usePipelineRun(
    runBelongsHere ? activeRunId : undefined,
  );

  // Sync status from polling when WS may have missed events
  React.useEffect(() => {
    if (runData?.status) {
      syncRunStatus(runData.status);
    }
  }, [runData?.status, syncRunStatus]);

  // ── WS rehydration: reconnect if page is reloaded mid-run ─────────────────
  React.useEffect(() => {
    if (
      activeRunId &&
      !isTerminal &&
      activeTemplateId === templateId &&
      wsStatus === "disconnected"
    ) {
      connectWebSocket(activeRunId);
    }
    // Only run once on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Auto-scroll logs when panel is open ────────────────────────────────────
  React.useEffect(() => {
    if (logsOpen && logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [logMessages, logsOpen]);

  // ── Derived flags ──────────────────────────────────────────────────────────
  const hasActiveRun = runBelongsHere;
  const isActivelyRunning =
    hasActiveRun &&
    (activeRunStatus === "running" ||
      activeRunStatus === "paused" ||
      activeRunStatus === "pending");
  const isTerminalRun = hasActiveRun && isTerminal;
  const canStartRun = !startMutation.isPending && !isActivelyRunning;

  // ── Handlers ───────────────────────────────────────────────────────────────
  const handleRun = async () => {
    if (!canStartRun) return;
    try {
      const result = await startMutation.mutateAsync({
        templateId,
        file: file ?? undefined,
        llmProfileId: llmProfileId ?? undefined,
      });
      const runId = result.id ?? result.run_id;
      if (!runId) {
        throw new Error("No run ID returned from server.");
      }
      startSession(runId, templateId);
      toast.success(
        "Pipeline started",
        `Run ${runId.slice(0, 8)}… is now queued.`,
      );
    } catch (err) {
      toast.error(
        "Failed to start pipeline",
        err instanceof Error ? err.message : "Unknown error.",
      );
    }
  };

  // ── Early return states ────────────────────────────────────────────────────
  if (templateLoading) return <LoadingTemplate />;
  if (templateError || !template) {
    return <ErrorTemplate error={templateError ?? null} />;
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Render
  // ─────────────────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col gap-6">
      {/* ── Page header ──────────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          {/* Back to builder */}
          <Link
            href={`/pipelines/${templateId}`}
            className={cn(
              "inline-flex items-center justify-center w-8 h-8 rounded-lg shrink-0 mt-0.5",
              "border border-[#2b3b55] bg-[#18202F] text-[#92a4c9]",
              "hover:border-[#3d5070] hover:text-white transition-colors duration-150",
            )}
            title="Back to builder"
          >
            <ArrowLeft className="w-4 h-4" aria-hidden="true" />
          </Link>

          <div>
            <h1 className="text-lg font-bold text-white leading-tight">
              {template.name}
            </h1>
            {template.description && (
              <p className="mt-0.5 text-sm text-[#92a4c9] line-clamp-2">
                {template.description}
              </p>
            )}
            <div className="mt-1.5 flex flex-wrap items-center gap-3">
              {/* Node count */}
              <span className="inline-flex items-center gap-1 text-xs text-[#3d5070]">
                <Layers className="w-3.5 h-3.5" />
                {template.node_count}{" "}
                {template.node_count === 1 ? "node" : "nodes"}
              </span>

              {/* WS status — only when run is active */}
              {hasActiveRun && <WsStatusIndicator status={wsStatus} />}

              {/* Run ID badge */}
              {hasActiveRun && activeRunId && (
                <span className="inline-flex items-center gap-1 text-xs text-[#3d5070] font-mono">
                  <FileText className="w-3.5 h-3.5" />
                  {activeRunId.slice(0, 8)}…
                </span>
              )}
            </div>
          </div>
        </div>

        {/* History link */}
        <Link href={`/pipelines/${templateId}/runs`} className="shrink-0">
          <Button
            variant="ghost"
            size="sm"
            leftIcon={<History className="w-3.5 h-3.5" aria-hidden="true" />}
          >
            Run History
          </Button>
        </Link>
      </div>

      {/* ── Main two-column grid ──────────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-[380px,1fr] gap-6 items-start">
        {/* ── Left column: controls ──────────────────────────────────────── */}
        <div className="flex flex-col gap-4">
          {/* Document upload */}
          <section className="rounded-xl border border-[#2b3b55] bg-[#18202F] p-4">
            <h2 className="mb-3 text-sm font-semibold text-white">
              Document{" "}
              <span className="font-normal text-[#3d5070]">(optional)</span>
            </h2>
            <DocumentUpload
              file={file}
              onChange={setFile}
              disabled={isActivelyRunning || startMutation.isPending}
            />
          </section>

          {/* LLM profile */}
          <section className="rounded-xl border border-[#2b3b55] bg-[#18202F] p-4">
            <LLMProfileSelector
              value={llmProfileId}
              onChange={setLlmProfileId}
              disabled={isActivelyRunning || startMutation.isPending}
            />
          </section>

          {/* Run button */}
          <Button
            variant="primary"
            size="lg"
            fullWidth
            loading={startMutation.isPending}
            disabled={!canStartRun}
            onClick={handleRun}
            leftIcon={
              !startMutation.isPending ? (
                <Play className="w-4 h-4" aria-hidden="true" />
              ) : undefined
            }
          >
            {startMutation.isPending
              ? "Starting…"
              : isActivelyRunning
                ? "Pipeline Running…"
                : "Run Pipeline"}
          </Button>

          {/* Pause / Resume / Cancel controls */}
          {hasActiveRun &&
            activeRunStatus &&
            !isTerminal &&
            activeRunId && (
              <div className="flex justify-center">
                <PipelineControls
                  runId={activeRunId}
                  status={activeRunStatus}
                  onCancelled={() => {
                    /* store updates via WS */
                  }}
                />
              </div>
            )}

          {/* Status summary pill */}
          {hasActiveRun && activeRunStatus && (
            <div
              className={cn(
                "rounded-lg border px-3 py-2 text-xs font-medium text-center",
                activeRunStatus === "running"
                  ? "border-blue-500/30 bg-blue-500/5 text-blue-400"
                  : activeRunStatus === "paused"
                    ? "border-yellow-500/30 bg-yellow-500/5 text-yellow-400"
                    : activeRunStatus === "completed"
                      ? "border-green-500/30 bg-green-500/5 text-green-400"
                      : activeRunStatus === "failed"
                        ? "border-red-500/30 bg-red-500/5 text-red-400"
                        : "border-[#2b3b55] bg-[#1e2a3d] text-[#92a4c9]",
              )}
            >
              Status:{" "}
              <span className="capitalize">{activeRunStatus}</span>
            </div>
          )}
        </div>

        {/* ── Right column: DAG + progress ──────────────────────────────── */}
        <div className="flex flex-col gap-4">
          {/* No run yet */}
          {!hasActiveRun && <NoRunPlaceholder />}

          {/* Active run: DAG visualization */}
          {isActivelyRunning && template.nodes.length > 0 && (
            <div
              className="rounded-xl border border-[#2b3b55] overflow-hidden"
              style={{ height: 420 }}
            >
              <PipelineRunView
                templateNodes={template.nodes}
                templateEdges={template.edges}
              />
            </div>
          )}

          {/* Active run: node progress layers */}
          {isActivelyRunning && (
            <NodeProgressSection
              executionLayers={executionLayers}
              nodeStatuses={nodeStatuses}
              currentNode={currentNode}
              templateNodes={template.nodes}
            />
          )}

          {/* Terminal run: results summary */}
          {isTerminalRun && activeRunStatus && activeRunId && (
            <>
              {/* Still show DAG in terminal state */}
              {template.nodes.length > 0 && (
                <div
                  className="rounded-xl border border-[#2b3b55] overflow-hidden"
                  style={{ height: 380 }}
                >
                  <PipelineRunView
                    templateNodes={template.nodes}
                    templateEdges={template.edges}
                  />
                </div>
              )}
              <TerminalSummaryCard
                status={activeRunStatus}
                runId={activeRunId}
                nodeStatuses={nodeStatuses}
                templateId={templateId}
                runData={runData ?? undefined}
              />
            </>
          )}
        </div>
      </div>

      {/* ── Log messages (collapsible) ────────────────────────────────────── */}
      {hasActiveRun && (
        <LogsPanel
          logs={logMessages}
          open={logsOpen}
          onToggle={() => setLogsOpen((v) => !v)}
          logsEndRef={logsEndRef}
        />
      )}
    </div>
  );
}

export default PipelineRunPage;
