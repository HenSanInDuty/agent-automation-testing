"use client";

import * as React from "react";
import { RefreshCw, ChevronDown } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/utils";
import { useLLMProfiles } from "@/hooks/useLLMProfiles";
import type { LLMProfileResponse } from "@/types";

// ─────────────────────────────────────────────────────────────────────────────
// Props
// ─────────────────────────────────────────────────────────────────────────────

export interface LLMProfileSelectorProps {
  /** The selected profile ID, or null to use the system default. */
  value: number | null;
  onChange: (id: number | null) => void;
  disabled?: boolean;
}

// ─────────────────────────────────────────────────────────────────────────────
// Loading skeleton
// ─────────────────────────────────────────────────────────────────────────────

function SelectorSkeleton() {
  return (
    <div
      role="status"
      aria-label="Loading LLM profiles…"
      className="flex flex-col gap-1.5"
    >
      {/* Label */}
      <div className="h-4 w-24 bg-[#2b3b55] rounded animate-pulse" />
      {/* Select */}
      <div className="h-9 w-full bg-[#2b3b55] rounded-lg animate-pulse" />
      {/* Hint */}
      <div className="h-3 w-3/4 bg-[#2b3b55] rounded animate-pulse" />
      <span className="sr-only">Loading LLM profiles…</span>
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
    <div className="flex items-center gap-3 px-3 py-2 rounded-lg bg-[#ef4444]/10 border border-[#ef4444]/25">
      <span className="flex-1 text-xs text-[#f87171]">
        Failed to load LLM profiles.
      </span>
      <Button
        variant="ghost"
        size="xs"
        leftIcon={<RefreshCw className="w-3 h-3" aria-hidden="true" />}
        onClick={onRetry}
        className="shrink-0 text-[#92a4c9] hover:text-white"
      >
        Retry
      </Button>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Option label builder
// ─────────────────────────────────────────────────────────────────────────────

function buildOptionLabel(profile: LLMProfileResponse): string {
  const defaultTag = profile.is_default ? " (Default)" : "";
  return `${profile.name}${defaultTag} – ${profile.provider}/${profile.model}`;
}

// ─────────────────────────────────────────────────────────────────────────────
// LLMProfileSelector
// ─────────────────────────────────────────────────────────────────────────────

export function LLMProfileSelector({
  value,
  onChange,
  disabled = false,
}: LLMProfileSelectorProps) {
  const { data, isLoading, isError, refetch } = useLLMProfiles({ limit: 100 });

  const profiles: LLMProfileResponse[] = data?.items ?? [];
  const defaultProfile = profiles.find((p) => p.is_default);

  const isDisabled = disabled || profiles.length === 0;

  const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const val = e.target.value;
    onChange(val === "" ? null : Number(val));
  };

  // ── Loading ───────────────────────────────────────────────────────────────
  if (isLoading) return <SelectorSkeleton />;

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col gap-1.5">
      {/* ── Label ──────────────────────────────────────────────────────────── */}
      <label
        htmlFor="llm-profile-select"
        className="block text-sm font-medium text-[#92a4c9] select-none"
      >
        LLM Profile
      </label>

      {/* ── Error state ────────────────────────────────────────────────────── */}
      {isError ? (
        <ErrorState onRetry={refetch} />
      ) : (
        <>
          {/* ── Select dropdown ──────────────────────────────────────────── */}
          <div className="relative w-full">
            <select
              id="llm-profile-select"
              value={value ?? ""}
              onChange={handleChange}
              disabled={isDisabled}
              aria-label="LLM Profile"
              className={cn(
                // Base
                "w-full appearance-none rounded-lg bg-[#101622] border text-sm text-white",
                "h-9 px-3 pr-9",
                "transition-colors duration-150",
                // Focus
                "outline-none focus:ring-2 focus:ring-[#135bec] focus:ring-offset-0 focus:border-[#135bec]",
                // Border
                "border-[#2b3b55]",
                // Cursor
                isDisabled
                  ? "opacity-50 cursor-not-allowed"
                  : "cursor-pointer hover:border-[#3d5070]"
              )}
            >
              {/* System Default option — shows the active default's name when known */}
              <option value="">
                {defaultProfile
                  ? `🌐 System Default (${defaultProfile.name})`
                  : "🌐 System Default"}
              </option>

              {/* Profile options */}
              {profiles.map((profile) => (
                <option key={profile.id} value={profile.id}>
                  {buildOptionLabel(profile)}
                </option>
              ))}
            </select>

            {/* Chevron icon */}
            <ChevronDown
              className="absolute top-1/2 right-2.5 -translate-y-1/2 w-4 h-4 pointer-events-none text-[#92a4c9]"
              aria-hidden="true"
            />
          </div>

          {/* ── Hint text ────────────────────────────────────────────────── */}
          <p className="text-xs text-[#3d5070]">
            Select a profile for this run (leave as Default to use the system
            default)
          </p>
        </>
      )}
    </div>
  );
}

export default LLMProfileSelector;
