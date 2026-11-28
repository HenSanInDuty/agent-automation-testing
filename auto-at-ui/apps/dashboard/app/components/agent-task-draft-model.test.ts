import assert from "node:assert/strict";
import test from "node:test";
import type { AgentTaskConsistency } from "../generation-types";
import { agentTaskProvenance, canApproveAgentDraft, canRequestDraft, clearInputs, consistencyLines, consistencyReasonLabel, decisionFailureMessage, draftFailureMessage, emptyInputs, inputsFilled, setInput, statusDistribution, testValueOrigin, draftInputs, validConsistency } from "./agent-task-draft-model.ts";

const report: AgentTaskConsistency = {
  schema_version: "v1", session_id: "s", group_sessions: 5, assessed_sessions: 5, status_counts: { achieved: 5, blocked: 0, inconclusive: 0, not_achieved: 0 },
  modal_status: "achieved", modal_count: 5, agreement_rate: 1, source_status: "achieved", source_is_modal: true, threshold: 0.9, small_sample: false, eligible: true, reasons: [], advisory: true, notice: "advisory",
};
const secret = "Zx9!hunter2-sample";

const inputsAnswer = (type_steps: unknown, owned_test_target: unknown = true, has_type_steps: unknown = Array.isArray(type_steps) && type_steps.length > 0) => ({ owned_test_target, has_type_steps, type_steps });
const stepsOf = (count: number) => Array.from({ length: count }, (_, n) => ({ position: n + 1, label: "Type into field", textChars: 8 }));

test("the type steps are the API's list: numbered by position, with the locator name and the exact length it expects", () => {
  assert.deepEqual(draftInputs(inputsAnswer([{ step_index: 1, locator_name: "Tên đăng nhập", text_chars: 24 }, { step_index: 1, locator_name: "Mật khẩu", text_chars: 12 }, { step_index: 3, locator_name: "", text_chars: 5 }])), {
    owned: true,
    hasTypeSteps: true,
    steps: [
      { position: 1, label: "Type into field “Tên đăng nhập”", textChars: 24 },
      { position: 2, label: "Type into field “Mật khẩu”", textChars: 12 },
      { position: 3, label: "Type into field", textChars: 5 },
    ],
  });
  assert.deepEqual(draftInputs(inputsAnswer([])), { owned: true, hasTypeSteps: false, steps: [] });
  assert.deepEqual(draftInputs(inputsAnswer([], false)), { owned: false, hasTypeSteps: false, steps: [] });
  assert.deepEqual(draftInputs(inputsAnswer([], false, true)), { owned: false, hasTypeSteps: true, steps: [] });
  assert.deepEqual(draftInputs({ owned_test_target: true, has_type_steps: false, type_steps: [] }), { owned: true, hasTypeSteps: false, steps: [] });
});

test("an answer that is not in the agreed shape is unusable instead of guessed", () => {
  const bad: unknown[] = [null, undefined, "x", [], {}, inputsAnswer(undefined), inputsAnswer("a"), inputsAnswer([], "yes"), inputsAnswer([], true, "no"), { owned_test_target: true, type_steps: [] }, inputsAnswer([null]),
    inputsAnswer([{ step_index: 1, locator_name: "A" }]), inputsAnswer([{ step_index: 1, locator_name: "A", text_chars: "8" }]),
    inputsAnswer([{ step_index: 1, locator_name: "A", text_chars: 0 }]), inputsAnswer([{ step_index: 1, locator_name: "A", text_chars: 2.5 }]),
    inputsAnswer([{ step_index: 1, locator_name: 5, text_chars: 3 }])];
  for (const value of bad) assert.equal(draftInputs(value), null, JSON.stringify(value));
});

test("typed values live in a fresh array, and nothing of them stays once cleared", () => {
  const steps = stepsOf(2);
  const initial = emptyInputs(steps);
  assert.deepEqual(initial, ["", ""]);
  assert.equal(inputsFilled(initial), false);
  const typed = setInput(setInput(initial, 0, secret), 1, "other");
  assert.deepEqual(initial, ["", ""], "the previous state is not mutated");
  assert.equal(inputsFilled(typed), true);
  assert.equal(inputsFilled(setInput(typed, 1, "")), false);
  const cleared = clearInputs(typed);
  assert.deepEqual(cleared, ["", ""]);
  assert.equal(JSON.stringify(cleared).includes(secret), false);
  assert.deepEqual(typed, [secret, "other"], "clearing returns a new array and leaves the one that was sent alone");
  assert.deepEqual(emptyInputs([]), []);
  assert.equal(inputsFilled([]), true);
});

test("building, editing and clearing the form never touches storage, the console or the address", () => {
  const touched: string[] = [];
  const guard = (name: string) => new Proxy({}, { get: (_, key) => () => { touched.push(`${name}.${String(key)}`); }, set: () => { touched.push(`${name} set`); return true; } });
  const keep = { localStorage: Object.getOwnPropertyDescriptor(globalThis, "localStorage"), sessionStorage: Object.getOwnPropertyDescriptor(globalThis, "sessionStorage"), location: Object.getOwnPropertyDescriptor(globalThis, "location"), history: Object.getOwnPropertyDescriptor(globalThis, "history") };
  const consoleMethods = ["log", "info", "warn", "error", "debug", "trace"] as const;
  const originals = consoleMethods.map((name) => console[name]);
  Object.defineProperty(globalThis, "localStorage", { value: guard("localStorage"), configurable: true });
  Object.defineProperty(globalThis, "sessionStorage", { value: guard("sessionStorage"), configurable: true });
  Object.defineProperty(globalThis, "location", { value: guard("location"), configurable: true });
  Object.defineProperty(globalThis, "history", { value: guard("history"), configurable: true });
  for (const name of consoleMethods) console[name] = () => { touched.push(`console.${name}`); };
  try {
    const steps = stepsOf(1);
    const typed = setInput(emptyInputs(steps), 0, secret);
    inputsFilled(typed); clearInputs(typed);
    draftFailureMessage("input_value_mismatch"); testValueOrigin({ contains_test_values: true, requested_by: "alice" });
  } finally {
    consoleMethods.forEach((name, index) => { console[name] = originals[index] as never; });
    for (const [name, descriptor] of Object.entries(keep)) { if (descriptor) Object.defineProperty(globalThis, name, descriptor); else delete (globalThis as Record<string, unknown>)[name]; }
  }
  assert.deepEqual(touched, []);
});

test("the request button follows the API's own verdict and a malformed report is not trusted", () => {
  assert.equal(canRequestDraft(report), true);
  assert.equal(canRequestDraft({ ...report, eligible: false }), false);
  assert.equal(canRequestDraft(null), false);
  assert.equal(canRequestDraft(undefined), false);
  assert.equal(validConsistency(report), report);
  assert.equal(validConsistency({ id: "a session, not a report" }), null);
  assert.equal(validConsistency({ ...report, reasons: undefined }), null);
  assert.equal(validConsistency(null), null);
  // A report that says "not eligible" with no reason is still not a draft button: only `eligible` counts.
  const silent: AgentTaskConsistency = { ...report, eligible: false, reasons: [] };
  assert.equal(canRequestDraft(silent), false);
});

test("the report is worded with the API's own numbers and never invents a verdict", () => {
  assert.deepEqual(consistencyLines(report), [
    "5 of 5 sessions of this task have an assessment.",
    "Results: achieved 5.",
    "Agreement: 100% reported achieved (the required agreement is 90%).",
  ]);
  const split = { ...report, assessed_sessions: 3, group_sessions: 4, status_counts: { achieved: 2, not_achieved: 1, blocked: 0, inconclusive: 0 }, agreement_rate: 0.6667, modal_status: "achieved", small_sample: false };
  assert.deepEqual(consistencyLines(split), [
    "3 of 4 sessions of this task have an assessment.",
    "Results: achieved 2 · not achieved 1.",
    "Agreement: 66.7% reported achieved (the required agreement is 90%).",
  ]);
  assert.deepEqual(consistencyLines({ ...report, assessed_sessions: 0, group_sessions: 1, status_counts: { achieved: 0 }, agreement_rate: null, modal_status: null, small_sample: true }), [
    "0 of 1 sessions of this task have an assessment.",
    "Results: none yet.",
    "Agreement: not available.",
    "Few sessions: high agreement says little with so small a sample.",
  ]);
  assert.deepEqual(consistencyLines({ assessed_sessions: 4, group_sessions: 4, agreement_rate: 1, modal_status: "not_achieved", threshold: 0.9, small_sample: false }), [
    "4 of 4 sessions of this task have an assessment.",
    "Agreement: 100% reported not achieved (the required agreement is 90%).",
  ]);
  assert.equal(statusDistribution({}), "none yet");
});

test("every reason the API gives has a plain label, and a new one falls back to readable text", () => {
  for (const reason of ["assessment_inconsistent", "modal_not_achieved", "source_not_modal"]) assert.ok(consistencyReasonLabel(reason).length > 40, reason);
  assert.notEqual(consistencyReasonLabel("assessment_inconsistent"), consistencyReasonLabel("modal_not_achieved"));
  assert.equal(consistencyReasonLabel("brand_new_reason"), "brand new reason");
  assert.equal(consistencyReasonLabel("constructor"), "constructor");
});

test("every refusal code of the create route is explained, and the explanation carries no value", () => {
  const codes = ["session_not_completed", "assessment_unavailable", "assessment_not_achieved", "assessment_inconsistent", "origin_not_allowed", "input_value_not_allowed", "input_value_missing", "input_value_mismatch", "input_value_rejected_by_source_policy", "credentials_in_source", "evidence_expired", "operation_failed", "action_outcome_unknown", "action_unsupported", "locator_unavailable", "ephemeral_locator", "source_policy_rejected", "target_url_invalid", "rendered_source_limit", "idempotency_key_conflict", "request_invalid"];
  const messages = codes.map((code) => draftFailureMessage(code));
  messages.forEach((message, index) => assert.ok(message && message.length > 20, codes[index]));
  assert.equal(new Set(messages).size, codes.length, "each code has its own wording");
  assert.match(draftFailureMessage("assessment_inconsistent")!, /do not agree/);
  assert.match(draftFailureMessage("input_value_mismatch")!, /length differs/);
  assert.match(draftFailureMessage("input_value_not_allowed")!, /test environment you own/);
  assert.match(draftFailureMessage("credentials_in_source")!, /cannot be revised with a model/);
  assert.equal(draftFailureMessage(undefined), undefined);
  assert.equal(draftFailureMessage("something_new"), undefined);
  assert.equal(draftFailureMessage("constructor"), undefined);
  assert.equal(draftFailureMessage("__proto__"), undefined);
});

test("review refusals are worded for the reviewer and unknown text is left to the caller", () => {
  assert.match(decisionFailureMessage("reviewer_must_differ_from_requester")!, /someone else must review/);
  assert.match(decisionFailureMessage("disposable_credentials_ack_required")!, /disposable test accounts/);
  assert.match(decisionFailureMessage("owned_test_target_disabled")!, /no longer declared/);
  assert.equal(decisionFailureMessage("Generated draft is already decided."), undefined);
  assert.equal(decisionFailureMessage("toString"), undefined);
});

test("approval needs the disposable-account confirmation exactly when the draft carries test values", () => {
  assert.equal(canApproveAgentDraft(true, false), false);
  assert.equal(canApproveAgentDraft(true, true), true);
  assert.equal(canApproveAgentDraft(false, false), true);
  assert.equal(canApproveAgentDraft(false, true), true);
});

test("an agent-session draft is recognised by its provenance and a malformed one is not", () => {
  const provenance = {
    provider: "deterministic", agent_trace_source: { session_id: "s-1", trace_hash: "h".repeat(64) }, contains_test_values: true, owned_test_target: true, requested_by: "alice",
    consistency: { schema_version: "v1", assessed_sessions: 5, group_sessions: 6, agreement_rate: 1, modal_status: "achieved", threshold: 0.9, small_sample: false },
  };
  assert.deepEqual(agentTaskProvenance(provenance), {
    agent_trace_source: { session_id: "s-1", trace_hash: "h".repeat(64) }, contains_test_values: true, owned_test_target: true, requested_by: "alice",
    consistency: { assessed_sessions: 5, group_sessions: 6, agreement_rate: 1, modal_status: "achieved", threshold: 0.9, small_sample: false },
  });
  assert.equal(agentTaskProvenance({ provider: "gemini", vision_source: { session_id: "s-1" } }), null);
  assert.equal(agentTaskProvenance({}), null);
  assert.equal(agentTaskProvenance(null), null);
  assert.equal(agentTaskProvenance({ agent_trace_source: { session_id: 5 } }), null);
  const bare = agentTaskProvenance({ agent_trace_source: { session_id: "s", trace_hash: "h" } });
  assert.deepEqual(bare, { agent_trace_source: { session_id: "s", trace_hash: "h" }, contains_test_values: false, owned_test_target: false, requested_by: null, consistency: null });
});

test("the reviewer is told plainly where typed values came from", () => {
  assert.match(testValueOrigin({ contains_test_values: true, requested_by: "alice" }), /entered by alice when the draft was requested.*written as-is in the source.*only their length/);
  assert.match(testValueOrigin({ contains_test_values: true, requested_by: null }), /by the requester/);
  assert.equal(testValueOrigin({ contains_test_values: false, requested_by: "alice" }), "This draft types no values.");
});
