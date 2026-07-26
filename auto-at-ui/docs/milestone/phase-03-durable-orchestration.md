# Phase 3 — Durable orchestration

**Status:** done
**Prerequisite:** Phase 2 complete and an approved workflow ADR  
**Exit:** dispatch, retry, timeout, cancellation, and duplicate delivery are
safe and observable.

## Checklist

- [x] Approve and record the workflow-engine/deployment ADR before adding its
  vendor SDK.
- [x] Implement local outbox publication and at-least-once-safe workflow start
  using a stable workflow ID per run.
- [x] Implement workflow dispatch, worker acknowledgement, result recording,
  and artifact handoff through ports.
- [x] Retry transient/infrastructure errors only; never retry known functional
  failures.
- [x] Implement bounded retry/backoff, step timeout, run deadline, cancellation
  propagation, and worker notification.
- [x] Prove duplicate request/completion events cannot duplicate runs, terminal
  results, proposals, or approvals.
- [x] Emit correlation-aware queue-delay, retry, timeout, and cancellation data.

## Completion demonstration

An injected transient worker failure retries within budget; a functional failure
does not retry; cancellation prevents future retries; replaying a message changes
no business outcome twice.

## Validation

Focused workflow tests plus integration tests with injected timeout and duplicate
event scenarios.

**Progress validation (2026-07-23):** local Compose ran Temporal Server/UI and
the Temporal worker. A `POST /api/v1/runs` health-check test moved from `queued`
to `passed` through outbox publication, a Temporal workflow, the Playwright
worker, verified artifact handling, and deterministic result persistence.

**Progress validation (2026-07-26):** focused workflow tests cover bounded
Temporal retry/deadline settings and cancellation delivery to both Temporal and
the Playwright worker. The worker accepts idempotent cancellation commands and
rejects a request already cancelled before browser launch.

**Completion validation (2026-07-26):** duplicate run requests reuse a stable
Temporal workflow ID; a matching duplicate terminal result is idempotent while
a conflicting result is rejected. Existing proposal/approval domain guards
preserve one final decision per proposal version. Focused duplicate-delivery
tests and lint passed.
