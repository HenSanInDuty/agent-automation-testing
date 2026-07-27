"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { ControlPlaneError, decideDraft, getArtifacts, getDraft, getGenerationRequest, getRun, setPolicy, submitGeneration } from "./generation-api";
import { shouldPollGeneration } from "./generation-polling";
import type { Artifact, DashboardIdentity, GeneratedDraft, GenerationRequest, Run } from "./generation-types";

const initialIdentity: DashboardIdentity = { tenantId: "demo-tenant", actorId: "local-developer", roles: "contributor" };
function errorMessage(error: unknown) { return error instanceof ControlPlaneError ? error.message : "The control plane is unavailable. Try again later."; }

export function GenerationDashboard({ apiUrl }: { apiUrl: string }) {
  const [identity, setIdentity] = useState(initialIdentity);
  const [projectId, setProjectId] = useState("");
  const [targetUrl, setTargetUrl] = useState("");
  const [naturalRequest, setNaturalRequest] = useState("");
  const [origins, setOrigins] = useState("");
  const [generation, setGeneration] = useState<GenerationRequest | null>(null);
  const [draft, setDraft] = useState<GeneratedDraft | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [reason, setReason] = useState("");
  const [notice, setNotice] = useState("");
  const canDecide = useMemo(() => draft?.state === "pending_review", [draft]);

  useEffect(() => {
    if (!generation || !shouldPollGeneration(generation.state)) return;
    const timer = window.setInterval(async () => {
      try { setGeneration(await getGenerationRequest(apiUrl, identity, generation.id)); }
      catch (error) { setNotice(errorMessage(error)); }
    }, 2000);
    return () => window.clearInterval(timer);
  }, [apiUrl, generation, identity]);

  useEffect(() => {
    if (!generation?.draft_id || draft?.id === generation.draft_id) return;
    getDraft(apiUrl, identity, generation.draft_id).then(setDraft).catch((error) => setNotice(errorMessage(error)));
  }, [apiUrl, draft?.id, generation?.draft_id, identity]);

  useEffect(() => {
    if (!draft?.linked_run_id) return;
    Promise.all([getRun(apiUrl, identity, draft.linked_run_id), getArtifacts(apiUrl, identity, draft.linked_run_id)])
      .then(([nextRun, nextArtifacts]) => { setRun(nextRun); setArtifacts(nextArtifacts); })
      .catch((error) => setNotice(errorMessage(error)));
  }, [apiUrl, draft?.linked_run_id, identity]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setNotice(""); setDraft(null); setRun(null); setArtifacts([]);
    try { setGeneration(await submitGeneration(apiUrl, identity, { project_id: projectId, target_url: targetUrl, request: naturalRequest })); }
    catch (error) { setNotice(errorMessage(error)); }
  }
  async function decide(approved: boolean) {
    if (!draft) return;
    try { setDraft(await decideDraft(apiUrl, identity, draft.id, approved, reason)); setNotice(approved ? "Draft approved. The control plane created one deterministic run." : "Draft rejected. This final decision is immutable."); }
    catch (error) { setNotice(errorMessage(error)); }
  }
  async function savePolicy(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try { const policy = await setPolicy(apiUrl, identity, projectId, origins.split(/\s|,/).filter(Boolean)); setNotice(`Project policy saved: ${policy.allowed_origins.join(", ")}`); }
    catch (error) { setNotice(errorMessage(error)); }
  }

  return <main>
    <h1>Generated test review</h1>
    <p>The dashboard sends requests to the control plane; it does not redact, authorize, generate, approve, or execute tests itself.</p>
    <fieldset><legend>Local development identity</legend>
      <label>Tenant <input value={identity.tenantId} onChange={(e) => setIdentity({ ...identity, tenantId: e.target.value })} /></label>
      <label>Actor <input value={identity.actorId} onChange={(e) => setIdentity({ ...identity, actorId: e.target.value })} /></label>
      <label>Roles <input value={identity.roles} onChange={(e) => setIdentity({ ...identity, roles: e.target.value })} /></label>
    </fieldset>
    <form onSubmit={submit}><h2>Request a Playwright test</h2>
      <label>Project ID <input required value={projectId} onChange={(e) => setProjectId(e.target.value)} /></label>
      <label>Target URL <input required type="url" value={targetUrl} onChange={(e) => setTargetUrl(e.target.value)} /></label>
      <label>Natural-language request <textarea required value={naturalRequest} onChange={(e) => setNaturalRequest(e.target.value)} /></label>
      <button type="submit">Submit for generation</button>
    </form>
    <form onSubmit={savePolicy}><h2>Project policy (administrators only)</h2>
      <label>Allowed origins <input required placeholder="https://example.com" value={origins} onChange={(e) => setOrigins(e.target.value)} /></label>
      <button type="submit">Save allowed origins</button>
    </form>
    {notice && <p role="alert">{notice}</p>}
    {generation && <section aria-label="Generation request"><h2>Generation request</h2>
      <p>Status: <strong>{generation.state}</strong></p><p>Request: {generation.redacted_request}</p><p>Request hash: <code>{generation.request_hash}</code></p>
      {generation.failure_reason && <p>Safe failure: {generation.failure_reason}</p>}
    </section>}
    {draft && <section aria-label="Generated draft"><h2>{draft.title}</h2><p>Draft status: <strong>{draft.state}</strong></p>
      <p>Source hash: <code>{draft.source_hash}</code></p><pre>{draft.playwright_test_source}</pre>
      <h3>Assumptions</h3><ul>{draft.assumptions.map((item) => <li key={item}>{item}</li>)}</ul>
      <h3>Stop conditions</h3><ul>{draft.stop_conditions.map((item) => <li key={item}>{item}</li>)}</ul>
      <h3>Provenance</h3><pre>{JSON.stringify(draft.provenance, null, 2)}</pre>
      {canDecide && <><label>Decision reason <input value={reason} onChange={(e) => setReason(e.target.value)} /></label><button onClick={() => decide(true)}>Approve and dispatch once</button><button onClick={() => decide(false)}>Reject draft</button></>}
      {draft.linked_test_case_id && <p>Versioned test case: <code>{draft.linked_test_case_id}</code></p>}
    </section>}
    {run && <section aria-label="Deterministic run"><h2>Deterministic v1 run</h2><p>Run: <code>{run.id}</code> ({run.status})</p><p>Correlation: <code>{run.correlation_id}</code></p>
      <h3>Evidence</h3><ul>{artifacts.map((artifact) => <li key={artifact.id}>{artifact.kind}: <code>{artifact.checksum}</code> ({artifact.size} bytes)</li>)}</ul>
    </section>}
  </main>;
}
