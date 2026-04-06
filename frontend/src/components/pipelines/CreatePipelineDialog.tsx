"use client";

import React, { useEffect } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useRouter } from "next/navigation";
import { X, GitBranch, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { useCreateTemplate } from "@/hooks/usePipelineTemplates";

// ─────────────────────────────────────────────────────────────────────────────
// Schema
// ─────────────────────────────────────────────────────────────────────────────

const schema = z.object({
  name: z.string().min(1, "Name is required").max(80),
  template_id: z
    .string()
    .min(1, "ID is required")
    .max(50)
    .regex(/^[a-z0-9_-]+$/, "Only lowercase letters, numbers, _ and - allowed"),
  description: z.string().max(300).optional(),
  tags: z.string().optional(),
});

type FormValues = z.infer<typeof schema>;

// ─────────────────────────────────────────────────────────────────────────────
// CreatePipelineDialog
// ─────────────────────────────────────────────────────────────────────────────

interface CreatePipelineDialogProps {
  open: boolean;
  onClose: () => void;
}

export function CreatePipelineDialog({ open, onClose }: CreatePipelineDialogProps) {
  const router = useRouter();
  const createMutation = useCreateTemplate();

  const {
    register,
    handleSubmit,
    reset,
    setValue,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { name: "", template_id: "", description: "", tags: "" },
  });

  const nameValue = watch("name");

  // Auto-generate template_id from name
  useEffect(() => {
    const generated = nameValue
      .toLowerCase()
      .trim()
      .replace(/\s+/g, "_")
      .replace(/[^a-z0-9_-]/g, "")
      .slice(0, 50);
    setValue("template_id", generated);
  }, [nameValue, setValue]);

  // Reset form when dialog opens
  useEffect(() => {
    if (open) {
      reset();
    }
  }, [open, reset]);

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open, onClose]);

  const onSubmit = async (values: FormValues) => {
    const tags = values.tags
      ? values.tags
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean)
      : [];

    const created = await createMutation.mutateAsync({
      name: values.name,
      template_id: values.template_id,
      description: values.description ?? "",
      tags,
      nodes: [],
      edges: [],
    });

    onClose();
    router.push(`/pipelines/${created.template_id}`);
  };

  if (!open) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm"
        aria-hidden="true"
        onClick={onClose}
      />

      {/* Dialog */}
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="create-pipeline-title"
        className={cn(
          "fixed inset-0 z-50 flex items-center justify-center p-4",
          "pointer-events-none",
        )}
      >
        <div
          className={cn(
            "relative w-full max-w-md rounded-2xl",
            "bg-[#18202F] border border-[#2b3b55]",
            "shadow-2xl pointer-events-auto",
          )}
          onClick={(e) => e.stopPropagation()}
        >
          {/* ── Header ── */}
          <div className="flex items-center gap-3 px-5 py-4 border-b border-[#2b3b55]">
            <div className="w-8 h-8 rounded-lg bg-[#135bec]/15 flex items-center justify-center shrink-0">
              <GitBranch className="w-4 h-4 text-[#5b9eff]" />
            </div>
            <h2 id="create-pipeline-title" className="text-sm font-semibold text-white">
              New Pipeline Template
            </h2>
            <button
              type="button"
              onClick={onClose}
              className={cn(
                "ml-auto w-7 h-7 rounded-lg flex items-center justify-center",
                "text-[#3d5070] hover:text-white hover:bg-[#1e2a3d]",
                "transition-colors duration-150",
              )}
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* ── Form ── */}
          <form onSubmit={handleSubmit(onSubmit)} className="p-5 space-y-4">
            {/* Name */}
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-[#92a4c9]">
                Pipeline Name <span className="text-red-400">*</span>
              </label>
              <input
                {...register("name")}
                placeholder="e.g. Auto Testing Pipeline"
                className={cn(
                  "w-full h-9 px-3 rounded-lg text-sm",
                  "bg-[#1e2a3d] border text-white placeholder-[#3d5070]",
                  "focus:outline-none focus:ring-2 focus:ring-[#135bec]/50 focus:border-[#135bec]",
                  "transition-colors duration-150",
                  errors.name ? "border-red-500/60" : "border-[#2b3b55]",
                )}
              />
              {errors.name && (
                <p className="text-xs text-red-400">{errors.name.message}</p>
              )}
            </div>

            {/* Template ID */}
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-[#92a4c9]">
                Template ID <span className="text-red-400">*</span>
              </label>
              <input
                {...register("template_id")}
                placeholder="auto_generated_from_name"
                className={cn(
                  "w-full h-9 px-3 rounded-lg text-sm font-mono",
                  "bg-[#1e2a3d] border text-white placeholder-[#3d5070]",
                  "focus:outline-none focus:ring-2 focus:ring-[#135bec]/50 focus:border-[#135bec]",
                  "transition-colors duration-150",
                  errors.template_id ? "border-red-500/60" : "border-[#2b3b55]",
                )}
              />
              {errors.template_id ? (
                <p className="text-xs text-red-400">{errors.template_id.message}</p>
              ) : (
                <p className="text-xs text-[#3d5070]">
                  Unique identifier — auto-generated from name
                </p>
              )}
            </div>

            {/* Description */}
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-[#92a4c9]">
                Description
              </label>
              <textarea
                {...register("description")}
                placeholder="What does this pipeline do?"
                rows={3}
                className={cn(
                  "w-full px-3 py-2 rounded-lg text-sm resize-none",
                  "bg-[#1e2a3d] border border-[#2b3b55] text-white placeholder-[#3d5070]",
                  "focus:outline-none focus:ring-2 focus:ring-[#135bec]/50 focus:border-[#135bec]",
                  "transition-colors duration-150",
                )}
              />
              {errors.description && (
                <p className="text-xs text-red-400">{errors.description.message}</p>
              )}
            </div>

            {/* Tags */}
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-[#92a4c9]">
                Tags
              </label>
              <input
                {...register("tags")}
                placeholder="testing, automation, v3  (comma-separated)"
                className={cn(
                  "w-full h-9 px-3 rounded-lg text-sm",
                  "bg-[#1e2a3d] border border-[#2b3b55] text-white placeholder-[#3d5070]",
                  "focus:outline-none focus:ring-2 focus:ring-[#135bec]/50 focus:border-[#135bec]",
                  "transition-colors duration-150",
                )}
              />
              <p className="text-xs text-[#3d5070]">Separate multiple tags with commas</p>
            </div>

            {/* Error from mutation */}
            {createMutation.isError && (
              <p className="text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
                {createMutation.error?.message ?? "Failed to create pipeline"}
              </p>
            )}

            {/* Actions */}
            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={onClose}
                className={cn(
                  "h-9 px-4 rounded-lg text-sm",
                  "text-[#92a4c9] hover:text-white border border-[#2b3b55]",
                  "hover:bg-[#1e2a3d] transition-all duration-150",
                )}
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={isSubmitting || createMutation.isPending}
                className={cn(
                  "flex items-center gap-2 h-9 px-4 rounded-lg text-sm font-medium",
                  "bg-[#135bec] text-white hover:bg-[#1a6aff]",
                  "disabled:opacity-50 disabled:cursor-not-allowed",
                  "transition-colors duration-150",
                )}
              >
                {(isSubmitting || createMutation.isPending) && (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                )}
                Create & Open Builder
              </button>
            </div>
          </form>
        </div>
      </div>
    </>
  );
}
