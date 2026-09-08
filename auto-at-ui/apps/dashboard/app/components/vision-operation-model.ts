import type { VisualOperation, VisionResult } from "../generation-types";

export function selectedOperation(items: VisualOperation[], selected: string | null, follow: boolean): string | null {
  if (follow) return items.at(-1)?.id ?? null;
  return items.find((item) => item.id === selected)?.id ?? items[0]?.id ?? null;
}
export function shouldPollVisionResult(result: VisionResult): boolean {
  return ["queued", "running"].includes(result.exploration_state)
    || ["queued", "generating"].includes(result.links.generation.state)
    || ["queued", "running"].includes(result.links.run.state)
    || result.links.report.state === "pending";
}
export function visionResultLabel(state: string): string {
  const labels: Record<string, string> = { completed: "Exploration complete", unavailable: "Unavailable", failed: "Failed", pending_review: "Awaiting review", ready: "Verified evidence ready", not_started: "Not started", legacy_missing: "No recorded link", available: "Available", queued: "Queued", generating: "Creating draft", running: "Running", pending: "Pending", cancelled: "Cancelled" };
  return labels[state] ?? state.replaceAll("_", " ");
}
