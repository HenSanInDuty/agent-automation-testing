# Phase 1 — Control-plane foundation

**Status:** planned  
**Prerequisite:** Phase 0 complete  
**Exit:** the control plane persists a run lifecycle, audit events, and outbox
events through tested HTTP use cases.

## Checklist

- [ ] Add domain entities, policies, and ports for projects, test cases, runs,
  artifacts, proposals, approvals, audit events, and outbox events.
- [ ] Enforce invariants: immutable run revision; runner-only terminal result;
  final approval per proposal version; append-only audit.
- [ ] Add SQLAlchemy persistence, Alembic migrations, tenant-aware repositories,
  optimistic versioning, and transaction boundaries.
- [ ] Define event envelope and names with correlation, causation, and
  idempotency fields.
- [ ] Implement application use cases: create/get run, list artifacts, record
  deterministic result.
- [ ] Implement HTTP DTOs/routes; require `Idempotency-Key` when creating a run.
- [ ] Add domain, repository, and HTTP tests for validation, duplicates, and
  cross-tenant access.

## Completion demonstration

Creating a Web UI run creates a `queued` run and `test.run.requested.v1` outbox
event atomically. Repeating the idempotency key returns the original run.

## Validation

`uv run ruff check .`, `uv run pytest`, type checking, and migration tests.
