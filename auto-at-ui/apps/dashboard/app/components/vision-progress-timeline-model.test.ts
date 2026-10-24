import assert from "node:assert/strict";
import test from "node:test";

import {
  isVisionModelPending, latestVisionProgress, orderedVisionProgress, parseVisionProgress, visionConnectionLabel, visionModelWaitLabel, visionProgressLabel, visionProgressMetrics,
} from "./vision-progress-timeline-model.ts";
import type { VisionProgressActivity, VisualOperation } from "../generation-types";

test("Codex stages show observed mode and counters without claiming browser work", () => {
  const event: VisionProgressActivity = { id: "job", run_id: null, correlation_id: "fixture", source: "vision", status: "running", safe_summary: "Synthetic progress", stage: "codex.started", occurred_at: "2026-10-24T00:00:00Z", metadata: { job_id: "one", call_sequence: 2, elapsed_ms: 1234, mode: "image" } };
  assert.equal(isVisionModelPending(event, undefined), true);
  assert.equal(visionModelWaitLabel(event), "Analyzing the requested screenshot");
  assert.equal(visionProgressMetrics(event), "Call 2 · 1.2s elapsed at this update");
  assert.equal(visionProgressMetrics({ ...event, metadata: { call_sequence: 99, elapsed_ms: NaN } }), "");
  assert.equal(isVisionModelPending({ ...event, stage: "codex.completed" }, undefined), false);
});

test("late Codex progress cannot replace terminal job or session state", () => {
  const completed: VisionProgressActivity = { id: "a", run_id: null, correlation_id: "fixture", source: "vision", status: "running", safe_summary: "Synthetic progress", stage: "codex.completed", occurred_at: "2026-10-24T00:00:00Z", metadata: { job_id: "one" } };
  const late = { ...completed, id: "b", stage: "codex.started", occurred_at: "2026-10-24T00:00:01Z" };
  assert.equal(latestVisionProgress([late, completed, completed]), completed);
  const terminal = { ...completed, id: "c", stage: "unavailable" };
  assert.equal(latestVisionProgress([late, terminal]), terminal);
  const next = { ...late, metadata: { job_id: "two" } };
  assert.equal(latestVisionProgress([completed, next]), next);
});

test("model wait ends when newer browser work or a completion event is observed", () => {
  const event = { stage: "candidate.requested", occurred_at: "2026-10-23T08:45:55Z" } as VisionProgressActivity;
  const operation = { status: "completed", started_at: "2026-10-23T08:45:46Z" } as VisualOperation;
  assert.equal(isVisionModelPending(event, operation), true);
  assert.equal(isVisionModelPending(event, undefined), true);
  assert.equal(isVisionModelPending(null, operation), false);
  assert.equal(isVisionModelPending({ ...event, stage: "candidate.received" }, operation), false);
  assert.equal(isVisionModelPending({ ...event, stage: "unavailable" }, operation), false);
  assert.equal(isVisionModelPending({ ...event, occurred_at: "invalid" }, operation), false);
  assert.equal(isVisionModelPending(event, { ...operation, started_at: "2026-10-23T08:46:00Z" }), false);
  for (const status of ["prepared", "executing"]) assert.equal(isVisionModelPending(event, { ...operation, status }), false);
});

test("Vision progress is ordered, deduplicated, and mapped to safe user copy", () => {
  const ordered = orderedVisionProgress([
    { id: "b", occurred_at: "2026-09-06T10:00:00Z" },
    { id: "a", occurred_at: "2026-09-06T10:00:00Z" },
    { id: "a", occurred_at: "2026-09-06T10:00:00Z", stage: "completed" },
  ] as never);

  assert.deepEqual(ordered.map((item) => item.id), ["a", "b"]);
  assert.equal(visionProgressLabel("candidate.requested"), "Requesting advisory candidates");
  assert.equal(visionProgressLabel("cancelled"), "Advisory exploration cancelled");
  assert.equal(visionProgressLabel("constructor"), "Advisory progress updated");
  assert.equal(visionConnectionLabel("polling"), "Reconnecting - polling fallback active");
});

test("Vision progress parser rejects untrusted or non-vision event payloads", () => {
  assert.equal(parseVisionProgress({ stage: "action.recorded", text: "do not render" }), null);
  assert.equal(parseVisionProgress({
    id: "safe-1", source: "vision", stage: "action.recorded", status: "running",
    safe_summary: "Candidate action recorded.", metadata: { action_kind: "click" },
    occurred_at: "2026-09-06T10:00:00Z",
  })?.safe_summary, "Candidate action recorded.");
});
