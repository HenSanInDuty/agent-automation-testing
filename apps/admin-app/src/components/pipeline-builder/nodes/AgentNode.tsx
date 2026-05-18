"use client";

import { Handle, Position } from "@xyflow/react";
import type { NodeProps } from "@xyflow/react";
import type { AgentNodeData } from "@/store/builderStore";

export function AgentNode({ data, selected }: NodeProps) {
  const typedData = data as AgentNodeData;

  const statusColors: Record<string, string> = {
    idle: "border-zinc-600",
    running: "border-blue-500 animate-pulse",
    completed: "border-green-500",
    failed: "border-red-500",
  };

  const nodeIcons: Record<string, string> = {
    input: "📥",
    output: "📤",
    agent: "🤖",
    pure_python: "🐍",
  };

  const status = typedData.status || "idle";
  const nodeType = typedData.nodeType;

  return (
    <div
      className={`
                px-4 py-3 rounded-xl border-2 bg-zinc-900 shadow-lg
                min-w-40 transition-all
                ${statusColors[status] || statusColors.idle}
                ${selected ? "ring-2 ring-blue-400" : ""}
                ${!typedData.enabled ? "opacity-50" : ""}
            `}
    >
      {/* Input Handle */}
      {nodeType !== "input" && (
        <Handle
          type="target"
          position={Position.Top}
          className="w-3! h-3! bg-blue-500! border-2! border-zinc-800!"
        />
      )}

      {/* Node Content */}
      <div className="flex items-center gap-2">
        <span className="text-lg">{nodeIcons[nodeType] || "🤖"}</span>
        <div>
          <div className="font-medium text-sm text-zinc-100">
            {typedData.label}
          </div>
          {typedData.description && (
            <div className="text-xs text-zinc-400 mt-0.5 max-w-35 truncate">
              {typedData.description}
            </div>
          )}
        </div>
      </div>

      {/* Status indicator for running */}
      {status === "running" && (
        <div className="mt-2 h-1 bg-zinc-700 rounded-full overflow-hidden">
          <div className="h-full w-1/2 bg-blue-500 animate-pulse rounded-full" />
        </div>
      )}

      {/* Output Handle */}
      {nodeType !== "output" && (
        <Handle
          type="source"
          position={Position.Bottom}
          className="w-3! h-3! bg-green-500! border-2! border-zinc-800!"
        />
      )}
    </div>
  );
}
