# Fluent Bit, Loki, Grafana, and RustFS artifact observability plan

## Goal and acceptance criteria

Replace MinIO completely with RustFS as the durable S3-compatible artifact store, and add structured service/runner diagnostics through Fluent Bit → Loki → Grafana. `/artifacts` becomes short-lived staging only; all completed evidence is checksum-verified, uploaded to RustFS, and accessed through authorized control-plane APIs.

- No MinIO service, `MINIO_*` setting, MinIO text, or `minio://` fixture remains.
- RustFS holds every durable artifact, including bounded/redacted `runner-log` JSONL and `artifact-manifest` JSON evidence; staging is removed only after successful verified promotion.
- Logs are JSON stdout, redacted twice (producer and Fluent Bit), searchable in Grafana by JSON `correlation_id`/`run_id` fields, never high-cardinality labels.
- Expiry deletion is tenant-safe/idempotent for RustFS objects and metadata; migration preserves legacy MinIO until reconciliation succeeds.
- Execution request/result v1 and deterministic verdict authority remain unchanged.

## Confirmed decisions, assumptions, and questions

| Item | Decision |
| --- | --- |
| Log stack | Fluent Bit → Loki → Grafana. |
| Artifact store | Self-hosted RustFS selected by user. |
| RustFS integration | S3 API through `boto3`/`botocore`, Signature V4, path-style endpoint. |
| Upload authority | Control-plane/workflow after verifying worker staging bytes; worker/browser receive no RustFS credentials. |
| Object URI/key | `s3://{bucket}/tenants/{tenant_id}/runs/{run_id}/artifacts/{safe-name}`. |
| Local deployment | Single-node/single-disk RustFS Compose service; production HA/TLS/secret-source are unresolved. |
| Retention | 30 days, per ADR-006. |

Production still needs a chosen RustFS topology, TLS, secret manager, backup/recovery owner, Grafana auth/RBAC, and alert routing. The plan does not grant product tenants direct Grafana or RustFS access.

## Scout evidence

- `docker-compose.yml` currently starts `minio`/`minio-init` but runners write to shared `execution-artifacts:/artifacts`.
- `config.py` has `minio_*`; `VerifiedLocalArtifactPort` in `infrastructure/runners.py` only verifies/persists contained `file://` paths.
- `api/v1/routes/runs.py`, `application/reporting_events.py`, and Temporal wiring read local artifacts directly, so upload, download, reporting, and retention must migrate together.
- `ArtifactModel` already has tenant/run, URI, checksum, size, type, and retention fields—enough for logical S3 URIs without mandatory schema change.
- README, `.env.example`, docs, `tests/test_config.py`, and execution fixtures include MinIO references.
- RustFS documents S3 API 9000, console 9001, `RUSTFS_ACCESS_KEY`/`RUSTFS_SECRET_KEY`, S3 Signature V4 and path-style access. [Quick start](https://docs.rustfs.com/en/installation/linux/quick-start), [Python SDK](https://docs.rustfs.com/en/developer/sdk/python), [compatibility](https://docs.rustfs.com/en/reference/s3-compatibility).

## Constraints

- `config.py` is the sole Python environment reader; RustFS/S3 code belongs in infrastructure behind domain ports.
- Never log/store raw secrets, cookies, headers, agent prompts, bodies, DOM/screenshot content, or browser output in Loki/runner JSONL.
- Validate all staging paths; object keys are generated from trusted tenant/run context, not arbitrary filenames. Existing application RBAC remains the only end-user authorization layer.
- Storage/logging failures must be observable but cannot alter deterministic runner verdicts.

## Phases

| Phase | Objective | Status | Dependencies | Validation |
| --- | --- | --- | --- | --- |
| [01](phase-01-structured-logging.md) | Safe structured logs and correlation context. | completed (2026-09-01 19:16 +07:00) | — | Python/worker focused tests |
| [02](phase-02-runner-log-artifacts.md) | Bounded runner-log/manifest staging evidence. | completed (2026-09-01 19:20 +07:00) | 01 | Worker and artifact tests |
| [03](phase-03-rustfs-artifact-storage.md) | RustFS adapter and complete MinIO replacement. | completed (2026-09-01 19:35 +07:00) | 02 | Storage, API, Compose tests |
| [04](phase-04-compose-observability-stack.md) | Fluent Bit/Loki/Grafana Compose and dashboards. | completed (2026-09-01 20:44 +07:00) | 01 | Compose/config/smoke query |
| [05](phase-05-retention-migration-operations.md) | RustFS retention, safe legacy migration, runbook. | completed (2026-09-01 20:48 +07:00) | 03, 04 | Retention/migration tests |

## Rollout, risks, and out of scope

Inventory MinIO read-only first, copy only after explicit operator confirmation, reconcile counts/bytes/checksums, retain its volume through a rollback window, and never auto-delete it. RustFS supports a tested subset of S3; use only documented bucket/object/head/list/delete operations. Out of scope: production migration execution, managed/cloud services, HA RustFS, SSO, tenant log self-service, trace backend, and verdict/approval changes.

Use `$feature-plan-execution` to implement this plan.

## Execution progress

Phase 01 started 2026-09-01 19:08 +07:00. Scope: introduce safe, context-aware JSON logging in the control plane and Playwright worker without changing the v1 execution contracts or deterministic verdict handling.

### Phase 01 completed — 2026-09-01 19:16 +07:00

- Implemented JSON stdout logging with recursive secret redaction, W3C request context, context cleanup, stable lifecycle events, and safe worker HTTP failures.
- Changed: `apps/control-plane/config.py`, `apps/control-plane/main.py`, `apps/control-plane/infrastructure/observability/{__init__,telemetry,logging}.py`, `apps/control-plane/infrastructure/runners.py`, `apps/control-plane/infrastructure/workflows/temporal_worker.py`, `workers/playwright/src/{execute,server,observability,observability.spec}.ts`, `tests/test_telemetry.py`, and `tests/test_runner_transport.py`.
- Validation passed: `uv run ruff check …`, `uv run pytest tests/test_telemetry.py tests/test_runner_transport.py` (9 passed), `corepack pnpm --dir workers/playwright run typecheck`, and `corepack pnpm --dir workers/playwright test` (16 passed, 1 existing browser-image test skipped).
- Deviation: the repository is a pnpm workspace and has no worker `package-lock.json`, so the plan's npm commands were run through the pinned `corepack pnpm` instead.
- Phase 02 is unblocked and in progress.

### Phase 02 completed — 2026-09-01 19:20 +07:00

- Implemented bounded, recursively redacted `runner-log.jsonl` staging evidence and an `artifact-manifest.json` that records only safe names, metadata, checksums, sizes, and timestamps. Both handwritten and generated-source execution paths preserve v1 result semantics and do not let observability failures affect verdicts.
- Changed: `workers/playwright/src/{execute,observability,observability.spec}.ts`.
- Validation passed: worker typecheck; worker tests (17 passed, 1 existing browser-image test skipped); Python artifact tests (2 passed) with a workspace-local pytest base temp directory because the global Windows pytest temporary directory has an ACL denial.
- Phase 03 is unblocked and in progress.

### Phase 03 completed — 2026-09-01 19:35 +07:00

- Replaced local durable evidence with a path-style SigV4 RustFS adapter. Promotion verifies staging bytes, uploads and heads tenant/run-scoped `s3://` objects before persisting metadata, and removes staging only after promotion succeeds. Authorized RustFS reads now back downloads, archive previews, trace views, archives, and reporting evidence.
- Changed: `pyproject.toml`, `uv.lock`, deployment/config/docs/fixture references, the control-plane RustFS adapter/wiring, and focused storage/config/routing tests.
- Validation passed: `uv lock`; focused Ruff; `uv run pytest tests/test_rustfs_artifacts.py tests/test_verified_artifacts.py tests/test_reporting_event_processor.py tests/test_reporting_routes.py tests/test_run_routes.py --basetemp .pytest-phase3` (13 passed); `docker compose config --quiet`; and a legacy-identifier search outside this plan returned no matches.
- Deferred: the existing Compose worker test invocation did not emit a final summary in this non-interactive shell. Phase 4 adds independent Compose validation; final validation remains required.
- Phase 04 is in progress.

### Phase 04 completed — 2026-09-01 20:44 +07:00

- Verified the checked-in Fluent Bit, Loki, and Grafana Compose topology: finite filesystem buffering and bounded retries, 30-day Loki retention, only `service`/`environment`/`level` stream labels, and a provisioned JSON-field investigation dashboard.
- Validation passed: `uv run pytest tests/test_observability_compose.py tests/test_playwright_worker_compose.py::test_compose_worker_reports_a_deterministic_pass --basetemp .pytest-phase4-final` (2 passed), `docker compose config --quiet`, local Grafana/Loki/Fluent Bit health checks, a Loki range query returning the injected correlation ID, and a query returning no secret-shaped fixture.
- Loki was briefly stopped during a deterministic Compose worker execution; its result remained `passed`, and Loki recovered healthy. The Compose assertion was updated in `tests/test_playwright_worker_compose.py` to include the Phase 02 `runner-log` and `artifact-manifest` evidence artifacts.
- Phase 05 is in progress. Scope: tenant-safe RustFS expiry deletion, an operator-controlled legacy MinIO migration utility, and operational documentation.

### Phase 05 completed — 2026-09-01 20:48 +07:00

- Added `ExpireArtifacts`, which selects expired metadata in bounded batches, deletes scoped RustFS bytes before tenant-qualified metadata, and leaves failed work retryable. The Temporal worker now schedules it with a bounded configuration interval.
- Added `scripts/migrate_minio_to_rustfs.py`: default inventory is read-only; copy mode requires `COPY_LEGACY_MINIO`, verifies copied object size and SHA-256 metadata, and never deletes the source. Operations documentation records both boundaries.
- Validation passed: focused Ruff for the Phase 5 paths; `uv run pytest tests/test_artifact_retention.py tests/test_rustfs_artifacts.py --basetemp .pytest-phase5-final` (4 passed); `docker compose config --quiet`; and `git diff --check`.
- Deviation: this implementation does not run a migration because no source endpoint, credentials, or explicit production migration authorization was supplied. The utility is intentionally operator-controlled.

## Overall completion

Status: completed 2026-09-01 20:48 +07:00. All five plan phases are implemented without changing the v1 execution request/result contracts or deterministic verdict authority. Production RustFS topology/TLS/secrets/backups, Grafana auth/alerting, and any legacy migration execution remain explicitly deferred.
