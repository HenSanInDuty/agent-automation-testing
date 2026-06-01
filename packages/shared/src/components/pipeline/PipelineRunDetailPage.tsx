"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, FileText, Timer, Calendar, GitBranch, X } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

import { usePipelineRun } from "../../hooks/usePipeline";
import { usePipelineTemplate } from "../../hooks/usePipelineTemplates";
import { usePipelineWebSocket } from "../../hooks/usePipelineWebSocket";
import { ResultsViewer } from "./ResultsViewer";
import { cn } from "../../lib/utils";
import { queryKeys } from "../../lib/queryClient";
import { pipelineApi } from "../../api/client";
import { toast } from "../../components/ui/Toast";
import type { PipelineStatus } from "../../types";

function formatDateTime(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    year: "numeric", month: "short", day: "2-digit",
    hour: "2-digit", minute: "2-digit",
  });
}

function formatDuration(start?: string | null, end?: string | null, secs?: number | null): string | null {
  if (secs != null) {
    const m = Math.floor(secs / 60);
    const s = Math.round(secs % 60);
    return m > 0 ? String(m) + "m " + String(s) + "s" : String(s) + "s";
  }
  if (!start || !end) return null;
  const ms = new Date(end).getTime() - new Date(start).getTime();
  const totalSec = Math.round(ms / 1000);
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  return m > 0 ? String(m) + "m " + String(s) + "s" : String(s) + "s";
}

const STATUS_STYLES: Record<PipelineStatus | string, { dot: string; text: string; label: string }> = {
  pending:   { dot: "bg-zinc-500",  text: "text-zinc-400",  label: "Pending" },
  running:   { dot: "bg-blue-500",  text: "text-blue-400",  label: "Running" },
  completed: { dot: "bg-green-500", text: "text-green-400", label: "Completed" },
  failed:    { dot: "bg-red-500",   text: "text-red-400",   label: "Failed" },
  cancelled: { dot: "bg-zinc-500",  text: "text-zinc-400",  label: "Cancelled" },
  paused:    { dot: "bg-yellow-500",text: "text-yellow-400",label: "Paused" },
};

function StatusBadge({ status }: { status: string }) {
  const s = STATUS_STYLES[status] ?? STATUS_STYLES.pending;
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-xs font-medium", s.text)}>
      <span className={cn("w-1.5 h-1.5 rounded-full", s.dot)} />
      {s.label}
    </span>
  );
}

export interface PipelineRunDetailPageProps {
  templateId: string;
  runId: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// DeriveRunModal
// ─────────────────────────────────────────────────────────────────────────────

interface DeriveRunModalProps {
  runId: string;
  templateId: string;
  nodeIds: string[];
  onClose: () => void;
  onDerived: (newRunId: string) => void;
}

function DeriveRunModal({ runId, templateId, nodeIds, onClose, onDerived }: DeriveRunModalProps) {
  const [selectedNode, setSelectedNode] = useState(nodeIds[0] ?? "");
  const [label, setLabel] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedNode) return;
    setIsSubmitting(true);
    try {
      const derived = await pipelineApi.deriveRun(runId, {
        rerun_from_node: selectedNode,
        label: label || undefined,
      });
      toast.success("Derived run created: " + derived.id.slice(0, 8));
      onDerived(derived.id);
      onClose();
    } catch {
      toast.error("Failed to create derived run");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-2xl border border-[#2b3b55] bg-[#111827] p-6 shadow-2xl">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold text-white flex items-center gap-2">
            <GitBranch className="w-4 h-4 text-blue-400" />
            Re-run from Checkpoint
          </h2>
          <button onClick={onClose} className="text-[#3d5070] hover:text-white transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-[10px] uppercase tracking-wider text-[#3d5070] mb-1.5">
              Re-run from node
            </label>
            <select
              value={selectedNode}
              onChange={(e) => setSelectedNode(e.target.value)}
              className="w-full rounded-lg border border-[#2b3b55] bg-[#18202F] text-sm text-white px-3 py-2 focus:outline-none focus:border-blue-500"
            >
              {nodeIds.map((id) => (
                <option key={id} value={id}>{id}</option>
              ))}
            </select>
            <p className="text-[10px] text-[#3d5070] mt-1">Nodes before this will be inherited from the current run.</p>
          </div>
          <div>
            <label className="block text-[10px] uppercase tracking-wider text-[#3d5070] mb-1.5">
              Label (optional)
            </label>
            <input
              type="text"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="e.g. gpt-4o retry"
              className="w-full rounded-lg border border-[#2b3b55] bg-[#18202F] text-sm text-white px-3 py-2 placeholder:text-[#3d5070] focus:outline-none focus:border-blue-500"
            />
          </div>
          <div className="flex gap-3 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 rounded-lg border border-[#2b3b55] px-4 py-2 text-sm text-[#92a4c9] hover:text-white transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!selectedNode || isSubmitting}
              className="flex-1 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 px-4 py-2 text-sm font-medium text-white transition-colors"
            >
              {isSubmitting ? "Creating…" : "Create derived run"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export function PipelineRunDetailPage({ templateId, runId }: PipelineRunDetailPageProps) {
  const qc = useQueryClient();
  const { data: run, isLoading: runLoading, isError: runError } = usePipelineRun(runId);
  const { data: template } = usePipelineTemplate(templateId);
  const [showDeriveModal, setShowDeriveModal] = useState(false);

  const isActive = run?.status === "running" || run?.status === "pending";
  const isV3 = !!(run?.node_statuses);
  const canDerive = isV3 && run?.status === "completed";

  // Connect WebSocket only while the run is active so we know when it finishes.
  const { isTerminal } = usePipelineWebSocket({
    runId,
    enabled: isActive,
  });

  // When the WebSocket signals the run is done, refetch the run detail so
  // results are displayed without requiring a manual page refresh.
  useEffect(() => {
    if (isTerminal) {
      qc.invalidateQueries({ queryKey: queryKeys.pipelineRuns.detail(runId) });
    }
  }, [isTerminal, runId, qc]);

  const templateNodes = template?.nodes?.map((n) => ({
    node_id: n.node_id,
    label: n.label,
    node_type: n.node_type,
    enabled: n.enabled ?? true,
  }));

  const nodeIds = run?.node_statuses ? Object.keys(run.node_statuses) : [];

  const duration = run
    ? formatDuration(run.started_at, run.completed_at, run.duration_seconds)
    : null;

  return (
    <div className="flex flex-col gap-6 p-6 max-w-5xl mx-auto w-full">
      <div className="flex items-center gap-3">
        <Link
          href={"/pipelines/" + templateId + "/runs"}
          className="inline-flex items-center gap-1.5 text-sm text-[#92a4c9] hover:text-white transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to run history
        </Link>
      </div>

      <div className="rounded-2xl border border-[#2b3b55] bg-[#18202F] p-5">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-lg font-semibold text-white">Run Detail</h1>
            <p className="text-xs text-[#3d5070] font-mono mt-0.5">{runId}</p>
          </div>
          <div className="flex items-center gap-3">
            {run && <StatusBadge status={run.status} />}
            {canDerive && (
              <button
                onClick={() => setShowDeriveModal(true)}
                className="inline-flex items-center gap-1.5 text-xs font-medium text-blue-400 hover:text-white border border-blue-400/30 hover:border-blue-400 px-3 py-1.5 rounded-lg transition-colors"
              >
                <GitBranch className="w-3 h-3" />
                Re-run from checkpoint
              </button>
            )}
          </div>
        </div>

        {run && (
          <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div>
              <p className="text-[10px] uppercase tracking-wider text-[#3d5070] mb-1">Template</p>
              <p className="text-xs text-[#92a4c9] font-mono">{templateId}</p>
            </div>
            <div>
              <p className="text-[10px] uppercase tracking-wider text-[#3d5070] mb-1">Document</p>
              <span className="inline-flex items-center gap-1 text-xs text-[#92a4c9]">
                <FileText className="w-3 h-3" />
                {run.document_filename || "—"}
              </span>
            </div>
            <div>
              <p className="text-[10px] uppercase tracking-wider text-[#3d5070] mb-1">Started</p>
              <span className="inline-flex items-center gap-1 text-xs text-[#92a4c9]">
                <Calendar className="w-3 h-3" />
                {formatDateTime(run.started_at ?? run.created_at)}
              </span>
            </div>
            <div>
              <p className="text-[10px] uppercase tracking-wider text-[#3d5070] mb-1">Duration</p>
              <span className="inline-flex items-center gap-1 text-xs text-[#92a4c9]">
                <Timer className="w-3 h-3" />
                {duration ?? "—"}
              </span>
            </div>
          </div>
        )}

        {run?.error_message && (
          <div className="mt-4 rounded-lg border border-red-900/40 bg-red-950/20 p-3">
            <p className="text-xs text-red-400">{run.error_message}</p>
          </div>
        )}
      </div>

      {runLoading && (
        <div className="flex items-center justify-center py-16">
          <div className="h-6 w-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
        </div>
      )}

      {runError && (
        <div className="rounded-2xl border border-red-900/40 bg-red-950/20 p-6 text-center">
          <p className="text-sm text-red-400">Failed to load run details.</p>
        </div>
      )}

      {run && !runLoading && (
        <ResultsViewer run={run} templateNodes={templateNodes} />
      )}

      {showDeriveModal && (
        <DeriveRunModal
          runId={runId}
          templateId={templateId}
          nodeIds={nodeIds}
          onClose={() => setShowDeriveModal(false)}
          onDerived={(newId) => {
            qc.invalidateQueries({ queryKey: queryKeys.pipelineRuns.lists() });
            window.location.href = `/pipelines/${templateId}/runs/${newId}`;
          }}
        />
      )}
    </div>
  );
}
