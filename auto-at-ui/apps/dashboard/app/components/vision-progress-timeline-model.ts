import type { VisionProgressActivity } from "../generation-types";

export type VisionProgressConnection = "connecting" | "live" | "polling" | "complete";

const stages: Record<string, string> = {
  queued: "Exploration queued",
  started: "Starting advisory exploration",
  "state.captured": "Capturing a permitted page state",
  "candidate.requested": "Requesting advisory candidates",
  "candidate.received": "Advisory candidates received",
  "action.recorded": "Candidate action recorded",
  "edge.proposed": "Candidate branch proposed",
  "edge.observed": "Candidate branch observed",
  "edge.failed": "Candidate branch unavailable",
  "edge.terminal": "Candidate branch terminal",
  "limit.reached": "Configured exploration limit reached",
  "draft.handoff": "Preparing generated-draft handoff",
  "operation.prepared": "Before frame saved",
  "operation.executing": "Performing browser action",
  "operation.completed": "Browser operation recorded",
  "operation.failed": "Browser operation failed",
  "operation.rejected": "Browser action rejected",
  "operation.unknown": "Browser action outcome unknown",
  "locator.verified": "Locator verified",
  "locator.unresolved": "Locator unresolved",
  "state.restore_started": "Returning to the previous state",
  "state.restored": "Previous state verified",
  "state.restore_failed": "Could not restore the previous state",
  "handoff.ready": "Evidence ready for draft generation",
  "handoff.unavailable": "Insufficient evidence for draft generation",
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
  if (connection === "complete") return "Saved progress";
  if (connection === "live") return "Live updates connected";
  if (connection === "polling") return "Reconnecting - polling fallback active";
  return "Connecting to live updates";
}
