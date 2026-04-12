"use client";

import { useState } from "react";
import {
  Search,
  Plus,
  GripVertical,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import { useAgentConfigsGrouped } from "@/hooks/useAgentConfigs";

interface CatalogItem {
  agentId: string;
  label: string;
  nodeType: string;
  description: string;
  stage: string;
}

export function AgentCatalogSidebar() {
  const [search, setSearch] = useState("");
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(
    new Set(["special"]),
  );
  const { data: groupedAgents } = useAgentConfigsGrouped();

  // Special nodes (always available)
  const specialItems: CatalogItem[] = [
    {
      agentId: "__input__",
      label: "📥 Input",
      nodeType: "input",
      description: "Pipeline entry point",
      stage: "special",
    },
    {
      agentId: "__output__",
      label: "📤 Output",
      nodeType: "output",
      description: "Pipeline final output",
      stage: "special",
    },
  ];

  // Flatten all agents from dynamic stage groups
  const allAgents = groupedAgents
    ? groupedAgents.groups.flatMap((g) => g.agents)
    : [];

  // Agent items grouped by stage
  const agentItems: CatalogItem[] = allAgents.map((a) => ({
    agentId: a.agent_id,
    label: a.display_name,
    nodeType: a.stage === "ingestion" ? "pure_python" : "agent",
    description: a.display_name,
    stage: a.stage,
  }));

  // Build groups object
  const groups: Record<string, CatalogItem[]> = { special: specialItems };
  agentItems.forEach((item) => {
    if (!groups[item.stage]) groups[item.stage] = [];
    groups[item.stage].push(item);
  });

  // Filter by search
  const filteredGroups = Object.entries(groups).reduce(
    (acc, [stage, items]) => {
      const filtered = items.filter(
        (item) =>
          item.label.toLowerCase().includes(search.toLowerCase()) ||
          item.description.toLowerCase().includes(search.toLowerCase()),
      );
      if (filtered.length > 0) acc[stage] = filtered;
      return acc;
    },
    {} as Record<string, CatalogItem[]>,
  );

  const toggleGroup = (group: string) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(group)) next.delete(group);
      else next.add(group);
      return next;
    });
  };

  const onDragStart = (event: React.DragEvent, item: CatalogItem) => {
    event.dataTransfer.setData("application/reactflow", JSON.stringify(item));
    event.dataTransfer.effectAllowed = "move";
  };

  // Build stage label map from dynamic groups returned by the API
  const stageLabelMap: Record<string, string> = {
    special: "⚡ Special",
    ...Object.fromEntries(
      (groupedAgents?.groups ?? []).map((g) => [g.stage_id, g.display_name]),
    ),
  };

  return (
    <div className="w-64 border-r border-zinc-700 bg-zinc-900 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="p-3 border-b border-zinc-700">
        <h3 className="font-semibold text-sm text-zinc-300 mb-2">
          Agent Catalog
        </h3>
        <div className="relative">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-zinc-500" />
          <input
            type="text"
            placeholder="Search agents..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-8 pr-3 py-1.5 text-xs bg-zinc-800 border border-zinc-600 rounded-md text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-blue-500"
          />
        </div>
      </div>

      {/* Agent Groups */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {Object.entries(filteredGroups).map(([stage, items]) => (
          <div key={stage}>
            <button
              onClick={() => toggleGroup(stage)}
              className="w-full flex items-center gap-1 px-2 py-1.5 text-xs font-medium text-zinc-400 hover:text-zinc-200 transition-colors"
            >
              {expandedGroups.has(stage) ? (
                <ChevronDown className="h-3 w-3" />
              ) : (
                <ChevronRight className="h-3 w-3" />
              )}
              {stageLabelMap[stage] ||
                stage.charAt(0).toUpperCase() + stage.slice(1)}
              <span className="ml-auto text-zinc-600">{items.length}</span>
            </button>

            {expandedGroups.has(stage) && (
              <div className="space-y-0.5 ml-2">
                {items.map((item) => (
                  <div
                    key={item.agentId}
                    draggable
                    onDragStart={(e) => onDragStart(e, item)}
                    className="flex items-center gap-2 px-2 py-1.5 rounded-md
                                                   cursor-grab active:cursor-grabbing
                                                   hover:bg-zinc-800 transition-colors
                                                   border border-transparent hover:border-zinc-600"
                  >
                    <GripVertical className="h-3 w-3 text-zinc-600 shrink-0" />
                    <div className="min-w-0">
                      <div className="text-xs font-medium text-zinc-200 truncate">
                        {item.label}
                      </div>
                      <div className="text-[10px] text-zinc-500 truncate">
                        {item.nodeType === "pure_python"
                          ? "🐍 Pure Python"
                          : item.nodeType === "input"
                            ? "Entry point"
                            : item.nodeType === "output"
                              ? "Exit point"
                              : "🤖 Agent"}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
        {Object.keys(filteredGroups).length === 0 && (
          <p className="text-xs text-zinc-500 text-center py-4">
            No agents found
          </p>
        )}
      </div>

      {/* Footer */}
      <div className="p-2 border-t border-zinc-700">
        <button className="w-full flex items-center justify-center gap-1 px-3 py-1.5 text-xs bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded-md transition-colors">
          <Plus className="h-3 w-3" />
          New Agent
        </button>
      </div>
    </div>
  );
}
