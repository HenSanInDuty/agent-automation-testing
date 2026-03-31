"use client";

import * as React from "react";
import { Edit3, RotateCcw, CheckCircle2, XCircle } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { Toggle, Badge } from "@/components/ui/Select";
import { cn, formatRelativeTime } from "@/lib/utils";
import type { AgentConfigSummary, AgentConfigUpdate } from "@/types";

// ─────────────────────────────────────────────────────────────────────────────
// Props
// ─────────────────────────────────────────────────────────────────────────────

export interface AgentCardProps {
  /** The agent summary data to display */
  agent: AgentConfigSummary;
  /** Zero-based position within the stage group (used for the row badge) */
  index: number;
  /**
   * Called either:
   *  – with only `agentId`           → open the full edit dialog
   *  – with `agentId` + `payload`    → perform a quick inline update (toggles)
   */
  onEdit: (agentId: string, payload?: AgentConfigUpdate) => void;
  /** Trigger the per-agent reset confirmation flow */
  onReset: (agentId: string) => void;
}

// ─────────────────────────────────────────────────────────────────────────────
// AgentCard
// ─────────────────────────────────────────────────────────────────────────────

export function AgentCard({ agent, index, onEdit, onReset }: AgentCardProps) {
  return (
    <div
      className={cn(
        "group flex items-center gap-3 px-4 py-3",
        "border-b border-[#2b3b55]/60 last:border-b-0",
        "hover:bg-[#1e2a3d]/60 transition-colors duration-150",
      )}
    >
      {/* ── Index badge ──────────────────────────────────────────────────── */}
      <div
        className={cn(
          "shrink-0 w-7 h-7 rounded-lg",
          "bg-[#101622] border border-[#2b3b55]",
          "flex items-center justify-center",
        )}
        aria-hidden="true"
      >
        <span className="text-[11px] font-semibold text-[#92a4c9] tabular-nums">
          {index + 1}
        </span>
      </div>

      {/* ── Display name + timestamp ──────────────────────────────────────── */}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-white truncate leading-snug">
          {agent.display_name}
        </p>
        <time
          dateTime={agent.updated_at}
          className="text-[10px] text-[#3d5070] select-none"
          title={new Date(agent.updated_at).toLocaleString()}
        >
          Updated {formatRelativeTime(agent.updated_at)}
        </time>
      </div>

      {/* ── LLM profile ───────────────────────────────────────────────────── */}
      <div className="hidden sm:flex shrink-0 w-36 items-center">
        {agent.llm_profile_id === null ? (
          <Badge variant="default" size="xs">
            DEFAULT
          </Badge>
        ) : (
          <span
            className="text-xs text-[#92a4c9] truncate font-mono"
            title={agent.llm_profile_name ?? undefined}
          >
            {agent.llm_profile_name ?? "—"}
          </span>
        )}
      </div>

      {/* ── Max iterations ────────────────────────────────────────────────── */}
      <div className="hidden md:flex shrink-0">
        <Badge variant="outline" size="xs" title="Max iterations">
          {agent.max_iter} iter
        </Badge>
      </div>

      {/* ── Enabled toggle ────────────────────────────────────────────────── */}
      <div className="shrink-0 flex flex-col items-center gap-0.5">
        <span className="text-[9px] font-semibold uppercase tracking-wider text-[#3d5070] select-none">
          Enabled
        </span>
        <Toggle
          checked={agent.enabled}
          onChange={() =>
            onEdit(agent.agent_id, { enabled: !agent.enabled })
          }
          size="sm"
          aria-label={`Toggle enabled for ${agent.display_name}`}
        />
      </div>

      {/* ── Verbose toggle ────────────────────────────────────────────────── */}
      <div className="shrink-0 flex flex-col items-center gap-0.5">
        <span className="text-[9px] font-semibold uppercase tracking-wider text-[#3d5070] select-none">
          Verbose
        </span>
        <Toggle
          checked={agent.verbose}
          onChange={() =>
            onEdit(agent.agent_id, { verbose: !agent.verbose })
          }
          size="sm"
          aria-label={`Toggle verbose for ${agent.display_name}`}
        />
      </div>

      {/* ── Status icon ───────────────────────────────────────────────────── */}
      <div className="hidden lg:flex shrink-0" aria-hidden="true">
        {agent.enabled ? (
          <CheckCircle2
            className="w-4 h-4 text-[#4ade80]"
            aria-label="Enabled"
          />
        ) : (
          <XCircle
            className="w-4 h-4 text-[#f87171]"
            aria-label="Disabled"
          />
        )}
      </div>

      {/* ── Action buttons ────────────────────────────────────────────────── */}
      <div className="shrink-0 flex items-center gap-1">
        <Button
          variant="ghost"
          size="xs"
          leftIcon={<Edit3 className="w-3 h-3" aria-hidden="true" />}
          onClick={() => onEdit(agent.agent_id)}
          title={`Edit ${agent.display_name}`}
          className={cn(
            "opacity-0 group-hover:opacity-100",
            "transition-opacity duration-150",
          )}
        >
          Edit
        </Button>

        <Button
          variant="ghost"
          size="xs"
          leftIcon={<RotateCcw className="w-3 h-3" aria-hidden="true" />}
          onClick={() => onReset(agent.agent_id)}
          title={`Reset ${agent.display_name} to default`}
          className={cn(
            "opacity-0 group-hover:opacity-100",
            "transition-opacity duration-150",
            "text-[#92a4c9] hover:text-[#fbbf24] hover:bg-[#f59e0b]/10",
          )}
        >
          Reset
        </Button>
      </div>
    </div>
  );
}

export default AgentCard;
