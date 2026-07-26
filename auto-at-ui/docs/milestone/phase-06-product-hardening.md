# Phase 6 — Product hardening

**Status:** complete
**Prerequisite:** Phase 5 complete and approved auth/deployment/retention ADRs  
**Exit:** the product has an operable dashboard, enforced authorization,
observability, delivery pipeline, and documented production posture.

## Checklist

- [x] Approve identity/RBAC, deployment/tenant isolation, artifact/log
  retention, and deletion policies before production-like integration.
- [x] Implement dashboard views for projects, tests, runs, artifacts, proposals,
  approvals, and audit history; no browser-side business rules/direct DB access.
- [x] Implement `Actor`/`Principal` adapter, project/tenant authorization in
  application queries, and approval permissions.
- [x] Add OpenTelemetry-compatible traces API -> workflow -> worker -> agent;
  attach correlation ID to logs, spans, and artifact metadata.
- [x] Export queue-delay, duration, retries, failure class, artifact failure,
  agent latency/cost, proposal acceptance, and false-healing metrics.
- [x] Add CI gates: Python lint/test/type check, TypeScript lint/type check/
  contract tests, Compose integration, secret/dependency scans, reproducibility.
- [x] Document SLOs, alerts, runbooks, backup/recovery, deployment, and
  operational ownership.

## Completion demonstration

An authorized reviewer can inspect a correlated run/evidence, approve or reject
a proposal, and see an auditable outcome. CI blocks contract, redaction, and
approval-boundary regressions.

## Validation

All quality gates in architecture-implementation section 9 operate in a
non-production environment.
