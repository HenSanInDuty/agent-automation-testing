# Phase 01 — Structured logging

## Objective

Make all first-party runtime services emit safe, queryable JSON logs with shared correlation context before adding a collector.

## Scope and prerequisites

- No collector or Compose service is required in this phase.
- Retain Python standard-library logging; do not add a logging SaaS SDK or make application code depend on Fluent Bit/Loki.
- Keep `TestExecutionRequest` / `TestExecutionResult` v1 unchanged. The existing `traceparent` placed in runner config remains an internal propagation value.

## Source paths

| Path | Change |
| --- | --- |
| `apps/control-plane/config.py` | Add bounded settings for log level, JSON logging enablement, and service name defaults; retain this file as the sole Python environment reader. |
| `apps/control-plane/infrastructure/observability/telemetry.py` | Extend request-scoped context to safely expose correlation/trace IDs to logging and add context reset semantics so data cannot leak between requests. |
| `apps/control-plane/infrastructure/observability/logging.py` (new) | Implement JSON formatter, context filter, safe event helper, recursive sensitive-key/value redaction, and one idempotent `configure_logging(settings, service)` bootstrap. |
| `apps/control-plane/infrastructure/observability/__init__.py` | Export the approved logging bootstrap/interfaces. |
| `apps/control-plane/main.py` | Invoke the infrastructure logging bootstrap during application initialization; preserve its route-only/application setup role. |
| `apps/control-plane/infrastructure/workflows/temporal_worker.py` | Replace `basicConfig` with the shared bootstrap and add bounded lifecycle/error events without exception payload leakage. |
| `apps/control-plane/infrastructure/runners.py` | Replace format-string operational events with named, structured transport/timeout events carrying known run/correlation fields. |
| `workers/playwright/src/observability.ts` (new) | Implement the worker JSON logger, typed event fields, recursive redaction, and W3C traceparent parsing without adding a runtime logging dependency. |
| `workers/playwright/src/server.ts` | Log request acceptance, validation rejection, cancellation, execution start/finish, and safe HTTP errors; bind run/correlation/trace context from validated request data. |
| `workers/playwright/src/execute.ts` | Emit only safe lifecycle events around browser start, step outcome, evidence collection, cancellation, and terminal result. Never log page bodies or raw browser output. |
| `tests/test_telemetry.py` and `tests/test_runner_transport.py` | Update/extend Python tests for JSON schema, context isolation, redaction, and transport event fields. |
| `workers/playwright/src/observability.spec.ts` (new) | Test JSON output schema, sensitive-value/key redaction, and valid/invalid traceparent behavior. |

## Detailed behavior

1. Define a common JSON envelope: `timestamp`, `level`, `service`, `environment`, `event`, `message`, `correlation_id`, `trace_id`, `span_id`, `run_id`, `attempt`, and optional non-sensitive numeric fields. Omit unavailable fields rather than serializing null placeholders.
2. Establish one conservative redaction policy shared conceptually across implementations: redact fields named/password-like (`authorization`, `cookie`, `token`, `secret`, `password`, API-key variants) and mask recognizable bearer/basic credentials and query-string secret keys. Apply it before serialization; retain only safe error class/code and approved safe summary.
3. Update `trace_context` to bind context for the request lifetime and reset it afterward. Ensure `main.py` handles exceptions while still returning correlation headers and logging a safe completion/failure event.
4. Configure Python logging once per process to stdout in JSON mode, including Uvicorn/FastAPI and application loggers. Preserve normal level control through `Settings`; do not write files.
5. Create TypeScript helpers that write exactly one JSON object per `console` call. Build context only from validated execution payloads and do not write arbitrary caught error stacks to logs.
6. Add lifecycle event names with stable namespaces such as `api.request.completed`, `workflow.outbox.publish_failed`, `runner.request.accepted`, `runner.step.failed`, and `artifact.verification_failed`.

## Contract, security, and operational notes

- No HTTP response/API schema, database schema, runner request, or result contract changes are expected.
- `correlation_id`, `run_id`, and `trace_id` are log fields only. They must later be parsed by Fluent Bit, not attached as Loki stream labels.
- Raw `exc_info`, request headers, agent inputs, generated test source, DOM content, screenshot-derived data, and Playwright child-process output are prohibited from operational logs.
- Logging is observational. Catch/redaction/serialization failures must fall back to a minimal safe event and not interrupt request execution.

## Validation

```powershell
uv run ruff check apps/control-plane/infrastructure/observability apps/control-plane/infrastructure/runners.py apps/control-plane/main.py tests/test_telemetry.py tests/test_runner_transport.py
uv run pytest tests/test_telemetry.py tests/test_runner_transport.py
npm.cmd run typecheck --prefix workers/playwright
npm.cmd test --prefix workers/playwright
```

## Acceptance criteria

- Python and worker test fixtures can parse every emitted line as JSON and assert required common fields.
- Secret-shaped inputs never appear in emitted records; context disappears after a request context ends.
- Existing runner timeout test still confirms run/correlation observability with the new JSON representation.
- No deterministic result, approval state, or contract test changes are needed.

## Risks and non-goals

- Do not attempt to log every internal value; safe event design is deliberate.
- Do not add OpenTelemetry tracing export in this phase; existing traceparent context is sufficient for log correlation.

## Completion record

- Status: completed 2026-09-01 19:16 +07:00.
- Delivered safe JSON logging, request-context cleanup, worker lifecycle events, and focused redaction/schema tests without changing execution v1 contracts or verdict authority.
- Validation: Python Ruff and 9 focused Pytest tests passed; Playwright worker typecheck passed; worker tests passed (16 passed, 1 existing browser-image test skipped).
- Deviation: used the repository's pinned Corepack pnpm workspace tooling because no worker `package-lock.json` exists.
