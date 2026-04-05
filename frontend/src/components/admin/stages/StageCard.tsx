"use client";

import * as React from "react";
import { GripVertical, Edit3, Trash2, Timer } from "lucide-react";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";

import { Button } from "@/components/ui/Button";
import { Toggle, Badge } from "@/components/ui/Select";
import { cn } from "@/lib/utils";
import type { StageConfig, StageCrewType } from "@/types";

// ─────────────────────────────────────────────────────────────────────────────
// Crew type badge config
// ─────────────────────────────────────────────────────────────────────────────

const CREW_TYPE_BADGE: Record<
  StageCrewType,
  { label: string; variant: "primary" | "info" | "warning" }
> = {
  pure_python: { label: "Pure Python", variant: "primary" },
  crewai_sequential: { label: "Sequential", variant: "info" },
  crewai_hierarchical: { label: "Hierarchical", variant: "warning" },
};

// ─────────────────────────────────────────────────────────────────────────────
// Props
// ─────────────────────────────────────────────────────────────────────────────

export interface StageCardProps {
  stage: StageConfig;
  onEdit: (stageId: string) => void;
  onDelete: (stageId: string) => void;
  onToggle: (stageId: string, enabled: boolean) => void;
}

// ─────────────────────────────────────────────────────────────────────────────
// StageCard
// ─────────────────────────────────────────────────────────────────────────────

export function StageCard({ stage, onEdit, onDelete, onToggle }: StageCardProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: stage.stage_id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  const crewBadge = CREW_TYPE_BADGE[stage.crew_type];

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={cn(
        "group flex items-center gap-3 px-4 py-3",
        "bg-[#18202F] border border-[#2b3b55] rounded-xl",
        "transition-all duration-150",
        isDragging && "opacity-50 shadow-2xl z-50 scale-[1.02]",
      )}
    >
      {/* ── Drag handle ──────────────────────────────────────────────────── */}
      <button
        type="button"
        {...attributes}
        {...listeners}
        className={cn(
          "shrink-0 p-1 rounded text-[#3d5070] cursor-grab active:cursor-grabbing",
          "hover:text-[#92a4c9] hover:bg-[#1e2a3d]",
          "transition-colors duration-150 focus-visible:outline-none",
        )}
        aria-label="Drag to reorder"
      >
        <GripVertical className="w-4 h-4" aria-hidden="true" />
      </button>

      {/* ── Order badge ───────────────────────────────────────────────────── */}
      <div
        className={cn(
          "shrink-0 w-7 h-7 rounded-lg",
          "bg-[#101622] border border-[#2b3b55]",
          "flex items-center justify-center",
        )}
        aria-hidden="true"
      >
        <span className="text-[11px] font-semibold text-[#92a4c9] tabular-nums">
          {Math.floor(stage.order / 100)}
        </span>
      </div>

      {/* ── Name + description ────────────────────────────────────────────── */}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-white truncate leading-snug">
          {stage.display_name}
        </p>
        {stage.description && (
          <p className="text-[11px] text-[#3d5070] truncate mt-0.5">
            {stage.description}
          </p>
        )}
      </div>

      {/* ── Crew type badge ───────────────────────────────────────────────── */}
      <div className="hidden sm:flex shrink-0">
        <Badge variant={crewBadge.variant} size="xs">
          {crewBadge.label}
        </Badge>
      </div>

      {/* ── Timeout ───────────────────────────────────────────────────────── */}
      <div className="hidden md:flex shrink-0 items-center gap-1 text-[#92a4c9]">
        <Timer className="w-3 h-3" aria-hidden="true" />
        <span className="text-xs tabular-nums">{stage.timeout_seconds}s</span>
      </div>

      {/* ── Builtin badge ─────────────────────────────────────────────────── */}
      <div className="hidden lg:flex shrink-0">
        {stage.is_builtin && (
          <Badge variant="outline" size="xs">
            Builtin
          </Badge>
        )}
      </div>

      {/* ── Enabled toggle ────────────────────────────────────────────────── */}
      <div className="shrink-0 flex flex-col items-center gap-0.5">
        <span className="text-[9px] font-semibold uppercase tracking-wider text-[#3d5070] select-none">
          Enabled
        </span>
        <Toggle
          checked={stage.enabled}
          onChange={(v) => onToggle(stage.stage_id, v)}
          size="sm"
          aria-label={`Toggle enabled for ${stage.display_name}`}
        />
      </div>

      {/* ── Action buttons ────────────────────────────────────────────────── */}
      <div className="shrink-0 flex items-center gap-1">
        <Button
          variant="ghost"
          size="xs"
          leftIcon={<Edit3 className="w-3 h-3" aria-hidden="true" />}
          onClick={() => onEdit(stage.stage_id)}
          title={`Edit ${stage.display_name}`}
          className={cn(
            "opacity-0 group-hover:opacity-100",
            "transition-opacity duration-150",
          )}
        >
          Edit
        </Button>

        {!stage.is_builtin && (
          <Button
            variant="ghost"
            size="xs"
            leftIcon={<Trash2 className="w-3 h-3" aria-hidden="true" />}
            onClick={() => onDelete(stage.stage_id)}
            title={`Delete ${stage.display_name}`}
            className={cn(
              "opacity-0 group-hover:opacity-100",
              "transition-opacity duration-150",
              "text-[#92a4c9] hover:text-[#f87171] hover:bg-[#ef4444]/10",
            )}
          >
            Delete
          </Button>
        )}
      </div>
    </div>
  );
}

export default StageCard;
