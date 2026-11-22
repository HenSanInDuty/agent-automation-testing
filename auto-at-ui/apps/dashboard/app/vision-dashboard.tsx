"use client";

import { FormEvent, type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { History, Plus, RotateCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { Code, CodeBlock, Disclosure, FormField, Hint, ItemList, Notice } from "./components/agent-ui";
import { Section } from "./components/section";
import { VisionSessionDetail } from "./components/vision-session-detail";
import { VisionProviderSettings } from "./components/vision-provider-settings";
import { hasUnsavedVisionPolicy, hasVisionConsent, visionDisclosure, visionConfirmation, visionFailureMessage, visionProviderLabel } from "./components/vision-provider-model";
import { getVisionProviders, reloadVisualExploration } from "./generation-api";
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
type ExplorationConfirmation = ReturnType<typeof visionConfirmation> & { disclosure: string } & (
  | { kind: "new"; request: { project_id: string; target_url: string; task_intent: string } }
  | { kind: "reload"; sessionId: string }
);
const message = (error: unknown) => error instanceof ControlPlaneError ? visionFailureMessage(error.code) ?? error.message : "The control plane is unavailable. Try again later.";

function SafeAction({ item }: { item: VisualAction }) {
  const action = item.action;
  const detail = [
    typeof action.confidence === "number" ? `confidence ${action.confidence}` : null,
    typeof action.x === "number" && typeof action.y === "number" ? `position ${action.x}, ${action.y}` : null,
    typeof action.delta_y === "number" ? `scroll ${action.delta_y}` : null,
    typeof action.duration_ms === "number" ? `wait ${action.duration_ms}ms` : null,
  ].filter(Boolean).join(" · ");
  return <li className="rounded-lg border bg-muted/30 px-3 py-2 text-sm"><strong className="font-medium">{item.sequence}. {action.kind}</strong>{detail && ` — ${detail}`}{item.evidence_checksum && <><br /><span className="text-xs text-muted-foreground">Screenshot checksum: </span><Code>{item.evidence_checksum}</Code></>}</li>;
}

export function VisionDashboard({ apiUrl, projectPolicy, onProjectChange }: { apiUrl: string; projectPolicy?: ReactNode; onProjectChange?: (projectId: string) => void }) {
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
  const [confirmation, setConfirmation] = useState<ExplorationConfirmation | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [replayDeletion, setReplayDeletion] = useState<"frame" | "all" | null>(null);
  const [deletingReplay, setDeletingReplay] = useState(false);
  const [role, setRole] = useState<string | null>(null);
  const [debugEvidence, setDebugEvidence] = useState<VisionDebugEvidencePayload | null>(null);
  const [saving, setSaving] = useState(false);
  const [newOpen, setNewOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const settingsRef = useRef<HTMLDetailsElement>(null);
  const historyRef = useRef<HTMLDetailsElement>(null);
  const contextRef = useRef("");
  const refreshing = useRef<string | null>(null);
  contextRef.current = [apiUrl, projectId, selected?.id].join("|");
  const dirty = hasUnsavedVisionPolicy(savedPolicy, draftPolicy);
  const enabled = Boolean(!settingsError && savedPolicy?.enabled && hasVisionConsent(savedPolicy) && (savedPolicy.provider !== "codex_cli" || savedPolicy.input_policy_fingerprint) && providers.find((item) => item.id === savedPolicy.provider)?.configured);
  const active = useMemo(() => selected !== null && !terminal.has(selected.state), [selected]);
  useEffect(() => { onProjectChange?.(projectId); }, [projectId, onProjectChange]);

  useEffect(() => {
    let disposed = false;
    setSettingsError(false); setSavedPolicy(null); setDraftPolicy(null); setProviders([]); setConfirmation(null);
    Promise.all([getVisionPolicy(apiUrl), getVisionProviders(apiUrl)]).then(([policy, catalogue]) => {
      if (!disposed) { setSavedPolicy(policy); setDraftPolicy(policy); setProviders(catalogue.items); }
    }).catch(() => { if (!disposed) setSettingsError(true); });
    return () => { disposed = true; };
  }, [apiUrl, settingsRefresh]);
  useEffect(() => {
    if (draftPolicy?.provider !== "codex_cli") return;
    let disposed = false;
    const timer = setInterval(() => {
      void getVisionProviders(apiUrl).then((catalogue) => { if (!disposed) setProviders(catalogue.items); }).catch(() => {
        if (!disposed) setProviders((items) => items.map((item) => item.id === "codex_cli" ? { ...item, configured: false, bridge_readiness: null } : item));
      });
    }, 5000);
    return () => { disposed = true; clearInterval(timer); };
  }, [apiUrl, draftPolicy?.provider]);
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
      setSelected((current) => current?.project_id === projectId ? page.items.find((item) => item.id === current.id) ?? current : page.items[0] ?? null);
    }).catch((error) => { if (!disposed) setNotice(message(error)); });
    return () => { disposed = true; };
  }, [apiUrl, projectId]);
  function refreshSelected(sessionId: string) {
    const expectedContext = contextRef.current;
    if (refreshing.current === expectedContext) return;
    refreshing.current = expectedContext;
    void Promise.allSettled([getVisualExploration(apiUrl, sessionId), listVisualActions(apiUrl, sessionId), getVisualTrajectory(apiUrl, sessionId), getVisionResult(apiUrl, sessionId)])
      .then(([sessionResult, nextActions, nextTrajectory, result]) => {
        if (contextRef.current !== expectedContext) return;
        if (sessionResult.status !== "fulfilled") { setNotice(message(sessionResult.reason)); return; }
        const session = sessionResult.value;
        setSelected((current) => {
          if (current?.id !== sessionId) return current;
          return current.state === session.state
            && current.safe_failure_reason === session.safe_failure_reason ? current : session;
        });
        setSessions((current) => current.map((item) => item.id === sessionId ? session : item));
        if (nextActions.status === "fulfilled") setActions(nextActions.value);
        if (nextTrajectory.status === "fulfilled") setTrajectory(nextTrajectory.value);
        if (result.status === "fulfilled") setDraftId(result.value.links.draft.id);
      }).finally(() => { if (refreshing.current === expectedContext) refreshing.current = null; });
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
    if (!enabled) { setNotice("Vision exploration is disabled by tenant policy."); return; }
    if (savedPolicy) setConfirmation({ ...visionConfirmation(savedPolicy), disclosure: visionDisclosure(savedPolicy), kind: "new", request: { project_id: projectId, target_url: targetUrl, task_intent: taskIntent } });
  }
  function requestReload() {
    if (!selected || active || !enabled || dirty || saving || submitting || !savedPolicy) return;
    setNotice("");
    setConfirmation({ ...visionConfirmation(savedPolicy), disclosure: visionDisclosure(savedPolicy), kind: "reload", sessionId: selected.id });
  }
  async function submitExploration() {
    if (!confirmation || submitting || dirty || saving) return;
    const snapshot = confirmation;
    setSubmitting(true);
    try {
      const provider = { expected_provider: snapshot.expected_provider, expected_model: snapshot.expected_model, ...(snapshot.expected_input_policy_fingerprint ? { expected_input_policy_fingerprint: snapshot.expected_input_policy_fingerprint } : {}) };
      const session = snapshot.kind === "reload"
        ? await reloadVisualExploration(apiUrl, snapshot.sessionId, provider)
        : await submitVisualExploration(apiUrl, { ...snapshot.request, use_vision: true, ...provider });
      setSessions((current) => [session, ...current.filter((item) => item.id !== session.id)]); setSelected(session); setNewOpen(false); setNotice("Visual exploration queued.");
      const url = new URL(window.location.href);
      url.searchParams.set("vision", session.id);
      window.history.replaceState(null, "", url);
    } catch (error) {
      if (error instanceof ControlPlaneError && error.status === 409 && error.code === "vision_policy_changed") {
        setSettingsRefresh((value) => value + 1);
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

  const visionSettings = <section aria-label="Vision settings"><h2 className="sr-only">Vision settings</h2>{settingsError
    ? <div className="grid justify-items-start gap-3"><Notice tone="danger" role="alert" className="w-full">Vision settings could not be loaded.</Notice><Button type="button" variant="outline" size="sm" onClick={() => setSettingsRefresh((value) => value + 1)}>Retry Vision settings</Button></div>
    : draftPolicy ? <VisionProviderSettings policy={draftPolicy} providers={providers} canManage={role === "tenant_admin"} saving={saving || submitting || confirmation !== null} dirty={dirty} onChange={setDraftPolicy} onSave={saveVisionPolicy} onDiscard={() => setDraftPolicy(savedPolicy)} />
    : <LoadingState title="Loading vision policy" />}</section>;
  const showHistory = (session: VisualExploration) => { setSelected(session); setNewOpen(false); setHistoryOpen(false); const url = new URL(window.location.href); url.searchParams.set("vision", session.id); window.history.replaceState(null, "", url); };
  const noticeTone = notice.includes("unavailable") || notice.includes("disabled") ? "danger" : notice.includes("saved") || notice.includes("queued") || notice.includes("deleted") ? "success" : "info";

  return <div className="grid min-w-0 gap-6 [overflow-wrap:anywhere]">
    {selected && <div role="group" className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 rounded-xl border bg-card px-4 py-2.5 shadow-xs" aria-label="Session controls">
      <div className="flex min-w-0 items-center gap-2.5"><strong className="truncate text-sm font-semibold">{options.find((project) => project.id === selected.project_id)?.name ?? "Website exploration"}</strong> <StatusBadge status={selected.state} /></div>
      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="outline" size="sm" aria-expanded={historyOpen} onClick={() => { setHistoryOpen(true); historyRef.current?.scrollIntoView({ block: "nearest" }); }}><History aria-hidden="true" />History</Button>
        <Button type="button" variant="outline" size="sm" aria-expanded={newOpen} aria-controls="vision-new" onClick={() => setNewOpen((open) => !open)}><Plus aria-hidden="true" />New exploration</Button>
        <Button type="button" variant="outline" size="sm" onClick={requestReload} disabled={active || !enabled || dirty || saving || submitting || confirmation !== null}><RotateCw aria-hidden="true" />Reload</Button>
      </div>
    </div>}
    <Section id="vision-new" hidden={Boolean(selected) && !newOpen} aria-label="Vision exploration" title="Start a new Vision exploration" description="Choose a target and describe what to explore. Previous sessions remain available below." contentClassName="grid gap-4">
      <form onSubmit={requestExploration} className="grid gap-4 min-[720px]:grid-cols-2">
        <FormField id="vision-project" label="Project"><NativeSelect id="vision-project" required value={projectId} onChange={(event) => setProjectId(event.target.value)}><option value="">Choose a project</option>{options.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}</NativeSelect></FormField>
        <FormField id="vision-target-url" label="Target URL"><Input id="vision-target-url" required type="url" placeholder="https://example.com" value={targetUrl} onChange={(event) => setTargetUrl(event.target.value)} /></FormField>
        <FormField id="vision-intent" label="Exploration intent" className="min-[720px]:col-span-2"><Textarea id="vision-intent" required className="min-h-24" value={taskIntent} onChange={(event) => setTaskIntent(event.target.value)} /></FormField>
        {!enabled && <Notice tone="warning" className="min-[720px]:col-span-2">Vision is unavailable until a tenant administrator enables an available provider and accepts its required data-transfer disclosure in Vision settings below.</Notice>}
        <div className="min-[720px]:col-span-2"><Button disabled={!projectId || !enabled || dirty || saving || submitting}>Start advisory exploration</Button></div>
      </form>
      {dirty && <Notice tone="info" role="status">Save or discard your Vision settings changes before starting an exploration.</Notice>}
      {savedPolicy && <Hint>{visionDisclosure(savedPolicy)} Any resulting test draft requires your approval before execution.</Hint>}
    </Section>
    {notice && <Notice tone={noticeTone} role="alert">{notice}</Notice>}
    {selected && <VisionSessionDetail key={`${apiUrl}:${projectId}:${selected.id}`} apiUrl={apiUrl} session={selected} canDelete={canDeleteReplay} onActivity={() => refreshSelected(selected.id)} />}
    {selected && selected.trace_version !== "v4" && trajectory && <Section aria-label="Exploration evidence"><VisionTrajectory apiUrl={apiUrl} sessionId={selected.id} trajectory={trajectory} frames={frames} selectedFrame={selectedFrame} onSelectFrame={setSelectedFrame} /></Section>}
    {(!enabled || dirty || settingsError) && <Notice tone="info" role="status" className="flex flex-wrap items-center justify-between gap-3 text-muted-foreground">
      <span>{dirty ? "Save or discard your settings changes before starting a session." : settingsError ? "Vision settings could not be loaded." : "Starting a session requires an available provider, enabled Vision settings and its required transfer consent."}</span>
      <Button type="button" variant="outline" size="sm" onClick={() => { if (settingsRef.current) { settingsRef.current.open = true; settingsRef.current.scrollIntoView({ block: "nearest" }); } }}>Open settings</Button>
    </Notice>}
    <Disclosure ref={settingsRef} title="Vision settings">{visionSettings}</Disclosure>
    <Disclosure title="Project settings" bodyClassName="p-0">{projectPolicy}</Disclosure>
    <Disclosure ref={historyRef} open={historyOpen} onToggle={(event) => setHistoryOpen(event.currentTarget.open)} title="Session history">
      <section aria-label="Visual exploration sessions" className="grid gap-3"><h2 className="text-sm font-semibold">Visual exploration sessions</h2>{sessions.length ? <ul className="grid gap-2">{sessions.map((session, index) => <li key={session.id} className={cn("flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border px-3 py-2", session.id === selected?.id && "border-primary/40 bg-accent/50")}><Button type="button" variant="outline" size="sm" onClick={() => showHistory(session)}>View</Button> <span className="text-sm font-medium">Exploration {sessions.length - index}</span> <StatusBadge status={session.state} /> <Disclosure variant="plain" title="Session ID" className="ml-auto"><Code>{session.id}</Code></Disclosure></li>)}</ul> : <EmptyState title="No visual explorations">Start one only after confirming the privacy disclosure above.</EmptyState>}</section>
    </Disclosure>
    {selected && selected.trace_version !== "v4" && <Section aria-label="Selected visual exploration" title="Advisory session" actions={<StatusBadge status={selected.state} />} contentClassName="grid gap-5">
      <ItemList className="text-muted-foreground"><li>Correlation: <Code>{selected.correlation_id}</Code></li><li>Bounded to {selected.max_hops} hops, {selected.max_states} states, and {selected.max_session_seconds} seconds.</li><li>Stop condition: state/depth limit, time limit, policy guard, provider failure, or model stop.</li>{selected.safe_failure_reason && <li>Safe failure: {selected.safe_failure_reason}</li>}</ItemList>
      {active && <LoadingState title="Visual exploration is in progress" />}
      <VisionProgressTimeline apiUrl={apiUrl} sessionId={selected.id} live={active} onActivity={() => refreshSelected(selected.id)} />
      <h3 className="text-sm font-semibold">Visual replay</h3>
      <Hint>Frames may contain target-page data. They are private evidence retained until an authorized deletion, visible only to project readers, and never change a deterministic verdict.</Hint>
      {frames.length ? <>
        <div className="flex flex-wrap gap-2" role="list">{frames.map((frame) => <Button type="button" key={frame.id} variant={frame.id === selectedFrame?.id ? "secondary" : "outline"} size="sm" onClick={() => setSelectedFrame(frame)}>State {frame.sequence} · {frame.checksum.slice(0, 12)} · retained</Button>)}</div>
        {selectedFrame && <>
          <Hint>State {selectedFrame.sequence}, captured {new Date(selectedFrame.captured_at).toLocaleString()}: model proposals only; these were not executed test steps.</Hint>
          {frameUrl ? <div className="relative inline-block max-w-full justify-self-start overflow-hidden rounded-lg border bg-muted/40">{frameImageSize && selectedFrame.actions.map((item) => { const position = replayMarkerPosition(item.action, frameImageSize); return position ? <span key={item.sequence} className="pointer-events-none absolute z-[1] -translate-x-1/2 -translate-y-1/2 rounded-sm border-2 border-[#f4c542] bg-black/70 px-1.5 py-0.5 text-[11px] text-white" style={position}>model proposal</span> : null; })}<img className="block h-auto max-w-full" src={frameUrl} alt={`Captured visual exploration state ${selectedFrame.sequence}`} onLoad={(event) => setFrameImageSize({ width: event.currentTarget.naturalWidth, height: event.currentTarget.naturalHeight })} /></div> : frameError ? <Notice tone="warning" role="status">Replay frame unavailable.</Notice> : <LoadingState title="Loading replay frame" />}
          <ItemList>{selectedFrame.actions.map((action) => <SafeAction key={action.sequence} item={action} />)}</ItemList>
        </>}
      </> : <Hint>No replay frame was retained for this exploration.</Hint>}
      <h3 className="text-sm font-semibold">Safe action candidates</h3>
      {actions.length ? <ItemList>{actions.map((action) => <SafeAction key={action.sequence} item={action} />)}</ItemList> : <Hint>No action candidate has been recorded.</Hint>}
      {draftId && <p><Link className="text-sm font-medium text-primary underline-offset-4 hover:underline" href={`/agent?draft=${encodeURIComponent(draftId)}`}>Review the resulting Playwright draft</Link></p>}
      <h3 className="text-sm font-semibold">Tenant-admin diagnostic evidence</h3>
      <Hint>Available only to tenant administrators. Open it only when needed; do not copy sensitive content.</Hint>
      <div><Button type="button" variant="outline" size="sm" onClick={() => void inspectDebugEvidence()}>Inspect diagnostic evidence</Button></div>
      {debugEvidence && <><Hint>Expires: {debugEvidence.retention_until}</Hint><CodeBlock label="Diagnostic evidence">{debugEvidence.payload}</CodeBlock></>}
    </Section>}
    {selected && canDeleteReplay && frames.length > 0 && <Section aria-label="Replay deletion" title="Delete replay evidence" description="Only tenant administrators can permanently delete these private frames." contentClassName="flex flex-wrap gap-2">{selectedFrame && <Button type="button" variant="destructive" size="sm" onClick={() => setReplayDeletion("frame")}>Delete selected frame</Button>} <Button type="button" variant="destructive" size="sm" onClick={() => setReplayDeletion("all")}>Delete all replay frames</Button></Section>}
    <ConfirmDialog open={confirmation !== null} title={confirmation?.expected_provider === "codex_cli" ? "Send page elements to OpenAI?" : `Send screenshots to ${visionProviderLabel(confirmation?.expected_provider ?? "")}?`} description={`${confirmation?.disclosure ?? ""} Model: ${confirmation?.expected_model ?? ""}. ${confirmation?.kind === "reload" ? "Reload starts a new session with the saved target and intent; the previous session stays in history." : "This starts an advisory exploration."} Any resulting test draft requires approval before execution.`} confirmLabel={confirmation?.kind === "reload" ? "Start new session" : "Start advisory exploration"} onConfirm={() => void submitExploration()} onCancel={() => setConfirmation(null)} busy={submitting} />
    <ConfirmDialog open={replayDeletion !== null} title={replayDeletion === "all" ? "Delete all replay frames?" : "Delete this replay frame?"} description="This permanently removes private replay evidence. It does not change the advisory session, generated draft, or deterministic test verdict." confirmLabel="Delete replay evidence" onConfirm={() => void deleteReplay()} onCancel={() => setReplayDeletion(null)} busy={deletingReplay} />
  </div>;
}
