"use client";

import { Eye, FileCode2 } from "lucide-react";
import { FormEvent, useEffect, useId, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { Code, CodeBlock, FormField, Hint, ItemList, Notice } from "./components/agent-ui";
import { Section } from "./components/section";
import { ConfirmDialog } from "./components/confirm-dialog";
import { ActivityTimeline } from "./components/activity-timeline";
import { EmptyState, LoadingState } from "./components/states";
import { StatusBadge } from "./components/status-badge";
import { VisionDashboard } from "./vision-dashboard";
import { GenerationProviderSettings } from "./components/generation-provider-settings";
import { agentWorkspaceTab } from "./components/agent-workspace-model";
import { ControlPlaneError, decideDraft, getArtifacts, getDraft, getGenerationRequest, getPolicy, getRun, setPolicy, submitGeneration } from "./generation-api";
import { shouldPollGeneration } from "./generation-polling";
import type { Artifact, GeneratedDraft, GenerationRequest, Run } from "./generation-types";
import { projects, type Project } from "./run-api";

function errorMessage(error: unknown) { return error instanceof ControlPlaneError ? error.message : "The control plane is unavailable. Try again later."; }

export function GenerationDashboard({ apiUrl }: { apiUrl: string }) {
  const searchParams = useSearchParams();
  const policyFieldId = useId();
  const visionId = searchParams.get("vision");
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
  const [activeTab, setActiveTab] = useState<"generation" | "vision">(() => agentWorkspaceTab(draftId));
  const [visionProjectId, setVisionProjectId] = useState("");
  const [loadedPolicyProject, setLoadedPolicyProject] = useState("");
  const policyProjectId = activeTab === "vision" ? visionProjectId : projectId;
  const policyContext = useRef("");
  policyContext.current = apiUrl + ":" + policyProjectId;
  useEffect(() => { setActiveTab(agentWorkspaceTab(draftId)); }, [draftId, visionId]);
  const visionSource = draft?.provenance.vision_source as { session_id?: string } | undefined;
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
    let disposed = false;
    setLoadedPolicyProject("");
    if (!policyProjectId) { setOrigins(""); setSavedOrigins([]); setVisionMaxHops(5); setVisionMaxStates(50); return; }
    getPolicy(apiUrl, policyProjectId).then((policy) => {
      if (disposed) return;
      setLoadedPolicyProject(policyProjectId);
      setSavedOrigins(policy.allowed_origins);
      setOrigins(policy.allowed_origins.join(", "));
      setVisionMaxHops(policy.vision_max_hops);
      setVisionMaxStates(policy.vision_max_states);
    }).catch((error) => { if (!disposed) setNotice(errorMessage(error)); });
    return () => { disposed = true; };
  }, [apiUrl, policyProjectId]);

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
    if (!policyProjectId || loadedPolicyProject !== policyProjectId) return;
    const expected = policyContext.current;
    try { const policy = await setPolicy(apiUrl, policyProjectId, { allowed_origins: origins.split(/\s|,/).filter(Boolean), vision_max_hops: visionMaxHops, vision_max_states: visionMaxStates }); if (expected !== policyContext.current) return; setSavedOrigins(policy.allowed_origins); setOrigins(policy.allowed_origins.join(", ")); setVisionMaxHops(policy.vision_max_hops); setVisionMaxStates(policy.vision_max_states); setNotice(`Project policy saved: ${policy.allowed_origins.join(", ")}`); }
    catch (error) { if (expected === policyContext.current) setNotice(errorMessage(error)); }
  }
  const renderProjectPolicy = (showVisionLimits: boolean) => <Section aria-label="Project policy" title="Project policy" className={showVisionLimits ? "rounded-none border-0 bg-transparent py-5 shadow-none" : undefined} contentClassName="grid gap-5" description={<>{showVisionLimits && <>Vision continues across external origins and records them in the session log. The origin allowlist below applies to deterministic test runs. </>}Only project administrators can save the origin allowlist{showVisionLimits ? " and Vision tree bounds" : ""}.</>}>
    <form onSubmit={savePolicy} className="grid gap-4 min-[640px]:grid-cols-2">
      <FormField id={`${policyFieldId}-origins`} label="Allowed origins" className="min-[640px]:col-span-2">
        <Input id={`${policyFieldId}-origins`} required placeholder="https://example.com or *" value={origins} onChange={(e) => setOrigins(e.target.value)} />
        <Hint className="text-xs"><Code>*</Code> permits this project to access every HTTP(S) website. Use it only when that broad browser access is intended.</Hint>
      </FormField>
      {showVisionLimits && <>
        <FormField id={`${policyFieldId}-hops`} label="Vision maximum hops"><Input id={`${policyFieldId}-hops`} required type="number" min="1" max="20" value={visionMaxHops} onChange={(e) => setVisionMaxHops(Number(e.target.value))} /></FormField>
        <FormField id={`${policyFieldId}-states`} label="Vision maximum states"><Input id={`${policyFieldId}-states`} required type="number" min="1" max="200" value={visionMaxStates} onChange={(e) => setVisionMaxStates(Number(e.target.value))} /></FormField>
      </>}
      <div className="min-[640px]:col-span-2"><Button variant="outline" type="submit" disabled={!policyProjectId || loadedPolicyProject !== policyProjectId}>Save project policy</Button></div>
    </form>
    <div className="grid gap-2">
      <h3 className="text-sm font-semibold">Saved allowed origins</h3>
      {savedOrigins.length ? <ItemList className="flex flex-wrap gap-2">{savedOrigins.map((origin) => <li key={origin}><Code className="px-2 py-1">{origin}</Code></li>)}</ItemList> : <Hint>No origin policy has been saved for this project.</Hint>}
    </div>
  </Section>;
  const noticeTone = notice.includes("unavailable") ? "danger" : "info";

  return <div className="grid gap-5">
    <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as "generation" | "vision")} className="gap-5">
      <header className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold tracking-tight">Agent</h1>
          <p className="text-sm text-muted-foreground">Watch the website and follow each browser action.</p>
        </div>
        <TabsList aria-label="Agent capability">
          <TabsTrigger value="generation" className="gap-2 px-3"><FileCode2 aria-hidden="true" />Playwright test</TabsTrigger>
          <TabsTrigger value="vision" className="gap-2 px-3"><Eye aria-hidden="true" />Vision Agent</TabsTrigger>
        </TabsList>
      </header>
      <TabsContent value="generation" className="grid gap-5">
        <Section title="Request a Playwright test" description="The dashboard is an API client: it never authorizes, redacts, generates, approves, or executes a test itself." contentClassName="grid gap-4">
          <form onSubmit={submit} className="grid gap-4 min-[720px]:grid-cols-2">
            <FormField id="generation-project" label="Project"><NativeSelect id="generation-project" required value={projectId} onChange={(e) => setProjectId(e.target.value)} disabled={Boolean(draftId) || !projectOptions.length}><option value="">{projectOptions.length ? "Choose a project" : "No projects available"}</option>{projectOptions.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}</NativeSelect></FormField>
            <FormField id="generation-target-url" label="Target URL"><Input id="generation-target-url" required type="url" placeholder="https://example.com" value={targetUrl} onChange={(e) => setTargetUrl(e.target.value)} readOnly={Boolean(draftId)} /></FormField>
            <FormField id="generation-request" label="Natural-language request" className="min-[720px]:col-span-2"><Textarea id="generation-request" required className="min-h-28" value={naturalRequest} onChange={(e) => setNaturalRequest(e.target.value)} readOnly={Boolean(draftId)} /></FormField>
            {draftId ? <Notice tone="info" className="min-[720px]:col-span-2">Source request is shown for review only. Use the decision controls below; this page will not submit another generation request.</Notice> : <div className="flex flex-wrap items-center gap-4 min-[720px]:col-span-2"><Button type="submit" disabled={!projectId}>Submit for generation</Button>{!projectOptions.length && <Link className="text-sm font-medium text-primary underline-offset-4 hover:underline" href="/projects">Create a project</Link>}</div>}
          </form>
        </Section>
        {renderProjectPolicy(false)}
        {notice && <Notice tone={noticeTone} role="alert">{notice}</Notice>}
        {generation && <>
          <Section aria-label="Generation request" title="Generation request" actions={<StatusBadge status={generation.state} />} contentClassName="grid gap-4">
            <ItemList className="text-muted-foreground"><li>Request: {generation.redacted_request}</li><li>Request hash: <Code>{generation.request_hash}</Code></li><li>Correlation: <Code>{generation.correlation_id}</Code></li>{generation.failure_reason && <li className="text-destructive">Safe failure: {generation.failure_reason}</li>}</ItemList>
            {shouldPollGeneration(generation.state) && <LoadingState title="Generation is in progress" />}
          </Section>
          <ActivityTimeline apiUrl={apiUrl} correlationId={generation.correlation_id} live={shouldPollGeneration(generation.state)} />
        </>}
        {draft && <Section aria-label="Generated draft" title={draft.title} actions={<StatusBadge status={draft.state} />} contentClassName="grid gap-5">
          <p className="text-sm text-muted-foreground">Source hash: <Code>{draft.source_hash}</Code></p>
          <CodeBlock label="Generated Playwright source" className="max-h-[30rem]">{draft.playwright_test_source}</CodeBlock>
          <div className="grid gap-5 min-[720px]:grid-cols-2">
            <div className="grid content-start gap-2"><h3 className="text-sm font-semibold">Assumptions</h3><ul className="grid list-disc gap-1 pl-5 text-sm text-muted-foreground">{draft.assumptions.map((item) => <li key={item}>{item}</li>)}</ul></div>
            <div className="grid content-start gap-2"><h3 className="text-sm font-semibold">Stop conditions</h3><ul className="grid list-disc gap-1 pl-5 text-sm text-muted-foreground">{draft.stop_conditions.map((item) => <li key={item}>{item}</li>)}</ul></div>
          </div>
          <h3 className="text-sm font-semibold">Provenance</h3>
          {visionSource?.session_id && <p><Link className="text-sm font-medium text-primary underline-offset-4 hover:underline" href={`/agent?vision=${encodeURIComponent(visionSource.session_id)}`}>View source Vision trace</Link></p>}
          <CodeBlock label="Draft provenance">{JSON.stringify(draft.provenance, null, 2)}</CodeBlock>
          {canDecide && <div className="grid gap-4 rounded-lg border bg-muted/30 p-4">
            <FormField id="generation-decision-reason" label="Decision reason" className="max-w-xl"><Input id="generation-decision-reason" value={reason} onChange={(e) => setReason(e.target.value)} /></FormField>
            <div className="flex flex-wrap gap-2"><Button type="button" onClick={() => setDecision(true)}>Approve and dispatch once</Button><Button type="button" variant="destructive" onClick={() => setDecision(false)}>Reject draft</Button></div>
          </div>}
          {draft.linked_test_case_id && <p className="text-sm">Versioned test case: <Code>{draft.linked_test_case_id}</Code></p>}
        </Section>}
        {run && <>
          <Section aria-label="Deterministic run" title="Deterministic v1 run" actions={<StatusBadge status={run.status} />} contentClassName="grid gap-4">
            <ItemList className="text-muted-foreground"><li>Run: <Code>{run.id}</Code></li><li>Correlation: <Code>{run.correlation_id}</Code></li></ItemList>
            <h3 className="text-sm font-semibold">Evidence</h3>
            {artifacts.length ? <ItemList>{artifacts.map((artifact) => <li key={artifact.id} className="rounded-lg border bg-muted/30 px-3 py-2">{artifact.kind}: <Code>{artifact.checksum}</Code> ({artifact.size} bytes)</li>)}</ItemList> : <EmptyState title="No evidence has been recorded">Artifacts are published by the deterministic runner when the configured artifact policy requires them.</EmptyState>}
          </Section>
          <ActivityTimeline apiUrl={apiUrl} runId={run.id} live={["queued", "running"].includes(run.status)} />
        </>}
        <ConfirmDialog open={decision !== null} title={decision ? "Approve this draft?" : "Reject this draft?"} description={decision ? "Approval is final and creates one deterministic v1 run." : "Rejection is final and cannot be changed later."} confirmLabel={decision ? "Approve and dispatch" : "Reject draft"} onConfirm={() => { if (decision !== null) void decide(decision); }} onCancel={() => setDecision(null)} busy={isDeciding} />
      </TabsContent>
      <TabsContent value="vision" className="grid gap-5">
        <VisionDashboard apiUrl={apiUrl} onProjectChange={setVisionProjectId} projectPolicy={<>{notice && <Notice tone={noticeTone} role="status" className="mx-6 mt-5">{notice}</Notice>}{renderProjectPolicy(true)}</>} />
      </TabsContent>
    </Tabs>
    <GenerationProviderSettings apiUrl={apiUrl} />
  </div>;
}
