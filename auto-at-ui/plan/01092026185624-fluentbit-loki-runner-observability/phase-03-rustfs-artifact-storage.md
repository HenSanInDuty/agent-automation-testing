# Phase 03 — RustFS artifact storage migration

## Objective

Replace MinIO and shared-volume durable evidence with a verified RustFS S3 adapter. Staging remains only a handoff between worker and workflow.

## Exact source paths

| Path | Change |
| --- | --- |
| `pyproject.toml`, `uv.lock` | Add `boto3`/`botocore` through `uv`. |
| `apps/control-plane/config.py`, `.env.example` | Replace every `minio_*`/`MINIO_*` variable with typed `rustfs_*`/`RUSTFS_*` endpoint, credentials, bucket, secure/region/path-style and bounded upload settings; document `artifact_root` as staging. |
| `apps/control-plane/domain/ports.py` | Add narrow verified artifact read/write/delete/list ports, keeping S3 imports out of domain. |
| `apps/control-plane/infrastructure/artifacts/rustfs.py` (new) | Implement path-style SigV4 S3 client, bucket bootstrap, verified put/head/get/range/delete/list, and safe provider error mapping. |
| `apps/control-plane/infrastructure/runners.py` | Separate contained local checksum validation from durable upload. Construct tenant/run-scoped keys, persist `s3://` URI only after upload/head verification, then idempotently clear staging. |
| `infrastructure/workflows/temporal.py`, `temporal_worker.py`, `application/reporting_events.py`, `api/v1/routes/runs.py` | Inject/read through storage adapter for persistence, reports, authorized downloads/traces; remove durable direct-local reads. |
| `docker-compose.yml` | Remove `minio`/`minio-init`; add pinned `rustfs`, `rustfs-init`, `rustfs-data`, documented healthcheck/internal endpoint, and retain staging volume only for handoff. |
| `README.md`, `docs/`, fixtures, config/API/reporting tests | Replace MinIO names/text/URIs with RustFS and standard `s3://`; update backups to RustFS durable volume rather than staging. |
| `tests/test_rustfs_artifacts.py` (new) | Mock S3 client for key isolation, path style, ordering, checksum mismatch, reads, cleanup, upload failures, and no MinIO identifiers. |

## Data flow and constraints

1. Worker returns v1 staging file URIs/checksums without storage credentials.
2. Workflow resolves each URI below `artifact_root`, verifies bytes against runner manifest, uploads to `tenants/{tenant}/runs/{run}/artifacts/{safe-name}`, and verifies object metadata before recording database metadata.
3. Upload/metadata failure preserves staging for retry and logs `artifact.promotion_failed`; it must not create a nonexistent `s3://` record. Delete staging only after full promotion success.
4. Existing API RBAC precedes adapter reads; do not expose object endpoint, console, bucket listing, credentials, or direct URLs. Use only documented S3 operations and non-sensitive metadata.

## Validation

```powershell
uv lock
uv run ruff check apps/control-plane tests/test_rustfs_artifacts.py tests/test_config.py
uv run pytest tests/test_rustfs_artifacts.py tests/test_verified_artifacts.py tests/test_reporting_event_processor.py tests/test_reporting_routes.py tests/test_run_routes.py
docker compose config
uv run pytest tests/test_playwright_worker_compose.py
```

Manual smoke: execute one run; assert persisted `s3://` metadata/object and authorized download SHA-256 after staging containers restart. Tampering/failing upload must leave no false metadata. No MinIO service/config/document/fixture identifier may remain.

## Non-goals

No browser presigned URLs, multi-node RustFS, or legacy-data deletion; those are Phase 05/production operations.

## Completion record

- Status: completed 2026-09-01 19:35 +07:00.
- Implemented checksum-verified RustFS promotion and authorized reads without changing v1 execution request/result semantics or verdict authority. The worker retains no storage credential.
- Validation: focused Ruff and 13 focused Python tests passed; `docker compose config --quiet` passed; no legacy storage identifier remains outside the historical plan.
- Deferred: a Compose worker invocation did not emit a final test summary in the non-interactive shell; the final plan validation will revisit Compose-backed checks.
