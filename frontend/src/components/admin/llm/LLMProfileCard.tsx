"use client";

import * as React from "react";
import { Edit3, Trash2, Star, Check } from "lucide-react";

import { Badge } from "@/components/ui/Select";
import { Button } from "@/components/ui/Button";
import { cn, formatRelativeTime, getInitials } from "@/lib/utils";
import {
  LLMProvider,
  LLM_PROVIDER_LABELS,
  type LLMProfileResponse,
} from "@/types";

// ─────────────────────────────────────────────────────────────────────────────
// Provider accent colours
// ─────────────────────────────────────────────────────────────────────────────

const PROVIDER_BADGE_CLASSES: Record<LLMProvider, string> = {
  [LLMProvider.OPENAI]:
    "bg-[#10a37f]/20 text-[#19c37d] border border-[#10a37f]/35",
  [LLMProvider.ANTHROPIC]:
    "bg-[#d97706]/20 text-[#fbbf24] border border-[#d97706]/35",
  [LLMProvider.OLLAMA]:
    "bg-[#7c3aed]/20 text-[#a78bfa] border border-[#7c3aed]/35",
  [LLMProvider.HUGGINGFACE]:
    "bg-[#f59e0b]/20 text-[#fcd34d] border border-[#f59e0b]/35",
  [LLMProvider.AZURE]:
    "bg-[#0078d4]/20 text-[#60a5fa] border border-[#0078d4]/35",
  [LLMProvider.GROQ]:
    "bg-[#e11d48]/20 text-[#fb7185] border border-[#e11d48]/35",
};

const PROVIDER_GLOW_CLASSES: Record<LLMProvider, string> = {
  [LLMProvider.OPENAI]: "group-hover:border-[#10a37f]/40",
  [LLMProvider.ANTHROPIC]: "group-hover:border-[#d97706]/40",
  [LLMProvider.OLLAMA]: "group-hover:border-[#7c3aed]/40",
  [LLMProvider.HUGGINGFACE]: "group-hover:border-[#f59e0b]/40",
  [LLMProvider.AZURE]: "group-hover:border-[#0078d4]/40",
  [LLMProvider.GROQ]: "group-hover:border-[#e11d48]/40",
};

// ─────────────────────────────────────────────────────────────────────────────
// Sub-components
// ─────────────────────────────────────────────────────────────────────────────

interface StatItemProps {
  label: string;
  value: string;
  mono?: boolean;
  className?: string;
}

function StatItem({ label, value, mono = false, className }: StatItemProps) {
  return (
    <div className={cn("flex flex-col gap-0.5 min-w-0", className)}>
      <span className="text-[10px] font-semibold uppercase tracking-wider text-[#3d5070]">
        {label}
      </span>
      <span
        className={cn("text-xs text-[#92a4c9] truncate", mono && "font-mono")}
        title={value}
      >
        {value}
      </span>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Props
// ─────────────────────────────────────────────────────────────────────────────

export interface LLMProfileCardProps {
  profile: LLMProfileResponse;
  onEdit: (profile: LLMProfileResponse) => void;
  onDelete: (profile: LLMProfileResponse) => void;
  onSetDefault: (profile: LLMProfileResponse) => void;
}

// ─────────────────────────────────────────────────────────────────────────────
// LLMProfileCard
// ─────────────────────────────────────────────────────────────────────────────

export function LLMProfileCard({
  profile,
  onEdit,
  onDelete,
  onSetDefault,
}: LLMProfileCardProps) {
  const providerLabel =
    LLM_PROVIDER_LABELS[profile.provider] ?? profile.provider;
  const initials = getInitials(profile.name);
  const badgeClasses =
    PROVIDER_BADGE_CLASSES[profile.provider] ??
    "bg-[#2b3b55] text-[#92a4c9] border border-[#2b3b55]";
  const glowClass =
    PROVIDER_GLOW_CLASSES[profile.provider] ?? "group-hover:border-[#3d5070]";

  return (
    <article
      className={cn(
        // Base layout
        "group relative flex flex-col rounded-xl border",
        "bg-[#18202F]",
        // Default border
        profile.is_default ? "border-[#135bec]/40" : "border-[#2b3b55]",
        // Hover state — subtle lift + border colour per provider
        "hover:bg-[#1c2538]",
        "hover:shadow-xl hover:shadow-black/30",
        "translate-y-0 hover:-translate-y-px",
        "transition-all duration-200 ease-out",
        // Provider accent on hover (only when not already default-styled)
        !profile.is_default && glowClass,
        // If default, stronger blue glow on hover
        profile.is_default &&
          "hover:border-[#135bec]/70 hover:shadow-[#135bec]/10",
      )}
    >
      {/* ── Default accent stripe ────────────────────────────────────────── */}
      {profile.is_default && (
        <span
          aria-hidden="true"
          className="absolute inset-x-0 top-0 h-0.5 rounded-t-xl bg-linear-to-r from-[#135bec]/60 via-[#135bec] to-[#135bec]/60"
        />
      )}

      {/* ── Header ──────────────────────────────────────────────────────── */}
      <div className="flex items-start gap-3 px-4 pt-4 pb-3">
        {/* Provider initials badge */}
        <div
          className={cn(
            "shrink-0 w-10 h-10 rounded-lg",
            "flex items-center justify-center",
            "text-[11px] font-bold tracking-wide select-none",
            "transition-transform duration-200 group-hover:scale-105",
            badgeClasses,
          )}
          aria-label={`${providerLabel} provider`}
        >
          {initials}
        </div>

        {/* Name + provider label */}
        <div className="flex-1 min-w-0 pt-0.5">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="text-sm font-semibold text-white leading-snug truncate">
              {profile.name}
            </h3>
            {profile.is_default && (
              <Badge variant="success" size="xs" dot>
                Default
              </Badge>
            )}
          </div>
          <p className="mt-0.5 text-xs text-[#92a4c9] truncate">
            {providerLabel}
          </p>
        </div>
      </div>

      {/* ── Divider ─────────────────────────────────────────────────────── */}
      <div className="mx-4 border-t border-[#2b3b55]/70" />

      {/* ── Stats grid ──────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 gap-x-4 gap-y-3 px-4 py-3">
        <StatItem
          label="Model"
          value={profile.model}
          mono
          className="col-span-2"
        />
        <StatItem
          label="Temperature"
          value={profile.temperature.toFixed(1)}
          mono
        />
        <StatItem
          label="Max Tokens"
          value={profile.max_tokens.toLocaleString()}
          mono
        />
        {profile.api_key && (
          <StatItem
            label="API Key"
            value={profile.api_key}
            mono
            className="col-span-2"
          />
        )}
        {profile.base_url && (
          <StatItem
            label="Base URL"
            value={profile.base_url}
            mono
            className="col-span-2"
          />
        )}
      </div>

      {/* ── Footer ──────────────────────────────────────────────────────── */}
      <div
        className={cn(
          "flex items-center justify-between gap-2 px-4 py-3",
          "border-t border-[#2b3b55]/70 mt-auto",
        )}
      >
        {/* Updated timestamp */}
        <time
          dateTime={profile.updated_at}
          className="shrink-0 text-[10px] text-[#3d5070] select-none"
          title={new Date(profile.updated_at).toLocaleString()}
        >
          Updated {formatRelativeTime(profile.updated_at)}
        </time>

        {/* Action buttons */}
        <div className="flex items-center gap-1">
          {/* Set Default — only shown when this is NOT the current default */}
          {!profile.is_default && (
            <Button
              variant="ghost"
              size="xs"
              leftIcon={<Star className="w-3 h-3" aria-hidden="true" />}
              onClick={() => onSetDefault(profile)}
              title="Set as default profile"
              className="text-[#92a4c9] hover:text-[#fbbf24] hover:bg-[#f59e0b]/10"
            >
              Default
            </Button>
          )}

          {/* Already-default indicator (non-interactive) */}
          {profile.is_default && (
            <span
              className={cn(
                "inline-flex items-center gap-1 h-6 px-2",
                "text-[10px] font-medium text-[#4ade80] select-none",
              )}
              aria-label="Currently set as default"
            >
              <Check className="w-3 h-3" aria-hidden="true" />
              Active default
            </span>
          )}

          <Button
            variant="ghost"
            size="xs"
            leftIcon={<Edit3 className="w-3 h-3" aria-hidden="true" />}
            onClick={() => onEdit(profile)}
            title="Edit this profile"
          >
            Edit
          </Button>

          <Button
            variant="ghost"
            size="xs"
            leftIcon={<Trash2 className="w-3 h-3" aria-hidden="true" />}
            onClick={() => onDelete(profile)}
            title="Delete this profile"
            className="text-[#92a4c9] hover:text-[#f87171] hover:bg-[#ef4444]/10"
          >
            Delete
          </Button>
        </div>
      </div>
    </article>
  );
}

export default LLMProfileCard;
