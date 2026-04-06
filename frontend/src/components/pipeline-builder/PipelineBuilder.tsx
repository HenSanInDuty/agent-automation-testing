"use client";

import { useCallback, useRef, useEffect, useState } from "react";
import { toast } from "@/components/ui/Toast";
import {
  ReactFlow,
  MiniMap,
  Controls,
  Background,
  BackgroundVariant,
  Panel,
  useReactFlow,
  ConnectionLineType,
  type Node,
  type Edge,
  type NodeTypes,
  ReactFlowProvider,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { useBuilderStore, type AgentNodeData } from "@/store/builderStore";
import {
  usePipelineTemplate,
  useUpdateTemplate,
} from "@/hooks/usePipelineTemplates";
import { AgentNode } from "./nodes/AgentNode";
import { InputNode } from "./nodes/InputNode";
import { OutputNode } from "./nodes/OutputNode";
import { AgentCatalogSidebar } from "./AgentCatalogSidebar";
import { NodePropertiesPanel } from "./NodePropertiesPanel";
import { BuilderToolbar } from "./BuilderToolbar";
import { ValidationPanel } from "./ValidationPanel";
import type { PipelineNodeConfig, PipelineEdgeConfig } from "@/types";

const nodeTypes: NodeTypes = {
  agentNode: AgentNode,
  inputNode: InputNode,
  outputNode: OutputNode,
};

// ── Conversion helpers ──────────────────────────────────────────────────────

function templateNodeToFlowNode(n: PipelineNodeConfig): Node {
  return {
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
      status: "idle",
      timeout_seconds: n.timeout_seconds,
      configOverrides: n.config_overrides ?? {},
    } satisfies AgentNodeData,
  };
}

function templateEdgeToFlowEdge(e: PipelineEdgeConfig): Edge {
  return {
    id: e.edge_id,
    source: e.source_node_id,
    target: e.target_node_id,
    type: "smoothstep",
    animated: e.animated,
    sourceHandle: e.source_handle,
    targetHandle: e.target_handle,
    label: e.label,
  };
}

function flowNodeToTemplateNode(n: Node): PipelineNodeConfig {
  const d = n.data as AgentNodeData;
  return {
    node_id: n.id,
    node_type: d.nodeType as "input" | "output" | "agent" | "pure_python",
    agent_id: d.agentId || undefined,
    label: d.label,
    description: d.description ?? "",
    position_x: n.position.x,
    position_y: n.position.y,
    timeout_seconds: d.timeout_seconds ?? 300,
    retry_count: 0,
    enabled: d.enabled,
    config_overrides: (d.configOverrides as Record<string, unknown>) ?? {},
  };
}

function flowEdgeToTemplateEdge(e: Edge): PipelineEdgeConfig {
  return {
    edge_id: e.id,
    source_node_id: e.source,
    target_node_id: e.target,
    source_handle: e.sourceHandle ?? undefined,
    target_handle: e.targetHandle ?? undefined,
    label: typeof e.label === "string" ? e.label : undefined,
    animated: e.animated ?? false,
  };
}

// ── Inner builder (needs ReactFlowProvider context) ──────────────────────────

function PipelineBuilderInner({ templateId }: { templateId: string }) {
  const reactFlowWrapper = useRef<HTMLDivElement>(null);
  const { screenToFlowPosition } = useReactFlow();
  const [initialized, setInitialized] = useState(false);

  const {
    nodes,
    edges,
    onNodesChange,
    onEdgesChange,
    onConnect,
    addNode,
    selectNode,
    selectedNodeId,
    validationErrors,
    isValid,
    isDirty,
    isSaving,
    setTemplate,
    templateName,
    templateDescription,
  } = useBuilderStore();

  // ── Load template ──
  const { data: template, isLoading } = usePipelineTemplate(templateId);
  const updateTemplateMutation = useUpdateTemplate(templateId);

  // Initialize builder when template loads
  useEffect(() => {
    if (template && !initialized) {
      const flowNodes = template.nodes.map(templateNodeToFlowNode);
      const flowEdges = template.edges.map(templateEdgeToFlowEdge);
      setTemplate(
        templateId,
        template.name,
        template.description,
        flowNodes,
        flowEdges,
      );
      setInitialized(true);
    }
  }, [template, initialized, templateId, setTemplate]);

  // ── Save handler ──
  const handleSave = useCallback(async () => {
    const state = useBuilderStore.getState();

    // Guard: warn but still allow saving an invalid DAG (warn only)
    if (!state.isValid && state.nodes.length > 0) {
      toast.warning(
        "DAG has validation errors",
        `Saving anyway — fix ${state.validationErrors.length} error(s) before running.`,
        6000,
      );
    }

    useBuilderStore.setState({ isSaving: true });
    try {
      await updateTemplateMutation.mutateAsync({
        nodes: state.nodes.map(flowNodeToTemplateNode),
        edges: state.edges.map(flowEdgeToTemplateEdge),
        name: state.templateName,
        description: state.templateDescription,
      });
      useBuilderStore.setState({ isDirty: false });
      toast.success(
        "Pipeline saved",
        `"${state.templateName}" has been saved.`,
      );
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "An unexpected error occurred.";
      // Surface DAG validation detail from the backend (HTTP 422)
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? message;
      toast.error("Save failed", detail, 8000);
    } finally {
      useBuilderStore.setState({ isSaving: false });
    }
  }, [updateTemplateMutation]);

  // ── Drag-over handler ──
  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
  }, []);

  // ── Drop handler ──
  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();

      const rawData = event.dataTransfer.getData("application/reactflow");
      if (!rawData) return;

      let catalogItem: {
        agentId: string;
        label: string;
        nodeType: string;
        description: string;
      };
      try {
        catalogItem = JSON.parse(rawData);
      } catch {
        return;
      }

      const {
        agentId,
        label,
        nodeType: rawNodeType,
        description,
      } = catalogItem;
      const nodeType = rawNodeType as AgentNodeData["nodeType"];

      const position = screenToFlowPosition({
        x: event.clientX,
        y: event.clientY,
      });

      const newNodeId = `${agentId}_${Date.now()}`;

      const newNode: Node = {
        id: newNodeId,
        type:
          rawNodeType === "input"
            ? "inputNode"
            : rawNodeType === "output"
              ? "outputNode"
              : "agentNode",
        position,
        data: {
          label,
          agentId,
          nodeType,
          description,
          enabled: true,
          status: "idle",
          timeout_seconds: 300,
          configOverrides: {},
        } satisfies AgentNodeData,
      };

      addNode(newNode);
    },
    [screenToFlowPosition, addNode],
  );

  const onNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      selectNode(node.id);
    },
    [selectNode],
  );

  const onPaneClick = useCallback(() => {
    selectNode(null);
  }, [selectNode]);

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center bg-zinc-950">
        <div className="flex flex-col items-center gap-3">
          <div className="h-8 w-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
          <p className="text-sm text-zinc-400">Loading pipeline...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full">
      {/* Left: Agent Catalog Sidebar */}
      <AgentCatalogSidebar />

      {/* Center: React Flow Canvas */}
      <div ref={reactFlowWrapper} className="flex-1 h-full relative">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onDragOver={onDragOver}
          onDrop={onDrop}
          onNodeClick={onNodeClick}
          onPaneClick={onPaneClick}
          nodeTypes={nodeTypes}
          fitView
          snapToGrid
          snapGrid={[20, 20]}
          connectionLineType={ConnectionLineType.SmoothStep}
          defaultEdgeOptions={{
            type: "smoothstep",
            animated: false,
          }}
          className="bg-zinc-950"
        >
          <Background
            variant={BackgroundVariant.Dots}
            gap={20}
            size={1}
            color="#333"
          />
          <MiniMap
            nodeColor={(n) => {
              const d = n.data as AgentNodeData;
              if (d?.nodeType === "input") return "#3b82f6";
              if (d?.nodeType === "output") return "#22c55e";
              return "#6366f1";
            }}
            className="bg-zinc-900/80! rounded-lg!"
          />
          <Controls className="bg-zinc-800! rounded-lg!" />

          {/* Toolbar */}
          <Panel position="top-right">
            <BuilderToolbar onSave={handleSave} templateId={templateId} />
          </Panel>

          {/* Validation Panel */}
          <Panel position="bottom-left">
            <ValidationPanel
              errors={validationErrors}
              isValid={isValid}
              isDirty={isDirty}
            />
          </Panel>
        </ReactFlow>
      </div>

      {/* Right: Properties Panel */}
      {selectedNodeId && <NodePropertiesPanel nodeId={selectedNodeId} />}
    </div>
  );
}

// ── Public exports ────────────────────────────────────────────────────────────

export function PipelineBuilder({ templateId }: { templateId: string }) {
  return (
    <ReactFlowProvider>
      <PipelineBuilderInner templateId={templateId} />
    </ReactFlowProvider>
  );
}
