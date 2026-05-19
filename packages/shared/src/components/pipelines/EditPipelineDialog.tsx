"use client";

import * as React from "react";
import { GitBranch, Loader2 } from "lucide-react";

import {
  Modal,
  ModalHeader,
  ModalBody,
  ModalFooter,
} from "../ui/Modal";
import { toast } from "../ui/Toast";
import { cn } from "../../lib/utils";
import { useUpdateTemplate } from "../../hooks/usePipelineTemplates";
import type { PipelineTemplateListItem } from "../../types";

// ─────────────────────────────────────────────────────────────────────────────
// Props
// ─────────────────────────────────────────────────────────────────────────────

export interface EditPipelineDialogProps {
  open: boolean;
  onClose: () => void;
  template: PipelineTemplateListItem;
}

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

const NAME_MAX = 120;
const DESC_MAX = 500;
const TAG_MAX = 32;
const TAGS_MAX_COUNT = 10;

function tagsToInput(tags: readonly string[] | undefined): string {
  return (tags ?? []).join(", ");
}

function parseTagsInput(input: string): string[] {
  return Array.from(
    new Set(
      input
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean),
    ),
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// EditPipelineDialog
// ─────────────────────────────────────────────────────────────────────────────

export function EditPipelineDialog({
  open,
  onClose,
  template,
}: EditPipelineDialogProps) {
  const updateMutation = useUpdateTemplate(template.template_id);

  const [name, setName] = React.useState(template.name);
  const [description, setDescription] = React.useState(
    template.description ?? "",
  );
  const [tagsInput, setTagsInput] = React.useState(tagsToInput(template.tags));

  // Reset local state every time the dialog opens or the template changes
  React.useEffect(() => {
    if (open) {
      setName(template.name);
      setDescription(template.description ?? "");
      setTagsInput(tagsToInput(template.tags));
    }
  }, [open, template]);

  const trimmedName = name.trim();
  const trimmedDescription = description.trim();
  const parsedTags = parseTagsInput(tagsInput);

  const nameError =
    trimmedName.length === 0
      ? "Name is required."
      : trimmedName.length > NAME_MAX
        ? `Name must be ${NAME_MAX} characters or fewer.`
        : null;
  const descriptionError =
    trimmedDescription.length > DESC_MAX
      ? `Description must be ${DESC_MAX} characters or fewer.`
      : null;
  const tagsError =
    parsedTags.length > TAGS_MAX_COUNT
      ? `At most ${TAGS_MAX_COUNT} tags allowed.`
      : parsedTags.find((t) => t.length > TAG_MAX)
        ? `Each tag must be ${TAG_MAX} characters or fewer.`
        : null;

  const hasError = Boolean(nameError ?? descriptionError ?? tagsError);

  const originalTags = template.tags ?? [];
  const tagsChanged =
    parsedTags.length !== originalTags.length ||
    parsedTags.some((t, i) => t !== originalTags[i]);

  const dirty =
    trimmedName !== template.name ||
    trimmedDescription !== (template.description ?? "") ||
    tagsChanged;

  const handleSave = async () => {
    if (hasError || !dirty) return;

    try {
      const updated = await updateMutation.mutateAsync({
        name: trimmedName,
        description: trimmedDescription,
        tags: parsedTags,
      });
      toast.success(
        "Pipeline updated",
        `"${updated.name}" has been updated.`,
      );
      onClose();
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? (err instanceof Error ? err.message : "Update failed.");
      toast.error("Update failed", detail);
    }
  };

  const handleKeyDown = (
    e: React.KeyboardEvent<HTMLInputElement | HTMLTextAreaElement>,
  ) => {
    // Cmd/Ctrl + Enter = submit
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      handleSave();
    }
  };

  const inputBase = cn(
    "w-full px-3 rounded-lg text-sm",
    "bg-[#1e2a3d] border text-white placeholder-[#3d5070]",
    "focus:outline-none focus:ring-2 focus:ring-[#135bec]/50 focus:border-[#135bec]",
    "transition-colors duration-150",
  );

  return (
    <Modal
      open={open}
      onClose={updateMutation.isPending ? () => {} : onClose}
      size="md"
    >
      <ModalHeader
        title="Edit Pipeline Details"
        subtitle={`Update name, description, and tags for "${template.name}".`}
        onClose={updateMutation.isPending ? undefined : onClose}
        icon={<GitBranch className="w-4 h-4" aria-hidden="true" />}
      />

      <ModalBody className="space-y-4">
        {/* Name */}
        <div className="space-y-1.5">
          <label
            htmlFor="edit-pipeline-name"
            className="text-xs font-medium text-[#92a4c9]"
          >
            Pipeline Name <span className="text-red-400">*</span>
          </label>
          <input
            id="edit-pipeline-name"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={handleKeyDown}
            maxLength={NAME_MAX + 20}
            disabled={updateMutation.isPending}
            className={cn(
              inputBase,
              "h-9",
              nameError ? "border-red-500/60" : "border-[#2b3b55]",
            )}
          />
          {nameError ? (
            <p className="text-xs text-red-400">{nameError}</p>
          ) : (
            <p className="text-xs text-[#3d5070]">
              {trimmedName.length}/{NAME_MAX}
            </p>
          )}
        </div>

        {/* Description */}
        <div className="space-y-1.5">
          <label
            htmlFor="edit-pipeline-description"
            className="text-xs font-medium text-[#92a4c9]"
          >
            Description
          </label>
          <textarea
            id="edit-pipeline-description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={3}
            maxLength={DESC_MAX + 50}
            disabled={updateMutation.isPending}
            placeholder="What does this pipeline do?"
            className={cn(
              inputBase,
              "py-2 resize-none",
              descriptionError ? "border-red-500/60" : "border-[#2b3b55]",
            )}
          />
          {descriptionError ? (
            <p className="text-xs text-red-400">{descriptionError}</p>
          ) : (
            <p className="text-xs text-[#3d5070]">
              {trimmedDescription.length}/{DESC_MAX}
            </p>
          )}
        </div>

        {/* Tags */}
        <div className="space-y-1.5">
          <label
            htmlFor="edit-pipeline-tags"
            className="text-xs font-medium text-[#92a4c9]"
          >
            Tags
          </label>
          <input
            id="edit-pipeline-tags"
            type="text"
            value={tagsInput}
            onChange={(e) => setTagsInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={updateMutation.isPending}
            placeholder="testing, automation, v3"
            className={cn(
              inputBase,
              "h-9",
              tagsError ? "border-red-500/60" : "border-[#2b3b55]",
            )}
          />
          {tagsError ? (
            <p className="text-xs text-red-400">{tagsError}</p>
          ) : (
            <p className="text-xs text-[#3d5070]">
              Separate tags with commas — up to {TAGS_MAX_COUNT}.
            </p>
          )}

          {/* Tag preview chips */}
          {parsedTags.length > 0 && !tagsError && (
            <div className="flex flex-wrap gap-1.5 pt-1.5">
              {parsedTags.map((tag) => (
                <span
                  key={tag}
                  className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-[#2b3b55] text-[#92a4c9]"
                >
                  {tag}
                </span>
              ))}
            </div>
          )}
        </div>
      </ModalBody>

      <ModalFooter>
        <button
          type="button"
          onClick={onClose}
          disabled={updateMutation.isPending}
          className={cn(
            "h-9 px-4 rounded-lg text-sm",
            "text-[#92a4c9] hover:text-white border border-[#2b3b55]",
            "hover:bg-[#1e2a3d] transition-all duration-150",
            "disabled:opacity-50 disabled:cursor-not-allowed",
          )}
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={handleSave}
          disabled={updateMutation.isPending || hasError || !dirty}
          className={cn(
            "flex items-center gap-2 h-9 px-4 rounded-lg text-sm font-medium",
            "bg-[#135bec] text-white hover:bg-[#1a6aff]",
            "disabled:opacity-50 disabled:cursor-not-allowed",
            "transition-colors duration-150",
          )}
        >
          {updateMutation.isPending && (
            <Loader2 className="w-3.5 h-3.5 animate-spin" aria-hidden="true" />
          )}
          Save Changes
        </button>
      </ModalFooter>
    </Modal>
  );
}

export default EditPipelineDialog;
