import assert from "node:assert/strict";
import test from "node:test";
import { agentWorkspaceTab } from "./agent-workspace-model.ts";

test("website exploration is the default and draft review takes precedence", () => {
  assert.equal(agentWorkspaceTab(null), "vision");
  assert.equal(agentWorkspaceTab("draft"), "generation");
  assert.equal(agentWorkspaceTab(""), "vision");
});
