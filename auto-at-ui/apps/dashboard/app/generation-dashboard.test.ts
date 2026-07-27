import assert from "node:assert/strict";
import test from "node:test";
import { shouldPollGeneration } from "./generation-polling.ts";

test("only non-terminal generation states are polled", () => {
  assert.equal(shouldPollGeneration("queued"), true);
  assert.equal(shouldPollGeneration("generating"), true);
  assert.equal(shouldPollGeneration("completed"), false);
  assert.equal(shouldPollGeneration("failed"), false);
});
