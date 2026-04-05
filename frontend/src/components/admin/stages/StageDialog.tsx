"use client";

import * as React from "react";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Layers } from "lucide-react";

import {
  Modal,
  ModalHeader,
  ModalBody,
  ModalFooter,
  ModalDivider,
} from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { FormField, TextareaField, Label } from "@/components/ui/Input";
import { SelectField, Toggle } from "@/components/ui/Select";
import { toast } from "@/components/ui/Toast";
import {
  useStageConfig,
  useCreateStageConfig,
  useUpdateStageConfig,
} from "@/hooks/useStageConfigs";
import type { StageCrewType } from "@/types";

// ─────────────────────────────────────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────────────────────────────────────

const CREW_TYPE_OPTIONS = [
  { value: "pure_python", label: "Pure Python" },
  { value: "crewai_sequential", label: "CrewAI Sequential" },
  { value: "crewai_hierarchical", label: "CrewAI Hierarchical" },
];

// ─────────────────────────────────────────────────────────────────────────────
// Schema
// ─────────────────────────────────────────────────────────────────────────────

const schema = z.object({
  stage_id: z
    .string()
    .min(3, "Min 3 characters")
    .max(50, "Max 50 characters")
    .regex(/^[a-z][a-z0-9_]+$/, "Must be snake_case (e.g. my_stage)"),
  display_name: z
    .string()
    .min(2, "Min 2 characters")
    .max(150, "Max 150 characters"),
  description: z.string().max(500, "Max 500 characters").optional(),
  order: z
    .number({ invalid_type_error: "Must be a number" })
    .int()
    .min(1, "Min 1"),
  crew_type: z.enum(["pure_python", "crewai_sequential", "crewai_hierarchical"]),
  timeout_seconds: z
    .number({ invalid_type_error: "Must be a number" })
    .int()
    .min(30, "Min 30s")
    .max(3600, "Max 3600s"),
  enabled: z.boolean(),
});

type FormValues = z.infer<typeof schema>;

// ─────────────────────────────────────────────────────────────────────────────
// Default values
// ─────────────────────────────────────────────────────────────────────────────

const DEFAULT_VALUES: FormValues = {
  stage_id: "",
  display_name: "",
  description: "",
  order: 500,
  crew_type: "crewai_sequential",
  timeout_seconds: 300,
  enabled: true,
};

// ─────────────────────────────────────────────────────────────────────────────
// Props
// ─────────────────────────────────────────────────────────────────────────────

interface StageDialogProps {
  open: boolean;
  onClose: () => void;
  /** If provided: edit mode. If undefined: create mode. */
  stageId?: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// StageDialog
// ─────────────────────────────────────────────────────────────────────────────

export function StageDialog({ open, onClose, stageId }: StageDialogProps) {
  const isEdit = Boolean(stageId);

  const { data: stage, isLoading: isLoadingStage } = useStageConfig(
    open && isEdit ? stageId : undefined,
  );

  const createMutation = useCreateStageConfig();
  const updateMutation = useUpdateStageConfig();

  const {
    register,
    handleSubmit,
    control,
    reset,
    formState: { errors, isDirty },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: DEFAULT_VALUES,
  });

  // Populate form when editing an existing stage
  React.useEffect(() => {
    if (stage && isEdit) {
      reset({
        stage_id: stage.stage_id,
        display_name: stage.display_name,
        description: stage.description ?? "",
        order: stage.order,
        crew_type: stage.crew_type,
        timeout_seconds: stage.timeout_seconds,
        enabled: stage.enabled,
      });
    }
  }, [stage, isEdit, reset]);

  // Reset to blank values when dialog closes
  React.useEffect(() => {
    if (!open) {
      reset(DEFAULT_VALUES);
    }
  }, [open, reset]);

  // ── Submit ──────────────────────────────────────────────────────────────────

  const onSubmit = async (values: FormValues) => {
    try {
      if (isEdit && stageId) {
        await updateMutation.mutateAsync({
          stageId,
          payload: {
            display_name: values.display_name,
            description: values.description ?? "",
            order: values.order,
            crew_type: values.crew_type as StageCrewType,
            timeout_seconds: values.timeout_seconds,
            enabled: values.enabled,
          },
        });
        toast.success(
          "Stage updated",
          `"${values.display_name}" has been saved.`,
        );
      } else {
        await createMutation.mutateAsync({
          stage_id: values.stage_id,
          display_name: values.display_name,
          description: values.description ?? "",
          order: values.order,
          crew_type: values.crew_type as StageCrewType,
          timeout_seconds: values.timeout_seconds,
          enabled: values.enabled,
        });
        toast.success(
          "Stage created",
          `"${values.display_name}" has been added.`,
        );
      }
      onClose();
    } catch {
      toast.error(
        isEdit ? "Update failed" : "Create failed",
        "Could not save the stage configuration. Please try again.",
      );
    }
  };

  // ── Derived ─────────────────────────────────────────────────────────────────

  const isBusy = createMutation.isPending || updateMutation.isPending;
  const isLoadingForm = isLoadingStage && isEdit;

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <Modal open={open} onClose={onClose} size="lg">
      <ModalHeader
        title={isEdit ? "Edit Stage" : "Create Stage"}
        subtitle={
          isEdit
            ? `Editing stage: ${stageId}`
            : "Add a new pipeline stage"
        }
        onClose={onClose}
        icon={<Layers className="w-4 h-4" aria-hidden="true" />}
      />

      <ModalBody>
        {isLoadingForm ? (
          /* ── Loading skeleton ── */
          <div className="space-y-5 animate-pulse" aria-hidden="true">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="space-y-1.5">
                <div className="h-3 bg-[#2b3b55] rounded w-1/4" />
                <div className="h-9 bg-[#2b3b55] rounded-lg" />
              </div>
            ))}
          </div>
        ) : (
          <form
            id="stage-form"
            onSubmit={handleSubmit(onSubmit)}
            className="space-y-5"
          >
            {/* ── Stage ID (create only) ── */}
            {!isEdit && (
              <FormField
                label="Stage ID"
                id="stage_id"
                placeholder="e.g. security_scan"
                required
                hint="Unique snake_case identifier. Cannot be changed after creation."
                error={errors.stage_id?.message}
                {...register("stage_id")}
              />
            )}

            {/* ── Display Name ── */}
            <FormField
              label="Display Name"
              id="display_name"
              placeholder="e.g. Security Scan"
              required
              error={errors.display_name?.message}
              {...register("display_name")}
            />

            {/* ── Description ── */}
            <TextareaField
              label="Description"
              id="description"
              placeholder="Brief description of what this stage does…"
              rows={2}
              error={errors.description?.message}
              {...register("description")}
            />

            <ModalDivider />

            {/* ── Order + Timeout row ── */}
            <div className="grid grid-cols-2 gap-4">
              <FormField
                label="Order"
                id="order"
                type="number"
                placeholder="e.g. 500"
                required
                hint="Stages run in ascending order"
                error={errors.order?.message}
                {...register("order", { valueAsNumber: true })}
              />
              <FormField
                label="Timeout (seconds)"
                id="timeout_seconds"
                type="number"
                placeholder="e.g. 300"
                required
                hint="30 – 3600 seconds"
                error={errors.timeout_seconds?.message}
                {...register("timeout_seconds", { valueAsNumber: true })}
              />
            </div>

            {/* ── Crew Type ── */}
            <Controller
              control={control}
              name="crew_type"
              render={({ field }) => (
                <SelectField
                  label="Crew Type"
                  id="crew_type"
                  required
                  disabled={isEdit && stage?.is_builtin}
                  hint={
                    isEdit && stage?.is_builtin
                      ? "Cannot change crew type for builtin stages"
                      : undefined
                  }
                  options={CREW_TYPE_OPTIONS}
                  error={errors.crew_type?.message}
                  value={field.value}
                  onChange={field.onChange}
                />
              )}
            />

            {/* ── Enabled toggle ── */}
            <div className="flex items-center justify-between py-1">
              <div>
                <Label htmlFor="enabled" className="mb-0">
                  Enabled
                </Label>
                <p className="text-xs text-[#3d5070] mt-0.5">
                  Disabled stages are skipped during pipeline execution
                </p>
              </div>
              <Controller
                control={control}
                name="enabled"
                render={({ field }) => (
                  <Toggle
                    id="enabled"
                    checked={field.value}
                    onChange={field.onChange}
                    size="md"
                  />
                )}
              />
            </div>
          </form>
        )}
      </ModalBody>

      <ModalFooter>
        <Button variant="ghost" onClick={onClose} disabled={isBusy}>
          Cancel
        </Button>
        <Button
          type="submit"
          form="stage-form"
          variant="primary"
          loading={isBusy}
          disabled={isEdit && !isDirty}
        >
          {isEdit ? "Save Changes" : "Create Stage"}
        </Button>
      </ModalFooter>
    </Modal>
  );
}

export default StageDialog;
