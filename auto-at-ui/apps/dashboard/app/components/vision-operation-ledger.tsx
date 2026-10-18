"use client";

import { useState } from "react";
import type { VisualLocator, VisualOperation, VisionHandoffBranch } from "../generation-types";
import { operationLabel, operationStatus } from "./vision-operation-model";

export function VisionOperationLedger({ items, locators, branches, selectedId, onSelect, follow, onFollow }: {
  items: VisualOperation[]; locators: VisualLocator[];
  branches: VisionHandoffBranch[]; selectedId: string | null; onSelect: (id: string) => void;
  follow: boolean; onFollow: (value: boolean) => void;
}) {
  const [branchId, setBranchId] = useState<string | null>(null);
  const [showRestore, setShowRestore] = useState(true);
  const branch = branches.find((b) => b.id === branchId);
  const visible = items.filter((item) => (!branch || branch.steps.some((step) => step.operation_id === item.id)) && (showRestore || !["restore", "replay"].includes(item.purpose)));
  const selected = items.find((item) => item.id === selectedId);
  const index = visible.findIndex((item) => item.id === selectedId);
  const locator = locators.find((item) => item.id === selected?.locator_id);
  return <section className="workspace-section vision-steps-card" aria-label="Operation trace" tabIndex={0} onKeyDown={(event) => {
    if ((event.target as HTMLElement).closest("input,textarea,select,[contenteditable=true]")) return;
    const next = event.key === "Home" ? 0 : event.key === "End" ? visible.length - 1 : event.key === "ArrowLeft" ? Math.max(0, index - 1) : event.key === "ArrowRight" ? Math.min(visible.length - 1, index + 1) : null;
    if (next !== null && visible[next]) { event.preventDefault(); onSelect(visible[next].id); }
  }}>
    <div className="section-heading"><h2>Browser steps</h2><label><input type="checkbox" checked={follow} onChange={(event) => { setBranchId(null); onFollow(event.target.checked); }} /> Follow live</label></div>
    <details className="vision-step-filters"><summary>Filter steps</summary>
    <label><input type="checkbox" checked={showRestore} onChange={(event) => setShowRestore(event.target.checked)} /> Show restoration</label>
    {branches.length > 0 && <div className="button-row" aria-label="Recorded branches"><button type="button" className="button button--secondary" onClick={() => setBranchId(null)}>All operations</button>{branches.map((item, i) => <button type="button" className="button button--secondary" key={item.id} aria-pressed={item.id === branchId} onClick={() => { setBranchId(item.id); const id = item.steps.at(-1)?.operation_id; if (id) onSelect(id); }}>Branch {i + 1}{item.status === "blocked" ? ` · ${item.reason_code?.replaceAll("_", " ")}` : ""}</button>)}</div>}
    </details>
    {visible.length ? <><ol className="vision-operation-list">{visible.map((item) => <li key={item.id}><button type="button" aria-label={`View operation ${item.sequence} ${item.action_kind}`} aria-current={item.id === selectedId ? "step" : undefined} className="vision-step" onClick={() => onSelect(item.id)}><span className="vision-step-number">{item.sequence}</span><span><strong>{operationLabel(item, locators.find((locator) => locator.id === item.locator_id))}</strong><small>{operationStatus(item.status)}{["restore", "replay"].includes(item.purpose) && " · Returning to an earlier page"}</small></span></button></li>)}</ol><label className="vision-trace-position">Step position<input type="range" aria-label="Trace position" min={0} max={Math.max(0, visible.length - 1)} value={Math.max(0, index)} onChange={(event) => onSelect(visible[Number(event.target.value)].id)} /></label></> : <p>No browser action has been recorded yet.</p>}
    {selected && <div className="vision-selected-step" aria-label="Selected operation"><strong>Operation {selected.sequence}: {operationLabel(selected, locator)}</strong><p>{operationStatus(selected.status)}</p></div>}
  </section>;
}
