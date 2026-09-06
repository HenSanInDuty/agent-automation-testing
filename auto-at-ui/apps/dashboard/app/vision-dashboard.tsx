"use client";

import { FormEvent, type ReactNode, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ConfirmDialog } from "./components/confirm-dialog";
import { EmptyState, LoadingState } from "./components/states";
import { StatusBadge } from "./components/status-badge";
import { VisionProgressTimeline } from "./components/vision-progress-timeline";
import { orderedReplayFrames, replayMarkerPosition } from "./components/vision-replay-model";
import { ControlPlaneError, deleteVisualReplayFrame, deleteVisualReplayFrames, getVisionDebugEvidence, getVisionPolicy, getVisualExploration, getVisualReplayFrameBlob, listGenerationRequests, listVisionDebugEvidence, listVisualActions, listVisualExplorations, listVisualReplayFrames, setVisionPolicy, submitVisualExploration } from "./generation-api";
import type { VisualAction, VisualExploration, VisualReplayFrame, VisionDebugEvidencePayload, VisionPolicy } from "./generation-types";
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

export function VisionDashboard({ apiUrl, projectPolicy }: { apiUrl: string; projectPolicy?: ReactNode }) {
  const [policy, setPolicy] = useState<VisionPolicy | null>(null);
  const [options, setOptions] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [targetUrl, setTargetUrl] = useState("");
  const [taskIntent, setTaskIntent] = useState("");
  const [useVision, setUseVision] = useState(false);
  const [sessions, setSessions] = useState<VisualExploration[]>([]);
  const [selected, setSelected] = useState<VisualExploration | null>(null);
  const [actions, setActions] = useState<VisualAction[]>([]);
  const [frames, setFrames] = useState<VisualReplayFrame[]>([]);
  const [selectedFrame, setSelectedFrame] = useState<VisualReplayFrame | null>(null);
  const [frameUrl, setFrameUrl] = useState<string | null>(null);
  const [frameImageSize, setFrameImageSize] = useState<{ width: number; height: number } | null>(null);
  const [draftId, setDraftId] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [replayDeletion, setReplayDeletion] = useState<"frame" | "all" | null>(null);
  const [deletingReplay, setDeletingReplay] = useState(false);
  const [role, setRole] = useState<string | null>(null);
  const [debugEvidence, setDebugEvidence] = useState<VisionDebugEvidencePayload | null>(null);
  const [saving, setSaving] = useState(false);
  const enabled = Boolean(policy?.enabled && policy.raw_screenshot_transfer_accepted);
  const active = useMemo(() => selected !== null && !terminal.has(selected.state), [selected]);

  useEffect(() => { getVisionPolicy(apiUrl).then(setPolicy).catch((error) => setNotice(message(error))); }, [apiUrl]);
  useEffect(() => { fetch(`${apiUrl}/api/v1/auth/me`, { credentials: "include" }).then(async (response) => response.ok ? setRole((await response.json() as { role: string }).role) : setRole(null)).catch(() => setRole(null)); }, [apiUrl]);
  useEffect(() => { projects(apiUrl).then((items) => { setOptions(items); setProjectId((current) => current || items[0]?.id || ""); }).catch((error) => setNotice(message(error))); }, [apiUrl]);
  useEffect(() => {
    if (!projectId) { setSessions([]); return; }
    listVisualExplorations(apiUrl, projectId).then((page) => {
      setSessions(page.items);
      setSelected((current) => current ? page.items.find((item) => item.id === current.id) ?? null : page.items[0] ?? null);
    }).catch((error) => setNotice(message(error)));
  }, [apiUrl, projectId]);
  function refreshSelected(sessionId: string) {
    void Promise.all([getVisualExploration(apiUrl, sessionId), listVisualActions(apiUrl, sessionId), listGenerationRequests(apiUrl)])
      .then(([session, nextActions, requests]) => {
        setSelected((current) => {
          if (current?.id !== sessionId) return current;
          return current.state === session.state
            && current.safe_failure_reason === session.safe_failure_reason ? current : session;
        });
        setSessions((current) => current.map((item) => item.id === sessionId ? session : item));
        setActions(nextActions);
        setDraftId(requests.items.find((request) => request.correlation_id === session.correlation_id)?.draft_id ?? null);
      }).catch((error) => setNotice(message(error)));
  }
  useEffect(() => {
    if (!selected) { setActions([]); setDraftId(null); return; }
    refreshSelected(selected.id);
  }, [apiUrl, selected]);
  useEffect(() => {
    if (!selected) { setFrames([]); setSelectedFrame(null); return; }
    listVisualReplayFrames(apiUrl, selected.id).then((result) => {
      const ordered = orderedReplayFrames(result.items);
      setFrames(ordered);
      setSelectedFrame((current) => ordered.find((item) => item.id === current?.id) ?? ordered[0] ?? null);
    }).catch((error) => setNotice(message(error)));
  }, [apiUrl, selected]);
  useEffect(() => {
    let active = true;
    setFrameImageSize(null);
    setFrameUrl((current) => { if (current) URL.revokeObjectURL(current); return null; });
    if (!selected || !selectedFrame) return;
    getVisualReplayFrameBlob(apiUrl, selected.id, selectedFrame.id).then((blob) => {
      if (!active) return;
      const next = URL.createObjectURL(blob);
      setFrameUrl((current) => { if (current) URL.revokeObjectURL(current); return next; });
    }).catch((error) => setNotice(message(error)));
    return () => { active = false; };
  }, [apiUrl, selected, selectedFrame]);

  async function saveVisionPolicy(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!policy) return;
    setSaving(true); setNotice("");
    try { setPolicy(await setVisionPolicy(apiUrl, policy)); setNotice("Vision policy saved by the control plane."); }
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
  async function inspectDebugEvidence() {
    if (!selected) return;
    setDebugEvidence(null); setNotice("");
    try {
      const records = await listVisionDebugEvidence(apiUrl, selected.id);
      if (!records.length) { setNotice("No retained debug evidence is available."); return; }
      setDebugEvidence(await getVisionDebugEvidence(apiUrl, selected.id, records[0].id));
    } catch (error) { setNotice(message(error)); }
  }
  async function deleteReplay() {
    if (!selected || !replayDeletion || (replayDeletion === "frame" && !selectedFrame)) return;
    setDeletingReplay(true); setNotice("");
    try {
      if (replayDeletion === "all") await deleteVisualReplayFrames(apiUrl, selected.id);
      else await deleteVisualReplayFrame(apiUrl, selected.id, selectedFrame!.id);
      const result = await listVisualReplayFrames(apiUrl, selected.id);
      const ordered = orderedReplayFrames(result.items);
      setFrames(ordered); setSelectedFrame(ordered[0] ?? null);
      setNotice("Replay evidence was deleted. The advisory session and test verdict are unchanged.");
    } catch (error) { setNotice(message(error)); }
    finally { setDeletingReplay(false); setReplayDeletion(null); }
  }
  const canDeleteReplay = role === "tenant_admin";

  const visionSettings = <section className="workspace-section" aria-label="Vision settings"><h2>Vision settings</h2>{policy ? <form onSubmit={saveVisionPolicy} className="form-grid form-grid--one"><p>Provider: <code>{policy.provider}</code><br />Model: <code>{policy.model}</code><br />Limits: {policy.max_session_seconds}s, {policy.max_screenshot_bytes} bytes, ${policy.max_cost_usd} per session. Project policy sets BFS depth and total states.</p><label className="field field--checkbox"><input type="checkbox" checked={policy.enabled} onChange={(event) => setPolicy(event.target.checked ? { ...policy, enabled: true } : { ...policy, enabled: false, raw_screenshot_transfer_accepted: false })} /> Enable vision exploration</label><label className="field field--checkbox"><input type="checkbox" checked={policy.raw_screenshot_transfer_accepted} onChange={(event) => setPolicy({ ...policy, raw_screenshot_transfer_accepted: event.target.checked })} disabled={!policy.enabled} /> I understand raw screenshots for this tenant may be sent to Hugging Face.</label><div className="form-actions"><button className="button button--secondary" disabled={saving || (policy.enabled && !policy.raw_screenshot_transfer_accepted)}>{saving ? "Saving…" : "Save vision settings"}</button></div><p>Only a tenant administrator can save these settings. The server verifies authorization and consent.</p></form> : <LoadingState title="Loading vision policy" />}</section>;

  return <>
    <section className="workspace-section" aria-label="Vision exploration"><h2>Explore with the Vision Agent</h2><p>Vision is advisory only. A raw screenshot may be transferred to Hugging Face; it never decides a test result, and any resulting draft still needs human approval.</p><form onSubmit={requestExploration} className="form-grid"><label className="field">Project<select required value={projectId} onChange={(event) => setProjectId(event.target.value)}><option value="">Choose a project</option>{options.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}</select></label><label className="field">Target URL<input required type="url" value={targetUrl} onChange={(event) => setTargetUrl(event.target.value)} /></label><label className="field form-grid--full">Exploration intent<textarea required value={taskIntent} onChange={(event) => setTaskIntent(event.target.value)} /></label><label className="field field--checkbox form-grid--full"><input type="checkbox" checked={useVision} onChange={(event) => setUseVision(event.target.checked)} disabled={!enabled} /> Use Vision Agent</label>{!enabled && <p className="form-grid--full">Vision is unavailable until a tenant administrator enables it and accepts the raw-screenshot transfer disclosure.</p>}<div className="form-actions form-grid--full"><button className="button" disabled={!projectId || !enabled || !useVision}>Start advisory exploration</button></div></form></section>
    {visionSettings}
    {projectPolicy}
    {notice && <p className={`notice ${notice.includes("unavailable") || notice.includes("disabled") ? "notice--error" : ""}`} role="alert">{notice}</p>}
    <section className="workspace-section" aria-label="Visual exploration sessions"><h2>Visual exploration sessions</h2>{sessions.length ? <ul className="stack-list">{sessions.map((session) => <li key={session.id}><button type="button" className="button button--secondary" onClick={() => setSelected(session)}>View</button> <StatusBadge status={session.state} /> <code>{session.id}</code></li>)}</ul> : <EmptyState title="No visual explorations">Start one only after confirming the privacy disclosure above.</EmptyState>}</section>
    {selected && <><section className="workspace-section" aria-label="Selected visual exploration"><div className="section-heading"><h2>Advisory session</h2><StatusBadge status={selected.state} /></div><ul className="detail-list"><li>Correlation: <code>{selected.correlation_id}</code></li><li>Bounded to {selected.max_hops} hops, {selected.max_states} states, and {selected.max_session_seconds} seconds.</li><li>Stop condition: state/depth limit, time limit, policy guard, provider failure, or model stop.</li>{selected.safe_failure_reason && <li>Safe failure: {selected.safe_failure_reason}</li>}</ul>{active && <LoadingState title="Visual exploration is in progress" />}<VisionProgressTimeline apiUrl={apiUrl} sessionId={selected.id} live={active} onActivity={() => refreshSelected(selected.id)} /><h3>Visual replay</h3><p>Frames may contain target-page data. They are private evidence retained until an authorized deletion, visible only to project readers, and never change a deterministic verdict.</p>{frames.length ? <><div className="stack-list" role="list">{frames.map((frame) => <button type="button" key={frame.id} className="button button--secondary" onClick={() => setSelectedFrame(frame)}>State {frame.sequence} · {frame.checksum.slice(0, 12)} · retained</button>)}</div>{selectedFrame && <><p>State {selectedFrame.sequence}, captured {new Date(selectedFrame.captured_at).toLocaleString()}: model proposals only; these were not executed test steps.</p>{frameUrl ? <div className="vision-replay-image">{frameImageSize && selectedFrame.actions.map((item) => { const position = replayMarkerPosition(item.action, frameImageSize); return position ? <span key={item.sequence} className="vision-replay-marker" style={position}>model proposal</span> : null; })}<img src={frameUrl} alt={`Captured visual exploration state ${selectedFrame.sequence}`} onLoad={(event) => setFrameImageSize({ width: event.currentTarget.naturalWidth, height: event.currentTarget.naturalHeight })} /></div> : <LoadingState title="Loading replay frame" />}<ul className="stack-list">{selectedFrame.actions.map((action) => <SafeAction key={action.sequence} item={action} />)}</ul></>}</> : <p>No replay frame was retained for this exploration.</p>}<h3>Safe action candidates</h3>{actions.length ? <ul className="stack-list">{actions.map((action) => <SafeAction key={action.sequence} item={action} />)}</ul> : <p>No action candidate has been recorded.</p>}{draftId && <p><Link href={`/agent?draft=${encodeURIComponent(draftId)}`}>Review the resulting Playwright draft</Link></p>}<h3>Tenant-admin diagnostic evidence</h3><p>Available only to tenant administrators. Open it only when needed; do not copy sensitive content.</p><button type="button" className="button button--secondary" onClick={() => void inspectDebugEvidence()}>Inspect diagnostic evidence</button>{debugEvidence && <><p>Expires: {debugEvidence.retention_until}</p><pre>{debugEvidence.payload}</pre></>}</section></>}
    {selected && canDeleteReplay && frames.length > 0 && <section className="workspace-section" aria-label="Replay deletion"><h2>Delete replay evidence</h2><p>Only tenant administrators can permanently delete these private frames.</p>{selectedFrame && <button type="button" className="button button--danger" onClick={() => setReplayDeletion("frame")}>Delete selected frame</button>} <button type="button" className="button button--danger" onClick={() => setReplayDeletion("all")}>Delete all replay frames</button></section>}
    <ConfirmDialog open={confirming} title="Send a screenshot to Hugging Face?" description="This starts an advisory exploration. Raw screenshots may be sent to the configured Hugging Face model; no test verdict or source change occurs without the existing human review flow." confirmLabel="Start advisory exploration" onConfirm={() => void submitExploration()} onCancel={() => setConfirming(false)} />
    <ConfirmDialog open={replayDeletion !== null} title={replayDeletion === "all" ? "Delete all replay frames?" : "Delete this replay frame?"} description="This permanently removes private replay evidence. It does not change the advisory session, generated draft, or deterministic test verdict." confirmLabel="Delete replay evidence" onConfirm={() => void deleteReplay()} onCancel={() => setReplayDeletion(null)} busy={deletingReplay} />
  </>;
}
