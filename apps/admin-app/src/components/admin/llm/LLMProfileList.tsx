"use client";

import * as React from "react";
import { Brain, Plus, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/Modal";
import { toast } from "@/components/ui/Toast";
import {
  useLLMProfiles,
  useDeleteLLMProfile,
  useSetDefaultLLMProfile,
} from "@/hooks/useLLMProfiles";
import { cn } from "@/lib/utils";
import type { LLMProfileResponse } from "@/types";

import { LLMProfileCard } from "./LLMProfileCard";
import { LLMProfileDialog } from "./LLMProfileDialog";

// ─────────────────────────────────────────────────────────────────────────────
// Loading skeleton
// ─────────────────────────────────────────────────────────────────────────────

function ProfileCardSkeleton() {
  return (
    <div
      aria-hidden="true"
      className="rounded-xl border border-[#2b3b55] bg-[#18202F] animate-pulse overflow-hidden"
    >
      {/* Header */}
      <div className="flex items-start gap-3 px-4 pt-4 pb-3">
        <div className="w-10 h-10 rounded-lg bg-[#2b3b55] shrink-0" />
        <div className="flex-1 space-y-2 pt-0.5">
          <div className="h-3.5 bg-[#2b3b55] rounded-md w-2/5" />
          <div className="h-3 bg-[#2b3b55] rounded-md w-1/4" />
        </div>
      </div>

      {/* Divider */}
      <div className="mx-4 border-t border-[#2b3b55]/60" />

      {/* Stats */}
      <div className="px-4 py-3 grid grid-cols-2 gap-x-4 gap-y-3">
        <div className="col-span-2 space-y-1.5">
          <div className="h-2 bg-[#2b3b55] rounded w-1/6" />
          <div className="h-3 bg-[#2b3b55] rounded-md w-3/5" />
        </div>
        <div className="space-y-1.5">
          <div className="h-2 bg-[#2b3b55] rounded w-2/5" />
          <div className="h-3 bg-[#2b3b55] rounded-md w-1/4" />
        </div>
        <div className="space-y-1.5">
          <div className="h-2 bg-[#2b3b55] rounded w-2/5" />
          <div className="h-3 bg-[#2b3b55] rounded-md w-1/3" />
        </div>
      </div>

      {/* Footer */}
      <div className="mx-4 border-t border-[#2b3b55]/60" />
      <div className="flex items-center justify-between px-4 py-3">
        <div className="h-2.5 bg-[#2b3b55] rounded w-1/5" />
        <div className="flex gap-1.5">
          <div className="h-6 w-16 bg-[#2b3b55] rounded-md" />
          <div className="h-6 w-14 bg-[#2b3b55] rounded-md" />
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Empty state
// ─────────────────────────────────────────────────────────────────────────────

interface EmptyStateProps {
  onAdd: () => void;
}

function EmptyState({ onAdd }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-24 gap-5 text-center">
      <div
        className={cn(
          "w-18 h-18 rounded-2xl",
          "bg-[#135bec]/10 border border-[#135bec]/20",
          "flex items-center justify-center",
        )}
        style={{ width: "4.5rem", height: "4.5rem" }}
      >
        <Brain className="w-8 h-8 text-[#135bec]" aria-hidden="true" />
      </div>

      <div className="max-w-xs">
        <h3 className="text-base font-semibold text-white">
          No LLM profiles yet
        </h3>
        <p className="mt-1.5 text-sm text-[#92a4c9] leading-relaxed">
          Add a profile to connect your agents to an AI provider like OpenAI,
          Anthropic, or a local Ollama instance.
        </p>
      </div>

      <Button
        variant="primary"
        leftIcon={<Plus className="w-4 h-4" aria-hidden="true" />}
        onClick={onAdd}
      >
        Add First Profile
      </Button>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Error state
// ─────────────────────────────────────────────────────────────────────────────

interface ErrorStateProps {
  onRetry: () => void;
}

function ErrorState({ onRetry }: ErrorStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-20 gap-4 text-center">
      <div
        className={cn(
          "w-14 h-14 rounded-xl",
          "bg-[#ef4444]/10 border border-[#ef4444]/20",
          "flex items-center justify-center",
        )}
      >
        <Brain className="w-7 h-7 text-[#f87171]" aria-hidden="true" />
      </div>

      <div className="max-w-xs">
        <p className="text-sm font-semibold text-[#f87171]">
          Failed to load profiles
        </p>
        <p className="mt-1 text-xs text-[#92a4c9] leading-relaxed">
          Something went wrong while fetching your LLM profiles. Check your
          connection and try again.
        </p>
      </div>

      <Button
        variant="secondary"
        size="sm"
        leftIcon={<RefreshCw className="w-3.5 h-3.5" aria-hidden="true" />}
        onClick={onRetry}
      >
        Retry
      </Button>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// LLMProfileList
// ─────────────────────────────────────────────────────────────────────────────

export function LLMProfileList() {
  // ── Dialog / selection state ───────────────────────────────────────────────
  const [dialogOpen, setDialogOpen] = React.useState(false);
  const [editProfile, setEditProfile] = React.useState<
    LLMProfileResponse | undefined
  >(undefined);
  const [deleteConfirmId, setDeleteConfirmId] = React.useState<string | null>(
    null,
  );

  // ── Data fetching ──────────────────────────────────────────────────────────
  const { data, isLoading, isError, refetch } = useLLMProfiles({ limit: 100 });
  const deleteMutation = useDeleteLLMProfile();
  const setDefaultMutation = useSetDefaultLLMProfile();

  const profiles: LLMProfileResponse[] = data?.items ?? [];
  const total: number = data?.total ?? 0;

  // ── Handlers ───────────────────────────────────────────────────────────────

  const handleOpenCreate = () => {
    setEditProfile(undefined);
    setDialogOpen(true);
  };

  const handleDialogClose = () => {
    setDialogOpen(false);
    // Delay clearing editProfile so the closing animation doesn't flash
    setTimeout(() => setEditProfile(undefined), 250);
  };

  const handleEdit = (profile: LLMProfileResponse) => {
    setEditProfile(profile);
    setDialogOpen(true);
  };

  const handleDeleteRequest = (profile: LLMProfileResponse) => {
    setDeleteConfirmId(profile.id);
  };

  const handleDeleteCancel = () => {
    setDeleteConfirmId(null);
  };

  const handleDeleteConfirm = async () => {
    if (deleteConfirmId == null) return;
    try {
      await deleteMutation.mutateAsync(deleteConfirmId);
      toast.success("Profile deleted", "The LLM profile has been removed.");
    } catch {
      toast.error(
        "Delete failed",
        "Could not delete the profile. Please try again.",
      );
    } finally {
      setDeleteConfirmId(null);
    }
  };

  const handleSetDefault = async (profile: LLMProfileResponse) => {
    if (profile.is_default) return; // already default — no-op
    try {
      await setDefaultMutation.mutateAsync(profile.id);
      toast.success(
        "Default updated",
        `"${profile.name}" is now the default profile.`,
      );
    } catch {
      toast.error(
        "Update failed",
        "Could not set the default profile. Please try again.",
      );
    }
  };

  // Resolve the profile object for the delete confirmation message
  const profileToDelete = profiles.find((p) => p.id === deleteConfirmId);

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <>
      {/* ── Page header ──────────────────────────────────────────────────── */}
      <div className="flex items-start justify-between gap-4 mb-6">
        <div>
          <h2 className="text-lg font-semibold text-white leading-snug">
            LLM Profiles
          </h2>

          <p className="mt-0.5 text-sm text-[#92a4c9]">
            {isLoading ? (
              // Skeleton count line
              <span
                aria-hidden="true"
                className="inline-block h-3.5 w-20 bg-[#2b3b55] rounded animate-pulse"
              />
            ) : isError ? (
              <span className="text-[#f87171]">Could not load profiles</span>
            ) : (
              <>
                {total} <span>{total === 1 ? "profile" : "profiles"}</span>
              </>
            )}
          </p>
        </div>

        <Button
          variant="primary"
          size="sm"
          leftIcon={<Plus className="w-4 h-4" aria-hidden="true" />}
          onClick={handleOpenCreate}
          className="shrink-0"
        >
          New Profile
        </Button>
      </div>

      {/* ── Main content ─────────────────────────────────────────────────── */}
      {isLoading ? (
        // Loading — 3 skeleton cards
        <div
          role="status"
          aria-label="Loading profiles…"
          className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4"
        >
          <ProfileCardSkeleton />
          <ProfileCardSkeleton />
          <ProfileCardSkeleton />
          <span className="sr-only">Loading LLM profiles…</span>
        </div>
      ) : isError ? (
        // Error state
        <ErrorState onRetry={refetch} />
      ) : profiles.length === 0 ? (
        // Empty state
        <EmptyState onAdd={handleOpenCreate} />
      ) : (
        // Profile grid
        <div
          className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4"
          role="list"
          aria-label="LLM profiles"
        >
          {profiles.map((profile) => (
            <div key={profile.id} role="listitem">
              <LLMProfileCard
                profile={profile}
                onEdit={handleEdit}
                onDelete={handleDeleteRequest}
                onSetDefault={handleSetDefault}
              />
            </div>
          ))}
        </div>
      )}

      {/* ── Create / Edit dialog ──────────────────────────────────────────── */}
      <LLMProfileDialog
        open={dialogOpen}
        onClose={handleDialogClose}
        profile={editProfile}
      />

      {/* ── Delete confirm dialog ─────────────────────────────────────────── */}
      <ConfirmDialog
        open={deleteConfirmId !== null}
        onClose={handleDeleteCancel}
        onConfirm={handleDeleteConfirm}
        title="Delete LLM Profile"
        description={
          profileToDelete
            ? `Are you sure you want to delete "${profileToDelete.name}"? Any agents using this profile will lose their configured model. This action cannot be undone.`
            : "Are you sure you want to delete this profile? This action cannot be undone."
        }
        confirmLabel="Delete Profile"
        cancelLabel="Keep Profile"
        variant="danger"
        loading={deleteMutation.isPending}
      />
    </>
  );
}

export default LLMProfileList;
