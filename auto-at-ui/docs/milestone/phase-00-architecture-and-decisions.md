# Phase 0 — Architecture and decisions

**Status:** done
**Prerequisite:** none  
**Exit:** an agreed local threat model and provider-neutral boundaries; all team
members can trace one Web UI test run end to end.

## Learning outcomes

- Explain control, workflow, execution, intelligence, and evidence planes.
- Trace `run_id` and `correlation_id` across every component.
- Explain why PostgreSQL, workflow history, and object storage have different
  ownership, and why the runner alone determines a verdict.

## Checklist

- [x] Read the README, both architecture documents, and ADR-001; redraw the
  target flow in our own words.
- [x] Read the execution contract; identify common fields and target-specific
  `runner_config`.
- [x] Walk through the current FastAPI composition, settings boundary, runner
  port, and proposal approval rule.
- [x] Confirm first-release scope: Web UI only; API/Game are future adapters.
- [x] Write a local threat model: tenant boundary, secrets/PII, artifact access,
  agent authority, duplicate retries, and auditability.
- [x] Record ADR decisions or explicit deferrals for LLM, identity/RBAC,
  workflow engine, deployment/tenant model, and retention/deletion policy.

## Decision boundary

No cloud provider, LLM provider/model, auth provider, workflow deployment mode,
or production retention period is selected without explicit user direction.
Until then, code only ports and local/provider-neutral adapters.

## Completion demonstration

Narrate: `POST /runs` -> transactional DB write/outbox -> dispatch -> worker ->
result/artifacts -> optional proposal -> immutable approval. Existing checks pass:
`uv run ruff check .` and `uv run pytest`.

## Questions awaiting your answer

Answer these before we continue the Phase 0 architecture walkthrough:

1. If a worker executes a test and it fails, may the AI immediately rerun the
   test? Why or why not?
2. If a human approves a healing proposal, why must the system still perform a
   deterministic rerun before considering that healing valid?

## Decisions intentionally deferred

These do not need an answer in the next session. They require explicit user
direction before their respective production-like phases: LLM provider/model and
data budget (Phase 4), authentication provider and RBAC model (Phase 6),
workflow engine/deployment mode (Phase 3), cloud/tenant model, and production
artifact/log retention policy (Phase 6).

| Decision | Current record | Revisit by |
| --- | --- | --- |
| LLM provider/model, data budget and rate limits | Deferred; only a provider-neutral agent port and redaction boundary are permitted. | Phase 4 |
| Identity provider and RBAC model | Deferred; local development has one trusted developer and must not define production authorization. | Phase 6 |
| Workflow engine and deployment mode | Deferred; workflow remains a port and local services do not establish the production choice. | Phase 3 |
| Cloud/deployment and tenant model | Deferred; no cloud or multi-tenant assumption is encoded in the contract. | Before production-like deployment |
| Artifact/log retention and deletion | Deferred; local artifact policy is not a production retention policy. | Phase 6 |
