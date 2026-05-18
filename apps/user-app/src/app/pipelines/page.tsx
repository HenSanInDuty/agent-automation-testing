"use client";

import * as React from "react";
import Link from "next/link";
import { Play, History, Network, Clock, Layers } from "lucide-react";

import { usePipelineTemplates } from "@auto-at/shared";
import type { PipelineTemplateListItem } from "@auto-at/shared";


// ─────────────────────────────────────────────────────────────────────────────
// Status badge
// ─────────────────────────────────────────────────────────────────────────────

function LastRunBadge({ status }: { status?: string }) {
  if (!status) return null;

  const colors: Record<string, string> = {
    completed: "bg-emerald-500/15 text-emerald-400 border-emerald-500/20",
    failed: "bg-red-500/15 text-red-400 border-red-500/20",
    running: "bg-blue-500/15 text-blue-400 border-blue-500/20",
    cancelled: "bg-orange-500/15 text-orange-400 border-orange-500/20",
    pending: "bg-zinc-500/15 text-zinc-400 border-zinc-500/20",
  };

  const colorClass = colors[status] ?? "bg-[#2b3b55] text-[#92a4c9] border-[#3d5070]";

  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium border ${colorClass}`}
    >
      {status}
    </span>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Pipeline card
// ─────────────────────────────────────────────────────────────────────────────

function PipelineCard({ template }: { template: PipelineTemplateListItem }) {
  const id = template.template_id;

  return (
    <div className="rounded-xl border border-[#2b3b55] bg-[#18202F] p-5 flex flex-col gap-4 hover:border-[#3d5070] transition-colors duration-150">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3 flex-1 min-w-0">
          <div className="flex items-center justify-center w-9 h-9 rounded-lg bg-[#1e2a3d] border border-[#2b3b55] shrink-0 mt-0.5">
            <Network className="w-4 h-4 text-[#92a4c9]" aria-hidden="true" />
          </div>
          <div className="min-w-0">
            <h2 className="text-sm font-semibold text-white leading-tight truncate">
              {template.name}
            </h2>
            {template.description && (
              <p className="mt-0.5 text-xs text-[#92a4c9] line-clamp-2">
                {template.description}
              </p>
            )}
          </div>
        </div>
        <LastRunBadge status={template.last_run_status ?? undefined} />
      </div>

      {/* Stats */}
      <div className="flex items-center gap-4">
        <span className="inline-flex items-center gap-1 text-xs text-[#3d5070]">
          <Layers className="w-3.5 h-3.5" />
          {template.node_count ?? 0} nodes
        </span>
        {template.version && (
          <span className="inline-flex items-center gap-1 text-xs text-[#3d5070]">
            <Clock className="w-3.5 h-3.5" />
            v{template.version}
          </span>
        )}
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2 pt-1 border-t border-[#2b3b55]">
        <Link href={`/pipelines/${id}/run`} className="flex-1">
          <button
            type="button"
            className="w-full inline-flex items-center justify-center gap-1.5 h-8 px-3 rounded-lg text-xs font-medium bg-[#135bec] hover:bg-[#1a6df0] text-white transition-colors duration-150"
          >
            <Play className="w-3.5 h-3.5" aria-hidden="true" />
            Run
          </button>
        </Link>
        <Link href={`/pipelines/${id}/runs`}>
          <button
            type="button"
            className="inline-flex items-center justify-center gap-1.5 h-8 px-3 rounded-lg text-xs font-medium bg-[#1e2a3d] hover:bg-[#2b3b55] text-[#92a4c9] hover:text-white border border-[#2b3b55] transition-colors duration-150"
          >
            <History className="w-3.5 h-3.5" aria-hidden="true" />
            History
          </button>
        </Link>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Skeleton card
// ─────────────────────────────────────────────────────────────────────────────

function SkeletonCard() {
  return (
    <div className="rounded-xl border border-[#2b3b55] bg-[#18202F] p-5 flex flex-col gap-4 animate-pulse">
      <div className="flex items-start gap-3">
        <div className="w-9 h-9 rounded-lg bg-[#2b3b55] shrink-0" />
        <div className="flex-1 flex flex-col gap-2">
          <div className="h-4 w-3/4 rounded bg-[#2b3b55]" />
          <div className="h-3 w-full rounded bg-[#2b3b55]" />
          <div className="h-3 w-1/2 rounded bg-[#2b3b55]" />
        </div>
      </div>
      <div className="h-3 w-1/3 rounded bg-[#2b3b55]" />
      <div className="flex gap-2 pt-1 border-t border-[#2b3b55]">
        <div className="flex-1 h-8 rounded-lg bg-[#2b3b55]" />
        <div className="h-8 w-20 rounded-lg bg-[#2b3b55]" />
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Page
// ─────────────────────────────────────────────────────────────────────────────

export default function PipelinesPage() {
  const { data, isLoading, isError, refetch } = usePipelineTemplates({
    include_archived: false,
  });

  const templates = data?.items ?? [];

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      {/* Page header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-white">Pipelines</h1>
        <p className="mt-1 text-sm text-[#92a4c9]">
          Select a pipeline to run or view its history.
        </p>
      </div>

      {/* Error state */}
      {isError && (
        <div className="flex flex-col items-center justify-center gap-4 py-20 text-center">
          <p className="text-sm text-red-400">Failed to load pipelines.</p>
          <button
            type="button"
            onClick={() => refetch()}
            className="inline-flex items-center gap-1.5 text-xs text-[#92a4c9] hover:text-white border border-[#2b3b55] rounded-lg px-3 h-8 transition-colors"
          >
            Retry
          </button>
        </div>
      )}

      {/* Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {isLoading
          ? Array.from({ length: 6 }).map((_, i) => <SkeletonCard key={i} />)
          : templates.map((t: PipelineTemplateListItem) => (
              <PipelineCard key={t.template_id} template={t} />
            ))}
      </div>

      {/* Empty state */}
      {!isLoading && !isError && templates.length === 0 && (
        <div className="flex flex-col items-center justify-center gap-3 py-20 text-center">
          <Network className="w-10 h-10 text-[#3d5070]" />
          <p className="text-sm text-[#92a4c9]">No pipelines available.</p>
        </div>
      )}
    </div>
  );
}
