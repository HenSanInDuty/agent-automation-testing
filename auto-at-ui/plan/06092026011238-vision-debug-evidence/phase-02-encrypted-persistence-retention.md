# Phase 02 — Encrypted persistence and seven-day expiry

## Objective

Add tenant-scoped encrypted debug-evidence persistence with a fixed seven-day
retention deadline and retry-safe deletion.

## Scope and prerequisites

- Depends on Phase 01's typed, bounded capture handoff.
- Reuse the Fernet implementation pattern from `agents/vision/intent.py`, but introduce
  a separate debug-evidence key namespace and key ID. Do not reuse
  `VISION_INTENT_ENCRYPTION_KEY`.

## Changes

1. Add Settings for a required-on-capture dedicated key and explicit key ID, e.g.
   `VISION_DEBUG_EVIDENCE_ENCRYPTION_KEY`, `VISION_DEBUG_EVIDENCE_KEY_ID`, a fixed
   `VISION_DEBUG_EVIDENCE_RETENTION_DAYS=7` constrained to seven for this approved
   policy, a payload byte cap, and cleanup batch/interval settings. Document deployment
   secret injection only; do not put secret values in `.env.example` beyond placeholders.
2. Add `agents/vision/debug_evidence.py` for deterministic redaction, UTF-8/size cap,
   JSON canonicalization, Fernet encryption/decryption, key-ID validation, and a safe
   unavailable result. Redact before encryption; store content SHA-256 after redaction;
   never store original exception objects or raw response envelopes.
3. Add a migration and model in `infrastructure/persistence/models.py` for
   `vision_debug_evidence`: UUID, tenant/session/correlation IDs, optional state ID,
   diagnostic code, provider/model/prompt version, encrypted payload, key ID, payload
   checksum/byte count, redaction version, captured/retention/deleted timestamps. Index
   `(tenant_id, session_id)` and `(retention_until, id)`; make a session/state/attempt
   idempotency key unique to tolerate at-least-once workflow delivery.
4. Extend `VisualExplorationRepository` in `domain/ports.py` and
   `SqlAlchemyVisionRepository` with tenant-scoped add/list/get/delete-expired methods.
   Read metadata separately from ciphertext; the route must never receive ORM objects
   containing ciphertext by accident.
5. Add an application cleanup use case alongside `ExpireArtifacts` that deletes an
   expired record without decrypting it, is idempotent, and returns deleted/failed/
   overdue counts. Wire it into the existing periodic Temporal-worker cleanup loop.
6. Add minimal audit records for capture and expiry; audit metadata must contain IDs,
   diagnostic code, key ID, retention deadline, and deletion outcome only.

## Tests and validation

- Add migration/model/repository tests using tenant isolation, duplicate event delivery,
  expired record selection, and deletion without a decryption key.
- Add crypto tests for separate keys, invalid/rotated key ID, tampered ciphertext,
  deterministic redaction, payload cap, checksum, and no secret leakage.
- Extend `tests/test_artifact_retention.py` or add `tests/test_vision_debug_retention.py`
  for on-time deletion, retry after failure, and no cross-tenant deletion.
- Run focused tests plus `uv run ruff check apps/control-plane tests`.

## Acceptance criteria

Only redacted, bounded ciphertext is persisted; its deadline is capture time plus seven
days. A key failure blocks new capture safely but cannot block deletion. No existing
Vision session/action schema or execution contract changes.

## Risks and non-goals

This phase defines a secret-injection interface, not a cloud KMS/secret provider.
No backfill of historical failures and no retention override are allowed.

## Completion record

- Status: completed 2026-09-06T12:24:54+07:00.
- Added separate key settings, encrypted record migration/model/repository, seven-day
  expiry application use case and worker loop, and crypto/retention tests. A bounded
  previous-key read path supports rotation without changing the current capture key.
- Validation: focused Vision crypto/retention/executor tests passed; lint passed.
