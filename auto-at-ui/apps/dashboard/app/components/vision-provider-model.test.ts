import assert from "node:assert/strict";
import test from "node:test";
import type { VisionPolicy, VisionProvider } from "../generation-types";
import { hasUnsavedVisionPolicy, hasVisionConsent, screenshotDisclosure, switchVisionProvider, visionConfirmation, visionFailureMessage, visionProviderLabel } from "./vision-provider-model.ts";

const saved: VisionPolicy = { enabled: true, provider: "huggingface", model: "custom/hf-model", raw_screenshot_transfer_accepted: true, max_steps: 3, max_screenshot_bytes: 1000, max_session_seconds: 120, max_cost_usd: 0, max_requests_per_minute: 5 };
const gemini: VisionProvider = { id: "gemini", display_name: "Gehihi (Google Gemini)", models: [{ id: "gemini-3.8-flash", display_name: "gemini-3.8-flash" }], configured: true, supports_inline_images: true };

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
  for (const code of ["provider_not_configured", "provider_auth_failed", "provider_billing_required", "provider_rate_limited", "provider_model_unavailable", "provider_timeout", "model_output_invalid", "policy_disabled", "model_unavailable", "image_delivery_auth_required"]) assert.ok(visionFailureMessage(code));
  assert.equal(visionFailureMessage("arbitrary provider body"), undefined);
  assert.equal(visionFailureMessage("__proto__"), undefined);
});
