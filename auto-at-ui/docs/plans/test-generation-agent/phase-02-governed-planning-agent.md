# Phase 2 — governed natural-language planning agent

**Status:** complete  
**Prerequisite:** Phase 1 complete  
**Exit:** A queued natural-language request produces a bounded, schema-valid
Playwright Test draft in `pending_review` or an auditable request `failed`
state. It never creates a run.

## Preconditions

Use the already configured agent provider/runtime and its configured model; do
not select a new provider or model in this phase. The deployment configuration
must supply rate, concurrency, token, and cost limits, a redaction policy
version, a safe unavailable response, and correlated telemetry.

## Checklist

- [x] Process `agent.test_generation.requested.v1` idempotently from the
  outbox; claim `queued` work before changing it to `generating`.
- [x] Build a bounded prompt from only redacted request text, its URL/origin,
  the project policy, and the generated-test schema. The planner receives no
  browser, shell, filesystem, repository, database, dispatch, or approval
  tools.
- [x] Require structured output containing title, Playwright Test source,
  assumptions, stop conditions, and the configured provenance fields. The
  project policy, target URL, and acceptance criteria remain control-plane
  inputs, not model-controlled fields.
- [x] Derive the source hash server-side; validate the response schema and
  reject credentials, unsupported imports/APIs, sources that contradict the
  policy, and invented credentials or acceptance criteria.
- [x] Persist one `pending_review` draft and mark its request `completed`, or
  persist a safe request `failed` reason, idempotently with
  provider/model/prompt/redaction-policy/request-hash/source-hash provenance,
  audit events, and correlation-aware telemetry.
- [x] On outage, malformed output, budget exhaustion, timeout, or policy
  violation, leave no test case, run, or dispatch event. Preserve only
  redacted diagnostic data.

## Completion demonstration

A fixture provider turns an allowed natural-language request into a reviewable
source draft. Provider, schema, budget, or policy failures leave the request
in `failed` and deterministic execution untouched.

## Validation

Planner unit/evaluator fixtures, recursive-redaction and source-policy tests,
budget/rate-limit tests, outbox idempotency tests, and telemetry tests.
