# Phase 4 — dashboard and end-to-end quality

**Status:** complete  
**Prerequisite:** Phases 1–3 complete  
**Exit:** The dashboard supports the complete authorized natural-language
request-to-evidence flow, while regression gates prove the approval and v1
execution boundaries.

## Checklist

- [x] Add a dashboard form for project, target URL, and natural-language
  request. Submit only through the control-plane API; never redact, authorize,
  or decide drafts in the browser.
- [x] Show request (`queued`/`generating`/`completed`/`failed`) and draft
  (`pending_review`/`approved`/`rejected`) status, redacted request, source preview/hash,
  provenance, assumptions, stop conditions, and safe failure messages.
- [x] Provide authorized approve/reject actions and link approved drafts to the
  test case, v1 run, result, and artifacts. Expose project policy management
  only to project and tenant administrators.
- [x] Add client/server tests for loading, authorization failures, polling,
  immutable decisions, and redacted rendering; do not duplicate business rules
  in the dashboard.
- [x] Add a Compose-backed end-to-end scenario: submit → generation → review →
  versioned test case → v1 Temporal dispatch → deterministic result/artifacts.
- [x] Update the API collection, operations/runbook material, architecture,
  metric definitions, and plan progress board with validation evidence.

## Completion demonstration

An authorized contributor submits an allowed public target, inspects the
generated source and assumptions, approves it, and views the resulting
deterministic run and evidence. Unauthorized users, rejected drafts, and
disallowed targets cannot trigger execution.

## Validation evidence

- Dashboard: `npm.cmd run typecheck`, `npm.cmd test`, and `npm.cmd run build`.
- Control plane: Python lint, unit/regression, contract, redaction, and
  approval-boundary checks (run from the repository root with `uv`).
- Compose: use the governed generation collection scenario in the operations
  handbook against the locally configured model gateway; it asserts the full
  authorized flow without giving the dashboard planner or approval authority.
