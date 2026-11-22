"use client";

import { useEffect, useRef, useState } from "react";

import { listVisionProgress, visionProgressStreamUrl } from "../generation-api";
import type { VisionProgressActivity } from "../generation-types";
import { Code, Notice } from "./agent-ui";
import { Section } from "./section";
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

  return <Section aria-label="Advisory session progress" title="Advisory session progress" description={<span aria-live="polite">{visionConnectionLabel(connection)}</span>} contentClassName="grid gap-3">
    {error && <Notice tone="warning" role="status">{error}</Notice>}
    <div ref={log} role="log" aria-live="polite" className="max-h-96 overflow-y-auto rounded-lg border bg-muted/20 p-3 scrollbar-thin" onScroll={() => { const node = log.current; if (node) follow.current = node.scrollHeight - node.scrollTop - node.clientHeight < 40; }}>
      {items.length ? <ol className="grid gap-3">{items.map((item) => <li key={item.id} className="grid gap-1 border-l-2 pl-3 text-sm"><span className="flex flex-wrap items-center gap-2"><StatusBadge status={item.status} /> <span className="font-medium">{visionProgressLabel(item.stage)}</span></span><small className="block text-xs text-muted-foreground">{item.safe_summary} / {new Date(item.occurred_at).toLocaleTimeString()}</small>{visionProgressMetrics(item) && <small className="block text-xs text-muted-foreground">{visionProgressMetrics(item)}</small>}{item.stage === "origin.observed" && typeof item.metadata.origin === "string" && <small className="block text-xs text-muted-foreground"><Code>{item.metadata.origin}</Code> · {item.metadata.request_kind}</small>}{typeof item.metadata.reason_code === "string" && <small className="block text-xs text-muted-foreground">{visionFailureMessage(item.metadata.reason_code) ?? item.metadata.reason_code.replaceAll("_", " ")}</small>}</li>)}</ol> : <p className="text-sm text-muted-foreground">{live ? "Waiting for safe advisory progress." : "No progress events were saved for this session."}</p>}
    </div>
  </Section>;
}
