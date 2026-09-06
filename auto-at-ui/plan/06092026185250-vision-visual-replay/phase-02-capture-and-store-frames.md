# Phase 02 — Capture and store replay frames

## Objective

Durably store the same verified browser-state PNG that the Vision processor
already reads, before temporary provider delivery, without increasing agent
calls or changing exploration outcome semantics.

## Scope and prerequisites

- Requires Phase 01's frame model/repository/migration.
- Uses the existing RustFS configuration and checksum-verification adapter;
  neither a new storage vendor nor a new model/provider is selected.

## Exact paths

- Change `apps/control-plane/application/vision_events.py`.
- Change `apps/control-plane/infrastructure/artifacts/rustfs.py` and, if needed,
  `apps/control-plane/domain/ports.py` for a Vision-specific verified-byte port.
- Change `apps/control-plane/infrastructure/persistence/repositories.py`.
- Change `workers/playwright/src/vision.ts` only if the worker response needs a
  stable capture sequence; preserve its browser and policy checks.
- Update `workers/playwright/src/contract.ts` and
  `workers/playwright/src/contract.spec.ts` only for a deliberate Vision v2
  observation metadata addition; do not alter `TestExecutionRequest` or
  `TestExecutionResult`.
- Add/update `tests/test_vision_event_processor.py`,
  `tests/test_vision_evidence.py`, `tests/test_rustfs_artifacts.py`, and worker
  tests.

## Detailed behavior and data flow

1. After the processor validates root containment, PNG signature, max bytes,
   and SHA-256 for `tree-<state_id>.png`, build the deterministic private key
   `tenants/<tenant>/vision-explorations/<session>/states/<state>.png`.
2. Upload through the RustFS verified-write path with checksum and content type;
   have the adapter reject a key whose tenant/session scope does not match the
   record. Never persist or log a public URL.
3. Re-read/head-verify the stored object before inserting the frame metadata and
   state/action records. If the same state is redelivered, accept only the same
   checksum/content metadata; a mismatch fails closed as replay unavailable and
   creates a safe audit/activity outcome rather than overwriting evidence.
4. Insert frame metadata idempotently, then persist the state. Set every new
   action proposal's `originating_state_id` to the state that produced its
   candidate batch. Continue retaining only safe action fields; never preserve
   `TypeAction.text`.
5. Deliver the in-memory image to the existing temporary-image adapter exactly
   as today. A RustFS upload failure ends only the advisory exploration safely;
   it cannot fabricate a candidate, create a draft, or change a test verdict.
6. Continue worker cleanup after the control plane has confirmed durable storage.
   Old sessions remain non-replayable and should return an empty frame list.

## Contract/API/schema changes

- The worker observation contract changes only if a capture order must be sent
  explicitly; version that worker-local Vision contract deliberately and keep
  legacy request validation separate.
- No target-neutral execution-contract change is expected.

## Tests and validation

- Test a successful state writes one tenant-scoped PNG and immutable metadata.
- Test checksum/size/signature/root violations, storage failures, duplicate
  event delivery, and same-key checksum mismatch fail closed without model/draft
  side effects.
- Test action-to-originating-state association and ensure typed text is absent.
- Run `uv run pytest tests/test_vision_event_processor.py tests/test_vision_evidence.py tests/test_rustfs_artifacts.py` and worker test/typecheck commands already used by the repository.

## Acceptance criteria

Every new completed or unavailable exploration retains any successfully captured
state frames, and each retained frame is private, checksum-verified, tenant
scoped, and linked to its safe model proposals.

## Risks and non-goals

Do not use the Google Drive delivery URL as replay storage: it may be
unlisted/public and is intentionally absent from durable records. Do not create
video, action execution telemetry, or additional model calls.

## Execution record

Status: completed 2026-09-06 19:11 ICT.

The processor now stores an already-validated PNG at its deterministic private
replay key before persisting frame metadata or making temporary provider
delivery available. RustFS head-verifies every write and refuses to overwrite
an existing frame whose size/checksum differ; matching deliveries are
idempotent. The replay storage dependency is a domain port injected by the
Temporal composition root. State-linked safe action proposals are retained as
before and no additional model request, draft decision, verdict, worker
contract, or execution contract was introduced.

Validation: 19 focused Python tests passed; focused Ruff, worker TypeScript
typecheck, and `git diff --check` passed. The worker Playwright test listing
reported no discoverable tests, so it was not counted as a passing validation.
