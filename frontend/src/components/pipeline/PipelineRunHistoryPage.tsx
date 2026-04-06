"use client";

import * as React from "react";
import Link from "next/link";
import {
  ArrowLeft,
  Play,
  History,
  AlertCircle,
  RefreshCw,
  ChevronLeft,
  ChevronRight,
  FileText,
  Clock,
  Hash,
  Calendar,
  Timer,
  Inbox,
  ExternalLink,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { usePipelineTemplate } from "@/hooks/usePipelineTemplates";
import { usePipelineRuns } from "@/hooks/usePipeline";
import { Button } from "@/components/ui/Button";
import type { PipelineRunResponse, PipelineStatus } from "@/types";

// ─────────────────────────────────────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────────────────────────────────────

const PAGE_SIZE = 20;

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

function formatDateTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function formatDuration(
  startedAt: string | null | undefined,
  completedAt: string | null | undefined,
  durationSeconds: number | null | undefined,
): string | null {
  if (durationSeconds != null) {
    if (durationSeconds < 60) return `${durationSeconds.toFixed(1)}s`;
    const mins = Math.floor(durationSeconds / 60);
    const secs = Math.round(durationSeconds % 60);
    return `${mins}m ${secs}s`;
  }
  if (startedAt && completedAt) {
    const ms = new Date(completedAt).getTime() - new Date(startedAt).getTime();
    if (isNaN(ms)) return null;
    const totalSec = ms / 1000;
    if (totalSec < 60) return `${totalSec.toFixed(1)}s`;
    const mins = Math.floor(totalSec / 60);
    const secs = Math.round(totalSec % 60);
    return `${mins}m ${secs}s`;
  }
  return null;
}

// ─────────────────────────────────────────────────────────────────────────────
// Status badge
// ─────────────────────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: PipelineStatus }) {
  switch (status) {
    case "running":
      return (
        <span
          className={cn(
            "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium",
            "bg-blue-500/10 text-blue-400 border border-blue-500/20",
          )}
        >
          <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse shrink-0" />
          Running
        </span>
      );
    case "pending":
      return (
        <span
          className={cn(
            "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium",
            "bg-zinc-500/10 text-zinc-400 border border-zinc-500/20",
          )}
        >
          <span className="w-1.5 h-1.5 rounded-full bg-zinc-400 shrink-0" />
          Pending
        </span>
      );
    case "paused":
      return (
        <span
          className={cn(
            "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium",
            "bg-yellow-500/10 text-yellow-400 border border-yellow-500/20",
          )}
        >
          <span className="w-1.5 h-1.5 rounded-full bg-yellow-400 shrink-0" />
          Paused
        </span>
      );
    case "completed":
      return (
        <span
          className={cn(
            "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium",
            "bg-green-500/10 text-green-400 border border-green-500/20",
          )}
        >
          <span className="w-1.5 h-1.5 rounded-full bg-green-400 shrink-0" />
          Completed
        </span>
      );
    case "failed":
      return (
        <span
          className={cn(
            "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium",
            "bg-red-500/10 text-red-400 border border-red-500/20",
          )}
        >
          <span className="w-1.5 h-1.5 rounded-full bg-red-400 shrink-0" />
          Failed
        </span>
      );
    case "cancelled":
      return (
        <span
          className={cn(
            "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium",
            "bg-zinc-500/10 text-zinc-500 border border-zinc-500/20",
          )}
        >
          <span className="w-1.5 h-1.5 rounded-full bg-zinc-500 shrink-0" />
          <span className="line-through">Cancelled</span>
        </span>
      );
    default:
      return (
        <span
          className={cn(
            "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium",
            "bg-zinc-500/10 text-zinc-400 border border-zinc-500/20",
          )}
        >
          {status}
        </span>
      );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Skeleton row
// ─────────────────────────────────────────────────────────────────────────────

function SkeletonRow() {
  return (
    <tr className="animate-pulse border-b border-[#2b3b55]">
      <td className="px-4 py-3">
        <div className="h-4 w-20 rounded bg-[#2b3b55]" />
      </td>
      <td className="px-4 py-3">
        <div className="h-4 w-36 rounded bg-[#2b3b55]" />
      </td>
      <td className="px-4 py-3">
        <div className="h-5 w-20 rounded-full bg-[#2b3b55]" />
      </td>
      <td className="px-4 py-3">
        <div className="h-4 w-32 rounded bg-[#2b3b55]" />
      </td>
      <td className="px-4 py-3">
        <div className="h-4 w-12 rounded bg-[#2b3b55]" />
      </td>
      <td className="px-4 py-3">
        <div className="h-7 w-16 rounded-md bg-[#2b3b55]" />
      </td>
    </tr>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Empty state
// ─────────────────────────────────────────────────────────────────────────────

function EmptyState({ templateId }: { templateId: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-4 py-20 px-8 text-center">
      <div className="flex items-center justify-center w-14 h-14 rounded-xl bg-[#1e2a3d] border border-[#2b3b55]">
        <Inbox className="w-7 h-7 text-[#3d5070]" aria-hidden="true" />
      </div>
      <div>
        <p className="text-sm font-semibold text-[#92a4c9]">No runs yet</p>
        <p className="mt-1 text-xs text-[#3d5070]">
          This pipeline hasn&apos;t been run yet. Start your first run to see
          history here.
        </p>
      </div>
      <Link href={`/pipelines/${templateId}/run`}>
        <Button
          variant="primary"
          size="sm"
          leftIcon={<Play className="w-3.5 h-3.5" aria-hidden="true" />}
        >
          Run Pipeline
        </Button>
      </Link>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Error state
// ─────────────────────────────────────────────────────────────────────────────

function ErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center gap-4 py-16 px-8 text-center">
      <div className="flex items-center justify-center w-12 h-12 rounded-xl bg-red-500/10 border border-red-500/25">
        <AlertCircle className="w-6 h-6 text-red-400" aria-hidden="true" />
      </div>
      <div>
        <p className="text-sm font-semibold text-white">
          Failed to load run history
        </p>
        <p className="mt-1 text-xs text-[#92a4c9]">
          There was an error fetching the pipeline runs. Please try again.
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
// Template header skeleton
// ─────────────────────────────────────────────────────────────────────────────

function TemplateHeaderSkeleton() {
  return (
    <div className="flex items-start gap-3 animate-pulse">
      <div className="w-8 h-8 rounded-lg bg-[#2b3b55] shrink-0 mt-0.5" />
      <div className="flex flex-col gap-2">
        <div className="h-5 w-48 rounded bg-[#2b3b55]" />
        <div className="h-3 w-32 rounded bg-[#2b3b55]" />
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Run row
// ─────────────────────────────────────────────────────────────────────────────

interface RunRowProps {
  run: PipelineRunResponse;
}

function RunRow({ run }: RunRowProps) {
  const duration = formatDuration(
    run.started_at,
    run.completed_at,
    run.duration_seconds,
  );
  const runId = run.id ?? run.run_id ?? "";
  const shortId = runId.slice(0, 8);

  return (
    <tr
      className={cn(
        "group border-b border-[#2b3b55] transition-colors duration-100",
        "hover:bg-[#1e2a3d]",
      )}
    >
      {/* Run ID */}
      <td className="px-4 py-3">
        <span
          className="font-mono text-xs text-[#92a4c9] group-hover:text-white transition-colors"
          title={runId}
        >
          {shortId}…
        </span>
      </td>

      {/* Document */}
      <td className="px-4 py-3 max-w-[200px]">
        {run.document_filename ? (
          <span
            className="inline-flex items-center gap-1.5 text-xs text-[#92a4c9] truncate"
            title={run.document_filename}
          >
            <FileText
              className="w-3.5 h-3.5 shrink-0 text-[#3d5070]"
              aria-hidden="true"
            />
            <span className="truncate">{run.document_filename}</span>
          </span>
        ) : (
          <span className="text-xs text-[#3d5070] italic">No document</span>
        )}
      </td>

      {/* Status */}
      <td className="px-4 py-3">
        <StatusBadge status={run.status} />
      </td>

      {/* Created at */}
      <td className="px-4 py-3">
        <span className="inline-flex items-center gap-1.5 text-xs text-[#92a4c9]">
          <Calendar
            className="w-3.5 h-3.5 shrink-0 text-[#3d5070]"
            aria-hidden="true"
          />
          {formatDateTime(run.created_at)}
        </span>
      </td>

      {/* Duration */}
      <td className="px-4 py-3">
        {duration ? (
          <span className="inline-flex items-center gap-1.5 text-xs text-[#92a4c9]">
            <Timer
              className="w-3.5 h-3.5 shrink-0 text-[#3d5070]"
              aria-hidden="true"
            />
            {duration}
          </span>
        ) : run.status === "running" || run.status === "pending" ? (
          <span className="inline-flex items-center gap-1 text-xs text-blue-400">
            <Clock className="w-3.5 h-3.5 animate-spin" aria-hidden="true" />
            In progress
          </span>
        ) : (
          <span className="text-xs text-[#3d5070]">—</span>
        )}
      </td>

      {/* Error snippet (shown only on failed) */}
      <td className="px-4 py-3 max-w-[160px] hidden xl:table-cell">
        {run.error_message ? (
          <span
            className="text-xs text-red-400 truncate block"
            title={run.error_message}
          >
            {run.error_message.slice(0, 60)}
            {run.error_message.length > 60 ? "…" : ""}
          </span>
        ) : (
          <span className="text-xs text-[#3d5070]">—</span>
        )}
      </td>

      {/* Actions */}
      <td className="px-4 py-3">
        <div className="flex items-center gap-1.5">
          <Link
            href={`/pipelines/${run.template_id ?? ""}/run`}
            title="View run"
          >
            <Button
              variant="ghost"
              size="xs"
              rightIcon={
                <ExternalLink className="w-3 h-3" aria-hidden="true" />
              }
              className="opacity-60 group-hover:opacity-100 transition-opacity"
            >
              Details
            </Button>
          </Link>
        </div>
      </td>
    </tr>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Pagination controls
// ─────────────────────────────────────────────────────────────────────────────

interface PaginationProps {
  page: number;
  totalPages: number;
  total: number;
  pageSize: number;
  onPrev: () => void;
  onNext: () => void;
}

function Pagination({
  page,
  totalPages,
  total,
  pageSize,
  onPrev,
  onNext,
}: PaginationProps) {
  const start = (page - 1) * pageSize + 1;
  const end = Math.min(page * pageSize, total);

  return (
    <div className="flex items-center justify-between px-4 py-3 border-t border-[#2b3b55]">
      <p className="text-xs text-[#3d5070]">
        Showing{" "}
        <span className="text-[#92a4c9] font-medium">
          {start}–{end}
        </span>{" "}
        of <span className="text-[#92a4c9] font-medium">{total}</span> runs
      </p>
      <div className="flex items-center gap-2">
        <Button
          variant="secondary"
          size="sm"
          leftIcon={<ChevronLeft className="w-3.5 h-3.5" aria-hidden="true" />}
          onClick={onPrev}
          disabled={page <= 1}
          aria-label="Previous page"
        >
          Prev
        </Button>
        <span className="text-xs text-[#92a4c9] tabular-nums">
          {page} / {totalPages}
        </span>
        <Button
          variant="secondary"
          size="sm"
          rightIcon={
            <ChevronRight className="w-3.5 h-3.5" aria-hidden="true" />
          }
          onClick={onNext}
          disabled={page >= totalPages}
          aria-label="Next page"
        >
          Next
        </Button>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Main component
// ─────────────────────────────────────────────────────────────────────────────

export interface PipelineRunHistoryPageProps {
  templateId: string;
}

export function PipelineRunHistoryPage({
  templateId,
}: PipelineRunHistoryPageProps) {
  const [page, setPage] = React.useState(1);

  // ── Template info (for header) ─────────────────────────────────────────────
  const {
    data: template,
    isLoading: templateLoading,
  } = usePipelineTemplate(templateId);

  // ── Runs list ──────────────────────────────────────────────────────────────
  const {
    data: runsData,
    isLoading: runsLoading,
    isError: runsError,
    refetch,
  } = usePipelineRuns({
    template_id: templateId,
    page,
    page_size: PAGE_SIZE,
  });

  const runs: PipelineRunResponse[] = runsData?.items ?? [];
  const total = runsData?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const handlePrev = () => setPage((p) => Math.max(1, p - 1));
  const handleNext = () => setPage((p) => Math.min(totalPages, p + 1));

  // ─────────────────────────────────────────────────────────────────────────
  // Render
  // ─────────────────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col gap-6">
      {/* ── Page header ──────────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          {/* Back to run page */}
          <Link
            href={`/pipelines/${templateId}/run`}
            className={cn(
              "inline-flex items-center justify-center w-8 h-8 rounded-lg shrink-0 mt-0.5",
              "border border-[#2b3b55] bg-[#18202F] text-[#92a4c9]",
              "hover:border-[#3d5070] hover:text-white transition-colors duration-150",
            )}
            title="Back to run page"
          >
            <ArrowLeft className="w-4 h-4" aria-hidden="true" />
          </Link>

          {/* Title */}
          {templateLoading ? (
            <TemplateHeaderSkeleton />
          ) : (
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-lg font-bold text-white leading-tight">
                  {template?.name ?? templateId}
                </h1>
                {total > 0 && (
                  <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-[#2b3b55] text-[#92a4c9]">
                    {total}
                  </span>
                )}
              </div>
              <div className="mt-1 flex items-center gap-1.5 text-sm text-[#92a4c9]">
                <History className="w-3.5 h-3.5 text-[#3d5070]" />
                Run History
              </div>
            </div>
          )}
        </div>

        {/* Action: go to run page */}
        <Link href={`/pipelines/${templateId}/run`} className="shrink-0">
          <Button
            variant="primary"
            size="sm"
            leftIcon={<Play className="w-3.5 h-3.5" aria-hidden="true" />}
          >
            New Run
          </Button>
        </Link>
      </div>

      {/* ── Runs table card ───────────────────────────────────────────────── */}
      <div className="rounded-xl border border-[#2b3b55] bg-[#18202F] overflow-hidden">
        {/* Table header row */}
        <div className="border-b border-[#2b3b55] px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Hash className="w-4 h-4 text-[#3d5070]" aria-hidden="true" />
            <span className="text-sm font-semibold text-white">Runs</span>
          </div>
          <button
            type="button"
            onClick={() => refetch()}
            className={cn(
              "inline-flex items-center gap-1.5 text-xs text-[#3d5070] hover:text-[#92a4c9]",
              "transition-colors duration-150 rounded-md px-2 py-1",
              "hover:bg-[#1e2a3d]",
            )}
            aria-label="Refresh run list"
          >
            <RefreshCw className="w-3.5 h-3.5" aria-hidden="true" />
            Refresh
          </button>
        </div>

        {/* Error state */}
        {runsError && !runsLoading && (
          <ErrorState onRetry={() => refetch()} />
        )}

        {/* Table */}
        {!runsError && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[700px] border-collapse text-left">
              <thead>
                <tr className="border-b border-[#2b3b55] bg-[#101622]/60">
                  <th className="px-4 py-2.5 text-xs font-semibold text-[#3d5070] uppercase tracking-wider whitespace-nowrap">
                    Run ID
                  </th>
                  <th className="px-4 py-2.5 text-xs font-semibold text-[#3d5070] uppercase tracking-wider whitespace-nowrap">
                    Document
                  </th>
                  <th className="px-4 py-2.5 text-xs font-semibold text-[#3d5070] uppercase tracking-wider whitespace-nowrap">
                    Status
                  </th>
                  <th className="px-4 py-2.5 text-xs font-semibold text-[#3d5070] uppercase tracking-wider whitespace-nowrap">
                    Created At
                  </th>
                  <th className="px-4 py-2.5 text-xs font-semibold text-[#3d5070] uppercase tracking-wider whitespace-nowrap">
                    Duration
                  </th>
                  <th className="px-4 py-2.5 text-xs font-semibold text-[#3d5070] uppercase tracking-wider whitespace-nowrap hidden xl:table-cell">
                    Error
                  </th>
                  <th className="px-4 py-2.5 text-xs font-semibold text-[#3d5070] uppercase tracking-wider whitespace-nowrap">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody>
                {/* Loading skeletons */}
                {runsLoading &&
                  Array.from({ length: 6 }).map((_, i) => (
                    <SkeletonRow key={i} />
                  ))}

                {/* Actual rows */}
                {!runsLoading &&
                  runs.map((run) => <RunRow key={run.id ?? run.run_id} run={run} />)}
              </tbody>
            </table>

            {/* Empty state (inside table area) */}
            {!runsLoading && !runsError && runs.length === 0 && (
              <EmptyState templateId={templateId} />
            )}
          </div>
        )}

        {/* Pagination */}
        {!runsLoading && !runsError && total > PAGE_SIZE && (
          <Pagination
            page={page}
            totalPages={totalPages}
            total={total}
            pageSize={PAGE_SIZE}
            onPrev={handlePrev}
            onNext={handleNext}
          />
        )}
      </div>
    </div>
  );
}

export default PipelineRunHistoryPage;
