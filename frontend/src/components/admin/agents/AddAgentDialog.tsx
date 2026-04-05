"use client";

import * as React from "react";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Bot } from "lucide-react";

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
import { useCreateAgentConfig } from "@/hooks/useAgentConfigs";
import { useLLMProfiles } from "@/hooks/useLLMProfiles";
import { useStageConfigs } from "@/hooks/useStageConfigs";
import type { LLMProfileResponse } from "@/types";

// ─────────────────────────────────────────────────────────────────────────────
// Validation schema
// ─────────────────────────────────────────────────────────────────────────────

const createAgentSchema = z.object({
  agent_id: z
    .string()
    .min(3, "Min 3 characters")
    .max(50, "Max 50 characters")
    .regex(/^[a-z][a-z0-9_]+$/, "Must be snake_case (e.g. my_agent)"),
  display_name: z
    .string()
    .min(2, "Min 2 characters")
    .max(150, "Max 150 characters"),
  stage: z.string().min(1, "Select a stage"),
  role: z.string().min(10, "Role must be at least 10 characters"),
  goal: z.string().min(10, "Goal must be at least 10 characters"),
  backstory: z.string().min(10, "Backstory must be at least 10 characters"),
  llm_profile_id: z.number().nullable().optional(),
  max_iter: z
    .number({ invalid_type_error: "Must be a number" })
    .int()
    .min(1, "Min 1")
    .max(50, "Max 50")
    .default(5),
  enabled: z.boolean().default(true),
  verbose: z.boolean().default(false),
});

type FormValues = z.infer<typeof createAgentSchema>;

// ─────────────────────────────────────────────────────────────────────────────
// Props
// ─────────────────────────────────────────────────────────────────────────────

interface AddAgentDialogProps {
  open: boolean;
  onClose: () => void;
}

// ─────────────────────────────────────────────────────────────────────────────
// AddAgentDialog
// ─────────────────────────────────────────────────────────────────────────────

export function AddAgentDialog({ open, onClose }: AddAgentDialogProps) {
  const createMutation = useCreateAgentConfig();
  const { data: profilesData } = useLLMProfiles({ limit: 100 });
  const { data: stages } = useStageConfigs();

  const {
    register,
    handleSubmit,
    control,
    reset,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(createAgentSchema),
    defaultValues: {
      agent_id: "",
      display_name: "",
      stage: "",
      role: "",
      goal: "",
      backstory: "",
      llm_profile_id: null,
      max_iter: 5,
      enabled: true,
      verbose: false,
    },
  });

  // Reset form whenever the dialog is closed
  React.useEffect(() => {
    if (!open) {
      reset();
    }
  }, [open, reset]);

  // ── Dropdown options ───────────────────────────────────────────────────────

  const profileOptions = React.useMemo(() => {
    const profiles: LLMProfileResponse[] = profilesData?.items ?? [];
    return [
      { value: "", label: "Use Default" },
      ...profiles.map((p: LLMProfileResponse) => ({
        value: String(p.id),
        label: p.name + (p.is_default ? " (default)" : ""),
      })),
    ];
  }, [profilesData]);

  const stageOptions = React.useMemo(() => {
    if (!stages) return [{ value: "", label: "Loading stages…" }];
    return [
      { value: "", label: "Select a stage…" },
      ...stages.map((s) => ({
        value: s.stage_id,
        label: s.display_name,
      })),
    ];
  }, [stages]);

  // ── Submit ─────────────────────────────────────────────────────────────────

  const onSubmit = async (values: FormValues) => {
    try {
      await createMutation.mutateAsync({
        agent_id: values.agent_id,
        display_name: values.display_name,
        stage: values.stage,
        role: values.role,
        goal: values.goal,
        backstory: values.backstory,
        llm_profile_id: values.llm_profile_id ?? null,
        max_iter: values.max_iter,
        enabled: values.enabled,
        verbose: values.verbose,
      });
      toast.success(
        "Agent created",
        `"${values.display_name}" has been added to the ${values.stage} stage.`,
      );
      onClose();
    } catch {
      toast.error(
        "Create failed",
        "Could not create the agent. Please try again.",
      );
    }
  };

  const isBusy = createMutation.isPending;

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <Modal open={open} onClose={onClose} size="lg">
      <ModalHeader
        title="Create New Agent"
        subtitle="Add a custom agent to a pipeline stage"
        onClose={onClose}
        icon={<Bot className="w-4 h-4" aria-hidden="true" />}
      />

      <ModalBody>
        <form
          id="add-agent-form"
          onSubmit={handleSubmit(onSubmit)}
          className="space-y-5"
        >
          {/* ── Agent ID ──────────────────────────────────────────────────── */}
          <FormField
            label="Agent ID"
            id="agent_id"
            placeholder="e.g. security_auditor"
            required
            hint="Unique snake_case identifier (3–50 chars). Cannot be changed."
            error={errors.agent_id?.message}
            {...register("agent_id")}
          />

          {/* ── Display Name ──────────────────────────────────────────────── */}
          <FormField
            label="Display Name"
            id="display_name"
            placeholder="e.g. Security Auditor"
            required
            error={errors.display_name?.message}
            {...register("display_name")}
          />

          {/* ── Pipeline Stage ────────────────────────────────────────────── */}
          <Controller
            control={control}
            name="stage"
            render={({ field }) => (
              <SelectField
                label="Pipeline Stage"
                id="stage"
                required
                placeholder="Select a stage…"
                options={stageOptions}
                error={errors.stage?.message}
                value={field.value}
                onChange={field.onChange}
              />
            )}
          />

          {/* ── LLM Profile ───────────────────────────────────────────────── */}
          <Controller
            control={control}
            name="llm_profile_id"
            render={({ field }) => (
              <SelectField
                label="LLM Profile"
                id="llm_profile_id"
                options={profileOptions}
                hint="Leave as 'Use Default' to inherit the pipeline's LLM profile"
                error={errors.llm_profile_id?.message}
                value={
                  field.value !== null && field.value !== undefined
                    ? String(field.value)
                    : ""
                }
                onChange={(e) => {
                  const v = e.target.value;
                  field.onChange(v === "" ? null : Number(v));
                }}
              />
            )}
          />

          <ModalDivider />

          {/* ── Role ──────────────────────────────────────────────────────── */}
          <TextareaField
            label="Role"
            id="role"
            placeholder="e.g. You are a security expert specialized in reviewing test cases for vulnerabilities…"
            required
            rows={3}
            error={errors.role?.message}
            {...register("role")}
          />

          {/* ── Goal ──────────────────────────────────────────────────────── */}
          <TextareaField
            label="Goal"
            id="goal"
            placeholder="e.g. Identify security gaps in the test coverage and suggest additional security test cases…"
            required
            rows={3}
            error={errors.goal?.message}
            {...register("goal")}
          />

          {/* ── Backstory ─────────────────────────────────────────────────── */}
          <TextareaField
            label="Backstory"
            id="backstory"
            placeholder="e.g. With years of penetration testing experience, you have a deep understanding of common attack vectors…"
            required
            rows={3}
            error={errors.backstory?.message}
            {...register("backstory")}
          />

          <ModalDivider />

          {/* ── Max Iterations ────────────────────────────────────────────── */}
          <FormField
            label="Max Iterations"
            id="max_iter"
            type="number"
            required
            hint="1–50 iterations per agent execution"
            error={errors.max_iter?.message}
            {...register("max_iter", { valueAsNumber: true })}
          />

          {/* ── Toggles row ───────────────────────────────────────────────── */}
          <div className="flex items-center gap-8">
            <div className="flex flex-col items-start gap-1">
              <Label className="mb-0">Enabled</Label>
              <Controller
                control={control}
                name="enabled"
                render={({ field }) => (
                  <Toggle
                    checked={field.value}
                    onChange={field.onChange}
                    size="sm"
                    label="Enabled"
                  />
                )}
              />
            </div>
            <div className="flex flex-col items-start gap-1">
              <Label className="mb-0">Verbose</Label>
              <Controller
                control={control}
                name="verbose"
                render={({ field }) => (
                  <Toggle
                    checked={field.value}
                    onChange={field.onChange}
                    size="sm"
                    label="Verbose"
                  />
                )}
              />
            </div>
          </div>
        </form>
      </ModalBody>

      <ModalFooter>
        <Button variant="ghost" onClick={onClose} disabled={isBusy}>
          Cancel
        </Button>
        <Button
          type="submit"
          form="add-agent-form"
          variant="primary"
          loading={isBusy}
        >
          Create Agent
        </Button>
      </ModalFooter>
    </Modal>
  );
}

export default AddAgentDialog;
