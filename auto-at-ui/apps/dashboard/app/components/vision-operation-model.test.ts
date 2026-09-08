import assert from "node:assert/strict";
import test from "node:test";
import { selectedOperation, shouldPollVisionResult, visionResultLabel } from "./vision-operation-model.ts";

test("polling preserves a scrubbed operation and follows latest only when enabled", () => {
  const items = [{ id: "root" }, { id: "a" }, { id: "restore" }, { id: "b" }] as never;
  assert.equal(selectedOperation(items, "a", false), "a");
  assert.equal(selectedOperation(items, "a", true), "b");
  assert.equal(selectedOperation(items, "missing", false), "root");
});
test("terminal exploration polls only active downstream work", () => {
  const result = { exploration_state: "completed", links: { generation: { state: "failed" }, run: { state: "not_started" }, report: { state: "not_started" } } };
  assert.equal(shouldPollVisionResult(result as never), false);
  result.links.report.state = "pending";
  assert.equal(shouldPollVisionResult(result as never), true);
  assert.equal(visionResultLabel("pending_review"), "Awaiting review");
});
