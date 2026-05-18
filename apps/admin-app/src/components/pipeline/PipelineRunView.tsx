"use client";

import { useMemo } from "react";
import {
  ReactFlow,
  MiniMap,
  Controls,
  Background,
  BackgroundVariant,
  ReactFlowProvider,
  type Node,
  type Edge,
  type NodeTypes,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { usePipelineStore } from "@/store/pipelineStore";
import { AgentNode } from "../pipeline-builder/nodes/AgentNode";
import { InputNode } from "../pipeline-builder/nodes/InputNode";
import { OutputNode } from "../pipeline-builder/nodes/OutputNode";
import type { PipelineNodeConfig, PipelineEdgeConfig } from "@/types";
import type { AgentNodeData } from "@/store/builderStore";

const nodeTypes: NodeTypes = {
  agentNode: AgentNode,
  inputNode: InputNode,
  outputNode: OutputNode,
};

export interface PipelineRunViewProps {
  templateNodes: PipelineNodeConfig[];
  templateEdges: PipelineEdgeConfig[];
}

function PipelineRunViewInner({
  templateNodes,
  templateEdges,
}: PipelineRunViewProps) {
  // Try to get nodeStatuses — fall back gracefully if not yet in store
  const nodeStatuses = usePipelineStore((s) => s.nodeStatuses ?? {});

  // Convert template nodes to React Flow nodes with live status
  const nodes: Node[] = useMemo(() => {
    return templateNodes.map((n) => ({
      id: n.node_id,
      type:
        n.node_type === "input"
          ? "inputNode"
          : n.node_type === "output"
            ? "outputNode"
            : "agentNode",
      position: { x: n.position_x, y: n.position_y },
      data: {
        label: n.label,
        agentId: n.agent_id ?? "",
        nodeType: n.node_type,
        description: n.description,
        enabled: n.enabled,
        status: (nodeStatuses[n.node_id] || "idle") as AgentNodeData["status"],
      } satisfies AgentNodeData,
      draggable: false,
    }));
  }, [templateNodes, nodeStatuses]);

  // Convert template edges with animation based on node statuses
  const edges: Edge[] = useMemo(() => {
    return templateEdges.map((e) => ({
      id: e.edge_id,
      source: e.source_node_id,
      target: e.target_node_id,
      type: "smoothstep",
      animated:
        nodeStatuses[e.source_node_id] === "completed" &&
        nodeStatuses[e.target_node_id] === "running",
      style: {
        stroke:
          nodeStatuses[e.source_node_id] === "completed"
            ? "#22c55e"
            : nodeStatuses[e.source_node_id] === "failed"
              ? "#ef4444"
              : "#555",
      },
    }));
  }, [templateEdges, nodeStatuses]);

  return (
    <div className="w-full h-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        panOnDrag
        zoomOnScroll
        className="bg-zinc-950"
      >
        <Background
          variant={BackgroundVariant.Dots}
          gap={20}
          size={1}
          color="#222"
        />
        <MiniMap
          nodeColor={(n) => {
            const status = (n.data as AgentNodeData)?.status;
            if (status === "running") return "#3b82f6";
            if (status === "completed") return "#22c55e";
            if (status === "failed") return "#ef4444";
            return "#555";
          }}
          className="bg-zinc-900/80! rounded-lg!"
        />
        <Controls className="bg-zinc-800! rounded-lg!" />
      </ReactFlow>
    </div>
  );
}

export function PipelineRunView(props: PipelineRunViewProps) {
  return (
    <ReactFlowProvider>
      <PipelineRunViewInner {...props} />
    </ReactFlowProvider>
  );
}
