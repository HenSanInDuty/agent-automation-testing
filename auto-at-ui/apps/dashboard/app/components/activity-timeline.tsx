"use client";

import { useEffect, useState } from "react";

import { activities, type Activity } from "../run-api";
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
  return <section className="workspace-section" aria-label="Pipeline timeline">
    <div className="section-heading"><h2>Pipeline timeline</h2><small aria-live="polite">{stateLabel}</small></div>
    {timeline.length ? <ol className="stack-list">{timeline.map((event) => <li key={event.id}><StatusBadge status={event.status} /> {event.safe_summary} <small>{event.source} / {event.stage} / {new Date(event.occurred_at).toLocaleTimeString()}</small></li>)}</ol> : <p>Waiting for safe activity events.</p>}
  </section>;
}
