# Phase 1 - trajectory contracts and storage

## Objective

Establish an append-only, redacted trajectory-edge model that accurately connects a parent state, one model proposal, its observed child state when present, and a safe outcome.

## Scope and prerequisites

Use the existing Vision-only contract boundary and PostgreSQL persistence. This phase is schema/data access only: it does not change worker behavior, expose an API, or redesign the dashboard.

## Source paths to change

- `packages/contracts/src/auto_at/contracts/vision.py`
- `packages/contracts/src/auto_at/contracts/__init__.py` if it exports new public types
- `apps/control-plane/domain/entities.py`
- `apps/control-plane/domain/ports.py`
- `apps/control-plane/infrastructure/persistence/models.py`
- `apps/control-plane/infrastructure/persistence/repositories.py`
- `migrations/versions/<new_revision>_add_visual_trajectory_edges.py`
- `tests/test_vision_contracts.py`
- `tests/test_persistence_schema.py` and/or a focused new `tests/test_vision_trajectory_repository.py`

## Detailed behavior and data flow

1. Introduce a frozen, extra-forbidden `VisualTrajectoryEdge` v1 contract. Bound the IDs, timestamps, duration, confidence, and safe enums. Represent action summaries only with existing safe numeric fields; omit `TypeAction.text` and `expected_outcome`.
2. Define explicit safe edge lifecycle values such as `proposed`, `attempting`, `observed`, `no_meaningful_change`, `rejected`, `failed`, and `terminal`, plus a bounded classification/code enum for `model_stop`, `hop_limit`, `state_limit`, `session_timeout`, `policy_block`, `navigation_failed`, `capture_failed`, `candidate_rejected`, and `draft_handoff_unavailable`. Do not store free-form worker/provider errors in the edge.
3. Add an immutable `visual_trajectory_edges` table linked to session, parent state, proposal, and nullable child state. Store action summary JSON, confidence, safe status/code, capture/result timestamps, non-negative duration, URL fingerprint/change classification, and optional child screenshot checksum. Include tenant/session indexes and uniqueness on the session/proposal/attempt identity that makes duplicate outbox processing harmless.
4. Keep state/frame/proposal tables unchanged except adding a narrow relationship/index only if needed for referential integrity. Do not overload `visual_action_proposals` with mutable result fields.
5. Add a domain record and repository/port operations to insert-or-verify immutable edges, update only a bounded pre-observation attempt record when required by the chosen lifecycle, list ordered session edges, and query edges by parent/child state. Ensure tenant filters are present in every query.
6. Specify deterministic ordering: parent state capture sequence, proposal sequence, then edge ID. Define a pure helper for default-path selection later: complete/observed child paths score by cumulative confidence; ties use state/proposal sequence then UUID lexical order. Stop/failed edges are displayed but cannot invent a child state.

## Contract/schema changes

- New internal advisory `VisualTrajectoryEdge` v1 only; do not change `TestExecutionRequest` or `TestExecutionResult`.
- Additive migration with nullable child/observation fields so failed actions and historical sessions are representable.
- No raw URL, page title, screenshot bytes/storage key, type text, expected outcome, prompt, or provider result field.

## Tests and validation

- Contract tests reject unknown fields, raw text/URLs, invalid UUIDs/enums/checksums, negative duration, and invalid confidence.
- Repository tests prove tenant isolation, stable ordering, immutable duplicate acceptance, mismatch rejection, nullable child/error edge behavior, and no regression in replay frame listing/deletion.
- Run `uv run ruff check apps/control-plane packages/contracts/src tests/test_vision_contracts.py tests/test_persistence_schema.py tests/test_vision_trajectory_repository.py` and the corresponding focused `uv run pytest` files.
- Run `uv run alembic heads` and migration upgrade/check against the local test database according to existing migration-test conventions.

## Acceptance criteria

An authorized application caller can persist and retrieve a redacted edge for every proposed branch without ambiguous parent/action/child association; duplicate delivery cannot silently create a second or divergent edge.

## Risks and non-goals

The status taxonomy must remain small enough to be safe and meaningful. Do not expose the new storage through routes yet, backfill historical outcomes, alter retention, or select a provider.

## Execution record

- Status: completed 2026-09-07 21:38 +07:00.
- Changed: `packages/contracts/src/auto_at/contracts/vision.py`, `packages/contracts/src/auto_at/contracts/__init__.py`, `apps/control-plane/domain/entities.py`, `apps/control-plane/domain/ports.py`, `apps/control-plane/infrastructure/persistence/models.py`, `apps/control-plane/infrastructure/persistence/repositories.py`, `migrations/versions/f8a9b0c1d2e3_add_visual_trajectory_edges.py`, and focused contract/schema/repository tests.
- Validation passed: `uv run ruff check apps/control-plane packages/contracts/src tests/test_vision_contracts.py tests/test_persistence_schema.py tests/test_vision_trajectory_repository.py`; `uv run pytest tests/test_vision_contracts.py tests/test_persistence_schema.py tests/test_vision_trajectory_repository.py` (9 passed); `uv run alembic heads`; `git diff --check`.
- Deferred validation: an actual migration upgrade was not run because no local test database was available.
