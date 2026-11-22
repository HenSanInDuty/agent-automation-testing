"use client";

import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { getVisualReplayFrameBlob } from "../generation-api";
import type { VisualReplayFrame, VisualTrajectory as Trajectory } from "../generation-types";
import { Hint } from "./agent-ui";
import { boundedStep, defaultTrajectoryPath, orderedAlternatives, replayMarkerPosition, trajectoryPathForEdge } from "./vision-replay-model";

type FramePair = { before: string | null; after: string | null };

export function VisionTrajectory({ apiUrl, sessionId, trajectory, frames, selectedFrame, onSelectFrame }: {
  apiUrl: string; sessionId: string; trajectory: Trajectory; frames: VisualReplayFrame[];
  selectedFrame: VisualReplayFrame | null; onSelectFrame: (frame: VisualReplayFrame) => void;
}) {
  const [choice, setChoice] = useState<string | null>(null);
  const path = useMemo(() => choice ? trajectoryPathForEdge(trajectory, choice) : defaultTrajectoryPath(trajectory), [trajectory, choice]);
  const [step, setStep] = useState(0);
  const [errors, setErrors] = useState({ before: false, after: false });
  const [images, setImages] = useState<FramePair>({ before: null, after: null });
  const states = useMemo(() => new Map(trajectory.states.map((state) => [state.id, state])), [trajectory]);
  useEffect(() => { setStep(0); setChoice(null); }, [sessionId]);
  const edge = path[step];
  const before = edge ? states.get(edge.parent_state_id) : undefined;
  const after = edge?.child_state_id ? states.get(edge.child_state_id) : undefined;
  const beforeFrame = before?.frame_id ? frames.find((frame) => frame.id === before.frame_id) : undefined;
  const afterFrame = after?.frame_id ? frames.find((frame) => frame.id === after.frame_id) : undefined;
  useEffect(() => {
    let disposed = false;
    const urls: string[] = [];
    setImages({ before: null, after: null });
    setErrors({ before: false, after: false });
    for (const [role, frame] of [["before", beforeFrame], ["after", afterFrame]] as const) {
      if (!frame) continue;
      void getVisualReplayFrameBlob(apiUrl, sessionId, frame.id).then((blob) => {
        if (disposed) return;
        const url = URL.createObjectURL(blob); urls.push(url);
        setImages((current) => ({ ...current, [role]: url }));
      }).catch(() => { if (!disposed) setErrors((current) => ({ ...current, [role]: true })); });
    }
    return () => { disposed = true; urls.forEach((url) => URL.revokeObjectURL(url)); };
  }, [apiUrl, sessionId, beforeFrame?.id, afterFrame?.id]);

  if (!trajectory.trajectory_available) return <Hint>{trajectory.legacy_label}</Hint>;
  if (!edge) return <Hint>No observed branch is available yet. The latest captured state remains available below.</Hint>;
  const alternatives = before ? orderedAlternatives(trajectory, before.id) : [];
  const marker = replayMarkerPosition(edge.action);
  const frameBox = "relative inline-block max-w-full overflow-hidden rounded-lg border bg-muted/40";
  return <section aria-label="Exploration evidence trajectory" tabIndex={0} className="grid gap-4 rounded-lg outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50" onKeyDown={(event) => {
    if ((event.target as HTMLElement).closest("input,textarea,select,[contenteditable=true]")) return;
    if (event.key === "ArrowLeft") setStep((value) => boundedStep(value - 1, path.length));
    else if (event.key === "ArrowRight") setStep((value) => boundedStep(value + 1, path.length));
    else if (event.key === "Home") setStep(0);
    else if (event.key === "End") setStep(Math.max(0, path.length - 1));
    else return;
    event.preventDefault();
  }}>
    <h3 className="text-base font-semibold tracking-tight">Exploration evidence</h3>
    <Hint>This is saved legacy exploration evidence. Choosing an alternative changes the displayed path; it does not operate the browser.</Hint>
    <p className="text-sm">Step {step + 1} of {path.length} · <strong>{edge.action.kind} attempted</strong> · {edge.status}{edge.duration_ms ? ` · ${edge.duration_ms}ms` : ""}{edge.url_change === "changed" ? " · page changed" : ""}</p>
    <div className="flex flex-wrap gap-2"><Button type="button" variant="outline" size="sm" onClick={() => setStep((value) => boundedStep(value - 1, path.length))} disabled={step === 0}>Previous</Button><Button type="button" variant="outline" size="sm" onClick={() => setStep((value) => boundedStep(value + 1, path.length))} disabled={step >= path.length - 1}>Next</Button></div>
    <div className="grid items-center gap-4 min-[700px]:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)]" aria-label={`State transition ${step + 1}`}>
      <div className="grid min-w-0 gap-2"><h4 className="text-sm font-medium">Before · state {before?.sequence ?? "unavailable"}</h4>{images.before ? <div className={frameBox}>{marker && <span className="pointer-events-none absolute z-[1] -translate-x-1/2 -translate-y-1/2 rounded-sm border-2 border-[#f4c542] bg-black/70 px-1.5 py-0.5 text-[11px] text-white" style={marker}>attempted {edge.action.kind}</span>}<img className="block h-auto max-w-full" src={images.before} alt={`State before ${edge.action.kind}`} /></div> : <Hint>{!beforeFrame ? "Before frame missing or deleted." : errors.before ? "Before frame unavailable." : "Loading before frame…"}</Hint>}</div>
      <p className="text-center text-sm font-medium text-muted-foreground max-[699px]:rotate-90">↓<br />{edge.action.kind}<br /><small className="font-normal">{edge.status}</small></p>
      <div className="grid min-w-0 content-start gap-2"><h4 className="text-sm font-medium">After · state {after?.sequence ?? "unavailable"}</h4>{after && images.after ? <div className={frameBox}><img className="block h-auto max-w-full" src={images.after} alt={`State after ${edge.action.kind}`} /></div> : <Hint>{afterFrame ? errors.after ? "After frame unavailable." : "Loading after frame…" : `No after frame (${edge.outcome_code ?? edge.status}).`}</Hint>}{afterFrame && <div><Button variant="outline" size="sm" type="button" onClick={() => onSelectFrame(afterFrame)}>View this frame</Button></div>}</div>
    </div>
    <div className="flex flex-wrap gap-2" role="group" aria-label="Branch alternatives">{alternatives.map((item) => <Button type="button" variant={item === edge ? "secondary" : "outline"} size="sm" key={item.id} onClick={() => { const next = trajectoryPathForEdge(trajectory, item.id); setChoice(item.id); setStep(Math.max(0, next.findIndex((edge) => edge.id === item.id))); }}>{item === edge ? "Selected" : "Alternative"}: {item.action.kind} · {item.status}{item.child_state_id ? " · after frame saved" : ""}</Button>)}</div>
    <div className="flex flex-wrap gap-1.5" role="group" aria-label="Path scrubber">{path.map((item, index) => <Button key={item.id} type="button" variant={index === step ? "secondary" : "outline"} size="xs" aria-current={index === step ? "step" : undefined} onClick={() => setStep(index)}>{index + 1}. {item.action.kind}</Button>)}</div>
    {selectedFrame && <Hint>Current gallery selection: state {selectedFrame.sequence}.</Hint>}
  </section>;
}
