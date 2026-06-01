"use client";

import React, { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ArrowLeft, FileText, Timer, Calendar, GitBranch, X, ChevronDown, ChevronUp } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

import { usePipelineRun } from "../../hooks/usePipeline";
import { usePipelineTemplate } from "../../hooks/usePipelineTemplates";
import { usePipelineWebSocket } from "../../hooks/usePipelineWebSocket";
import { useLLMProfiles } from "../../hooks/useLLMProfiles";
import { ResultsViewer } from "./ResultsViewer";
import { cn } from "../../lib/utils";
import { queryKeys } from "../../lib/queryClient";
import { pipelineApi } from "../../api/client";
import { toast } from "../../components/ui/Toast";
import type { PipelineStatus, PipelineEdgeConfig } from "../../types";

function formatDateTime(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    year: "numeric", month: "short", day: "2-digit",
    hour: "2-digit", minute: "2-digit",
  });
}

function formatDuration(start?: string | null, end?: string | null, secs?: number | null): string | null {
  if (secs != null) {
    const m = Math.floor(secs / 60);
    const s = Math.round(secs % 60);
    return m > 0 ? String(m) + "m " + String(s) + "s" : String(s) + "s";
  }
  if (!start || !end) return null;
  const ms = new Date(end).getTime() - new Date(start).getTime();
  const totalSec = Math.round(ms / 1000);
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  return m > 0 ? String(m) + "m " + String(s) + "s" : String(s) + "s";
}

const STATUS_STYLES: Record<PipelineStatus | string, { dot: string; text: string; label: string }> = {
  pending:   { dot: "bg-zinc-500",  text: "text-zinc-400",  label: "Pending" },
  running:   { dot: "bg-blue-500",  text: "text-blue-400",  label: "Running" },
  completed: { dot: "bg-green-500", text: "text-green-400", label: "Completed" },
  failed:    { dot: "bg-red-500",   text: "text-red-400",   label: "Failed" },
  cancelled: { dot: "bg-zinc-500",  text: "text-zinc-400",  label: "Cancelled" },
  paused:    { dot: "bg-yellow-500",text: "text-yellow-400",label: "Paused" },
};

function StatusBadge({ status }: { status: string }) {
  const s = STATUS_STYLES[status] ?? STATUS_STYLES.pending;
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-xs font-medium", s.text)}>
      <span className={cn("w-1.5 h-1.5 rounded-full", s.dot)} />
      {s.label}
    </span>
  );
}

export interface PipelineRunDetailPageProps {
  templateId: string;
  runId: string;
  /** Hide the per-node ("Nodes") results tab — end users only need the final output. */
  hideNodeResults?: boolean;
}

// ─────────────────────────────────────────────────────────────────────────────
// Helpers: topological sort + descendant calculation
// ─────────────────────────────────────────────────────────────────────────────

function topoSort(nodeIds: string[], edges: PipelineEdgeConfig[]): string[] {
  const inDegree: Record<string, number> = {};
  const adj: Record<string, string[]> = {};
  for (const n of nodeIds) { inDegree[n] = 0; adj[n] = []; }
  for (const e of edges) {
    if (adj[e.source_node_id] !== undefined && inDegree[e.target_node_id] !== undefined) {
      adj[e.source_node_id].push(e.target_node_id);
      inDegree[e.target_node_id]++;
    }
  }
  const queue = nodeIds.filter((n) => inDegree[n] === 0);
  const result: string[] = [];
  while (queue.length > 0) {
    const cur = queue.shift()!;
    result.push(cur);
    for (const next of adj[cur]) {
      if (--inDegree[next] === 0) queue.push(next);
    }
  }
  // Append any cycle-stranded nodes
  for (const n of nodeIds) { if (!result.includes(n)) result.push(n); }
  return result;
}

function getDescendants(nodeId: string, edges: PipelineEdgeConfig[]): Set<string> {
  const adj: Record<string, string[]> = {};
  for (const e of edges) {
    if (!adj[e.source_node_id]) adj[e.source_node_id] = [];
    adj[e.source_node_id].push(e.target_node_id);
  }
  const visited = new Set<string>();
  const queue = [nodeId];
  while (queue.length > 0) {
    const cur = queue.shift()!;
    if (visited.has(cur)) continue;
    visited.add(cur);
    for (const next of (adj[cur] ?? [])) queue.push(next);
  }
  return visited;
}

// ─────────────────────────────────────────────────────────────────────────────
// DeriveRunModal
// ─────────────────────────────────────────────────────────────────────────────

interface TemplateNodeInfo {
  node_id: string;
  label: string;
  node_type: string;
  enabled: boolean;
}

interface DeriveRunModalProps {
  runId: string;
  templateId: string;
  nodeIds: string[];
  templateNodes: TemplateNodeInfo[];
  edges: PipelineEdgeConfig[];
  onClose: () => void;
  onDerived: (newRunId: string) => void;
}

function DeriveRunModal({ runId, templateId, nodeIds, templateNodes, edges, onClose, onDerived }: DeriveRunModalProps) {
  const { data: llmProfiles } = useLLMProfiles();
  const qc = useQueryClient();

  // Phase 1: Build ordered node list with labels
  const sortedNodes = useMemo<TemplateNodeInfo[]>(() => {
    const nodeSet = new Set(nodeIds);
    const base: TemplateNodeInfo[] = templateNodes.length > 0
      ? templateNodes.filter((n) => nodeSet.has(n.node_id))
      : nodeIds.map((id) => ({ node_id: id, label: id, node_type: "", enabled: true }));
    // Include run nodes not found in template (fallback)
    const baseIds = new Set(base.map((n) => n.node_id));
    const extra = nodeIds
      .filter((id) => !baseIds.has(id))
      .map((id): TemplateNodeInfo => ({ node_id: id, label: id, node_type: "", enabled: true }));
    const all = [...base, ...extra];
    const sorted = topoSort(all.map((n) => n.node_id), edges);
    const map = new Map(all.map((n) => [n.node_id, n]));
    return sorted.map((id) => map.get(id)).filter(Boolean) as TemplateNodeInfo[];
  }, [templateNodes, nodeIds, edges]);

  const [selectedNode, setSelectedNode] = useState(sortedNodes[0]?.node_id ?? "");
  const [label, setLabel] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [llmProfileId, setLlmProfileId] = useState("");

  // Node input playground state
  const [nodeInputEnabled, setNodeInputEnabled] = useState<Set<string>>(new Set());
  const [nodeInputValues, setNodeInputValues] = useState<Record<string, string>>({});
  const [nodeInputErrors, setNodeInputErrors] = useState<Record<string, string>>({});

  // Phase 2: Compute inheritance preview
  const { rerunNodes, inheritedNodes } = useMemo(() => {
    if (!selectedNode) return { rerunNodes: [] as TemplateNodeInfo[], inheritedNodes: [] as TemplateNodeInfo[] };
    const descendants = getDescendants(selectedNode, edges);
    return {
      rerunNodes: sortedNodes.filter((n) => descendants.has(n.node_id)),
      inheritedNodes: sortedNodes.filter((n) => !descendants.has(n.node_id)),
    };
  }, [selectedNode, sortedNodes, edges]);

  // Clear input overrides for nodes that are no longer in the re-run set
  useEffect(() => {
    const rerunSet = new Set(rerunNodes.map((n) => n.node_id));
    setNodeInputEnabled((prev) => {
      const next = new Set(prev);
      for (const id of prev) { if (!rerunSet.has(id)) next.delete(id); }
      return next;
    });
  }, [rerunNodes]);

  function toggleInputOverride(nodeId: string) {
    setNodeInputEnabled((prev) => {
      const next = new Set(prev);
      if (next.has(nodeId)) {
        next.delete(nodeId);
        setNodeInputErrors((e) => { const n = { ...e }; delete n[nodeId]; return n; });
      } else {
        next.add(nodeId);
        if (!nodeInputValues[nodeId]) {
          setNodeInputValues((v) => ({ ...v, [nodeId]: "{}" }));
        }
      }
      return next;
    });
  }

  function validateJson(nodeId: string, raw: string) {
    try {
      JSON.parse(raw);
      setNodeInputErrors((e) => { const n = { ...e }; delete n[nodeId]; return n; });
    } catch {
      setNodeInputErrors((e) => ({ ...e, [nodeId]: "Invalid JSON" }));
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedNode) return;

    // Validate all enabled JSON overrides before submitting
    const parseErrors: Record<string, string> = {};
    const parsedOverrides: Record<string, unknown> = {};
    for (const nodeId of nodeInputEnabled) {
      const raw = nodeInputValues[nodeId] ?? "{}";
      try {
        parsedOverrides[nodeId] = JSON.parse(raw);
      } catch {
        parseErrors[nodeId] = "Invalid JSON — fix before submitting";
      }
    }
    if (Object.keys(parseErrors).length > 0) {
      setNodeInputErrors(parseErrors);
      return;
    }

    setIsSubmitting(true);
    try {
      const derived = await pipelineApi.deriveRun(runId, {
        rerun_from_node: selectedNode,
        label: label || undefined,
        llm_profile_id: llmProfileId || undefined,
        node_input_overrides: Object.keys(parsedOverrides).length > 0 ? parsedOverrides : undefined,
      });
      qc.invalidateQueries({ queryKey: queryKeys.pipelineRuns.lists() });
      toast.success(
        "Derived run created",
        `ID: ${derived.id.slice(0, 8)} — check run history to view it`,
        6000,
      );
      onDerived(derived.id);
      onClose();
    } catch {
      toast.error("Failed to create derived run");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-xl rounded-2xl border border-[#2b3b55] bg-[#111827] p-6 shadow-2xl max-h-[90vh] flex flex-col">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold text-white flex items-center gap-2">
            <GitBranch className="w-4 h-4 text-blue-400" />
            Re-run from Checkpoint
          </h2>
          <button onClick={onClose} className="text-[#3d5070] hover:text-white transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4 overflow-y-auto flex-1 pr-1">
          {/* Phase 1: Node selector with labels */}
          <div>
            <label className="block text-[10px] uppercase tracking-wider text-[#3d5070] mb-1.5">
              Re-run from node
            </label>
            <select
              value={selectedNode}
              onChange={(e) => setSelectedNode(e.target.value)}
              className="w-full rounded-lg border border-[#2b3b55] bg-[#18202F] text-sm text-white px-3 py-2 focus:outline-none focus:border-blue-500"
            >
              {sortedNodes.map((n) => (
                <option key={n.node_id} value={n.node_id}>
                  {n.label}{n.node_type ? ` (${n.node_type})` : ""}
                </option>
              ))}
            </select>
          </div>

          {/* Phase 2: Inheritance preview chips */}
          {selectedNode && (
            <div className="rounded-lg border border-[#2b3b55] bg-[#0d1420] p-3 space-y-2.5">
              {inheritedNodes.length > 0 && (
                <div>
                  <p className="text-[10px] uppercase tracking-wider text-[#3d5070] mb-1.5">
                    Inherited (reused)
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {inheritedNodes.map((n) => (
                      <span
                        key={n.node_id}
                        className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] bg-zinc-800 text-zinc-400 border border-zinc-700"
                      >
                        {n.label}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {rerunNodes.length > 0 && (
                <div>
                  <p className="text-[10px] uppercase tracking-wider text-[#3d5070] mb-1.5">
                    Will re-run
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {rerunNodes.map((n) => (
                      <span
                        key={n.node_id}
                        className={cn(
                          "inline-flex items-center px-2 py-0.5 rounded-full text-[10px] border",
                          n.node_id === selectedNode
                            ? "bg-blue-900/50 text-blue-300 border-blue-600"
                            : "bg-blue-950/30 text-blue-400/70 border-blue-800/50",
                        )}
                      >
                        {n.label}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Node Input Playground */}
          {rerunNodes.length > 0 && (
            <div>
              <p className="text-[10px] uppercase tracking-wider text-[#3d5070] mb-2">
                Node Input Overrides
              </p>
              <div className="space-y-2">
                {rerunNodes.map((n) => {
                  const enabled = nodeInputEnabled.has(n.node_id);
                  const err = nodeInputErrors[n.node_id];
                  return (
                    <div
                      key={n.node_id}
                      className={cn(
                        "rounded-lg border bg-[#0d1420] overflow-hidden",
                        enabled ? "border-blue-600/50" : "border-[#2b3b55]",
                      )}
                    >
                      <button
                        type="button"
                        onClick={() => toggleInputOverride(n.node_id)}
                        className="w-full flex items-center justify-between px-3 py-2 hover:bg-[#18202F] transition-colors"
                      >
                        <span className="text-xs text-[#92a4c9] font-medium">
                          {n.label}
                          {n.node_type && (
                            <span className="ml-1.5 text-[10px] text-[#3d5070]">
                              ({n.node_type})
                            </span>
                          )}
                        </span>
                        <span
                          className={cn(
                            "text-[10px] px-2 py-0.5 rounded-full border transition-colors",
                            enabled
                              ? "bg-blue-900/40 text-blue-300 border-blue-600/60"
                              : "bg-zinc-800/40 text-zinc-500 border-zinc-700/60",
                          )}
                        >
                          {enabled ? "Override ON" : "Use parent output"}
                        </span>
                      </button>
                      {enabled && (
                        <div className="px-3 pb-3">
                          <textarea
                            value={nodeInputValues[n.node_id] ?? "{}"}
                            onChange={(e) => {
                              const val = e.target.value;
                              setNodeInputValues((v) => ({ ...v, [n.node_id]: val }));
                              // Clear error optimistically while typing
                              setNodeInputErrors((er) => { const next = { ...er }; delete next[n.node_id]; return next; });
                            }}
                            onBlur={(e) => validateJson(n.node_id, e.target.value)}
                            rows={4}
                            spellCheck={false}
                            placeholder='{"key": "value"}'
                            className={cn(
                              "w-full rounded-md border bg-[#18202F] text-xs text-white font-mono px-2.5 py-2 resize-y focus:outline-none",
                              err ? "border-red-500/70 focus:border-red-500" : "border-[#2b3b55] focus:border-blue-500",
                            )}
                          />
                          {err && (
                            <p className="text-[10px] text-red-400 mt-1">{err}</p>
                          )}
                          <p className="text-[10px] text-[#3d5070] mt-1">
                            JSON object — replaces collected parent outputs for this node.
                          </p>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Label */}
          <div>
            <label className="block text-[10px] uppercase tracking-wider text-[#3d5070] mb-1.5">
              Label (optional)
            </label>
            <input
              type="text"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="e.g. gpt-4o retry"
              className="w-full rounded-lg border border-[#2b3b55] bg-[#18202F] text-sm text-white px-3 py-2 placeholder:text-[#3d5070] focus:outline-none focus:border-blue-500"
            />
          </div>

          {/* Phase 3: Advanced — LLM override */}
          <div>
            <button
              type="button"
              onClick={() => setShowAdvanced((v) => !v)}
              className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-[#3d5070] hover:text-[#92a4c9] transition-colors"
            >
              {showAdvanced ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
              Advanced
            </button>
            {showAdvanced && (
              <div className="mt-2">
                <label className="block text-[10px] uppercase tracking-wider text-[#3d5070] mb-1.5">
                  LLM Profile override
                </label>
                <select
                  value={llmProfileId}
                  onChange={(e) => setLlmProfileId(e.target.value)}
                  className="w-full rounded-lg border border-[#2b3b55] bg-[#18202F] text-sm text-white px-3 py-2 focus:outline-none focus:border-blue-500"
                >
                  <option value="">Use run default</option>
                  {llmProfiles?.items.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name} — {p.model}{p.is_default ? " (default)" : ""}
                    </option>
                  ))}
                </select>
                <p className="text-[10px] text-[#3d5070] mt-1">Applies to all re-run nodes.</p>
              </div>
            )}
          </div>

          <div className="flex gap-3 pt-1 sticky bottom-0 bg-[#111827] pb-1">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 rounded-lg border border-[#2b3b55] px-4 py-2 text-sm text-[#92a4c9] hover:text-white transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!selectedNode || isSubmitting}
              className="flex-1 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 px-4 py-2 text-sm font-medium text-white transition-colors"
            >
              {isSubmitting ? "Creating…" : "Create derived run"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export function PipelineRunDetailPage({ templateId, runId, hideNodeResults = false }: PipelineRunDetailPageProps) {
  const qc = useQueryClient();
  const { data: run, isLoading: runLoading, isError: runError } = usePipelineRun(runId);
  const { data: template } = usePipelineTemplate(templateId);
  const [showDeriveModal, setShowDeriveModal] = useState(false);

  const isActive = run?.status === "running" || run?.status === "pending";
  const isV3 = !!(run?.node_statuses);
  const canDerive = isV3 && run?.status === "completed";

  // Connect WebSocket only while the run is active so we know when it finishes.
  const { isTerminal } = usePipelineWebSocket({
    runId,
    enabled: isActive,
  });

  // When the WebSocket signals the run is done, refetch the run detail so
  // results are displayed without requiring a manual page refresh.
  useEffect(() => {
    if (isTerminal) {
      qc.invalidateQueries({ queryKey: queryKeys.pipelineRuns.detail(runId) });
    }
  }, [isTerminal, runId, qc]);

  const templateNodes = template?.nodes?.map((n) => ({
    node_id: n.node_id,
    label: n.label,
    node_type: n.node_type,
    enabled: n.enabled ?? true,
  })) ?? [];

  const templateEdges = template?.edges ?? [];

  const nodeIds = run?.node_statuses ? Object.keys(run.node_statuses) : [];

  const duration = run
    ? formatDuration(run.started_at, run.completed_at, run.duration_seconds)
    : null;

  return (
    <div className="flex flex-col gap-6 p-6 max-w-5xl mx-auto w-full">
      <div className="flex items-center gap-3">
        <Link
          href={"/pipelines/" + templateId + "/runs"}
          className="inline-flex items-center gap-1.5 text-sm text-[#92a4c9] hover:text-white transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to run history
        </Link>
      </div>

      <div className="rounded-2xl border border-[#2b3b55] bg-[#18202F] p-5">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-lg font-semibold text-white">Run Detail</h1>
            <p className="text-xs text-[#3d5070] font-mono mt-0.5">{runId}</p>
          </div>
          <div className="flex items-center gap-3">
            {run && <StatusBadge status={run.status} />}
            {canDerive && (
              <button
                onClick={() => setShowDeriveModal(true)}
                className="inline-flex items-center gap-1.5 text-xs font-medium text-blue-400 hover:text-white border border-blue-400/30 hover:border-blue-400 px-3 py-1.5 rounded-lg transition-colors"
              >
                <GitBranch className="w-3 h-3" />
                Re-run from checkpoint
              </button>
            )}
          </div>
        </div>

        {run && (
          <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div>
              <p className="text-[10px] uppercase tracking-wider text-[#3d5070] mb-1">Template</p>
              <p className="text-xs text-[#92a4c9] font-mono">{templateId}</p>
            </div>
            <div>
              <p className="text-[10px] uppercase tracking-wider text-[#3d5070] mb-1">Document</p>
              <span className="inline-flex items-center gap-1 text-xs text-[#92a4c9]">
                <FileText className="w-3 h-3" />
                {run.document_filename || "—"}
              </span>
            </div>
            <div>
              <p className="text-[10px] uppercase tracking-wider text-[#3d5070] mb-1">Started</p>
              <span className="inline-flex items-center gap-1 text-xs text-[#92a4c9]">
                <Calendar className="w-3 h-3" />
                {formatDateTime(run.started_at ?? run.created_at)}
              </span>
            </div>
            <div>
              <p className="text-[10px] uppercase tracking-wider text-[#3d5070] mb-1">Duration</p>
              <span className="inline-flex items-center gap-1 text-xs text-[#92a4c9]">
                <Timer className="w-3 h-3" />
                {duration ?? "—"}
              </span>
            </div>
          </div>
        )}

        {run?.error_message && (
          <div className="mt-4 rounded-lg border border-red-900/40 bg-red-950/20 p-3">
            <p className="text-xs text-red-400">{run.error_message}</p>
          </div>
        )}
      </div>

      {runLoading && (
        <div className="flex items-center justify-center py-16">
          <div className="h-6 w-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
        </div>
      )}

      {runError && (
        <div className="rounded-2xl border border-red-900/40 bg-red-950/20 p-6 text-center">
          <p className="text-sm text-red-400">Failed to load run details.</p>
        </div>
      )}

      {run && !runLoading && (
        <ResultsViewer
          run={run}
          templateNodes={templateNodes}
          hideNodeResults={hideNodeResults}
        />
      )}

      {showDeriveModal && (
        <DeriveRunModal
          runId={runId}
          templateId={templateId}
          nodeIds={nodeIds}
          templateNodes={templateNodes}
          edges={templateEdges}
          onClose={() => setShowDeriveModal(false)}
          onDerived={(newId) => {
            qc.invalidateQueries({ queryKey: queryKeys.pipelineRuns.lists() });
          }}
        />
      )}
    </div>
  );
}
