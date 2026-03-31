"use client";

import * as React from "react";
import { ChevronDown, ChevronUp } from "lucide-react";

import { Badge } from "@/components/ui/Select";
import { cn } from "@/lib/utils";
import {
  STAGE_LABELS,
  type AgentStage,
  type AgentConfigSummary,
  type AgentConfigUpdate,
} from "@/types";

import { AgentCard } from "./AgentCard";

// ─────────────────────────────────────────────────────────────────────────────
// Props
// ─────────────────────────────────────────────────────────────────────────────

interface AgentGroupSectionProps {
  stage: AgentStage;
  agents: AgentConfigSummary[];
  onEditAgent: (agentId: string, payload?: AgentConfigUpdate) => void;
  onResetAgent: (agentId: string) => void;
  /** Zero-based position of this stage in STAGE_ORDER — used for accent styling */
  index: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// Per-stage visual accents
// ─────────────────────────────────────────────────────────────────────────────

interface StageAccent {
  dot: string;
  headerBorder: string;
  headerGlow: string;
  badgeBg: string;
  badgeText: string;
  badgeBorder: string;
  numberLabel: string;
}

const STAGE_ACCENTS: Record<AgentStage, StageAccent> = {
  ingestion: {
    dot: "bg-[#135bec]",
    headerBorder: "border-[#135bec]/30",
    headerGlow: "hover:border-[#135bec]/50",
    badgeBg: "bg-[#135bec]/10",
    badgeText: "text-[#5b9eff]",
    badgeBorder: "border-[#135bec]/25",
    numberLabel: "text-[#5b9eff]",
  },
  testcase: {
    dot: "bg-[#7c3aed]",
    headerBorder: "border-[#7c3aed]/30",
    headerGlow: "hover:border-[#7c3aed]/50",
    badgeBg: "bg-[#7c3aed]/10",
    badgeText: "text-[#a78bfa]",
    badgeBorder: "border-[#7c3aed]/25",
    numberLabel: "text-[#a78bfa]",
  },
  execution: {
    dot: "bg-[#d97706]",
    headerBorder: "border-[#d97706]/30",
    headerGlow: "hover:border-[#d97706]/50",
    badgeBg: "bg-[#d97706]/10",
    badgeText: "text-[#fbbf24]",
    badgeBorder: "border-[#d97706]/25",
    numberLabel: "text-[#fbbf24]",
  },
  reporting: {
    dot: "bg-[#22c55e]",
    headerBorder: "border-[#22c55e]/30",
    headerGlow: "hover:border-[#22c55e]/50",
    badgeBg: "bg-[#22c55e]/10",
    badgeText: "text-[#4ade80]",
    badgeBorder: "border-[#22c55e]/25",
    numberLabel: "text-[#4ade80]",
  },
};

// ─────────────────────────────────────────────────────────────────────────────
// AgentGroupSection
// ─────────────────────────────────────────────────────────────────────────────

export function AgentGroupSection({
  stage,
  agents,
  onEditAgent,
  onResetAgent,
  index,
}: AgentGroupSectionProps) {
  const [expanded, setExpanded] = React.useState(true);

  const label = STAGE_LABELS[stage];
  const accent = STAGE_ACCENTS[stage];
  const agentCount = agents.length;

  return (
    <section aria-label={label}>
      {/* ── Section header (toggle button) ─────────────────────────────── */}
      <button
        type="button"
        onClick={() => setExpanded((prev) => !prev)}
        aria-expanded={expanded}
        aria-controls={`stage-body-${stage}`}
        className={cn(
          // Layout
          "w-full flex items-center gap-3 px-4 py-3",
          // Shape — round all corners when collapsed, top only when expanded
          "rounded-xl",
          expanded && "rounded-b-none",
          // Surface
          "bg-[#18202F]",
          // Border
          "border",
          accent.headerBorder,
          accent.headerGlow,
          // Interaction
          "transition-colors duration-150",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#135bec] focus-visible:ring-inset",
          "cursor-pointer select-none",
        )}
      >
        {/* Stage order number */}
        <span
          className={cn(
            "shrink-0 text-[11px] font-bold tabular-nums",
            accent.numberLabel,
          )}
          aria-hidden="true"
        >
          {String(index + 1).padStart(2, "0")}
        </span>

        {/* Stage dot indicator */}
        <span
          className={cn(
            "shrink-0 w-2 h-2 rounded-full",
            expanded ? accent.dot : "bg-[#3d5070]",
            "transition-colors duration-200",
          )}
          aria-hidden="true"
        />

        {/* Stage label */}
        <span className="flex-1 text-left text-sm font-semibold text-white leading-snug">
          {label}
        </span>

        {/* Agent count badge */}
        <span
          className={cn(
            "shrink-0 inline-flex items-center",
            "px-2 py-0.5 rounded-md text-[11px] font-semibold",
            "border",
            accent.badgeBg,
            accent.badgeText,
            accent.badgeBorder,
          )}
        >
          {agentCount}&nbsp;
          <span className="font-normal opacity-80">
            {agentCount === 1 ? "agent" : "agents"}
          </span>
        </span>

        {/* Chevron */}
        <span className="shrink-0 text-[#92a4c9]" aria-hidden="true">
          {expanded ? (
            <ChevronUp className="w-4 h-4" />
          ) : (
            <ChevronDown className="w-4 h-4" />
          )}
        </span>
      </button>

      {/* ── Collapsible body ───────────────────────────────────────────── */}
      {expanded && (
        <div
          id={`stage-body-${stage}`}
          role="list"
          aria-label={`Agents in ${label}`}
          className={cn(
            "rounded-b-xl",
            "border-x border-b border-[#2b3b55]",
            "bg-[#18202F]",
            // Subtle inner top shadow to anchor it to the header
            "shadow-[inset_0_2px_4px_rgba(0,0,0,0.15)]",
          )}
        >
          {agentCount === 0 ? (
            <div className="flex items-center justify-center py-8 px-4">
              <p className="text-sm text-[#3d5070] italic">
                No agents configured for this stage.
              </p>
            </div>
          ) : (
            agents.map((agent, i) => (
              <div key={agent.id} role="listitem">
                <AgentCard
                  agent={agent}
                  index={i}
                  onEdit={onEditAgent}
                  onReset={onResetAgent}
                />
              </div>
            ))
          )}
        </div>
      )}
    </section>
  );
}

export default AgentGroupSection;
