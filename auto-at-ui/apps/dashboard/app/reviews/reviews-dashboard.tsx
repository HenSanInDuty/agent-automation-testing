"use client";

import { useEffect, useState } from "react";
import { Check, ExternalLink, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ConfirmDialog } from "../components/confirm-dialog";
import { Section } from "../components/section";
import { EmptyState, ErrorState, LoadingState } from "../components/states";
import { StatusBadge } from "../components/status-badge";
import { ControlPlaneError, decideProposal, listDrafts, listProposals } from "../generation-api";
import type { GeneratedDraft, Proposal } from "../generation-types";

function message(error: unknown) { return error instanceof ControlPlaneError ? error.message : "The control plane is unavailable. Try again later."; }

type Filter = "all" | "pending" | "decided";

function EvidenceBlock({ payload }: { payload: Record<string, unknown> }) {
  return <details className="group rounded-lg border bg-muted/40">
    <summary className="cursor-pointer select-none rounded-lg px-3 py-2 text-xs font-medium text-muted-foreground outline-none hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-ring/50">
      Proposal evidence
    </summary>
    <pre aria-label="Proposal evidence" className="max-h-72 overflow-auto border-t p-3 font-mono text-xs leading-relaxed"><code>{JSON.stringify(payload, null, 2)}</code></pre>
  </details>;
}

export function ReviewsDashboard({ apiUrl }: { apiUrl: string }) {
  const [drafts, setDrafts] = useState<GeneratedDraft[] | null>(null);
  const [proposals, setProposals] = useState<Proposal[] | null>(null);
  const [error, setError] = useState("");
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [pending, setPending] = useState<{ proposal: Proposal; approved: boolean } | null>(null);
  const [busy, setBusy] = useState(false);
  const [filter, setFilter] = useState<Filter>("all");
  const load = () => Promise.all([listDrafts(apiUrl, "pending_review"), listProposals(apiUrl)]).then(([nextDrafts, nextProposals]) => { setDrafts(nextDrafts.items); setProposals(nextProposals.items); setError(""); }).catch((nextError) => setError(message(nextError)));
  useEffect(() => { void load(); }, [apiUrl]);
  async function decide() {
    if (!pending) return;
    const id = pending.proposal.id;
    setBusy(true);
    try {
      await decideProposal(apiUrl, id, pending.approved, reasons[id] ?? "");
      setPending(null);
      setReasons((current) => ({ ...current, [id]: "" }));
      await load();
    } catch (nextError) {
      setError(message(nextError));
    } finally {
      setBusy(false);
    }
  }
  if (drafts === null || proposals === null) return <LoadingState title="Loading governed review queue" />;

  const pendingCount = proposals.filter((item) => !item.decision).length;
  const visible = proposals.filter((item) => filter === "all" || (filter === "pending" ? !item.decision : item.decision));

  return <div className="space-y-6">
    {error && <ErrorState title="Unable to load reviews">{error}</ErrorState>}

    <Section title="Generated drafts awaiting a decision">
      {drafts.length === 0
        ? <EmptyState title="No generated drafts are waiting">Approved and rejected drafts remain available through their linked request and run records.</EmptyState>
        : <ul className="divide-y rounded-lg border">
          {drafts.map((draft) => <li key={draft.id} className="space-y-2 p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <strong className="min-w-0 break-words text-sm font-medium">{draft.title}</strong>
              <StatusBadge status={draft.state} />
            </div>
            <p className="min-w-0 break-all text-xs text-muted-foreground">Source hash: <code className="font-mono">{draft.source_hash}</code></p>
            <a href={`/agent?draft=${draft.id}`} className="inline-flex items-center gap-1 text-sm font-medium text-primary underline-offset-4 hover:underline">
              Inspect draft, assumptions, provenance, and decide
            </a>
          </li>)}
        </ul>}
    </Section>

    <Section
      title="Agent proposals"
      description={`${pendingCount} pending of ${proposals.length} total`}
      actions={proposals.length > 0 && <Tabs value={filter} onValueChange={(value) => setFilter(value as Filter)}>
        <TabsList>
          <TabsTrigger value="all">All</TabsTrigger>
          <TabsTrigger value="pending">Pending</TabsTrigger>
          <TabsTrigger value="decided">Decided</TabsTrigger>
        </TabsList>
      </Tabs>}
      contentClassName="space-y-4"
    >
      {proposals.length === 0
        ? <EmptyState title="No proposals yet">Failure triage and healing proposals appear here with their deterministic run evidence.</EmptyState>
        : visible.length === 0
          ? <p className="py-8 text-center text-sm text-muted-foreground">No {filter} proposals.</p>
          : <ul className="space-y-4">
            {visible.map((proposal) => <li key={proposal.id} className="space-y-4 rounded-lg border p-4">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <strong className="min-w-0 flex-1 break-words text-sm font-medium">{proposal.summary}</strong>
                <StatusBadge status={proposal.decision ? (proposal.decision.approved ? "approved" : "rejected") : "pending_review"} />
              </div>
              <div className="space-y-1 text-xs text-muted-foreground">
                <p>Kind: {proposal.kind} · version {proposal.proposal_version}</p>
                <p className="flex flex-wrap items-center gap-x-2 gap-y-1">
                  <a href={`/runs/${proposal.run_id}`} className="inline-flex items-center gap-1 font-medium text-primary underline-offset-4 hover:underline">
                    Open deterministic run evidence<ExternalLink className="size-3" aria-hidden="true" />
                  </a>
                  <span aria-hidden="true">·</span>
                  <span className="min-w-0 break-all">Correlation: <code className="font-mono">{proposal.correlation_id}</code></span>
                </p>
              </div>
              <EvidenceBlock payload={proposal.payload} />
              {proposal.decision
                ? <p className="text-sm">Final decision: {proposal.decision.approved ? "Approved" : "Rejected"} by {proposal.decision.decided_by}{proposal.decision.reason ? ` — ${proposal.decision.reason}` : ""}.</p>
                : <div className="flex flex-col gap-3 border-t pt-4 sm:flex-row sm:items-end">
                  <div className="min-w-0 flex-1 space-y-2">
                    <Label htmlFor={`reason-${proposal.id}`}>Decision reason (optional)</Label>
                    <Input id={`reason-${proposal.id}`} value={reasons[proposal.id] ?? ""} onChange={(event) => setReasons((current) => ({ ...current, [proposal.id]: event.target.value }))} />
                  </div>
                  <div className="flex gap-2">
                    <Button type="button" onClick={() => setPending({ proposal, approved: true })}><Check />Approve proposal</Button>
                    <Button type="button" variant="outline" className="text-destructive hover:text-destructive" onClick={() => setPending({ proposal, approved: false })}><X />Reject proposal</Button>
                  </div>
                </div>}
            </li>)}
          </ul>}
    </Section>

    <ConfirmDialog
      open={pending !== null}
      title={pending?.approved ? "Approve this proposal?" : "Reject this proposal?"}
      description="This decision is final, immutable, and is recorded by the control plane before the queue updates."
      confirmLabel={pending?.approved ? "Approve proposal" : "Reject proposal"}
      tone={pending?.approved ? "default" : "destructive"}
      onConfirm={() => void decide()}
      onCancel={() => setPending(null)}
      busy={busy}
    />
  </div>;
}
