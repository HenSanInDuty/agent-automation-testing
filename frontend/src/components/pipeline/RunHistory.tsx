"use client";

import * as React from "react";
import {
  History,
  RefreshCw,
  Trash2,
  AlertCircle,
  Clock,
  FileText,
} from "lucide-react";

import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Select";
import { ConfirmDialog } from "@/components/ui/Modal";
import { toast } from "@/components/ui/Toast";
import { usePipelineRuns, useDeletePipelineRun } from "@/hooks/usePipeline";
import { cn } from "@/lib/utils";
import type { PipelineRunResponse, PipelineStatus } from "@/types";

// ─────────────────────────────────────────────────────────────────────────────
// Props
// ─────────────────────────────────────────────────────────────────────────────

export interface RunHistoryProps {
  onSelectRun: (run: PipelineRunResponse) => void;
  selectedRunId?: string | null;
}

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

function formatRunDate(iso: string): string {
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatDuration(
  startedAt: string | null | undefined,
  completedAt: string | null | undefined
): string | null {
  if (!startedAt || !completedAt) return null;
  const ms = new Date(completedAt).getTime() - new Date(startedAt).getTime();
  if (ms < 0) return null;
  const totalSec = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSec / 60);
  const seconds = totalSec % 60;
  if (minutes === 0) return `${seconds}s`;
  return `${minutes}m ${seconds}s`;
}

// ─────────────────────────────────────────────────────────────────────────────
// Status badge
// ─────────────────────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: PipelineStatus }) {
  switch (status) {
    case "pending":
      return <Badge variant="info" size="xs">Pending</Badge>;
    case "running":
      return (
        <Badge variant="primary" size="xs" dot className="animate-pulse">
          Running
        </Badge>
      );
    case "completed":
      return <Badge variant="success" size="xs">Completed</Badge>;
    case "failed":
      return <Badge variant="danger" size="xs">Failed</Badge>;
    case "cancelled":
      return <Badge variant="default" size="xs">Cancelled</Badge>;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Loading skeleton
// ─────────────────────────────────────────────────────────────────────────────

function SkeletonRow() {
  return (
    <div
      aria-hidden="true"
      className={cn(
        "flex items-center gap-3 px-4 py-3",
        "border-b border-[#2b3b55]/60 last:border-b-0",
        "animate-pulse"
      )}
    >
      {/* Icon placeholder */}
      <div className="w-7 h-7 rounded-lg bg-[#2b3b55] shrink-0" />

      {/* Filename + date */}
      <div className="flex-1 space-y-2 min-w-0">
        <div className="h-3.5 bg-[#2b3b55] rounded-md w-3/5" />
        <div className="h-3 bg-[#2b3b55] rounded-md w-1/3" />
      </div>

      {/* Badge */}
      <div className="h-5 w-20 bg-[#2b3b55] rounded-md shrink-0" />

      {/* Delete btn */}
      <div className="w-6 h-6 bg-[#2b3b55] rounded-md shrink-0" />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Empty state
// ─────────────────────────────────────────────────────────────────────────────

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-14 px-4 text-center">
      <div
        className={cn(
          "w-11 h-11 rounded-xl",
          "bg-[#1e2a3d] border border-[#2b3b55]",
          "flex items-center justify-center"
        )}
        aria-hidden="true"
      >
        <History className="w-5 h-5 text-[#3d5070]" />
      </div>
      <div>
        <p className="text-sm font-medium text-[#92a4c9]">No pipeline runs yet</p>
        <p className="mt-1 text-xs text-[#3d5070] leading-relaxed max-w-[22rem] mx-auto">
          Upload a document and click "Run Pipeline" to start the multi-agent
          analysis. Your run history will appear here.
        </p>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Error state
// ─────────────────────────────────────────────────────────────────────────────

function ErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-12 px-4 text-center">
      <div
        className={cn(
          "w-11 h-11 rounded-xl",
          "bg-[#ef4444]/10 border border-[#ef4444]/20",
          "flex items-center justify-center"
        )}
        aria-hidden="true"
      >
        <AlertCircle className="w-5 h-5 text-[#f87171]" />
      </div>
      <div>
        <p className="text-sm font-semibold text-[#f87171]">
          Failed to load run history
        </p>
        <p className="mt-1 text-xs text-[#92a4c9]">
          Something went wrong. Check your connection and try again.
        </p>
      </div>
      <Button
        variant="secondary"
        size="sm"
        leftIcon={<RefreshCw className="w-3.5 h-3.5" aria-hidden="true" />}
        onClick={onRetry}
      >
        Retry
      </Button>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Run row
// ─────────────────────────────────────────────────────────────────────────────

interface RunRowProps {
  run: PipelineRunResponse;
  isSelected: boolean;
  onSelect: (run: PipelineRunResponse) => void;
  onDeleteRequest: (runId: string) => void;
}

function RunRow({ run, isSelected, onSelect, onDeleteRequest }: RunRowProps) {
  const duration = formatDuration(run.started_at, run.completed_at);

  return (
    <li role="listitem" className="relative">
      {/* ── Selected left accent ──────────────────────────────────────────── */}
      {isSelected && (
        <span
          className="absolute inset-y-0 left-0 w-0.5 bg-[#135bec]/60 rounded-r"
          aria-hidden="true"
        />
      )}

      {/* ── Clickable row area ────────────────────────────────────────────── */}
      <div
        role="button"
        tabIndex={0}
        onClick={() => onSelect(run)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onSelect(run);
          }
        }}
        aria-label={`View run for ${run.document_filename}, status: ${run.status}`}
        aria-pressed={isSelected}
        className={cn(
          "group flex items-center gap-3 px-4 py-3 cursor-pointer",
          "border-b border-[#2b3b55]/60 last:border-b-0",
          "transition-colors duration-150",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[#135bec]",
          isSelected
            ? "bg-[#135bec]/10"
            : "hover:bg-[#1e2a3d]/60"
        )}
      >
        {/* File icon */}
        <div
          className={cn(
            "shrink-0 w-7 h-7 rounded-lg",
            "bg-[#101622] border border-[#2b3b55]",
            "flex items-center justify-center"
          )}
          aria-hidden="true"
        >
          <FileText className="w-3.5 h-3.5 text-[#92a4c9]" />
        </div>

        {/* Filename + meta ────────────────────────────────────────────────── */}
        <div className="flex-1 min-w-0 space-y-0.5">
          <p
            className="text-sm font-medium text-white truncate leading-snug"
            title={run.document_filename}
          >
            {run.document_filename}
          </p>

          <div className="flex items-center gap-2 flex-wrap">
            <time
              dateTime={run.created_at}
              className="text-xs text-[#3d5070]"
              title={new Date(run.created_at).toLocaleString()}
            >
              {formatRunDate(run.created_at)}
            </time>

            {duration && (
              <span className="flex items-center gap-1 text-xs text-[#3d5070]">
                <Clock className="w-3 h-3" aria-hidden="true" />
                {duration}
              </span>
            )}
          </div>
        </div>

        {/* Status badge ───────────────────────────────────────────────────── */}
        <div className="shrink-0">
          <StatusBadge status={run.status} />
        </div>

        {/* Delete button ──────────────────────────────────────────────────── */}
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onDeleteRequest(run.id);
          }}
          aria-label={`Delete run for ${run.document_filename}`}
          title={`Delete run for ${run.document_filename}`}
          className={cn(
            "shrink-0 p-1.5 rounded-lg",
            "text-[#3d5070] hover:text-[#f87171] hover:bg-[#ef4444]/10",
            "transition-colors duration-150",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#135bec]",
            // Only show on row hover or when selected
            "opacity-0 group-hover:opacity-100",
            isSelected && "opacity-100"
          )}
        >
          <Trash2 className="w-3.5 h-3.5" aria-hidden="true" />
        </button>
      </div>
    </li>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// RunHistory
// ─────────────────────────────────────────────────────────────────────────────

export function RunHistory({ onSelectRun, selectedRunId }: RunHistoryProps) {
  const [deleteConfirmId, setDeleteConfirmId] = React.useState<string | null>(
    null
  );

  // ── Data ───────────────────────────────────────────────────────────────────
  const { data, isLoading, isError, refetch } = usePipelineRuns({ limit: 20 });
  const deleteMutation = useDeletePipelineRun();

  const runs: PipelineRunResponse[] = data?.items ?? [];
  const totalCount: number = data?.total ?? 0;

  // ── Handlers ───────────────────────────────────────────────────────────────

  const handleDeleteRequest = (runId: string) => {
    setDeleteConfirmId(runId);
  };

  const handleDeleteCancel = () => {
    setDeleteConfirmId(null);
  };

  const handleDeleteConfirm = async () => {
    if (!deleteConfirmId) return;
    try {
      await deleteMutation.mutateAsync(deleteConfirmId);
      toast.success("Run deleted", "The pipeline run has been removed.");
    } catch {
      toast.error(
        "Delete failed",
        "Could not delete the pipeline run. Please try again."
      );
    } finally {
      setDeleteConfirmId(null);
    }
  };

  const runToDelete = runs.find((r) => r.id === deleteConfirmId);

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <>
      <div className="rounded-2xl border border-[#2b3b55] bg-[#18202F] overflow-hidden">
        {/* ── Header ───────────────────────────────────────────────────────── */}
        <div className="flex items-center justify-between gap-3 px-4 py-3 border-b border-[#2b3b55]">
          <div className="flex items-center gap-2">
            <History
              className="w-4 h-4 text-[#92a4c9] shrink-0"
              aria-hidden="true"
            />
            <h2 className="text-sm font-semibold text-white">Run History</h2>
            {!isLoading && !isError && (
              <span className="text-xs text-[#3d5070] tabular-nums">
                ({totalCount})
              </span>
            )}
          </div>

          <Button
            variant="ghost"
            size="xs"
            leftIcon={
              <RefreshCw className="w-3 h-3" aria-hidden="true" />
            }
            onClick={() => refetch()}
            title="Refresh run history"
            aria-label="Refresh run history"
          >
            Refresh
          </Button>
        </div>

        {/* ── Body ─────────────────────────────────────────────────────────── */}
        {isLoading ? (
          // Loading — 3 skeleton rows
          <div role="status" aria-label="Loading run history…">
            <SkeletonRow />
            <SkeletonRow />
            <SkeletonRow />
            <span className="sr-only">Loading run history…</span>
          </div>
        ) : isError ? (
          // Error state
          <ErrorState onRetry={refetch} />
        ) : runs.length === 0 ? (
          // Empty state
          <EmptyState />
        ) : (
          // Run list
          <ul
            role="list"
            aria-label="Pipeline runs"
            className={cn(
              // Scrollbar styling
              "[&::-webkit-scrollbar]:w-1.5",
              "[&::-webkit-scrollbar-track]:bg-transparent",
              "[&::-webkit-scrollbar-thumb]:bg-[#2b3b55] [&::-webkit-scrollbar-thumb]:rounded-full"
            )}
          >
            {runs.map((run) => (
              <RunRow
                key={run.id}
                run={run}
                isSelected={run.id === selectedRunId}
                onSelect={onSelectRun}
                onDeleteRequest={handleDeleteRequest}
              />
            ))}
          </ul>
        )}
      </div>

      {/* ── Delete confirm dialog ─────────────────────────────────────────── */}
      <ConfirmDialog
        open={deleteConfirmId !== null}
        onClose={handleDeleteCancel}
        onConfirm={handleDeleteConfirm}
        title="Delete Pipeline Run"
        description={
          runToDelete
            ? `Are you sure you want to delete the run for "${runToDelete.document_filename}"? This action cannot be undone.`
            : "Are you sure you want to delete this pipeline run? This action cannot be undone."
        }
        confirmLabel="Delete Run"
        cancelLabel="Keep Run"
        variant="danger"
        loading={deleteMutation.isPending}
      />
    </>
  );
}

export default RunHistory;
