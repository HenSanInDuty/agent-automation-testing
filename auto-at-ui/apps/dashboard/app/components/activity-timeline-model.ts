import type { Activity } from "../run-api";

export type TimelineConnectionState = "connecting" | "live" | "polling";

export function orderedActivities(events: Activity[]): Activity[] {
  return [...events].sort((left, right) => (
    left.occurred_at.localeCompare(right.occurred_at) || left.id.localeCompare(right.id)
  ));
}

export function timelineConnectionLabel(connection: TimelineConnectionState): string {
  if (connection === "live") return "Live updates connected";
  if (connection === "polling") return "Reconnecting - polling fallback active";
  return "Connecting to live updates";
}

export function usesPollingFallback(live: boolean, eventSourceAvailable: boolean): boolean {
  return !live || !eventSourceAvailable;
}
