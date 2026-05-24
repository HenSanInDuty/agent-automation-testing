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
  WifiOff,
  Loader2,
  AlertCircle,
  CheckCircle2,
  XCircle,
  Clock,
  FileText,
  RefreshCw,
  Sparkles,
  Hash,
  GitBranch,
} from "lucide-react";

import { cn } from "../../lib/utils";
import { usePipelineTemplate } from "../../hooks/usePipelineTemplates";
import { useStartDagPipeline, usePipelineRun } from "../../hooks/usePipeline";
import { usePipelineStore } from "../../store/pipelineStore";
import { DocumentUpload } from "../../components/pipeline/DocumentUpload";
import { LLMProfileSelector } from "../../components/pipeline/LLMProfileSelector";
import { PipelineControls } from "../../components/pipeline/PipelineControls";
import { Button } from "../../components/ui/Button";
import { toast } from "../../components/ui/Toast";
import type { PipelineStatus } from "../../types";

// ─────────────────────────────────────────────────────────────────────────────
// Design tokens
// ─────────────────────────────────────────────────────────────────────────────

const card =
  "rounded-2xl border border-[#22304a] bg-[#141c2c]/80 backdrop-blur-sm shadow-[0_1px_0_0_rgba(255,255,255,0.02)_inset]";
const cardHeader = "flex items-center gap-2 px-5 py-3.5 border-b border-[#22304a]";
const cardTitle = "text-sm font-semibold text-white tracking-tight";
const subtle = "text-xs text-[#7a8baa]";
const mutedText = "text-[#92a4c9]";

// ─────────────────────────────────────────────────────────────────────────────
// Section header — reusable card section heading
// ─────────────────────────────────────────────────────────────────────────────

function SectionHeader({
  icon,
  title,
  hint,
  trailing,
}: {
  icon: React.ReactNode;
  title: string;
  hint?: string;
  trailing?: React.ReactNode;
}) {
  return (
    <div className={cardHeader}>
      <span className="flex items-center justify-center w-7 h-7 rounded-lg bg-[#1e2a3d] border border-[#22304a] text-[#92a4c9]">
        {icon}
      </span>
      <div className="flex flex-col leading-tight">
        <span className={cardTitle}>{title}</span>
        {hint && <span className="text-[11px] text-[#5e7196]">{hint}</span>}
      </div>
      {trailing && <span className="ml-auto">{trailing}</span>}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Sub-components
// ─────────────────────────────────────────────────────────────────────────────

/** WS connection status pill */
function WsStatusIndicator({
  status,
}: {
  status: "disconnected" | "connecting" | "connected" | "error";
}) {
  const base =
    "inline-flex items-center gap-1.5 px-2 py-1 rounded-full text-[11px] font-medium border";
  if (status === "connected") {
    return (
      <span className={cn(base, "bg-emerald-500/10 text-emerald-300 border-emerald-500/25")}>
        <span className="relative flex w-1.5 h-1.5">
          <span className="absolute inline-flex w-full h-full rounded-full bg-emerald-400 opacity-60 animate-ping" />
          <span className="relative inline-flex w-1.5 h-1.5 rounded-full bg-emerald-400" />
        </span>
        Live
      </span>
    );
  }
  if (status === "connecting") {
    return (
      <span className={cn(base, "bg-yellow-500/10 text-yellow-300 border-yellow-500/25")}>
        <Loader2 className="w-3 h-3 animate-spin" />
        Connecting
      </span>
    );
  }
  if (status === "error") {
    return (
      <span className={cn(base, "bg-red-500/10 text-red-300 border-red-500/25")}>
        <WifiOff className="w-3 h-3" />
        WS error
      </span>
    );
  }
  return (
    <span className={cn(base, "bg-[#1e2a3d] text-[#7a8baa] border-[#22304a]")}>
      <WifiOff className="w-3 h-3" />
      Offline
    </span>
  );
}

/** Shown when no run is active yet */
function NoRunPlaceholder() {
  return (
    <div
      className={cn(
        card,
        "relative overflow-hidden",
        "flex flex-col items-center justify-center text-center py-20 px-8",
      )}
    >
      {/* Decorative backdrop */}
      <div
        aria-hidden="true"
        className="absolute inset-0 opacity-[0.18] pointer-events-none"
        style={{
          backgroundImage:
            "radial-gradient(circle at 50% 0%, #135bec 0%, transparent 60%)",
        }}
      />
      <div className="relative flex flex-col items-center gap-4">
        <div className="relative">
          <div className="absolute inset-0 rounded-2xl bg-[#135bec]/20 blur-xl" />
          <div className="relative flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-[#1e2a3d] to-[#141c2c] border border-[#2b3b55]">
            <Sparkles className="w-7 h-7 text-[#5b9eff]" aria-hidden="true" />
          </div>
        </div>
        <div className="max-w-sm">
          <p className="text-base font-semibold text-white">Ready when you are</p>
          <p className={cn("mt-1.5 text-sm", mutedText)}>
            Configure your run on the left — upload a document, pick an LLM
            profile, then hit{" "}
            <span className="font-medium text-white">Run Pipeline</span>.
          </p>
        </div>
      </div>
    </div>
  );
}

/** Friendly waiting card shown to end-users while the pipeline runs */
const LOADING_MESSAGES = [
  "Đang xử lý tài liệu của bạn…",
  "Hệ thống đang phân tích nội dung, vui lòng chờ trong giây lát…",
  "Quá trình này có thể mất một vài phút — cảm ơn bạn đã kiên nhẫn.",
  "Đang sinh test cases, gần xong rồi…",
  "Hoàn tất các bước cuối cùng…",
];

function RunInProgressCard() {
  const [messageIdx, setMessageIdx] = React.useState(0);

  React.useEffect(() => {
    const interval = setInterval(() => {
      setMessageIdx((i) => (i + 1) % LOADING_MESSAGES.length);
    }, 3500);
    return () => clearInterval(interval);
  }, []);

  return (
    <div
      className={cn(
        card,
        "relative overflow-hidden",
        "flex flex-col items-center justify-center text-center py-16 px-8",
      )}
    >
      <div
        aria-hidden="true"
        className="absolute inset-0 opacity-[0.18] pointer-events-none"
        style={{
          backgroundImage:
            "radial-gradient(circle at 50% 0%, #135bec 0%, transparent 60%)",
        }}
      />
      <div className="relative flex flex-col items-center gap-5">
        <div className="relative">
          <div className="absolute inset-0 rounded-2xl bg-[#135bec]/25 blur-2xl animate-pulse" />
          <div className="relative flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-[#1e2a3d] to-[#141c2c] border border-[#2b3b55]">
            <Loader2 className="w-7 h-7 text-[#5b9eff] animate-spin" aria-hidden="true" />
          </div>
        </div>
        <div className="max-w-md min-h-[3rem]">
          <p className="text-base font-semibold text-white">Pipeline đang chạy</p>
          <p
            key={messageIdx}
            className={cn(
              "mt-2 text-sm transition-opacity duration-500",
              mutedText,
            )}
          >
            {LOADING_MESSAGES[messageIdx]}
          </p>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-blue-400 animate-bounce [animation-delay:-0.3s]" />
          <span className="w-2 h-2 rounded-full bg-blue-400 animate-bounce [animation-delay:-0.15s]" />
          <span className="w-2 h-2 rounded-full bg-blue-400 animate-bounce" />
        </div>
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

  const accent = isSuccess
    ? {
        ring: "border-emerald-500/30",
        bg: "bg-emerald-500/[0.04]",
        iconBg: "bg-emerald-500/10 border-emerald-500/25",
        iconColor: "text-emerald-400",
        title: "text-emerald-300",
        Icon: CheckCircle2,
        label: "Pipeline completed successfully",
      }
    : isFailed
      ? {
          ring: "border-red-500/30",
          bg: "bg-red-500/[0.04]",
          iconBg: "bg-red-500/10 border-red-500/25",
          iconColor: "text-red-400",
          title: "text-red-300",
          Icon: XCircle,
          label: "Pipeline failed",
        }
      : {
          ring: "border-[#22304a]",
          bg: "bg-[#141c2c]/80",
          iconBg: "bg-[#1e2a3d] border-[#22304a]",
          iconColor: "text-zinc-300",
          title: "text-[#92a4c9]",
          Icon: AlertCircle,
          label: isCancelled ? "Pipeline cancelled" : `Run ${status}`,
        };

  return (
    <div className={cn("rounded-2xl border p-6", accent.ring, accent.bg)}>
      <div className="flex items-start gap-4">
        <div
          className={cn(
            "flex items-center justify-center w-12 h-12 rounded-xl shrink-0 border",
            accent.iconBg,
          )}
        >
          <accent.Icon className={cn("w-6 h-6", accent.iconColor)} aria-hidden="true" />
        </div>
        <div className="flex-1 min-w-0">
          <h3 className={cn("text-base font-semibold", accent.title)}>
            {accent.label}
          </h3>
          <p className="mt-1 text-xs text-[#5e7196] font-mono flex items-center gap-1.5">
            <Hash className="w-3 h-3" /> {runId.slice(0, 8)}…
          </p>

          {/* Stats grid */}
          {total > 0 && (
            <div className="mt-4 flex flex-wrap gap-2">
              <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-emerald-500/10 border border-emerald-500/20">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                <span className="text-xs font-medium text-emerald-300">
                  {completed} completed
                </span>
              </div>
              {failed > 0 && (
                <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-red-500/10 border border-red-500/20">
                  <XCircle className="w-3.5 h-3.5 text-red-400" />
                  <span className="text-xs font-medium text-red-300">
                    {failed} failed
                  </span>
                </div>
              )}
              {runData?.duration_seconds != null && (
                <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-[#1e2a3d] border border-[#22304a]">
                  <Clock className="w-3.5 h-3.5 text-[#92a4c9]" />
                  <span className="text-xs font-medium text-[#92a4c9]">
                    {runData.duration_seconds.toFixed(1)}s
                  </span>
                </div>
              )}
            </div>
          )}

          {/* Error message */}
          {runData?.error_message && (
            <div className="mt-4 rounded-lg border border-red-500/25 bg-red-500/[0.06] p-3">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-red-300/80 mb-1">
                Error
              </p>
              <p className="text-xs text-red-200 font-mono leading-relaxed whitespace-pre-wrap">
                {runData.error_message}
              </p>
            </div>
          )}

          {/* Link to history */}
          <div className="mt-5 pt-4 border-t border-[#22304a]/60">
            <Link
              href={`/pipelines/${templateId}/runs`}
              className="inline-flex items-center gap-1.5 text-xs font-medium text-[#92a4c9] hover:text-white transition-colors group"
            >
              <History className="w-3.5 h-3.5" />
              View full run history
              <span className="opacity-0 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all">
                →
              </span>
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
  const lastLogs = logs.slice(-50);

  return (
    <div className={cn(card, "overflow-hidden")}>
      <button
        type="button"
        onClick={onToggle}
        className="w-full flex items-center gap-2.5 px-5 py-3.5 text-left hover:bg-[#19233a] transition-colors"
        aria-expanded={open}
      >
        <span className="flex items-center justify-center w-7 h-7 rounded-lg bg-[#1e2a3d] border border-[#22304a] text-[#92a4c9]">
          <Terminal className="w-3.5 h-3.5" />
        </span>
        <span className={cardTitle}>Log Messages</span>
        {logs.length > 0 && (
          <span className="px-2 py-0.5 rounded-full text-[10px] font-mono font-semibold bg-[#1e2a3d] border border-[#22304a] text-[#92a4c9]">
            {logs.length}
          </span>
        )}
        <span className="ml-auto text-[#5e7196]">
          {open ? (
            <ChevronUp className="w-4 h-4" />
          ) : (
            <ChevronDown className="w-4 h-4" />
          )}
        </span>
      </button>

      {open && (
        <div className="border-t border-[#22304a] bg-[#0c121d]">
          {lastLogs.length === 0 ? (
            <div className="px-5 py-8 text-center">
              <Terminal className="w-6 h-6 text-[#3d5070] mx-auto mb-2" />
              <p className="text-xs text-[#5e7196] italic">
                No log messages yet.
              </p>
            </div>
          ) : (
            <div className="max-h-72 overflow-y-auto font-mono text-[11px] leading-relaxed scrollbar-thin">
              {lastLogs.map((msg, i) => (
                <div
                  key={i}
                  className={cn(
                    "px-5 py-1.5 border-b border-[#22304a]/40 last:border-0",
                    "text-[#a8b8d4] hover:bg-[#141d2c] transition-colors",
                  )}
                >
                  <span className="text-[#3d5070] mr-3 select-none">
                    {String(i + 1).padStart(3, "0")}
                  </span>
                  <span>{msg}</span>
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
      <div className="flex items-center gap-4">
        <div className="h-10 w-10 rounded-xl bg-[#1e2a3d]" />
        <div className="flex flex-col gap-2">
          <div className="h-6 w-64 rounded bg-[#1e2a3d]" />
          <div className="h-3 w-80 rounded bg-[#1e2a3d]" />
        </div>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-[400px_1fr] gap-6">
        <div className="flex flex-col gap-4">
          <div className="h-48 rounded-2xl bg-[#141c2c] border border-[#22304a]" />
          <div className="h-28 rounded-2xl bg-[#141c2c] border border-[#22304a]" />
          <div className="h-12 rounded-xl bg-[#1e2a3d]" />
        </div>
        <div className="h-96 rounded-2xl bg-[#141c2c] border border-[#22304a]" />
      </div>
    </div>
  );
}

/** Template error state */
function ErrorTemplate({ error }: { error: Error | null }) {
  return (
    <div className="flex flex-col items-center justify-center gap-4 py-24">
      <div className="flex items-center justify-center w-14 h-14 rounded-2xl bg-red-500/10 border border-red-500/25">
        <AlertCircle className="w-7 h-7 text-red-400" aria-hidden="true" />
      </div>
      <div className="text-center max-w-md">
        <p className="text-base font-semibold text-white">
          Failed to load pipeline template
        </p>
        <p className="mt-2 text-sm text-[#92a4c9]">
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
// Status meta (for the run-status pill in header)
// ─────────────────────────────────────────────────────────────────────────────

function statusMeta(status: PipelineStatus | null | undefined) {
  switch (status) {
    case "running":
      return {
        label: "Running",
        cls: "bg-blue-500/10 text-blue-300 border-blue-500/25",
        dot: "bg-blue-400 animate-pulse",
      };
    case "paused":
      return {
        label: "Paused",
        cls: "bg-yellow-500/10 text-yellow-300 border-yellow-500/25",
        dot: "bg-yellow-400",
      };
    case "completed":
      return {
        label: "Completed",
        cls: "bg-emerald-500/10 text-emerald-300 border-emerald-500/25",
        dot: "bg-emerald-400",
      };
    case "failed":
      return {
        label: "Failed",
        cls: "bg-red-500/10 text-red-300 border-red-500/25",
        dot: "bg-red-400",
      };
    case "cancelled":
      return {
        label: "Cancelled",
        cls: "bg-zinc-500/10 text-zinc-300 border-zinc-500/25",
        dot: "bg-zinc-400",
      };
    case "pending":
      return {
        label: "Pending",
        cls: "bg-indigo-500/10 text-indigo-300 border-indigo-500/25",
        dot: "bg-indigo-400 animate-pulse",
      };
    default:
      return {
        label: status ? String(status) : "Idle",
        cls: "bg-[#1e2a3d] text-[#92a4c9] border-[#22304a]",
        dot: "bg-[#3d5070]",
      };
  }
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
  const runBelongsHere = !!activeRunId && activeTemplateId === templateId;

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

  const runMeta = statusMeta(activeRunStatus);

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
      {/* ── Hero header ──────────────────────────────────────────────────── */}
      <header
        className={cn(
          "relative overflow-hidden rounded-2xl border border-[#22304a]",
          "bg-gradient-to-br from-[#141c2c] via-[#141c2c] to-[#101725]",
        )}
      >
        {/* Decorative top glow */}
        <div
          aria-hidden="true"
          className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-[#3d5070] to-transparent"
        />
        <div
          aria-hidden="true"
          className="absolute -top-24 -right-24 w-64 h-64 rounded-full bg-[#135bec]/10 blur-3xl pointer-events-none"
        />

        <div className="relative flex flex-col sm:flex-row sm:items-start justify-between gap-4 px-6 py-5">
          <div className="flex items-start gap-4 min-w-0">
            <Link
              href={`/pipelines/${templateId}`}
              className={cn(
                "inline-flex items-center justify-center w-10 h-10 rounded-xl shrink-0 mt-0.5",
                "border border-[#22304a] bg-[#101725] text-[#92a4c9]",
                "hover:border-[#3d5070] hover:text-white hover:bg-[#19233a]",
                "transition-all duration-150",
              )}
              title="Back to pipeline"
              aria-label="Back to pipeline"
            >
              <ArrowLeft className="w-4 h-4" aria-hidden="true" />
            </Link>

            <div className="min-w-0">
              <p className="text-[11px] font-medium uppercase tracking-wider text-[#5e7196] flex items-center gap-1.5">
                <GitBranch className="w-3 h-3" />
                Pipeline Run
              </p>
              <h1 className="mt-1 text-xl sm:text-2xl font-bold text-white leading-tight truncate">
                {template.name}
              </h1>
              {template.description && (
                <p className={cn("mt-1.5 text-sm line-clamp-2 max-w-2xl", mutedText)}>
                  {template.description}
                </p>
              )}

              {/* Meta row */}
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-[11px] font-medium bg-[#1e2a3d] border border-[#22304a] text-[#92a4c9]">
                  <Layers className="w-3 h-3" />
                  {template.node_count}{" "}
                  {template.node_count === 1 ? "node" : "nodes"}
                </span>

                {hasActiveRun && (
                  <span
                    className={cn(
                      "inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-[11px] font-medium border",
                      runMeta.cls,
                    )}
                  >
                    <span className={cn("w-1.5 h-1.5 rounded-full", runMeta.dot)} />
                    {runMeta.label}
                  </span>
                )}

                {hasActiveRun && <WsStatusIndicator status={wsStatus} />}

                {hasActiveRun && activeRunId && (
                  <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-[11px] font-mono bg-[#1e2a3d] border border-[#22304a] text-[#7a8baa]">
                    <Hash className="w-3 h-3" />
                    {activeRunId.slice(0, 8)}
                  </span>
                )}
              </div>
            </div>
          </div>

          <Link href={`/pipelines/${templateId}/runs`} className="shrink-0">
            <Button
              variant="secondary"
              size="sm"
              leftIcon={<History className="w-3.5 h-3.5" aria-hidden="true" />}
            >
              Run History
            </Button>
          </Link>
        </div>
      </header>

      {/* ── Main two-column grid ──────────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-[400px_1fr] gap-6 items-start">
        {/* ── Left column: controls ──────────────────────────────────────── */}
        <aside className="flex flex-col gap-4 lg:sticky lg:top-4">
          {/* Document upload */}
          <section className={cn(card, "overflow-hidden")}>
            <SectionHeader
              icon={<FileText className="w-3.5 h-3.5" />}
              title="Document"
              hint="Optional input file"
            />
            <div className="p-4">
              <DocumentUpload
                file={file}
                onChange={setFile}
                disabled={isActivelyRunning || startMutation.isPending}
              />
            </div>
          </section>

          {/* LLM profile */}
          <section className={cn(card, "overflow-hidden")}>
            <SectionHeader
              icon={<Sparkles className="w-3.5 h-3.5" />}
              title="LLM Profile"
              hint="Model used by AI nodes"
            />
            <div className="p-4">
              <LLMProfileSelector
                value={llmProfileId}
                onChange={setLlmProfileId}
                disabled={isActivelyRunning || startMutation.isPending}
              />
            </div>
          </section>

          {/* Run button + controls */}
          <div className="flex flex-col gap-3 pt-1">
            <Button
              variant="primary"
              size="lg"
              fullWidth
              loading={startMutation.isPending}
              disabled={!canStartRun}
              onClick={handleRun}
              leftIcon={
                !startMutation.isPending ? (
                  <Play className="w-4 h-4 fill-current" aria-hidden="true" />
                ) : undefined
              }
              className="shadow-lg shadow-blue-500/20"
            >
              {startMutation.isPending
                ? "Starting…"
                : isActivelyRunning
                  ? "Pipeline Running…"
                  : "Run Pipeline"}
            </Button>

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
          </div>
        </aside>

        {/* ── Right column: DAG + progress ──────────────────────────────── */}
        <div className="flex flex-col gap-4 min-w-0">
          {!hasActiveRun && <NoRunPlaceholder />}

          {isActivelyRunning && <RunInProgressCard />}

          {isTerminalRun && activeRunStatus && activeRunId && (
            <TerminalSummaryCard
              status={activeRunStatus}
              runId={activeRunId}
              nodeStatuses={nodeStatuses}
              templateId={templateId}
              runData={runData ?? undefined}
            />
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
