export type StatusTone = "neutral" | "success" | "danger" | "warning" | "muted";

const statusTones: Record<string, StatusTone> = {
  passed: "success", approved: "success", completed: "success",
  failed: "danger", errored: "danger", rejected: "danger",
  queued: "warning", running: "warning", generating: "warning", pending_review: "warning",
  skipped: "muted", cancelled: "muted",
};

export function statusTone(status: string): StatusTone { return statusTones[status.toLowerCase()] ?? "neutral"; }
export function statusLabel(status: string): string { return status.replaceAll("_", " "); }
