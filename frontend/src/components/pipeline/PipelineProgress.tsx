"use client";

import * as React from "react";
import {
  CheckCircle2,
  XCircle,
  Loader2,
  Clock,
  MinusCircle,
  Wifi,
  WifiOff,
} from "lucide-react";

import { Badge } from "@/components/ui/Select";
import { cn } from "@/lib/utils";
import {
  STAGE_LABELS,
  STAGE_ORDER,
  type PipelineRunResponse,
  type AgentRunStatus,
  type AgentRunResult,
  type AgentStage,
  type WSEvent,
  type PipelineStatus,
} from "@/types";

// ─────────────────────────────────────────────────────────────────────────────
// Props
// ─────────────────────────────────────────────────────────────────────────────

export interface PipelineProgressProps {
  run: PipelineRunResponse | null;
  wsEvents: WSEvent[];
  agentStatuses: Record<string, AgentRunStatus>;
  currentStage: string | null;
  wsConnected: boolean;
}

// ─────────────────────────────────────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────────────────────────────────────

const STAGE_AGENT_COUNTS: Record<string, number> = {
  ingestion: 1,
  testcase: 10,
  execution: 5,
  reporting: 3,
};

// ─────────────────────────────────────────────────────────────────────────────
// Status configuration
// ─────────────────────────────────────────────────────────────────────────────

interface StatusConfig {
  icon: React.ReactNode;
  textClass: string;
  label: string;
}

function getAgentStatusConfig(status: AgentRunStatus): StatusConfig {
  switch (status) {
    case "completed":
      return {
        icon: (
          <CheckCircle2
            className="w-4 h-4 text-[#4ade80] shrink-0"
            aria-hidden="true"
          />
        ),
        textClass: "text-[#4ade80]",
        label: "Completed",
      };
    case "running":
      return {
        icon: (
          <Loader2
            className="w-4 h-4 text-[#5b9eff] animate-spin shrink-0"
            aria-hidden="true"
          />
        ),
        textClass: "text-[#5b9eff] animate-pulse",
        label: "Running",
      };
    case "failed":
      return {
        icon: (
          <XCircle
            className="w-4 h-4 text-[#f87171] shrink-0"
            aria-hidden="true"
          />
        ),
        textClass: "text-[#f87171]",
        label: "Failed",
      };
    case "skipped":
      return {
        icon: (
          <MinusCircle
            className="w-4 h-4 text-[#3d5070] shrink-0"
            aria-hidden="true"
          />
        ),
        textClass: "text-[#3d5070]",
        label: "Skipped",
      };
    default:
      return {
        icon: (
          <Clock
            className="w-4 h-4 text-[#92a4c9] shrink-0"
            aria-hidden="true"
          />
        ),
        textClass: "text-[#92a4c9]",
        label: "Pending",
      };
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Pipeline-level status badge config
// ─────────────────────────────────────────────────────────────────────────────

type BadgeVariant =
  | "default"
  | "primary"
  | "success"
  | "warning"
  | "danger"
  | "info";

interface PipelineStatusBadgeConfig {
  variant: BadgeVariant;
  label: string;
  dot: boolean;
}

const PIPELINE_STATUS_BADGE: Record<PipelineStatus, PipelineStatusBadgeConfig> =
  {
    pending: { variant: "default", label: "Pending", dot: false },
    running: { variant: "info", label: "Running", dot: true },
    completed: { variant: "success", label: "Completed", dot: false },
    failed: { variant: "danger", label: "Failed", dot: false },
    cancelled: { variant: "warning", label: "Cancelled", dot: false },
  };

// ─────────────────────────────────────────────────────────────────────────────
// ProgressBar
// ─────────────────────────────────────────────────────────────────────────────

interface ProgressBarProps {
  /** 0–100 */
  value: number;
  completed?: boolean;
  className?: string;
}

function ProgressBar({
  value,
  completed = false,
  className,
}: ProgressBarProps) {
  const pct = Math.max(0, Math.min(100, value));

  return (
    <div
      role="progressbar"
      aria-valuenow={pct}
      aria-valuemin={0}
      aria-valuemax={100}
      className={cn(
        "h-1.5 w-full rounded-full bg-[#2b3b55] overflow-hidden",
        className,
      )}
    >
      <div
        className={cn(
          "h-full rounded-full transition-[width] duration-500 ease-out",
          completed
            ? "bg-[#22c55e]"
            : "bg-linear-to-r from-[#135bec] to-[#5b9eff]",
        )}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// AgentRow
// ─────────────────────────────────────────────────────────────────────────────

interface AgentRowProps {
  agent: AgentRunResult;
  /** Live status override from WebSocket events, takes precedence over agent.status */
  liveStatus?: AgentRunStatus;
}

function AgentRow({ agent, liveStatus }: AgentRowProps) {
  const effectiveStatus = liveStatus ?? agent.status;
  const cfg = getAgentStatusConfig(effectiveStatus);

  const rawPreview = agent.output_preview ?? null;
  const preview =
    rawPreview && rawPreview.length > 80
      ? rawPreview.slice(0, 79) + "…"
      : rawPreview;

  return (
    <div
      className={cn(
        "flex items-start gap-3 px-4 py-2.5",
        "border-b border-[#2b3b55]/50 last:border-0",
        effectiveStatus === "running" && "bg-[#135bec]/5",
      )}
    >
      {/* Status icon */}
      <div className="mt-0.5">{cfg.icon}</div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-medium text-white leading-snug">
            {agent.display_name}
          </span>
          <span className={cn("text-xs shrink-0", cfg.textClass)}>
            {cfg.label}
          </span>
        </div>

        {/* Output preview */}
        {preview && (
          <p
            className="mt-0.5 text-xs text-[#3d5070] truncate"
            title={rawPreview ?? undefined}
          >
            {preview}
          </p>
        )}

        {/* Error message */}
        {effectiveStatus === "failed" && agent.error_message && (
          <p
            className="mt-0.5 text-xs text-[#f87171] truncate"
            title={agent.error_message}
          >
            {agent.error_message.length > 80
              ? agent.error_message.slice(0, 79) + "…"
              : agent.error_message}
          </p>
        )}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// StageBlock
// ─────────────────────────────────────────────────────────────────────────────

interface StageBlockProps {
  stage: AgentStage;
  agents: AgentRunResult[];
  agentStatuses: Record<string, AgentRunStatus>;
  isCurrentStage: boolean;
}

function StageBlock({
  stage,
  agents,
  agentStatuses,
  isCurrentStage,
}: StageBlockProps) {
  const label = STAGE_LABELS[stage];
  const totalExpected = STAGE_AGENT_COUNTS[stage] ?? agents.length;

  const completedCount = agents.filter((a) => {
    const s = agentStatuses[a.agent_id] ?? a.status;
    return s === "completed" || s === "skipped";
  }).length;

  const hasRunning = agents.some(
    (a) => (agentStatuses[a.agent_id] ?? a.status) === "running",
  );
  const hasFailed = agents.some(
    (a) => (agentStatuses[a.agent_id] ?? a.status) === "failed",
  );

  const progressPct =
    totalExpected > 0 ? (completedCount / totalExpected) * 100 : 0;
  const stageCompleted =
    completedCount >= totalExpected && totalExpected > 0 && !hasFailed;

  return (
    <div
      className={cn(
        "rounded-xl border overflow-hidden",
        "bg-[#18202F]",
        isCurrentStage
          ? "border-[#135bec]/40 shadow-[0_0_0_1px_rgba(19,91,236,0.08)]"
          : stageCompleted
            ? "border-[#22c55e]/25"
            : hasFailed
              ? "border-[#ef4444]/25"
              : "border-[#2b3b55]",
      )}
    >
      {/* ── Stage header ────────────────────────────────────────────────── */}
      <div
        className={cn(
          "flex items-center gap-3 px-4 py-3",
          "border-b",
          isCurrentStage
            ? "border-[#135bec]/20 bg-[#135bec]/5"
            : stageCompleted
              ? "border-[#22c55e]/15 bg-[#22c55e]/5"
              : hasFailed
                ? "border-[#ef4444]/15 bg-[#ef4444]/5"
                : "border-[#2b3b55]/60",
        )}
      >
        {/* Stage label */}
        <span className="flex-1 text-sm font-semibold text-white leading-snug truncate">
          {label}
        </span>

        {/* Progress fraction */}
        <span className="shrink-0 text-xs text-[#92a4c9] tabular-nums">
          {completedCount}/{totalExpected}
        </span>

        {/* Running indicator */}
        {isCurrentStage && hasRunning && (
          <span className="shrink-0 inline-flex items-center gap-1.5 text-xs text-[#5b9eff]">
            <span
              className="w-1.5 h-1.5 rounded-full bg-[#5b9eff] animate-pulse"
              aria-hidden="true"
            />
            Running
          </span>
        )}

        {/* Status badges */}
        {stageCompleted && (
          <Badge variant="success" size="xs">
            Done
          </Badge>
        )}
        {hasFailed && !isCurrentStage && (
          <Badge variant="danger" size="xs">
            Failed
          </Badge>
        )}
      </div>

      {/* ── Progress bar ────────────────────────────────────────────────── */}
      <ProgressBar
        value={progressPct}
        completed={stageCompleted}
        className="rounded-none h-1"
      />

      {/* ── Agent rows ──────────────────────────────────────────────────── */}
      {agents.length > 0 ? (
        <div role="list" aria-label={`Agents in ${label}`}>
          {agents.map((agent) => (
            <div key={agent.agent_id} role="listitem">
              <AgentRow
                agent={agent}
                liveStatus={agentStatuses[agent.agent_id]}
              />
            </div>
          ))}
        </div>
      ) : (
        <div className="flex items-center justify-center py-6 px-4">
          <p className="text-xs text-[#3d5070] italic">
            Waiting for agents in this stage…
          </p>
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// PipelineProgress
// ─────────────────────────────────────────────────────────────────────────────

export function PipelineProgress({
  run,
  wsEvents,
  agentStatuses,
  currentStage,
  wsConnected,
}: PipelineProgressProps) {
  // ── Always group agents before any conditional returns (hooks rules) ──────
  const agentsByStage = React.useMemo<
    Record<AgentStage, AgentRunResult[]>
  >(() => {
    const groups: Record<AgentStage, AgentRunResult[]> = {
      ingestion: [],
      testcase: [],
      execution: [],
      reporting: [],
    };
    if (!run) return groups;
    for (const agent of run.agent_runs) {
      if (agent.stage in groups) {
        groups[agent.stage].push(agent);
      }
    }
    return groups;
  }, [run]);

  // ── Placeholder when no run is active ────────────────────────────────────
  if (!run) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-4 text-center">
        <div
          className={cn(
            "w-14 h-14 rounded-xl",
            "bg-[#1e2a3d] border border-[#2b3b55]",
            "flex items-center justify-center",
          )}
        >
          <Clock className="w-7 h-7 text-[#3d5070]" aria-hidden="true" />
        </div>
        <div className="max-w-xs">
          <p className="text-sm font-semibold text-[#92a4c9]">
            Waiting for pipeline run…
          </p>
          <p className="mt-1 text-xs text-[#3d5070] leading-relaxed">
            Submit a document above to start the pipeline.
          </p>
        </div>
      </div>
    );
  }

  // ── Resolve overall status badge config ───────────────────────────────────
  const statusCfg =
    PIPELINE_STATUS_BADGE[run.status] ?? PIPELINE_STATUS_BADGE.pending;

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col gap-4">
      {/* ── Top status bar ────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2.5 flex-wrap">
          <span className="text-sm font-semibold text-white">Pipeline Run</span>

          {/* Short run ID */}
          <code className="text-[11px] font-mono text-[#3d5070] bg-[#1e2a3d] px-1.5 py-0.5 rounded border border-[#2b3b55]">
            {run.id.slice(0, 8)}…
          </code>

          {/* Overall status badge */}
          <Badge variant={statusCfg.variant} dot={statusCfg.dot}>
            {statusCfg.label}
          </Badge>

          {/* Document filename */}
          {run.document_filename && (
            <span
              className="text-xs text-[#92a4c9] truncate max-w-50"
              title={run.document_filename}
            >
              {run.document_filename}
            </span>
          )}
        </div>

        {/* WebSocket connection indicator */}
        <div
          className={cn(
            "flex items-center gap-1.5 text-xs font-medium transition-colors duration-300",
            wsConnected ? "text-[#4ade80]" : "text-[#3d5070]",
          )}
          title={
            wsConnected
              ? "Live updates active"
              : "Not connected to live updates"
          }
          aria-label={
            wsConnected ? "Live updates active" : "Live updates offline"
          }
        >
          {wsConnected ? (
            <Wifi className="w-3.5 h-3.5" aria-hidden="true" />
          ) : (
            <WifiOff className="w-3.5 h-3.5" aria-hidden="true" />
          )}
          <span>{wsConnected ? "Live" : "Offline"}</span>
        </div>
      </div>

      {/* ── Top-level error message ───────────────────────────────────────── */}
      {run.error_message && (
        <div className="flex items-start gap-2.5 px-3 py-2.5 rounded-lg bg-[#ef4444]/10 border border-[#ef4444]/25">
          <XCircle
            className="w-4 h-4 text-[#f87171] mt-0.5 shrink-0"
            aria-hidden="true"
          />
          <p className="text-xs text-[#f87171] leading-relaxed">
            {run.error_message}
          </p>
        </div>
      )}

      {/* ── Stage blocks ─────────────────────────────────────────────────── */}
      {STAGE_ORDER.map((stage) => (
        <StageBlock
          key={stage}
          stage={stage}
          agents={agentsByStage[stage]}
          agentStatuses={agentStatuses}
          isCurrentStage={currentStage === stage}
        />
      ))}

      {/* ── Live event log (collapsible, last 20 events) ─────────────────── */}
      {wsEvents.length > 0 && (
        <details className="group">
          <summary
            className={cn(
              "cursor-pointer select-none",
              "text-xs text-[#3d5070] hover:text-[#92a4c9]",
              "transition-colors duration-150 py-1 w-fit",
            )}
          >
            {wsEvents.length} live event
            {wsEvents.length !== 1 ? "s" : ""} received
          </summary>

          <ul className="mt-2 flex flex-col gap-1 max-h-48 overflow-y-auto pr-1">
            {wsEvents.slice(-20).map((ev, i) => (
              <li
                key={i}
                className={cn(
                  "flex items-center gap-2 px-2.5 py-1.5 rounded-lg",
                  "text-[11px] font-mono",
                  "bg-[#1e2a3d] border border-[#2b3b55]/60",
                )}
              >
                <span className="text-[#92a4c9] shrink-0">{ev.event}</span>
                <span className="text-[#2b3b55]" aria-hidden="true">
                  ·
                </span>
                <span className="text-[#3d5070]">
                  {new Date(ev.timestamp).toLocaleTimeString()}
                </span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

export default PipelineProgress;
