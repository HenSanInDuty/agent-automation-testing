"use client";

import { useEffect, useState } from "react";
import { CodeBlock } from "../components/code-block";
import { ConfirmDialog } from "../components/confirm-dialog";
import { EmptyState, ErrorState, LoadingState } from "../components/states";
import { StatusBadge } from "../components/status-badge";
import { ControlPlaneError, decideProposal, listDrafts, listProposals } from "../generation-api";
import type { GeneratedDraft, Proposal } from "../generation-types";

function message(error: unknown) { return error instanceof ControlPlaneError ? error.message : "The control plane is unavailable. Try again later."; }

export function ReviewsDashboard({ apiUrl }: { apiUrl: string }) {
  const [drafts, setDrafts] = useState<GeneratedDraft[] | null>(null);
  const [proposals, setProposals] = useState<Proposal[] | null>(null);
  const [error, setError] = useState("");
  const [reason, setReason] = useState("");
  const [pending, setPending] = useState<{ proposal: Proposal; approved: boolean } | null>(null);
  const [busy, setBusy] = useState(false);
  const load = () => Promise.all([listDrafts(apiUrl, "pending_review"), listProposals(apiUrl)]).then(([nextDrafts, nextProposals]) => { setDrafts(nextDrafts.items); setProposals(nextProposals.items); setError(""); }).catch((nextError) => setError(message(nextError)));
  useEffect(() => { void load(); }, [apiUrl]);
  async function decide() { if (!pending) return; setBusy(true); try { await decideProposal(apiUrl, pending.proposal.id, pending.approved, reason); setPending(null); setReason(""); await load(); } catch (nextError) { setError(message(nextError)); } finally { setBusy(false); } }
  if (drafts === null || proposals === null) return <LoadingState title="Loading governed review queue" />;
  return <>{error && <ErrorState title="Unable to load reviews">{error}</ErrorState>}
    <section className="workspace-section"><h2>Generated drafts awaiting a decision</h2>{drafts.length === 0 ? <EmptyState title="No generated drafts are waiting">Approved and rejected drafts remain available through their linked request and run records.</EmptyState> : <ul className="stack-list">{drafts.map((draft) => <li key={draft.id}><div className="section-heading"><strong>{draft.title}</strong><StatusBadge status={draft.state} /></div><p>Source hash: <code>{draft.source_hash}</code></p><p><a href={`/agent?draft=${draft.id}`}>Inspect draft, assumptions, provenance, and decide</a></p></li>)}</ul>}</section>
    <section className="workspace-section"><h2>Agent proposals</h2>{proposals.length === 0 ? <EmptyState title="No proposals yet">Failure triage and healing proposals appear here with their deterministic run evidence.</EmptyState> : <ul className="stack-list">{proposals.map((proposal) => <li key={proposal.id}><div className="section-heading"><strong>{proposal.summary}</strong><StatusBadge status={proposal.decision ? (proposal.decision.approved ? "approved" : "rejected") : "pending_review"} /></div><p>Kind: {proposal.kind} · version {proposal.proposal_version}</p><p><a href={`/runs/${proposal.run_id}`}>Open deterministic run evidence</a> · Correlation: <code>{proposal.correlation_id}</code></p><CodeBlock label="Proposal evidence">{JSON.stringify(proposal.payload, null, 2)}</CodeBlock>{proposal.decision ? <p>Final decision: {proposal.decision.approved ? "Approved" : "Rejected"} by {proposal.decision.decided_by}{proposal.decision.reason ? ` — ${proposal.decision.reason}` : ""}.</p> : <div className="form-grid form-grid--one"><label className="field">Decision reason (optional)<input value={pending?.proposal.id === proposal.id ? reason : ""} onChange={(event) => setReason(event.target.value)} /></label><div className="button-row"><button className="button" type="button" onClick={() => setPending({ proposal, approved: true })}>Approve proposal</button><button className="button button--danger" type="button" onClick={() => setPending({ proposal, approved: false })}>Reject proposal</button></div></div>}</li>)}</ul>}</section>
    <ConfirmDialog open={pending !== null} title={pending?.approved ? "Approve this proposal?" : "Reject this proposal?"} description="This decision is final, immutable, and is recorded by the control plane before the queue updates." confirmLabel={pending?.approved ? "Approve proposal" : "Reject proposal"} onConfirm={() => void decide()} onCancel={() => setPending(null)} busy={busy} />
  </>;
}
