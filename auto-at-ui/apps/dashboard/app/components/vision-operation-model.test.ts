import assert from "node:assert/strict";
import test from "node:test";
import { operationLabel, operationStatus, selectedOperation, shouldPollVisionResult, visionResultLabel } from "./vision-operation-model.ts";

test("steps distinguish execution outcomes and hide technical selectors", () => {
  assert.equal(operationStatus("rejected"), "Not executed");
  assert.equal(operationStatus("unknown"), "Outcome unknown");
  assert.equal(operationStatus("completed"), "Performed");
  const operation = { action_kind: "click" } as never;
  assert.equal(operationLabel(operation, { status: "verified", descriptor: { strategy: "role", value: "Open details" } } as never), "Click “Open details”");
  assert.equal(operationLabel(operation, { status: "verified", descriptor: { strategy: "css", value: '[name="internal"]' } } as never), "Click");
});

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
