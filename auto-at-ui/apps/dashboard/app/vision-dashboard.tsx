"use client";

import { FormEvent, type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { VisionSessionDetail } from "./components/vision-session-detail";
import { VisionProviderSettings } from "./components/vision-provider-settings";
import { hasUnsavedVisionPolicy, hasVisionConsent, screenshotDisclosure, visionConfirmation, visionFailureMessage, visionProviderLabel } from "./components/vision-provider-model";
import { getVisionProviders } from "./generation-api";
import type { VisionProvider } from "./generation-types";
import { ConfirmDialog } from "./components/confirm-dialog";
import { EmptyState, LoadingState } from "./components/states";
import { StatusBadge } from "./components/status-badge";
import { VisionProgressTimeline } from "./components/vision-progress-timeline";
import { VisionTrajectory } from "./components/vision-trajectory";
import { orderedReplayFrames, replayMarkerPosition } from "./components/vision-replay-model";
import { ControlPlaneError, deleteVisualReplayFrame, deleteVisualReplayFrames, getVisionDebugEvidence, getVisionPolicy, getVisualExploration, getVisualReplayFrameBlob, getVisualTrajectory, getVisionResult, listVisionDebugEvidence, listVisualActions, listVisualExplorations, listVisualReplayFrames, setVisionPolicy, submitVisualExploration } from "./generation-api";
import type { VisualAction, VisualExploration, VisualReplayFrame, VisualTrajectory as VisualTrajectoryData, VisionDebugEvidencePayload, VisionPolicy } from "./generation-types";
import { projects, type Project } from "./run-api";

const terminal = new Set(["completed", "unavailable", "cancelled"]);
const message = (error: unknown) => error instanceof ControlPlaneError ? visionFailureMessage(error.code) ?? error.message : "The control plane is unavailable. Try again later.";

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
  const searchParams = useSearchParams();
  const requestedSession = searchParams.get("vision");
  const [savedPolicy, setSavedPolicy] = useState<VisionPolicy | null>(null);
  const [draftPolicy, setDraftPolicy] = useState<VisionPolicy | null>(null);
  const [providers, setProviders] = useState<VisionProvider[]>([]);
  const [settingsError, setSettingsError] = useState(false);
  const [settingsRefresh, setSettingsRefresh] = useState(0);
  const [options, setOptions] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [targetUrl, setTargetUrl] = useState("");
  const [taskIntent, setTaskIntent] = useState("");
  const [useVision, setUseVision] = useState(false);
  const [sessions, setSessions] = useState<VisualExploration[]>([]);
  const [selected, setSelected] = useState<VisualExploration | null>(null);
  const [actions, setActions] = useState<VisualAction[]>([]);
  const [frames, setFrames] = useState<VisualReplayFrame[]>([]);
  const [trajectory, setTrajectory] = useState<VisualTrajectoryData | null>(null);
  const [selectedFrame, setSelectedFrame] = useState<VisualReplayFrame | null>(null);
  const [frameError, setFrameError] = useState(false);
  const [frameUrl, setFrameUrl] = useState<string | null>(null);
  const [frameImageSize, setFrameImageSize] = useState<{ width: number; height: number } | null>(null);
  const [draftId, setDraftId] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const [confirmation, setConfirmation] = useState<ReturnType<typeof visionConfirmation> | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [replayDeletion, setReplayDeletion] = useState<"frame" | "all" | null>(null);
  const [deletingReplay, setDeletingReplay] = useState(false);
  const [role, setRole] = useState<string | null>(null);
  const [debugEvidence, setDebugEvidence] = useState<VisionDebugEvidencePayload | null>(null);
  const [saving, setSaving] = useState(false);
  const contextRef = useRef("");
  contextRef.current = [apiUrl, projectId, selected?.id].join("|");
  const dirty = hasUnsavedVisionPolicy(savedPolicy, draftPolicy);
  const enabled = Boolean(!settingsError && savedPolicy?.enabled && hasVisionConsent(savedPolicy) && providers.find((item) => item.id === savedPolicy.provider)?.configured);
  const active = useMemo(() => selected !== null && !terminal.has(selected.state), [selected]);

  useEffect(() => {
    let disposed = false;
    setSettingsError(false); setSavedPolicy(null); setDraftPolicy(null); setProviders([]); setConfirmation(null);
    Promise.all([getVisionPolicy(apiUrl), getVisionProviders(apiUrl)]).then(([policy, catalogue]) => {
      if (!disposed) { setSavedPolicy(policy); setDraftPolicy(policy); setProviders(catalogue.items); }
    }).catch(() => { if (!disposed) setSettingsError(true); });
    return () => { disposed = true; };
  }, [apiUrl, settingsRefresh]);
  useEffect(() => { fetch(`${apiUrl}/api/v1/auth/me`, { credentials: "include" }).then(async (response) => response.ok ? setRole((await response.json() as { role: string }).role) : setRole(null)).catch(() => setRole(null)); }, [apiUrl]);
  useEffect(() => { projects(apiUrl).then((items) => { setOptions(items); setProjectId((current) => current || (requestedSession ? "" : items[0]?.id) || ""); }).catch((error) => setNotice(message(error))); }, [apiUrl]);
  useEffect(() => {
    let disposed = false;
    if (requestedSession) getVisualExploration(apiUrl, requestedSession).then((session) => {
      if (!disposed) { setProjectId(session.project_id); setSelected(session); }
    }).catch((error) => { if (!disposed) setNotice(message(error)); });
    return () => { disposed = true; };
  }, [apiUrl, requestedSession]);
  useEffect(() => {
    let disposed = false;
    if (!projectId) { setSessions([]); return; }
    listVisualExplorations(apiUrl, projectId).then((page) => {
      if (disposed) return;
      setSessions(page.items);
      setSelected((current) => current?.project_id === projectId ? page.items.find((item) => item.id === current.id) ?? null : page.items[0] ?? null);
    }).catch((error) => { if (!disposed) setNotice(message(error)); });
    return () => { disposed = true; };
  }, [apiUrl, projectId]);
  function refreshSelected(sessionId: string) {
    const expectedContext = contextRef.current;
    void Promise.all([getVisualExploration(apiUrl, sessionId), listVisualActions(apiUrl, sessionId), getVisualTrajectory(apiUrl, sessionId), getVisionResult(apiUrl, sessionId)])
      .then(([session, nextActions, nextTrajectory, result]) => {
        if (contextRef.current !== expectedContext) return;
        setSelected((current) => {
          if (current?.id !== sessionId) return current;
          return current.state === session.state
            && current.safe_failure_reason === session.safe_failure_reason ? current : session;
        });
        setSessions((current) => current.map((item) => item.id === sessionId ? session : item));
        setActions(nextActions);
        setTrajectory(nextTrajectory);
        setDraftId(result.links.draft.id);
      }).catch((error) => setNotice(message(error)));
  }
  useEffect(() => {
    if (!selected) { setActions([]); setTrajectory(null); setDraftId(null); return; }
    refreshSelected(selected.id);
  }, [apiUrl, selected?.id]);
  useEffect(() => {
    if (!selected) { setFrames([]); setSelectedFrame(null); return; }
    let disposed = false;
    listVisualReplayFrames(apiUrl, selected.id).then((result) => {
      if (disposed) return;
      const ordered = orderedReplayFrames(result.items);
      setFrames(ordered);
      setSelectedFrame((current) => ordered.find((item) => item.id === current?.id) ?? ordered[0] ?? null);
    }).catch((error) => { if (!disposed) setNotice(message(error)); });
    return () => { disposed = true; };
  }, [apiUrl, selected?.id]);
  useEffect(() => {
    let active = true;
    setFrameImageSize(null); setFrameError(false);
    setFrameUrl((current) => { if (current) URL.revokeObjectURL(current); return null; });
    if (!selected || !selectedFrame) return;
    getVisualReplayFrameBlob(apiUrl, selected.id, selectedFrame.id).then((blob) => {
      if (!active) return;
      const next = URL.createObjectURL(blob);
      setFrameUrl((current) => { if (current) URL.revokeObjectURL(current); return next; });
    }).catch((error) => { if (active) { setFrameError(true); setNotice(message(error)); } });
    return () => { active = false; setFrameUrl((current) => { if (current) URL.revokeObjectURL(current); return null; }); };
  }, [apiUrl, selected?.id, selectedFrame?.id]);

  async function saveVisionPolicy(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!draftPolicy || role !== "tenant_admin" || saving) return;
    setSaving(true); setNotice("");
    try { const saved = await setVisionPolicy(apiUrl, draftPolicy); setSavedPolicy(saved); setDraftPolicy(saved); setNotice("Vision policy saved by the control plane."); }
    catch (error) { setNotice(message(error)); }
    finally { setSaving(false); }
  }
  function requestExploration(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setNotice("");
    if (dirty || saving) { setNotice("Save or discard your Vision settings changes before starting an exploration."); return; }
    if (!enabled || !useVision) { setNotice("Vision exploration is disabled by tenant policy."); return; }
    if (savedPolicy) setConfirmation(visionConfirmation(savedPolicy));
  }
  async function submitExploration() {
    if (!confirmation || submitting || dirty || saving) return;
    const snapshot = confirmation;
    setSubmitting(true);
    try {
      const session = await submitVisualExploration(apiUrl, { project_id: projectId, target_url: targetUrl, task_intent: taskIntent, use_vision: true, ...snapshot });
      setSessions((current) => [session, ...current.filter((item) => item.id !== session.id)]); setSelected(session); setNotice("Visual exploration queued. It is advisory and cannot change a test verdict.");
      const url = new URL(window.location.href);
      url.searchParams.set("vision", session.id);
      window.history.replaceState(null, "", url);
    } catch (error) {
      if (error instanceof ControlPlaneError && error.status === 409 && error.code === "vision_policy_changed") {
        setSettingsRefresh((value) => value + 1); setUseVision(false);
      }
      setNotice(message(error));
    } finally { setConfirmation(null); setSubmitting(false); }
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

  const visionSettings = <section className="workspace-section" aria-label="Vision settings"><h2>Vision settings</h2>{settingsError
    ? <><p role="alert">Vision settings could not be loaded.</p><button type="button" className="button button--secondary" onClick={() => setSettingsRefresh((value) => value + 1)}>Retry Vision settings</button></>
    : draftPolicy ? <VisionProviderSettings policy={draftPolicy} providers={providers} canManage={role === "tenant_admin"} saving={saving || submitting || confirmation !== null} dirty={dirty} onChange={setDraftPolicy} onSave={saveVisionPolicy} onDiscard={() => setDraftPolicy(savedPolicy)} />
    : <LoadingState title="Loading vision policy" />}</section>;

  return <>
    <section className="workspace-section" aria-label="Vision exploration">
      <h2>Start a new Vision exploration</h2>
      <p>Choose a target and describe what to explore. Previous sessions remain available below.</p>
      <form onSubmit={requestExploration} className="form-grid">
        <label className="field">Project<select required value={projectId} onChange={(event) => setProjectId(event.target.value)}><option value="">Choose a project</option>{options.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}</select></label>
        <label className="field">Target URL<input required type="url" value={targetUrl} onChange={(event) => setTargetUrl(event.target.value)} /></label>
        <label className="field form-grid--full">Exploration intent<textarea required value={taskIntent} onChange={(event) => setTaskIntent(event.target.value)} /></label>
        <label className="field field--checkbox form-grid--full"><input type="checkbox" checked={useVision} onChange={(event) => setUseVision(event.target.checked)} disabled={!enabled} /> Use Vision Agent</label>
        {!enabled && <p className="form-grid--full">Vision is unavailable until a tenant administrator enables it and accepts the raw-screenshot transfer disclosure in Vision settings below.</p>}
        <div className="form-actions form-grid--full"><button className="button" disabled={!projectId || !enabled || !useVision || dirty || saving || submitting}>Start advisory exploration</button></div>
      </form>
      {dirty && <p role="status">Save or discard your Vision settings changes before starting an exploration.</p>}
      {savedPolicy && <p>{screenshotDisclosure(savedPolicy.provider)} Any resulting test draft requires your approval before execution.</p>}
    </section>
    {notice && <p className={`notice ${notice.includes("unavailable") || notice.includes("disabled") ? "notice--error" : ""}`} role="alert">{notice}</p>}
    <details className="workspace-section"><summary>Vision settings</summary>{visionSettings}</details>
    {selected && <VisionSessionDetail key={`${apiUrl}:${projectId}:${selected.id}`} apiUrl={apiUrl} session={selected} canDelete={canDeleteReplay} />}
    {selected?.trace_version === "v4" && <VisionProgressTimeline apiUrl={apiUrl} sessionId={selected.id} live={active} onActivity={() => refreshSelected(selected.id)} />}
    {selected && selected.trace_version !== "v4" && trajectory && <section className="workspace-section" aria-label="Exploration evidence"><VisionTrajectory apiUrl={apiUrl} sessionId={selected.id} trajectory={trajectory} frames={frames} selectedFrame={selectedFrame} onSelectFrame={setSelectedFrame} /></section>}
    {projectPolicy}
    <section className="workspace-section" aria-label="Visual exploration sessions"><h2>Visual exploration sessions</h2>{sessions.length ? <ul className="stack-list">{sessions.map((session) => <li key={session.id}><button type="button" className="button button--secondary" onClick={() => { setSelected(session); const url = new URL(window.location.href); url.searchParams.set("vision", session.id); window.history.replaceState(null, "", url); }}>View</button> <StatusBadge status={session.state} /> <code>{session.id}</code></li>)}</ul> : <EmptyState title="No visual explorations">Start one only after confirming the privacy disclosure above.</EmptyState>}</section>
    {selected && selected.trace_version !== "v4" && <><section className="workspace-section" aria-label="Selected visual exploration"><div className="section-heading"><h2>Advisory session</h2><StatusBadge status={selected.state} /></div><ul className="detail-list"><li>Correlation: <code>{selected.correlation_id}</code></li><li>Bounded to {selected.max_hops} hops, {selected.max_states} states, and {selected.max_session_seconds} seconds.</li><li>Stop condition: state/depth limit, time limit, policy guard, provider failure, or model stop.</li>{selected.safe_failure_reason && <li>Safe failure: {selected.safe_failure_reason}</li>}</ul>{active && <LoadingState title="Visual exploration is in progress" />}<VisionProgressTimeline apiUrl={apiUrl} sessionId={selected.id} live={active} onActivity={() => refreshSelected(selected.id)} /><h3>Visual replay</h3><p>Frames may contain target-page data. They are private evidence retained until an authorized deletion, visible only to project readers, and never change a deterministic verdict.</p>{frames.length ? <><div className="stack-list" role="list">{frames.map((frame) => <button type="button" key={frame.id} className="button button--secondary" onClick={() => setSelectedFrame(frame)}>State {frame.sequence} · {frame.checksum.slice(0, 12)} · retained</button>)}</div>{selectedFrame && <><p>State {selectedFrame.sequence}, captured {new Date(selectedFrame.captured_at).toLocaleString()}: model proposals only; these were not executed test steps.</p>{frameUrl ? <div className="vision-replay-image">{frameImageSize && selectedFrame.actions.map((item) => { const position = replayMarkerPosition(item.action, frameImageSize); return position ? <span key={item.sequence} className="vision-replay-marker" style={position}>model proposal</span> : null; })}<img src={frameUrl} alt={`Captured visual exploration state ${selectedFrame.sequence}`} onLoad={(event) => setFrameImageSize({ width: event.currentTarget.naturalWidth, height: event.currentTarget.naturalHeight })} /></div> : frameError ? <p role="status">Replay frame unavailable.</p> : <LoadingState title="Loading replay frame" />}<ul className="stack-list">{selectedFrame.actions.map((action) => <SafeAction key={action.sequence} item={action} />)}</ul></>}</> : <p>No replay frame was retained for this exploration.</p>}<h3>Safe action candidates</h3>{actions.length ? <ul className="stack-list">{actions.map((action) => <SafeAction key={action.sequence} item={action} />)}</ul> : <p>No action candidate has been recorded.</p>}{draftId && <p><Link href={`/agent?draft=${encodeURIComponent(draftId)}`}>Review the resulting Playwright draft</Link></p>}<h3>Tenant-admin diagnostic evidence</h3><p>Available only to tenant administrators. Open it only when needed; do not copy sensitive content.</p><button type="button" className="button button--secondary" onClick={() => void inspectDebugEvidence()}>Inspect diagnostic evidence</button>{debugEvidence && <><p>Expires: {debugEvidence.retention_until}</p><pre>{debugEvidence.payload}</pre></>}</section></>}
    {selected && canDeleteReplay && frames.length > 0 && <section className="workspace-section" aria-label="Replay deletion"><h2>Delete replay evidence</h2><p>Only tenant administrators can permanently delete these private frames.</p>{selectedFrame && <button type="button" className="button button--danger" onClick={() => setReplayDeletion("frame")}>Delete selected frame</button>} <button type="button" className="button button--danger" onClick={() => setReplayDeletion("all")}>Delete all replay frames</button></section>}
    <ConfirmDialog open={confirmation !== null} title={`Send screenshots to ${visionProviderLabel(confirmation?.expected_provider ?? "")}?`} description={`${screenshotDisclosure(confirmation?.expected_provider ?? "")} Model: ${confirmation?.expected_model ?? ""}. This starts an advisory exploration; any resulting test draft requires approval before execution.`} confirmLabel="Start advisory exploration" onConfirm={() => void submitExploration()} onCancel={() => setConfirmation(null)} busy={submitting} />
    <ConfirmDialog open={replayDeletion !== null} title={replayDeletion === "all" ? "Delete all replay frames?" : "Delete this replay frame?"} description="This permanently removes private replay evidence. It does not change the advisory session, generated draft, or deterministic test verdict." confirmLabel="Delete replay evidence" onConfirm={() => void deleteReplay()} onCancel={() => setReplayDeletion(null)} busy={deletingReplay} />
  </>;
}
