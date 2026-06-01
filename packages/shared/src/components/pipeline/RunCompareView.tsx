"use client";

import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Clock, SkipForward, Download } from "lucide-react";
import { cn } from "../../lib/utils";
import { pipelineApi } from "../../api/client";
import { PrettyOutput } from "./PrettyOutput";
import type { NodeCompareItem } from "../../types";

// ─────────────────────────────────────────────────────────────────────────────
// Props
// ─────────────────────────────────────────────────────────────────────────────

export interface RunCompareViewProps {
  runIds: string[];
  nodeIds: string[];
}

// ─────────────────────────────────────────────────────────────────────────────
// RunColumn — one run's result for a node
// ─────────────────────────────────────────────────────────────────────────────

function RunColumn({ item }: { item: NodeCompareItem }) {
  const durationLabel = item.duration_seconds != null
    ? (item.duration_seconds < 60
        ? `${Math.round(item.duration_seconds)}s`
        : `${Math.floor(item.duration_seconds / 60)}m ${Math.round(item.duration_seconds % 60)}s`)
    : null;

  const outputStr = item.output != null
    ? (typeof item.output === "string" ? item.output : JSON.stringify(item.output, null, 2))
    : null;

  return (
    <div className="flex flex-col gap-2 min-w-0">
      <div className="flex items-center gap-2 flex-wrap">
        <code className="text-[10px] font-mono text-[#92a4c9] bg-[#1e2a3d] px-1.5 py-0.5 rounded border border-[#2b3b55]">
          {item.run_id.slice(0, 12)}…
        </code>
        {item.is_inherited && (
          <span className="inline-flex items-center gap-1 text-[10px] font-medium text-yellow-400 bg-yellow-400/10 border border-yellow-400/20 px-1.5 py-0.5 rounded">
            <SkipForward className="w-2.5 h-2.5" />
            Inherited
          </span>
        )}
        {durationLabel && (
          <span className="inline-flex items-center gap-1 text-[10px] text-[#3d5070]">
            <Clock className="w-2.5 h-2.5" />
            {durationLabel}
          </span>
        )}
      </div>
      {item.llm_profile_id && (
        <span className="text-[10px] text-[#3d5070] font-mono truncate">
          {item.llm_profile_id}
        </span>
      )}
      <a
        href={pipelineApi.getNodeExportUrl(item.run_id, "")}
        download
        className="w-fit inline-flex items-center gap-1 text-[10px] text-[#92a4c9] hover:text-white border border-[#2b3b55] hover:border-[#92a4c9] px-2 py-0.5 rounded transition-colors"
      >
        <Download className="w-3 h-3" />
        JSON
      </a>
      <div className="rounded-lg border border-[#2b3b55] bg-[#111827] overflow-hidden">
        {outputStr ? (
          <PrettyOutput value={outputStr} />
        ) : (
          <p className="p-4 text-xs text-[#3d5070]">No output</p>
        )}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// RunCompareView
// ─────────────────────────────────────────────────────────────────────────────

export function RunCompareView({ runIds, nodeIds }: RunCompareViewProps) {
  const [activeNode, setActiveNode] = useState(nodeIds[0] ?? "");

  const { data, isLoading, isError } = useQuery({
    queryKey: ["compare", runIds.join(","), activeNode],
    queryFn: () => pipelineApi.compareRunNodes(runIds, activeNode),
    enabled: runIds.length > 0 && !!activeNode,
    staleTime: 5 * 60_000,
  });

  return (
    <div className="flex flex-col gap-4">
      {/* Node selector tabs */}
      {nodeIds.length > 1 && (
        <div className="flex flex-wrap gap-2">
          {nodeIds.map((id) => (
            <button
              key={id}
              onClick={() => setActiveNode(id)}
              className={cn(
                "text-xs px-3 py-1.5 rounded-lg border transition-colors",
                activeNode === id
                  ? "border-blue-500 bg-blue-500/10 text-blue-400"
                  : "border-[#2b3b55] text-[#92a4c9] hover:text-white hover:border-[#92a4c9]",
              )}
            >
              {id.slice(0, 16)}
            </button>
          ))}
        </div>
      )}

      {isLoading && (
        <div className="flex items-center justify-center py-12">
          <div className="h-5 w-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
        </div>
      )}

      {isError && (
        <div className="rounded-lg border border-red-900/40 bg-red-950/20 p-4 text-sm text-red-400">
          Failed to load comparison data.
        </div>
      )}

      {data && (
        <div
          className="grid gap-4"
          style={{ gridTemplateColumns: `repeat(${data.runs.length}, minmax(0, 1fr))` }}
        >
          {data.runs.map((item) => (
            <RunColumn key={item.run_id} item={item} />
          ))}
        </div>
      )}

      {data && data.runs.length === 0 && (
        <div className="py-8 text-center text-sm text-[#3d5070]">
          No data found for selected node across these runs.
        </div>
      )}
    </div>
  );
}
