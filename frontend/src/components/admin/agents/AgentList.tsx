"use client";

import * as React from "react";
import { Bot, Search, Filter, RotateCcw, RefreshCw, Plus } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select, Badge } from "@/components/ui/Select";
import { ConfirmDialog } from "@/components/ui/Modal";
import { toast } from "@/components/ui/Toast";
import {
  useAgentConfigsByPipeline,
  useResetAgentConfig,
  useResetAllAgentConfigs,
  useUpdateAgentConfig,
  useDeleteAgentConfig,
} from "@/hooks/useAgentConfigs";
import { type AgentConfigSummary, type AgentConfigUpdate } from "@/types";
import { cn } from "@/lib/utils";

import { PipelineGroupSection } from "./PipelineGroupSection";
import { AgentDialog } from "./AgentDialog";
import { AddAgentDialog } from "./AddAgentDialog";
import { ManageStagesDialog } from "./ManageStagesDialog";

// ─────────────────────────────────────────────────────────────────────────────
// Loading skeleton
// ─────────────────────────────────────────────────────────────────────────────

function AgentRowSkeleton() {
  return (
    <div className="flex items-center gap-3 px-4 py-3 border-b border-[#2b3b55]/60 last:border-b-0">
      {/* Index badge */}
      <div className="w-7 h-7 rounded-lg bg-[#2b3b55] shrink-0" />
      {/* Name + timestamp */}
      <div className="flex-1 space-y-1.5 min-w-0">
        <div className="h-3.5 bg-[#2b3b55] rounded w-2/5" />
        <div className="h-2.5 bg-[#2b3b55] rounded w-1/5" />
      </div>
      {/* LLM profile */}
      <div className="hidden sm:block h-5 w-20 bg-[#2b3b55] rounded-md shrink-0" />
      {/* Max iter */}
      <div className="hidden md:block h-5 w-14 bg-[#2b3b55] rounded-md shrink-0" />
      {/* Enabled toggle */}
      <div className="flex flex-col items-center gap-0.5 shrink-0">
        <div className="h-2 w-10 bg-[#2b3b55] rounded" />
        <div className="h-4 w-8 bg-[#2b3b55] rounded-full" />
      </div>
      {/* Verbose toggle */}
      <div className="flex flex-col items-center gap-0.5 shrink-0">
        <div className="h-2 w-10 bg-[#2b3b55] rounded" />
        <div className="h-4 w-8 bg-[#2b3b55] rounded-full" />
      </div>
      {/* Status icon placeholder */}
      <div className="hidden lg:block w-4 h-4 bg-[#2b3b55] rounded-full shrink-0" />
      {/* Action buttons */}
      <div className="flex items-center gap-1 shrink-0">
        <div className="h-6 w-12 bg-[#2b3b55] rounded-md" />
        <div className="h-6 w-14 bg-[#2b3b55] rounded-md" />
      </div>
    </div>
  );
}

function StageGroupSkeleton({ rowCount = 2 }: { rowCount?: number }) {
  return (
    <div className="animate-pulse rounded-xl border border-[#2b3b55] overflow-hidden">
      {/* Stage header */}
      <div className="flex items-center gap-3 px-3 py-2 bg-[#18202F] border-b border-[#2b3b55]">
        <div className="w-4 h-2.5 bg-[#2b3b55] rounded" />
        <div className="w-1.5 h-1.5 rounded-full bg-[#2b3b55]" />
        <div className="flex-1 h-3.5 bg-[#2b3b55] rounded w-1/4" />
        <div className="h-4 w-16 bg-[#2b3b55] rounded-md" />
        <div className="w-3.5 h-3.5 bg-[#2b3b55] rounded" />
      </div>
      {/* Rows */}
      <div className="bg-[#18202F]">
        {Array.from({ length: rowCount }).map((_, i) => (
          <AgentRowSkeleton key={i} />
        ))}
      </div>
    </div>
  );
}

function PipelineSkeleton() {
  return (
    <div className="animate-pulse mb-4">
      {/* Pipeline header */}
      <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-[#0f1729] border border-[#1e2f4a]">
        <div className="w-5 h-3 bg-[#1e2f4a] rounded" />
        <div className="w-4 h-4 bg-[#1e2f4a] rounded" />
        <div className="flex-1 space-y-1.5">
          <div className="h-4 bg-[#1e2f4a] rounded w-1/3" />
          <div className="h-2.5 bg-[#1e2f4a] rounded w-1/2" />
        </div>
        <div className="h-5 w-20 bg-[#1e2f4a] rounded-md" />
        <div className="h-5 w-16 bg-[#1e2f4a] rounded-md" />
        <div className="w-4 h-4 bg-[#1e2f4a] rounded" />
        <div className="h-6 w-16 bg-[#1e2f4a] rounded-md" />
      </div>
      {/* Stage children */}
      <div className="rounded-b-xl border-x border-b border-[#1e2f4a] bg-[#0f1729]/50 p-3 space-y-2">
        <StageGroupSkeleton rowCount={3} />
        <StageGroupSkeleton rowCount={2} />
      </div>
    </div>
  );
}

function ListSkeleton() {
  return (
    <div
      role="status"
      aria-label="Loading agent configurations…"
      className="space-y-1"
    >
      <PipelineSkeleton />
      <PipelineSkeleton />
      <span className="sr-only">Loading agent configurations…</span>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Error state
// ─────────────────────────────────────────────────────────────────────────────

function ErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-20 gap-4 text-center">
      <div
        className={cn(
          "w-14 h-14 rounded-xl",
          "bg-[#ef4444]/10 border border-[#ef4444]/20",
          "flex items-center justify-center",
        )}
      >
        <Bot className="w-7 h-7 text-[#f87171]" aria-hidden="true" />
      </div>

      <div className="max-w-xs">
        <p className="text-sm font-semibold text-[#f87171]">
          Failed to load agent configurations
        </p>
        <p className="mt-1.5 text-xs text-[#92a4c9] leading-relaxed">
          Something went wrong while fetching the pipeline agent configs. Check
          your connection and try again.
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
// Empty search state
// ─────────────────────────────────────────────────────────────────────────────

function EmptySearchState({
  query,
  onClear,
}: {
  query: string;
  onClear: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-4 text-center">
      <div
        className={cn(
          "w-12 h-12 rounded-xl",
          "bg-[#2b3b55]/40 border border-[#2b3b55]",
          "flex items-center justify-center",
        )}
      >
        <Search className="w-5 h-5 text-[#3d5070]" aria-hidden="true" />
      </div>

      <div className="max-w-xs">
        <p className="text-sm font-semibold text-white">No agents found</p>
        <p className="mt-1 text-xs text-[#92a4c9] leading-relaxed">
          No agents match&nbsp;
          <span className="text-white font-medium">&ldquo;{query}&rdquo;</span>.
          Try a different search term or clear the filter.
        </p>
      </div>

      <Button variant="ghost" size="sm" onClick={onClear}>
        Clear search
      </Button>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// AgentList
// ─────────────────────────────────────────────────────────────────────────────

export function AgentList() {
  // ── UI state ───────────────────────────────────────────────────────────────
  const [dialogOpen, setDialogOpen] = React.useState(false);
  const [editAgentId, setEditAgentId] = React.useState<string | undefined>(
    undefined,
  );
  const [resetConfirmId, setResetConfirmId] = React.useState<string | null>(
    null,
  );
  const [resetAllConfirm, setResetAllConfirm] = React.useState(false);
  const [searchQuery, setSearchQuery] = React.useState("");
  const [pipelineFilter, setPipelineFilter] = React.useState<string>("all");
  const [addAgentOpen, setAddAgentOpen] = React.useState(false);
  const [deleteConfirmId, setDeleteConfirmId] = React.useState<string | null>(
    null,
  );
  /** Which pipeline's stages dialog is open; null means closed. */
  const [managingPipeline, setManagingPipeline] = React.useState<{
    templateId: string;
    templateName: string;
  } | null>(null);

  // ── Data ───────────────────────────────────────────────────────────────────
  const { data, isLoading, isError, refetch } = useAgentConfigsByPipeline();
  const resetMutation = useResetAgentConfig();
  const resetAllMutation = useResetAllAgentConfigs();
  const updateMutation = useUpdateAgentConfig();
  const deleteAgentMutation = useDeleteAgentConfig();

  // ── Derived totals ─────────────────────────────────────────────────────────
  const totalAgents = data?.total_agents ?? 0;
  const totalPipelines = data?.pipelines.length ?? 0;

  // ── Pipeline filter options ────────────────────────────────────────────────
  const pipelineFilterOptions = React.useMemo(() => {
    if (!data) return [{ value: "all", label: "All Pipelines" }];
    return [
      { value: "all", label: "All Pipelines" },
      ...data.pipelines.map((p) => ({ value: p.template_id, label: p.name })),
    ];
  }, [data]);

  // ── Filtered pipeline data ─────────────────────────────────────────────────
  const filteredPipelines = React.useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    return (data?.pipelines ?? [])
      .filter(
        (pipeline) =>
          pipelineFilter === "all" || pipeline.template_id === pipelineFilter,
      )
      .map((pipeline) => ({
        ...pipeline,
        stages: pipeline.stages.map((stage) => ({
          ...stage,
          agents: stage.agents.filter(
            (agent) => q === "" || agent.display_name.toLowerCase().includes(q),
          ),
        })),
      }));
  }, [data, searchQuery, pipelineFilter]);

  // Whether the current filters yield zero matching agents
  const hasNoResults =
    !isLoading &&
    !isError &&
    filteredPipelines.every((p) =>
      p.stages.every((s) => s.agents.length === 0),
    );

  // ── Agent lookup helper (for reset confirm description) ────────────────────
  const agentToReset = React.useMemo<AgentConfigSummary | undefined>(() => {
    if (!resetConfirmId) return undefined;
    for (const pipeline of data?.pipelines ?? []) {
      for (const stage of pipeline.stages) {
        const found = stage.agents.find((a) => a.agent_id === resetConfirmId);
        if (found) return found;
      }
    }
    return undefined;
  }, [resetConfirmId, data]);

  // ── Handlers ───────────────────────────────────────────────────────────────

  /**
   * Unified edit handler:
   *  – no payload  → open the full AgentDialog
   *  – with payload → fire a quick inline update (toggle)
   */
  const handleEditAgent = React.useCallback(
    (agentId: string, payload?: AgentConfigUpdate) => {
      if (payload) {
        updateMutation.mutate(
          { agentId, payload },
          {
            onError: () => {
              toast.error(
                "Update failed",
                "Could not apply the change. Please try again.",
              );
            },
          },
        );
      } else {
        setEditAgentId(agentId);
        setDialogOpen(true);
      }
    },
    [updateMutation],
  );

  const handleDialogClose = React.useCallback(() => {
    setDialogOpen(false);
    // Delay clearing so closing animation doesn't flash stale data
    setTimeout(() => setEditAgentId(undefined), 250);
  }, []);

  const handleResetAgent = React.useCallback((agentId: string) => {
    setResetConfirmId(agentId);
  }, []);

  const handleResetConfirm = async () => {
    if (!resetConfirmId) return;
    try {
      await resetMutation.mutateAsync(resetConfirmId);
      toast.success(
        "Agent reset",
        "The agent configuration has been restored to its default.",
      );
    } catch {
      toast.error(
        "Reset failed",
        "Could not reset the agent configuration. Please try again.",
      );
    } finally {
      setResetConfirmId(null);
    }
  };

  const handleResetAllConfirm = async () => {
    try {
      await resetAllMutation.mutateAsync();
      toast.success(
        "All agents reset",
        "All agent configurations have been restored to their defaults.",
      );
    } catch {
      toast.error(
        "Reset failed",
        "Could not reset all agent configurations. Please try again.",
      );
    } finally {
      setResetAllConfirm(false);
    }
  };

  const handleClearSearch = () => {
    setSearchQuery("");
    setPipelineFilter("all");
  };

  const handleDeleteAgent = React.useCallback((agentId: string) => {
    setDeleteConfirmId(agentId);
  }, []);

  const handleDeleteAgentConfirm = async () => {
    if (!deleteConfirmId) return;
    // Find the agent name for the toast message
    let agentName = deleteConfirmId;
    outer: for (const pipeline of data?.pipelines ?? []) {
      for (const stage of pipeline.stages) {
        const found = stage.agents.find(
          (a: AgentConfigSummary) => a.agent_id === deleteConfirmId,
        );
        if (found) {
          agentName = found.display_name;
          break outer;
        }
      }
    }
    try {
      await deleteAgentMutation.mutateAsync(deleteConfirmId);
      toast.success("Agent deleted", `"${agentName}" has been removed.`);
    } catch {
      toast.error(
        "Delete failed",
        "Could not delete the agent. Please try again.",
      );
    } finally {
      setDeleteConfirmId(null);
    }
  };

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <>
      {/* ── Page header ──────────────────────────────────────────────────── */}
      <div className="flex items-start justify-between gap-4 mb-6">
        <div>
          <h2 className="text-lg font-semibold text-white leading-snug flex items-center gap-2.5">
            <span
              className={cn(
                "inline-flex items-center justify-center",
                "w-7 h-7 rounded-lg shrink-0",
                "bg-[#135bec]/10 border border-[#135bec]/20",
                "text-[#5b9eff]",
              )}
            >
              <Bot className="w-4 h-4" aria-hidden="true" />
            </span>
            Agent Configurations
          </h2>

          <p className="mt-1 text-sm text-[#92a4c9]">
            {isLoading ? (
              <span
                aria-hidden="true"
                className="inline-block h-3.5 w-48 bg-[#2b3b55] rounded animate-pulse"
              />
            ) : isError ? (
              <span className="text-[#f87171]">
                Could not load agent configurations
              </span>
            ) : (
              <>
                <span className="text-white font-medium">{totalAgents}</span>
                {" agents across "}
                <span className="text-white font-medium">{totalPipelines}</span>
                {totalPipelines === 1 ? " pipeline" : " pipelines"}
              </>
            )}
          </p>
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-2 shrink-0">
          <Button
            variant="primary"
            size="sm"
            leftIcon={<Plus className="w-3.5 h-3.5" aria-hidden="true" />}
            onClick={() => setAddAgentOpen(true)}
          >
            Add Agent
          </Button>

          <Button
            variant="danger"
            size="sm"
            leftIcon={<RotateCcw className="w-3.5 h-3.5" aria-hidden="true" />}
            onClick={() => setResetAllConfirm(true)}
            disabled={isLoading || isError || totalAgents === 0}
            title="Reset all agent configurations to their seeded defaults"
          >
            Reset All to Default
          </Button>
        </div>
      </div>

      {/* ── Search & filter toolbar ───────────────────────────────────────── */}
      {!isError && (
        <div className="flex items-center gap-3 mb-5 flex-wrap">
          {/* Search input */}
          <div className="flex-1 min-w-[200px] max-w-sm">
            <Input
              placeholder="Search agents by name…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              leftElement={
                <Search className="w-3.5 h-3.5" aria-hidden="true" />
              }
              aria-label="Search agents"
              disabled={isLoading}
            />
          </div>

          {/* Pipeline filter */}
          <div className="flex items-center gap-2 shrink-0">
            <Filter
              className="w-3.5 h-3.5 text-[#92a4c9] shrink-0"
              aria-hidden="true"
            />
            <div className="w-52">
              <Select
                options={pipelineFilterOptions}
                value={pipelineFilter}
                onChange={(e) => setPipelineFilter(e.target.value)}
                disabled={isLoading}
                aria-label="Filter by pipeline"
              />
            </div>
          </div>

          {/* Active filter badge */}
          {(searchQuery.trim() || pipelineFilter !== "all") && !isLoading && (
            <div className="flex items-center gap-2">
              <Badge variant="primary" size="sm" dot>
                Filtered
              </Badge>
              <button
                type="button"
                onClick={handleClearSearch}
                className={cn(
                  "text-xs text-[#92a4c9] hover:text-white",
                  "transition-colors duration-150",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#135bec] rounded",
                )}
              >
                Clear
              </button>
            </div>
          )}
        </div>
      )}

      {/* ── Main content ─────────────────────────────────────────────────── */}
      {isLoading ? (
        <ListSkeleton />
      ) : isError ? (
        <ErrorState onRetry={refetch} />
      ) : hasNoResults ? (
        <EmptySearchState
          query={searchQuery.trim() || pipelineFilter}
          onClear={handleClearSearch}
        />
      ) : (
        <div>
          {filteredPipelines.map((pipeline, i) => {
            // When searching, hide pipelines where ALL stages have 0 matching agents
            if (
              searchQuery.trim() &&
              pipeline.stages.every((s) => s.agents.length === 0)
            ) {
              return null;
            }

            return (
              <PipelineGroupSection
                key={pipeline.template_id}
                templateId={pipeline.template_id}
                pipelineName={pipeline.name}
                pipelineDescription={pipeline.description}
                stages={pipeline.stages}
                totalAgents={pipeline.total_agents}
                onEditAgent={handleEditAgent}
                onResetAgent={handleResetAgent}
                onDeleteAgent={handleDeleteAgent}
                onManageStages={(templateId, templateName) =>
                  setManagingPipeline({ templateId, templateName })
                }
                index={i}
              />
            );
          })}
        </div>
      )}

      {/* ── Edit dialog ───────────────────────────────────────────────────── */}
      <AgentDialog
        open={dialogOpen}
        onClose={handleDialogClose}
        agentId={editAgentId}
      />

      {/* ── Per-agent reset confirmation ──────────────────────────────────── */}
      <ConfirmDialog
        open={resetConfirmId !== null}
        onClose={() => setResetConfirmId(null)}
        onConfirm={handleResetConfirm}
        title="Reset Agent Configuration"
        description={
          agentToReset
            ? `Reset "${agentToReset.display_name}" to its seeded default? All custom changes — role, goal, backstory, LLM override, and iteration limit — will be permanently lost.`
            : "Reset this agent to its seeded default configuration? All custom changes will be permanently lost."
        }
        confirmLabel="Reset Agent"
        cancelLabel="Keep Changes"
        variant="danger"
        loading={resetMutation.isPending}
      />

      {/* ── Reset-all confirmation ────────────────────────────────────────── */}
      <ConfirmDialog
        open={resetAllConfirm}
        onClose={() => setResetAllConfirm(false)}
        onConfirm={handleResetAllConfirm}
        title="Reset All Agent Configurations"
        description={`This will restore all ${totalAgents} agent configurations across every pipeline to their seeded defaults. Every custom change — including roles, goals, backstories, LLM overrides, and iteration limits — will be permanently lost. This action cannot be undone.`}
        confirmLabel="Reset All Agents"
        cancelLabel="Cancel"
        variant="danger"
        loading={resetAllMutation.isPending}
      />

      {/* ── Add agent dialog ──────────────────────────────────────────────── */}
      <AddAgentDialog
        open={addAgentOpen}
        onClose={() => setAddAgentOpen(false)}
      />

      {/* ── Manage stages dialog (per-pipeline) ──────────────────────────── */}
      {managingPipeline && (
        <ManageStagesDialog
          open={managingPipeline !== null}
          onClose={() => setManagingPipeline(null)}
          templateId={managingPipeline.templateId}
          templateName={managingPipeline.templateName}
        />
      )}

      {/* ── Delete agent confirmation ─────────────────────────────────────── */}
      <ConfirmDialog
        open={Boolean(deleteConfirmId)}
        onClose={() => setDeleteConfirmId(null)}
        onConfirm={handleDeleteAgentConfirm}
        title="Delete Agent"
        description="Are you sure you want to delete this agent? This action cannot be undone."
        confirmLabel="Delete Agent"
        cancelLabel="Cancel"
        variant="danger"
        loading={deleteAgentMutation.isPending}
      />
    </>
  );
}
