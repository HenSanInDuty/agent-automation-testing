"use client";

import { useEffect, useRef, useState } from "react";
import { ControlPlaneError, deleteOperationFrames, deleteVisualReplayFrames, getVisualLocators, getVisualTrace, getVisionResult } from "../generation-api";
import type { VisualExploration, VisualLocator, VisualTrace, VisionResult } from "../generation-types";
import { ConfirmDialog } from "./confirm-dialog";
import { VisionLocatorCatalog } from "./vision-locator-catalog";
import { selectedOperation, shouldPollVisionResult } from "./vision-operation-model";
import { VisionOperationLedger } from "./vision-operation-ledger";
import { VisionResultSummary } from "./vision-result-summary";
import { visionProviderLabel } from "./vision-provider-model";
import { VisionLiveScreen } from "./vision-live-screen";
import { VisionProgressTimeline } from "./vision-progress-timeline";

export function VisionSessionDetail({ apiUrl, session, canDelete, onActivity }: { apiUrl: string; session: VisualExploration; canDelete: boolean; onActivity: () => void }) {
  const [result, setResult] = useState<VisionResult | null>(null);
  const [trace, setTrace] = useState<VisualTrace | null>(null);
  const [catalog, setCatalog] = useState<VisualLocator[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [more, setMore] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [follow, setFollow] = useState(true);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [deletion, setDeletion] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const reportRef = useRef<HTMLDetailsElement>(null);
  const expanded = useRef(false);
  const extraRequests = useRef(new Set<AbortController>());
  useEffect(() => () => { extraRequests.current.forEach((abort) => abort.abort()); }, []);
  useEffect(() => {
    const abort = new AbortController(); let timer: ReturnType<typeof setTimeout> | undefined;
    const load = async () => {
      let pending = true;
      try {
        const [nextResult, nextTrace, locators] = await Promise.allSettled([
          getVisionResult(apiUrl, session.id, abort.signal), getVisualTrace(apiUrl, session.id, abort.signal), getVisualLocators(apiUrl, session.id, undefined, abort.signal),
        ]);
        if (abort.signal.aborted) return;
        const denied = [nextResult, nextTrace, locators].find((item) => item.status === "rejected" && item.reason instanceof ControlPlaneError && [401, 403, 404].includes(item.reason.status));
        if (denied?.status === "rejected") throw denied.reason;
        if (nextResult.status === "fulfilled") { setResult(nextResult.value); pending = shouldPollVisionResult(nextResult.value); }
        if (nextTrace.status === "fulfilled") setTrace(nextTrace.value);
        if (locators.status === "fulfilled") {
          const page = locators.value;
          setCatalog((items) => [...new Map([...items, ...page.items].map((item) => [item.id, item])).values()]);
          if (!expanded.current) { setCursor(page.next_id); setMore(page.has_more); }
        }
        setError([nextResult, nextTrace, locators].some((item) => item.status === "rejected") ? "Some saved evidence is unavailable. Live progress is shown independently." : "");
      } catch (reason) {
        if (abort.signal.aborted) return;
        setError(reason instanceof ControlPlaneError ? reason.message : "Exploration evidence is unavailable.");
        if (reason instanceof ControlPlaneError && [401, 403, 404].includes(reason.status)) { setResult(null); setTrace(null); setCatalog([]); pending = false; }
      }
      if (pending && !abort.signal.aborted) timer = setTimeout(load, 5_000);
    };
    void load();
    return () => { abort.abort(); if (timer) clearTimeout(timer); };
  }, [apiUrl, session.id, session.state, refresh]);
  useEffect(() => { if (trace) setSelected((id) => selectedOperation(trace.items, id, follow)); }, [trace, follow]);
  async function loadMore() {
    const abort = new AbortController(); extraRequests.current.add(abort);
    try { const page = await getVisualLocators(apiUrl, session.id, cursor ?? undefined, abort.signal); if (abort.signal.aborted) return; expanded.current = true; setCatalog((items) => [...new Map([...items, ...page.items].map((item) => [item.id, item])).values()]); setCursor(page.next_id); setMore(page.has_more); }
    catch { if (!abort.signal.aborted) setError("Locator catalog is unavailable."); }
    finally { extraRequests.current.delete(abort); }
  }
  async function remove() {
    if (!deletion) return;
    setDeleting(true);
    try {
      await deleteOperationFrames(apiUrl, session.id, deletion === "all" ? undefined : deletion);
      if (deletion === "all") await deleteVisualReplayFrames(apiUrl, session.id);
      setTrace(null); setRefresh((value) => value + 1);
    } catch { setError("Evidence deletion is unavailable. Retry to finish remaining frames."); }
    finally { setDeletion(null); setDeleting(false); }
  }
  return <div className="vision-session-detail" aria-label="Saved Vision session">
    {session.trace_version === "v4" && <div className="vision-live-workspace">
      <VisionLiveScreen apiUrl={apiUrl} sessionId={session.id} live={["queued", "running"].includes(session.state)} operations={deleting ? [] : trace?.items ?? []} selectedId={selected} follow={follow} onFollow={setFollow} />
      <VisionOperationLedger items={trace?.items ?? []} locators={trace?.locators ?? []} branches={result?.handoffs.at(-1)?.branches ?? []} selectedId={selected} onSelect={(id) => { setFollow(false); setSelected(id); }} follow={follow} onFollow={setFollow} />
    </div>}
    {error && <p role="alert">{error}</p>}
    {result ? <VisionResultSummary result={result} apiUrl={apiUrl} compact /> : !error && <p role="status">Loading exploration result…</p>}
    <a className="vision-report-link" href={`#vision-report-${session.id}`} onClick={() => { if (reportRef.current) reportRef.current.open = true; }}>View exploration report</a>
    <details ref={reportRef} className="workspace-section"><summary>Exploration report</summary>
      {result && <VisionResultSummary result={result} apiUrl={apiUrl} />}
    </details>
    <details className="workspace-section"><summary>Technical details</summary>
    <p>Session: <code>{session.id}</code></p>
    <p>Session provider: {visionProviderLabel(session.provider)} · Model: <code>{session.model}</code></p>
    <p>Correlation: <code>{session.correlation_id}</code></p>
    {session.trace_version === "v4" && <VisionProgressTimeline apiUrl={apiUrl} sessionId={session.id} live={["queued", "running"].includes(session.state)} onActivity={onActivity} />}
    {trace?.trace_version === "v4" && <VisionLocatorCatalog items={catalog} hasMore={more} onMore={() => void loadMore()} />}
    <div className="button-row"><button type="button" className="button button--secondary" onClick={() => setRefresh((value) => value + 1)}>Refresh saved result</button>{canDelete && trace?.items.length ? <button type="button" className="button button--danger" onClick={() => setDeletion("all")}>Delete all evidence</button> : null}</div>
    </details>
    <ConfirmDialog open={deletion !== null} title="Delete private evidence?" description="The selected frame bytes will be permanently deleted. The recorded operations remain in the history." confirmLabel="Delete evidence" onConfirm={() => void remove()} onCancel={() => setDeletion(null)} busy={deleting} />
  </div>;
}
