"use client";

import { useEffect, useRef, useState } from "react";
import { ControlPlaneError, deleteOperationFrames, deleteVisualReplayFrames, getVisualLocators, getVisualTrace, getVisionResult } from "../generation-api";
import type { VisualExploration, VisualLocator, VisualTrace, VisionResult } from "../generation-types";
import { ConfirmDialog } from "./confirm-dialog";
import { VisionLocatorCatalog } from "./vision-locator-catalog";
import { selectedOperation, shouldPollVisionResult } from "./vision-operation-model";
import { VisionOperationLedger } from "./vision-operation-ledger";
import { VisionResultSummary } from "./vision-result-summary";

export function VisionSessionDetail({ apiUrl, session, canDelete }: { apiUrl: string; session: VisualExploration; canDelete: boolean }) {
  const [result, setResult] = useState<VisionResult | null>(null);
  const [trace, setTrace] = useState<VisualTrace | null>(null);
  const [catalog, setCatalog] = useState<VisualLocator[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [more, setMore] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [follow, setFollow] = useState(false);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [deletion, setDeletion] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const expanded = useRef(false);
  const extraRequests = useRef(new Set<AbortController>());
  useEffect(() => () => { extraRequests.current.forEach((abort) => abort.abort()); }, []);
  useEffect(() => {
    const abort = new AbortController(); let timer: ReturnType<typeof setTimeout> | undefined;
    const load = async () => {
      let pending = true;
      try {
        const [nextResult, nextTrace, locators] = await Promise.all([
          getVisionResult(apiUrl, session.id, abort.signal), getVisualTrace(apiUrl, session.id, abort.signal), getVisualLocators(apiUrl, session.id, undefined, abort.signal),
        ]);
        if (abort.signal.aborted) return;
        setResult(nextResult); setTrace(nextTrace); setError("");
        setCatalog((items) => [...new Map([...items, ...locators.items].map((item) => [item.id, item])).values()]);
        if (!expanded.current) { setCursor(locators.next_id); setMore(locators.has_more); }
        pending = shouldPollVisionResult(nextResult);
      } catch (reason) {
        if (abort.signal.aborted) return;
        setError(reason instanceof ControlPlaneError ? reason.message : "Exploration evidence is unavailable.");
        if (reason instanceof ControlPlaneError && [403, 404].includes(reason.status)) { setResult(null); setTrace(null); setCatalog([]); pending = false; }
      }
      if (pending && !abort.signal.aborted) timer = setTimeout(load, 5_000);
    };
    void load();
    return () => { abort.abort(); if (timer) clearTimeout(timer); };
  }, [apiUrl, session.id, refresh]);
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
  return <div aria-label="Saved Vision session">
    {error && <p role="alert">{error}</p>}
    {result ? <VisionResultSummary result={result} apiUrl={apiUrl} /> : !error && <p role="status">Loading exploration result…</p>}
    {trace?.trace_version === "v4" && !deleting && <VisionOperationLedger apiUrl={apiUrl} sessionId={session.id} items={trace.items} locators={trace.locators} branches={result?.handoffs.at(-1)?.branches ?? []} selectedId={selected} onSelect={(id) => { setFollow(false); setSelected(id); }} follow={follow} onFollow={setFollow} onDelete={canDelete ? setDeletion : undefined} />}
    {trace?.trace_version === "v4" && <VisionLocatorCatalog items={catalog} hasMore={more} onMore={() => void loadMore()} />}
    <div className="button-row"><button type="button" className="button button--secondary" onClick={() => setRefresh((value) => value + 1)}>Refresh saved result</button>{canDelete && trace?.items.length ? <button type="button" className="button button--danger" onClick={() => setDeletion("all")}>Delete all evidence</button> : null}</div>
    <ConfirmDialog open={deletion !== null} title="Delete private evidence?" description="The selected frame bytes will be permanently deleted. The recorded operations remain in the history." confirmLabel="Delete evidence" onConfirm={() => void remove()} onCancel={() => setDeletion(null)} busy={deleting} />
  </div>;
}
