"use client";

import React from "react";
import Link from "next/link";
import { ArrowLeft, FileText, Timer, Calendar } from "lucide-react";

import { usePipelineRun } from "@/hooks/usePipeline";
import { usePipelineTemplate } from "@/hooks/usePipelineTemplates";
import { ResultsViewer } from "./ResultsViewer";
import { cn } from "@/lib/utils";
import type { PipelineStatus } from "@/types";

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

export function PipelineRunDetailPage({ templateId, runId }: PipelineRunDetailPageProps) {
  const { data: run, isLoading: runLoading, isError: runError } = usePipelineRun(runId);
  const { data: template } = usePipelineTemplate(templateId);

  const templateNodes = template?.nodes?.map((n) => ({
    node_id: n.node_id,
    label: n.label,
    node_type: n.node_type,
    enabled: n.enabled ?? true,
  }));

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
          {run && <StatusBadge status={run.status} />}
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
    </div>
  );
}
