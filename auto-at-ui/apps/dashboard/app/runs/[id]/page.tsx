"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { artifactDownloadUrl } from "../../api-client";
import { ActivityTimeline } from "../../components/activity-timeline";
import { PageHeader } from "../../components/page-header";
import { StatusBadge } from "../../components/status-badge";
import { artifacts, cancelRun, run, type Artifact, type Run } from "../../run-api";

export default function RunDetailPage() {
  const apiUrl = process.env.NEXT_PUBLIC_CONTROL_PLANE_URL ?? "http://localhost:7000";
  const id = String(useParams<{ id: string }>().id);
  const [item, setItem] = useState<Run | null>(null);
  const [evidence, setEvidence] = useState<Artifact[]>([]);
  const [notice, setNotice] = useState("");

  useEffect(() => {
    Promise.all([run(apiUrl, id), artifacts(apiUrl, id)])
      .then(([next, files]) => { setItem(next); setEvidence(files); })
      .catch((error: Error) => setNotice(error.message));
  }, [apiUrl, id]);

  if (!item) return <><PageHeader eyebrow="Execution" title="Run detail" description="Loading deterministic run evidence." /><p className="panel">Loading...</p></>;
  const cancellable = item.status === "queued" || item.status === "running";
  return <>
    <PageHeader eyebrow="Execution" title={`Run ${item.id.slice(0, 8)}`} description="Immutable request, deterministic result, and verified evidence." actions={cancellable ? <button className="button button--danger" onClick={() => cancelRun(apiUrl, item.id).then(setItem).catch((error: Error) => setNotice(error.message))}>Cancel run</button> : undefined} />
    <section className="workspace-section"><div className="section-heading"><h2>Result</h2><StatusBadge status={item.status} /></div><ul className="detail-list"><li>Correlation ID: <code>{item.correlation_id}</code></li><li>Test: {item.test_case_id}</li><li>Revision: <code>{item.revision}</code></li>{item.terminal_summary && <li>Terminal summary: {item.terminal_summary}</li>}</ul></section>
    <ActivityTimeline apiUrl={apiUrl} runId={item.id} live={cancellable} />
    <section className="workspace-section"><h2>Artifacts</h2>{evidence.length ? <ul className="stack-list">{evidence.map((file) => <li key={file.id}><a href={artifactDownloadUrl(apiUrl, item.id, file.id)}>{file.kind}</a> - {file.size} bytes</li>)}</ul> : <p>No artifacts were retained for this run.</p>}</section>
    {notice && <p className="notice notice--error">{notice}</p>}
  </>;
}
