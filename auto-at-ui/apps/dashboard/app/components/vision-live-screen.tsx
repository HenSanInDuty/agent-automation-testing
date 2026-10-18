"use client";

import { useEffect, useRef, useState } from "react";
import { ControlPlaneError, getOperationFrameBlob, getVisionScreen } from "../generation-api";
import type { ExecutedClick, VisualOperation } from "../generation-types";
import { visionFailureMessage } from "./vision-provider-model";
import { advanceClickPreview, clickMarkerPosition, confirmedClick, type ClickPreviewHistory } from "./vision-click-model";
import { VisionClickOverlay } from "./vision-click-overlay";

export function VisionLiveScreen({ apiUrl, sessionId, live, operations, selectedId, follow, onFollow }: {
  apiUrl: string; sessionId: string; live: boolean; operations: VisualOperation[];
  selectedId: string | null; follow: boolean; onFollow: (value: boolean) => void;
}) {
  const latest = operations.at(-1);
  const selected = operations.find((item) => item.id === selectedId);
  const [selection, setSelection] = useState<{ id: string; role: "before" | "after" } | null>(null);
  const role = selection?.id === selected?.id ? selection?.role ?? "before" : "before";
  const frame = follow ? [...operations].reverse().find((item) => item.after.availability === "retained")?.after : selected?.[role];
  const preview = live && follow;
  const history = useRef<ClickPreviewHistory>({ initialized: false, following: false, seen: new Set() });
  const [recentId, setRecentId] = useState<string | null>(null);
  const [loadedRecentId, setLoadedRecentId] = useState<string | null>(null);
  const recent = preview ? operations.find((item) => item.id === recentId && confirmedClick(item, item.before.id)) : undefined;
  useEffect(() => {
    const next = advanceClickPreview(operations, history.current, preview);
    history.current = next.history;
    if (!preview) setRecentId(null);
    else if (next.operation) setRecentId(next.operation.id);
  }, [operations, preview]);
  useEffect(() => {
    if (!recent || loadedRecentId !== recent.id) return;
    const timer = setTimeout(() => setRecentId((id) => id === recent.id ? null : id), 1200);
    return () => clearTimeout(timer);
  }, [recent?.id, loadedRecentId]);
  const saved = frame?.availability === "retained" ? frame.id : null;
  const label = follow ? "Session stopped · last saved screen" : `${role === "before" ? "Before" : "After"} operation ${selected?.sequence ?? ""} · recorded frame`;
  return <section className="workspace-section vision-screen-card" aria-label="Vision browser screen">
    <div className="section-heading"><h2>Website</h2>{!follow && <button type="button" className="button button--secondary" onClick={() => onFollow(true)}>Return to live</button>}</div>
    {!follow && selected && <div className="button-row" aria-label="Frame view">
      {(["before", "after"] as const).map((value) => <button type="button" key={value} className="button button--secondary" aria-pressed={role === value} onClick={() => setSelection({ id: selected.id, role: value })}>{value === "before" ? "Before" : "After"}</button>)}
    </div>}
    <div className="vision-screen-content" hidden={Boolean(recent)}>
      <ScreenImage key={`${apiUrl}:${sessionId}:${preview ? "live" : `${selectedId}:${role}:${saved}:${frame?.availability}`}`} apiUrl={apiUrl} sessionId={sessionId} live={preview} saved={preview ? null : saved} label={label} click={!follow && role === "before" ? confirmedClick(selected, saved) : null} onUnavailable={() => { if (preview) setRecentId(null); }} missing={frame?.availability === "deleted" ? "This frame was deleted." : !follow ? "No saved image is available for this step." : "No saved page image is available."} />
    </div>
    {recent && <div className="vision-screen-content">
      <ScreenImage key={`${sessionId}:${recent.id}:${recent.before.id}`} apiUrl={apiUrl} sessionId={sessionId} live={false} saved={recent.before.id} label={`Recent click · operation ${recent.sequence} · recorded frame`} missing="Click frame unavailable." click={confirmedClick(recent, recent.before.id)} pulse onLoaded={() => setLoadedRecentId(recent.id)} onUnavailable={() => setRecentId((id) => id === recent.id ? null : id)} />
    </div>}
    {!follow && selected?.action_kind === "click" && !confirmedClick(selected, selected.before.id) && <p className="vision-click-caption">Click position unavailable.</p>}
    {!live && follow && latest?.status === "rejected" && <p role="alert">{visionFailureMessage(latest.outcome_code) ?? "The browser action was rejected before execution."}</p>}
    {!live && follow && latest?.status !== "rejected" && latest?.after.availability === "missing" && <p role="alert">The page screenshot could not be captured ({latest.after.reason_code?.replaceAll("_", " ") ?? "capture unavailable"}). Use Reload to start a new session.</p>}
  </section>;
}

function ScreenImage({ apiUrl, sessionId, live, saved, label, missing, click, pulse = false, onLoaded, onUnavailable }: {
  apiUrl: string; sessionId: string; live: boolean; saved?: string | null; label: string; missing: string;
  click?: ExecutedClick | null; pulse?: boolean; onLoaded?: () => void; onUnavailable?: () => void;
}) {
  const [url, setUrl] = useState<string | null>(null);
  const [status, setStatus] = useState("");
  const [image, setImage] = useState<{ url: string; width: number; height: number } | null>(null);
  const [container, setContainer] = useState({ width: 0, height: 0 });
  const viewport = useRef<HTMLDivElement>(null);
  const callbacks = useRef({ onLoaded, onUnavailable });
  callbacks.current = { onLoaded, onUnavailable };
  useEffect(() => {
    const node = viewport.current;
    if (!node) return;
    const measure = () => setContainer({ width: node.clientWidth, height: node.clientHeight });
    const observer = new ResizeObserver(measure);
    observer.observe(node); measure();
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    const abort = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let objectUrl: string | null = null;
    setUrl(null);
    const load = async () => {
      let retry = live;
      try {
        const image = live ? await getVisionScreen(apiUrl, sessionId, abort.signal)
          : saved ? await getOperationFrameBlob(apiUrl, sessionId, saved, abort.signal) : null;
        if (abort.signal.aborted) return;
        if (image) {
          const next = URL.createObjectURL(image);
          if (objectUrl) URL.revokeObjectURL(objectUrl);
          objectUrl = next; setUrl(next);
          setStatus(live ? "Live browser · updates every second" : label);
        } else setStatus(live ? "Waiting for the browser to start…" : "Session stopped · no page screenshot was saved.");
      } catch (error) {
        if (abort.signal.aborted) return;
        const denied = error instanceof ControlPlaneError && [401, 403, 404].includes(error.status);
        if (denied) { setUrl(null); if (objectUrl) URL.revokeObjectURL(objectUrl); objectUrl = null; retry = false; }
        setStatus(denied ? "Screen unavailable or access revoked." : live ? "Screen connection interrupted · retrying. Any displayed image is the last received frame." : "Saved screen unavailable.");
        if (denied || !live) callbacks.current.onUnavailable?.();
      }
      if (retry && !abort.signal.aborted) timer = setTimeout(load, 1000);
    };
    void load();
    return () => { abort.abort(); if (timer) clearTimeout(timer); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [apiUrl, sessionId, live, saved, label]);
  return <><p role="status">{status}</p>
    <div ref={viewport} className="vision-screen-viewport">
      {url ? <img key={url} src={url} alt="Vision browser screen" onLoad={(event) => {
        setImage({ url, width: event.currentTarget.naturalWidth, height: event.currentTarget.naturalHeight });
        callbacks.current.onLoaded?.();
      }} onError={() => { setUrl(null); setImage(null); setStatus("Screen could not be displayed."); callbacks.current.onUnavailable?.(); }} /> : <p>{live ? "Waiting for a browser frame…" : missing}</p>}
      {url && image?.url === url && click && <VisionClickOverlay click={click} image={image} container={container} pulse={pulse} />}
    </div>
    {url && image?.url === url && click && <p className="vision-click-caption">{clickMarkerPosition(click, image, container) ? "Click location · recorded before the action" : "Click position unavailable."}</p>}
  </>;
}
