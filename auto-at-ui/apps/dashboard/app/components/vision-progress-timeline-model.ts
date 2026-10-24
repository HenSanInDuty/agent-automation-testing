import type { VisionProgressActivity, VisualOperation } from "../generation-types";

export function isVisionModelPending(progress: VisionProgressActivity | null | undefined, operation: VisualOperation | undefined): boolean {
  if (!progress || !["candidate.requested", "codex.queued", "codex.started", "codex.image_requested", "codex.validating"].includes(progress.stage) || !Number.isFinite(Date.parse(progress.occurred_at))) return false;
  return !operation || (!["prepared", "executing"].includes(operation.status) && Date.parse(progress.occurred_at) >= Date.parse(operation.started_at));
}

export type VisionProgressConnection = "connecting" | "live" | "polling" | "complete";

const stages: Record<string, string> = {
  "codex.queued": "Waiting for Codex bridge",
  "codex.started": "Reading page elements",
  "codex.image_requested": "Image needed",
  "codex.validating": "Checking proposed action",
  "codex.completed": "Codex proposals received",
  "codex.failed": "Codex request stopped",
  "origin.observed": "External origin recorded",
  "origin.observations_limited": "External-origin log limit reached",
  "origin.observation_unavailable": "External-origin log temporarily unavailable",
  queued: "Exploration queued",
  started: "Starting advisory exploration",
  "state.captured": "Capturing a permitted page state",
  "candidate.requested": "Requesting advisory candidates",
  "candidate.received": "Advisory candidates received",
  "candidate.unavailable": "Invalid model response; continuing queued candidates",
  "action.recorded": "Candidate action recorded",
  "edge.proposed": "Candidate branch proposed",
  "edge.observed": "Candidate branch observed",
  "edge.failed": "Candidate branch unavailable",
  "edge.terminal": "Candidate branch terminal",
  "limit.reached": "Configured exploration limit reached",
  "draft.handoff": "Preparing generated-draft handoff",
  "operation.prepared": "Browser action prepared",
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
  cancelled: "Advisory exploration cancelled",
  unavailable: "Advisory exploration unavailable",
};

export function orderedVisionProgress(items: VisionProgressActivity[]): VisionProgressActivity[] {
  const unique = new Map(items.map((item) => [item.id, item]));
  return [...unique.values()].sort(
    (left, right) => left.occurred_at.localeCompare(right.occurred_at) || left.id.localeCompare(right.id),
  );
}

export function latestVisionProgress(items: VisionProgressActivity[]): VisionProgressActivity | null {
  const ordered = orderedVisionProgress(items);
  const terminal = ordered.filter((item) => ["completed", "unavailable", "cancelled"].includes(item.stage)).at(-1);
  if (terminal) return terminal;
  const ended = new Set(ordered.filter((item) => ["codex.completed", "codex.failed"].includes(item.stage)).map((item) => item.metadata?.job_id).filter(Boolean));
  return ordered.filter((item) => !["codex.queued", "codex.started", "codex.image_requested", "codex.validating"].includes(item.stage) || !ended.has(item.metadata?.job_id)).at(-1) ?? null;
}

export function visionModelWaitLabel(progress: VisionProgressActivity | null | undefined): string {
  if (progress?.stage === "codex.started" && progress.metadata.mode === "image") return "Analyzing the requested screenshot";
  return progress?.stage.startsWith("codex.") ? visionProgressLabel(progress.stage) : "Waiting for model response";
}

export function visionProgressMetrics(progress: VisionProgressActivity | null | undefined): string {
  if (!progress?.stage.startsWith("codex.")) return "";
  const call = progress.metadata.call_sequence, elapsed = progress.metadata.elapsed_ms;
  const parts = [];
  if (typeof call === "number" && Number.isInteger(call) && call >= 1 && call <= 10) parts.push(`Call ${call}`);
  if (typeof elapsed === "number" && Number.isFinite(elapsed) && elapsed >= 0 && elapsed <= 3600000) parts.push(`${(elapsed / 1000).toFixed(1)}s elapsed at this update`);
  return parts.join(" · ");
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
  return Object.hasOwn(stages, stage) ? stages[stage] : "Advisory progress updated";
}

export function visionConnectionLabel(connection: VisionProgressConnection): string {
  if (connection === "complete") return "Saved progress";
  if (connection === "live") return "Live updates connected";
  if (connection === "polling") return "Reconnecting - polling fallback active";
  return "Connecting to live updates";
}
