import type { VisualLocator, VisualOperation, VisionResult } from "../generation-types";

export function operationLabel(item: VisualOperation, locator?: VisualLocator): string {
  const labels: Record<string, string> = { navigate: "Open page", click: "Click", type: "Type into field", scroll: "Scroll page", wait: "Wait", back: "Go back", close_popup: "Close popup" };
  const label = labels[item.action_kind] ?? "Browser action";
  const target = locator?.status === "verified" && locator.descriptor?.strategy !== "css"
    ? locator?.descriptor?.value : null;
  return target && ["click", "type"].includes(item.action_kind) ? `${label} “${target}”` : label;
}

export function operationStatus(status: string): string {
  return ({ completed: "Performed", rejected: "Not executed", unknown: "Outcome unknown", failed: "Failed", prepared: "Preparing", executing: "In progress" } as Record<string, string>)[status] ?? "Pending";
}

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
