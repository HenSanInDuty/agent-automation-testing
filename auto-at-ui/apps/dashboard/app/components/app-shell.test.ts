import assert from "node:assert/strict";
import test from "node:test";
import { dialogKeyboardAction, initialDialogFocus } from "./confirm-dialog-model.ts";
import { isActiveRoute, nextDrawerState } from "./app-shell-state.ts";
import { stateAccessibility } from "./state-model.ts";
import { statusLabel, statusTone } from "./status-model.ts";

test("status badges reserve semantic color tones for execution states", () => {
  assert.equal(statusTone("passed"), "success");
  assert.equal(statusTone("failed"), "danger");
  assert.equal(statusTone("errored"), "danger");
  assert.equal(statusTone("queued"), "warning");
  assert.equal(statusTone("running"), "warning");
  assert.equal(statusTone("skipped"), "muted");
  assert.equal(statusTone("cancelled"), "muted");
  assert.equal(statusTone("unrecognized"), "neutral");
  assert.equal(statusLabel("pending_review"), "pending review");
});

test("responsive navigation opens only on toggle and closes for escape or navigation", () => {
  assert.equal(nextDrawerState(false, "toggle"), true);
  assert.equal(nextDrawerState(true, "toggle"), false);
  assert.equal(nextDrawerState(true, "escape"), false);
  assert.equal(nextDrawerState(true, "navigate"), false);
  assert.equal(isActiveRoute("/agent/drafts/one", "/agent"), true);
  assert.equal(isActiveRoute("/runs", "/"), false);
});

test("confirmation keyboard handling protects focus and does not dismiss a busy decision", () => {
  assert.equal(initialDialogFocus, "cancel");
  assert.equal(dialogKeyboardAction("Escape", false), "cancel");
  assert.equal(dialogKeyboardAction("Escape", true), null);
  assert.equal(dialogKeyboardAction("Enter", false), null);
});

test("empty, loading, and error states expose distinct accessible rendering contracts", () => {
  assert.deepEqual(stateAccessibility("empty"), { ariaLabel: "Empty state" });
  assert.deepEqual(stateAccessibility("loading"), { ariaLabel: "Loading state", busy: true });
  assert.deepEqual(stateAccessibility("error"), { ariaLabel: "Error state", role: "alert" });
});
