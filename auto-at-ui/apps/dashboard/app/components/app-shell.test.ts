import assert from "node:assert/strict";
import test from "node:test";
import { dialogKeyboardAction, initialDialogFocus } from "./confirm-dialog-model.ts";
import { isActiveRoute, isPublicRoute, loginRedirectPath, nextDrawerState, postLoginPath, safeNextPath, tenantSelectionPath } from "./app-shell-state.ts";
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

test("unauthenticated visitors go to login and come back only to a safe same-origin page", () => {
  assert.equal(loginRedirectPath("/"), "/login");
  assert.equal(loginRedirectPath("/runs/abc", "?tab=evidence"), "/login?next=%2Fruns%2Fabc%3Ftab%3Devidence");
  assert.equal(safeNextPath("/runs/abc?tab=evidence"), "/runs/abc?tab=evidence");
  assert.equal(safeNextPath(null), "/");
  assert.equal(safeNextPath("https://evil.test"), "/");
  assert.equal(safeNextPath("//evil.test/path"), "/");
  assert.equal(safeNextPath("/\\evil.test"), "/");
  assert.equal(safeNextPath("/login?next=/admin"), "/");
  assert.equal(isPublicRoute("/login"), true);
  assert.equal(isPublicRoute("/select-tenant"), true);
  assert.equal(isPublicRoute("/admin"), false);
  assert.equal(safeNextPath("/select-tenant?next=%2Fadmin"), "/select-tenant?next=%2Fadmin");
});

test("after login the user changes a temporary password, then picks a tenant, then reaches the page", () => {
  const single = { force_password_change: false, tenant_selection_required: false };
  const multi = { force_password_change: false, tenant_selection_required: true };
  assert.equal(postLoginPath(single, null), "/");
  assert.equal(postLoginPath(single, "/runs"), "/runs");
  assert.equal(postLoginPath(multi, null), "/select-tenant");
  assert.equal(postLoginPath(multi, "/admin"), "/select-tenant?next=%2Fadmin");
  assert.equal(postLoginPath({ ...multi, force_password_change: true }, "/admin"), "/change-password?next=%2Fselect-tenant%3Fnext%3D%252Fadmin");
  assert.equal(postLoginPath({ ...single, force_password_change: true }, null), "/change-password");
  assert.equal(postLoginPath(multi, "https://evil.test"), "/select-tenant");
  assert.equal(tenantSelectionPath("/runs?status=failed"), "/select-tenant?next=%2Fruns%3Fstatus%3Dfailed");
});
