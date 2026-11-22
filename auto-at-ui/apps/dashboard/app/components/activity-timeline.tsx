"use client";

import { useEffect, useState } from "react";

import { activities, type Activity } from "../run-api";
import { cn } from "@/lib/utils";
import { Section } from "./section";
import { StatusBadge } from "./status-badge";
import {
  orderedActivities,
  timelineConnectionLabel,
  usesPollingFallback,
  type TimelineConnectionState,
} from "./activity-timeline-model";

export function ActivityTimeline({ apiUrl, runId, correlationId, live }: {
  apiUrl: string;
  runId?: string;
  correlationId?: string;
  live: boolean;
}) {
  const [timeline, setTimeline] = useState<Activity[]>([]);
  const [connection, setConnection] = useState<TimelineConnectionState>("connecting");

  useEffect(() => {
    let disposed = false;
    const scope = correlationId ?? runId;
    if (!scope) return;
    const refresh = () => activities(apiUrl, scope, Boolean(correlationId))
      .then((events) => { if (!disposed) setTimeline(orderedActivities(events)); })
      .catch(() => undefined);
    refresh();
    if (usesPollingFallback(live, typeof EventSource !== "undefined")) {
      setConnection("polling");
      return;
    }
    const source = new EventSource(
      `${apiUrl}/api/v1/activities/stream?${correlationId ? "correlation_id" : "run_id"}=${encodeURIComponent(scope)}`,
      { withCredentials: true },
    );
    source.onopen = () => { if (!disposed) setConnection("live"); };
    source.addEventListener("activity", (message) => {
      try {
        const event = JSON.parse(message.data) as Activity;
        if (!disposed) {
          setTimeline((current) => orderedActivities([...current.filter((item) => item.id !== event.id), event]));
        }
      } catch {
        // Ignore malformed data; the server remains the only activity authority.
      }
    });
    source.onerror = () => {
      if (!disposed) {
        setConnection("polling");
        refresh();
      }
    };
    return () => { disposed = true; source.close(); };
  }, [apiUrl, correlationId, live, runId]);

  const stateLabel = timelineConnectionLabel(connection);
  return (
    <Section
      aria-label="Pipeline timeline"
      title="Pipeline timeline"
      actions={
        <span aria-live="polite" className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
          <span
            aria-hidden="true"
            className={cn(
              "size-1.5 rounded-full",
              connection === "live" ? "animate-pulse bg-success" : "bg-muted-foreground/60",
            )}
          />
          {stateLabel}
        </span>
      }
    >
      {timeline.length ? (
        <ol className="relative space-y-5 border-l border-border pl-6">
          {timeline.map((event) => (
            <li key={event.id} className="relative">
              <span
                aria-hidden="true"
                className="absolute -left-[29px] top-1.5 size-2.5 rounded-full border-2 border-card bg-primary ring-1 ring-border"
              />
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <StatusBadge status={event.status} />
                <time
                  dateTime={event.occurred_at}
                  className="text-xs tabular-nums text-muted-foreground"
                >
                  {new Date(event.occurred_at).toLocaleTimeString()}
                </time>
              </div>
              <p className="mt-1 text-sm break-words">{event.safe_summary}</p>
              <p className="text-xs text-muted-foreground">
                {event.source} / {event.stage}
              </p>
            </li>
          ))}
        </ol>
      ) : (
        <p className="text-sm text-muted-foreground">Waiting for safe activity events.</p>
      )}
    </Section>
  );
}
