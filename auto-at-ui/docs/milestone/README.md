# Auto-AT implementation milestones

This folder is the learning-and-delivery roadmap for the first product slice:
**deterministic Web UI execution with AI-assisted triage and reviewable healing
proposals**. API and Game remain future adapters behind the same execution
contract.

Shared terms are kept in the [glossary](glossary.md). We add new terms there as
they arise, so explanations do not need to be repeated in later phases.

## Progress board

| Progress | Phase | Product outcome |
| --- | --- | --- |
| In progress | [ ] [Phase 0 — architecture and decisions](phase-00-architecture-and-decisions.md) | Shared vocabulary, invariants, ADR decisions, and local threat model |
| [ ] | [Phase 1 — control-plane foundation](phase-01-control-plane-foundation.md) | Persisted run lifecycle, audit trail, outbox, and HTTP API |
| [ ] | [Phase 2 — Web UI vertical slice](phase-02-web-ui-vertical-slice.md) | A deterministic Playwright run with stored evidence |
| [ ] | [Phase 3 — durable orchestration](phase-03-durable-orchestration.md) | Safe retries, timeouts, cancellation, and idempotent delivery |
| [ ] | [Phase 4 — governed intelligence](phase-04-governed-intelligence.md) | Redacted triage/healing proposals with an explicit approval boundary |
| [ ] | [Phase 5 — thesis benchmark](phase-05-thesis-benchmark.md) | Repeatable baseline, comparison, ablation, and result manifest |
| [ ] | [Phase 6 — product hardening](phase-06-product-hardening.md) | Dashboard, RBAC, telemetry, CI/CD, and operational quality gates |

**Overall progress:** 0/7 phases complete; Phase 0 is in progress.

## How status is maintained

1. Every phase starts with `Status: planned` and unchecked task boxes.
2. When work starts, change that line to `Status: in progress`; check only the
   completed task(s). Keep the matching overview checkbox unchecked.
3. A phase becomes `done` only when every required checkbox and every exit
   criterion in its file is satisfied and its smallest relevant validation has
   passed. Then check its overview row and update the overall count.
4. If a decision or external dependency blocks work, use `Status: blocked —
   <reason>`; do not mark unfinished work done.

The overview is the source for phase-level progress. The individual phase file
is the source for task-level progress. We will update both together in each
working session.

## Delivery principles

- Work from Phase 0 to Phase 6; do not skip an exit criterion merely to reach a
  later feature.
- Build a thin, testable vertical slice before adding abstraction or AI.
- Preserve `TestExecutionRequest` and `TestExecutionResult` v1 as the
  cross-language boundary. Any change needs a deliberate versioning decision
  and Python/TypeScript contract tests.
- The runner is the only verdict authority. An agent can create an auditable
  proposal, never silently pass a failed test or mutate a suite.
- Use `uv` for all Python dependency and validation commands.

## Session rhythm

For each checked item we will: explain the design with one concrete run, inspect
the relevant code, write a focused test, implement the smallest change, run
validation, and record progress here. The explanation checkpoint is part of
completion: you should be able to describe the data flow, authority boundary,
and failure behaviour in your own words.
