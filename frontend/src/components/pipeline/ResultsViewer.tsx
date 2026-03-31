"use client";

import * as React from "react";
import {
  TestTube2,
  BarChart3,
  BookOpen,
  FileText,
  Clock,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Loader2,
  SkipForward,
} from "lucide-react";

import { Badge } from "@/components/ui/Select";
import { cn } from "@/lib/utils";
import type {
  PipelineRunResponse,
  AgentRunResult,
  AgentRunStatus,
  PipelineStatus,
} from "@/types";

// ─────────────────────────────────────────────────────────────────────────────
// Props
// ─────────────────────────────────────────────────────────────────────────────

export interface ResultsViewerProps {
  run: PipelineRunResponse;
}

// ─────────────────────────────────────────────────────────────────────────────
// Tab definitions
// ─────────────────────────────────────────────────────────────────────────────

type TabId = "testcases" | "coverage" | "report";

interface TabDef {
  id: TabId;
  label: string;
  icon: React.ReactNode;
}

const TABS: TabDef[] = [
  {
    id: "testcases",
    label: "Test Cases",
    icon: <TestTube2 className="w-3.5 h-3.5" aria-hidden="true" />,
  },
  {
    id: "coverage",
    label: "Coverage",
    icon: <BarChart3 className="w-3.5 h-3.5" aria-hidden="true" />,
  },
  {
    id: "report",
    label: "Report",
    icon: <BookOpen className="w-3.5 h-3.5" aria-hidden="true" />,
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

function formatDuration(
  startedAt: string | null | undefined,
  completedAt: string | null | undefined
): string {
  if (!startedAt || !completedAt) return "—";
  const ms = new Date(completedAt).getTime() - new Date(startedAt).getTime();
  if (ms < 0) return "—";
  const totalSec = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSec / 60);
  const seconds = totalSec % 60;
  if (minutes === 0) return `${seconds}s`;
  return `${minutes}m ${seconds}s`;
}

// ─────────────────────────────────────────────────────────────────────────────
// Agent status badge
// ─────────────────────────────────────────────────────────────────────────────

function AgentStatusBadge({ status }: { status: AgentRunStatus }) {
  switch (status) {
    case "completed":
      return <Badge variant="success" size="xs">Completed</Badge>;
    case "failed":
      return <Badge variant="danger" size="xs">Failed</Badge>;
    case "running":
      return (
        <Badge variant="primary" size="xs" dot className="animate-pulse">
          Running
        </Badge>
      );
    case "skipped":
      return <Badge variant="default" size="xs">Skipped</Badge>;
    default:
      return <Badge variant="default" size="xs">Pending</Badge>;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Agent status icon (inline, smaller)
// ─────────────────────────────────────────────────────────────────────────────

function AgentStatusIcon({ status }: { status: AgentRunStatus }) {
  switch (status) {
    case "completed":
      return (
        <CheckCircle2
          className="w-3.5 h-3.5 text-[#4ade80] shrink-0"
          aria-hidden="true"
        />
      );
    case "failed":
      return (
        <XCircle
          className="w-3.5 h-3.5 text-[#f87171] shrink-0"
          aria-hidden="true"
        />
      );
    case "running":
      return (
        <Loader2
          className="w-3.5 h-3.5 text-[#5b9eff] shrink-0 animate-spin"
          aria-hidden="true"
        />
      );
    case "skipped":
      return (
        <SkipForward
          className="w-3.5 h-3.5 text-[#3d5070] shrink-0"
          aria-hidden="true"
        />
      );
    default:
      return (
        <AlertCircle
          className="w-3.5 h-3.5 text-[#3d5070] shrink-0"
          aria-hidden="true"
        />
      );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Agent output card
// ─────────────────────────────────────────────────────────────────────────────

function AgentOutputCard({ agent }: { agent: AgentRunResult }) {
  const agentDuration = formatDuration(agent.started_at, agent.completed_at);

  return (
    <div className="rounded-xl border border-[#2b3b55] bg-[#18202F] overflow-hidden">
      {/* ── Card header ──────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between gap-3 px-4 py-3 border-b border-[#2b3b55]">
        <div className="flex items-center gap-2 min-w-0">
          <AgentStatusIcon status={agent.status} />
          <p className="text-sm font-medium text-white truncate leading-snug">
            {agent.display_name}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {agentDuration !== "—" && (
            <span className="flex items-center gap-1 text-[10px] text-[#3d5070]">
              <Clock className="w-3 h-3" aria-hidden="true" />
              {agentDuration}
            </span>
          )}
          <AgentStatusBadge status={agent.status} />
        </div>
      </div>

      {/* ── Card body ────────────────────────────────────────────────────── */}
      <div className="p-4">
        {agent.output_preview ? (
          <pre
            className={cn(
              "font-mono text-xs text-[#92a4c9] whitespace-pre-wrap break-words",
              "bg-[#101622] rounded-lg p-4 border border-[#2b3b55]",
              "max-h-64 overflow-y-auto",
              // Scrollbar styling
              "[&::-webkit-scrollbar]:w-1.5",
              "[&::-webkit-scrollbar-track]:bg-transparent",
              "[&::-webkit-scrollbar-thumb]:bg-[#2b3b55] [&::-webkit-scrollbar-thumb]:rounded-full"
            )}
          >
            {agent.output_preview}
          </pre>
        ) : agent.error_message ? (
          <div className="flex items-start gap-2.5 bg-[#ef4444]/5 rounded-lg p-3 border border-[#ef4444]/20">
            <XCircle
              className="w-3.5 h-3.5 text-[#f87171] shrink-0 mt-0.5"
              aria-hidden="true"
            />
            <p className="text-xs text-[#f87171] font-mono leading-relaxed">
              {agent.error_message}
            </p>
          </div>
        ) : (
          <p className="text-xs text-[#3d5070] italic text-center py-2">
            No output available for this agent.
          </p>
        )}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Empty stage placeholder
// ─────────────────────────────────────────────────────────────────────────────

function EmptyStage({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-4 text-center">
      <div
        className={cn(
          "w-12 h-12 rounded-xl",
          "bg-[#1e2a3d] border border-[#2b3b55]",
          "flex items-center justify-center"
        )}
        aria-hidden="true"
      >
        <FileText className="w-5 h-5 text-[#3d5070]" />
      </div>
      <p className="text-sm text-[#3d5070] max-w-xs leading-relaxed">{message}</p>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Run summary card (Report tab)
// ─────────────────────────────────────────────────────────────────────────────

const statusTextColor: Record<PipelineStatus, string> = {
  pending: "text-[#fbbf24]",
  running: "text-[#22d3ee]",
  completed: "text-[#4ade80]",
  failed: "text-[#f87171]",
  cancelled: "text-[#92a4c9]",
};

function RunSummaryCard({ run }: { run: PipelineRunResponse }) {
  const totalAgents = run.agent_runs.length;
  const completedAgents = run.agent_runs.filter(
    (a) => a.status === "completed"
  ).length;
  const failedAgents = run.agent_runs.filter(
    (a) => a.status === "failed"
  ).length;
  const duration = formatDuration(run.started_at, run.completed_at);

  return (
    <div className="rounded-xl border border-[#2b3b55] bg-[#18202F] p-5 mb-4">
      {/* ── Header ───────────────────────────────────────────────────────── */}
      <div className="flex items-center gap-2 mb-4">
        <BookOpen className="w-4 h-4 text-[#92a4c9]" aria-hidden="true" />
        <h3 className="text-sm font-semibold text-white">Run Summary</h3>
      </div>

      {/* ── Stats grid ───────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {/* Total agents */}
        <div className="flex flex-col gap-1">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-[#3d5070] select-none">
            Total Agents
          </span>
          <span className="text-2xl font-semibold text-white tabular-nums leading-none">
            {totalAgents}
          </span>
        </div>

        {/* Duration */}
        <div className="flex flex-col gap-1">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-[#3d5070] select-none">
            Duration
          </span>
          <span className="flex items-center gap-1.5 text-2xl font-semibold text-white tabular-nums leading-none">
            <Clock className="w-4 h-4 text-[#92a4c9] shrink-0" aria-hidden="true" />
            {duration}
          </span>
        </div>

        {/* Status */}
        <div className="flex flex-col gap-1">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-[#3d5070] select-none">
            Status
          </span>
          <span
            className={cn(
              "text-2xl font-semibold capitalize leading-none",
              statusTextColor[run.status]
            )}
          >
            {run.status}
          </span>
        </div>

        {/* Agent breakdown */}
        <div className="flex flex-col gap-1">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-[#3d5070] select-none">
            Agents
          </span>
          <div className="flex items-center gap-2 leading-none pt-0.5">
            <span className="flex items-center gap-1 text-sm text-[#4ade80] tabular-nums font-medium">
              <CheckCircle2 className="w-3.5 h-3.5" aria-hidden="true" />
              {completedAgents}
            </span>
            {failedAgents > 0 && (
              <span className="flex items-center gap-1 text-sm text-[#f87171] tabular-nums font-medium">
                <XCircle className="w-3.5 h-3.5" aria-hidden="true" />
                {failedAgents}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* ── Document ─────────────────────────────────────────────────────── */}
      <div className="mt-4 pt-4 border-t border-[#2b3b55] flex items-center gap-2">
        <FileText className="w-3.5 h-3.5 text-[#3d5070] shrink-0" aria-hidden="true" />
        <span className="text-xs text-[#92a4c9] truncate" title={run.document_filename}>
          {run.document_filename}
        </span>
      </div>

      {/* ── Error message ─────────────────────────────────────────────────── */}
      {run.error_message && (
        <div className="mt-3 flex items-start gap-2 bg-[#ef4444]/5 rounded-lg p-3 border border-[#ef4444]/20">
          <AlertCircle
            className="w-3.5 h-3.5 text-[#f87171] shrink-0 mt-0.5"
            aria-hidden="true"
          />
          <p className="text-xs text-[#f87171] leading-relaxed">
            {run.error_message}
          </p>
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// ResultsViewer
// ─────────────────────────────────────────────────────────────────────────────

export function ResultsViewer({ run }: ResultsViewerProps) {
  const [activeTab, setActiveTab] = React.useState<TabId>("testcases");

  // ── Filter agents by stage ────────────────────────────────────────────────
  const testcaseAgents = run.agent_runs.filter((a) => a.stage === "testcase");
  const executionAgents = run.agent_runs.filter((a) => a.stage === "execution");
  const reportingAgents = run.agent_runs.filter((a) => a.stage === "reporting");

  return (
    <div className="rounded-2xl border border-[#2b3b55] bg-[#18202F] overflow-hidden">
      {/* ── Tab bar ──────────────────────────────────────────────────────── */}
      <div
        className="flex items-center border-b border-[#2b3b55] px-1"
        role="tablist"
        aria-label="Results sections"
      >
        {TABS.map((tab) => {
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              role="tab"
              id={`results-tab-${tab.id}`}
              aria-selected={isActive}
              aria-controls={`results-panel-${tab.id}`}
              onClick={() => setActiveTab(tab.id)}
              className={cn(
                // Base
                "inline-flex items-center gap-2 px-4 py-3.5 text-sm font-medium",
                "border-b-2 transition-colors duration-150 select-none",
                // Focus
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[#135bec]",
                // Active vs inactive
                isActive
                  ? "text-white border-[#135bec]"
                  : "text-[#92a4c9] border-transparent hover:text-white hover:border-[#2b3b55]"
              )}
            >
              <span className="shrink-0">{tab.icon}</span>
              <span>{tab.label}</span>
            </button>
          );
        })}
      </div>

      {/* ── Tab panels ───────────────────────────────────────────────────── */}
      <div className="p-5">
        {/* ── Test Cases ─────────────────────────────────────────────────── */}
        <div
          id="results-panel-testcases"
          role="tabpanel"
          aria-labelledby="results-tab-testcases"
          hidden={activeTab !== "testcases"}
        >
          {activeTab === "testcases" && (
            <div className="space-y-4">
              {testcaseAgents.length > 0 ? (
                testcaseAgents.map((agent) => (
                  <AgentOutputCard key={agent.agent_id} agent={agent} />
                ))
              ) : (
                <EmptyStage message="Test cases will appear here after the pipeline completes." />
              )}
            </div>
          )}
        </div>

        {/* ── Coverage ───────────────────────────────────────────────────── */}
        <div
          id="results-panel-coverage"
          role="tabpanel"
          aria-labelledby="results-tab-coverage"
          hidden={activeTab !== "coverage"}
        >
          {activeTab === "coverage" && (
            <div className="space-y-4">
              {executionAgents.length > 0 ? (
                executionAgents.map((agent) => (
                  <AgentOutputCard key={agent.agent_id} agent={agent} />
                ))
              ) : (
                <EmptyStage message="Coverage data will appear here after the execution stage completes." />
              )}
            </div>
          )}
        </div>

        {/* ── Report ─────────────────────────────────────────────────────── */}
        <div
          id="results-panel-report"
          role="tabpanel"
          aria-labelledby="results-tab-report"
          hidden={activeTab !== "report"}
        >
          {activeTab === "report" && (
            <div className="space-y-4">
              <RunSummaryCard run={run} />
              {reportingAgents.length > 0 ? (
                reportingAgents.map((agent) => (
                  <AgentOutputCard key={agent.agent_id} agent={agent} />
                ))
              ) : (
                <EmptyStage message="Report output will appear here after the reporting stage completes." />
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default ResultsViewer;
