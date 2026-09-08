"use client";

import { useEffect, useMemo, useState } from "react";
import { getVisualReplayFrameBlob } from "../generation-api";
import type { VisualReplayFrame, VisualTrajectory as Trajectory } from "../generation-types";
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

  if (!trajectory.trajectory_available) return <p>{trajectory.legacy_label}</p>;
  if (!edge) return <p>No observed branch is available yet. The latest captured state remains available below.</p>;
  const alternatives = before ? orderedAlternatives(trajectory, before.id) : [];
  const marker = replayMarkerPosition(edge.action);
  return <section aria-label="Exploration evidence trajectory" tabIndex={0} onKeyDown={(event) => {
    if ((event.target as HTMLElement).closest("input,textarea,select,[contenteditable=true]")) return;
    if (event.key === "ArrowLeft") setStep((value) => boundedStep(value - 1, path.length));
    else if (event.key === "ArrowRight") setStep((value) => boundedStep(value + 1, path.length));
    else if (event.key === "Home") setStep(0);
    else if (event.key === "End") setStep(Math.max(0, path.length - 1));
    else return;
    event.preventDefault();
  }}>
    <h3>Exploration evidence</h3>
    <p>This is saved legacy exploration evidence. Choosing an alternative changes the displayed path; it does not operate the browser.</p>
    <p>Step {step + 1} of {path.length} · <strong>{edge.action.kind} attempted</strong> · {edge.status}{edge.duration_ms ? ` · ${edge.duration_ms}ms` : ""}{edge.url_change === "changed" ? " · page changed" : ""}</p>
    <div className="button-row"><button type="button" className="button button--secondary" onClick={() => setStep((value) => boundedStep(value - 1, path.length))} disabled={step === 0}>Previous</button><button type="button" className="button button--secondary" onClick={() => setStep((value) => boundedStep(value + 1, path.length))} disabled={step >= path.length - 1}>Next</button></div>
    <div className="vision-transition" aria-label={`State transition ${step + 1}`}>
      <div><h4>Before · state {before?.sequence ?? "unavailable"}</h4>{images.before ? <div className="vision-replay-image">{marker && <span className="vision-replay-marker" style={marker}>attempted {edge.action.kind}</span>}<img src={images.before} alt={`State before ${edge.action.kind}`} /></div> : <p>{!beforeFrame ? "Before frame missing or deleted." : errors.before ? "Before frame unavailable." : "Loading before frame?"}</p>}</div>
      <p className="vision-transition-action">↓<br />{edge.action.kind}<br /><small>{edge.status}</small></p>
      <div><h4>After · state {after?.sequence ?? "unavailable"}</h4>{after && images.after ? <div className="vision-replay-image"><img src={images.after} alt={`State after ${edge.action.kind}`} /></div> : <p>{afterFrame ? errors.after ? "After frame unavailable." : "Loading after frame?" : `No after frame (${edge.outcome_code ?? edge.status}).`}</p>}{afterFrame && <button className="button button--secondary" type="button" onClick={() => onSelectFrame(afterFrame)}>View this frame</button>}</div>
    </div>
    <div className="stack-list" aria-label="Branch alternatives">{alternatives.map((item) => <button type="button" className="button button--secondary" key={item.id} onClick={() => { const next = trajectoryPathForEdge(trajectory, item.id); setChoice(item.id); setStep(Math.max(0, next.findIndex((edge) => edge.id === item.id))); }}>{item === edge ? "Selected" : "Alternative"}: {item.action.kind} · {item.status}{item.child_state_id ? " · after frame saved" : ""}</button>)}</div>
    <div className="stack-list" aria-label="Path scrubber">{path.map((item, index) => <button key={item.id} type="button" className="button button--secondary" aria-current={index === step ? "step" : undefined} onClick={() => setStep(index)}>{index + 1}. {item.action.kind}</button>)}</div>
    {selectedFrame && <p>Current gallery selection: state {selectedFrame.sequence}.</p>}
  </section>;
}
