"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { artifactDownloadUrl } from "../../api-client";
import { PageHeader } from "../../components/page-header";
import { StatusBadge } from "../../components/status-badge";
import {
  activities,
  artifacts,
  cancelRun,
  run,
  type Activity,
  type Artifact,
  type Run,
} from "../../run-api";

export default function RunDetailPage() {
  const apiUrl = process.env.NEXT_PUBLIC_CONTROL_PLANE_URL ?? "http://localhost:7000";
  const id = String(useParams<{ id: string }>().id);
  const [item, setItem] = useState<Run | null>(null);
  const [evidence, setEvidence] = useState<Artifact[]>([]);
  const [timeline, setTimeline] = useState<Activity[]>([]);
  const [notice, setNotice] = useState("");

  useEffect(() => {
    Promise.all([run(apiUrl, id), artifacts(apiUrl, id), activities(apiUrl, id)])
      .then(([next, files, events]) => { setItem(next); setEvidence(files); setTimeline(events); })
      .catch((error: Error) => setNotice(error.message));
  }, [apiUrl, id]);
  useEffect(() => {
    if (!item || !["queued", "running"].includes(item.status)) return;
    const timer = window.setInterval(() => activities(apiUrl, id).then(setTimeline).catch(() => undefined), 3000);
    return () => window.clearInterval(timer);
  }, [apiUrl, id, item]);
  if (!item) return <><PageHeader eyebrow="Execution" title="Run detail" description="Loading deterministic run evidence." /><p className="panel">Loading…</p></>;
  const cancellable = item.status === "queued" || item.status === "running";
  return <><PageHeader eyebrow="Execution" title={`Run ${item.id.slice(0, 8)}`} description="Immutable request, deterministic result, and verified evidence." actions={cancellable ? <button className="button button--danger" onClick={() => cancelRun(apiUrl, item.id).then(setItem).catch((error: Error) => setNotice(error.message))}>Cancel run</button> : undefined} /><section className="workspace-section"><div className="section-heading"><h2>Result</h2><StatusBadge status={item.status} /></div><ul className="detail-list"><li>Correlation ID: <code>{item.correlation_id}</code></li><li>Test: {item.test_case_id}</li><li>Revision: <code>{item.revision}</code></li>{item.terminal_summary && <li>Terminal summary: {item.terminal_summary}</li>}</ul></section><section className="workspace-section"><h2>Pipeline timeline</h2>{timeline.length ? <ol className="stack-list">{timeline.map((event) => <li key={event.id}><StatusBadge status={event.status} /> {event.safe_summary} <small>{event.source} / {event.stage}</small></li>)}</ol> : <p>Waiting for safe activity events.</p>}</section><section className="workspace-section"><h2>Artifacts</h2>{evidence.length ? <ul className="stack-list">{evidence.map((file) => <li key={file.id}><a href={artifactDownloadUrl(apiUrl, item.id, file.id)}>{file.kind}</a> — {file.size} bytes</li>)}</ul> : <p>No artifacts were retained for this run.</p>}</section>{notice && <p className="notice notice--error">{notice}</p>}</>;
}
