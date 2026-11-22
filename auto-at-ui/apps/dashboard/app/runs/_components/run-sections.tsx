import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { artifactDownloadUrl } from "../../api-client";
import { Section } from "../../components/section";
import { StatusBadge } from "../../components/status-badge";
import type { Proposal } from "../../generation-types";
import type { Artifact, RevisedDraftRequest, Run, RunReport } from "../../run-api";
import { BulletList, CodeBlock, SubHeading } from "./code-block";

const muted = "text-sm text-muted-foreground";

export function WhatRanSection({ item }: { item: Run }) {
  return (
    <Section title="What ran" description="The approved, immutable Playwright source for this exact revision.">
      {item.playwright_test_source ? (
        <div className="space-y-3">
          <CodeBlock>{item.playwright_test_source}</CodeBlock>
          <p className="text-xs text-muted-foreground">
            This source describes the browser actions. Playback evidence (trace, video, screenshot) is retained on failure under the current artifact policy.
          </p>
          {item.blocked_external_origins.length > 0 && (
            <div>
              <SubHeading>External origins blocked by policy</SubHeading>
              <ul className="space-y-1">
                {item.blocked_external_origins.map((origin) => (
                  <li key={origin}><code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs break-all">{origin}</code></li>
                ))}
              </ul>
            </div>
          )}
        </div>
      ) : (
        <p className={muted}>This legacy/manual run has no Playwright source attached. Inspect the activity timeline and retained artifacts below.</p>
      )}
    </Section>
  );
}

export function TriageSection({ status, proposals, revisionRequest, onCreateDraft }: {
  status: string | undefined;
  proposals: Proposal[];
  revisionRequest: RevisedDraftRequest | null;
  onCreateDraft: () => void;
}) {
  const link = "font-medium text-primary underline-offset-4 hover:underline";
  return (
    <Section title="Failure triage" actions={status && <StatusBadge status={status} />}>
      {proposals.length > 0 ? (
        <ul className="space-y-4">
          {proposals.map((proposal) => (
            <li key={proposal.id} className="space-y-2 rounded-lg border p-4">
              <p className="text-sm font-semibold">{proposal.summary}</p>
              <p className="text-xs text-muted-foreground">Kind: {proposal.kind} · version {proposal.proposal_version}</p>
              <CodeBlock>{JSON.stringify(proposal.payload, null, 2)}</CodeBlock>
              <a className={`${link} text-sm`} href="/reviews">Review or decide this proposal</a>
            </li>
          ))}
        </ul>
      ) : status === "queued" ? (
        <p className={muted}>Triage is queued and will analyze the retained failure evidence.</p>
      ) : status === "unavailable" ? (
        <p className={muted}>Triage is unavailable for this run. The deterministic result remains unchanged.</p>
      ) : (
        <p className={muted}>No triage proposal is available for this historical run.</p>
      )}
      <SubHeading>Revised Playwright draft</SubHeading>
      {revisionRequest ? (
        <p className="text-sm">
          Revision request is <strong>{revisionRequest.state}</strong>.{" "}
          {revisionRequest.state === "completed"
            ? <a className={link} href="/reviews">Open Reviews to inspect and approve the new draft.</a>
            : "The draft will appear in Reviews when generation finishes."}
          {revisionRequest.failure_reason ? ` Safe failure: ${revisionRequest.failure_reason}` : ""}
        </p>
      ) : (
        <div className="space-y-3">
          <p className={muted}>
            Create a new reviewable source revision from the approved source and this run’s safe failure detail. It cannot modify this failed revision or change its verdict.
          </p>
          <Button type="button" onClick={onCreateDraft}>Create revised draft</Button>
        </div>
      )}
    </Section>
  );
}

export function ReviewSection({ apiUrl, runId, report, reportMissing, cancellable, evidence }: {
  apiUrl: string;
  runId: string;
  report: RunReport | null;
  reportMissing: boolean;
  cancellable: boolean;
  evidence: Artifact[];
}) {
  const evidenceLinks = (references: string[]): ReactNode[] => references.map((reference) => {
    const artifact = evidence.find((file) => file.uri === reference);
    return artifact
      ? <a key={reference} className="font-medium text-primary underline-offset-4 hover:underline" href={artifactDownloadUrl(apiUrl, runId, artifact.id)}>{artifact.kind}</a>
      : <span key={reference} className="text-muted-foreground">Verified evidence reference</span>;
  });
  const withEvidence = (text: string, references: string[]): ReactNode => (
    <>{text}{references.length > 0 && <> — {evidenceLinks(references).map((node, index) => <span key={index}>{index > 0 && ", "}{node}</span>)}</>}</>
  );
  const payload = report?.status === "completed" ? report.payload : null;
  return (
    <Section title="AI post-run review" actions={report && <StatusBadge status={report.status} />}>
      {report && payload ? (
        <div>
          <p className="mb-4 text-sm text-muted-foreground">
            The agent reviews every terminal result, including PASS. It cannot change the deterministic verdict.
          </p>
          <h3 className="text-base font-semibold">{payload.headline}</h3>
          <p className="mt-1 text-sm">{payload.what_ran}</p>
          {payload.observations.length > 0 && (
            <>
              <SubHeading>Verified observations</SubHeading>
              <BulletList items={payload.observations.map((observation) => withEvidence(observation.text, observation.evidence_references))} />
            </>
          )}
          {payload.failure && (
            <>
              <SubHeading>Failure detail</SubHeading>
              <BulletList items={[
                `Stage: ${payload.failure.stage}`,
                `Location: ${payload.failure.location}`,
                `Reason: ${payload.failure.message}`,
                ...(payload.failure.evidence_references.length > 0 ? [<>Evidence: {evidenceLinks(payload.failure.evidence_references)}</>] : []),
              ]} />
            </>
          )}
          {payload.unverified_or_skipped.length > 0 && (
            <>
              <SubHeading>Unverified or skipped scope</SubHeading>
              <BulletList items={payload.unverified_or_skipped} />
            </>
          )}
          {payload.limitations.length > 0 && (
            <>
              <SubHeading>Limitations</SubHeading>
              <BulletList items={payload.limitations} />
            </>
          )}
          <p className="mt-5 border-t pt-3 text-xs text-muted-foreground">
            Provenance: {report.provenance.provider ?? "provider unavailable"}
            {report.provenance.model ? ` / ${report.provenance.model}` : ""}; prompt {report.prompt_version}.
          </p>
        </div>
      ) : report?.status === "unavailable" ? (
        <p className={muted}>
          The AI post-run review is unavailable: {report.unavailable_reason ?? "No safe reason was recorded."} The deterministic runner result remains the primary verdict.
        </p>
      ) : !cancellable && reportMissing ? (
        <p className={muted}>No review is available for this historical run.</p>
      ) : (
        <p className={muted}>Review will be prepared after a deterministic result.</p>
      )}
    </Section>
  );
}
