"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { Download, XCircle } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { artifactArchiveDownloadUrl, artifactArchiveEntriesUrl, artifactDownloadUrl } from "../../api-client";
import { ActivityTimeline } from "../../components/activity-timeline";
import { PageHeader } from "../../components/page-header";
import { ErrorState } from "../../components/states";
import { StatusBadge } from "../../components/status-badge";
import { getGenerationRequest, listProposals } from "../../generation-api";
import type { Proposal } from "../../generation-types";
import { ActionLedger } from "../_components/action-ledger";
import { ArtifactsSection, previewType, type ArchiveEntry } from "../_components/artifacts-section";
import { ReviewSection, TriageSection, WhatRanSection } from "../_components/run-sections";
import { RunSummary } from "../_components/run-summary";
import { activities, artifacts, browserActions, cancelRun, createRevisedDraft, run, runReport, type Activity, type Artifact, type BrowserAction, type RevisedDraftRequest, type Run, type RunReport } from "../../run-api";

export default function RunDetailPage() {
  const apiUrl = process.env.NEXT_PUBLIC_CONTROL_PLANE_URL ?? "";
  const id = String(useParams<{ id: string }>().id);
  const [item, setItem] = useState<Run | null>(null);
  const [evidence, setEvidence] = useState<Artifact[]>([]);
  const [browserActionLedger, setBrowserActionLedger] = useState<BrowserAction[]>([]);
  const [report, setReport] = useState<RunReport | null>(null);
  const [reportMissing, setReportMissing] = useState(false);
  const [triageActivities, setTriageActivities] = useState<Activity[]>([]);
  const [triageProposals, setTriageProposals] = useState<Proposal[]>([]);
  const [revisionRequest, setRevisionRequest] = useState<RevisedDraftRequest | null>(null);
  const [notice, setNotice] = useState("");
  const [preview, setPreview] = useState<Artifact | null>(null);
  const [previewContent, setPreviewContent] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [archiveEntries, setArchiveEntries] = useState<ArchiveEntry[] | null>(null);

  useEffect(() => {
    Promise.all([run(apiUrl, id), artifacts(apiUrl, id), browserActions(apiUrl, id), activities(apiUrl, id), listProposals(apiUrl, undefined, id), runReport(apiUrl, id).catch((error: { status?: number }) => { if (error.status === 404) { setReportMissing(true); return null; } throw error; })])
      .then(([next, files, nextBrowserActions, nextActivities, nextProposals, nextReport]) => { setItem(next); setEvidence(files); setBrowserActionLedger(nextBrowserActions); setTriageActivities(nextActivities.filter((activity) => activity.source === "triage")); setTriageProposals(nextProposals.items); setReport(nextReport); })
      .catch((error: Error) => setNotice(error.message));
  }, [apiUrl, id]);

  useEffect(() => {
    if (!revisionRequest || !["queued", "generating"].includes(revisionRequest.state)) return;
    const timer = window.setInterval(() => {
      getGenerationRequest(apiUrl, revisionRequest.id)
        .then((next) => setRevisionRequest(next))
        .catch((error: Error) => setNotice(error.message));
    }, 2000);
    return () => window.clearInterval(timer);
  }, [apiUrl, revisionRequest]);

  if (!item) {
    return (
      <>
        <PageHeader eyebrow="Execution" title="Run detail" description={notice ? "Unable to load this run." : "Loading deterministic run evidence."} />
        {notice ? (
          <ErrorState title="Run could not be loaded">{notice}</ErrorState>
        ) : (
          <div className="space-y-3" aria-busy="true" aria-label="Loading run">
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-64 w-full" />
          </div>
        )}
      </>
    );
  }
  const cancellable = item.status === "queued" || item.status === "running";
  const triageStatus = triageProposals.length > 0 ? "completed" : triageActivities.at(-1)?.status;
  const openPreview = async (file: Artifact) => {
    setPreview(file); setPreviewContent(null); setPreviewUrl(null); setArchiveEntries(null); setNotice("");
    try {
      if (file.uri.toLowerCase().endsWith(".zip") || file.content_type === "application/zip") {
        const response = await fetch(artifactArchiveEntriesUrl(apiUrl, item.id, file.id), { credentials: "include" });
        if (!response.ok) throw new Error("Unable to inspect this archive.");
        setArchiveEntries(await response.json() as ArchiveEntry[]);
        return;
      }
      const response = await fetch(artifactDownloadUrl(apiUrl, item.id, file.id), { credentials: "include" });
      if (!response.ok) throw new Error("Unable to load this artifact preview.");
      if (previewType(file) === "text") setPreviewContent(await response.text());
      else setPreviewUrl(URL.createObjectURL(await response.blob()));
    } catch (error) { setPreview(null); setNotice(error instanceof Error ? error.message : "Unable to load this artifact preview."); }
  };
  const closePreview = () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreview(null); setPreviewContent(null); setPreviewUrl(null); setArchiveEntries(null);
  };
  const failed = item.status === "failed" || item.status === "errored";
  return (
    <>
      <PageHeader
        eyebrow="Execution"
        title={`Run ${item.id.slice(0, 8)}`}
        description="Immutable request, deterministic result, and verified evidence."
        actions={
          <>
            <StatusBadge status={item.status} className="px-3 py-1 text-sm" />
            {evidence.length > 0 && (
              <Button asChild variant="outline">
                <a href={artifactArchiveDownloadUrl(apiUrl, item.id)}><Download /> Download archive</a>
              </Button>
            )}
            {cancellable && (
              <Button
                variant="destructive"
                onClick={() => cancelRun(apiUrl, item.id).then(setItem).catch((error: Error) => setNotice(error.message))}
              >
                <XCircle /> Cancel run
              </Button>
            )}
          </>
        }
      />
      <div className="space-y-6">
        <RunSummary item={item} evidenceCount={evidence.length} actionCount={browserActionLedger.length} />
        <Tabs defaultValue="overview" className="gap-5">
          <TabsList className="h-auto w-full flex-wrap justify-start sm:w-fit">
            <TabsTrigger value="overview">Overview</TabsTrigger>
            <TabsTrigger value="evidence">Evidence</TabsTrigger>
            <TabsTrigger value="activity">Activity</TabsTrigger>
          </TabsList>
          <TabsContent value="overview" className="space-y-6">
            <WhatRanSection item={item} />
            {failed && (
              <TriageSection
                status={triageStatus}
                proposals={triageProposals}
                revisionRequest={revisionRequest}
                onCreateDraft={() => createRevisedDraft(apiUrl, item.id).then(setRevisionRequest).catch((error: Error) => setNotice(error.message))}
              />
            )}
            <ReviewSection apiUrl={apiUrl} runId={item.id} report={report} reportMissing={reportMissing} cancellable={cancellable} evidence={evidence} />
          </TabsContent>
          <TabsContent value="evidence" className="space-y-6">
            <ArtifactsSection
              apiUrl={apiUrl}
              runId={item.id}
              evidence={evidence}
              preview={preview}
              previewContent={previewContent}
              previewUrl={previewUrl}
              archiveEntries={archiveEntries}
              onPreview={(file) => void openPreview(file)}
              onClose={closePreview}
            />
            <ActionLedger apiUrl={apiUrl} runId={item.id} actions={browserActionLedger} />
          </TabsContent>
          <TabsContent value="activity">
            <ActivityTimeline apiUrl={apiUrl} runId={item.id} live={cancellable} />
          </TabsContent>
        </Tabs>
        {notice && (
          <Alert variant="destructive" role="alert">
            <AlertDescription>{notice}</AlertDescription>
          </Alert>
        )}
      </div>
    </>
  );
}
