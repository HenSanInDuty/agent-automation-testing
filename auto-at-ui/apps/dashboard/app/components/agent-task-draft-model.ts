import type { AgentTaskConsistency, AgentTaskDraftProvenance } from "../generation-types";

/*
 * ADR-047 test drafts. The dashboard is a thin client: the control plane decides who may ask, whether the
 * sessions agree, what a typed value must look like and who may approve. Nothing here repeats those rules; it
 * only shows the `type` steps the API lists, keeps the typed values in memory for one request, and words the
 * answers the API gives.
 */

const isObject = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null && !Array.isArray(value);

export type TypeStep = { position: number; label: string; textChars: number };
/** The answer of `GET .../test-draft/inputs` as the form needs it; `owned` false with `hasTypeSteps` true means the project may not type the values this session needs; with no `type` step
 * there is nothing to refuse and the form is simply empty. */
export type DraftInputs = { owned: boolean; hasTypeSteps: boolean; steps: TypeStep[] };

/**
 * The `type` steps to fill in, read from the API's own list (same order as the `values` it expects). Nothing is
 * derived or guessed here: an answer that is not in the agreed shape (or a length that is not a positive whole
 * number) is unusable and gives null, so the form never shows a made-up length. `step_index` repeats when one agent
 * step typed twice, so the position in the list is the number and the key.
 */
export function draftInputs(value: unknown): DraftInputs | null {
  const answer = value as { owned_test_target?: unknown; has_type_steps?: unknown; type_steps?: unknown } | null | undefined;
  if (!isObject(answer) || typeof answer.owned_test_target !== "boolean" || typeof answer.has_type_steps !== "boolean" || !Array.isArray(answer.type_steps)) return null;
  const steps: TypeStep[] = [];
  for (const [index, item] of answer.type_steps.entries()) {
    if (!isObject(item) || typeof item.locator_name !== "string" || typeof item.text_chars !== "number" || !Number.isInteger(item.text_chars) || item.text_chars < 1) return null;
    steps.push({ position: index + 1, label: item.locator_name ? `Type into field “${item.locator_name}”` : "Type into field", textChars: item.text_chars });
  }
  return { owned: answer.owned_test_target, hasTypeSteps: answer.has_type_steps, steps };
}

/** One empty slot per `type` step. */
export function emptyInputs(steps: readonly unknown[]): string[] { return steps.map(() => ""); }
export function setInput(values: readonly string[], index: number, value: string): string[] { return values.map((current, position) => position === index ? value : current); }
/** After a request is sent, no typed value stays in client state, whatever the answer was. */
export function clearInputs(values: readonly string[]): string[] { return values.map(() => ""); }
/** An empty field can never be right (a `type` step always typed at least one character); other checks belong to the API. */
export function inputsFilled(values: readonly string[]): boolean { return values.every((value) => value.length > 0); }

/** A report with the fields the panel reads; anything else (a newer or broken answer) is treated as unavailable. */
export function validConsistency(value: unknown): AgentTaskConsistency | null {
  const item = value as Partial<AgentTaskConsistency> | null | undefined;
  return item && typeof item === "object" && typeof item.eligible === "boolean" && Array.isArray(item.reasons) && typeof item.assessed_sessions === "number" && typeof item.group_sessions === "number" && typeof item.threshold === "number" ? item as AgentTaskConsistency : null;
}

/** The button is offered only when the API says the session is eligible. */
export function canRequestDraft(report: Pick<AgentTaskConsistency, "eligible"> | null | undefined): boolean { return report?.eligible === true; }

const reasonLabels: Record<AgentTaskConsistency["reasons"][number], string> = {
  assessment_inconsistent: "The sessions of this task do not agree often enough to rely on their result. Run the task again to collect more sessions.",
  modal_not_achieved: "Most sessions of this task did not end as achieved, so no test draft is offered.",
  source_not_modal: "This session's result differs from what most sessions of the task reported. Open a session that matches the most common result.",
};
export function consistencyReasonLabel(reason: string): string {
  return Object.hasOwn(reasonLabels, reason) ? reasonLabels[reason as keyof typeof reasonLabels] : reason.replaceAll("_", " ");
}

const percent = (rate: number) => `${Math.round(rate * 1000) / 10}%`;
/** "achieved 4 · not achieved 1": only statuses that occurred. */
export function statusDistribution(counts: Record<string, number>): string {
  const parts = Object.entries(counts).filter(([, count]) => count > 0).map(([status, count]) => `${status.replaceAll("_", " ")} ${count}`);
  return parts.length ? parts.join(" · ") : "none yet";
}
/** Plain-text summary lines of the consistency report, shared by the request panel and the review screen. */
export function consistencyLines(report: { assessed_sessions: number; group_sessions: number; agreement_rate: number | null; modal_status: string | null; threshold: number; small_sample: boolean; status_counts?: Record<string, number> }): string[] {
  const lines = [`${report.assessed_sessions} of ${report.group_sessions} sessions of this task have an assessment.`];
  if (report.status_counts) lines.push(`Results: ${statusDistribution(report.status_counts)}.`);
  lines.push(report.agreement_rate === null
    ? "Agreement: not available."
    : `Agreement: ${percent(report.agreement_rate)} reported ${report.modal_status?.replaceAll("_", " ") ?? "the same result"} (the required agreement is ${percent(report.threshold)}).`);
  if (report.small_sample) lines.push("Few sessions: high agreement says little with so small a sample.");
  return lines;
}

const draftFailures: Record<string, string> = {
  session_not_completed: "This session has not finished, so a draft cannot be made from it yet.",
  assessment_unavailable: "This session has no usable task assessment (it was not an agent-loop session or its assessment is missing).",
  assessment_not_achieved: "The task was not achieved in this session. A draft is made only from an achieved task.",
  assessment_inconsistent: "The sessions of this task do not agree enough. Run the task again to collect more sessions, then retry.",
  origin_not_allowed: "The target is not in the project's allowed origins. A project administrator must allow it first.",
  input_value_not_allowed: "This project is not declared as a test environment you own, so a draft that types values is refused. A project administrator can change that in Project settings.",
  input_value_missing: "A value is missing for one of the typed steps. Fill in every field.",
  input_value_mismatch: "A value does not fit what the session recorded for its step (its length differs). Check each value and its order.",
  input_value_rejected_by_source_policy: "One of the values is not allowed in test source. Use a different value.",
  credentials_in_source: "This draft contains typed test values, so it cannot be revised with a model. Create a new draft from the session instead.",
  evidence_expired: "The saved evidence of this session has expired or is incomplete, so no draft can be built from it.",
  operation_failed: "A step of this session failed, so no draft can be built from it.",
  action_outcome_unknown: "The outcome of a step of this session is unknown, so no draft can be built from it.",
  action_unsupported: "A step of this session cannot be replayed as a test.",
  locator_unavailable: "A step has no verified target, so the draft cannot be built. Labels that look sensitive are not recorded as targets.",
  ephemeral_locator: "A step can only be targeted for the length of that session, so it cannot be replayed as a test.",
  source_policy_rejected: "The test source built from this session breaks the source policy.",
  target_url_invalid: "The target address of this session cannot be used in a test.",
  rendered_source_limit: "The test built from this session is longer than allowed.",
  idempotency_key_conflict: "A draft with this identity already exists for another request. Reload and review it.",
  request_invalid: "The request was malformed. Reload the page and try again.",
};
/** Dashboard wording for a `detail.code` of `POST /vision/explorations/{id}/test-draft`; undefined when the code is not known. */
export function draftFailureMessage(code: string | undefined): string | undefined {
  return code !== undefined && Object.hasOwn(draftFailures, code) ? draftFailures[code] : undefined;
}

const decisionFailures: Record<string, string> = {
  reviewer_must_differ_from_requester: "You requested this draft, so someone else must review it.",
  disposable_credentials_ack_required: "Confirm that the typed test values belong to disposable test accounts before approving.",
  owned_test_target_disabled: "The project is no longer declared as a test environment you own, so a draft with typed values cannot be approved.",
  credentials_in_source: "This draft contains typed test values, so it cannot be revised with a model.",
};
/** The decision route answers with a plain code string (409) for these cases; undefined when the text is not one of them. */
export function decisionFailureMessage(detail: string): string | undefined {
  return Object.hasOwn(decisionFailures, detail) ? decisionFailures[detail] : undefined;
}
export const decisionNotFoundMessage = "This draft was not found, or you do not have permission to review it.";

/** Approving a draft that carries test values needs the disposable-account confirmation (the API enforces it too). */
export function canApproveAgentDraft(containsTestValues: boolean, acknowledged: boolean): boolean { return !containsTestValues || acknowledged; }

/** Reads the origin an agent-session draft records; null for any other draft. */
export function agentTaskProvenance(provenance: Record<string, unknown> | null | undefined): AgentTaskDraftProvenance | null {
  const source = provenance?.agent_trace_source;
  if (!isObject(source) || typeof source.session_id !== "string" || typeof source.trace_hash !== "string") return null;
  const snapshot = provenance?.consistency;
  const consistency = isObject(snapshot) && typeof snapshot.assessed_sessions === "number" && typeof snapshot.group_sessions === "number"
    ? { assessed_sessions: snapshot.assessed_sessions, group_sessions: snapshot.group_sessions, agreement_rate: typeof snapshot.agreement_rate === "number" ? snapshot.agreement_rate : null,
      modal_status: typeof snapshot.modal_status === "string" ? snapshot.modal_status : null, threshold: typeof snapshot.threshold === "number" ? snapshot.threshold : 0, small_sample: snapshot.small_sample === true }
    : null;
  return {
    agent_trace_source: { session_id: source.session_id, trace_hash: source.trace_hash },
    contains_test_values: provenance?.contains_test_values === true,
    owned_test_target: provenance?.owned_test_target === true,
    requested_by: typeof provenance?.requested_by === "string" ? provenance.requested_by : null,
    consistency,
  };
}

/** Where the typed values of a draft came from, for the reviewer. */
export function testValueOrigin(provenance: Pick<AgentTaskDraftProvenance, "contains_test_values" | "requested_by">): string {
  if (!provenance.contains_test_values) return "This draft types no values.";
  const who = provenance.requested_by ? `by ${provenance.requested_by}` : "by the requester";
  return `The values typed in this test were entered ${who} when the draft was requested. They are written as-is in the source above; the session itself kept only their length.`;
}
