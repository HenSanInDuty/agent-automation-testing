"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ActivityTimeline } from "./components/activity-timeline";
import { ConfirmDialog } from "./components/confirm-dialog";
import { EmptyState, LoadingState } from "./components/states";
import { StatusBadge } from "./components/status-badge";
import { ControlPlaneError, getVisionPolicy, listGenerationRequests, listVisualActions, listVisualExplorations, setVisionPolicy, submitVisualExploration } from "./generation-api";
import type { VisualAction, VisualExploration, VisionPolicy } from "./generation-types";
import { projects, type Project } from "./run-api";

const terminal = new Set(["completed", "unavailable", "cancelled"]);
const message = (error: unknown) => error instanceof ControlPlaneError ? error.message : "The control plane is unavailable. Try again later.";

function SafeAction({ item }: { item: VisualAction }) {
  const action = item.action;
  const detail = [
    typeof action.confidence === "number" ? `confidence ${action.confidence}` : null,
    typeof action.x === "number" && typeof action.y === "number" ? `position ${action.x}, ${action.y}` : null,
    typeof action.delta_y === "number" ? `scroll ${action.delta_y}` : null,
    typeof action.duration_ms === "number" ? `wait ${action.duration_ms}ms` : null,
  ].filter(Boolean).join(" · ");
  return <li><strong>{item.sequence}. {action.kind}</strong>{detail && ` — ${detail}`}{item.evidence_checksum && <><br />Screenshot checksum: <code>{item.evidence_checksum}</code></>}</li>;
}

export function VisionDashboard({ apiUrl }: { apiUrl: string }) {
  const [policy, setPolicy] = useState<VisionPolicy | null>(null);
  const [acknowledged, setAcknowledged] = useState(false);
  const [options, setOptions] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [targetUrl, setTargetUrl] = useState("");
  const [taskIntent, setTaskIntent] = useState("");
  const [useVision, setUseVision] = useState(false);
  const [sessions, setSessions] = useState<VisualExploration[]>([]);
  const [selected, setSelected] = useState<VisualExploration | null>(null);
  const [actions, setActions] = useState<VisualAction[]>([]);
  const [draftId, setDraftId] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [saving, setSaving] = useState(false);
  const enabled = Boolean(policy?.enabled && policy.raw_screenshot_transfer_accepted);
  const active = useMemo(() => selected !== null && !terminal.has(selected.state), [selected]);

  useEffect(() => { getVisionPolicy(apiUrl).then(setPolicy).catch((error) => setNotice(message(error))); }, [apiUrl]);
  useEffect(() => { projects(apiUrl).then((items) => { setOptions(items); setProjectId((current) => current || items[0]?.id || ""); }).catch((error) => setNotice(message(error))); }, [apiUrl]);
  useEffect(() => {
    if (!projectId) { setSessions([]); return; }
    listVisualExplorations(apiUrl, projectId).then((page) => {
      setSessions(page.items);
      setSelected((current) => current ? page.items.find((item) => item.id === current.id) ?? null : page.items[0] ?? null);
    }).catch((error) => setNotice(message(error)));
  }, [apiUrl, projectId]);
  useEffect(() => {
    if (!selected) { setActions([]); setDraftId(null); return; }
    void Promise.all([listVisualActions(apiUrl, selected.id), listGenerationRequests(apiUrl)])
      .then(([nextActions, requests]) => { setActions(nextActions); setDraftId(requests.items.find((request) => request.correlation_id === selected.correlation_id)?.draft_id ?? null); })
      .catch((error) => setNotice(message(error)));
  }, [apiUrl, selected]);
  useEffect(() => {
    if (!selected || terminal.has(selected.state)) return;
    const timer = window.setInterval(() => {
      if (!projectId) return;
      void listVisualExplorations(apiUrl, projectId).then((page) => {
        setSessions(page.items);
        setSelected(page.items.find((item) => item.id === selected.id) ?? null);
      }).catch((error) => setNotice(message(error)));
    }, 2000);
    return () => window.clearInterval(timer);
  }, [apiUrl, projectId, selected]);

  async function saveVisionPolicy(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!policy) return;
    setSaving(true); setNotice("");
    try { setPolicy(await setVisionPolicy(apiUrl, { ...policy, raw_screenshot_transfer_accepted: policy.enabled ? acknowledged : false })); setAcknowledged(false); setNotice("Vision policy saved by the control plane."); }
    catch (error) { setNotice(message(error)); }
    finally { setSaving(false); }
  }
  function requestExploration(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setNotice("");
    if (!enabled || !useVision) { setNotice("Vision exploration is disabled by tenant policy."); return; }
    setConfirming(true);
  }
  async function submitExploration() {
    setConfirming(false);
    try {
      const session = await submitVisualExploration(apiUrl, { project_id: projectId, target_url: targetUrl, task_intent: taskIntent, use_vision: true });
      setSessions((current) => [session, ...current.filter((item) => item.id !== session.id)]); setSelected(session); setNotice("Visual exploration queued. It is advisory and cannot change a test verdict.");
    } catch (error) { setNotice(message(error)); }
  }

  return <>
    <section className="workspace-section" aria-label="Vision settings"><h2>Vision settings</h2>{policy ? <form onSubmit={saveVisionPolicy} className="form-grid form-grid--one"><p>Provider: <code>{policy.provider}</code><br />Model: <code>{policy.model}</code><br />Limits: {policy.max_session_seconds}s, {policy.max_screenshot_bytes} bytes, ${policy.max_cost_usd} per session. Project policy sets BFS depth and total states.</p><label className="field"><input type="checkbox" checked={policy.enabled} onChange={(event) => setPolicy({ ...policy, enabled: event.target.checked })} /> Enable vision exploration</label><label className="field"><input type="checkbox" checked={acknowledged} onChange={(event) => setAcknowledged(event.target.checked)} disabled={!policy.enabled} /> I understand raw screenshots for this tenant may be sent to Hugging Face.</label><div className="form-actions"><button className="button button--secondary" disabled={saving || (policy.enabled && !acknowledged)}>{saving ? "Saving…" : "Save vision settings"}</button></div><p>Only a tenant administrator can save these settings. The server verifies authorization and consent.</p></form> : <LoadingState title="Loading vision policy" />}</section>
    <section className="workspace-section" aria-label="Vision exploration"><h2>Explore with the Vision Agent</h2><p>Vision is advisory only. A raw screenshot may be transferred to Hugging Face; it never decides a test result, and any resulting draft still needs human approval.</p><form onSubmit={requestExploration} className="form-grid"><label className="field">Project<select required value={projectId} onChange={(event) => setProjectId(event.target.value)}><option value="">Choose a project</option>{options.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}</select></label><label className="field">Target URL<input required type="url" value={targetUrl} onChange={(event) => setTargetUrl(event.target.value)} /></label><label className="field form-grid--full">Exploration intent<textarea required value={taskIntent} onChange={(event) => setTaskIntent(event.target.value)} /></label><label className="field form-grid--full"><input type="checkbox" checked={useVision} onChange={(event) => setUseVision(event.target.checked)} disabled={!enabled} /> Use Vision Agent</label>{!enabled && <p className="form-grid--full">Vision is unavailable until a tenant administrator enables it and accepts the raw-screenshot transfer disclosure.</p>}<div className="form-actions form-grid--full"><button className="button" disabled={!projectId || !enabled || !useVision}>Start advisory exploration</button></div></form></section>
    {notice && <p className={`notice ${notice.includes("unavailable") || notice.includes("disabled") ? "notice--error" : ""}`} role="alert">{notice}</p>}
    <section className="workspace-section" aria-label="Visual exploration sessions"><h2>Visual exploration sessions</h2>{sessions.length ? <ul className="stack-list">{sessions.map((session) => <li key={session.id}><button type="button" className="button button--secondary" onClick={() => setSelected(session)}>View</button> <StatusBadge status={session.state} /> <code>{session.id}</code></li>)}</ul> : <EmptyState title="No visual explorations">Start one only after confirming the privacy disclosure above.</EmptyState>}</section>
    {selected && <><section className="workspace-section" aria-label="Selected visual exploration"><div className="section-heading"><h2>Advisory session</h2><StatusBadge status={selected.state} /></div><ul className="detail-list"><li>Correlation: <code>{selected.correlation_id}</code></li><li>Bounded to {selected.max_hops} hops, {selected.max_states} states, and {selected.max_session_seconds} seconds.</li><li>Stop condition: state/depth limit, time limit, policy guard, provider failure, or model stop.</li>{selected.safe_failure_reason && <li>Safe failure: {selected.safe_failure_reason}</li>}</ul>{active && <LoadingState title="Visual exploration is in progress" />}<h3>Safe action candidates</h3>{actions.length ? <ul className="stack-list">{actions.map((action) => <SafeAction key={action.sequence} item={action} />)}</ul> : <p>No action candidate has been recorded.</p>}{draftId && <p><Link href={`/agent?draft=${encodeURIComponent(draftId)}`}>Review the resulting Playwright draft</Link></p>}</section><ActivityTimeline apiUrl={apiUrl} correlationId={selected.correlation_id} live={active} /></>}
    <ConfirmDialog open={confirming} title="Send a screenshot to Hugging Face?" description="This starts an advisory exploration. Raw screenshots may be sent to the configured Hugging Face model; no test verdict or source change occurs without the existing human review flow." confirmLabel="Start advisory exploration" onConfirm={() => void submitExploration()} onCancel={() => setConfirming(false)} />
  </>;
}
