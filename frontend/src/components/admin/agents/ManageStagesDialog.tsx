"use client";

import * as React from "react";
import { Layers, Plus, ArrowUpDown } from "lucide-react";

import {
  Modal,
  ModalHeader,
  ModalBody,
  ModalFooter,
} from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { toast } from "@/components/ui/Toast";
import {
  useStageConfigs,
  useCreateStageConfig,
  useUpdateStageConfig,
  useDeleteStageConfig,
  useReorderStages,
} from "@/hooks/useStageConfigs";
import { cn } from "@/lib/utils";
import type {
  StageConfig,
  StageConfigCreate,
  StageConfigUpdate,
} from "@/types";

import { StageRow } from "./StageRow";
import { AddStageForm } from "./AddStageForm";

// ─────────────────────────────────────────────────────────────────────────────
// Props
// ─────────────────────────────────────────────────────────────────────────────

export interface ManageStagesDialogProps {
  open: boolean;
  onClose: () => void;
}

// ─────────────────────────────────────────────────────────────────────────────
// Loading skeleton
// ─────────────────────────────────────────────────────────────────────────────

function StageListSkeleton() {
  return (
    <div className="space-y-2" aria-hidden="true" aria-label="Loading stages…">
      {Array.from({ length: 4 }).map((_, i) => (
        <div
          key={i}
          className={cn(
            "h-13 rounded-lg",
            "bg-[#18202F] border border-[#2b3b55]",
            "animate-pulse",
          )}
        />
      ))}
      <span className="sr-only">Loading pipeline stages…</span>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// ManageStagesDialog
// ─────────────────────────────────────────────────────────────────────────────

export function ManageStagesDialog({ open, onClose }: ManageStagesDialogProps) {
  // ── Server data ────────────────────────────────────────────────────────────
  const { data: stagesData, isLoading } = useStageConfigs();

  // ── Mutations ──────────────────────────────────────────────────────────────
  const createMutation = useCreateStageConfig();
  const updateMutation = useUpdateStageConfig();
  const deleteMutation = useDeleteStageConfig();
  const reorderMutation = useReorderStages();

  // ── Local state ────────────────────────────────────────────────────────────
  const [orderedStages, setOrderedStages] = React.useState<StageConfig[]>([]);
  const [showAddForm, setShowAddForm] = React.useState(false);
  const [editingId, setEditingId] = React.useState<string | null>(null);

  // Drag tracking — a ref so drag handlers don't cause re-renders
  const dragIndexRef = React.useRef<number | null>(null);
  // Track which index is being dragged-over for visual feedback
  const [dragOverIndex, setDragOverIndex] = React.useState<number | null>(null);

  // ── Sync ordered list from API ─────────────────────────────────────────────
  React.useEffect(() => {
    if (stagesData) {
      setOrderedStages([...stagesData]);
    }
  }, [stagesData]);

  // Reset transient UI state when the dialog is closed
  React.useEffect(() => {
    if (!open) {
      setShowAddForm(false);
      setEditingId(null);
      dragIndexRef.current = null;
      setDragOverIndex(null);
    }
  }, [open]);

  // ── Order-change detection ─────────────────────────────────────────────────
  const originalOrder = React.useMemo(
    () => stagesData?.map((s) => s.stage_id) ?? [],
    [stagesData],
  );

  const orderChanged = React.useMemo(() => {
    if (orderedStages.length !== originalOrder.length) return false;
    return orderedStages.some((s, i) => s.stage_id !== originalOrder[i]);
  }, [orderedStages, originalOrder]);

  // ── Drag-and-drop handlers ─────────────────────────────────────────────────

  const handleDragStart = (_e: React.DragEvent, index: number) => {
    dragIndexRef.current = index;
  };

  const handleDragOver = (e: React.DragEvent, index: number) => {
    e.preventDefault();
    setDragOverIndex(index);
  };

  const handleDrop = (_e: React.DragEvent, dropIndex: number) => {
    const dragIndex = dragIndexRef.current;

    setDragOverIndex(null);
    dragIndexRef.current = null;

    if (dragIndex === null || dragIndex === dropIndex) return;

    setOrderedStages((prev) => {
      const next = [...prev];
      const [removed] = next.splice(dragIndex, 1);
      next.splice(dropIndex, 0, removed);
      return next;
    });
  };

  const handleDragEnd = () => {
    setDragOverIndex(null);
    dragIndexRef.current = null;
  };

  // ── Create handler ─────────────────────────────────────────────────────────

  const handleCreate = async (data: StageConfigCreate) => {
    try {
      await createMutation.mutateAsync(data);
      toast.success(
        "Stage created",
        `"${data.display_name}" has been added to the pipeline.`,
      );
      setShowAddForm(false);
    } catch {
      toast.error(
        "Create failed",
        "Could not create the stage. Please try again.",
      );
    }
  };

  // ── Update handler ─────────────────────────────────────────────────────────

  const handleUpdate = async (stageId: string, data: StageConfigUpdate) => {
    try {
      await updateMutation.mutateAsync({ stageId, data });
      toast.success("Stage updated", "Your changes have been saved.");
      setEditingId(null);
    } catch {
      toast.error(
        "Update failed",
        "Could not update the stage. Please try again.",
      );
    }
  };

  // ── Delete handler ─────────────────────────────────────────────────────────

  const handleDelete = (stage: StageConfig) => {
    const confirmed = window.confirm(
      `Delete stage "${stage.display_name}"?\n\nAgents assigned to this stage will be moved to an unassigned state. This action cannot be undone.`,
    );
    if (!confirmed) return;

    deleteMutation
      .mutateAsync(stage.stage_id)
      .then(() => {
        toast.success(
          "Stage deleted",
          `"${stage.display_name}" has been removed.`,
        );
      })
      .catch(() => {
        toast.error(
          "Delete failed",
          "Could not delete the stage. Please try again.",
        );
      });
  };

  // ── Save order handler ─────────────────────────────────────────────────────

  const handleSaveOrder = async () => {
    try {
      await reorderMutation.mutateAsync(orderedStages.map((s) => s.stage_id));
      toast.success("Order saved", "Stage order has been updated.");
    } catch {
      toast.error(
        "Reorder failed",
        "Could not save the stage order. Please try again.",
      );
    }
  };

  // ── Derived busy state ─────────────────────────────────────────────────────
  const isBusy =
    createMutation.isPending ||
    updateMutation.isPending ||
    deleteMutation.isPending ||
    reorderMutation.isPending;

  // ─────────────────────────────────────────────────────────────────────────
  // Render
  // ─────────────────────────────────────────────────────────────────────────
  return (
    <Modal open={open} onClose={onClose} size="xl">
      {/* ── Header ─────────────────────────────────────────────────────── */}
      <ModalHeader
        title="Manage Stages"
        subtitle="Drag to reorder. Built-in stages cannot be deleted."
        onClose={onClose}
        icon={<Layers className="w-4 h-4" aria-hidden="true" />}
      />

      {/* ── Body ───────────────────────────────────────────────────────── */}
      <ModalBody className="space-y-3">
        {/* Loading state */}
        {isLoading && <StageListSkeleton />}

        {/* Stage list */}
        {!isLoading && orderedStages.length > 0 && (
          <div
            role="list"
            aria-label="Pipeline stages"
            className="space-y-2"
            onDragLeave={() => setDragOverIndex(null)}
          >
            {orderedStages.map((stage, index) => (
              <div
                key={stage.id}
                role="listitem"
                className={cn(
                  "rounded-lg transition-all duration-150",
                  dragOverIndex === index &&
                    dragIndexRef.current !== index &&
                    "ring-2 ring-[#135bec]/50 ring-offset-1 ring-offset-[#101622]",
                )}
              >
                <StageRow
                  stage={stage}
                  index={index}
                  isEditing={editingId === stage.id}
                  onEdit={() => {
                    setEditingId(stage.id);
                    setShowAddForm(false);
                  }}
                  onCancelEdit={() => setEditingId(null)}
                  onSaveEdit={(data: StageConfigUpdate) =>
                    handleUpdate(stage.stage_id, data)
                  }
                  onDelete={() => handleDelete(stage)}
                  draggable={editingId !== stage.id}
                  onDragStart={handleDragStart}
                  onDragOver={handleDragOver}
                  onDrop={handleDrop}
                />
              </div>
            ))}
          </div>
        )}

        {/* Empty state (loaded but no stages) */}
        {!isLoading && orderedStages.length === 0 && (
          <div className="flex items-center justify-center py-12">
            <p className="text-sm text-[#3d5070] italic">
              No stages configured yet.
            </p>
          </div>
        )}

        {/* Add stage form OR add button */}
        {!isLoading && (
          <>
            {showAddForm ? (
              <AddStageForm
                onSubmit={handleCreate}
                onCancel={() => setShowAddForm(false)}
                isLoading={createMutation.isPending}
              />
            ) : (
              <button
                type="button"
                onClick={() => {
                  setShowAddForm(true);
                  setEditingId(null);
                  setDragOverIndex(null);
                }}
                disabled={isBusy}
                aria-label="Add new stage"
                className={cn(
                  "w-full flex items-center justify-center gap-2 py-2.5 rounded-lg",
                  "border border-dashed border-[#2b3b55]",
                  "text-sm font-medium text-[#92a4c9]",
                  "hover:text-white hover:border-[#135bec]/50 hover:bg-[#135bec]/5",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#135bec]",
                  "transition-colors duration-150",
                  "disabled:opacity-50 disabled:cursor-not-allowed",
                )}
              >
                <Plus className="w-4 h-4" aria-hidden="true" />
                Add Stage
              </button>
            )}
          </>
        )}
      </ModalBody>

      {/* ── Footer ─────────────────────────────────────────────────────── */}
      <ModalFooter className="justify-between">
        {/* Left: order-change indicator */}
        <div className="flex items-center gap-2 min-w-0">
          {orderChanged && (
            <p
              className={cn(
                "flex items-center gap-1.5",
                "text-xs font-medium text-[#fbbf24]",
                "select-none",
              )}
              aria-live="polite"
            >
              <ArrowUpDown
                className="w-3.5 h-3.5 shrink-0"
                aria-hidden="true"
              />
              <span>Order changed — save to apply</span>
            </p>
          )}
        </div>

        {/* Right: action buttons */}
        <div className="flex items-center gap-2 shrink-0">
          <Button variant="ghost" onClick={onClose} disabled={isBusy}>
            Cancel
          </Button>

          {orderChanged && (
            <Button
              variant="primary"
              onClick={handleSaveOrder}
              loading={reorderMutation.isPending}
              disabled={isBusy}
              leftIcon={
                !reorderMutation.isPending ? (
                  <ArrowUpDown className="w-4 h-4" aria-hidden="true" />
                ) : undefined
              }
            >
              Save Order
            </Button>
          )}
        </div>
      </ModalFooter>
    </Modal>
  );
}

export default ManageStagesDialog;
