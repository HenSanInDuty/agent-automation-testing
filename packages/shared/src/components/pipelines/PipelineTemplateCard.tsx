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
  Clock,
  Network,
  Pencil,
  Check,
  X,
  Settings2,
} from "lucide-react";
import { cn } from "../../lib/utils";
import type { PipelineTemplateListItem } from "../../types";
import {
  useCloneTemplate,
  useDeleteTemplate,
  useArchiveTemplate,
  useUpdateTemplate,
} from "../../hooks/usePipelineTemplates";
import { toast } from "../../components/ui/Toast";
import { ConfirmDialog } from "../../components/ui/Modal";
import { EditPipelineDialog } from "./EditPipelineDialog";

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
  onRequestRename: () => void;
  onRequestEditDetails: () => void;
  onRequestDelete: () => void;
}

function CardMenu({
  template,
  onClose,
  onRequestRename,
  onRequestEditDetails,
  onRequestDelete,
}: CardMenuProps) {
  const cloneMutation = useCloneTemplate();
  const archiveMutation = useArchiveTemplate();

  const handleClone = async () => {
    try {
      const cloned = await cloneMutation.mutateAsync({
        templateId: template.template_id,
        newTemplateId: `${template.template_id}-copy`,
        newName: `${template.name} (Copy)`,
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

  return (
    <div
      className={cn(
        "absolute right-0 top-full mt-1 z-50 w-44",
        "bg-[#18202F] border border-[#2b3b55] rounded-xl shadow-xl",
        "py-1 overflow-hidden",
      )}
    >
      <>
        <button
          type="button"
          onClick={() => {
            onRequestRename();
            onClose();
          }}
          className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-[#92a4c9] hover:text-white hover:bg-[#1e2a3d] transition-colors"
        >
          <Pencil className="w-3.5 h-3.5" />
          Rename
        </button>

        <button
          type="button"
          onClick={() => {
            onRequestEditDetails();
            onClose();
          }}
          className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-[#92a4c9] hover:text-white hover:bg-[#1e2a3d] transition-colors"
        >
          <Settings2 className="w-3.5 h-3.5" />
          Edit details
        </button>
      </>

      <button
        type="button"
        onClick={handleClone}
        disabled={cloneMutation.isPending}
        className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-[#92a4c9] hover:text-white hover:bg-[#1e2a3d] transition-colors disabled:opacity-50"
      >
        <Copy className="w-3.5 h-3.5" />
        Clone
      </button>

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
          onClick={() => {
            onRequestDelete();
            onClose();
          }}
          className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-red-400 hover:text-red-300 hover:bg-[#1e2a3d] transition-colors"
        >
          <Trash2 className="w-3.5 h-3.5" />
          Delete
        </button>
      </>
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
  const [renaming, setRenaming] = useState(false);
  const [draftName, setDraftName] = useState(template.name);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [editDetailsOpen, setEditDetailsOpen] = useState(false);
  const renameInputRef = React.useRef<HTMLInputElement | null>(null);

  const updateMutation = useUpdateTemplate(template.template_id);
  const deleteMutation = useDeleteTemplate();

  // Close menu on outside click
  React.useEffect(() => {
    if (!menuOpen) return;
    const handler = () => setMenuOpen(false);
    document.addEventListener("click", handler);
    return () => document.removeEventListener("click", handler);
  }, [menuOpen]);

  // Sync draft when template name changes externally
  React.useEffect(() => {
    setDraftName(template.name);
  }, [template.name]);

  // Focus the input when entering rename mode
  React.useEffect(() => {
    if (renaming) {
      renameInputRef.current?.focus();
      renameInputRef.current?.select();
    }
  }, [renaming]);

  const beginRename = () => {
    setDraftName(template.name);
    setRenaming(true);
  };

  const cancelRename = () => {
    setRenaming(false);
    setDraftName(template.name);
  };

  const commitRename = async () => {
    const next = draftName.trim();
    if (!next || next === template.name) {
      cancelRename();
      return;
    }
    try {
      const updated = await updateMutation.mutateAsync({ name: next });
      toast.success("Pipeline renamed", `Renamed to "${updated.name}".`);
      setRenaming(false);
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? (err instanceof Error ? err.message : "Rename failed.");
      toast.error("Rename failed", detail);
    }
  };

  const handleRenameKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      commitRename();
    } else if (e.key === "Escape") {
      e.preventDefault();
      cancelRename();
    }
  };

  const handleDeleteConfirm = async () => {
    try {
      await deleteMutation.mutateAsync(template.template_id);
      toast.success(
        "Pipeline deleted",
        `"${template.name}" has been permanently removed.`,
      );
      setDeleteOpen(false);
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? (err instanceof Error ? err.message : "Delete failed.");
      toast.error("Delete failed", detail);
    }
  };

  const formattedDate = template.updated_at
    ? new Date(template.updated_at).toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
      })
    : null;

  const renameDirty =
    renaming &&
    draftName.trim().length > 0 &&
    draftName.trim() !== template.name;

  return (
    <>
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

          {/* Title + badges (or inline rename input) */}
          <div className="flex-1 min-w-0">
            {renaming ? (
              <div
                className="flex items-center gap-1.5"
                onClick={(e) => e.stopPropagation()}
              >
                <input
                  ref={renameInputRef}
                  type="text"
                  value={draftName}
                  onChange={(e) => setDraftName(e.target.value)}
                  onKeyDown={handleRenameKeyDown}
                  disabled={updateMutation.isPending}
                  maxLength={120}
                  aria-label="Pipeline name"
                  className={cn(
                    "flex-1 min-w-0 px-2 py-1 rounded-md",
                    "bg-[#0f1729] border border-[#135bec]/50",
                    "text-sm font-semibold text-white",
                    "outline-none focus:border-[#135bec] focus:ring-1 focus:ring-[#135bec]",
                    updateMutation.isPending && "opacity-60",
                  )}
                />
                <button
                  type="button"
                  onClick={commitRename}
                  disabled={!renameDirty || updateMutation.isPending}
                  title="Save (Enter)"
                  aria-label="Save new name"
                  className={cn(
                    "shrink-0 w-6 h-6 rounded-md flex items-center justify-center",
                    "bg-[#135bec]/15 text-[#5b9eff]",
                    "hover:bg-[#135bec]/25",
                    "disabled:opacity-40 disabled:cursor-not-allowed",
                    "transition-colors",
                  )}
                >
                  <Check className="w-3.5 h-3.5" />
                </button>
                <button
                  type="button"
                  onClick={cancelRename}
                  disabled={updateMutation.isPending}
                  title="Cancel (Esc)"
                  aria-label="Cancel rename"
                  className={cn(
                    "shrink-0 w-6 h-6 rounded-md flex items-center justify-center",
                    "text-[#92a4c9] hover:text-white hover:bg-[#1e2a3d]",
                    "disabled:opacity-40 disabled:cursor-not-allowed",
                    "transition-colors",
                  )}
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            ) : (
              <div className="flex items-center gap-2 flex-wrap">
                <h3
                  className={cn(
                    "text-sm font-semibold text-white truncate",
                    "cursor-text hover:text-[#5b9eff] transition-colors",
                  )}
                  title={`${template.name} — double-click to rename`}
                  onDoubleClick={(e) => {
                    e.stopPropagation();
                    beginRename();
                  }}
                >
                  {template.name}
                </h3>
                {template.is_archived && (
                  <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-[#2b3b55] text-[#92a4c9]">
                    Archived
                  </span>
                )}
              </div>
            )}
            {!renaming && (
              <p className="text-xs text-[#92a4c9] mt-0.5 line-clamp-2">
                {template.description || "No description"}
              </p>
            )}
          </div>

          {/* Rename quick-action button (visible on hover, hidden while renaming) */}
          {!renaming && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                beginRename();
              }}
              title="Rename pipeline"
              aria-label="Rename pipeline"
              className={cn(
                "shrink-0 w-7 h-7 rounded-lg flex items-center justify-center",
                "text-[#3d5070] hover:text-[#5b9eff] hover:bg-[#1e2a3d]",
                "transition-colors duration-150",
                "opacity-0 group-hover:opacity-100",
              )}
            >
              <Pencil className="w-3.5 h-3.5" />
            </button>
          )}

          {/* Menu trigger */}
          {!renaming && (
            <div
              className="relative shrink-0"
              onClick={(e) => e.stopPropagation()}
            >
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
                <CardMenu
                  template={template}
                  onClose={() => setMenuOpen(false)}
                  onRequestRename={beginRename}
                  onRequestEditDetails={() => setEditDetailsOpen(true)}
                  onRequestDelete={() => setDeleteOpen(true)}
                />
              )}
            </div>
          )}
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

      {/* ── Delete confirmation modal ── */}
      <ConfirmDialog
        open={deleteOpen}
        onClose={() => setDeleteOpen(false)}
        onConfirm={handleDeleteConfirm}
        title="Delete Pipeline"
        description={`Delete "${template.name}"? This will permanently remove the pipeline and cannot be undone.`}
        confirmLabel="Delete Pipeline"
        cancelLabel="Cancel"
        variant="danger"
        loading={deleteMutation.isPending}
      />

      {/* ── Edit details modal ── */}
      <EditPipelineDialog
        open={editDetailsOpen}
        onClose={() => setEditDetailsOpen(false)}
        template={template}
      />
    </>
  );
}
