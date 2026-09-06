"use client";

import { useEffect, useRef, useState } from "react";

import { listVisionProgress, visionProgressStreamUrl } from "../generation-api";
import type { VisionProgressActivity } from "../generation-types";
import { StatusBadge } from "./status-badge";
import {
  orderedVisionProgress, parseVisionProgress, visionConnectionLabel, visionProgressLabel,
  type VisionProgressConnection,
} from "./vision-progress-timeline-model";

export function VisionProgressTimeline({ apiUrl, sessionId, live, onActivity }: {
  apiUrl: string;
  sessionId: string;
  live: boolean;
  onActivity: () => void;
}) {
  const [items, setItems] = useState<VisionProgressActivity[]>([]);
  const [connection, setConnection] = useState<VisionProgressConnection>("connecting");
  const onActivityRef = useRef(onActivity);
  onActivityRef.current = onActivity;

  useEffect(() => {
    let disposed = false;
    let timer: number | undefined;
    const refresh = () => listVisionProgress(apiUrl, sessionId).then((events) => {
      if (!disposed) {
        setItems(orderedVisionProgress(events));
        onActivityRef.current();
      }
    }).catch(() => undefined);
    const polling = () => {
      setConnection("polling");
      timer = window.setInterval(refresh, 5_000);
    };
    refresh();
    if (!live || typeof EventSource === "undefined") {
      polling();
      return () => { disposed = true; if (timer) window.clearInterval(timer); };
    }
    const source = new EventSource(visionProgressStreamUrl(apiUrl, sessionId), { withCredentials: true });
    source.onopen = () => { if (!disposed) setConnection("live"); };
    source.addEventListener("activity", (message) => {
      try {
        const event = parseVisionProgress(JSON.parse(message.data));
        if (event && !disposed) {
          setItems((current) => orderedVisionProgress([...current, event]));
          onActivityRef.current();
        }
      } catch {
        // Malformed server data is ignored; it cannot be treated as an action payload.
      }
    });
    source.onerror = () => {
      source.close();
      if (!disposed && timer === undefined) polling();
    };
    return () => { disposed = true; source.close(); if (timer) window.clearInterval(timer); };
  }, [apiUrl, live, sessionId]);

  return <section className="workspace-section" aria-label="Advisory session progress">
    <div className="section-heading"><h3>Advisory session progress</h3><small aria-live="polite">{visionConnectionLabel(connection)}</small></div>
    {items.length ? <ol className="stack-list">{items.map((item) => <li key={item.id}><StatusBadge status={item.status} /> {visionProgressLabel(item.stage)}<small>{item.safe_summary} / {new Date(item.occurred_at).toLocaleTimeString()}</small></li>)}</ol> : <p>Waiting for safe advisory progress.</p>}
  </section>;
}
