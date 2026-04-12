"use client";

import * as React from "react";
import { ChevronDown, ChevronUp } from "lucide-react";

import { cn } from "@/lib/utils";
import { type AgentConfigSummary, type AgentConfigUpdate } from "@/types";

import { AgentCard } from "./AgentCard";
import { StageIcon } from "./StageIcon";

// ─────────────────────────────────────────────────────────────────────────────
// Props
// ─────────────────────────────────────────────────────────────────────────────

interface AgentGroupSectionProps {
  stageId: string;
  displayName: string;
  description?: string | null;
  color?: string | null;
  icon?: string | null;
  isBuiltin: boolean;
  agents: AgentConfigSummary[];
  onEditAgent: (agentId: string, payload?: AgentConfigUpdate) => void;
  onResetAgent: (agentId: string) => void;
  onDeleteAgent: (agentId: string) => void;
  /** Zero-based position of this stage — used for numbering */
  index: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// Dynamic accent from hex color
// ─────────────────────────────────────────────────────────────────────────────

function getAccentFromColor(color: string | null | undefined) {
  const c = color ?? "#4b6a9e";
  return {
    dot: "rounded-full",
    dotStyle: { backgroundColor: c } as React.CSSProperties,
    headerBorder: "",
    headerStyle: { borderColor: `${c}40` } as React.CSSProperties,
    badgeBg: "",
    badgeStyle: {
      backgroundColor: `${c}18`,
      borderColor: `${c}40`,
    } as React.CSSProperties,
    badgeText: "",
    badgeTextStyle: { color: c } as React.CSSProperties,
    numberLabel: "",
    numberStyle: { color: c } as React.CSSProperties,
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// AgentGroupSection
// ─────────────────────────────────────────────────────────────────────────────

export function AgentGroupSection({
  stageId,
  displayName,
  description,
  color,
  icon,
  isBuiltin,
  agents,
  onEditAgent,
  onResetAgent,
  onDeleteAgent,
  index,
}: AgentGroupSectionProps) {
  const [expanded, setExpanded] = React.useState(true);

  const accent = getAccentFromColor(color);
  const agentCount = agents.length;

  return (
    <section aria-label={displayName}>
      {/* ── Section header (toggle button) ─────────────────────────────── */}
      <button
        type="button"
        onClick={() => setExpanded((prev) => !prev)}
        aria-expanded={expanded}
        aria-controls={`stage-body-${stageId}`}
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
          // Interaction
          "transition-colors duration-150",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#135bec] focus-visible:ring-inset",
          "cursor-pointer select-none",
        )}
        style={accent.headerStyle}
      >
        {/* Stage order number */}
        <span
          className="shrink-0 text-[11px] font-bold tabular-nums"
          style={accent.numberStyle}
          aria-hidden="true"
        >
          {String(index + 1).padStart(2, "0")}
        </span>

        {/* Stage dot indicator */}
        <span
          className={cn(
            "shrink-0 w-2 h-2",
            accent.dot,
            "transition-colors duration-200",
          )}
          style={expanded ? accent.dotStyle : { backgroundColor: "#3d5070" }}
          aria-hidden="true"
        />

        {/* Stage icon */}
        <StageIcon
          name={icon}
          color={expanded ? (color ?? undefined) : "#3d5070"}
          className="shrink-0 w-4 h-4"
        />

        {/* Stage label + builtin lock + optional description */}
        <span className="flex-1 text-left leading-snug min-w-0">
          <span className="flex items-center gap-1.5 flex-wrap">
            <span className="text-sm font-semibold text-white">
              {displayName}
            </span>
            {isBuiltin && (
              <span
                title="Built-in stage"
                aria-label="Built-in stage"
                className="text-[11px] leading-none"
              >
                🔒
              </span>
            )}
          </span>
          {description && (
            <span className="block text-[11px] text-[#92a4c9] truncate mt-0.5">
              {description}
            </span>
          )}
        </span>

        {/* Agent count badge */}
        <span
          className={cn(
            "shrink-0 inline-flex items-center",
            "px-2 py-0.5 rounded-md text-[11px] font-semibold",
            "border",
          )}
          style={accent.badgeStyle}
        >
          <span style={accent.badgeTextStyle}>
            {agentCount}
            &nbsp;
            <span className="font-normal opacity-80">
              {agentCount === 1 ? "agent" : "agents"}
            </span>
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
          id={`stage-body-${stageId}`}
          role="list"
          aria-label={`Agents in ${displayName}`}
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
                  onDelete={onDeleteAgent}
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
