import assert from "node:assert/strict";
import test from "node:test";
import type { VisionPolicy, VisionProvider } from "../generation-types";
import { codexReadinessLabel, hasImageConsent, hasUnsavedVisionPolicy, hasVisionConsent, screenshotDisclosure, switchVisionProvider, visionConfirmation, visionDisclosure, visionFailureMessage, visionProviderLabel } from "./vision-provider-model.ts";

const saved: VisionPolicy = { enabled: true, provider: "huggingface", model: "custom/hf-model", raw_screenshot_transfer_accepted: true, max_steps: 3, max_screenshot_bytes: 1000, max_session_seconds: 120, max_cost_usd: 0, max_requests_per_minute: 5 };
const gemini: VisionProvider = { id: "gemini", display_name: "Gehihi (Google Gemini)", models: [{ id: "gemini-3.8-flash", display_name: "gemini-3.8-flash" }], configured: true, supports_inline_images: true };
const codex: VisionProvider = { id: "codex_cli", display_name: "Codex (existing account)", models: [{ id: "gpt-6-luna", display_name: "gpt-6-luna" }], configured: true, supports_inline_images: true,
  bridge_readiness: { configured: true, online: true, authenticated: true, capabilities_qualified: true, model_access: "unverified", failure_code: null } };

test("Codex DOM-only consent is independent and switching recipients resets both", () => {
  const reset = switchVisionProvider(saved, codex);
  assert.equal(hasVisionConsent(reset), false);
  assert.equal(hasImageConsent(reset), false);
  const accepted = { ...reset, enabled: true, codex: { ...reset.codex!, dom_transfer_accepted: true, dom_transfer_provider: "codex_cli" as const }, input_policy_fingerprint: "a".repeat(64) };
  assert.equal(hasVisionConsent(accepted), true);
  assert.equal(hasImageConsent(accepted), false);
  assert.match(visionDisclosure(accepted), /Screenshot transfer is disabled/);
  assert.match(visionDisclosure(accepted), /does not mean offline/);
  assert.deepEqual(visionConfirmation(accepted), { expected_provider: "codex_cli", expected_model: "gpt-6-luna", expected_input_policy_fingerprint: "a".repeat(64) });
  assert.equal(hasUnsavedVisionPolicy(accepted, structuredClone(accepted)), false);
  const changed = switchVisionProvider(accepted, gemini);
  assert.equal(changed.codex, null);
  assert.equal(changed.input_policy_fingerprint, null);
  assert.equal(changed.enabled, false);
});

test("Codex readiness distinguishes connection, login, compatibility, model access and busy", () => {
  assert.match(codexReadinessLabel(codex), /ready; model access unverified/);
  for (const [change, expected] of [
    [{ online: false }, /disconnected/], [{ authenticated: false }, /login required/],
    [{ capabilities_qualified: false }, /compatible CLI/], [{ model_access: "unavailable" }, /model unavailable/],
    [{ busy: true }, /busy/], [{ model_access: "available" }, /bridge ready/],
  ] as const) assert.match(codexReadinessLabel({ ...codex, bridge_readiness: { ...codex.bridge_readiness!, ...change } }), expected);
  for (const reason of ["bridge_login_required", "bridge_stale_result", "bridge_interrupted", "bridge_cleanup_pending", "image_consent_required", "step_limit"]) assert.ok(visionFailureMessage(reason));
});

test("switching recipient resets consent, enablement and model without changing saved policy", () => {
  const draft = switchVisionProvider(saved, gemini);
  assert.equal(draft.model, "gemini-3.8-flash");
  assert.equal(draft.enabled, false);
  assert.equal(draft.raw_screenshot_transfer_accepted, false);
  assert.equal(draft.raw_screenshot_transfer_provider, null);
  assert.equal(hasUnsavedVisionPolicy(saved, draft), true);
  assert.equal(saved.model, "custom/hf-model");
  assert.equal(hasVisionConsent(saved), true);
  assert.equal(hasVisionConsent({ ...draft, raw_screenshot_transfer_accepted: true }), false);
  assert.equal(hasVisionConsent({ ...draft, raw_screenshot_transfer_accepted: true, raw_screenshot_transfer_provider: "gemini" }), true);
});

test("confirmation freezes saved recipient through unsaved edits or failed save", () => {
  const snapshot = visionConfirmation(saved);
  const draft = switchVisionProvider(saved, gemini);
  assert.deepEqual(snapshot, { expected_provider: "huggingface", expected_model: "custom/hf-model" });
  assert.deepEqual(visionConfirmation(saved), snapshot);
  assert.notDeepEqual(visionConfirmation(draft), snapshot);
  assert.equal(hasUnsavedVisionPolicy(saved, { ...saved }), false);
  assert.equal(switchVisionProvider(draft, gemini), draft);
});

test("recipient labels and error messages do not expose arbitrary provider diagnostics", () => {
  assert.equal(visionProviderLabel("gemini"), "Gehihi (Google Gemini)");
  assert.equal(visionProviderLabel("secret-like unknown value"), "Unknown Vision provider");
  assert.equal(visionProviderLabel("constructor"), "Unknown Vision provider");
  assert.match(screenshotDisclosure("gemini"), /sent to Google/);
  assert.match(screenshotDisclosure("gemini"), /data-use conditions/);
  for (const code of ["provider_not_configured", "provider_auth_failed", "provider_billing_required", "provider_rate_limited", "provider_model_unavailable", "provider_timeout", "model_output_invalid", "policy_disabled", "model_unavailable", "image_delivery_auth_required", "worker_state_unavailable", "session_timeout"]) assert.ok(visionFailureMessage(code));
  assert.equal(visionFailureMessage("arbitrary provider body"), undefined);
  assert.equal(visionFailureMessage("__proto__"), undefined);
});
