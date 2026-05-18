"use client";

import * as React from "react";
import { GripVertical, Pencil, Trash2, Lock, X, Check } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/utils";
import type { StageConfig, StageConfigUpdate } from "@/types";

import { StageIcon } from "./StageIcon";

// ─────────────────────────────────────────────────────────────────────────────
// Props
// ─────────────────────────────────────────────────────────────────────────────

export interface StageRowProps {
  stage: StageConfig;
  index: number;
  isEditing: boolean;
  onEdit: () => void;
  onCancelEdit: () => void;
  onSaveEdit: (data: StageConfigUpdate) => void;
  onDelete: () => void;
  // For native HTML drag-drop reorder
  draggable?: boolean;
  onDragStart?: (e: React.DragEvent, index: number) => void;
  onDragOver?: (e: React.DragEvent, index: number) => void;
  onDrop?: (e: React.DragEvent, index: number) => void;
}

// ─────────────────────────────────────────────────────────────────────────────
// Inline field sub-component
// ─────────────────────────────────────────────────────────────────────────────

interface InlineFieldProps {
  label: string;
  children: React.ReactNode;
  className?: string;
}

function InlineField({ label, children, className }: InlineFieldProps) {
  return (
    <div className={cn("flex flex-col gap-1", className)}>
      <span className="text-[10px] font-semibold uppercase tracking-wider text-[#3d5070] select-none">
        {label}
      </span>
      {children}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// StageRow
// ─────────────────────────────────────────────────────────────────────────────

export function StageRow({
  stage,
  index,
  isEditing,
  onEdit,
  onCancelEdit,
  onSaveEdit,
  onDelete,
  draggable,
  onDragStart,
  onDragOver,
  onDrop,
}: StageRowProps) {
  // ── Local edit state ─────────────────────────────────────────────────────
  const [editName, setEditName] = React.useState(stage.display_name);
  const [editColor, setEditColor] = React.useState(stage.color ?? "#4b6a9e");
  const [editIcon, setEditIcon] = React.useState(stage.icon ?? "");

  // Re-sync local state whenever editing is activated for this row
  React.useEffect(() => {
    if (isEditing) {
      setEditName(stage.display_name);
      setEditColor(stage.color ?? "#4b6a9e");
      setEditIcon(stage.icon ?? "");
    }
  }, [isEditing, stage.display_name, stage.color, stage.icon]);

  const handleSave = () => {
    const data: StageConfigUpdate = {
      display_name: editName.trim() || stage.display_name,
      color: editColor || null,
      icon: editIcon.trim() || null,
    };
    onSaveEdit(data);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") handleSave();
    if (e.key === "Escape") onCancelEdit();
  };

  // ── Shared input style ────────────────────────────────────────────────────
  const inputCls = cn(
    "w-full h-8 rounded-md bg-[#101622] border border-[#2b3b55] px-3",
    "text-sm text-white placeholder:text-[#3d5070]",
    "outline-none focus:ring-2 focus:ring-[#135bec] focus:border-[#135bec]",
    "transition-colors duration-150",
    "disabled:opacity-50 disabled:cursor-not-allowed",
  );

  // ─────────────────────────────────────────────────────────────────────────
  // ── EDIT MODE
  // ─────────────────────────────────────────────────────────────────────────
  if (isEditing) {
    return (
      <div
        className={cn(
          "rounded-lg border border-[#135bec]/35 bg-[#1a2438]",
          "px-4 py-3 space-y-3",
        )}
        role="form"
        aria-label={`Edit stage ${stage.display_name}`}
      >
        {/* Stage ID hint */}
        <p className="text-[10px] font-mono text-[#3d5070] select-none">
          ID: {stage.stage_id}
          {stage.is_builtin && (
            <span className="ml-2 text-[#3d5070]">(built-in)</span>
          )}
        </p>

        {/* Display name */}
        <InlineField label="Display Name">
          <input
            autoFocus
            value={editName}
            onChange={(e) => setEditName(e.target.value)}
            onKeyDown={handleKeyDown}
            className={inputCls}
            placeholder="Stage display name"
            aria-label="Display name"
          />
        </InlineField>

        {/* Color + Icon row */}
        <div className="flex gap-3">
          {/* Color */}
          <InlineField label="Color" className="flex-1">
            <div className="flex items-center gap-2">
              <input
                type="color"
                value={editColor}
                onChange={(e) => setEditColor(e.target.value)}
                className={cn(
                  "w-8 h-8 shrink-0 rounded-md border border-[#2b3b55]",
                  "bg-[#101622] cursor-pointer p-0.5",
                  "focus:outline-none focus:ring-2 focus:ring-[#135bec]",
                )}
                aria-label="Pick stage color"
              />
              <input
                type="text"
                value={editColor}
                onChange={(e) => setEditColor(e.target.value)}
                onKeyDown={handleKeyDown}
                className={cn(inputCls, "font-mono")}
                placeholder="#4b6a9e"
                aria-label="Color hex value"
              />
            </div>
          </InlineField>

          {/* Icon */}
          <InlineField label="Icon" className="flex-1">
            <div className="flex items-center gap-2">
              {/* Live preview */}
              <div
                className="shrink-0 w-8 h-8 rounded-md flex items-center justify-center border"
                style={{
                  backgroundColor: editColor ? `${editColor}20` : "#135bec20",
                  borderColor: editColor ? `${editColor}40` : "#135bec40",
                }}
                aria-hidden="true"
              >
                <StageIcon
                  name={editIcon || null}
                  color={editColor || "#5b9eff"}
                  className="w-3.5 h-3.5"
                />
              </div>
              <input
                type="text"
                value={editIcon}
                onChange={(e) => setEditIcon(e.target.value)}
                onKeyDown={handleKeyDown}
                className={inputCls}
                placeholder="e.g. flask-conical"
                aria-label="Icon name"
              />
            </div>
          </InlineField>
        </div>

        {/* Action buttons */}
        <div className="flex items-center justify-end gap-2 pt-0.5">
          <Button
            variant="ghost"
            size="xs"
            onClick={onCancelEdit}
            leftIcon={<X className="w-3 h-3" aria-hidden="true" />}
          >
            Cancel
          </Button>
          <Button
            variant="primary"
            size="xs"
            onClick={handleSave}
            leftIcon={<Check className="w-3 h-3" aria-hidden="true" />}
          >
            Save
          </Button>
        </div>
      </div>
    );
  }

  // ─────────────────────────────────────────────────────────────────────────
  // ── VIEW MODE
  // ─────────────────────────────────────────────────────────────────────────
  return (
    <div
      className={cn(
        "group flex items-center gap-3 px-3 py-2.5",
        "bg-[#18202F] border border-[#2b3b55] rounded-lg",
        "transition-colors duration-150",
        "hover:bg-[#1e2a3d] hover:border-[#3d5070]",
        draggable && "cursor-grab active:cursor-grabbing",
      )}
      draggable={draggable}
      onDragStart={onDragStart ? (e) => onDragStart(e, index) : undefined}
      onDragOver={
        onDragOver
          ? (e) => {
              e.preventDefault();
              onDragOver(e, index);
            }
          : undefined
      }
      onDrop={
        onDrop
          ? (e) => {
              e.preventDefault();
              onDrop(e, index);
            }
          : undefined
      }
      aria-label={`Stage: ${stage.display_name}`}
    >
      {/* ── Drag handle ──────────────────────────────────────────────────── */}
      <GripVertical
        className={cn(
          "w-4 h-4 shrink-0 text-[#3d5070]",
          "group-hover:text-[#92a4c9] transition-colors duration-150",
        )}
        aria-hidden="true"
      />

      {/* ── Stage icon ───────────────────────────────────────────────────── */}
      <div
        className="shrink-0 w-7 h-7 rounded-md flex items-center justify-center border"
        style={{
          backgroundColor: stage.color ? `${stage.color}20` : "#135bec20",
          borderColor: stage.color ? `${stage.color}40` : "#135bec40",
        }}
        aria-hidden="true"
      >
        <StageIcon
          name={stage.icon}
          color={stage.color ?? "#5b9eff"}
          className="w-3.5 h-3.5"
        />
      </div>

      {/* ── Stage name + ID ──────────────────────────────────────────────── */}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-white leading-snug truncate">
          {stage.display_name}
        </p>
        <p className="text-[10px] font-mono text-[#3d5070] truncate select-none">
          {stage.stage_id}
        </p>
      </div>

      {/* ── Order badge ──────────────────────────────────────────────────── */}
      <div
        className={cn(
          "shrink-0 w-6 h-6 rounded-md",
          "bg-[#101622] border border-[#2b3b55]",
          "flex items-center justify-center",
        )}
        title={`Order: ${stage.order}`}
        aria-label={`Order ${stage.order}`}
      >
        <span className="text-[10px] font-semibold text-[#92a4c9] tabular-nums">
          {stage.order}
        </span>
      </div>

      {/* ── Built-in lock icon ───────────────────────────────────────────── */}
      {stage.is_builtin && (
        <Lock
          className="shrink-0 w-3.5 h-3.5 text-[#3d5070]"
          aria-label="Built-in stage (cannot be deleted)"
        />
      )}

      {/* ── Action buttons (visible on hover) ───────────────────────────── */}
      <div
        className={cn(
          "shrink-0 flex items-center gap-1",
          "opacity-0 group-hover:opacity-100 transition-opacity duration-150",
        )}
      >
        <Button
          variant="ghost"
          size="xs"
          leftIcon={<Pencil className="w-3 h-3" aria-hidden="true" />}
          onClick={onEdit}
          title={`Edit ${stage.display_name}`}
        >
          Edit
        </Button>

        {!stage.is_builtin && (
          <Button
            variant="ghost"
            size="xs"
            leftIcon={<Trash2 className="w-3 h-3" aria-hidden="true" />}
            onClick={onDelete}
            title={`Delete ${stage.display_name}`}
            className="text-[#92a4c9] hover:text-[#f87171] hover:bg-[#ef4444]/10"
          >
            Delete
          </Button>
        )}
      </div>
    </div>
  );
}

export default StageRow;
