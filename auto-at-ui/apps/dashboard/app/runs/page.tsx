"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { PageHeader } from "../components/page-header";
import { StatusBadge } from "../components/status-badge";
import { runs, type Run } from "../run-api";

export default function RunsPage() {
  const apiUrl = process.env.NEXT_PUBLIC_CONTROL_PLANE_URL ?? "http://localhost:7000"; const [items, setItems] = useState<Run[]>([]); const [status, setStatus] = useState("");
  useEffect(() => { runs(apiUrl, status ? `status=${encodeURIComponent(status)}` : "").then((page) => setItems(page.items)).catch(() => setItems([])); }, [apiUrl, status]);
  return <><PageHeader eyebrow="Execution" title="Runs" description="Find and investigate deterministic test executions." /><label className="field filter-field">Status <select value={status} onChange={(event) => setStatus(event.target.value)}><option value="">All statuses</option><option>queued</option><option>running</option><option>passed</option><option>failed</option><option>errored</option><option>cancelled</option></select></label>{items.length ? <div className="table-wrap"><table><thead><tr><th>Run</th><th>Status</th><th>Test</th><th>Revision</th></tr></thead><tbody>{items.map((item) => <tr key={item.id}><td><Link href={`/runs/${item.id}`}>{item.id.slice(0, 8)}</Link></td><td><StatusBadge status={item.status} /></td><td>{item.test_case_id}</td><td><code>{item.revision.slice(0, 12)}</code></td></tr>)}</tbody></table></div> : <p className="panel">No runs match the current filter.</p>}</>;
}
