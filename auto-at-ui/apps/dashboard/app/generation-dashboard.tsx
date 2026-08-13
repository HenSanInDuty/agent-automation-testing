"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { CodeBlock } from "./components/code-block";
import { ConfirmDialog } from "./components/confirm-dialog";
import { ActivityTimeline } from "./components/activity-timeline";
import { PageHeader } from "./components/page-header";
import { EmptyState, LoadingState } from "./components/states";
import { StatusBadge } from "./components/status-badge";
import { ControlPlaneError, decideDraft, getArtifacts, getDraft, getGenerationRequest, getPolicy, getRun, setPolicy, submitGeneration } from "./generation-api";
import { shouldPollGeneration } from "./generation-polling";
import type { Artifact, GeneratedDraft, GenerationRequest, Run } from "./generation-types";
import { projects, type Project } from "./run-api";

function errorMessage(error: unknown) { return error instanceof ControlPlaneError ? error.message : "The control plane is unavailable. Try again later."; }

export function GenerationDashboard({ apiUrl }: { apiUrl: string }) {
  const [projectId, setProjectId] = useState("");
  const [projectOptions, setProjectOptions] = useState<Project[]>([]);
  const [targetUrl, setTargetUrl] = useState("");
  const [naturalRequest, setNaturalRequest] = useState("");
  const [origins, setOrigins] = useState("");
  const [savedOrigins, setSavedOrigins] = useState<string[]>([]);
  const [generation, setGeneration] = useState<GenerationRequest | null>(null);
  const [draft, setDraft] = useState<GeneratedDraft | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [reason, setReason] = useState("");
  const [notice, setNotice] = useState("");
  const [decision, setDecision] = useState<boolean | null>(null);
  const [isDeciding, setIsDeciding] = useState(false);
  const canDecide = useMemo(() => draft?.state === "pending_review", [draft]);

  useEffect(() => {
    projects(apiUrl).then((next) => { setProjectOptions(next); setProjectId((current) => current || next[0]?.id || ""); }).catch((error) => setNotice(errorMessage(error)));
  }, [apiUrl]);

  useEffect(() => {
    if (!projectId) { setOrigins(""); setSavedOrigins([]); return; }
    getPolicy(apiUrl, projectId).then((policy) => {
      setSavedOrigins(policy.allowed_origins);
      setOrigins(policy.allowed_origins.join(", "));
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
    try { setDraft(await decideDraft(apiUrl, draft.id, approved, reason)); setNotice(approved ? "Draft approved. The control plane created one deterministic run." : "Draft rejected. This final decision is immutable."); setDecision(null); }
    catch (error) { setNotice(errorMessage(error)); }
    finally { setIsDeciding(false); }
  }
  async function savePolicy(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try { const policy = await setPolicy(apiUrl, projectId, origins.split(/\s|,/).filter(Boolean)); setSavedOrigins(policy.allowed_origins); setOrigins(policy.allowed_origins.join(", ")); setNotice(`Project policy saved: ${policy.allowed_origins.join(", ")}`); }
    catch (error) { setNotice(errorMessage(error)); }
  }

  return <><PageHeader eyebrow="Governed intelligence" title="Agent workspace" description="Request a bounded Playwright draft, inspect the control-plane response, then make one auditable decision." />
    <section className="workspace-section"><h2>Request a Playwright test</h2><p>The dashboard is an API client: it never authorizes, redacts, generates, approves, or executes a test itself.</p>
      <form onSubmit={submit} className="form-grid"><label className="field">Project<select required value={projectId} onChange={(e) => setProjectId(e.target.value)} disabled={!projectOptions.length}><option value="">{projectOptions.length ? "Choose a project" : "No projects available"}</option>{projectOptions.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}</select></label><label className="field">Target URL <input required type="url" value={targetUrl} onChange={(e) => setTargetUrl(e.target.value)} /></label><label className="field form-grid--full">Natural-language request <textarea required value={naturalRequest} onChange={(e) => setNaturalRequest(e.target.value)} /></label><div className="form-actions form-grid--full"><button className="button" type="submit" disabled={!projectId}>Submit for generation</button>{!projectOptions.length && <Link href="/projects">Create a project</Link>}</div></form>
    </section>
    <section className="workspace-section"><h2>Project policy</h2><p>Only project administrators can save an origin allowlist.</p><form onSubmit={savePolicy} className="form-grid form-grid--one"><label className="field">Allowed origins <input required placeholder="https://example.com" value={origins} onChange={(e) => setOrigins(e.target.value)} /></label><div className="form-actions"><button className="button button--secondary" type="submit" disabled={!projectId}>Save allowed origins</button></div></form><h3>Saved allowed origins</h3>{savedOrigins.length ? <ul className="stack-list">{savedOrigins.map((origin) => <li key={origin}><code>{origin}</code></li>)}</ul> : <p>No origin policy has been saved for this project.</p>}</section>
    {notice && <p className={`notice ${notice.includes("unavailable") ? "notice--error" : ""}`} role="alert">{notice}</p>}
    {generation && <><section className="workspace-section" aria-label="Generation request"><div className="section-heading"><h2>Generation request</h2><StatusBadge status={generation.state} /></div><ul className="detail-list"><li>Request: {generation.redacted_request}</li><li>Request hash: <code>{generation.request_hash}</code></li><li>Correlation: <code>{generation.correlation_id}</code></li>{generation.failure_reason && <li>Safe failure: {generation.failure_reason}</li>}</ul>{shouldPollGeneration(generation.state) && <LoadingState title="Generation is in progress" />}</section><ActivityTimeline apiUrl={apiUrl} correlationId={generation.correlation_id} live={shouldPollGeneration(generation.state)} /></>}
    {draft && <section className="workspace-section" aria-label="Generated draft"><div className="section-heading"><h2>{draft.title}</h2><StatusBadge status={draft.state} /></div><p>Source hash: <code>{draft.source_hash}</code></p><CodeBlock label="Generated Playwright source">{draft.playwright_test_source}</CodeBlock><h3>Assumptions</h3><ul className="stack-list">{draft.assumptions.map((item) => <li key={item}>{item}</li>)}</ul><h3>Stop conditions</h3><ul className="stack-list">{draft.stop_conditions.map((item) => <li key={item}>{item}</li>)}</ul><h3>Provenance</h3><CodeBlock label="Draft provenance">{JSON.stringify(draft.provenance, null, 2)}</CodeBlock>{canDecide && <div className="form-grid form-grid--one"><label className="field">Decision reason <input value={reason} onChange={(e) => setReason(e.target.value)} /></label><div className="button-row"><button type="button" className="button" onClick={() => setDecision(true)}>Approve and dispatch once</button><button type="button" className="button button--danger" onClick={() => setDecision(false)}>Reject draft</button></div></div>}{draft.linked_test_case_id && <p>Versioned test case: <code>{draft.linked_test_case_id}</code></p>}</section>}
    {run && <><section className="workspace-section" aria-label="Deterministic run"><div className="section-heading"><h2>Deterministic v1 run</h2><StatusBadge status={run.status} /></div><ul className="detail-list"><li>Run: <code>{run.id}</code></li><li>Correlation: <code>{run.correlation_id}</code></li></ul><h3>Evidence</h3>{artifacts.length ? <ul className="stack-list">{artifacts.map((artifact) => <li key={artifact.id}>{artifact.kind}: <code>{artifact.checksum}</code> ({artifact.size} bytes)</li>)}</ul> : <EmptyState title="No evidence has been recorded">Artifacts are published by the deterministic runner when the configured artifact policy requires them.</EmptyState>}</section><ActivityTimeline apiUrl={apiUrl} runId={run.id} live={["queued", "running"].includes(run.status)} /></>}
    <ConfirmDialog open={decision !== null} title={decision ? "Approve this draft?" : "Reject this draft?"} description={decision ? "Approval is final and creates one deterministic v1 run." : "Rejection is final and cannot be changed later."} confirmLabel={decision ? "Approve and dispatch" : "Reject draft"} onConfirm={() => { if (decision !== null) void decide(decision); }} onCancel={() => setDecision(null)} busy={isDeciding} />
  </>;
}
