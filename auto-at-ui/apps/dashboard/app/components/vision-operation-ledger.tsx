"use client";

import { useEffect, useState } from "react";
import { getOperationFrameBlob } from "../generation-api";
import type { OperationFrame, VisualLocator, VisualOperation, VisionHandoffBranch } from "../generation-types";

function Frame({ apiUrl, sessionId, frame, role, locator, onDelete }: { apiUrl: string; sessionId: string; frame: OperationFrame; role: string; locator?: VisualLocator; onDelete?: (id: string) => void }) {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const abort = new AbortController();
    let objectUrl: string | null = null;
    setUrl(null); setError("");
    if (frame.id && frame.availability === "retained") {
      void getOperationFrameBlob(apiUrl, sessionId, frame.id, abort.signal).then((blob) => {
        if (abort.signal.aborted) return;
        objectUrl = URL.createObjectURL(blob); setUrl(objectUrl);
      }).catch(() => { if (!abort.signal.aborted) setError("Frame unavailable or access revoked."); });
    }
    return () => { abort.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [apiUrl, sessionId, frame.id, frame.availability]);
  const box = locator?.bounding_box;
  return <figure><figcaption><strong>{role}</strong></figcaption>
    {frame.availability !== "retained" ? <p role="status">{frame.availability === "deleted" ? "Frame deleted" : "Frame missing"}: {frame.reason_code?.replaceAll("_", " ")}</p> : error ? <p role="status">{error}</p> : url ? <div className="vision-replay-image"><img src={url} alt={`${role} operation frame`} onError={() => setError("Frame could not be displayed.")} />{role === "Before" && box && <span className="vision-replay-marker" style={{ left: `${(box.x + box.width / 2) * 100}%`, top: `${(box.y + box.height / 2) * 100}%` }}>Selected element</span>}</div> : <p role="status">Loading {role.toLowerCase()} frame…</p>}
    {onDelete && frame.id && frame.availability === "retained" && <button type="button" className="button button--danger" onClick={() => onDelete(frame.id!)}>Delete {role.toLowerCase()} frame</button>}
  </figure>;
}

export function VisionOperationLedger({ apiUrl, sessionId, items, locators, branches, selectedId, onSelect, follow, onFollow, onDelete }: {
  apiUrl: string; sessionId: string; items: VisualOperation[]; locators: VisualLocator[];
  branches: VisionHandoffBranch[]; selectedId: string | null; onSelect: (id: string) => void;
  follow: boolean; onFollow: (value: boolean) => void; onDelete?: (id: string) => void;
}) {
  const [branchId, setBranchId] = useState<string | null>(null);
  const [showRestore, setShowRestore] = useState(true);
  const branch = branches.find((b) => b.id === branchId);
  const visible = items.filter((item) => (!branch || branch.steps.some((step) => step.operation_id === item.id)) && (showRestore || !["restore", "replay"].includes(item.purpose)));
  const selected = items.find((item) => item.id === selectedId);
  const index = visible.findIndex((item) => item.id === selectedId);
  const locator = locators.find((item) => item.id === selected?.locator_id);
  return <section className="workspace-section" aria-label="Operation trace" tabIndex={0} onKeyDown={(event) => {
    if ((event.target as HTMLElement).closest("input,textarea,select,[contenteditable=true]")) return;
    const next = event.key === "Home" ? 0 : event.key === "End" ? visible.length - 1 : event.key === "ArrowLeft" ? Math.max(0, index - 1) : event.key === "ArrowRight" ? Math.min(visible.length - 1, index + 1) : null;
    if (next !== null && visible[next]) { event.preventDefault(); onSelect(visible[next].id); }
  }}>
    <h2>Operation trace</h2><p>Recorded browser actions in execution order. Selecting evidence does not control the browser.</p>
    <div className="button-row"><label><input type="checkbox" checked={follow} onChange={(event) => { setBranchId(null); onFollow(event.target.checked); }} /> Follow live</label><label><input type="checkbox" checked={showRestore} onChange={(event) => setShowRestore(event.target.checked)} /> Show restoration</label></div>
    {branches.length > 0 && <div className="button-row" aria-label="Recorded branches"><button type="button" className="button button--secondary" onClick={() => setBranchId(null)}>All operations</button>{branches.map((item, i) => <button type="button" className="button button--secondary" key={item.id} aria-pressed={item.id === branchId} onClick={() => { setBranchId(item.id); const id = item.steps.at(-1)?.operation_id; if (id) onSelect(id); }}>Branch {i + 1}{item.status === "blocked" ? ` · ${item.reason_code?.replaceAll("_", " ")}` : ""}</button>)}</div>}
    {visible.length ? <><ol className="vision-operation-list">{visible.map((item) => <li key={item.id}><button type="button" aria-current={item.id === selectedId ? "step" : undefined} className="button button--secondary" onClick={() => onSelect(item.id)}>View operation {item.sequence} {item.action_kind}</button> <strong>{item.purpose}</strong> · {item.status} · <time dateTime={item.started_at}>{new Date(item.started_at).toLocaleTimeString()}</time></li>)}</ol><label>Trace position<input type="range" aria-label="Trace position" min={0} max={Math.max(0, visible.length - 1)} value={Math.max(0, index)} onChange={(event) => onSelect(visible[Number(event.target.value)].id)} /></label></> : <p>No recorded operation is available in this view.</p>}
    {selected && <div aria-label="Selected operation"><h3>Operation {selected.sequence}: {selected.action_kind} · {selected.status}</h3><p>{locator?.descriptor ? `${locator.status} ${locator.descriptor.strategy}: ${locator.descriptor.value}` : selected.locator_id ? "Locator unresolved" : selected.purpose}{selected.outcome_code && ` · ${selected.outcome_code.replaceAll("_", " ")}`}</p><div className="vision-operation-frames"><Frame key={`before:${selected.id}`} apiUrl={apiUrl} sessionId={sessionId} frame={selected.before} role="Before" locator={locator} onDelete={onDelete} /><Frame key={`after:${selected.id}`} apiUrl={apiUrl} sessionId={sessionId} frame={selected.after} role="After" onDelete={onDelete} /></div></div>}
  </section>;
}
