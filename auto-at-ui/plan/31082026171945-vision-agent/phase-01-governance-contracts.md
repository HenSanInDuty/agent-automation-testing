# Phase 1 — Governance and contracts

## Objective

Define a versioned, provider-neutral visual exploration contract and a
tenant-scoped policy that is disabled by default and records raw-image consent.

## Scope and prerequisites

- Use the confirmed Hugging Face provider and raw-screenshot consent decision.
- Preserve `TestExecutionRequest` / `TestExecutionResult` v1; do not add
  visual actions to either type.
- Reuse `agent.runtime.v1` and the `configs` repository rather than creating a
  second secret-bearing configuration store.

## Exact paths and changes

- Change `apps/control-plane/agents/shared/runtime.py` and `config.py` to add
  a nested `vision` policy: `enabled`, `provider` (initially Hugging Face only),
  `model`, `raw_screenshot_transfer_accepted`, `max_steps`,
  `max_screenshot_bytes`, `max_session_seconds`, `max_cost_usd`, and
  `max_requests_per_minute`.  Validate that an enabled policy requires the
  consent flag, a supported provider, and all bounded values.
- Add `packages/contracts/src/auto_at/contracts/vision.py` and export it from
  the contracts package.  Define a `VisualExplorationRequest`/result state,
  visual evidence metadata (artifact ID/checksum/content type/byte count, not
  URL or bytes), an allowlisted action schema (`click`, `type`, `scroll`,
  `wait`, `stop`), normalized coordinates, expected observable outcome,
  confidence, and stop conditions.  Forbid unknown fields and bound every
  string/list/value.
- Extend `packages/contracts/src/auto_at/contracts/agent.py` only as needed to
  express a `VISION` proposal kind and provenance that includes visual contract
  and prompt versions; do not weaken existing evidence contracts.
- Add a migration under `migrations/versions/` plus persistence models and
  repositories for a tenant/project-scoped visual exploration session and
  immutable action proposals.  Store IDs, hashes/checksums, policy/model/prompt
  versions, status, correlations, timestamps, and safe failure reason only.
  Store neither image bytes nor provider request/response bodies.
- Add application/domain ports in `apps/control-plane/domain/ports.py` and
  `apps/control-plane/domain/` for session state and idempotent proposal
  persistence.  Use `ConfigurationRepository` for policy and keep authorization
  decisions outside domain models.
- Add `apps/control-plane/api/v1/routes/vision.py` request/response schemas
  and route registration in `api/v1/router.py`: read policy, tenant-admin
  policy update, submit/list/get exploration, and no direct model/worker calls.
  Authorize policy updates as tenant admin; authorize submission against the
  selected project's existing generation/run permissions and origin policy.

## Data flow

1. Settings provide non-secret bootstrap defaults; tenant override validates
   over them at `agent.runtime.v1`.
2. A tenant admin enables vision only after affirmative raw-image consent;
   saving emits an audit event with actor, tenant, policy version, and consent
   timestamp but no screenshot content.
3. An authorized user submits a project, allowed target URL, task intent, and
   `use_vision=true`.  The API rejects it if global policy is disabled, consent
   is absent, target is not `web_ui`, the origin is disallowed, or guards would
   be invalid.
4. The route calls an application use case that creates an idempotent,
   correlation-linked session/outbox event.  It returns queued state only.

## Tests and validation

- Add focused tests beside `tests/test_agent_runtime.py` for defaults, nested
  override merge, consent invariant, and invalid vision guard combinations.
- Add `tests/test_vision_contracts.py`, persistence-schema assertions, and HTTP
  route tests for RBAC, cross-tenant invisibility, origin policy, idempotency,
  and disabled-policy rejection.
- Run `uv run pytest tests/test_agent_runtime.py tests/test_vision_contracts.py tests/test_persistence_schema.py`.

## Acceptance criteria

- No API client can enable raw transfer or use vision without the required
  authorization and stored consent.
- The new contract can describe action candidates without changing runner
  request/result JSON fixtures.

## Risks and non-goals

- Do not select a production retention period, region, or individual model.
- Do not expose policy secrets, raw evidence, or arbitrary browser commands.

## Completion record

**Status:** completed — 2026-08-31 18:07 ICT

Implemented the policy/configuration guard, separate v1 visual contracts,
tenant-scoped safe-metadata persistence and migration, application submission
use case, and API policy/session boundary. The implementation preserves the
existing runner request/result contracts and queues only an advisory outbox
event; no browser or model call is made by Phase 1.

Validation passed:

```text
uv run ruff check apps/control-plane packages/contracts/src tests/test_agent_runtime.py tests/test_vision_contracts.py tests/test_persistence_schema.py tests/test_dashboard_route_contracts.py
uv run pytest tests/test_agent_runtime.py tests/test_vision_contracts.py tests/test_persistence_schema.py tests/test_dashboard_route_contracts.py
# 25 passed; one existing Starlette TestClient deprecation warning
```

Deviation: the plan requested a consent timestamp. The consent is represented
by the append-only tenant-admin audit event, which records the actor and event
time; raw screenshots and provider request/response bodies remain absent from
the stored configuration and session records.
