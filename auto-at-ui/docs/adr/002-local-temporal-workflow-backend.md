# ADR-002: Local Temporal backend behind a workflow port

- Status: Accepted
- Date: 2026-07-23

## Context

Phase 3 needs durable local orchestration for dispatch, retry, timeout,
cancellation, and duplicate delivery. The local development machine can run a
small Docker Compose stack, but selecting a local stack must not select the
production deployment model.

## Decision

Use the pinned `temporalio/auto-setup:1.29.7` image and Temporal UI in Docker
Compose for local development only. The control plane records an outbox event in the same
transaction as a run. A publisher starts a workflow using a deterministic
workflow ID derived from `run_id`; duplicate publication therefore cannot start
a second workflow for the same run.

Application code depends on workflow-publishing and runner ports. The Temporal
SDK and workflow definitions stay in `infrastructure/workflows/`. Workflow
inputs use the versioned `TestExecutionRequest` contract and event envelope;
Temporal history is not an application source of truth. PostgreSQL remains the
source of truth for runs, deterministic results, artifacts, audit events, and
outbox delivery state.

## Consequences

- The local stack gains a separate Temporal Server, UI, and worker process.
- Workflow execution receives bounded retries for infrastructure failures only.
  A runner-reported functional failure is recorded as `failed` and completes
  normally; it is never retried as a workflow error.
- No Temporal Cloud account, production self-hosted topology, tenant/RBAC
  policy, production retention period, or SLO is selected by this ADR.
- Moving to Temporal Cloud or another workflow implementation changes settings
  and infrastructure adapters, rather than HTTP routes, domain rules, or the
  versioned runner contract.

## Local safeguards and deferrals

The local namespace is `auto-at-local`, is not an authorization boundary, and
contains no production credentials. Configuration comes only through
`Settings`; Docker Compose defaults are development-only. Correlation IDs are
carried in the event, workflow input, runner request, and result. Production
tenant isolation, RBAC, secrets source, retention, observability exporter,
SLOs, and workflow deployment remain explicit pre-production decisions.
