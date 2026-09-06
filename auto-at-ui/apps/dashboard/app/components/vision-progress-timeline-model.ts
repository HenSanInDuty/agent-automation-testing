import type { VisionProgressActivity } from "../generation-types";

export type VisionProgressConnection = "connecting" | "live" | "polling";

const stages: Record<string, string> = {
  queued: "Exploration queued",
  started: "Starting advisory exploration",
  "state.captured": "Capturing a permitted page state",
  "candidate.requested": "Requesting advisory candidates",
  "candidate.received": "Advisory candidates received",
  "action.recorded": "Candidate action recorded",
  "limit.reached": "Configured exploration limit reached",
  "draft.handoff": "Preparing generated-draft handoff",
  completed: "Advisory exploration completed",
  unavailable: "Advisory exploration unavailable",
};

export function orderedVisionProgress(items: VisionProgressActivity[]): VisionProgressActivity[] {
  const unique = new Map(items.map((item) => [item.id, item]));
  return [...unique.values()].sort(
    (left, right) => left.occurred_at.localeCompare(right.occurred_at) || left.id.localeCompare(right.id),
  );
}

export function parseVisionProgress(value: unknown): VisionProgressActivity | null {
  if (!value || typeof value !== "object") return null;
  const item = value as Record<string, unknown>;
  if (
    typeof item.id !== "string" || typeof item.stage !== "string" ||
    typeof item.status !== "string" || typeof item.safe_summary !== "string" ||
    typeof item.occurred_at !== "string" || item.source !== "vision" ||
    !item.metadata || typeof item.metadata !== "object" || Array.isArray(item.metadata)
  ) return null;
  return {
    id: item.id, run_id: typeof item.run_id === "string" ? item.run_id : null,
    correlation_id: typeof item.correlation_id === "string" ? item.correlation_id : "",
    source: "vision", stage: item.stage, status: item.status, safe_summary: item.safe_summary,
    metadata: item.metadata as Record<string, string | number | boolean>, occurred_at: item.occurred_at,
  };
}

export function visionProgressLabel(stage: string): string {
  return stages[stage] ?? "Advisory progress updated";
}

export function visionConnectionLabel(connection: VisionProgressConnection): string {
  if (connection === "live") return "Live updates connected";
  if (connection === "polling") return "Reconnecting - polling fallback active";
  return "Connecting to live updates";
}
