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
import {
  SelectField,
  Toggle,
  Badge,
  type BadgeVariant,
} from "@/components/ui/Select";
import { toast } from "@/components/ui/Toast";
import { useAgentConfig, useUpdateAgentConfig } from "@/hooks/useAgentConfigs";
import { useLLMProfiles } from "@/hooks/useLLMProfiles";
import { cn } from "@/lib/utils";
import type { LLMProfileResponse, AgentStage } from "@/types";

// ─────────────────────────────────────────────────────────────────────────────
// Zod schema
// ─────────────────────────────────────────────────────────────────────────────

const schema = z.object({
  display_name: z
    .string()
    .min(1, "Display name is required")
    .max(150, "Must be 150 characters or less"),
  llm_profile_id: z.string().nullable().optional(),
  role: z.string().min(1, "Role is required"),
  goal: z.string().min(1, "Goal is required"),
  backstory: z.string().min(1, "Backstory is required"),
  max_iter: z
    .number({ invalid_type_error: "Must be a number" })
    .int("Must be a whole number")
    .min(1, "Minimum is 1")
    .max(50, "Maximum is 50"),
  enabled: z.boolean(),
  verbose: z.boolean(),
});

type FormValues = z.infer<typeof schema>;

// ─────────────────────────────────────────────────────────────────────────────
// Props
// ─────────────────────────────────────────────────────────────────────────────

interface AgentDialogProps {
  open: boolean;
  onClose: () => void;
  agentId?: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// Loading skeleton
// ─────────────────────────────────────────────────────────────────────────────

function FormSkeleton() {
  return (
    <div aria-hidden="true" className="space-y-5 animate-pulse">
      {/* Agent ID badge row */}
      <div className="flex items-center gap-2 pb-1">
        <div className="h-3 w-14 bg-[#2b3b55] rounded" />
        <div className="h-5 w-40 bg-[#2b3b55] rounded" />
        <div className="h-5 w-20 bg-[#2b3b55] rounded-md" />
      </div>

      {/* Display Name */}
      <div className="space-y-1.5">
        <div className="h-3 bg-[#2b3b55] rounded w-1/4" />
        <div className="h-9 bg-[#2b3b55] rounded-lg" />
      </div>

      {/* LLM Profile */}
      <div className="space-y-1.5">
        <div className="h-3 bg-[#2b3b55] rounded w-1/3" />
        <div className="h-9 bg-[#2b3b55] rounded-lg" />
      </div>

      {/* Divider */}
      <div className="border-t border-[#2b3b55]" />

      {/* Role */}
      <div className="space-y-1.5">
        <div className="h-3 bg-[#2b3b55] rounded w-1/6" />
        <div className="h-16 bg-[#2b3b55] rounded-lg" />
      </div>

      {/* Goal */}
      <div className="space-y-1.5">
        <div className="h-3 bg-[#2b3b55] rounded w-1/6" />
        <div className="h-16 bg-[#2b3b55] rounded-lg" />
      </div>

      {/* Backstory */}
      <div className="space-y-1.5">
        <div className="h-3 bg-[#2b3b55] rounded w-1/5" />
        <div className="h-20 bg-[#2b3b55] rounded-lg" />
      </div>

      {/* Divider */}
      <div className="border-t border-[#2b3b55]" />

      {/* Max Iterations */}
      <div className="space-y-1.5">
        <div className="h-3 bg-[#2b3b55] rounded w-1/4" />
        <div className="h-9 bg-[#2b3b55] rounded-lg w-1/3" />
      </div>

      {/* Toggles */}
      <div className="flex items-center gap-8 pt-1">
        <div className="space-y-2">
          <div className="h-3 bg-[#2b3b55] rounded w-12" />
          <div className="h-5 w-10 bg-[#2b3b55] rounded-full" />
        </div>
        <div className="space-y-2">
          <div className="h-3 bg-[#2b3b55] rounded w-12" />
          <div className="h-5 w-10 bg-[#2b3b55] rounded-full" />
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Stage badge variant map
// ─────────────────────────────────────────────────────────────────────────────

const STAGE_BADGE_VARIANT: Record<AgentStage, BadgeVariant> = {
  ingestion: "primary",
  testcase: "info",
  execution: "warning",
  reporting: "success",
};

// ─────────────────────────────────────────────────────────────────────────────
// AgentDialog
// ─────────────────────────────────────────────────────────────────────────────

export function AgentDialog({ open, onClose, agentId }: AgentDialogProps) {
  // ── Data fetching ──────────────────────────────────────────────────────────
  const { data: agent, isLoading: isLoadingAgent } = useAgentConfig(
    open ? agentId : undefined,
  );

  const { data: profilesData } = useLLMProfiles({ limit: 100 });
  const updateMutation = useUpdateAgentConfig();

  // ── Form ───────────────────────────────────────────────────────────────────
  const {
    register,
    handleSubmit,
    control,
    reset,
    formState: { errors, isDirty },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      display_name: "",
      llm_profile_id: null,
      role: "",
      goal: "",
      backstory: "",
      max_iter: 15,
      enabled: true,
      verbose: false,
    },
  });

  // Populate form when agent data arrives
  React.useEffect(() => {
    if (agent) {
      reset({
        display_name: agent.display_name,
        llm_profile_id: agent.llm_profile_id ?? null,
        role: agent.role,
        goal: agent.goal,
        backstory: agent.backstory,
        max_iter: agent.max_iter,
        enabled: agent.enabled,
        verbose: agent.verbose,
      });
    }
  }, [agent, reset]);

  // Clear form when dialog closes so stale data doesn't flash on next open
  React.useEffect(() => {
    if (!open) {
      reset({
        display_name: "",
        llm_profile_id: null,
        role: "",
        goal: "",
        backstory: "",
        max_iter: 15,
        enabled: true,
        verbose: false,
      });
    }
  }, [open, reset]);

  // ── LLM profile options ────────────────────────────────────────────────────
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

  // ── Submit ─────────────────────────────────────────────────────────────────
  const onSubmit = async (values: FormValues) => {
    if (!agentId) return;
    try {
      await updateMutation.mutateAsync({
        agentId,
        payload: {
          display_name: values.display_name,
          llm_profile_id: values.llm_profile_id ?? null,
          role: values.role,
          goal: values.goal,
          backstory: values.backstory,
          max_iter: values.max_iter,
          enabled: values.enabled,
          verbose: values.verbose,
        },
      });
      toast.success(
        "Agent saved",
        `"${values.display_name}" has been updated successfully.`,
      );
      onClose();
    } catch {
      toast.error(
        "Save failed",
        "Could not update the agent configuration. Please try again.",
      );
    }
  };

  const handleClose = () => {
    if (!updateMutation.isPending) onClose();
  };

  const isLoadingForm = isLoadingAgent && !!agentId;
  const isBusy = updateMutation.isPending;

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <Modal
      open={open}
      onClose={handleClose}
      size="xl"
      disableBackdropClose={isBusy}
    >
      <ModalHeader
        title="Edit Agent Config"
        subtitle={agentId ?? undefined}
        icon={<Bot className="w-4 h-4" aria-hidden="true" />}
        onClose={handleClose}
      />

      <form onSubmit={handleSubmit(onSubmit)}>
        <ModalBody className="space-y-5">
          {isLoadingForm ? (
            <FormSkeleton />
          ) : (
            <>
              {/* ── Agent metadata badge row ───────────────────────────── */}
              {agent && (
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs text-[#92a4c9]">Agent ID</span>
                  <code
                    className={cn(
                      "px-2 py-0.5 text-xs font-mono rounded",
                      "bg-[#1e2a3d] border border-[#2b3b55] text-[#5b9eff]",
                    )}
                  >
                    {agent.agent_id}
                  </code>
                  <Badge
                    variant={
                      STAGE_BADGE_VARIANT[agent.stage as AgentStage] ??
                      "default"
                    }
                    size="xs"
                  >
                    {agent.stage}
                  </Badge>
                </div>
              )}

              {/* ── Display Name ───────────────────────────────────────── */}
              <FormField
                label="Display Name"
                id="display_name"
                required
                placeholder="e.g. Requirement Analyzer"
                error={errors.display_name?.message}
                {...register("display_name")}
              />

              {/* ── LLM Profile Override ───────────────────────────────── */}
              <Controller
                name="llm_profile_id"
                control={control}
                render={({ field }) => (
                  <SelectField
                    label="LLM Profile Override"
                    id="llm_profile_id"
                    hint="Leave as 'Use Default' to inherit the globally configured model."
                    options={profileOptions}
                    value={
                      field.value === null || field.value === undefined
                        ? ""
                        : String(field.value)
                    }
                    onChange={(e) => {
                      const val = e.target.value;
                      field.onChange(val === "" ? null : val);
                    }}
                    error={errors.llm_profile_id?.message}
                  />
                )}
              />

              <ModalDivider />

              {/* ── Role ──────────────────────────────────────────────── */}
              <TextareaField
                label="Role"
                id="role"
                required
                rows={2}
                placeholder="Describe the agent's role and responsibilities…"
                error={errors.role?.message}
                {...register("role")}
              />

              {/* ── Goal ──────────────────────────────────────────────── */}
              <TextareaField
                label="Goal"
                id="goal"
                required
                rows={2}
                placeholder="Describe what this agent aims to achieve…"
                error={errors.goal?.message}
                {...register("goal")}
              />

              {/* ── Backstory ─────────────────────────────────────────── */}
              <TextareaField
                label="Backstory"
                id="backstory"
                required
                rows={3}
                placeholder="Provide background context that shapes the agent's behaviour…"
                error={errors.backstory?.message}
                {...register("backstory")}
              />

              <ModalDivider />

              {/* ── Max Iterations ────────────────────────────────────── */}
              <FormField
                label="Max Iterations"
                id="max_iter"
                type="number"
                required
                hint="Maximum number of reasoning iterations the agent is allowed (1 – 50)."
                error={errors.max_iter?.message}
                className="max-w-[180px]"
                {...register("max_iter", { valueAsNumber: true })}
              />

              {/* ── Toggles ───────────────────────────────────────────── */}
              <div className="flex items-start gap-8 pt-1">
                {/* Enabled */}
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="enabled" className="mb-0">
                    Enabled
                  </Label>
                  <Controller
                    name="enabled"
                    control={control}
                    render={({ field }) => (
                      <div className="flex items-center gap-2">
                        <Toggle
                          checked={field.value}
                          onChange={field.onChange}
                          id="enabled"
                        />
                        <span
                          className={cn(
                            "text-xs font-medium",
                            field.value ? "text-[#4ade80]" : "text-[#92a4c9]",
                          )}
                        >
                          {field.value ? "Active" : "Inactive"}
                        </span>
                      </div>
                    )}
                  />
                </div>

                {/* Verbose */}
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="verbose" className="mb-0">
                    Verbose
                  </Label>
                  <Controller
                    name="verbose"
                    control={control}
                    render={({ field }) => (
                      <div className="flex items-center gap-2">
                        <Toggle
                          checked={field.value}
                          onChange={field.onChange}
                          id="verbose"
                        />
                        <span
                          className={cn(
                            "text-xs font-medium",
                            field.value ? "text-[#5b9eff]" : "text-[#92a4c9]",
                          )}
                        >
                          {field.value ? "On" : "Off"}
                        </span>
                      </div>
                    )}
                  />
                </div>
              </div>
            </>
          )}
        </ModalBody>

        <ModalFooter>
          <Button
            type="button"
            variant="secondary"
            onClick={handleClose}
            disabled={isBusy}
          >
            Cancel
          </Button>
          <Button
            type="submit"
            variant="primary"
            loading={isBusy}
            disabled={isLoadingForm || (!isDirty && !isBusy)}
          >
            Save Changes
          </Button>
        </ModalFooter>
      </form>
    </Modal>
  );
}

export default AgentDialog;
