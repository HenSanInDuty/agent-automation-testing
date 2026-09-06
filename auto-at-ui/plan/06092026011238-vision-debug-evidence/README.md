# Production Vision debug evidence plan

> **Overall status: completed 2026-09-06T12:34:14+07:00.** The original phase table
> remains as the approved baseline; the completion records below are canonical progress.

## Goal

Provide a production-grade, tenant-isolated mechanism that lets a `tenant_admin`
diagnose why a Vision candidate batch was rejected without putting model output,
prompts, screenshots, temporary image URLs, credentials, or debug payloads in
ordinary logs, activity feeds, standard Vision responses, or non-admin UI. Debug
evidence is redacted, encrypted at rest, fully audited, and irreversibly deleted
seven days after capture.

### Acceptance criteria

- A rejected model response is classified into a stable diagnostic code rather than
  being collapsed by `except Exception` into one generic failure.
- Only an authenticated `tenant_admin` in the record's tenant can list/read debug
  evidence; project admins, viewers, services, cross-tenant callers, and local
  header impersonation in production-like mode receive non-enumerating results.
- Stored payloads use a dedicated deployment-injected encryption key, have a key
  identifier/version, are redacted and size-bounded before encryption, and are
  never written to application/Grafana logs or standard activity/session APIs.
- Every capture, successful or denied read attempt, expiry/deletion attempt, and
  key/decryption/redaction failure produces an audit event without payload data.
- A retry-safe cleanup job deletes debug records at `retention_until` (seven days),
  with operational metrics and a runbook procedure for key rotation and incidents.
- Vision remains advisory: debug capture cannot retry a model call, expand the BFS,
  alter a candidate/action, mutate a test, or influence a deterministic verdict.

## Request and confirmed decisions

| Item | Decision |
| --- | --- |
| Scope | Production design, not local-evaluation-only. |
| Audience | `tenant_admin` only. |
| Evidence | Redacted model diagnostic payload and structured validation/provider metadata; no screenshots, prompts, Drive links, credentials, or raw browser evidence. |
| Encryption | Dedicated application key supplied through the deployment secret boundary; no cloud/KMS vendor selected. |
| Retention | Seven days from capture, then retry-safe deletion. |
| Audit | Capture, access (allowed/denied), expiry, cleanup failure, and cryptographic/redaction failures. |

### Assumptions

- Production authentication continues to populate the existing provider-neutral
  `Principal`; selecting an IdP remains out of scope under ADR-004.
- The production deployment injects a dedicated `VISION_DEBUG_EVIDENCE_*` key via
  its approved secret-management mechanism. This plan deliberately does not select
  a cloud, KMS, or secret vendor.
- Seven days is a product-approved maximum retention. Legal holds, longer retention,
  export, and backup policy changes are out of scope.

## Scout findings

- `apps/control-plane/agents/vision/executor.py` calls the model and wraps response
  extraction plus schema validation in one broad `except Exception`; it returns only
  `vision model returned an invalid candidate batch`.
- `apps/control-plane/agents/vision/service.py` distinguishes malformed JSON,
  wrong root shape, action validation, and candidate-count failures internally but
  discards that detail in its public errors.
- `apps/control-plane/application/vision_events.py` persists safe session state,
  action proposals, activities, and audits; `_unavailable` stores only a safe reason.
- `apps/control-plane/infrastructure/persistence/models.py` has tenant-scoped Vision
  sessions/actions/states and append-only audit/activity tables, but no debug-payload
  record. `SqlAlchemyVisionRepository` is the natural tenant-scoped persistence
  extension.
- `apps/control-plane/agents/vision/intent.py` already uses Fernet and a bounded
  retention check for an encrypted request intent. It must not be reused as the
  debug-evidence key because key separation is required.
- `apps/control-plane/domain/authorization.py` has `tenant_admin` and
  `Permission.MANAGE_TENANT`; `api/v1/routes/vision.py` already resolves a
  `Principal` and returns inaccessible Vision resources as 404.
- `apps/control-plane/application/artifact_retention.py` and
  `infrastructure/workflows/temporal_worker.py` establish the existing periodic,
  idempotent expiry pattern.
- `apps/dashboard/app/vision-dashboard.tsx` displays safe session failure and action
  candidates to ordinary readers. It contains no privileged debug-evidence panel.
- ADR-006 permits retention-driven deletion; ADR-007/008 and
  `docs/vision-agent-operations.md` prohibit raw screenshots/prompts/provider output
  in ordinary records and treat Vision as a bounded advisory capability.

## Constraints and boundaries

- Preserve the versioned target-neutral `TestExecutionRequest` / `TestExecutionResult`;
  this feature is Vision diagnostic metadata and must not modify execution contracts.
- Model/provider remains the existing approved Vision route; no provider, model, data
  region, pricing, cloud, KMS, or authentication provider selection is authorized.
- Treat returned model text as untrusted and potentially sensitive. Apply an
  allow-list schema, secret-pattern redaction, deterministic truncation, byte cap,
  and checksum before encryption. Never log the plaintext, ciphertext, or redaction
  replacements.
- Tenant ID, session ID, correlation ID, actor ID, and audit categories are the only
  correlation data exposed outside the privileged endpoint. Grafana retains only
  safe operational event codes/counts.
- The endpoint is read-only, HTTPS-only in production deployment documentation, and
  no-cache. It must reject service principals even if they have tenant membership.

## Phases

### Progress record

Phase 01 is **completed** at 2026-09-06T03:09:25+07:00. It added the allow-listed
`VisualDiagnosticCode` taxonomy; separated provider, response-envelope, JSON, root,
schema, empty-list, and candidate-limit failures; and introduced a text-only,
secret-redacted, 16 KiB-bounded capture handoff with a checksum. The generic public
candidate-batch detail is unchanged. Changed paths:
`apps/control-plane/agents/vision/diagnostics.py`, `executor.py`, `service.py`, and
`tests/test_vision_executor.py`. Validation passed: `uv run pytest
tests/test_vision_executor.py tests/test_vision_contracts.py` (17 passed), `uv run
ruff check apps/control-plane/agents/vision tests/test_vision_executor.py`, and `git
diff --check`. No execution contracts changed; no payload is persisted or exposed yet.

Phase 02 is **in progress** at 2026-09-06T03:09:25+07:00. It will add encrypted,
tenant-scoped persistence and retention cleanup using the Phase 01 handoff.

Phase 02 is **completed** at 2026-09-06T12:24:54+07:00. It introduced a dedicated
settings/key namespace, Fernet encryption/decryption with key IDs, a migration and
tenant-scoped persistence model, idempotent capture repository methods, and a
decryption-free retry-safe expiry worker. Focused crypto, retention, executor, and
event tests passed (19 tests).

Phase 03 is **completed** at 2026-09-06T12:24:54+07:00. Rejected batches now attempt
one encrypted capture before the unchanged unavailable result. Safe activity/audit
events record only IDs, codes, and capture availability; capture failure remains
fail-closed and cannot retry a model call.

Phase 04 is **completed** at 2026-09-06T12:24:54+07:00. A non-service tenant-admin
permission protects no-store metadata/payload routes and an explicit dashboard action;
the server is the authorization boundary. Focused authorization, route-contract,
workflow, crypto, and dashboard typecheck validations passed.

Phase 05 is **completed** at 2026-09-06T12:34:14+07:00. The Vision and operations
runbooks now document deployment-secret injection, seven-day retention, rotation,
incident response, canary steps, and payload-free observability. `uv run ruff check .`,
dashboard typecheck, `docker compose config --quiet`, and `git diff --check` passed.
The final reconciliation also redacted URLs from captured text, implemented a bounded
previous-key read path, and audited every expiry attempt/outcome. The focused Vision/
auth/retention suite passed (25 tests). The full `uv run pytest` attempt did not
complete in this environment: it stalled at `tests/test_catalog_routes.py` after 18%
with no result, so it is not claimed passed.

| Phase | Objective | Status | Depends on | Validation |
| --- | --- | --- | --- | --- |
| [01](phase-01-diagnostic-taxonomy.md) | Preserve safe root-cause taxonomy at model/validation boundary. | completed | — | Executor/service unit tests |
| [02](phase-02-encrypted-persistence-retention.md) | Persist encrypted, redacted debug evidence and delete it after seven days. | completed | 01 | Migration, repository, crypto, expiry tests |
| [03](phase-03-workflow-audit.md) | Capture evidence fail-closed in Vision workflow and emit audit/safe telemetry. | completed | 01, 02 | Workflow/application tests |
| [04](phase-04-admin-debug-api-dashboard.md) | Expose evidence only to tenant admins through protected API and UI. | completed | 02, 03 | HTTP/RBAC/dashboard tests |
| [05](phase-05-operations-rollout.md) | Operationalize cleanup, key rotation, observability, documentation, and rollout. | completed | 01–04 | Focused suite and deployment checks |

## Risks and rollout

- **Sensitive model output:** cap and redact before encryption; deny ordinary readers;
  use no-cache responses; audit every access. Add synthetic hostile fixtures covering
  prompt injection, bearer tokens, cookies, API keys, passwords, and oversized output.
- **Key loss/rotation:** records encrypted under an unavailable retired key become
  unreadable and must surface a safe `debug_evidence_unavailable` result plus audit;
  deletion remains possible without decryption. Maintain current and previous key IDs
  during a bounded rotation window.
- **Cleanup outage:** expiry job remains retryable; measure overdue records and alert
  the operator. Do not extend retention automatically.
- **Schema drift/provider failures:** persist only normalized error code, safe provider
  status/category, parser/validator path, and redacted bounded content; never make
  diagnostics part of candidate selection.
- **Migration:** deploy schema and cleanup reader before enabling capture. Existing
  sessions have no backfill; their generic safe failure remains unchanged.

## Out of scope

- Storing screenshots, prompts, Drive URLs, request headers, credentials, full browser
  state, or provider request bodies.
- Changing Vision limits, policy consent, model/provider, test generation authority,
  runner contracts, or deterministic verdicts.
- Admin self-service retention extension, tenant export, legal-hold workflow, managed
  KMS selection, and external SIEM/log shipping of debug payloads.
