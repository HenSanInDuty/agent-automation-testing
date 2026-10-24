"use client";

import { useEffect, useRef, useState } from "react";

import { listVisionProgress, visionProgressStreamUrl } from "../generation-api";
import type { VisionProgressActivity } from "../generation-types";
import { StatusBadge } from "./status-badge";
import {
  latestVisionProgress, orderedVisionProgress, parseVisionProgress, visionConnectionLabel, visionProgressLabel, visionProgressMetrics,
  type VisionProgressConnection,
} from "./vision-progress-timeline-model";
import { visionFailureMessage } from "./vision-provider-model";

export function VisionProgressTimeline({ apiUrl, sessionId, live, onActivity, onProgress }: {
  apiUrl: string;
  sessionId: string;
  live: boolean;
  onActivity: () => void;
  onProgress?: (item: VisionProgressActivity | null) => void;
}) {
  const [items, setItems] = useState<VisionProgressActivity[]>([]);
  const [connection, setConnection] = useState<VisionProgressConnection>("connecting");
  const [error, setError] = useState("");
  const log = useRef<HTMLDivElement>(null);
  const follow = useRef(true);
  const onActivityRef = useRef(onActivity);
  onActivityRef.current = onActivity;
  const onProgressRef = useRef(onProgress);
  onProgressRef.current = onProgress;

  useEffect(() => {
    let disposed = false;
    let timer: number | undefined;
    const refresh = () => listVisionProgress(apiUrl, sessionId).then((events) => {
      if (!disposed) {
        setItems((current) => orderedVisionProgress([...current, ...events]));
        setError("");
        onActivityRef.current();
      }
    }).catch(() => { if (!disposed) setError("Progress history is unavailable. Retrying while the session is running."); });
    const polling = () => {
      setConnection("polling");
      timer = window.setInterval(refresh, 5_000);
    };
    refresh();
    if (!live) {
      setConnection("complete");
      return () => { disposed = true; };
    }
    if (typeof EventSource === "undefined") {
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

  useEffect(() => { if (log.current && follow.current) log.current.scrollTop = log.current.scrollHeight; }, [items]);
  useEffect(() => { onProgressRef.current?.(latestVisionProgress(items)); }, [items]);

  return <section className="workspace-section vision-progress-card" aria-label="Advisory session progress">
    <h2>Advisory session progress</h2><p aria-live="polite">{visionConnectionLabel(connection)}</p>
    {error && <p role="status">{error}</p>}
    <div ref={log} role="log" aria-live="polite" onScroll={() => { const node = log.current; if (node) follow.current = node.scrollHeight - node.scrollTop - node.clientHeight < 40; }}>
      {items.length ? <ol className="stack-list">{items.map((item) => <li key={item.id}><StatusBadge status={item.status} /> {visionProgressLabel(item.stage)}<small>{item.safe_summary} / {new Date(item.occurred_at).toLocaleTimeString()}</small>{visionProgressMetrics(item) && <small>{visionProgressMetrics(item)}</small>}{item.stage === "origin.observed" && typeof item.metadata.origin === "string" && <small><code>{item.metadata.origin}</code> · {item.metadata.request_kind}</small>}{typeof item.metadata.reason_code === "string" && <small>{visionFailureMessage(item.metadata.reason_code) ?? item.metadata.reason_code.replaceAll("_", " ")}</small>}</li>)}</ol> : <p>{live ? "Waiting for safe advisory progress." : "No progress events were saved for this session."}</p>}
    </div>
  </section>;
}
