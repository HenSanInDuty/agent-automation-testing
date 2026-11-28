# ADR-002: Governed generated-test authority

- Status: Accepted
- Date: 2026-07-27
- Amended: 2026-11-27 (scoped exception for disposable test-account values, ADR-047)

## Context

The platform will turn a natural-language Web UI testing request into a
Playwright Test draft.  Generated source is untrusted input: it must not gain
authority to change a repository, approve itself, or determine a test verdict.

## Decision

- The planner is advisory only. It has no browser, shell, database,
  repository, dispatch, or approval tools.
- A generated draft contains only redacted request text, reproducibility
  hashes, provenance, assumptions, and stop conditions. Raw requests and
  credentials are not persisted or sent to a model, and login and supplied
  credentials are outside v1 scope, except for the scoped exception below.
- A project execution policy owns an allowlist of canonical HTTP(S) origins.
  The control plane rejects credentials, non-HTTP(S) URLs, and origins outside
  that policy before dispatch.
- Generated TypeScript may import only `@playwright/test`; Node.js, shell,
  filesystem, process, package, and direct network APIs are prohibited.
- Approval is immutable and human-authorized. The approval flow, not the
  planner, creates a test case and exactly one deterministic run. The runner
  remains the sole authority for a verdict.
- Generated source is executed only from an isolated temporary workspace. It
  is never written to a source repository or review branch by this feature.

## Scoped exception: disposable test-account values

ADR-047 allows a draft built from an agent task session to carry values for
a disposable test account. This exception applies only when all of these hold:

- The project has `vision_owned_test_target` enabled. The flag is checked
  when the draft is requested and again when it is approved.
- The draft is built from the trace of an agent task session
  (`provenance.agent_trace_source`) and is marked `contains_test_values`.
- The requester supplies each value in the draft request. Values are never
  extracted from the task text, and the model never receives them.

Where the values may appear verbatim. The values are literal in the generated
source and therefore travel with it:

- `generated_test_drafts` (draft source);
- `test_cases.specification` (after approval);
- `test_runs.request` (the `runner_config` of the run);
- `outbox_events.payload` (the `test.run.requested` event);
- Temporal workflow input and history;
- the HTTP request body sent to the worker during execution (transient,
  not stored);
- API and dashboard responses that return the source (run and draft);
- the worker's temporary workspace, removed after each execution;
- run artifacts: trace, DOM snapshots (including password fields),
  screenshots and video. They contain the values even when the test passes.
  `retain_days` stays at 30.

The artifact retention period is not guaranteed in practice: the job that
deletes expired artifacts currently fails for the whole batch on the local
stack (ADR-047, Risks). That defect is tracked outside this decision, so
artifacts may outlive 30 days until it is fixed.

Where the values must not appear. They are never written to raw requests
(`generation_requests`), audit events, logs, or `provenance`.

Paths to a model stay closed for a draft or test case that contains test
values:

- free-text revision of the draft through preflight is rejected with
  `credentials_in_source`;
- `POST /runs/{id}/revised-draft` is rejected with `credentials_in_source`;
- run evidence sent to a model carries no excerpts (neither
  `playwright-output`, which prints the `fill` line when a test fails, nor
  `worker-result`), and the approved source is dropped from the report's
  review context.
A revision therefore means generating a new draft from the session.

Approval conditions for such a draft: the approver holds `DECIDE_PROPOSAL`
(ADR-004), is not the person who requested the draft, sends
`acknowledge_disposable_credentials=true`, and the project flag is still on.
Approval remains immutable, and the only path to a test case and a run stays
the approval flow.

All other rules of this ADR are unchanged: the planner has no tools or
authority, origins are checked against the project allowlist, generated
TypeScript imports only `@playwright/test`, approval is immutable and
human-authorized, and source is executed only from an isolated temporary
workspace.

## Consequences

The existing v1 execution request remains the only cross-language request.
The target-specific `playwright_test_source` runner configuration is validated
before browser startup without changing the v1 envelope.
