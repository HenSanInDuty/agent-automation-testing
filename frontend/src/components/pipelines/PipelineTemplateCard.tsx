"use client";

import React, { useState } from "react";
import Link from "next/link";
import {
  GitBranch,
  MoreVertical,
  Copy,
  Archive,
  Trash2,
  Play,
  History,
  Lock,
  Clock,
  Network,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { PipelineTemplateListItem } from "@/types";
import {
  useCloneTemplate,
  useDeleteTemplate,
  useArchiveTemplate,
} from "@/hooks/usePipelineTemplates";
import { toast } from "@/components/ui/Toast";

// ─────────────────────────────────────────────────────────────────────────────
// Status badge
// ─────────────────────────────────────────────────────────────────────────────

function StatusBadge({ lastRunStatus }: { lastRunStatus?: string }) {
  if (!lastRunStatus) return null;

  const colors: Record<string, string> = {
    completed: "bg-emerald-500/15 text-emerald-400 border-emerald-500/20",
    failed: "bg-red-500/15 text-red-400 border-red-500/20",
    running: "bg-[#135bec]/15 text-[#5b9eff] border-[#135bec]/20",
    cancelled: "bg-orange-500/15 text-orange-400 border-orange-500/20",
  };

  const colorClass =
    colors[lastRunStatus] ?? "bg-[#2b3b55] text-[#92a4c9] border-[#3d5070]";

  return (
    <span
      className={cn(
        "inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium border",
        colorClass,
      )}
    >
      {lastRunStatus}
    </span>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Dropdown menu
// ─────────────────────────────────────────────────────────────────────────────

interface CardMenuProps {
  template: PipelineTemplateListItem;
  onClose: () => void;
}

function CardMenu({ template, onClose }: CardMenuProps) {
  const cloneMutation = useCloneTemplate();
  const deleteMutation = useDeleteTemplate();
  const archiveMutation = useArchiveTemplate();

  const handleClone = async () => {
    try {
      const cloned = await cloneMutation.mutateAsync({
        templateId: template.template_id,
      });
      toast.success(
        "Pipeline cloned",
        `"${cloned.name}" has been created as a copy.`,
      );
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? (err instanceof Error ? err.message : "Clone failed.");
      toast.error("Clone failed", detail);
    } finally {
      onClose();
    }
  };

  const handleArchive = async () => {
    const isArchived = template.is_archived;
    try {
      await archiveMutation.mutateAsync(template.template_id);
      toast.success(
        isArchived ? "Pipeline unarchived" : "Pipeline archived",
        `"${template.name}" has been ${isArchived ? "restored" : "archived"}.`,
      );
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ??
        (err instanceof Error ? err.message : "Operation failed.");
      toast.error(isArchived ? "Unarchive failed" : "Archive failed", detail);
    } finally {
      onClose();
    }
  };

  const handleDelete = async () => {
    if (!confirm(`Delete "${template.name}"? This cannot be undone.`)) {
      onClose();
      return;
    }
    try {
      await deleteMutation.mutateAsync(template.template_id);
      toast.success(
        "Pipeline deleted",
        `"${template.name}" has been permanently removed.`,
      );
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? (err instanceof Error ? err.message : "Delete failed.");
      toast.error("Delete failed", detail);
    } finally {
      onClose();
    }
  };

  return (
    <div
      className={cn(
        "absolute right-0 top-full mt-1 z-50 w-44",
        "bg-[#18202F] border border-[#2b3b55] rounded-xl shadow-xl",
        "py-1 overflow-hidden",
      )}
    >
      <button
        type="button"
        onClick={handleClone}
        disabled={cloneMutation.isPending}
        className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-[#92a4c9] hover:text-white hover:bg-[#1e2a3d] transition-colors disabled:opacity-50"
      >
        <Copy className="w-3.5 h-3.5" />
        Clone
      </button>

      {!template.is_builtin && (
        <>
          <button
            type="button"
            onClick={handleArchive}
            disabled={archiveMutation.isPending}
            className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-[#92a4c9] hover:text-white hover:bg-[#1e2a3d] transition-colors disabled:opacity-50"
          >
            <Archive className="w-3.5 h-3.5" />
            {template.is_archived ? "Unarchive" : "Archive"}
          </button>

          <div className="h-px bg-[#2b3b55] my-1" />

          <button
            type="button"
            onClick={handleDelete}
            disabled={deleteMutation.isPending}
            className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-red-400 hover:text-red-300 hover:bg-[#1e2a3d] transition-colors disabled:opacity-50"
          >
            <Trash2 className="w-3.5 h-3.5" />
            Delete
          </button>
        </>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// PipelineTemplateCard
// ─────────────────────────────────────────────────────────────────────────────

interface PipelineTemplateCardProps {
  template: PipelineTemplateListItem;
}

export function PipelineTemplateCard({ template }: PipelineTemplateCardProps) {
  const [menuOpen, setMenuOpen] = useState(false);

  // Close menu on outside click
  React.useEffect(() => {
    if (!menuOpen) return;
    const handler = () => setMenuOpen(false);
    document.addEventListener("click", handler);
    return () => document.removeEventListener("click", handler);
  }, [menuOpen]);

  const formattedDate = template.updated_at
    ? new Date(template.updated_at).toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
      })
    : null;

  return (
    <div
      className={cn(
        "group relative flex flex-col rounded-xl border transition-all duration-150",
        "bg-[#18202F] border-[#2b3b55]",
        "hover:border-[#3d5070] hover:shadow-lg hover:shadow-black/20",
        template.is_archived && "opacity-60",
      )}
    >
      {/* ── Card header ── */}
      <div className="flex items-start gap-3 p-4 pb-3">
        {/* Icon */}
        <div className="shrink-0 w-9 h-9 rounded-lg bg-[#135bec]/15 flex items-center justify-center">
          <GitBranch className="w-4.5 h-4.5 text-[#5b9eff]" />
        </div>

        {/* Title + badges */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="text-sm font-semibold text-white truncate">
              {template.name}
            </h3>
            {template.is_builtin && (
              <span aria-label="Built-in" title="Built-in">
                <Lock className="w-3 h-3 text-[#3d5070] shrink-0" />
              </span>
            )}
            {template.is_archived && (
              <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-[#2b3b55] text-[#92a4c9]">
                Archived
              </span>
            )}
          </div>
          <p className="text-xs text-[#92a4c9] mt-0.5 line-clamp-2">
            {template.description || "No description"}
          </p>
        </div>

        {/* Menu trigger */}
        <div className="relative shrink-0" onClick={(e) => e.stopPropagation()}>
          <button
            type="button"
            onClick={() => setMenuOpen((v) => !v)}
            className={cn(
              "w-7 h-7 rounded-lg flex items-center justify-center",
              "text-[#3d5070] hover:text-white hover:bg-[#1e2a3d]",
              "transition-colors duration-150",
              "opacity-0 group-hover:opacity-100",
            )}
          >
            <MoreVertical className="w-4 h-4" />
          </button>

          {menuOpen && (
            <CardMenu template={template} onClose={() => setMenuOpen(false)} />
          )}
        </div>
      </div>

      {/* ── Stats row ── */}
      <div className="flex items-center gap-4 px-4 py-2 border-t border-[#2b3b55]/50">
        <span className="flex items-center gap-1.5 text-xs text-[#92a4c9]">
          <Network className="w-3.5 h-3.5" />
          {template.node_count} node{template.node_count !== 1 ? "s" : ""}
        </span>
        <span className="flex items-center gap-1.5 text-xs text-[#92a4c9]">
          <GitBranch className="w-3 h-3" />v{template.version}
        </span>
        {template.last_run_status && (
          <div className="ml-auto">
            <StatusBadge lastRunStatus={template.last_run_status} />
          </div>
        )}
      </div>

      {/* ── Tags ── */}
      {template.tags.length > 0 && (
        <div className="flex flex-wrap gap-1.5 px-4 pb-3">
          {template.tags.slice(0, 3).map((tag) => (
            <span
              key={tag}
              className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-[#2b3b55] text-[#92a4c9]"
            >
              {tag}
            </span>
          ))}
          {template.tags.length > 3 && (
            <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-[#2b3b55] text-[#92a4c9]">
              +{template.tags.length - 3}
            </span>
          )}
        </div>
      )}

      {/* ── Footer ── */}
      <div className="mt-auto flex items-center gap-2 px-4 py-3 border-t border-[#2b3b55]">
        {formattedDate && (
          <span className="flex items-center gap-1 text-[11px] text-[#3d5070]">
            <Clock className="w-3 h-3" />
            {formattedDate}
          </span>
        )}

        <div className="flex items-center gap-2 ml-auto">
          {/* History */}
          <Link
            href={`/pipelines/${template.template_id}/runs`}
            className={cn(
              "flex items-center gap-1.5 h-7 px-2.5 rounded-lg text-xs",
              "text-[#92a4c9] hover:text-white border border-[#2b3b55]",
              "hover:bg-[#1e2a3d] hover:border-[#3d5070]",
              "transition-all duration-150",
            )}
          >
            <History className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">History</span>
          </Link>

          {/* Edit / Open builder */}
          <Link
            href={`/pipelines/${template.template_id}`}
            className={cn(
              "flex items-center gap-1.5 h-7 px-2.5 rounded-lg text-xs font-medium",
              "bg-[#135bec]/15 text-[#5b9eff]",
              "hover:bg-[#135bec]/25 border border-[#135bec]/20",
              "transition-all duration-150",
            )}
          >
            <GitBranch className="w-3.5 h-3.5" />
            <span>Open</span>
          </Link>

          {/* Run */}
          <Link
            href={`/pipelines/${template.template_id}/run`}
            className={cn(
              "flex items-center gap-1.5 h-7 px-2.5 rounded-lg text-xs font-medium",
              "bg-[#135bec] text-white hover:bg-[#1a6aff]",
              "transition-colors duration-150",
            )}
          >
            <Play className="w-3.5 h-3.5" />
            Run
          </Link>
        </div>
      </div>
    </div>
  );
}
