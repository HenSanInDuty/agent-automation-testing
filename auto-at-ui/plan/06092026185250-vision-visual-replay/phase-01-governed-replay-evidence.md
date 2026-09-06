# Phase 01 — Governed replay evidence

## Objective

Define a Vision-only persistent evidence model that can represent a captured
state PNG without attaching it to a deterministic run, and make the approved
no-expiry/until-delete policy explicit.

## Scope and prerequisites

- Depends on no implementation phase. Review the existing completed Vision
  progress-stream migration to avoid overlapping revisions.
- Does not capture screenshots, add HTTP endpoints, or render UI.

## Exact paths

- Add an Alembic migration under `migrations/versions/`.
- Change `packages/contracts/src/auto_at/contracts/vision.py`.
- Change `apps/control-plane/infrastructure/persistence/models.py`.
- Change `apps/control-plane/domain/ports.py` and add/update domain evidence
  value objects in `apps/control-plane/domain/entities.py` if that is where the
  existing `ArtifactRecord` belongs.
- Change `apps/control-plane/infrastructure/persistence/repositories.py`.
- Change `docs/adr/006-proposed-retention-and-deletion.md` and
  `docs/vision-agent-operations.md`.
- Add focused tests beside `tests/test_vision_contracts.py`,
  `tests/test_vision_evidence.py`, and repository tests.

## Detailed behavior and data flow

1. Add a versioned `VisualReplayFrame` metadata contract containing immutable
   frame ID, session ID, state ID, sequence/capture order, checksum, byte count,
   PNG/JPEG content type, and no storage URL. Keep screenshot bytes out of all
   contracts and JSON metadata.
2. Add a `visual_replay_frames` table keyed by UUID with tenant ID, session FK,
   state FK, stable private storage URI/key, checksum, size, content type,
   captured timestamp, `deleted_at`, and deletion actor/timestamp only if the
   existing repository convention supports it. Enforce unique `(session_id,
   state_id)` and add tenant/session ordering indexes.
3. Add an `originating_state_id` nullable FK/index to
   `visual_action_proposals`; new records must set it. This lets a frame overlay
   only candidates made from that screenshot. Existing actions remain readable
   with null association and do not receive guessed backfill.
4. Extend the Vision repository port/SQLAlchemy implementation with idempotent
   frame add/get/list and an atomic tenant-scoped delete/soft-delete operation.
   Define a dedicated Vision replay record instead of changing `ArtifactRecord`,
   whose required `run_id` represents a different lifecycle.
5. Amend ADR-006 with a distinct “Vision replay frames” class: persistent until
   explicit authorized deletion, private object storage, byte-first deletion,
   and no automatic cleanup worker. Document that this is the user-approved
   local product policy and that production privacy/legal approval remains a
   gate.

## Contract/API/schema changes

- Vision contract receives metadata-only frame models; no execution contract
  version changes.
- SQL migration is forward-only; it adds the frame table and nullable action
  linkage with no destructive rewrite or historical backfill.

## Tests and validation

- Validate Pydantic metadata rejects URIs/bytes and invalid checksum/type/size.
- Validate SQL uniqueness, tenant/session filtering, insertion idempotency, and
  legacy actions with null originating state.
- Run `uv run pytest tests/test_vision_contracts.py tests/test_vision_evidence.py`
  plus the added repository tests and `uv run ruff check .`.

## Acceptance criteria

The migration applies to an existing database, a replay frame can be represented
without a test run, actions can identify their source state, and no automatic
retention timestamp is created for replay frames.

## Risks and non-goals

Coordinate migration revision ordering with the existing uncommitted Vision
progress migration. Do not expose, upload, delete, or render a screenshot yet.

## Execution record

Status: completed 2026-09-06 19:03 ICT.

Implemented the replay-only contract, domain record, SQL model/repository, and
forward-only migration `f7a8b9c0d1e2` following the existing `f6a7b8c9d0e1`
head. The replay table has immutable checksum/size/content metadata, a private
storage key, tenant/session ordering, a unique session/state constraint, and no
retention timestamp. Action proposals now have a nullable indexed originating
state link; legacy rows remain null. ADR-006 and the Vision runbook now make
the no-expiry-until-authorized-deletion policy explicit, including the production
privacy/legal gate.

Validation: focused Ruff passed; 11 focused contract/evidence/schema tests
passed; Alembic reports one `f7a8b9c0d1e2` head; `git diff --check` passed.
No deviations or deferred work within this phase.
