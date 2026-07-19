# Phase 0 — Architecture and decisions

**Status:** in progress  
**Prerequisite:** none  
**Exit:** an agreed local threat model and provider-neutral boundaries; all team
members can trace one Web UI test run end to end.

## Learning outcomes

- Explain control, workflow, execution, intelligence, and evidence planes.
- Trace `run_id` and `correlation_id` across every component.
- Explain why PostgreSQL, workflow history, and object storage have different
  ownership, and why the runner alone determines a verdict.

## Checklist

- [ ] Read the README, both architecture documents, and ADR-001; redraw the
  target flow in our own words.
- [x] Read the execution contract; identify common fields and target-specific
  `runner_config`.
- [ ] Walk through the current FastAPI composition, settings boundary, runner
  port, and proposal approval rule.
- [ ] Confirm first-release scope: Web UI only; API/Game are future adapters.
- [ ] Write a local threat model: tenant boundary, secrets/PII, artifact access,
  agent authority, duplicate retries, and auditability.
- [ ] Record ADR decisions or explicit deferrals for LLM, identity/RBAC,
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
