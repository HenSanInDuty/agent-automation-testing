"use client";

import Link from "next/link";
import { FormEvent, useEffect, useId, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Code, CheckboxField, FormField, Hint, ItemList, Notice } from "./agent-ui";
import { Section } from "./section";
import { VisionTaskAssessmentPanel } from "./vision-task-assessment";
import { validTaskAssessment } from "./vision-task-assessment-model";
import { agentTaskProvenance, canRequestDraft, clearInputs, consistencyLines, consistencyReasonLabel, draftFailureMessage, emptyInputs, inputsFilled, setInput, testValueOrigin, draftInputs, validConsistency, type TypeStep } from "./agent-task-draft-model";
import { ControlPlaneError, createAgentTaskDraft, getAgentTaskConsistency, getAgentTaskDraftInputs, getVisionResult } from "../generation-api";
import type { AgentTaskConsistency, AgentTaskDraftCreated, GeneratedDraft, VisionTaskAssessment } from "../generation-types";

const notOwned = "This project is not declared as a test environment you own, so a draft that types values cannot be requested. A project administrator can change that in Project settings.";
const unavailable = "The control plane is unavailable. Try again later.";
function failureText(error: unknown): string {
  if (!(error instanceof ControlPlaneError)) return unavailable;
  return draftFailureMessage(error.code) ?? error.message;
}

/**
 * Asks the API whether sessions of this task agree and, only if it says so, offers to create a test draft.
 * Typed values live in this component's state until the request is sent and are cleared as it is sent; they are
 * never put in the URL, storage, a log line or a field the browser may remember.
 */
export function AgentTaskDraftPanel({ apiUrl, sessionId }: { apiUrl: string; sessionId: string }) {
  const fieldId = useId();
  const [report, setReport] = useState<AgentTaskConsistency | null>(null);
  const [reportError, setReportError] = useState("");
  const [steps, setSteps] = useState<TypeStep[] | null>(null);
  const [values, setValues] = useState<string[]>([]);
  const [loadingSteps, setLoadingSteps] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState("");
  const [created, setCreated] = useState<AgentTaskDraftCreated | null>(null);

  useEffect(() => {
    const abort = new AbortController();
    setReport(null); setReportError(""); setSteps(null); setValues([]); setFailure(""); setCreated(null);
    getAgentTaskConsistency(apiUrl, sessionId, abort.signal)
      .then((next) => { if (abort.signal.aborted) return; const valid = validConsistency(next); setReport(valid); if (!valid) setReportError("The agreement report is unavailable, so no draft can be requested."); })
      .catch((error) => { if (!abort.signal.aborted) setReportError(failureText(error)); });
    return () => abort.abort();
  }, [apiUrl, sessionId]);

  async function openForm() {
    setFailure(""); setCreated(null); setLoadingSteps(true);
    try {
      const found = draftInputs(await getAgentTaskDraftInputs(apiUrl, sessionId));
      if (!found) setFailure("The list of values to type could not be read, so no draft can be requested. Reload the page and try again.");
      else if (!found.owned && found.hasTypeSteps) setFailure(notOwned);
      else { setSteps(found.steps); setValues(emptyInputs(found.steps)); }
    } catch (error) { setFailure(failureText(error)); }
    finally { setLoadingSteps(false); }
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || !steps) return;
    const sent = values;
    setValues(clearInputs(values)); setBusy(true); setFailure("");
    try {
      const draft = await createAgentTaskDraft(apiUrl, sessionId, sent);
      setCreated(draft); setSteps(null); setValues([]);
    } catch (error) { setFailure(failureText(error)); }
    finally { setBusy(false); }
  }

  return <Section aria-label="Test draft" title="Test draft" description="Turn this task into a Playwright test. A different person must review it before it runs; only that run gives a pass or fail verdict." contentClassName="grid gap-4">
    {!report && !reportError && <p role="status" className="text-sm text-muted-foreground">Checking whether sessions of this task agree…</p>}
    {reportError && <Notice tone="warning" role="status">{reportError}</Notice>}
    {report && <>
      <ItemList aria-label="Consistency report" className="text-muted-foreground">{consistencyLines(report).map((line) => <li key={line}>{line}</li>)}</ItemList>
      <Hint className="text-xs">{report.notice}</Hint>
      {!canRequestDraft(report) && <Notice tone="warning" role="status" className="grid gap-1.5">
        <p className="font-medium">A test draft cannot be created from this session yet.</p>
        <ul className="list-disc pl-5">{report.reasons.map((reason) => <li key={reason}>{consistencyReasonLabel(reason)}</li>)}</ul>
      </Notice>}
    </>}
    {created && <Notice tone="success" role="status" className="grid gap-1.5">
      <p>{created.created ? "Draft created. It waits for review by someone other than you." : "A draft for this session already exists; no new one was made."}</p>
      {created.contains_test_values && <p>It contains the test values you typed. The reviewer sees them in its source and must confirm they belong to disposable accounts.</p>}
      <p><Link className="font-medium text-primary underline-offset-4 hover:underline" href={`/agent?draft=${encodeURIComponent(created.draft_id)}`}>Open the draft for review</Link></p>
    </Notice>}
    {failure && <Notice tone="danger" role="alert">{failure}</Notice>}
    {canRequestDraft(report) && !steps && !created && <div><Button type="button" onClick={() => void openForm()} disabled={loadingSteps}>Create test draft</Button></div>}
    {steps && <form onSubmit={(event) => void submit(event)} autoComplete="off" className="grid gap-4" aria-label="Test draft values">
      {steps.length ? <>
        <Notice tone="warning" className="grid gap-1">
          <p className="font-medium">Type the value for each step, in order.</p>
          <p>Use only disposable test accounts. Each value is written as-is into the test source, which the reviewer reads, and is kept in the saved test and its run evidence. This browser does not store it; the fields are cleared when you send them.</p>
        </Notice>
        <ol className="grid gap-4">{steps.map((step, index) => <li key={step.position}>
          <FormField id={`${fieldId}-${step.position}`} label={`Step ${step.position}: ${step.label}`}>
            <Input id={`${fieldId}-${step.position}`} type="text" autoComplete="off" autoCorrect="off" autoCapitalize="off" spellCheck={false} data-1p-ignore="true" data-lpignore="true" data-form-type="other" required disabled={busy} value={values[index] ?? ""} onChange={(event) => setValues((current) => setInput(current, index, event.target.value))} aria-describedby={`${fieldId}-${step.position}-count`} />
            <Hint id={`${fieldId}-${step.position}-count`} className="text-xs tabular-nums">Needs exactly {step.textChars} characters · {(values[index] ?? "").length} typed</Hint>
          </FormField>
        </li>)}</ol>
      </> : <Hint>This session types no values. The draft is built from its recorded steps alone.</Hint>}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={busy || !inputsFilled(values)}>{busy ? "Creating draft…" : "Create draft for review"}</Button>
        <Button type="button" variant="outline" disabled={busy} onClick={() => { setSteps(null); setValues([]); }}>Cancel</Button>
      </div>
    </form>}
  </Section>;
}

/** Required before approving a draft that carries test values; the API refuses the approval without it. */
export function DisposableCredentialsAck({ checked, onChange }: { checked: boolean; onChange: (checked: boolean) => void }) {
  return <div className="grid gap-1.5">
    <CheckboxField checked={checked} onCheckedChange={onChange}>These typed values belong to disposable test accounts that can be reset or deleted.</CheckboxField>
    <Hint className="pl-[1.625rem] text-xs">Approval is not possible without this. The values stay in the saved test and in the run evidence.</Hint>
  </div>;
}

/** What a reviewer needs besides the source: the advisory assessment, how consistent the sessions were, and where typed values came from. */
export function AgentTaskDraftReview({ apiUrl, draft }: { apiUrl: string; draft: Pick<GeneratedDraft, "provenance" | "stop_conditions"> }) {
  const provenance = agentTaskProvenance(draft.provenance);
  const sessionId = provenance?.agent_trace_source.session_id;
  const [assessment, setAssessment] = useState<VisionTaskAssessment | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!sessionId) return;
    const abort = new AbortController();
    setAssessment(null); setError("");
    getVisionResult(apiUrl, sessionId, abort.signal)
      .then((result) => { if (!abort.signal.aborted) { const next = validTaskAssessment(result.task_assessment); setAssessment(next); if (!next) setError("The source session has no task assessment."); } })
      .catch((reason) => { if (!abort.signal.aborted) setError(reason instanceof ControlPlaneError ? reason.message : "The source session's assessment could not be loaded."); });
    return () => abort.abort();
  }, [apiUrl, sessionId]);
  if (!provenance || !sessionId) return null;
  return <Section aria-label="Agent session review" className="bg-muted/20 py-5 shadow-none" title="Review: where this draft comes from" description="Made from a recorded agent session. The assessment is the agent's advisory opinion, not a verdict; only the run after approval gives one." contentClassName="grid gap-4">
    <ItemList className="text-muted-foreground">
      <li>Source session: <Code>{sessionId}</Code> · <Link className="font-medium text-primary underline-offset-4 hover:underline" href={`/agent?vision=${encodeURIComponent(sessionId)}`}>View the session</Link></li>
      <li>Session trace hash: <Code>{provenance.agent_trace_source.trace_hash}</Code></li>
      <li>Requested by: {provenance.requested_by ? <Code>{provenance.requested_by}</Code> : "not recorded"}. The requester cannot approve their own draft.</li>
      {provenance.contains_test_values && <li>The project was {provenance.owned_test_target ? "" : "not "}declared a test environment you own when this was requested.</li>}
    </ItemList>
    {assessment ? <VisionTaskAssessmentPanel assessment={assessment} /> : error ? <Notice tone="warning" role="alert">{error}</Notice> : <p role="status" className="text-sm text-muted-foreground">Loading the session assessment…</p>}
    <div className="grid gap-1.5" role="group" aria-label="Session agreement">
      <h3 className="text-sm font-semibold">Agreement between sessions (when requested)</h3>
      {provenance.consistency ? <ItemList className="text-muted-foreground">{consistencyLines(provenance.consistency).map((line) => <li key={line}>{line}</li>)}</ItemList> : <Hint>Not recorded for this draft.</Hint>}
    </div>
    <div className="grid gap-1.5" role="group" aria-label="Test values">
      <h3 className="text-sm font-semibold">Test values</h3>
      <Notice tone={provenance.contains_test_values ? "warning" : "neutral"}>{testValueOrigin(provenance)}</Notice>
    </div>
    <Hint>A step the platform cannot verify makes the request fail instead of being dropped, so no recorded step is silently left out of the source above. Assertions that were left out are listed under stop conditions{draft.stop_conditions.length ? "" : " (none for this draft)"}.</Hint>
  </Section>;
}
