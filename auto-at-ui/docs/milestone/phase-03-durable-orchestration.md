# Phase 3 — Durable orchestration

**Status:** planned  
**Prerequisite:** Phase 2 complete and an approved workflow ADR  
**Exit:** dispatch, retry, timeout, cancellation, and duplicate delivery are
safe and observable.

## Checklist

- [ ] Approve and record the workflow-engine/deployment ADR before adding its
  vendor SDK.
- [ ] Implement outbox publication and at-least-once-safe event consumption.
- [ ] Implement workflow dispatch, worker acknowledgement, result recording,
  and artifact handoff through ports.
- [ ] Retry transient/infrastructure errors only; never retry known functional
  failures.
- [ ] Implement bounded retry/backoff, step timeout, run deadline, cancellation
  propagation, and worker notification.
- [ ] Prove duplicate request/completion events cannot duplicate runs, terminal
  results, proposals, or approvals.
- [ ] Emit correlation-aware queue-delay, retry, timeout, and cancellation data.

## Completion demonstration

An injected transient worker failure retries within budget; a functional failure
does not retry; cancellation prevents future retries; replaying a message changes
no business outcome twice.

## Validation

Focused workflow tests plus integration tests with injected timeout and duplicate
event scenarios.
