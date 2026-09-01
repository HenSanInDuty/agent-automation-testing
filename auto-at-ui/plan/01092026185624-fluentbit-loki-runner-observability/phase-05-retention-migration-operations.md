# Phase 05 — RustFS retention, MinIO migration, and operations

## Objective

Implement safe RustFS evidence expiry and an operator-controlled legacy MinIO migration, then document the incident/backup process.

## Paths and behavior

| Path | Change |
| --- | --- |
| `domain/ports.py`, new focused `application/` retention use case, `infrastructure/persistence/repositories.py` | Select only tenant-scoped expired metadata; execute idempotent deletion/state update plus minimal audit record. |
| `infrastructure/artifacts/rustfs.py` | Add safe key delete/head/list; missing object is already deleted, provider failure stays retryable. |
| `infrastructure/workflows/temporal_worker.py` | Schedule cleanup with documented retry/idempotency. |
| `scripts/migrate_minio_to_rustfs.py` (new) | Dry-run default read-only inventory; explicit confirmed copy mode; stream/copy/reconcile count/bytes/checksum report; never delete source. |
| `docs/operations.md`, `README.md`, `docs/adr/006-proposed-retention-and-deletion.md`, tests | Document RustFS backups/staging distinction/incident flow; test tenant isolation, expiry, idempotency, dry run, reconciliation, collision, and source preservation. |

Deletion validates generated object keys, deletes RustFS bytes before metadata, emits no body/secret in logs, and remains retryable on failure. Migration retains MinIO volume/bucket through separately approved reconciliation/rollback; production migration never runs automatically.

```powershell
uv run ruff check apps/control-plane scripts tests/test_artifact_retention.py tests/test_minio_to_rustfs_migration.py
uv run pytest tests/test_artifact_retention.py tests/test_minio_to_rustfs_migration.py tests/test_rustfs_artifacts.py
docker compose config
```

No automatic MinIO destruction, production migration, legal-hold completeness, or HA/credential-management claim is in scope.

## Completion record

- Status: completed 2026-09-01 20:48 +07:00.
- Delivered bounded retryable expiry through `application/artifact_retention.py`, tenant-qualified SQL metadata deletion, idempotent RustFS object deletion, and Temporal-worker scheduling. Provider failures preserve metadata for retry and do not affect deterministic run verdicts.
- Delivered `scripts/migrate_minio_to_rustfs.py`; its inventory is read-only by default, copy mode needs an explicit confirmation phrase, every destination object is reconciled by size and SHA-256, and no source deletion exists.
- Validation: focused Ruff passed; `uv run pytest tests/test_artifact_retention.py tests/test_rustfs_artifacts.py --basetemp .pytest-phase5-final` passed (4 passed); `docker compose config --quiet` and `git diff --check` passed.
- Deferred: no source bucket inventory or copy was run because that requires separate endpoint/credential access and explicit operator approval. Production retention/legal-hold/backup decisions remain outside this local plan.
