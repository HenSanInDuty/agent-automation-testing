'use client';

import { useBuilderStore } from '@/store/builderStore';
import { useLLMProfiles } from '@/hooks/useLLMProfiles';
import { Trash2, Settings, Zap, Link2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { AgentNodeData } from '@/store/builderStore';

// ─────────────────────────────────────────────────────────────────────────────
// AdaptivePlannerConfig — bounded config fields for the adaptive_api_test_planner
// node. Only rendered when agentId === "adaptive_api_test_planner".
// Admin-editable template defaults; validated in the UI before saving.
// ─────────────────────────────────────────────────────────────────────────────

interface AdaptivePlannerConfigProps {
    overrides: Record<string, unknown>;
    onChange: (patch: Record<string, unknown>) => void;
}

function clamp(value: number, min: number, max: number): number {
    return Math.max(min, Math.min(max, value));
}

function AdaptivePlannerConfig({ overrides, onChange }: AdaptivePlannerConfigProps) {
    const minAgents = Number(overrides.min_planner_agents ?? 1);
    const maxAgents = Number(overrides.max_planner_agents ?? 5);
    const threshold = Number(overrides.coverage_threshold_percent ?? 90);
    const maxIter = Number(overrides.max_review_iterations ?? 3);
    const continueOnExhaustion = Boolean(overrides.continue_on_exhaustion ?? true);

    const inputCls = 'w-full px-3 py-1.5 text-sm bg-zinc-800 border border-zinc-600 rounded-md text-zinc-200 focus:outline-none focus:border-blue-500';
    const labelCls = 'text-xs font-medium text-zinc-400';
    const hintCls = 'text-[10px] text-zinc-600 mt-0.5';

    return (
        <section className="space-y-3 pt-3 border-t border-zinc-700">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-blue-400">
                Adaptive Planner Config
            </p>

            {/* min_planner_agents */}
            <div className="space-y-1">
                <label className={labelCls}>Min Planner Agents (1–5)</label>
                <input
                    type="number"
                    value={minAgents}
                    min={1}
                    max={5}
                    onChange={(e) => {
                        const v = clamp(parseInt(e.target.value) || 1, 1, 5);
                        onChange({ min_planner_agents: v, max_planner_agents: Math.max(v, maxAgents) });
                    }}
                    className={inputCls}
                />
                <p className={hintCls}>Minimum agents selected regardless of complexity score.</p>
            </div>

            {/* max_planner_agents */}
            <div className="space-y-1">
                <label className={labelCls}>Max Planner Agents (1–5)</label>
                <input
                    type="number"
                    value={maxAgents}
                    min={1}
                    max={5}
                    onChange={(e) => {
                        const v = clamp(parseInt(e.target.value) || 5, 1, 5);
                        onChange({ max_planner_agents: v, min_planner_agents: Math.min(v, minAgents) });
                    }}
                    className={inputCls}
                />
                {maxAgents < minAgents && (
                    <p className="text-[10px] text-red-400 mt-0.5">Must be ≥ min agents ({minAgents}).</p>
                )}
            </div>

            {/* coverage_threshold_percent */}
            <div className="space-y-1">
                <label className={labelCls}>Coverage Threshold % (0–100)</label>
                <input
                    type="number"
                    value={threshold}
                    min={0}
                    max={100}
                    onChange={(e) => {
                        const v = clamp(parseInt(e.target.value) || 0, 0, 100);
                        onChange({ coverage_threshold_percent: v });
                    }}
                    className={inputCls}
                />
                <p className={hintCls}>Senior reviewer approves when coverage_percent ≥ this value.</p>
            </div>

            {/* max_review_iterations */}
            <div className="space-y-1">
                <label className={labelCls}>Max Review Iterations (0–5)</label>
                <input
                    type="number"
                    value={maxIter}
                    min={0}
                    max={5}
                    onChange={(e) => {
                        const v = clamp(parseInt(e.target.value) || 0, 0, 5);
                        onChange({ max_review_iterations: v });
                    }}
                    className={inputCls}
                />
                <p className={hintCls}>Maximum refinement loops before the gate is exhausted.</p>
            </div>

            {/* continue_on_exhaustion */}
            <div className="flex items-center justify-between py-1">
                <div>
                    <label className={labelCls}>Continue on Exhaustion</label>
                    <p className={hintCls}>Accept best available result when gate exhausts.</p>
                </div>
                <button
                    type="button"
                    onClick={() => onChange({ continue_on_exhaustion: !continueOnExhaustion })}
                    className={cn(
                        'relative w-10 h-5 rounded-full transition-colors shrink-0',
                        continueOnExhaustion ? 'bg-blue-600' : 'bg-zinc-700',
                    )}
                    aria-pressed={continueOnExhaustion}
                    title={continueOnExhaustion ? 'Continue on exhaustion: ON' : 'Continue on exhaustion: OFF'}
                >
                    <span
                        className={cn(
                            'absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform',
                            continueOnExhaustion ? 'translate-x-5' : 'translate-x-0',
                        )}
                    />
                </button>
            </div>
        </section>
    );
}

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

                        {/* Task Instruction */}
                        <section className="space-y-1.5">
                            <label className="text-xs font-medium text-zinc-400">
                                Task Instruction
                                <span className="ml-1 text-zinc-600 font-normal">(leave blank to use agent&apos;s goal)</span>
                            </label>
                            <textarea
                                value={(typedData.configOverrides?.task_instruction as string) || ''}
                                onChange={(e) =>
                                    updateNodeData(nodeId, {
                                        configOverrides: {
                                            ...(typedData.configOverrides || {}),
                                            task_instruction: e.target.value || undefined,
                                        },
                                    })
                                }
                                rows={4}
                                placeholder="e.g. Extract all functional requirements from the document. Return a JSON list with id, description, priority, and acceptance criteria for each."
                                className="w-full px-3 py-1.5 text-sm bg-zinc-800 border border-zinc-600 rounded-md text-zinc-200 resize-none focus:outline-none focus:border-blue-500 placeholder:text-zinc-600"
                            />
                        </section>

                        {/* Expected Output */}
                        <section className="space-y-1.5">
                            <label className="text-xs font-medium text-zinc-400">
                                Expected Output
                                <span className="ml-1 text-zinc-600 font-normal">(leave blank for default JSON)</span>
                            </label>
                            <textarea
                                value={(typedData.configOverrides?.expected_output as string) || ''}
                                onChange={(e) =>
                                    updateNodeData(nodeId, {
                                        configOverrides: {
                                            ...(typedData.configOverrides || {}),
                                            expected_output: e.target.value || undefined,
                                        },
                                    })
                                }
                                rows={3}
                                placeholder="e.g. A detailed HTML report with test results..."
                                className="w-full px-3 py-1.5 text-sm bg-zinc-800 border border-zinc-600 rounded-md text-zinc-200 resize-none focus:outline-none focus:border-blue-500 placeholder:text-zinc-600"
                            />
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

                        {/* ── Adaptive Test Planner config (bounded defaults) ── */}
                        {typedData.agentId === 'adaptive_api_test_planner' && (
                            <AdaptivePlannerConfig
                                overrides={typedData.configOverrides ?? {}}
                                onChange={(patch) =>
                                    updateNodeData(nodeId, {
                                        configOverrides: {
                                            ...(typedData.configOverrides ?? {}),
                                            ...patch,
                                        },
                                    })
                                }
                            />
                        )}

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
