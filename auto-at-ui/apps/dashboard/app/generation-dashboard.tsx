"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { CodeBlock } from "./components/code-block";
import { ConfirmDialog } from "./components/confirm-dialog";
import { ActivityTimeline } from "./components/activity-timeline";
import { PageHeader } from "./components/page-header";
import { EmptyState, LoadingState } from "./components/states";
import { StatusBadge } from "./components/status-badge";
import { VisionDashboard } from "./vision-dashboard";
import { ControlPlaneError, decideDraft, getArtifacts, getDraft, getGenerationRequest, getPolicy, getRun, setPolicy, submitGeneration } from "./generation-api";
import { shouldPollGeneration } from "./generation-polling";
import type { Artifact, GeneratedDraft, GenerationRequest, Run } from "./generation-types";
import { projects, type Project } from "./run-api";

function errorMessage(error: unknown) { return error instanceof ControlPlaneError ? error.message : "The control plane is unavailable. Try again later."; }

export function GenerationDashboard({ apiUrl }: { apiUrl: string }) {
  const searchParams = useSearchParams();
  const draftId = searchParams.get("draft");
  const [projectId, setProjectId] = useState("");
  const [projectOptions, setProjectOptions] = useState<Project[]>([]);
  const [targetUrl, setTargetUrl] = useState("");
  const [naturalRequest, setNaturalRequest] = useState("");
  const [origins, setOrigins] = useState("");
  const [savedOrigins, setSavedOrigins] = useState<string[]>([]);
  const [visionMaxHops, setVisionMaxHops] = useState(5);
  const [visionMaxStates, setVisionMaxStates] = useState(50);
  const [generation, setGeneration] = useState<GenerationRequest | null>(null);
  const [draft, setDraft] = useState<GeneratedDraft | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [reason, setReason] = useState("");
  const [notice, setNotice] = useState("");
  const [decision, setDecision] = useState<boolean | null>(null);
  const [isDeciding, setIsDeciding] = useState(false);
  const [activeTab, setActiveTab] = useState<"generation" | "vision">("generation");
  const canDecide = useMemo(() => draft?.state === "pending_review", [draft]);

  useEffect(() => {
    projects(apiUrl).then((next) => { setProjectOptions(next); setProjectId((current) => current || next[0]?.id || ""); }).catch((error) => setNotice(errorMessage(error)));
  }, [apiUrl]);

  useEffect(() => {
    if (!draftId || draft?.id === draftId) return;
    getDraft(apiUrl, draftId).then(setDraft).catch((error) => setNotice(errorMessage(error)));
  }, [apiUrl, draft?.id, draftId]);

  useEffect(() => {
    if (!draftId || !draft || generation?.id === draft.planning_request_id) return;
    getGenerationRequest(apiUrl, draft.planning_request_id)
      .then((request) => {
        setGeneration(request);
        setProjectId(request.project_id);
        setTargetUrl(request.target_url);
        setNaturalRequest(request.redacted_request);
      })
      .catch((error) => setNotice(errorMessage(error)));
  }, [apiUrl, draft, draftId, generation?.id]);

  useEffect(() => {
    if (!projectId) { setOrigins(""); setSavedOrigins([]); setVisionMaxHops(5); setVisionMaxStates(50); return; }
    getPolicy(apiUrl, projectId).then((policy) => {
      setSavedOrigins(policy.allowed_origins);
      setOrigins(policy.allowed_origins.join(", "));
      setVisionMaxHops(policy.vision_max_hops);
      setVisionMaxStates(policy.vision_max_states);
    }).catch((error) => setNotice(errorMessage(error)));
  }, [apiUrl, projectId]);

  useEffect(() => {
    if (!generation || !shouldPollGeneration(generation.state)) return;
    const timer = window.setInterval(async () => {
      try { setGeneration(await getGenerationRequest(apiUrl, generation.id)); }
      catch (error) { setNotice(errorMessage(error)); }
    }, 2000);
    return () => window.clearInterval(timer);
  }, [apiUrl, generation]);

  useEffect(() => {
    if (!generation?.draft_id || draft?.id === generation.draft_id) return;
    getDraft(apiUrl, generation.draft_id).then(setDraft).catch((error) => setNotice(errorMessage(error)));
  }, [apiUrl, draft?.id, generation?.draft_id]);

  useEffect(() => {
    if (!draft?.linked_run_id) return;
    Promise.all([getRun(apiUrl, draft.linked_run_id), getArtifacts(apiUrl, draft.linked_run_id)])
      .then(([nextRun, nextArtifacts]) => { setRun(nextRun); setArtifacts(nextArtifacts); })
      .catch((error) => setNotice(errorMessage(error)));
  }, [apiUrl, draft?.linked_run_id]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setNotice(""); setDraft(null); setRun(null); setArtifacts([]);
    try { setGeneration(await submitGeneration(apiUrl, { project_id: projectId, target_url: targetUrl, request: naturalRequest })); }
    catch (error) { setNotice(errorMessage(error)); }
  }
  async function decide(approved: boolean) {
    if (!draft) return;
    setIsDeciding(true);
    try { const next = await decideDraft(apiUrl, draft.id, approved, reason); setDraft(next); setNotice(next.preflight_repair_request_id ? (next.preflight_message ?? "Generated source failed while preparing execution. A revised draft is being created for review.") : approved ? "Draft approved. The control plane created one deterministic run." : "Draft rejected. This final decision is immutable."); setDecision(null); }
    catch (error) { setNotice(errorMessage(error)); }
    finally { setIsDeciding(false); }
  }
  async function savePolicy(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try { const policy = await setPolicy(apiUrl, projectId, { allowed_origins: origins.split(/\s|,/).filter(Boolean), vision_max_hops: visionMaxHops, vision_max_states: visionMaxStates }); setSavedOrigins(policy.allowed_origins); setOrigins(policy.allowed_origins.join(", ")); setVisionMaxHops(policy.vision_max_hops); setVisionMaxStates(policy.vision_max_states); setNotice(`Project policy saved: ${policy.allowed_origins.join(", ")}`); }
    catch (error) { setNotice(errorMessage(error)); }
  }
  const renderProjectPolicy = (showVisionLimits: boolean) => <section className="workspace-section"><h2>Project policy</h2><p>Only project administrators can save the origin allowlist{showVisionLimits ? " and Vision tree bounds" : ""}.</p><form onSubmit={savePolicy} className="form-grid form-grid--one"><label className="field">Allowed origins <input required placeholder="https://example.com or *" value={origins} onChange={(e) => setOrigins(e.target.value)} /></label><p><code>*</code> permits this project to access every HTTP(S) website. Use it only when that broad browser access is intended.</p>{showVisionLimits && <><label className="field">Vision maximum hops <input required type="number" min="1" max="10" value={visionMaxHops} onChange={(e) => setVisionMaxHops(Number(e.target.value))} /></label><label className="field">Vision maximum states <input required type="number" min="1" max="200" value={visionMaxStates} onChange={(e) => setVisionMaxStates(Number(e.target.value))} /></label></>}<div className="form-actions"><button className="button button--secondary" type="submit" disabled={!projectId}>Save project policy</button></div></form><h3>Saved allowed origins</h3>{savedOrigins.length ? <ul className="stack-list">{savedOrigins.map((origin) => <li key={origin}><code>{origin}</code></li>)}</ul> : <p>No origin policy has been saved for this project.</p>}</section>;

  return <><PageHeader eyebrow="Governed intelligence" title="Agent workspace" description="Request a bounded Playwright draft or explore a site with Vision, then make one auditable decision." />
    <div className="agent-tabs" role="tablist" aria-label="Agent capability"><button type="button" role="tab" aria-selected={activeTab === "generation"} className={`agent-tabs__tab ${activeTab === "generation" ? "agent-tabs__tab--active" : ""}`} onClick={() => setActiveTab("generation")}>Playwright test</button><button type="button" role="tab" aria-selected={activeTab === "vision"} className={`agent-tabs__tab ${activeTab === "vision" ? "agent-tabs__tab--active" : ""}`} onClick={() => setActiveTab("vision")}>Vision Agent</button></div>
    {activeTab === "generation" && <><section className="workspace-section"><h2>Request a Playwright test</h2><p>The dashboard is an API client: it never authorizes, redacts, generates, approves, or executes a test itself.</p>
      <form onSubmit={submit} className="form-grid"><label className="field">Project<select required value={projectId} onChange={(e) => setProjectId(e.target.value)} disabled={Boolean(draftId) || !projectOptions.length}><option value="">{projectOptions.length ? "Choose a project" : "No projects available"}</option>{projectOptions.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}</select></label><label className="field">Target URL <input required type="url" value={targetUrl} onChange={(e) => setTargetUrl(e.target.value)} readOnly={Boolean(draftId)} /></label><label className="field form-grid--full">Natural-language request <textarea required value={naturalRequest} onChange={(e) => setNaturalRequest(e.target.value)} readOnly={Boolean(draftId)} /></label>{draftId ? <p className="form-grid--full">Source request is shown for review only. Use the decision controls below; this page will not submit another generation request.</p> : <div className="form-actions form-grid--full"><button className="button" type="submit" disabled={!projectId}>Submit for generation</button>{!projectOptions.length && <Link href="/projects">Create a project</Link>}</div>}</form>
    </section>
    {renderProjectPolicy(false)}
    {notice && <p className={`notice ${notice.includes("unavailable") ? "notice--error" : ""}`} role="alert">{notice}</p>}
    {generation && <><section className="workspace-section" aria-label="Generation request"><div className="section-heading"><h2>Generation request</h2><StatusBadge status={generation.state} /></div><ul className="detail-list"><li>Request: {generation.redacted_request}</li><li>Request hash: <code>{generation.request_hash}</code></li><li>Correlation: <code>{generation.correlation_id}</code></li>{generation.failure_reason && <li>Safe failure: {generation.failure_reason}</li>}</ul>{shouldPollGeneration(generation.state) && <LoadingState title="Generation is in progress" />}</section><ActivityTimeline apiUrl={apiUrl} correlationId={generation.correlation_id} live={shouldPollGeneration(generation.state)} /></>}
    {draft && <section className="workspace-section" aria-label="Generated draft"><div className="section-heading"><h2>{draft.title}</h2><StatusBadge status={draft.state} /></div><p>Source hash: <code>{draft.source_hash}</code></p><CodeBlock label="Generated Playwright source">{draft.playwright_test_source}</CodeBlock><h3>Assumptions</h3><ul className="stack-list">{draft.assumptions.map((item) => <li key={item}>{item}</li>)}</ul><h3>Stop conditions</h3><ul className="stack-list">{draft.stop_conditions.map((item) => <li key={item}>{item}</li>)}</ul><h3>Provenance</h3><CodeBlock label="Draft provenance">{JSON.stringify(draft.provenance, null, 2)}</CodeBlock>{canDecide && <div className="form-grid form-grid--one"><label className="field">Decision reason <input value={reason} onChange={(e) => setReason(e.target.value)} /></label><div className="button-row"><button type="button" className="button" onClick={() => setDecision(true)}>Approve and dispatch once</button><button type="button" className="button button--danger" onClick={() => setDecision(false)}>Reject draft</button></div></div>}{draft.linked_test_case_id && <p>Versioned test case: <code>{draft.linked_test_case_id}</code></p>}</section>}
    {run && <><section className="workspace-section" aria-label="Deterministic run"><div className="section-heading"><h2>Deterministic v1 run</h2><StatusBadge status={run.status} /></div><ul className="detail-list"><li>Run: <code>{run.id}</code></li><li>Correlation: <code>{run.correlation_id}</code></li></ul><h3>Evidence</h3>{artifacts.length ? <ul className="stack-list">{artifacts.map((artifact) => <li key={artifact.id}>{artifact.kind}: <code>{artifact.checksum}</code> ({artifact.size} bytes)</li>)}</ul> : <EmptyState title="No evidence has been recorded">Artifacts are published by the deterministic runner when the configured artifact policy requires them.</EmptyState>}</section><ActivityTimeline apiUrl={apiUrl} runId={run.id} live={["queued", "running"].includes(run.status)} /></>}
    <ConfirmDialog open={decision !== null} title={decision ? "Approve this draft?" : "Reject this draft?"} description={decision ? "Approval is final and creates one deterministic v1 run." : "Rejection is final and cannot be changed later."} confirmLabel={decision ? "Approve and dispatch" : "Reject draft"} onConfirm={() => { if (decision !== null) void decide(decision); }} onCancel={() => setDecision(null)} busy={isDeciding} />
    </>}
    {activeTab === "vision" && <VisionDashboard apiUrl={apiUrl} projectPolicy={renderProjectPolicy(true)} />}
  </>;
}
