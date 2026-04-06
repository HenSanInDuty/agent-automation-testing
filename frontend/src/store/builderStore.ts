import { create } from 'zustand';
import {
    type Node,
    type Edge,
    type OnNodesChange,
    type OnEdgesChange,
    type OnConnect,
    applyNodeChanges,
    applyEdgeChanges,
    addEdge,
} from '@xyflow/react';

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

export interface AgentNodeData {
    label: string;
    agentId: string;
    nodeType: 'agent' | 'pure_python' | 'input' | 'output';
    status?: 'idle' | 'running' | 'completed' | 'failed';
    enabled: boolean;
    description?: string;
    timeout_seconds?: number;
    configOverrides?: Record<string, unknown>;
    [key: string]: unknown; // Required for @xyflow/react Node data
}

interface HistoryEntry {
    nodes: Node[];
    edges: Edge[];
}

interface BuilderState {
    // Template metadata
    templateId: string | null;
    templateName: string;
    templateDescription: string;

    // React Flow state
    nodes: Node[];
    edges: Edge[];

    // Selection
    selectedNodeId: string | null;

    // Dirty state
    isDirty: boolean;
    isSaving: boolean;

    // Validation
    validationErrors: string[];
    isValid: boolean;

    // Undo/Redo
    history: HistoryEntry[];
    historyIndex: number;

    // Actions
    onNodesChange: OnNodesChange;
    onEdgesChange: OnEdgesChange;
    onConnect: OnConnect;

    setTemplate: (
        templateId: string,
        name: string,
        description: string,
        nodes: Node[],
        edges: Edge[],
    ) => void;
    addNode: (node: Node) => void;
    removeNode: (nodeId: string) => void;
    updateNodeData: (nodeId: string, data: Partial<AgentNodeData>) => void;
    selectNode: (nodeId: string | null) => void;

    validate: () => string[];
    saveTemplate: () => Promise<void>;

    undo: () => void;
    redo: () => void;
    pushHistory: () => void;

    resetBuilder: () => void;
}

// ─────────────────────────────────────────────────────────────────────────────
// Cycle detection utility (DFS)
// ─────────────────────────────────────────────────────────────────────────────

function detectCycle(nodes: Node[], edges: Edge[]): boolean {
    // Build adjacency list
    const adj: Record<string, string[]> = {};
    for (const node of nodes) {
        adj[node.id] = [];
    }
    for (const edge of edges) {
        if (adj[edge.source]) {
            adj[edge.source].push(edge.target);
        }
    }

    // DFS with three-color marking: 0 = unvisited, 1 = in-stack, 2 = done
    const color: Record<string, number> = {};
    for (const node of nodes) {
        color[node.id] = 0;
    }

    function dfs(nodeId: string): boolean {
        color[nodeId] = 1; // mark as in-stack
        for (const neighbor of (adj[nodeId] ?? [])) {
            if (color[neighbor] === 1) return true;  // back edge → cycle
            if (color[neighbor] === 0 && dfs(neighbor)) return true;
        }
        color[nodeId] = 2; // mark as done
        return false;
    }

    for (const node of nodes) {
        if (color[node.id] === 0) {
            if (dfs(node.id)) return true;
        }
    }

    return false;
}

// ─────────────────────────────────────────────────────────────────────────────
// Initial / blank state
// ─────────────────────────────────────────────────────────────────────────────

const BLANK_STATE = {
    templateId: null as string | null,
    templateName: '',
    templateDescription: '',
    nodes: [] as Node[],
    edges: [] as Edge[],
    selectedNodeId: null as string | null,
    isDirty: false,
    isSaving: false,
    validationErrors: [] as string[],
    isValid: false,
    history: [] as HistoryEntry[],
    historyIndex: -1,
};

// ─────────────────────────────────────────────────────────────────────────────
// Store
// ─────────────────────────────────────────────────────────────────────────────

export const useBuilderStore = create<BuilderState>()((set, get) => ({
    // ── Initial state ──────────────────────────────────────────────────────────
    ...BLANK_STATE,

    // ── React Flow event handlers ──────────────────────────────────────────────

    onNodesChange: (changes) => {
        set((s) => ({
            nodes: applyNodeChanges(changes, s.nodes),
        }));
    },

    onEdgesChange: (changes) => {
        set((s) => ({
            edges: applyEdgeChanges(changes, s.edges),
        }));
    },

    onConnect: (connection) => {
        const newEdge: Edge = {
            ...connection,
            id: `edge-${connection.source}-${connection.target}`,
            type: 'smoothstep',
            animated: false,
            source: connection.source ?? '',
            target: connection.target ?? '',
        };
        set((s) => ({
            edges: addEdge(newEdge, s.edges),
            isDirty: true,
        }));
        // Auto-validate after connection
        get().validate();
    },

    // ── Template ───────────────────────────────────────────────────────────────

    setTemplate: (templateId, name, description, nodes, edges) => {
        const initialEntry: HistoryEntry = {
            nodes: JSON.parse(JSON.stringify(nodes)),
            edges: JSON.parse(JSON.stringify(edges)),
        };
        set({
            templateId,
            templateName: name,
            templateDescription: description,
            nodes,
            edges,
            isDirty: false,
            selectedNodeId: null,
            history: [initialEntry],
            historyIndex: 0,
        });
        get().validate();
    },

    // ── Node management ────────────────────────────────────────────────────────

    addNode: (node) => {
        get().pushHistory();
        set((s) => ({
            nodes: [...s.nodes, node],
            isDirty: true,
        }));
    },

    removeNode: (nodeId) => {
        get().pushHistory();
        set((s) => {
            const nodes = s.nodes.filter((n) => n.id !== nodeId);
            const edges = s.edges.filter(
                (e) => e.source !== nodeId && e.target !== nodeId,
            );
            const selectedNodeId =
                s.selectedNodeId === nodeId ? null : s.selectedNodeId;
            return { nodes, edges, selectedNodeId, isDirty: true };
        });
        get().validate();
    },

    updateNodeData: (nodeId, data) => {
        set((s) => ({
            nodes: s.nodes.map((n) => {
                if (n.id !== nodeId) return n;
                return {
                    ...n,
                    data: { ...n.data, ...data },
                };
            }),
            isDirty: true,
        }));
    },

    selectNode: (nodeId) => {
        set({ selectedNodeId: nodeId });
    },

    // ── Validation ─────────────────────────────────────────────────────────────

    validate: () => {
        const { nodes, edges } = get();
        const errors: string[] = [];

        // (1) Exactly 1 INPUT node
        const inputNodes = nodes.filter(
            (n) => (n.data as AgentNodeData).nodeType === 'input',
        );
        if (inputNodes.length === 0) {
            errors.push('Pipeline must have exactly one Input node.');
        } else if (inputNodes.length > 1) {
            errors.push(
                `Pipeline has ${inputNodes.length} Input nodes; only one is allowed.`,
            );
        }

        // (2) Exactly 1 OUTPUT node
        const outputNodes = nodes.filter(
            (n) => (n.data as AgentNodeData).nodeType === 'output',
        );
        if (outputNodes.length === 0) {
            errors.push('Pipeline must have exactly one Output node.');
        } else if (outputNodes.length > 1) {
            errors.push(
                `Pipeline has ${outputNodes.length} Output nodes; only one is allowed.`,
            );
        }

        // (3) No cycles
        if (detectCycle(nodes, edges)) {
            errors.push('Pipeline contains a cycle, which is not allowed.');
        }

        // (4) No orphan agent nodes (agents with no edges)
        const agentNodes = nodes.filter((n) => {
            const nodeType = (n.data as AgentNodeData).nodeType;
            return nodeType === 'agent' || nodeType === 'pure_python';
        });
        for (const agentNode of agentNodes) {
            const hasEdge = edges.some(
                (e) => e.source === agentNode.id || e.target === agentNode.id,
            );
            if (!hasEdge) {
                const label = (agentNode.data as AgentNodeData).label || agentNode.id;
                errors.push(`Agent node "${label}" is not connected to anything.`);
            }
        }

        set({ validationErrors: errors, isValid: errors.length === 0 });
        return errors;
    },

    // ── Save (placeholder) ─────────────────────────────────────────────────────

    saveTemplate: async () => {
        // Placeholder — no-op
    },

    // ── History ────────────────────────────────────────────────────────────────

    pushHistory: () => {
        const { nodes, edges, history, historyIndex } = get();
        // Slice off any redo entries beyond current index
        const trimmed = history.slice(0, historyIndex + 1);
        const entry: HistoryEntry = {
            nodes: JSON.parse(JSON.stringify(nodes)),
            edges: JSON.parse(JSON.stringify(edges)),
        };
        set({
            history: [...trimmed, entry],
            historyIndex: trimmed.length,
        });
    },

    undo: () => {
        const { history, historyIndex } = get();
        if (historyIndex <= 0) return;
        const prevIndex = historyIndex - 1;
        const entry = history[prevIndex];
        set({
            nodes: JSON.parse(JSON.stringify(entry.nodes)),
            edges: JSON.parse(JSON.stringify(entry.edges)),
            historyIndex: prevIndex,
            isDirty: true,
        });
    },

    redo: () => {
        const { history, historyIndex } = get();
        if (historyIndex >= history.length - 1) return;
        const nextIndex = historyIndex + 1;
        const entry = history[nextIndex];
        set({
            nodes: JSON.parse(JSON.stringify(entry.nodes)),
            edges: JSON.parse(JSON.stringify(entry.edges)),
            historyIndex: nextIndex,
            isDirty: true,
        });
    },

    // ── Reset ──────────────────────────────────────────────────────────────────

    resetBuilder: () => {
        set({ ...BLANK_STATE });
    },
}));
