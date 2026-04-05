"use client";

import * as React from "react";
import { Plus, Layers, AlertCircle, RotateCcw } from "lucide-react";
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
  arrayMove,
} from "@dnd-kit/sortable";

import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/Modal";
import { toast } from "@/components/ui/Toast";
import { cn } from "@/lib/utils";
import {
  useStageConfigs,
  useDeleteStageConfig,
  useUpdateStageConfig,
  useReorderStages,
} from "@/hooks/useStageConfigs";
import type { StageConfig } from "@/types";

import { StageCard } from "./StageCard";
import { StageDialog } from "./StageDialog";

// ─────────────────────────────────────────────────────────────────────────────
// Skeleton
// ─────────────────────────────────────────────────────────────────────────────

function ListSkeleton() {
  return (
    <div className="space-y-2 animate-pulse" aria-hidden="true">
      {[...Array(4)].map((_, i) => (
        <div
          key={i}
          className="flex items-center gap-3 px-4 py-3 bg-[#18202F] border border-[#2b3b55] rounded-xl"
        >
          <div className="w-4 h-4 bg-[#2b3b55] rounded" />
          <div className="w-7 h-7 bg-[#2b3b55] rounded-lg" />
          <div className="flex-1 space-y-1">
            <div className="h-3 bg-[#2b3b55] rounded w-1/3" />
            <div className="h-2.5 bg-[#2b3b55] rounded w-1/2" />
          </div>
          <div className="w-20 h-5 bg-[#2b3b55] rounded" />
          <div className="w-10 h-4 bg-[#2b3b55] rounded-full" />
        </div>
      ))}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Error state
// ─────────────────────────────────────────────────────────────────────────────

function ErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-4">
      <div className="w-12 h-12 rounded-full bg-[#ef4444]/10 border border-[#ef4444]/20 flex items-center justify-center mb-4">
        <AlertCircle className="w-6 h-6 text-[#f87171]" aria-hidden="true" />
      </div>
      <h3 className="text-base font-semibold text-white mb-1">
        Failed to load stage configs
      </h3>
      <p className="text-sm text-[#92a4c9] mb-6 text-center max-w-sm">
        There was an error fetching the pipeline stage configurations from the
        server.
      </p>
      <Button
        variant="secondary"
        size="sm"
        leftIcon={<RotateCcw className="w-3.5 h-3.5" aria-hidden="true" />}
        onClick={onRetry}
      >
        Retry
      </Button>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// StageConfigList
// ─────────────────────────────────────────────────────────────────────────────

export function StageConfigList() {
  const { data: stagesData, isLoading, isError, refetch } = useStageConfigs();
  const deleteMutation = useDeleteStageConfig();
  const updateMutation = useUpdateStageConfig();
  const reorderMutation = useReorderStages();

  // Local ordered copy for optimistic DnD
  const [localStages, setLocalStages] = React.useState<StageConfig[]>([]);
  React.useEffect(() => {
    if (stagesData) setLocalStages(stagesData);
  }, [stagesData]);

  // Dialog state
  const [dialogOpen, setDialogOpen] = React.useState(false);
  const [editStageId, setEditStageId] = React.useState<string | undefined>(
    undefined,
  );

  // Delete confirm state
  const [deleteConfirmId, setDeleteConfirmId] = React.useState<string | null>(
    null,
  );

  // ── DnD setup ──────────────────────────────────────────────────────────────

  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    }),
  );

  const handleDragEnd = async (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;

    const oldIndex = localStages.findIndex((s) => s.stage_id === active.id);
    const newIndex = localStages.findIndex((s) => s.stage_id === over.id);

    if (oldIndex === -1 || newIndex === -1) return;

    const newOrder = arrayMove(localStages, oldIndex, newIndex);
    setLocalStages(newOrder);

    const payload = newOrder.map((s, i) => ({
      stage_id: s.stage_id,
      order: (i + 1) * 100,
    }));

    try {
      await reorderMutation.mutateAsync({ stages: payload });
      toast.success("Order saved", "Pipeline stage order has been updated.");
    } catch {
      // Revert on failure
      setLocalStages(stagesData ?? []);
      toast.error("Reorder failed", "Could not save the new stage order.");
    }
  };

  // ── Handlers ───────────────────────────────────────────────────────────────

  const handleEdit = (stageId: string) => {
    setEditStageId(stageId);
    setDialogOpen(true);
  };

  const handleCreate = () => {
    setEditStageId(undefined);
    setDialogOpen(true);
  };

  const handleDialogClose = () => {
    setDialogOpen(false);
    setTimeout(() => setEditStageId(undefined), 250);
  };

  const handleToggle = async (stageId: string, enabled: boolean) => {
    try {
      await updateMutation.mutateAsync({ stageId, payload: { enabled } });
      toast.success(
        enabled ? "Stage enabled" : "Stage disabled",
        `Stage has been ${enabled ? "enabled" : "disabled"}.`,
      );
    } catch {
      toast.error(
        "Update failed",
        "Could not update the stage. Please try again.",
      );
    }
  };

  const handleDeleteConfirm = async () => {
    if (!deleteConfirmId) return;
    const stage = localStages.find((s) => s.stage_id === deleteConfirmId);
    try {
      await deleteMutation.mutateAsync(deleteConfirmId);
      toast.success(
        "Stage deleted",
        `"${stage?.display_name ?? deleteConfirmId}" has been removed.`,
      );
    } catch {
      toast.error(
        "Delete failed",
        "Could not delete the stage. Please try again.",
      );
    } finally {
      setDeleteConfirmId(null);
    }
  };

  // ── Derived ────────────────────────────────────────────────────────────────

  const totalStages = localStages.length;
  const enabledCount = localStages.filter((s) => s.enabled).length;
  const stageToDelete = localStages.find((s) => s.stage_id === deleteConfirmId);

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <>
      {/* ── Page header ── */}
      <div className="flex items-start justify-between gap-4 mb-6">
        <div>
          <h2 className="text-lg font-semibold text-white leading-snug flex items-center gap-2.5">
            <span
              className={cn(
                "inline-flex items-center justify-center",
                "w-7 h-7 rounded-lg shrink-0",
                "bg-[#135bec]/10 border border-[#135bec]/20",
                "text-[#5b9eff]",
              )}
            >
              <Layers className="w-4 h-4" aria-hidden="true" />
            </span>
            Pipeline Stages
          </h2>
          <p className="mt-1 text-sm text-[#92a4c9]">
            {isLoading ? (
              <span
                aria-hidden="true"
                className="inline-block h-3.5 w-40 bg-[#2b3b55] rounded animate-pulse"
              />
            ) : isError ? (
              <span className="text-[#f87171]">
                Could not load stage configurations
              </span>
            ) : (
              <>
                <span className="text-white font-medium">{totalStages}</span>
                {" stages, "}
                <span className="text-white font-medium">{enabledCount}</span>
                {" enabled"}
              </>
            )}
          </p>
        </div>

        {/* Add Stage button */}
        <Button
          variant="primary"
          size="sm"
          leftIcon={<Plus className="w-3.5 h-3.5" aria-hidden="true" />}
          onClick={handleCreate}
        >
          Add Stage
        </Button>
      </div>

      {/* ── Drag hint ── */}
      {!isLoading && !isError && totalStages > 0 && (
        <p className="text-xs text-[#3d5070] mb-4">
          Drag the{" "}
          <span className="text-[#92a4c9]">≡</span>{" "}
          handle to reorder stages. Changes are saved automatically.
        </p>
      )}

      {/* ── Content ── */}
      {isLoading ? (
        <ListSkeleton />
      ) : isError ? (
        <ErrorState onRetry={refetch} />
      ) : localStages.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 px-4">
          <p className="text-sm text-[#3d5070] italic">No stages configured.</p>
          <Button
            variant="primary"
            size="sm"
            className="mt-4"
            leftIcon={<Plus className="w-3.5 h-3.5" aria-hidden="true" />}
            onClick={handleCreate}
          >
            Add First Stage
          </Button>
        </div>
      ) : (
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          onDragEnd={handleDragEnd}
        >
          <SortableContext
            items={localStages.map((s) => s.stage_id)}
            strategy={verticalListSortingStrategy}
          >
            <div className="space-y-2">
              {localStages.map((stage) => (
                <StageCard
                  key={stage.stage_id}
                  stage={stage}
                  onEdit={handleEdit}
                  onDelete={(id) => setDeleteConfirmId(id)}
                  onToggle={handleToggle}
                />
              ))}
            </div>
          </SortableContext>
        </DndContext>
      )}

      {/* ── Dialogs ── */}
      <StageDialog
        open={dialogOpen}
        onClose={handleDialogClose}
        stageId={editStageId}
      />

      <ConfirmDialog
        open={Boolean(deleteConfirmId)}
        onClose={() => setDeleteConfirmId(null)}
        onConfirm={handleDeleteConfirm}
        title="Delete Stage"
        description={
          stageToDelete
            ? `Are you sure you want to delete "${stageToDelete.display_name}"? This action cannot be undone.`
            : "Are you sure you want to delete this stage?"
        }
        confirmLabel="Delete Stage"
        cancelLabel="Cancel"
        variant="danger"
        loading={deleteMutation.isPending}
      />
    </>
  );
}

export default StageConfigList;
