"use client";

import * as React from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { X } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { FormField, Label } from "@/components/ui/Input";
import { cn } from "@/lib/utils";
import type { StageConfigCreate } from "@/types";

// ─────────────────────────────────────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────────────────────────────────────

const DEFAULT_COLOR = "#4b6a9e";

// ─────────────────────────────────────────────────────────────────────────────
// Validation schema
// ─────────────────────────────────────────────────────────────────────────────

const addStageSchema = z.object({
  stage_id: z
    .string()
    .min(2, "Min 2 characters")
    .max(50, "Max 50 characters")
    .regex(
      /^[a-z][a-z0-9_]+$/,
      "Must start with a lowercase letter and contain only a–z, 0–9, _",
    ),
  display_name: z
    .string()
    .min(2, "Min 2 characters")
    .max(100, "Max 100 characters"),
  color: z.string().optional(),
  icon: z.string().optional(),
});

type FormValues = z.infer<typeof addStageSchema>;

// ─────────────────────────────────────────────────────────────────────────────
// Props
// ─────────────────────────────────────────────────────────────────────────────

export interface AddStageFormProps {
  onSubmit: (data: StageConfigCreate) => Promise<void>;
  onCancel: () => void;
  isLoading: boolean;
}

// ─────────────────────────────────────────────────────────────────────────────
// AddStageForm
// ─────────────────────────────────────────────────────────────────────────────

export function AddStageForm({
  onSubmit,
  onCancel,
  isLoading,
}: AddStageFormProps) {
  // Track the color value separately so the color picker and text input stay in sync
  const [colorHex, setColorHex] = React.useState(DEFAULT_COLOR);

  const {
    register,
    handleSubmit,
    setValue,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(addStageSchema),
    defaultValues: {
      stage_id: "",
      display_name: "",
      color: DEFAULT_COLOR,
      icon: "",
    },
  });

  // ── Color sync helpers ─────────────────────────────────────────────────────

  const handleColorPickerChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setColorHex(val);
    setValue("color", val);
  };

  const handleColorTextChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setColorHex(val);
    setValue("color", val);
  };

  // ── Submit ─────────────────────────────────────────────────────────────────

  const handleFormSubmit = async (values: FormValues) => {
    await onSubmit({
      stage_id: values.stage_id,
      display_name: values.display_name,
      color: values.color?.trim() || null,
      icon: values.icon?.trim() || null,
      enabled: true,
    });
  };

  // ── Shared styles ──────────────────────────────────────────────────────────

  const bareInputCls = cn(
    "w-full h-9 rounded-lg bg-[#101622] border border-[#2b3b55] px-3",
    "text-sm text-white placeholder:text-[#3d5070]",
    "outline-none focus:ring-2 focus:ring-[#135bec] focus:border-[#135bec]",
    "transition-colors duration-150",
    "disabled:opacity-50 disabled:cursor-not-allowed",
  );

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div
      className={cn(
        "rounded-xl border border-[#135bec]/30 bg-[#1a2438]",
        "px-4 pt-4 pb-3",
      )}
      role="region"
      aria-label="Add new stage"
    >
      {/* ── Card header ─────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-white leading-snug">
          New Stage
        </h3>
        <button
          type="button"
          onClick={onCancel}
          aria-label="Cancel adding stage"
          className={cn(
            "p-1.5 rounded-lg text-[#92a4c9]",
            "hover:bg-[#2b3b55] hover:text-white",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#135bec]",
            "transition-colors duration-150",
          )}
        >
          <X className="w-3.5 h-3.5" aria-hidden="true" />
        </button>
      </div>

      {/* ── Form ────────────────────────────────────────────────────────── */}
      <form
        id="add-stage-form"
        onSubmit={handleSubmit(handleFormSubmit)}
        noValidate
        className="space-y-3"
      >
        {/* Stage ID */}
        <FormField
          label="Stage ID"
          id="stage_id"
          placeholder="e.g. security_review"
          required
          hint="Unique snake_case ID (e.g. security_review)"
          error={errors.stage_id?.message}
          disabled={isLoading}
          {...register("stage_id")}
        />

        {/* Display Name */}
        <FormField
          label="Display Name"
          id="display_name"
          placeholder="e.g. Security Review"
          required
          error={errors.display_name?.message}
          disabled={isLoading}
          {...register("display_name")}
        />

        {/* Color + Icon row */}
        <div className="flex gap-3">
          {/* Color */}
          <div className="flex flex-col gap-1.5 flex-1 min-w-0">
            <Label htmlFor="stage_color_text">Color</Label>
            <div className="flex items-center gap-2">
              {/* Native color picker swatch */}
              <input
                type="color"
                id="stage_color_picker"
                value={colorHex}
                onChange={handleColorPickerChange}
                disabled={isLoading}
                aria-label="Pick stage colour"
                className={cn(
                  "w-9 h-9 shrink-0 rounded-lg border border-[#2b3b55]",
                  "bg-[#101622] cursor-pointer p-0.5",
                  "focus:outline-none focus:ring-2 focus:ring-[#135bec]",
                  "disabled:opacity-50 disabled:cursor-not-allowed",
                )}
              />
              {/* Hex text input */}
              <input
                type="text"
                id="stage_color_text"
                value={colorHex}
                onChange={handleColorTextChange}
                disabled={isLoading}
                placeholder={DEFAULT_COLOR}
                aria-label="Colour hex value"
                className={cn(bareInputCls, "font-mono")}
              />
            </div>
          </div>

          {/* Icon */}
          <div className="flex flex-col gap-1.5 flex-1 min-w-0">
            <Label htmlFor="stage_icon">Icon</Label>
            <input
              type="text"
              id="stage_icon"
              placeholder="e.g. flask-conical, shield"
              disabled={isLoading}
              aria-label="Icon name"
              className={bareInputCls}
              {...register("icon")}
            />
            {errors.icon?.message && (
              <p className="text-xs text-[#ef4444]" role="alert">
                {errors.icon.message}
              </p>
            )}
          </div>
        </div>
      </form>

      {/* ── Footer actions ───────────────────────────────────────────────── */}
      <div className="flex items-center justify-end gap-2 mt-4">
        <Button
          variant="ghost"
          size="sm"
          onClick={onCancel}
          disabled={isLoading}
        >
          Cancel
        </Button>
        <Button
          type="submit"
          form="add-stage-form"
          variant="primary"
          size="sm"
          loading={isLoading}
        >
          Add Stage
        </Button>
      </div>
    </div>
  );
}

export default AddStageForm;
