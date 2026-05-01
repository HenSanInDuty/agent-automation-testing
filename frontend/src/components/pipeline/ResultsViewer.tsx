"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import {
  TestTube2,
  BarChart3,
  BookOpen,
  FileText,
  FileDown,
  Clock,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Loader2,
  SkipForward,
  Network,
  FolderOpen,
  Download,
  Archive,
} from "lucide-react";

import { Badge } from "@/components/ui/Select";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/utils";
import { pipelineApi } from "@/lib/api";
import type {
  PipelineRunResponse,
  AgentRunResult,
  AgentRunStatus,
  PipelineStatus,
} from "@/types";
import { toast } from "@/components/ui/Toast";
import { PrettyOutput } from "./PrettyOutput";

// ─────────────────────────────────────────────────────────────────────────────
// Props
// ─────────────────────────────────────────────────────────────────────────────

export interface ResultsViewerProps {
  run: PipelineRunResponse;
  // V3 DAG fields (optional — from template)
  templateNodes?: Array<{
    node_id: string;
    label: string;
    node_type: string;
    enabled: boolean;
  }>;
}

// ─────────────────────────────────────────────────────────────────────────────
// Tab definitions
// ─────────────────────────────────────────────────────────────────────────────

type TabId = "testcases" | "coverage" | "report" | "nodes" | "files";

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
  {
    id: "nodes",
    label: "Nodes",
    icon: <Network className="w-3.5 h-3.5" aria-hidden="true" />,
  },
  {
    id: "files",
    label: "Files",
    icon: <FolderOpen className="w-3.5 h-3.5" aria-hidden="true" />,
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

function formatDuration(
  startedAt: string | null | undefined,
  completedAt: string | null | undefined,
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
      return (
        <Badge variant="success" size="xs">
          Completed
        </Badge>
      );
    case "failed":
      return (
        <Badge variant="danger" size="xs">
          Failed
        </Badge>
      );
    case "running":
      return (
        <Badge variant="primary" size="xs" dot className="animate-pulse">
          Running
        </Badge>
      );
    case "skipped":
      return (
        <Badge variant="default" size="xs">
          Skipped
        </Badge>
      );
    default:
      return (
        <Badge variant="default" size="xs">
          Pending
        </Badge>
      );
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
          <PrettyOutput value={agent.output_preview} />
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
          "flex items-center justify-center",
        )}
        aria-hidden="true"
      >
        <FileText className="w-5 h-5 text-[#3d5070]" />
      </div>
      <p className="text-sm text-[#3d5070] max-w-xs leading-relaxed">
        {message}
      </p>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────// FilesTab — downloadable Playwright artifacts
// ─────────────────────────────────────────────────────────────────────────────

function FilesTab({ runId }: { runId: string }) {
  const { data: files, isLoading, isError } = useQuery({
    queryKey: ["playwrightArtifacts", runId],
    queryFn: () => pipelineApi.listPlaywrightArtifacts(runId),
    staleTime: 30_000,
  });

  const handleDownloadFile = (filePath: string) => {
    const url = pipelineApi.getPlaywrightFileUrl(runId, filePath);
    const a = document.createElement("a");
    a.href = url;
    a.download = filePath.split("/").pop() ?? filePath;
    document.body.appendChild(a);
    a.click();
    a.remove();
  };

  const handleDownloadZip = () => {
    const url = pipelineApi.getPlaywrightZipUrl(runId);
    const a = document.createElement("a");
    a.href = url;
    a.download = `playwright-tests-${runId.slice(0, 8)}.zip`;
    document.body.appendChild(a);
    a.click();
    a.remove();
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16 gap-2 text-[#3d5070]">
        <Loader2 className="w-4 h-4 animate-spin" />
        <span className="text-sm">Loading files…</span>
      </div>
    );
  }

  if (isError || !files) {
    return (
      <EmptyStage message="Could not load artifact files. Run the pipeline first." />
    );
  }

  if (files.length === 0) {
    return (
      <EmptyStage message="No Playwright files generated yet. Re-run the pipeline to generate .spec.ts files and test infrastructure." />
    );
  }

  // Group by directory
  const grouped = files.reduce<Record<string, typeof files>>((acc, f) => {
    const dir = f.path.includes("/") ? f.path.split("/").slice(0, -1).join("/") : "root";
    if (!acc[dir]) acc[dir] = [];
    acc[dir].push(f);
    return acc;
  }, {});

  const fileExtIcon: Record<string, string> = {
    ".ts": "🟦",
    ".js": "🟨",
    ".json": "📋",
    ".md": "📝",
    ".example": "⚙️",
  };
  const getIcon = (p: string) => {
    const ext = "." + p.split(".").pop();
    return fileExtIcon[ext] ?? "📄";
  };

  const formatSize = (bytes: number) =>
    bytes < 1024 ? `${bytes}B` : `${(bytes / 1024).toFixed(1)}KB`;

  return (
    <div className="space-y-4">
      {/* Header row with zip download */}
      <div className="flex items-center justify-between">
        <span className="text-xs text-[#92a4c9]">{files.length} file(s) generated</span>
        <Button
          variant="outline"
          size="sm"
          leftIcon={<Archive className="w-3.5 h-3.5" aria-hidden="true" />}
          onClick={handleDownloadZip}
          title="Download all files as ZIP"
        >
          Download All (.zip)
        </Button>
      </div>

      {/* File groups */}
      {Object.entries(grouped).map(([dir, dirFiles]) => (
        <div key={dir} className="rounded-xl border border-[#2b3b55] overflow-hidden">
          <div className="px-4 py-2 bg-[#1e2a3d] border-b border-[#2b3b55]">
            <span className="text-xs font-mono text-[#92a4c9]">
              {dir === "root" ? "/" : `/${dir}/`}
            </span>
          </div>
          <div className="divide-y divide-[#2b3b55]">
            {dirFiles.map((f) => (
              <div
                key={f.path}
                className="flex items-center justify-between gap-3 px-4 py-2.5 hover:bg-[#1e2a3d] transition-colors"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <span className="text-base shrink-0">{getIcon(f.path)}</span>
                  <span className="text-sm font-mono text-white truncate">
                    {f.path.split("/").pop()}
                  </span>
                  <span className="text-xs text-[#3d5070] shrink-0">
                    {formatSize(f.size_bytes)}
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() => handleDownloadFile(f.path)}
                  className="shrink-0 flex items-center gap-1 text-xs text-[#5b9eff] hover:text-white transition-colors px-2 py-1 rounded hover:bg-[#2b3b55]"
                  title={`Download ${f.path}`}
                >
                  <Download className="w-3.5 h-3.5" />
                  Download
                </button>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────// Run summary card (Report tab)
// ─────────────────────────────────────────────────────────────────────────────

const statusTextColor: Record<PipelineStatus, string> = {
  pending: "text-[#fbbf24]",
  running: "text-[#22d3ee]",
  paused: "text-[#fbbf24]",
  completed: "text-[#4ade80]",
  failed: "text-[#f87171]",
  cancelled: "text-[#92a4c9]",
};

// ─────────────────────────────────────────────────────────────────────────────
// ExportButtons
// ─────────────────────────────────────────────────────────────────────────────

function ExportButtons({ runId }: { runId: string }) {
  const [htmlLoading, setHtmlLoading] = React.useState(false);
  const [docxLoading, setDocxLoading] = React.useState(false);

  const handleDownload = async (type: "html" | "docx") => {
    const url =
      type === "html"
        ? pipelineApi.getExportHtmlUrl(runId)
        : pipelineApi.getExportDocxUrl(runId);
    const setLoading = type === "html" ? setHtmlLoading : setDocxLoading;

    setLoading(true);
    try {
      const response = await fetch(url);
      if (!response.ok) {
        const detail = await response
          .text()
          .catch(() => `HTTP ${response.status}`);
        throw new Error(detail || `Server returned ${response.status}`);
      }
      const blob = await response.blob();
      const objectUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = objectUrl;
      a.download = `report-${runId.slice(0, 8)}.${type}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(objectUrl);
      toast.success(
        "Report downloaded",
        `The ${type.toUpperCase()} report has been saved to your downloads folder.`,
      );
    } catch (err) {
      toast.error(
        "Export failed",
        err instanceof Error
          ? err.message
          : `Could not download the ${type.toUpperCase()} report. Please try again.`,
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex items-center gap-2">
      <Button
        variant="outline"
        size="sm"
        loading={htmlLoading}
        disabled={htmlLoading || docxLoading}
        leftIcon={
          !htmlLoading ? (
            <FileDown className="w-3.5 h-3.5" aria-hidden="true" />
          ) : undefined
        }
        onClick={() => handleDownload("html")}
        title="Download self-contained HTML report"
      >
        HTML
      </Button>
      <Button
        variant="outline"
        size="sm"
        loading={docxLoading}
        disabled={htmlLoading || docxLoading}
        leftIcon={
          !docxLoading ? (
            <FileText className="w-3.5 h-3.5" aria-hidden="true" />
          ) : undefined
        }
        onClick={() => handleDownload("docx")}
        title="Download Microsoft Word report"
      >
        DOCX
      </Button>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// NodeResultCard
// ─────────────────────────────────────────────────────────────────────────────

interface NodeResultCardProps {
  nodeId: string;
  label: string;
  nodeType: string;
  status: string;
  outputPreview?: string | null;
}

function NodeResultCard({
  nodeId,
  label,
  nodeType,
  status,
  outputPreview,
}: NodeResultCardProps) {
  const statusColors: Record<string, string> = {
    idle: "text-zinc-500",
    running: "text-blue-400",
    completed: "text-green-400",
    failed: "text-red-400",
    skipped: "text-zinc-400",
  };
  const nodeIcons: Record<string, string> = {
    input: "📥",
    output: "📤",
    agent: "🤖",
    pure_python: "🐍",
  };

  return (
    <div className="rounded-xl border border-[#2b3b55] bg-[#18202F] p-4">
      <div className="flex items-center gap-3">
        <span className="text-xl">{nodeIcons[nodeType] ?? "🤖"}</span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-white truncate">
              {label}
            </span>
            <code className="text-[10px] font-mono text-[#3d5070] bg-[#1e2a3d] px-1.5 py-0.5 rounded border border-[#2b3b55]">
              {nodeId.slice(0, 12)}…
            </code>
          </div>
          <span
            className={cn(
              "text-xs capitalize mt-0.5 block",
              statusColors[status] ?? "text-zinc-500",
            )}
          >
            {status}
          </span>
        </div>
      </div>
      {outputPreview && (
        <PrettyOutput value={outputPreview} className="mt-3" />
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// RunSummaryCard
// ─────────────────────────────────────────────────────────────────────────────

function RunSummaryCard({ run }: { run: PipelineRunResponse }) {
  const totalAgents = run.agent_runs.length;
  const completedAgents = run.agent_runs.filter(
    (a) => a.status === "completed",
  ).length;
  const failedAgents = run.agent_runs.filter(
    (a) => a.status === "failed",
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
            <Clock
              className="w-4 h-4 text-[#92a4c9] shrink-0"
              aria-hidden="true"
            />
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
              statusTextColor[run.status],
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
        <FileText
          className="w-3.5 h-3.5 text-[#3d5070] shrink-0"
          aria-hidden="true"
        />
        <span
          className="text-xs text-[#92a4c9] truncate"
          title={run.document_filename}
        >
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

export function ResultsViewer({ run, templateNodes }: ResultsViewerProps) {
  const isV3RunCheck = !!run.node_statuses && Object.keys(run.node_statuses).length > 0;
  const [activeTab, setActiveTab] = React.useState<TabId>(isV3RunCheck ? "nodes" : "testcases");

  // ── Group agents by stage — works with any dynamic stages ─────────────────
  const agentsByStage = run.agent_runs.reduce<
    Record<string, typeof run.agent_runs>
  >((acc, agent) => {
    (acc[agent.stage] ??= []).push(agent);
    return acc;
  }, {});
  // Agents that produce viewable results (exclude ingestion which is document processing)
  const displayAgents = run.agent_runs.filter((a) => a.stage !== "ingestion");

  const isCompleted = run.status === "completed";
  const canExport = run.status === "completed" || run.status === "paused";

  // ── V3 DAG ────────────────────────────────────────────────────────────────
  const isV3Run =
    !!run.node_statuses && Object.keys(run.node_statuses).length > 0;

  // Fetch per-node outputs for the Nodes tab (V3 only)
  const { data: nodeResultsRaw } = useQuery({
    queryKey: ["nodeResults", run.id],
    queryFn: () => pipelineApi.getRunResults(run.id),
    enabled: isV3Run,
    staleTime: 5 * 60_000,
  });
  // Map: stage field = node_id for V3 results
  const nodeOutputMap = React.useMemo(() => {
    const map: Record<string, { output?: unknown; status?: string }> = {};
    if (nodeResultsRaw) {
      for (const r of nodeResultsRaw) {
        if ((r as any).stage) {
          map[(r as any).stage] = { output: (r as any).output, status: (r as any).status };
        }
      }
    }
    return map;
  }, [nodeResultsRaw]);
  const visibleTabs = isV3Run ? TABS : TABS.filter((t) => t.id !== "nodes" && t.id !== "files");

  return (
    <div className="rounded-2xl border border-[#2b3b55] bg-[#18202F] overflow-hidden">
      {/* ── Tab bar + Export buttons ──────────────────────────────────────── */}
      <div className="flex items-center justify-between border-b border-[#2b3b55] px-1">
        <div
          className="flex items-center"
          role="tablist"
          aria-label="Results sections"
        >
          {visibleTabs.map((tab) => {
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
                    : "text-[#92a4c9] border-transparent hover:text-white hover:border-[#2b3b55]",
                )}
              >
                <span className="shrink-0">{tab.icon}</span>
                <span>{tab.label}</span>
              </button>
            );
          })}
        </div>

        {/* ── Export buttons (completed or paused with partial results) ─── */}
        {canExport && (
          <div className="px-3 py-1.5">
            <ExportButtons runId={run.id} />
          </div>
        )}
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
              {displayAgents.length > 0 ? (
                displayAgents.map((agent) => (
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
              {displayAgents.length > 0 ? (
                displayAgents.map((agent) => (
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
              {displayAgents.length > 0 ? (
                displayAgents.map((agent) => (
                  <AgentOutputCard key={agent.agent_id} agent={agent} />
                ))
              ) : (
                <EmptyStage message="Report output will appear here after the reporting stage completes." />
              )}
            </div>
          )}
        </div>

        {/* ── Files (Playwright artifacts) ─────────────────────────────── */}
        <div
          id="results-panel-files"
          role="tabpanel"
          aria-labelledby="results-tab-files"
          hidden={activeTab !== "files"}
        >
          {activeTab === "files" && <FilesTab runId={run.id} />}
        </div>

        {/* ── Nodes (V3 DAG) ──────────────────────────────────────────────── */}
        <div
          id="results-panel-nodes"
          role="tabpanel"
          aria-labelledby="results-tab-nodes"
          hidden={activeTab !== "nodes"}
        >
          {activeTab === "nodes" && (
            <div className="space-y-3">
              {isV3Run && run.node_statuses ? (
                Object.entries(run.node_statuses).map(([nodeId, status]) => {
                  const tmplNode = templateNodes?.find(
                    (n) => n.node_id === nodeId,
                  );
                  const nodeData = nodeOutputMap[nodeId];
                  const rawOutput = nodeData?.output;
                  const outputPreview = rawOutput != null
                    ? (typeof rawOutput === "string" ? rawOutput : JSON.stringify(rawOutput, null, 2))
                    : null;
                  return (
                    <NodeResultCard
                      key={nodeId}
                      nodeId={nodeId}
                      label={tmplNode?.label ?? nodeId}
                      nodeType={tmplNode?.node_type ?? "agent"}
                      status={status}
                      outputPreview={outputPreview}
                    />
                  );
                })
              ) : (
                <div className="py-8 text-center text-sm text-[#3d5070]">
                  No node results available.
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default ResultsViewer;
