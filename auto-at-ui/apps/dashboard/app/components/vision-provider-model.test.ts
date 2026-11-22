import assert from "node:assert/strict";
import test from "node:test";
import type { VisionPolicy, VisionProvider } from "../generation-types";
import { agentStepView, blockedReasonMessage, codexReadinessLabel, engineRequestFields, explorationEngine, hasImageConsent, hasUnsavedVisionPolicy, hasVisionConsent, screenshotDisclosure, switchVisionProvider, visionConfirmation, visionDisclosure, visionFailureMessage, visionProviderLabel } from "./vision-provider-model.ts";

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
  for (const reason of ["bridge_login_required", "bridge_stale_result", "bridge_interrupted", "bridge_cleanup_pending", "image_consent_required", "step_limit", "exploration_call_limit", "exploration_coverage_incomplete"]) assert.ok(visionFailureMessage(reason));
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
  assert.equal(visionProviderLabel("claude_cli"), "Claude (claude -p, existing account)");
  assert.match(screenshotDisclosure("claude_cli"), /sent to Anthropic/);
  assert.match(screenshotDisclosure("codex_cli"), /sent to OpenAI/);
  for (const code of ["provider_not_configured", "provider_auth_failed", "provider_billing_required", "provider_rate_limited", "provider_model_unavailable", "provider_timeout", "model_output_invalid", "policy_disabled", "model_unavailable", "image_delivery_auth_required", "worker_state_unavailable", "session_timeout"]) assert.ok(visionFailureMessage(code));
  assert.equal(visionFailureMessage("arbitrary provider body"), undefined);
  assert.equal(visionFailureMessage("__proto__"), undefined);
});

test("claude_cli uses the DOM-first bridge consent bound to its own provider", () => {
  const claude: VisionProvider = { id: "claude_cli", display_name: "Claude", models: [{ id: "claude-opus-5-5", display_name: "claude-opus-5-5" }], configured: true, supports_inline_images: false };
  const draft = switchVisionProvider(saved, claude);
  assert.equal(draft.model, "claude-opus-5-5");
  assert.equal(draft.codex?.input_mode, "dom_first");
  assert.equal(hasVisionConsent(draft), false);
  const accepted = { ...draft, codex: { ...draft.codex!, dom_transfer_accepted: true, dom_transfer_provider: "claude_cli" as const } };
  assert.equal(hasVisionConsent(accepted), true);
  assert.equal(hasVisionConsent({ ...accepted, codex: { ...accepted.codex, dom_transfer_provider: "codex_cli" as const } }), false);
  assert.match(visionDisclosure(accepted), /Anthropic using the existing Claude Code account/);
});

const agentCodes = ["stale_ref", "invalid_ref", "origin_blocked", "sensitive_action_blocked", "action_kind_blocked", "ineligible_target", "batch_stopped", "agent_step_limit", "agent_done", "agent_stopped"];

test("agent-loop reason codes map to their own copy, not the generic fallback", () => {
  const messages = agentCodes.map((code) => visionFailureMessage(code));
  for (const message of messages) assert.ok(message);
  assert.equal(new Set(messages).size, agentCodes.length);
  assert.match(visionFailureMessage("stale_ref")!, /page changed/);
  assert.match(visionFailureMessage("sensitive_action_blocked")!, /No text was typed/);
});

test("unknown or hostile skipped reasons fall back to a bounded, non-generic line", () => {
  assert.equal(blockedReasonMessage(undefined), "Skipped before it was sent to the browser.");
  assert.equal(blockedReasonMessage(""), "Skipped before it was sent to the browser.");
  assert.equal(blockedReasonMessage("future_new_code"), "Skipped (future new code).");
  assert.notEqual(blockedReasonMessage("future_new_code"), blockedReasonMessage("stale_ref"));
  assert.match(blockedReasonMessage("__proto__"), /^Skipped \(/);
  assert.equal(blockedReasonMessage("x".repeat(500)).length, "Skipped ()." .length + 80);
});

test("agent step view is absent without a step and renders three fields for a step", () => {
  assert.equal(agentStepView({} as never), null);
  assert.equal(agentStepView({ agent_step: null } as never), null);
  assert.deepEqual(agentStepView({ agent_step: {} } as never), { previous: "Not recorded", memory: "Not recorded", next: "Not recorded", blocked: [] });
  const view = agentStepView({ agent_step: { step_index: 1, evaluation_previous_goal: "  Đã mở trang sản phẩm  ", memory: "   ", next_goal: "y".repeat(2000),
    skipped_actions: [{ index: 2, kind: "click", skipped_reason: "stale_ref" }, { index: 3, kind: "type", skipped_reason: "future_code" }] } } as never);
  assert.ok(view);
  assert.equal(view.previous, "Đã mở trang sản phẩm");
  assert.equal(view.memory, "Not recorded");
  assert.equal(view.next.length, 601);
  assert.ok(view.next.endsWith("…"));
  assert.match(view.blocked[0], /^click: The page changed after the agent chose this element/);
  assert.equal(view.blocked[1], "type: Skipped (future code).");
  const longKind = agentStepView({ agent_step: { step_index: 2, evaluation_previous_goal: "", memory: "", next_goal: "", skipped_actions: [{ kind: "k".repeat(200), skipped_reason: "agent_done" }] } } as never);
  assert.equal(longKind?.blocked[0].split(":")[0].length, 40);
});

test("engine values: unknown strings act as Planner and only Agent loop adds the request field", () => {
  assert.equal(explorationEngine("agent_loop"), "agent_loop");
  assert.equal(explorationEngine("planner"), "planner");
  assert.equal(explorationEngine("constructor"), "planner");
  assert.equal(explorationEngine(undefined), "planner");
  assert.deepEqual(engineRequestFields("planner"), {});
  assert.deepEqual(engineRequestFields("agent_loop"), { engine: "agent_loop" });
});

test("QA: agent step view tolerates malformed skipped actions and caps the blocked list", () => {
  const many = Array.from({ length: 50 }, (_, i) => ({ index: i, kind: "click", skipped_reason: "origin_blocked" }));
  assert.equal(agentStepView({ agent_step: { step_index: 1, evaluation_previous_goal: "a", memory: "b", next_goal: "c", skipped_actions: many } } as never)?.blocked.length, 20);
  const bad = agentStepView({ agent_step: { step_index: 1, evaluation_previous_goal: "a", memory: "b", next_goal: "c", skipped_actions: "oops" } } as never);
  assert.deepEqual(bad?.blocked, []);
  const nulls = agentStepView({ agent_step: { step_index: 1, evaluation_previous_goal: 7, memory: null, next_goal: "Chuyển sang trang thanh toán", skipped_actions: [null, { kind: 5, skipped_reason: 9 }] } } as never);
  assert.equal(nulls?.previous, "Not recorded");
  assert.equal(nulls?.next, "Chuyển sang trang thanh toán");
  assert.deepEqual(nulls?.blocked, ["Action: Skipped before it was sent to the browser.", "Action: Skipped before it was sent to the browser."]);
});
