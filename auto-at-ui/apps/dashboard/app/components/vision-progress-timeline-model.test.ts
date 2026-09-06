import assert from "node:assert/strict";
import test from "node:test";

import {
  orderedVisionProgress, parseVisionProgress, visionConnectionLabel, visionProgressLabel,
} from "./vision-progress-timeline-model.ts";

test("Vision progress is ordered, deduplicated, and mapped to safe user copy", () => {
  const ordered = orderedVisionProgress([
    { id: "b", occurred_at: "2026-09-06T10:00:00Z" },
    { id: "a", occurred_at: "2026-09-06T10:00:00Z" },
    { id: "a", occurred_at: "2026-09-06T10:00:00Z", stage: "completed" },
  ] as never);

  assert.deepEqual(ordered.map((item) => item.id), ["a", "b"]);
  assert.equal(visionProgressLabel("candidate.requested"), "Requesting advisory candidates");
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
