"use client";

import React, { useState } from "react";
import Link from "next/link";
import {
  Plus,
  Search,
  GitBranch,
  RefreshCw,
  Filter,
  Archive,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { usePipelineTemplates } from "@/hooks/usePipelineTemplates";
import { PipelineTemplateCard } from "./PipelineTemplateCard";
import { CreatePipelineDialog } from "./CreatePipelineDialog";

// ─────────────────────────────────────────────────────────────────────────────
// PipelineListPage
// ─────────────────────────────────────────────────────────────────────────────

export function PipelineListPage() {
  const [search, setSearch] = useState("");
  const [includeArchived, setIncludeArchived] = useState(false);
  const [showCreateDialog, setShowCreateDialog] = useState(false);

  const { data, isLoading, isError, refetch, isFetching } =
    usePipelineTemplates({ include_archived: includeArchived });

  const templates = data?.items ?? [];

  const filtered = templates.filter((t) => {
    if (!search.trim()) return true;
    const q = search.toLowerCase();
    return (
      t.name.toLowerCase().includes(q) ||
      t.description.toLowerCase().includes(q) ||
      t.tags.some((tag) => tag.toLowerCase().includes(q))
    );
  });

  return (
    <div className="space-y-6">
      {/* ── Header ── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-white flex items-center gap-2">
            <GitBranch className="w-5 h-5 text-[#5b9eff]" />
            Pipeline Templates
          </h1>
          <p className="text-sm text-[#92a4c9] mt-1">
            {data
              ? `${data.total} template${data.total !== 1 ? "s" : ""}`
              : "Manage your AI pipeline templates"}
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => refetch()}
            disabled={isFetching}
            className={cn(
              "flex items-center gap-1.5 h-9 px-3 rounded-lg text-sm",
              "text-[#92a4c9] hover:text-white border border-[#2b3b55]",
              "hover:bg-[#1e2a3d] transition-all duration-150",
              "disabled:opacity-50 disabled:cursor-not-allowed",
            )}
          >
            <RefreshCw
              className={cn("w-3.5 h-3.5", isFetching && "animate-spin")}
            />
            <span className="hidden sm:inline">Refresh</span>
          </button>

          <button
            type="button"
            onClick={() => setShowCreateDialog(true)}
            className={cn(
              "flex items-center gap-1.5 h-9 px-4 rounded-lg text-sm font-medium",
              "bg-[#135bec] text-white hover:bg-[#1a6aff]",
              "transition-colors duration-150",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#135bec] focus-visible:ring-offset-2 focus-visible:ring-offset-[#101622]",
            )}
          >
            <Plus className="w-4 h-4" />
            New Pipeline
          </button>
        </div>
      </div>

      {/* ── Filters ── */}
      <div className="flex flex-col sm:flex-row gap-3">
        {/* Search */}
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#3d5070]" />
          <input
            type="search"
            placeholder="Search pipelines..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className={cn(
              "w-full h-9 pl-9 pr-3 rounded-lg text-sm",
              "bg-[#1e2a3d] border border-[#2b3b55]",
              "text-white placeholder-[#3d5070]",
              "focus:outline-none focus:ring-2 focus:ring-[#135bec]/50 focus:border-[#135bec]",
              "transition-colors duration-150",
            )}
          />
        </div>

        {/* Archive toggle */}
        <button
          type="button"
          onClick={() => setIncludeArchived((v) => !v)}
          className={cn(
            "flex items-center gap-1.5 h-9 px-3 rounded-lg text-sm shrink-0",
            "border transition-all duration-150",
            includeArchived
              ? "bg-[#135bec]/15 border-[#135bec]/40 text-[#5b9eff]"
              : "border-[#2b3b55] text-[#92a4c9] hover:bg-[#1e2a3d] hover:text-white",
          )}
        >
          <Archive className="w-3.5 h-3.5" />
          <span>Archived</span>
          {includeArchived && (
            <Filter className="w-3 h-3 text-[#135bec]" />
          )}
        </button>
      </div>

      {/* ── Content ── */}
      {isLoading ? (
        <PipelineListSkeleton />
      ) : isError ? (
        <ErrorState onRetry={() => refetch()} />
      ) : filtered.length === 0 ? (
        <EmptyState
          hasSearch={!!search.trim()}
          onClearSearch={() => setSearch("")}
          onCreateNew={() => setShowCreateDialog(true)}
        />
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map((template) => (
            <PipelineTemplateCard key={template.id} template={template} />
          ))}
        </div>
      )}

      {/* ── Create dialog ── */}
      <CreatePipelineDialog
        open={showCreateDialog}
        onClose={() => setShowCreateDialog(false)}
      />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Loading skeleton
// ─────────────────────────────────────────────────────────────────────────────

function PipelineListSkeleton() {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
      {Array.from({ length: 6 }).map((_, i) => (
        <div
          key={i}
          className="h-48 rounded-xl bg-[#1e2a3d] border border-[#2b3b55] animate-pulse"
        />
      ))}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Empty state
// ─────────────────────────────────────────────────────────────────────────────

interface EmptyStateProps {
  hasSearch: boolean;
  onClearSearch: () => void;
  onCreateNew: () => void;
}

function EmptyState({ hasSearch, onClearSearch, onCreateNew }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-20 gap-4 text-center">
      <div className="w-16 h-16 rounded-2xl bg-[#1e2a3d] border border-[#2b3b55] flex items-center justify-center">
        <GitBranch className="w-8 h-8 text-[#3d5070]" />
      </div>
      {hasSearch ? (
        <>
          <p className="text-white font-medium">No pipelines match your search</p>
          <p className="text-sm text-[#92a4c9]">
            Try a different keyword or{" "}
            <button
              type="button"
              onClick={onClearSearch}
              className="text-[#5b9eff] hover:underline"
            >
              clear the search
            </button>
          </p>
        </>
      ) : (
        <>
          <p className="text-white font-medium">No pipelines yet</p>
          <p className="text-sm text-[#92a4c9]">
            Create your first pipeline template to get started
          </p>
          <button
            type="button"
            onClick={onCreateNew}
            className={cn(
              "flex items-center gap-2 h-9 px-4 rounded-lg text-sm font-medium mt-2",
              "bg-[#135bec] text-white hover:bg-[#1a6aff]",
              "transition-colors duration-150",
            )}
          >
            <Plus className="w-4 h-4" />
            New Pipeline
          </button>
        </>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Error state
// ─────────────────────────────────────────────────────────────────────────────

function ErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-20 gap-3 text-center">
      <p className="text-white font-medium">Failed to load pipelines</p>
      <p className="text-sm text-[#92a4c9]">Check your connection and try again</p>
      <button
        type="button"
        onClick={onRetry}
        className={cn(
          "flex items-center gap-2 h-9 px-4 rounded-lg text-sm font-medium mt-2",
          "border border-[#2b3b55] text-[#92a4c9] hover:text-white hover:bg-[#1e2a3d]",
          "transition-colors duration-150",
        )}
      >
        <RefreshCw className="w-3.5 h-3.5" />
        Retry
      </button>
    </div>
  );
}
