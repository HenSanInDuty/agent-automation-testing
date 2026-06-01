"use client";

import Link from "next/link";
import {
  Play,
  History,
  Network,
  Clock,
  Layers,
  Workflow,
  Sparkles,
  CheckCircle2,
  XCircle,
  Loader2,
  Tag,
  AlertCircle,
  RefreshCw,
  ArrowUpRight,
} from "lucide-react";

import { usePipelineTemplates } from "@auto-at/shared";
import type { PipelineTemplateListItem } from "@auto-at/shared";

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

function cn(...args: Array<string | false | null | undefined>): string {
  return args.filter(Boolean).join(" ");
}

function formatRelativeTime(iso?: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  const diffMs = Date.now() - d.getTime();
  const diffSec = Math.round(diffMs / 1000);
  if (diffSec < 60) return "just now";
  const diffMin = Math.round(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffH = Math.round(diffMin / 60);
  if (diffH < 24) return `${diffH}h ago`;
  const diffD = Math.round(diffH / 24);
  if (diffD < 30) return `${diffD}d ago`;
  const diffMo = Math.round(diffD / 30);
  if (diffMo < 12) return `${diffMo}mo ago`;
  return `${Math.round(diffMo / 12)}y ago`;
}

// ─────────────────────────────────────────────────────────────────────────────
// Status badge
// ─────────────────────────────────────────────────────────────────────────────

function statusStyle(status?: string) {
  switch (status) {
    case "completed":
      return {
        cls: "bg-emerald-500/10 text-emerald-300 border-emerald-500/25",
        Icon: CheckCircle2,
      };
    case "failed":
      return {
        cls: "bg-red-500/10 text-red-300 border-red-500/25",
        Icon: XCircle,
      };
    case "running":
    case "pending":
      return {
        cls: "bg-blue-500/10 text-blue-300 border-blue-500/25",
        Icon: Loader2,
      };
    case "cancelled":
      return {
        cls: "bg-orange-500/10 text-orange-300 border-orange-500/25",
        Icon: XCircle,
      };
    default:
      return {
        cls: "bg-[#1e2a3d] text-[#92a4c9] border-[#22304a]",
        Icon: Clock,
      };
  }
}

function LastRunBadge({ status }: { status?: string }) {
  if (!status) return null;
  const { cls, Icon } = statusStyle(status);
  const isRunning = status === "running" || status === "pending";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold border uppercase tracking-wide",
        cls,
      )}
    >
      <Icon className={cn("w-2.5 h-2.5", isRunning && "animate-spin")} />
      {status}
    </span>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Pipeline card
// ─────────────────────────────────────────────────────────────────────────────

function PipelineCard({ template }: { template: PipelineTemplateListItem }) {
  const id = template.template_id;
  const lastRun = formatRelativeTime(template.last_run_at ?? null);
  const isBuiltin = template.is_builtin;

  return (
    <article
      className={cn(
        "group relative flex flex-col rounded-2xl overflow-hidden",
        "border border-[#22304a] bg-[#141c2c]/80 backdrop-blur-sm",
        "transition-all duration-200",
        "hover:border-[#3d5070] hover:bg-[#172033] hover:-translate-y-0.5",
        "hover:shadow-[0_8px_24px_-8px_rgba(19,91,236,0.25)]",
      )}
    >
      {/* Gradient accent strip on top, brighter on hover */}
      <div
        aria-hidden="true"
        className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-[#3d5070] to-transparent opacity-60 group-hover:opacity-100 group-hover:via-[#5b9eff] transition-opacity duration-300"
      />

      {/* Body */}
      <div className="flex flex-col gap-4 p-5 flex-1">
        {/* Header row */}
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3 min-w-0 flex-1">
            {/* Icon container */}
            <div
              className={cn(
                "relative flex items-center justify-center w-11 h-11 rounded-xl shrink-0",
                "bg-gradient-to-br from-[#1e2a3d] to-[#141c2c]",
                "border border-[#22304a] group-hover:border-[#3d5070]",
                "transition-all duration-200",
              )}
            >
              <Workflow
                className="w-5 h-5 text-[#92a4c9] group-hover:text-[#5b9eff] transition-colors"
                aria-hidden="true"
              />
              {isBuiltin && (
                <span
                  className="absolute -top-1 -right-1 flex items-center justify-center w-4 h-4 rounded-full bg-[#135bec] border-2 border-[#141c2c]"
                  title="Built-in"
                >
                  <Sparkles className="w-2 h-2 text-white" />
                </span>
              )}
            </div>

            <div className="min-w-0 flex-1">
              <h2
                className="text-sm font-semibold text-white leading-snug line-clamp-1"
                title={template.name}
              >
                {template.name}
              </h2>
              {template.description && (
                <p
                  className="mt-1 text-xs text-[#92a4c9] line-clamp-2 leading-relaxed"
                  title={template.description}
                >
                  {template.description}
                </p>
              )}
            </div>
          </div>

          <LastRunBadge status={template.last_run_status ?? undefined} />
        </div>

        {/* Tags */}
        {template.tags && template.tags.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {template.tags.slice(0, 4).map((tag) => (
              <span
                key={tag}
                className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-[#1e2a3d] border border-[#22304a] text-[#7a8baa]"
              >
                <Tag className="w-2.5 h-2.5" />
                {tag}
              </span>
            ))}
            {template.tags.length > 4 && (
              <span className="text-[10px] text-[#5e7196]">
                +{template.tags.length - 4}
              </span>
            )}
          </div>
        )}

        {/* Meta */}
        <div className="flex items-center flex-wrap gap-x-3 gap-y-1 text-[11px] text-[#7a8baa] mt-auto">
          <span className="inline-flex items-center gap-1">
            <Layers className="w-3 h-3" />
            {template.node_count ?? 0} {template.node_count === 1 ? "node" : "nodes"}
          </span>
          {typeof template.version === "number" && (
            <span className="inline-flex items-center gap-1">
              <Clock className="w-3 h-3" />v{template.version}
            </span>
          )}
          {lastRun && (
            <span className="inline-flex items-center gap-1 ml-auto text-[#5e7196]">
              Last run {lastRun}
            </span>
          )}
        </div>
      </div>

      {/* Footer actions */}
      <div className="flex items-stretch gap-px bg-[#22304a]/60 border-t border-[#22304a]">
        <Link
          href={`/pipelines/${id}/run`}
          className={cn(
            "flex-1 inline-flex items-center justify-center gap-1.5 h-10 px-3 text-xs font-semibold",
            "bg-[#135bec] hover:bg-[#1a6aff] text-white",
            "transition-colors duration-150",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-white/30",
          )}
        >
          <Play className="w-3.5 h-3.5 fill-current" aria-hidden="true" />
          Run pipeline
          <ArrowUpRight className="w-3.5 h-3.5 opacity-0 -translate-x-1 group-hover:opacity-100 group-hover:translate-x-0 transition-all" />
        </Link>
        <Link
          href={`/pipelines/${id}/runs`}
          className={cn(
            "inline-flex items-center justify-center gap-1.5 h-10 px-4 text-xs font-medium",
            "bg-[#141c2c] hover:bg-[#1e2a3d] text-[#92a4c9] hover:text-white",
            "transition-colors duration-150",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[#135bec]",
          )}
        >
          <History className="w-3.5 h-3.5" aria-hidden="true" />
          History
        </Link>
      </div>
    </article>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Skeleton card
// ─────────────────────────────────────────────────────────────────────────────

function SkeletonCard() {
  return (
    <div className="rounded-2xl border border-[#22304a] bg-[#141c2c]/60 overflow-hidden animate-pulse">
      <div className="p-5 flex flex-col gap-4">
        <div className="flex items-start gap-3">
          <div className="w-11 h-11 rounded-xl bg-[#1e2a3d] shrink-0" />
          <div className="flex-1 flex flex-col gap-2">
            <div className="h-4 w-3/4 rounded bg-[#1e2a3d]" />
            <div className="h-3 w-full rounded bg-[#1e2a3d]" />
            <div className="h-3 w-2/3 rounded bg-[#1e2a3d]" />
          </div>
        </div>
        <div className="h-3 w-2/5 rounded bg-[#1e2a3d]" />
      </div>
      <div className="h-10 bg-[#1e2a3d]/60 border-t border-[#22304a]" />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Hero header
// ─────────────────────────────────────────────────────────────────────────────

function HeroHeader({ total }: { total: number }) {
  return (
    <header
      className={cn(
        "relative overflow-hidden rounded-2xl border border-[#22304a]",
        "bg-gradient-to-br from-[#141c2c] via-[#141c2c] to-[#101725]",
        "px-6 py-6 mb-6",
      )}
    >
      {/* Decorative top hairline */}
      <div
        aria-hidden="true"
        className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-[#3d5070] to-transparent"
      />
      {/* Decorative glow */}
      <div
        aria-hidden="true"
        className="absolute -top-24 -right-20 w-72 h-72 rounded-full bg-[#135bec]/10 blur-3xl pointer-events-none"
      />

      <div className="relative flex flex-col lg:flex-row lg:items-center justify-between gap-4">
        <div className="flex items-start gap-4">
          <div className="flex items-center justify-center w-12 h-12 rounded-2xl bg-gradient-to-br from-[#135bec]/20 to-[#135bec]/5 border border-[#135bec]/30 shrink-0">
            <Network className="w-6 h-6 text-[#5b9eff]" aria-hidden="true" />
          </div>
          <div>
            <p className="text-[11px] font-medium uppercase tracking-wider text-[#5e7196]">
              Workflow Library
            </p>
            <div className="mt-1 flex items-center gap-3">
              <h1 className="text-2xl font-bold text-white leading-tight">
                Pipelines
              </h1>
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-mono font-semibold bg-[#1e2a3d] border border-[#22304a] text-[#92a4c9]">
                {total}
              </span>
            </div>
            <p className="mt-1.5 text-sm text-[#92a4c9] max-w-xl">
              Pick a pipeline to run an automated test workflow and see the
              results right here.
            </p>
          </div>
        </div>
      </div>
    </header>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Empty state
// ─────────────────────────────────────────────────────────────────────────────

function EmptyState() {
  return (
    <div className="relative overflow-hidden rounded-2xl border border-dashed border-[#22304a] bg-[#141c2c]/40 py-20 px-6 text-center">
      <div
        aria-hidden="true"
        className="absolute inset-0 opacity-[0.15] pointer-events-none"
        style={{
          backgroundImage:
            "radial-gradient(circle at 50% 30%, #135bec 0%, transparent 55%)",
        }}
      />
      <div className="relative flex flex-col items-center gap-4">
        <div className="flex items-center justify-center w-14 h-14 rounded-2xl bg-gradient-to-br from-[#1e2a3d] to-[#141c2c] border border-[#22304a]">
          <Network className="w-7 h-7 text-[#92a4c9]" aria-hidden="true" />
        </div>
        <div className="max-w-md">
          <p className="text-base font-semibold text-white">No pipelines yet</p>
          <p className="mt-1.5 text-sm text-[#92a4c9]">
            There are no available pipelines for your account yet.
          </p>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Error state
// ─────────────────────────────────────────────────────────────────────────────

function ErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="rounded-2xl border border-red-500/25 bg-red-500/[0.04] py-12 px-6 text-center">
      <div className="flex flex-col items-center gap-3">
        <div className="flex items-center justify-center w-12 h-12 rounded-xl bg-red-500/10 border border-red-500/25">
          <AlertCircle className="w-6 h-6 text-red-400" aria-hidden="true" />
        </div>
        <div>
          <p className="text-sm font-semibold text-white">
            Failed to load pipelines
          </p>
          <p className="mt-1 text-xs text-[#92a4c9]">
            Check your network connection or try again.
          </p>
        </div>
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex items-center gap-1.5 h-8 px-3 rounded-lg text-xs font-medium bg-[#1e2a3d] hover:bg-[#263450] text-[#92a4c9] hover:text-white border border-[#22304a] transition-colors"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          Retry
        </button>
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
    <div className="max-w-7xl mx-auto px-4 sm:px-6 py-8">
      <HeroHeader total={templates.length} />

      {isError && <ErrorState onRetry={() => refetch()} />}

      {!isError && (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {isLoading
              ? Array.from({ length: 6 }).map((_, i) => <SkeletonCard key={i} />)
              : templates.map((t: PipelineTemplateListItem) => (
                  <PipelineCard key={t.template_id} template={t} />
                ))}
          </div>

          {!isLoading && templates.length === 0 && (
            <div className="mt-4">
              <EmptyState />
            </div>
          )}
        </>
      )}
    </div>
  );
}
