"use client";

import { useEffect, useState } from "react";

import { activities, type Activity } from "../run-api";
import { StatusBadge } from "./status-badge";

type ConnectionState = "connecting" | "live" | "polling";

function ordered(events: Activity[]): Activity[] {
  return [...events].sort((left, right) => (
    left.occurred_at.localeCompare(right.occurred_at) || left.id.localeCompare(right.id)
  ));
}

export function ActivityTimeline({ apiUrl, runId, live }: {
  apiUrl: string;
  runId: string;
  live: boolean;
}) {
  const [timeline, setTimeline] = useState<Activity[]>([]);
  const [connection, setConnection] = useState<ConnectionState>("connecting");

  useEffect(() => {
    let disposed = false;
    const refresh = () => activities(apiUrl, runId)
      .then((events) => { if (!disposed) setTimeline(ordered(events)); })
      .catch(() => undefined);
    refresh();
    if (!live || typeof EventSource === "undefined") {
      setConnection("polling");
      return;
    }
    const source = new EventSource(
      `${apiUrl}/api/v1/activities/stream?run_id=${encodeURIComponent(runId)}`,
      { withCredentials: true },
    );
    source.onopen = () => { if (!disposed) setConnection("live"); };
    source.addEventListener("activity", (message) => {
      try {
        const event = JSON.parse(message.data) as Activity;
        if (!disposed) {
          setTimeline((current) => ordered([...current.filter((item) => item.id !== event.id), event]));
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
  }, [apiUrl, live, runId]);

  const stateLabel = connection === "live" ? "Live updates connected" : connection === "polling" ? "Reconnecting - polling fallback active" : "Connecting to live updates";
  return <section className="workspace-section" aria-label="Pipeline timeline">
    <div className="section-heading"><h2>Pipeline timeline</h2><small aria-live="polite">{stateLabel}</small></div>
    {timeline.length ? <ol className="stack-list">{timeline.map((event) => <li key={event.id}><StatusBadge status={event.status} /> {event.safe_summary} <small>{event.source} / {event.stage} / {new Date(event.occurred_at).toLocaleTimeString()}</small></li>)}</ol> : <p>Waiting for safe activity events.</p>}
  </section>;
}
