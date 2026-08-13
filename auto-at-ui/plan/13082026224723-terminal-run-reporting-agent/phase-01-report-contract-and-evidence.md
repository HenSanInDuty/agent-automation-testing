# Phase 01 — Report contract and safe evidence

## Objective

Create a typed, tenant-scoped, immutable report record and the bounded evidence input needed to
describe successful and failed deterministic runs without changing execution contracts.

## Scope and prerequisites

- No dependency beyond the existing run, artifact, configuration, and migration infrastructure.
- Preserve existing triage contract and proposal storage.

## Source paths

- Add `RunReport`/`RunReportStatus`/typed report sections to
  `packages/contracts/src/auto_at/contracts/agent.py`.
- Add a terminal run-report event value in `packages/contracts/src/auto_at/contracts/events.py`.
- Extend `apps/control-plane/agents/shared/evidence.py` with an allowlisted textual artifact
  extraction interface and a report-specific bounded evidence bundle.
- Add a report record/model and repository port/implementation in
  `apps/control-plane/domain/entities.py`, `apps/control-plane/domain/ports.py`,
  `apps/control-plane/infrastructure/persistence/models.py`, and
  `apps/control-plane/infrastructure/persistence/repositories.py`.
- Add one new Alembic revision in `migrations/versions/` with a `run_reports` table:
  UUID primary key, tenant ID, run ID foreign key, correlation ID, schema/prompt versions,
  deterministic status, report state, JSON payload, provenance/input hash, created timestamp, and
  unique `(tenant_id, run_id, report_version)` constraint.
- Add focused tests under `tests/` for contract validation, redaction/byte caps, repository tenant
  isolation, migration/schema presence, and duplicate insert behavior.

## Behavior and data flow

1. Define a strict report payload: `deterministic_status`, `headline`, `what_ran`,
   `observations`, `failure` (optional, with `stage`, `location`, `message`,
   `evidence_references`), `unverified_or_skipped`, and `limitations`.
2. Define report state independently from run status: `completed` or `unavailable`; both retain
   the original deterministic status. Enforce bounded string/list sizes and forbid extra keys.
3. Build report evidence from the current redacted `EvidenceBundle`. Add text only when all are
   true: artifact kind is allowlisted (initially Playwright output and JSON result), MIME type is
   textual/JSON, the artifact is verified/run-scoped, `include_redacted_text` is true, and byte
   limits permit it.
4. Read the verified file through an artifact port, cap raw bytes, decode defensively, redact,
   cap redacted output, and attach only safe excerpts plus URI/checksum/kind. Exclude trace, video,
   screenshot, unknown MIME types, and unverified paths.
5. Hash the final safe evidence input and persist provenance, never raw provider response, request,
   secret, or binary artifact.
6. Add repository `get_for_run`/`add` methods that always require tenant ID and return an immutable
   record. Create the migration with cascade behavior matching run-owned records.

## Contract/API/schema impact

- Additive agent/report and event contracts only; do not alter `TestExecutionRequest` or
  `TestExecutionResult`.
- Additive `run_reports` table and migration; no changes to `agent_proposals` or approvals.

## Validation

```bash
uv run pytest tests/test_agent_boundaries.py tests/test_persistence_schema.py
uv run pytest tests/test_<new_report_contract>.py tests/test_<new_report_repository>.py
uv run ruff check packages/contracts/src apps/control-plane tests
uv run alembic upgrade head
```

## Acceptance criteria

- Invalid/oversized/extra report output is rejected before persistence.
- A text artifact containing a credential-like value is redacted and no binary data enters the
  bundle.
- A report cannot be read or inserted across tenants, and a duplicate run/version is idempotent.

## Risks and non-goals

- Do not infer a failure location from binary trace/video in this phase.
- Do not backfill old runs or create UI/API yet.

## Completion record

- Status: completed 2026-08-13T22:56:31+07:00.
- Delivered strict report contracts, bounded verified-text evidence, tenant-scoped immutable
  persistence, event contract, Alembic migration, and focused tests.
- Validation: `UV_CACHE_DIR=/tmp/auto-at-uv-cache uv run alembic upgrade head`; focused pytest
  suite passed (13 tests); scoped Ruff passed.
- Deviation: none. Phase 02 may now enqueue and consume the additive event.
