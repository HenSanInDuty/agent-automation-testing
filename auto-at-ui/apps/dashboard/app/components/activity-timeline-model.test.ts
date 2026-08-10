import assert from "node:assert/strict";
import test from "node:test";

import {
  orderedActivities,
  timelineConnectionLabel,
  usesPollingFallback,
} from "./activity-timeline-model.ts";

test("timeline preserves a stable event order and announces its connection mode", () => {
  const ordered = orderedActivities([
    { id: "b", occurred_at: "2026-08-10T10:00:00Z" },
    { id: "a", occurred_at: "2026-08-10T10:00:00Z" },
  ] as never);

  assert.deepEqual(ordered.map((event) => event.id), ["a", "b"]);
  assert.equal(timelineConnectionLabel("connecting"), "Connecting to live updates");
  assert.equal(timelineConnectionLabel("live"), "Live updates connected");
  assert.equal(timelineConnectionLabel("polling"), "Reconnecting - polling fallback active");
});

test("timeline safely falls back to polling when live updates are unavailable", () => {
  assert.equal(usesPollingFallback(false, true), true);
  assert.equal(usesPollingFallback(true, false), true);
  assert.equal(usesPollingFallback(true, true), false);
});
