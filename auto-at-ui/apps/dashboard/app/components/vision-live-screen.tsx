"use client";

import { ChevronRight } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { ControlPlaneError, getOperationFrameBlob, getVisionScreen } from "../generation-api";
import type { ExecutedClick, VisualLocator, VisualOperation, VisionProgressActivity } from "../generation-types";
import { Hint, Notice, Panel } from "./agent-ui";
import { visionFailureMessage } from "./vision-provider-model";
import { advanceClickPreview, verifiedClickTarget, verifiedTargetPosition, clickMarkerPosition, confirmedClick, confirmedClickTarget, type ClickPreviewHistory } from "./vision-click-model";
import { clickTargetClass, VisionClickOverlay } from "./vision-click-overlay";
import { operationLabel, operationStatus } from "./vision-operation-model";
import { isVisionModelPending, visionModelWaitLabel, visionProgressMetrics } from "./vision-progress-timeline-model";

export function VisionLiveScreen({ apiUrl, sessionId, live, operations, locators, selectedId, follow, onFollow, onSelect, progress, completionReason }: {
  apiUrl: string; sessionId: string; live: boolean; operations: VisualOperation[]; locators: VisualLocator[];
  selectedId: string | null; follow: boolean; onFollow: (value: boolean) => void; onSelect: (id: string) => void;
  progress?: VisionProgressActivity | null; completionReason?: string | null;
}) {
  const latest = operations.at(-1);
  const lastClick = [...operations].reverse().find((item) => confirmedClick(item, item.before.id) || verifiedClickTarget(item, locators.find((locator) => locator.id === item.locator_id), item.before.id));
  const stoppedClick = !live && follow ? lastClick : undefined;
  const selected = operations.find((item) => item.id === selectedId);
  const [selection, setSelection] = useState<{ id: string; role: "before" | "after" } | null>(null);
  const role = selection?.id === selected?.id ? selection?.role ?? "before" : "before";
  const frame = stoppedClick?.before ?? (follow ? [...operations].reverse().find((item) => item.after.availability === "retained")?.after : selected?.[role]);
  const preview = live && follow;
  const history = useRef<ClickPreviewHistory>({ initialized: false, following: false, seen: new Set() });
  const [recentId, setRecentId] = useState<string | null>(null);
  const [loadedRecentId, setLoadedRecentId] = useState<string | null>(null);
  const recent = preview ? operations.find((item) => item.id === recentId && confirmedClick(item, item.before.id)) : undefined;
  const activity = recent ?? stoppedClick ?? (follow ? latest : selected);
  const activityLocator = locators.find((item) => item.id === activity?.locator_id && item.operation_id === activity?.id);
  const busy = live && follow && Boolean(activity && ["prepared", "executing"].includes(activity.status));
  const thinking = live && follow && !recent && isVisionModelPending(progress, latest);
  const stopped = !live && follow && completionReason;
  useEffect(() => {
    const next = advanceClickPreview(operations, history.current, preview);
    history.current = next.history;
    if (!preview) setRecentId(null);
    else if (next.operation) setRecentId(next.operation.id);
  }, [operations, preview]);
  useEffect(() => {
    if (!recent || loadedRecentId !== recent.id) return;
    const timer = setTimeout(() => setRecentId((id) => id === recent.id ? null : id), 3000);
    return () => clearTimeout(timer);
  }, [recent?.id, loadedRecentId]);
  const saved = frame?.availability === "retained" ? frame.id : null;
  const label = stoppedClick ? `Click operation ${stoppedClick.sequence} · recorded click location` : follow ? "Session stopped · last saved screen" : `${role === "before" ? "Before" : "After"} operation ${selected?.sequence ?? ""} · recorded frame`;
  const lastClickLocator = lastClick ? locators.find((item) => item.id === lastClick.locator_id) : undefined;
  return <Panel aria-label="Vision browser screen" title="Website" className="min-[900px]:h-[clamp(28rem,40vw,34rem)]"
    actions={!follow && <Button type="button" size="sm" variant="outline" onClick={() => onFollow(true)}>Return to live</Button>}>
    <div className={cn(
      "vision-screen-activity flex items-center justify-between gap-3 rounded-lg border border-l-4 px-3 py-2 text-xs",
      stopped ? "border-warning/40 border-l-warning bg-warning/10" : "border-info/30 border-l-info bg-info/10",
    )}>
      <div role="status" aria-live="polite" aria-atomic="true" className="grid min-w-0 gap-0.5 [overflow-wrap:anywhere]">
        <small className="flex items-center gap-1.5 text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
          {(busy || thinking) && <span aria-hidden="true" className="size-1.5 animate-pulse rounded-full bg-info" />}
          {stopped ? "Exploration stopped" : thinking ? "Agent is thinking" : recent ? "Recent click" : !follow ? "Selected action" : busy ? "Agent is acting" : live ? "Latest action" : "Last action"}
        </small>
        {thinking && <><strong className="text-sm font-medium">{visionModelWaitLabel(progress)}</strong><span className="text-muted-foreground">The page stays still while the model chooses the next action.</span>{visionProgressMetrics(progress) && <span className="text-muted-foreground">{visionProgressMetrics(progress)}</span>}</>}
        {stopped && <span className="text-foreground/80">{visionFailureMessage(completionReason) ?? "Exploration stopped. Check the exploration report for the reason."}</span>}
        <strong className="text-sm font-medium">{activity ? `Step ${activity.sequence}: ${operationLabel(activity, activityLocator)}` : live ? "Waiting for the agent’s first action…" : "No browser action recorded"}</strong>
        {activity && <span className="text-muted-foreground">{operationStatus(activity.status)}</span>}
      </div>
      {follow && activity && <Button type="button" size="xs" variant="outline" className="shrink-0 bg-background/70" onClick={() => { setSelection({ id: activity.id, role: "before" }); onSelect(activity.id); }}>Show action</Button>}
    </div>
    {!follow && selected && <div className="flex gap-1.5" role="group" aria-label="Frame view">
      {(["before", "after"] as const).map((value) => <Button type="button" key={value} size="sm" variant={role === value ? "secondary" : "outline"} className={cn(role === value && "ring-1 ring-ring/40")} aria-pressed={role === value} onClick={() => setSelection({ id: selected.id, role: value })}>{value === "before" ? "Before" : "After"}</Button>)}
    </div>}
    <div className="vision-screen-content flex min-h-0 flex-col min-[900px]:flex-1" hidden={Boolean(recent)}>
      <ScreenImage key={`${apiUrl}:${sessionId}:${preview ? "live" : `${selectedId}:${role}:${saved}:${frame?.availability}`}`} apiUrl={apiUrl} sessionId={sessionId} live={preview} saved={preview ? null : saved} label={label} click={stoppedClick ? confirmedClick(stoppedClick, saved) : !follow && role === "before" ? confirmedClick(selected, saved) : null} target={stoppedClick ? (confirmedClickTarget(stoppedClick, activityLocator, saved) ?? verifiedClickTarget(stoppedClick, activityLocator, saved)) : !follow && role === "before" ? (confirmedClickTarget(selected, activityLocator, saved) ?? verifiedClickTarget(selected, activityLocator, saved)) : null} onUnavailable={() => { if (preview) setRecentId(null); }} missing={frame?.availability === "deleted" ? "This frame was deleted." : !follow ? "No saved image is available for this step." : "No saved page image is available."} />
    </div>
    {recent && <div className="vision-screen-content flex min-h-0 flex-col min-[900px]:flex-1">
      <ScreenImage key={`${sessionId}:${recent.id}:${recent.before.id}`} apiUrl={apiUrl} sessionId={sessionId} live={false} saved={recent.before.id} label={`Recent click · operation ${recent.sequence} · recorded frame`} missing="Click frame unavailable." click={confirmedClick(recent, recent.before.id)} target={confirmedClickTarget(recent, activityLocator, recent.before.id)} pulse onLoaded={() => setLoadedRecentId(recent.id)} onUnavailable={() => setRecentId((id) => id === recent.id ? null : id)} />
    </div>}
    {live && follow && lastClick && !recent && <details className="vision-last-click group shrink-0 rounded-lg border bg-muted/30 px-3 py-2" open>
      <summary className="flex cursor-pointer list-none items-center gap-2 text-xs font-medium text-muted-foreground outline-none select-none hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-ring/50 [&::-webkit-details-marker]:hidden"><ChevronRight className="size-3.5 transition-transform group-open:rotate-90" aria-hidden="true" />Last confirmed click — step {lastClick.sequence}</summary>
      <div className="mt-2">
        <ScreenImage compact key={`confirmed:${sessionId}:${lastClick.id}`} apiUrl={apiUrl} sessionId={sessionId} live={false} saved={lastClick.before.id} label={`Click operation ${lastClick.sequence} · recorded click location`} missing="Click frame unavailable." click={confirmedClick(lastClick, lastClick.before.id)} target={confirmedClickTarget(lastClick, lastClickLocator, lastClick.before.id) ?? verifiedClickTarget(lastClick, lastClickLocator, lastClick.before.id)} />
      </div>
    </details>}
    {!follow && selected?.action_kind === "click" && !confirmedClick(selected, selected.before.id) && <Hint className="text-xs">Click position unavailable.</Hint>}
    {!live && follow && latest?.status === "rejected" && <Notice tone="danger" role="alert">{visionFailureMessage(latest.outcome_code) ?? "The browser action was rejected before execution."}</Notice>}
    {!live && follow && latest?.status !== "rejected" && latest?.after.availability === "missing" && <Notice tone="warning" role="alert">The page screenshot could not be captured ({latest.after.reason_code?.replaceAll("_", " ") ?? "capture unavailable"}). Use Reload to start a new session.</Notice>}
  </Panel>;
}

function ScreenImage({ apiUrl, sessionId, live, saved, label, missing, click, target, pulse = false, compact = false, onLoaded, onUnavailable }: {
  apiUrl: string; sessionId: string; live: boolean; saved?: string | null; label: string; missing: string;
  click?: ExecutedClick | null; pulse?: boolean; compact?: boolean; onLoaded?: () => void; onUnavailable?: () => void;
  target?: VisualLocator["bounding_box"];
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
  const targetBounds = image && target ? verifiedTargetPosition(target, image, container) : null;
  // A "browser chrome" frame: window dots plus the status line where an address bar would be.
  return <div className={cn("flex min-h-0 flex-col overflow-hidden rounded-lg border bg-background", !compact && "min-[900px]:flex-1")}>
    <div className="flex items-center gap-3 border-b bg-muted/60 px-3 py-1.5">
      <span className="flex shrink-0 gap-1.5" aria-hidden="true"><span className="size-2.5 rounded-full bg-destructive/50" /><span className="size-2.5 rounded-full bg-warning/60" /><span className="size-2.5 rounded-full bg-success/50" /></span>
      <p role="status" className="min-w-0 flex-1 rounded-md bg-background px-2.5 py-0.5 text-xs leading-snug text-muted-foreground [overflow-wrap:anywhere]">{status}</p>
    </div>
    <div ref={viewport} className={cn("relative grid min-h-0 place-items-center overflow-hidden bg-muted/40", compact ? "h-36" : "aspect-video min-[900px]:aspect-auto min-[900px]:flex-1")}>
      {url ? <img key={url} src={url} alt="Vision browser screen" className="block size-full min-h-0 object-contain" onLoad={(event) => {
        setImage({ url, width: event.currentTarget.naturalWidth, height: event.currentTarget.naturalHeight });
        callbacks.current.onLoaded?.();
      }} onError={() => { setUrl(null); setImage(null); setStatus("Screen could not be displayed."); callbacks.current.onUnavailable?.(); }} /> : <p className="p-4 text-center text-sm text-muted-foreground">{live ? "Waiting for a browser frame…" : missing}</p>}
      {url && image?.url === url && click && <VisionClickOverlay click={click} image={image} container={container} pulse={pulse} target={target} />}
      {url && image?.url === url && !click && targetBounds && <span aria-hidden="true" data-testid="vision-click-target" className={clickTargetClass} style={targetBounds} />}
    </div>
    {url && image?.url === url && !click && targetBounds && <p className="border-t px-3 py-1.5 text-xs text-muted-foreground">Verified click target: exact click position was not recorded</p>}
    {url && image?.url === url && click && <p className="border-t px-3 py-1.5 text-xs text-muted-foreground">{clickMarkerPosition(click, image, container) ? "Click location · recorded before the action" : "Click position unavailable."}</p>}
  </div>;
}
