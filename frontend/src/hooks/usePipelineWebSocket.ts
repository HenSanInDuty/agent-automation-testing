import { useCallback, useEffect, useRef, useState } from "react";

import type { AgentRunStatus, WSEvent } from "@/types";

// ─────────────────────────────────────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────────────────────────────────────

const WS_BASE_URL = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000";

const MAX_EVENTS = 500;
const MAX_RETRIES = 3;

/** Events that carry no useful information for the UI — filter from event list */
const NOISE_EVENTS = new Set(["connected", "ping", "pong"]);

// ─────────────────────────────────────────────────────────────────────────────
// Public types
// ─────────────────────────────────────────────────────────────────────────────

export interface UsePipelineWebSocketOptions {
  runId: string | undefined;
  enabled?: boolean;
  onEvent?: (event: WSEvent) => void;
}

export interface UsePipelineWebSocketReturn {
  status: "connecting" | "connected" | "disconnected" | "error";
  events: WSEvent[];
  agentStatuses: Record<string, AgentRunStatus>;
  agentProgress: Record<string, { pct: number; message: string }>;
  currentStage: string | null;
  isTerminal: boolean;
  logMessages: string[];
  disconnect: () => void;
}

// ─────────────────────────────────────────────────────────────────────────────
// Hook
// ─────────────────────────────────────────────────────────────────────────────

export function usePipelineWebSocket(
  options: UsePipelineWebSocketOptions,
): UsePipelineWebSocketReturn {
  const { runId, enabled = true, onEvent } = options;

  // ── State ─────────────────────────────────────────────────────────────────
  const [status, setStatus] = useState<
    "connecting" | "connected" | "disconnected" | "error"
  >("disconnected");
  const [events, setEvents] = useState<WSEvent[]>([]);
  const [agentStatuses, setAgentStatuses] = useState<
    Record<string, AgentRunStatus>
  >({});
  const [agentProgress, setAgentProgress] = useState<
    Record<string, { pct: number; message: string }>
  >({});
  const [currentStage, setCurrentStage] = useState<string | null>(null);
  const [isTerminal, setIsTerminal] = useState(false);
  const [logMessages, setLogMessages] = useState<string[]>([]);

  // ── Refs ──────────────────────────────────────────────────────────────────
  const wsRef = useRef<WebSocket | null>(null);
  const retryCountRef = useRef(0);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Keep a ref to isTerminal so the reconnect closure always reads fresh value
  const isTerminalRef = useRef(false);
  // Keep a stable ref to onEvent so the effect doesn't re-run on every render
  const onEventRef = useRef(onEvent);
  useEffect(() => {
    onEventRef.current = onEvent;
  }, [onEvent]);

  // ── Disconnect helper ─────────────────────────────────────────────────────

  const disconnect = useCallback(() => {
    // Cancel any scheduled reconnect
    if (retryTimerRef.current !== null) {
      clearTimeout(retryTimerRef.current);
      retryTimerRef.current = null;
    }
    if (wsRef.current) {
      // Prevent the onclose handler from triggering a reconnect
      wsRef.current.onclose = null;
      wsRef.current.onerror = null;
      wsRef.current.onmessage = null;
      wsRef.current.onopen = null;
      wsRef.current.close();
      wsRef.current = null;
    }
    setStatus("disconnected");
  }, []);

  // ── Connect helper ────────────────────────────────────────────────────────

  const connect = useCallback(
    (id: string) => {
      // Guard: don't open a second socket if one already exists
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
        wsRef.current = null;
      }

      setStatus("connecting");

      const url = `${WS_BASE_URL}/ws/pipeline/${id}`;
      const ws = new WebSocket(url);
      wsRef.current = ws;

      // ── onopen ─────────────────────────────────────────────────────────
      ws.onopen = () => {
        retryCountRef.current = 0;
        setStatus("connected");
      };

      // ── onmessage ──────────────────────────────────────────────────────
      ws.onmessage = (messageEvent: MessageEvent) => {
        let parsed: WSEvent;
        try {
          parsed = JSON.parse(messageEvent.data as string) as WSEvent;
        } catch {
          // Ignore unparseable frames
          return;
        }

        // Only add meaningful events to the event list; skip noise
        if (!NOISE_EVENTS.has(parsed.event)) {
          setEvents((prev) => {
            const next = [...prev, parsed];
            return next.length > MAX_EVENTS ? next.slice(-MAX_EVENTS) : next;
          });
        }

        // Update derived state
        switch (parsed.event) {
          case "agent.started":
            setAgentStatuses((prev) => ({
              ...prev,
              [parsed.data.agent_id as string]: "running",
            }));
            break;

          case "agent.progress":
            setAgentProgress((prev) => ({
              ...prev,
              [parsed.data.agent_id as string]: {
                pct: (parsed.data.progress as number) ?? 0,
                message: (parsed.data.message as string) ?? "",
              },
            }));
            break;

          case "agent.completed":
            setAgentStatuses((prev) => ({
              ...prev,
              [parsed.data.agent_id as string]: "completed",
            }));
            // Clear progress entry once the agent finishes
            setAgentProgress((prev) => {
              const next = { ...prev };
              delete next[parsed.data.agent_id as string];
              return next;
            });
            break;

          case "agent.failed":
            setAgentStatuses((prev) => ({
              ...prev,
              [parsed.data.agent_id as string]: "failed",
            }));
            setAgentProgress((prev) => {
              const next = { ...prev };
              delete next[parsed.data.agent_id as string];
              return next;
            });
            break;

          case "stage.started":
            setCurrentStage(parsed.data.stage as string);
            break;

          case "log": {
            const msg = parsed.data.message as string;
            if (msg) {
              setLogMessages((prev) => {
                const next = [...prev, msg];
                return next.length > 100 ? next.slice(-100) : next;
              });
            }
            break;
          }

          case "run.completed":
          case "run.failed":
            isTerminalRef.current = true;
            setIsTerminal(true);
            // Close the socket gracefully — no more reconnects needed
            if (wsRef.current) {
              wsRef.current.onclose = null;
              wsRef.current.close();
              wsRef.current = null;
            }
            setStatus("disconnected");
            break;

          default:
            break;
        }

        // Fire optional consumer callback
        onEventRef.current?.(parsed);
      };

      // ── onerror ────────────────────────────────────────────────────────
      ws.onerror = () => {
        setStatus("error");
      };

      // ── onclose ────────────────────────────────────────────────────────
      ws.onclose = () => {
        wsRef.current = null;

        // If the run reached a terminal state, do not reconnect
        if (isTerminalRef.current) {
          setStatus("disconnected");
          return;
        }

        if (retryCountRef.current < MAX_RETRIES) {
          // Exponential backoff: 1 s, 2 s, 4 s
          const delay = 1000 * 2 ** retryCountRef.current;
          retryCountRef.current += 1;
          setStatus("connecting");

          retryTimerRef.current = setTimeout(() => {
            retryTimerRef.current = null;
            connect(id);
          }, delay);
        } else {
          setStatus("disconnected");
        }
      };
    },
    // `connect` is only stable within the effect scope below — we do NOT list
    // `connect` itself to avoid infinite loops; the effect manages lifecycle.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  // ── Effect: manage connection lifecycle ───────────────────────────────────

  useEffect(() => {
    if (!runId || !enabled) {
      // Clean up any existing connection when prerequisites are gone
      disconnect();
      return;
    }

    // Reset state for a new run
    retryCountRef.current = 0;
    isTerminalRef.current = false;
    setIsTerminal(false);
    setEvents([]);
    setAgentStatuses({});
    setAgentProgress({});
    setCurrentStage(null);
    setLogMessages([]);

    connect(runId);

    return () => {
      // Cancel retry timers and close socket on unmount / dep change
      if (retryTimerRef.current !== null) {
        clearTimeout(retryTimerRef.current);
        retryTimerRef.current = null;
      }
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.onerror = null;
        wsRef.current.onmessage = null;
        wsRef.current.onopen = null;
        wsRef.current.close();
        wsRef.current = null;
      }
    };
    // Re-run only when the run ID or enabled flag changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId, enabled]);

  return {
    status,
    events,
    agentStatuses,
    agentProgress,
    currentStage,
    isTerminal,
    logMessages,
    disconnect,
  };
}
