# Phase 02 — Advisory reporting agent and durable workflow

## Objective

Queue and execute one bounded, advisory run-report agent after every result-bearing terminal run,
without changing deterministic execution or existing failure triage.

## Prerequisites

- Phase 01 report contracts, safe evidence builder, repository, and migration are complete.

## Source paths

- Add `apps/control-plane/agents/reporting/service.py` and `executor.py`.
- Add `apps/control-plane/application/reporting.py` and `reporting_events.py`.
- Update `apps/control-plane/application/runs.py` to enqueue the report event after
  `RecordDeterministicResult` for `passed`, `failed`, `errored`, and `skipped` results.
- Update `apps/control-plane/application/runs.py` `PublishOutbox` handler protocol/wiring as needed.
- Update `apps/control-plane/infrastructure/workflows/temporal_worker.py` to inject the reporting
  processor with run/configuration/artifact/report/activity repositories.
- Extend `apps/control-plane/config.py` only with additive, bounded report-specific prompt-version
  settings if the existing general runtime guard cannot distinguish reporting provenance; do not
  add a provider/model selection.
- Add tests: `tests/test_reporting_executor.py`, `tests/test_reporting_event_processor.py`, and
  updates to `tests/test_run_use_cases.py` and `tests/test_outbox_publishing.py`.

## Behavior and data flow

1. After the worker result has been persisted and artifacts verified, enqueue
   `agent.run_report.requested.v1` with run ID/correlation and idempotency key
   `run-report:<run-id>:v1`. Emit an audit event and `reporting/requested` activity.
2. Keep `RequestFailureTriage` exactly as-is: only `failed`/`errored` additionally queue triage.
   A passed run queues reporting but no triage.
3. The reporting processor claims/loads the tenant-scoped terminal run, obtains verified artifact
   references/excerpts, resolves existing `agent.runtime.v1`, applies one-step/token/evidence-byte
   guards, and invokes the existing provider-neutral language model adapter.
4. Prompt the agent to summarize only supplied facts. It must preserve the deterministic status,
   identify a concrete failed location only if present in safe evidence, name unverified/omitted
   scope, and return the strict report schema. It must not claim that it reran, fixed, approved, or
   changed anything.
5. Apply the existing fallback behavior once. On provider/guard/schema failure, persist an
   `unavailable` report with a safe reason and provenance/input hash where available; never expose
   provider diagnostic text.
6. On success, persist exactly one `completed` report and activities for completed/unavailable.
   Retries reuse the idempotency key and return the existing report rather than issue another model
   call.

## Operational and security requirements

- One report invocation per result-bearing run; same configured concurrency, rate/cost guard, and
  fallback as triage. Add structured logs/telemetry counters and correlation IDs for queue,
  execution, success, unavailable, guard exhaustion, and latency.
- Read artifacts only after `VerifiedLocalArtifactPort`/repository authorization; redaction happens
  before agent input and persistence. Never write an artifact, alter a test/run, or access browser,
  shell, database outside the application/repository boundary.
- The report agent has no approval, dispatch, runner, or source-repository tool.

## Validation

```bash
uv run pytest tests/test_run_use_cases.py tests/test_outbox_publishing.py \
  tests/test_reporting_executor.py tests/test_reporting_event_processor.py
uv run ruff check apps/control-plane packages/contracts/src tests
uv run pytest
```

## Acceptance criteria

- One pass, one fail, one error, and one skipped result each enqueue and persist exactly one report;
  cancellation without a result does not.
- Failure evidence containing a Playwright `file:line:column` and assertion message is reported as
  a safe location/reason; missing evidence results in explicit “location unavailable.”
- Provider failure, malformed response, or exhausted guard yields an unavailable report and leaves
  the immutable result and triage behavior unchanged.
- Retried outbox delivery does not duplicate reports or model calls.

## Risks and non-goals

- This phase does not add notifications, report editing, or a human approval action.
- Do not use screenshots/trace/video in prompts without a separately approved evidence policy.

## Completion record

- Status: completed 2026-08-13T23:13:48+07:00.
- Delivered durable report request/outbox handling, bounded advisory execution with existing
  runtime/fallback/guard policy, immutable unavailable persistence, activities, and Temporal worker
  composition. Triage remains confined to failed/errored results.
- Validation: scoped Ruff passed; focused reporting/outbox/use-case pytest suite passed (21 tests);
  `git diff --check` passed. Existing `TestRun` collection warning is unrelated.
- Deviation: structured logs provide per-report status and latency, but a metrics exporter is
  deliberately deferred to production rollout work. Phase 03 may now expose the read-only record.
