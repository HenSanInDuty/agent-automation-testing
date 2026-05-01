"use client";

import * as React from "react";
import {
  ChevronDown,
  ChevronUp,
  Layers,
  GitBranch,
  ArrowRightLeft,
  Plus,
} from "lucide-react";

import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/utils";
import {
  type AgentConfigResponse,
  type AgentConfigUpdate,
  type AgentConfigSummary,
  type PipelineStageEntry,
} from "@/types";
import { useUpdateNodeStage } from "@/hooks/usePipelineTemplates";

import { AgentCard } from "./AgentCard";
import { StageIcon } from "./StageIcon";
import { AddAgentDialog } from "./AddAgentDialog";
import { useQueryClient } from "@tanstack/react-query";
import { pipelineTemplatesApi } from "@/lib/api";
import { queryKeys } from "@/lib/queryClient";
import { toast } from "@/components/ui/Toast";

// ─────────────────────────────────────────────────────────────────────────────
// Props
// ─────────────────────────────────────────────────────────────────────────────

interface PipelineGroupSectionProps {
  templateId: string;
  pipelineName: string;
  pipelineDescription: string;
  stages: PipelineStageEntry[];
  totalAgents: number;
  onEditAgent: (agentId: string, payload?: AgentConfigUpdate) => void;
  onResetAgent: (agentId: string) => void;
  onDeleteAgent: (agentId: string) => void;
  onManageStages: (templateId: string, templateName: string) => void;
  index: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// Stage selector row — appears below each agent card in the pipeline view
// ─────────────────────────────────────────────────────────────────────────────

interface StageSelectorProps {
  agent: AgentConfigSummary;
  currentStageId: string | null; // "__unassigned__" is treated as null
  availableStages: PipelineStageEntry[]; // filtered to exclude __unassigned__
  templateId: string;
}

function StageSelector({
  agent,
  currentStageId,
  availableStages,
  templateId,
}: StageSelectorProps) {
  const { mutate: updateNodeStage, isPending } = useUpdateNodeStage();

  if (!agent.node_id) return null;

  const normalizedCurrent =
    currentStageId === "__unassigned__" ? "" : (currentStageId ?? "");

  const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const newStageId = e.target.value || null;
    updateNodeStage({
      templateId,
      nodeId: agent.node_id!,
      stageId: newStageId,
    });
  };

  return (
    <div
      className={cn(
        "flex items-center gap-2 px-4 py-1.5",
        "bg-[#0d1420] border-x border-b border-[#2b3b55]/50",
        "last:rounded-b-lg",
      )}
    >
      <ArrowRightLeft
        className="w-3 h-3 text-[#3d5070] shrink-0"
        aria-hidden="true"
      />
      <span className="text-[9px] font-semibold uppercase tracking-wider text-[#3d5070] shrink-0 select-none">
        Stage
      </span>
      <select
        value={normalizedCurrent}
        onChange={handleChange}
        disabled={isPending}
        aria-label={`Assign ${agent.display_name} to a stage`}
        className={cn(
          "flex-1 min-w-0 text-xs bg-transparent border-none outline-none cursor-pointer",
          "text-[#92a4c9] hover:text-white transition-colors duration-150",
          isPending && "opacity-50 cursor-not-allowed",
        )}
      >
        <option value="" className="bg-[#101622] text-[#3d5070]">
          — Unassigned —
        </option>
        {availableStages.map((s) => (
          <option
            key={s.stage_id}
            value={s.stage_id}
            className="bg-[#101622] text-white"
          >
            {s.display_name}
          </option>
        ))}
      </select>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Accent color helper for stage headers
// ─────────────────────────────────────────────────────────────────────────────

function getAccentFromColor(color: string | null | undefined) {
  const c = color ?? "#4b6a9e";
  return {
    dotStyle: { backgroundColor: c } as React.CSSProperties,
    headerStyle: { borderColor: `${c}40` } as React.CSSProperties,
    badgeStyle: {
      backgroundColor: `${c}18`,
      borderColor: `${c}40`,
    } as React.CSSProperties,
    badgeTextStyle: { color: c } as React.CSSProperties,
    numberStyle: { color: c } as React.CSSProperties,
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// PipelineGroupSection
// ─────────────────────────────────────────────────────────────────────────────

export function PipelineGroupSection({
  templateId,
  pipelineName,
  pipelineDescription,
  stages,
  totalAgents,
  onEditAgent,
  onResetAgent,
  onDeleteAgent,
  onManageStages,
  index,
}: PipelineGroupSectionProps) {
  const [expanded, setExpanded] = React.useState(false);
  const [expandedStages, setExpandedStages] = React.useState<
    Record<string, boolean>
  >({});
  const [addAgentOpen, setAddAgentOpen] = React.useState(false);

  const qc = useQueryClient();

  // Initialise all stages as expanded whenever the stages list changes
  React.useEffect(() => {
    const initial: Record<string, boolean> = {};
    stages.forEach((s) => {
      initial[s.stage_id] = true;
    });
    setExpandedStages(initial);
  }, [stages]);

  const toggleStage = (stageId: string) => {
    setExpandedStages((prev) => ({ ...prev, [stageId]: !prev[stageId] }));
  };

  const handleAgentCreated = React.useCallback(
    async (agent: AgentConfigResponse) => {
      try {
        // Build a unique node ID that satisfies ^[a-z][a-z0-9_-]{2,49}$
        const suffix = Math.random().toString(36).slice(2, 8); // 6 random chars
        const nodeId = `${agent.agent_id.slice(0, 42)}_${suffix}`; // max 49 chars

        await pipelineTemplatesApi.appendNode(templateId, {
          node_id: nodeId,
          node_type: agent.stage === "ingestion" ? "pure_python" : "agent",
          agent_id: agent.agent_id,
          label: agent.display_name,
          description: "",
          position_x: 0,
          position_y: 0,
          timeout_seconds: 300,
          retry_count: 0,
          enabled: agent.enabled,
          config_overrides: {},
        });

        // Refresh the pipeline → agent mapping shown in this page
        qc.invalidateQueries({ queryKey: queryKeys.agentConfigs.byPipeline() });
      } catch {
        toast.error(
          "Add to pipeline failed",
          "The agent was created but could not be added to the pipeline. Open the Pipeline Builder to add it manually.",
        );
      }
    },
    [templateId, qc],
  );

  return (
    <>
      <section aria-label={pipelineName} className="mb-4">
        {/* ── Pipeline Header ──────────────────────────────────────────────── */}
        <div
          className={cn(
            "flex items-center gap-3 px-4 py-3 min-w-0 overflow-hidden",
            "rounded-xl",
            expanded && "rounded-b-none",
            "bg-[#0f1729]",
            "border border-[#1e2f4a]",
            "transition-colors duration-150",
          )}
        >
          {/* Toggle button wraps everything except the "Stages" button */}
          <button
            type="button"
            onClick={() => setExpanded((prev) => !prev)}
            aria-expanded={expanded}
            aria-controls={`pipeline-body-${templateId}`}
            className="flex-1 min-w-0 flex items-center gap-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#135bec] focus-visible:ring-inset rounded-lg"
          >
            {/* Pipeline number */}
            <span className="shrink-0 text-[11px] font-bold tabular-nums text-[#135bec]">
              {String(index + 1).padStart(2, "0")}
            </span>

            {/* GitBranch icon */}
            <GitBranch
              className="shrink-0 w-4 h-4 text-[#135bec]"
              aria-hidden="true"
            />

            {/* Pipeline name + description */}
            <span className="flex-1 text-left leading-snug min-w-0">
              <span className="text-sm font-semibold text-white">
                {pipelineName}
              </span>
              {pipelineDescription && (
                <span className="block text-[11px] text-[#92a4c9] truncate mt-0.5">
                  {pipelineDescription}
                </span>
              )}
            </span>

            {/* Stats badges */}
            <span className="shrink-0 inline-flex items-center gap-2">
              <span
                className={cn(
                  "inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-semibold",
                  "bg-[#135bec]/10 border border-[#135bec]/30 text-[#5b9eff]",
                )}
              >
                {stages.length} {stages.length === 1 ? "stage" : "stages"}
              </span>
              <span
                className={cn(
                  "inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-semibold",
                  "bg-[#18202F] border border-[#2b3b55] text-[#92a4c9]",
                )}
              >
                {totalAgents} {totalAgents === 1 ? "agent" : "agents"}
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

          {/* Add Agent button — lives outside the toggle button */}
          <Button
            variant="primary"
            size="xs"
            leftIcon={<Plus className="w-3 h-3" aria-hidden="true" />}
            onClick={(e) => {
              e.stopPropagation();
              setAddAgentOpen(true);
            }}
            title={`Add agent to ${pipelineName}`}
          >
            Add Agent
          </Button>

          {/* Manage Stages button — lives outside the toggle button */}
          <Button
            variant="secondary"
            size="xs"
            leftIcon={<Layers className="w-3 h-3" aria-hidden="true" />}
            onClick={(e) => {
              e.stopPropagation();
              onManageStages(templateId, pipelineName);
            }}
            title={`Manage stages for ${pipelineName}`}
          >
            Stages
          </Button>
        </div>

        {/* ── Expanded content — stages ─────────────────────────────────────── */}
        {expanded && (
          <div
            id={`pipeline-body-${templateId}`}
            className={cn(
              "rounded-b-xl border-x border-b border-[#1e2f4a]",
              "bg-[#0f1729]/50",
            )}
          >
            {stages.length === 0 ? (
              <div className="flex items-center justify-center py-8 px-4">
                <p className="text-sm text-[#3d5070] italic">
                  No stages configured for this pipeline.
                </p>
              </div>
            ) : (
              <div className="p-3 space-y-2">
                {stages.map((stage, stageIndex) => {
                  const accent = getAccentFromColor(stage.color);
                  const isStageExpanded =
                    expandedStages[stage.stage_id] ?? false;

                  return (
                    <section
                      key={stage.stage_id}
                      aria-label={stage.display_name}
                    >
                      {/* Stage header */}
                      <button
                        type="button"
                        onClick={() => toggleStage(stage.stage_id)}
                        aria-expanded={isStageExpanded}
                        aria-controls={`stage-body-${stage.stage_id}`}
                        className={cn(
                          "w-full flex items-center gap-3 px-3 py-2",
                          "rounded-lg",
                          isStageExpanded && "rounded-b-none",
                          "bg-[#18202F]",
                          "border",
                          "cursor-pointer select-none",
                          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#135bec] focus-visible:ring-inset",
                          "transition-colors duration-150",
                        )}
                        style={accent.headerStyle}
                      >
                        {/* Stage number */}
                        <span
                          className="shrink-0 text-[10px] font-bold tabular-nums"
                          style={accent.numberStyle}
                          aria-hidden="true"
                        >
                          {String(stageIndex + 1).padStart(2, "0")}
                        </span>

                        {/* Stage dot */}
                        <span
                          className="shrink-0 w-1.5 h-1.5 rounded-full transition-colors duration-200"
                          style={
                            isStageExpanded
                              ? accent.dotStyle
                              : { backgroundColor: "#3d5070" }
                          }
                          aria-hidden="true"
                        />

                        {/* Stage icon */}
                        <StageIcon
                          name={stage.icon}
                          color={
                            isStageExpanded
                              ? (stage.color ?? undefined)
                              : "#3d5070"
                          }
                          className="shrink-0 w-3.5 h-3.5"
                        />

                        {/* Stage name */}
                        <span className="flex-1 text-left text-xs font-semibold text-white truncate">
                          {stage.display_name}
                        </span>

                        {/* Agent count badge */}
                        <span
                          className="shrink-0 inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold border"
                          style={accent.badgeStyle}
                        >
                          <span style={accent.badgeTextStyle}>
                            {stage.agents.length}{" "}
                            {stage.agents.length === 1 ? "agent" : "agents"}
                          </span>
                        </span>

                        {/* Chevron */}
                        <span
                          className="shrink-0 text-[#92a4c9]"
                          aria-hidden="true"
                        >
                          {isStageExpanded ? (
                            <ChevronUp className="w-3.5 h-3.5" />
                          ) : (
                            <ChevronDown className="w-3.5 h-3.5" />
                          )}
                        </span>
                      </button>

                      {/* Stage agents */}
                      {isStageExpanded && (
                        <div
                          id={`stage-body-${stage.stage_id}`}
                          role="list"
                          aria-label={`Agents in ${stage.display_name}`}
                          className={cn(
                            "rounded-b-lg",
                            "border-x border-b border-[#2b3b55]",
                            "bg-[#18202F]",
                            "shadow-[inset_0_2px_4px_rgba(0,0,0,0.15)]",
                          )}
                        >
                          {stage.agents.length === 0 ? (
                            <div className="flex items-center justify-center py-6 px-4">
                              <p className="text-xs text-[#3d5070] italic">
                                No agents in this stage.
                              </p>
                            </div>
                          ) : (
                            stage.agents.map((agent, i) => (
                              <div key={agent.id} role="listitem">
                                <AgentCard
                                  agent={agent}
                                  index={i}
                                  onEdit={onEditAgent}
                                  onReset={onResetAgent}
                                  onDelete={onDeleteAgent}
                                />
                                <StageSelector
                                  agent={agent}
                                  currentStageId={stage.stage_id}
                                  availableStages={stages.filter(
                                    (s) => s.stage_id !== "__unassigned__",
                                  )}
                                  templateId={templateId}
                                />
                              </div>
                            ))
                          )}
                        </div>
                      )}
                    </section>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </section>

      <AddAgentDialog
        open={addAgentOpen}
        onClose={() => setAddAgentOpen(false)}
        templateId={templateId}
        onCreated={handleAgentCreated}
      />
    </>
  );
}

export default PipelineGroupSection;
