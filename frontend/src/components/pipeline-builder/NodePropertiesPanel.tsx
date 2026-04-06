'use client';

import { useBuilderStore } from '@/store/builderStore';
import { useLLMProfiles } from '@/hooks/useLLMProfiles';
import { Trash2, Settings, Zap, Link2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { AgentNodeData } from '@/store/builderStore';

export function NodePropertiesPanel({ nodeId }: { nodeId: string }) {
    const nodes = useBuilderStore((s) => s.nodes);
    const updateNodeData = useBuilderStore((s) => s.updateNodeData);
    const removeNode = useBuilderStore((s) => s.removeNode);
    const edges = useBuilderStore((s) => s.edges);

    const node = nodes.find((n) => n.id === nodeId);
    if (!node) return null;

    const typedData = node.data as AgentNodeData;
    const { data: llmProfilesData } = useLLMProfiles();
    const llmProfiles = llmProfilesData?.items ?? [];

    const incomingEdges = edges.filter((e) => e.target === nodeId);
    const outgoingEdges = edges.filter((e) => e.source === nodeId);
    const inputSources = incomingEdges.map((e) => {
        const sourceNode = nodes.find((n) => n.id === e.source);
        return (sourceNode?.data as AgentNodeData)?.label || e.source;
    });

    const isSpecial = typedData.nodeType === 'input' || typedData.nodeType === 'output';

    return (
        <div className="w-80 border-l border-zinc-700 bg-zinc-900 overflow-y-auto flex flex-col">
            {/* Header */}
            <div className="p-4 border-b border-zinc-700 flex items-center justify-between shrink-0">
                <div className="flex items-center gap-2">
                    <Settings className="h-4 w-4 text-zinc-400" />
                    <h3 className="font-semibold text-sm text-zinc-200">Properties</h3>
                </div>
                {!isSpecial && (
                    <button
                        onClick={() => removeNode(nodeId)}
                        title="Delete node"
                        className="p-1.5 text-red-400 hover:bg-red-400/10 rounded transition-colors"
                    >
                        <Trash2 className="h-4 w-4" />
                    </button>
                )}
            </div>

            <div className="p-4 space-y-4 flex-1">
                {/* Node type badge */}
                <div className="flex items-center gap-2">
                    <span className="text-2xl">
                        {typedData.nodeType === 'input' ? '📥'
                            : typedData.nodeType === 'output' ? '📤'
                            : typedData.nodeType === 'pure_python' ? '🐍'
                            : '🤖'}
                    </span>
                    <div>
                        <div className="text-xs text-zinc-500 uppercase tracking-wider">
                            {typedData.nodeType}
                        </div>
                        <div className="text-sm font-medium text-zinc-200 truncate max-w-[180px]">
                            {typedData.label}
                        </div>
                    </div>
                </div>

                {/* Label */}
                <section className="space-y-1.5">
                    <label className="text-xs font-medium text-zinc-400">Label</label>
                    <input
                        type="text"
                        value={typedData.label || ''}
                        onChange={(e) => updateNodeData(nodeId, { label: e.target.value })}
                        className="w-full px-3 py-1.5 text-sm bg-zinc-800 border border-zinc-600 rounded-md text-zinc-200 focus:outline-none focus:border-blue-500"
                    />
                </section>

                {/* Description */}
                <section className="space-y-1.5">
                    <label className="text-xs font-medium text-zinc-400">Description</label>
                    <textarea
                        value={typedData.description || ''}
                        onChange={(e) => updateNodeData(nodeId, { description: e.target.value })}
                        rows={2}
                        className="w-full px-3 py-1.5 text-sm bg-zinc-800 border border-zinc-600 rounded-md text-zinc-200 resize-none focus:outline-none focus:border-blue-500"
                    />
                </section>

                {/* Input Sources (read-only) */}
                {typedData.nodeType !== 'input' && (
                    <section className="space-y-1.5">
                        <label className="text-xs font-medium text-zinc-400 flex items-center gap-1">
                            <Zap className="h-3 w-3" />
                            Input From
                        </label>
                        {inputSources.length > 0 ? (
                            <div className="space-y-1">
                                {inputSources.map((src, i) => (
                                    <div
                                        key={i}
                                        className="px-2 py-1 text-xs bg-zinc-800 rounded border border-zinc-700 text-zinc-300"
                                    >
                                        ← {src}
                                    </div>
                                ))}
                            </div>
                        ) : (
                            <p className="text-xs text-zinc-500 italic">No inputs connected</p>
                        )}
                    </section>
                )}

                {/* Agent-specific config */}
                {(typedData.nodeType === 'agent' || typedData.nodeType === 'pure_python') && (
                    <>
                        {/* Agent ID (read-only) */}
                        <section className="space-y-1.5">
                            <label className="text-xs font-medium text-zinc-400">Agent ID</label>
                            <div className="px-3 py-1.5 text-sm bg-zinc-800/50 border border-zinc-700 rounded-md text-zinc-400 font-mono">
                                {typedData.agentId}
                            </div>
                        </section>

                        {/* LLM Override */}
                        <section className="space-y-1.5">
                            <label className="text-xs font-medium text-zinc-400">LLM Override</label>
                            <select
                                value={(typedData.configOverrides?.llm_profile_id as string) || ''}
                                onChange={(e) =>
                                    updateNodeData(nodeId, {
                                        configOverrides: {
                                            ...(typedData.configOverrides || {}),
                                            llm_profile_id: e.target.value || undefined,
                                        },
                                    })
                                }
                                className="w-full px-3 py-1.5 text-sm bg-zinc-800 border border-zinc-600 rounded-md text-zinc-200 focus:outline-none focus:border-blue-500"
                            >
                                <option value="">Use default</option>
                                {llmProfiles.map((p) => (
                                    <option key={p.id} value={String(p.id)}>
                                        {p.name} ({p.provider}/{p.model})
                                    </option>
                                ))}
                            </select>
                        </section>

                        {/* Timeout */}
                        <section className="space-y-1.5">
                            <label className="text-xs font-medium text-zinc-400">Timeout (seconds)</label>
                            <input
                                type="number"
                                value={typedData.timeout_seconds ?? 300}
                                onChange={(e) =>
                                    updateNodeData(nodeId, {
                                        timeout_seconds: parseInt(e.target.value) || 300,
                                    })
                                }
                                min={10}
                                max={7200}
                                className="w-full px-3 py-1.5 text-sm bg-zinc-800 border border-zinc-600 rounded-md text-zinc-200 focus:outline-none focus:border-blue-500"
                            />
                        </section>

                        {/* Enabled toggle */}
                        <section className="flex items-center justify-between py-1">
                            <label className="text-xs font-medium text-zinc-400">Enabled</label>
                            <button
                                onClick={() => updateNodeData(nodeId, { enabled: !typedData.enabled })}
                                className={cn(
                                    'relative w-10 h-5 rounded-full transition-colors',
                                    typedData.enabled ? 'bg-blue-600' : 'bg-zinc-700',
                                )}
                            >
                                <span
                                    className={cn(
                                        'absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform',
                                        typedData.enabled ? 'translate-x-5' : 'translate-x-0',
                                    )}
                                />
                            </button>
                        </section>
                    </>
                )}

                {/* Connection summary */}
                <section className="pt-2 border-t border-zinc-700 space-y-1">
                    <div className="flex items-center gap-1 text-xs text-zinc-500">
                        <Link2 className="h-3 w-3" />
                        {incomingEdges.length} incoming · {outgoingEdges.length} outgoing
                    </div>
                    <div className="text-xs text-zinc-600 font-mono">
                        {node.id}
                    </div>
                </section>
            </div>
        </div>
    );
}
