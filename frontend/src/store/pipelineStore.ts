import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

import type { AgentRunStatus, PipelineStatus, WSEvent } from "@/types";
import { wsManager } from "@/lib/wsManager";

// ─────────────────────────────────────────────────────────────────────────────
// State shape
// ─────────────────────────────────────────────────────────────────────────────

interface PipelineSession {
  activeRunId: string | null;
  activeRunStatus: PipelineStatus | null;
  agentStatuses: Record<string, AgentRunStatus>;
  agentProgress: Record<string, { pct: number; message: string }>;
  currentStage: string | null;
  completedStages: string[];
  stageResults: Record<string, Record<string, unknown>>;
  stageSummaries: Record<string, Record<string, unknown>>;
  logMessages: string[];
  events: WSEvent[];
  isTerminal: boolean;
}

interface PipelineStoreState extends PipelineSession {
  // Actions
  startSession: (runId: string) => void;
  clearSession: () => void;
  updateFromWSEvent: (event: WSEvent) => void;
  setStageResult: (stage: string, data: Record<string, unknown>) => void;
  setStageSummary: (stage: string, summary: Record<string, unknown>) => void;
  clearStageResults: () => void;

  // WebSocket
  wsStatus: "disconnected" | "connecting" | "connected" | "error";
  connectWebSocket: (runId: string) => void;
  disconnectWebSocket: () => void;
}

// ─────────────────────────────────────────────────────────────────────────────
// Initial state factory
// ─────────────────────────────────────────────────────────────────────────────

const INITIAL_SESSION: PipelineSession = {
  activeRunId: null,
  activeRunStatus: null,
  agentStatuses: {},
  agentProgress: {},
  currentStage: null,
  completedStages: [],
  stageResults: {},
  stageSummaries: {},
  logMessages: [],
  events: [],
  isTerminal: false,
};

const MAX_EVENTS = 500;
const MAX_LOGS = 100;
const NOISE_EVENTS = new Set(["connected", "ping", "pong"]);

// ─────────────────────────────────────────────────────────────────────────────
// Store
// ─────────────────────────────────────────────────────────────────────────────

export const usePipelineStore = create<PipelineStoreState>()(
  persist(
    (set, get) => ({
      // ── Initial state ──────────────────────────────────────────────────────
      ...INITIAL_SESSION,
      wsStatus: "disconnected",

      // ── Session lifecycle ──────────────────────────────────────────────────
      startSession: (runId) => {
        set({
          ...INITIAL_SESSION,
          activeRunId: runId,
          activeRunStatus: "running",
        });
        get().connectWebSocket(runId);
      },

      clearSession: () => {
        get().disconnectWebSocket();
        set({ ...INITIAL_SESSION, wsStatus: "disconnected" });
      },

      // ── WS event handler ───────────────────────────────────────────────────
      updateFromWSEvent: (event) => {
        // Append to event list (skip noise)
        if (!NOISE_EVENTS.has(event.event)) {
          set((s) => {
            const next = [...s.events, event];
            return {
              events: next.length > MAX_EVENTS ? next.slice(-MAX_EVENTS) : next,
            };
          });
        }

        switch (event.event) {
          case "agent.started":
            set((s) => ({
              agentStatuses: {
                ...s.agentStatuses,
                [event.data.agent_id as string]: "running" as AgentRunStatus,
              },
            }));
            break;

          case "agent.progress":
            set((s) => ({
              agentProgress: {
                ...s.agentProgress,
                [event.data.agent_id as string]: {
                  pct: (event.data.progress as number) ?? 0,
                  message: (event.data.message as string) ?? "",
                },
              },
            }));
            break;

          case "agent.completed": {
            const agentId = event.data.agent_id as string;
            set((s) => {
              const next = { ...s.agentProgress };
              delete next[agentId];
              return {
                agentStatuses: {
                  ...s.agentStatuses,
                  [agentId]: "completed" as AgentRunStatus,
                },
                agentProgress: next,
              };
            });
            break;
          }

          case "agent.failed": {
            const agentId = event.data.agent_id as string;
            set((s) => {
              const next = { ...s.agentProgress };
              delete next[agentId];
              return {
                agentStatuses: {
                  ...s.agentStatuses,
                  [agentId]: "failed" as AgentRunStatus,
                },
                agentProgress: next,
              };
            });
            break;
          }

          case "stage.started":
            set({ currentStage: event.data.stage as string });
            break;

          case "stage.completed": {
            const stage = event.data.stage as string;
            const summary = event.data.summary as
              | Record<string, unknown>
              | undefined;
            set((s) => ({
              completedStages: s.completedStages.includes(stage)
                ? s.completedStages
                : [...s.completedStages, stage],
              stageSummaries: summary
                ? { ...s.stageSummaries, [stage]: summary }
                : s.stageSummaries,
            }));
            break;
          }

          case "log": {
            const msg = event.data.message as string;
            if (msg) {
              set((s) => {
                const next = [...s.logMessages, msg];
                return {
                  logMessages:
                    next.length > MAX_LOGS ? next.slice(-MAX_LOGS) : next,
                };
              });
            }
            break;
          }

          case "run.completed":
            set({
              activeRunStatus: "completed",
              isTerminal: true,
            });
            break;

          case "run.failed":
            set({
              activeRunStatus: "failed",
              isTerminal: true,
            });
            break;

          case "run.paused":
            set({
              activeRunStatus: "paused",
              isTerminal: false,
            });
            break;

          case "run.resumed":
            set({
              activeRunStatus: "running",
              isTerminal: false,
            });
            break;

          case "run.cancelled":
            set({
              activeRunStatus: "cancelled",
              isTerminal: true,
            });
            break;

          default:
            break;
        }
      },

      // ── Stage results ──────────────────────────────────────────────────────
      setStageResult: (stage, data) => {
        set((s) => ({
          stageResults: { ...s.stageResults, [stage]: data },
        }));
      },

      setStageSummary: (stage, summary) => {
        set((s) => ({
          stageSummaries: { ...s.stageSummaries, [stage]: summary },
        }));
      },

      clearStageResults: () => {
        set({ stageResults: {}, stageSummaries: {} });
      },

      // ── WebSocket ──────────────────────────────────────────────────────────
      connectWebSocket: (runId) => {
        set({ wsStatus: "connecting" });
        wsManager.connect(
          runId,
          (event) => get().updateFromWSEvent(event),
          (status) => set({ wsStatus: status }),
        );
      },

      disconnectWebSocket: () => {
        wsManager.disconnect();
        set({ wsStatus: "disconnected" });
      },
    }),
    {
      name: "auto-at-pipeline-session",
      storage: createJSONStorage(() =>
        typeof window !== "undefined" ? sessionStorage : localStorage,
      ),
      // Only persist a lightweight subset — not events/logs (too large)
      partialize: (state) => ({
        activeRunId: state.activeRunId,
        activeRunStatus: state.activeRunStatus,
        agentStatuses: state.agentStatuses,
        currentStage: state.currentStage,
        completedStages: state.completedStages,
        isTerminal: state.isTerminal,
        stageSummaries: state.stageSummaries,
      }),
    },
  ),
);
