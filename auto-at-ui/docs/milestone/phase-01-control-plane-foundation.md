# Phase 1 — Control-plane foundation

**Status:** done
**Prerequisite:** Phase 0 complete  
**Exit:** the control plane persists a run lifecycle, audit events, and outbox
events through tested HTTP use cases.

## Checklist

**Persistence progress (2026-07-20):** SQLAlchemy schema, Alembic initial
migration, transaction boundary, and tenant-scoped `RunRepository` are in
place and validated against local PostgreSQL. Repository adapters for the
remaining aggregates will be added with their use cases; therefore the
persistence checklist item remains open.

**Use-case progress (2026-07-21):** `CreateRun`, `GetRun`, `ListArtifacts`,
and `RecordDeterministicResult` are implemented behind domain ports. `CreateRun`
creates a queued run and a `test.run.requested.v1` outbox event, and returns
the original run for a repeated idempotency key.

**HTTP progress (2026-07-21):** create, read, list-artifacts, and record-result
routes have request/response DTOs and delegate to application use cases.
`POST /api/v1/runs` requires `Idempotency-Key`; every run route requires
`X-Tenant-Id` at the local tenant boundary.

**Exit validation (2026-07-21):** the focused and full test suites pass (26
tests), including a PostgreSQL-backed HTTP happy path proving one request
commits the queued run, `run.created` audit event, and requested outbox event.

- [x] Add domain entities, policies, and ports for projects, test cases, runs,
  artifacts, proposals, approvals, audit events, and outbox events.
- [x] Enforce invariants: immutable run revision; runner-only terminal result;
  final approval per proposal version; append-only audit.
- [x] Add SQLAlchemy persistence, Alembic migrations, tenant-aware repositories,
  optimistic versioning, and transaction boundaries.
- [x] Define event envelope and names with correlation, causation, and
  idempotency fields.
- [x] Implement application use cases: create/get run, list artifacts, record
  deterministic result.
- [x] Implement HTTP DTOs/routes; require `Idempotency-Key` when creating a run.
- [x] Add domain, repository, and HTTP tests for validation, duplicates, and
  cross-tenant access.

## Completion demonstration

Creating a Web UI run creates a `queued` run and `test.run.requested.v1` outbox
event atomically. Repeating the idempotency key returns the original run.

## Validation

`uv run ruff check .`, `uv run pytest`, type checking, and migration tests.
