/**
 * Module-level singleton WebSocket manager.
 * Lives outside React — survives route changes.
 * Zustand store calls connect/disconnect; WS events flow back via callback.
 */

import type { WSEvent } from "@/types";

const WS_BASE_URL =
  typeof window !== "undefined"
    ? (process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000")
    : "ws://localhost:8000";

const MAX_RETRIES = 5;

class WSManager {
  private ws: WebSocket | null = null;
  private runId: string | null = null;
  private onEvent: ((event: WSEvent) => void) | null = null;
  private retryCount = 0;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private isTerminal = false;
  private onStatusChange:
    | ((status: "connecting" | "connected" | "disconnected" | "error") => void)
    | null = null;

  connect(
    runId: string,
    onEvent: (event: WSEvent) => void,
    onStatusChange?: (
      status: "connecting" | "connected" | "disconnected" | "error",
    ) => void,
  ) {
    this.disconnect(); // clean up previous
    this.runId = runId;
    this.onEvent = onEvent;
    this.onStatusChange = onStatusChange ?? null;
    this.retryCount = 0;
    this.isTerminal = false;
    this._open();
  }

  disconnect() {
    if (this.retryTimer) {
      clearTimeout(this.retryTimer);
      this.retryTimer = null;
    }
    if (this.ws) {
      this.ws.onclose = null;
      this.ws.onerror = null;
      this.ws.onmessage = null;
      this.ws.onopen = null;
      this.ws.close();
      this.ws = null;
    }
    this.runId = null;
    this.onEvent = null;
    this.onStatusChange = null;
  }

  private _open() {
    if (!this.runId) return;
    if (typeof window === "undefined") return; // SSR guard

    this.onStatusChange?.("connecting");

    const ws = new WebSocket(`${WS_BASE_URL}/ws/pipeline/${this.runId}`);

    ws.onopen = () => {
      this.retryCount = 0;
      this.onStatusChange?.("connected");
    };

    ws.onerror = () => {
      this.onStatusChange?.("error");
    };

    ws.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data as string) as WSEvent;
        this.onEvent?.(event);

        if (
          event.event === "run.completed" ||
          event.event === "run.failed" ||
          event.event === "run.cancelled"
        ) {
          this.isTerminal = true;
          ws.onclose = null;
          ws.close();
          this.ws = null;
          this.onStatusChange?.("disconnected");
        }
      } catch {
        /* ignore unparseable frames */
      }
    };

    ws.onclose = () => {
      this.ws = null;
      if (this.isTerminal) return;
      if (this.retryCount < MAX_RETRIES) {
        const delay = 1000 * 2 ** this.retryCount;
        this.retryCount++;
        this.onStatusChange?.("connecting");
        this.retryTimer = setTimeout(() => {
          this.retryTimer = null;
          this._open();
        }, delay);
      } else {
        this.onStatusChange?.("disconnected");
      }
    };

    this.ws = ws;
  }
}

export const wsManager = new WSManager();
