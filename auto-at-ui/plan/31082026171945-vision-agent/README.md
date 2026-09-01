# Governed Hugging Face Vision Agent

## Goal

Add an opt-in, vision-assisted Web UI exploration capability to `/agent`.  A
tenant administrator can enable the capability and explicitly consent to raw
screenshots being sent to the configured Hugging Face model.  An authorized
user can then choose whether a generation request uses vision.  The agent may
interpret screenshots and propose one bounded browser action at a time; it
never decides a test verdict or silently changes/executes a test revision.

## Acceptance criteria

- `/agent` exposes the capability state, raw-image transfer warning, and an
  opt-in control; a disabled policy cannot be bypassed by the client.
- Only a tenant administrator may enable/disable vision or change the
  non-secret Hugging Face vision-model setting; ordinary users may only opt
  in to an already-enabled policy for their own request.
- A visual exploration is isolated, tenant/project/origin scoped, bounded by
  step, time, byte, and cost/rate guards, and emits correlation-linked audit
  and activity events.
- The worker sends a raw screenshot only to the Hugging Face provider through
  the server-side model adapter.  It never places image bytes, signed artifact
  URLs, OCR output, or raw screenshot content in database records, logs,
  activity summaries, proposal payloads, or browser responses.
- Model output is schema-validated to a small action vocabulary and is treated
  as a candidate.  Every resulting test source change follows the existing
  draft/review/immutable-version/deterministic-rerun flow.
- `TestExecutionRequest` and `TestExecutionResult` remain unchanged; visual
  exploration has its own versioned contract and is not an execution verdict.

## Request and confirmed decisions

| Item | Decision |
| --- | --- |
| Entry point | `http://localhost:3000/agent` |
| User control | Vision use can be turned on/off from that workspace, subject to tenant policy. |
| Initial provider | Hugging Face through the existing OpenAI-compatible gateway. |
| Screenshot classification | Raw screenshots may be transferred to Hugging Face after explicit tenant-admin consent. |
| Authority | Advisory exploration/proposal only; Playwright remains the deterministic executor and humans approve generated changes. |

## Assumptions and unresolved model decision

- The raw-image consent applies to screenshots for projects in the tenant; the
  UI must state this plainly at each opt-in.  It does not permit raw logs,
  cookies, request bodies, traces, DOM dumps, or screenshots to be returned
  to the dashboard.
- The configured model must support OpenAI-compatible multimodal chat at the
  Hugging Face endpoint.  The implementation will benchmark and pin one
  approved Hugging Face vision model before it becomes a default.  No model is
  selected by this plan because model selection is a protected repository
  decision and the user has approved the provider, not a specific model.
- Vision exploration is available only for `web_ui`.  API and game adapters,
  production credentials, payments, destructive actions, uploads/downloads,
  and CAPTCHA/MFA bypass are out of scope.

## Source scout findings

- `apps/dashboard/app/agent/page.tsx` currently renders only
  `GenerationDashboard`; `apps/dashboard/app/generation-dashboard.tsx` already
  owns project selection, generation submission, allowed-origin policy, review,
  and the immutable draft decision UI.
- `apps/control-plane/agents/shared/runtime.py` exposes the tenant-scoped
  `agent.runtime.v1` configuration and has an inactive screenshot-evidence
  flag.  `config.py` defaults provider/model to Hugging Face and contains
  evidence, token, step, byte, concurrency, generation-cost, and request-rate
  guards.
- `apps/control-plane/agents/shared/openrouter.py` provides the server-only
  OpenAI-compatible Hugging Face adapter; the generic `LanguageModel` port is
  in `agents/shared/models.py`.
- `apps/control-plane/agents/shared/evidence.py` only creates redacted,
  reference-only evidence.  It intentionally does not read image bytes;
  `tests/test_agent_boundaries.py` verifies that boundary.
- `packages/contracts/src/auto_at/contracts/agent.py` defines contracts for
  bounded evidence and advisory proposals.  `packages/contracts/src/auto_at/contracts/execution.py`
  is the runner contract that must remain unchanged.
- `apps/control-plane/application/reporting_events.py` demonstrates the
  at-least-once event processor pattern, tenant configuration resolution,
  verified-artifact reading, safe unavailable fallback, persistence, and
  correlated activity events.
- `apps/control-plane/api/v1/routes/proposals.py` already provides the
  human-only approval boundary.  `ConfigurationModel` and
  `SqlAlchemyConfigurationRepository` persist non-secret tenant settings.
- `workers/playwright/` is the Web UI adapter and current artifacts include
  screenshot/trace/video.  `docs/architecture-implementation.md` explicitly
  describes screenshot visual matching as a fallback candidate generator, not
  deterministic verification.

## Constraints

- Preserve the one-way control-plane dependency rules in `AGENTS.md`; routes
  must not call models, storage, or the worker directly.
- Keep provider/model credentials only in settings or a future secret manager;
  tenant configuration must contain no API key.
- Enforce tenant isolation and project origin allowlists before browser launch,
  artifact read, model call, persistence, and dashboard response.
- Treat screenshot/UI text as untrusted prompt input.  Use a prompt-injection
  boundary and model output validation.  Do not give the model shell, database,
  source control, browser profile, or unrestricted network access.
- Raw image transfer requires consent audit records, visible privacy disclosure,
  retention inherited from the run/artifact policy, and no raw image content in
  application observability.

## Phases

| # | Objective | Status | Depends on | Validation |
| --- | --- | --- | --- | --- |
| 1 | Define policy, contracts, and evaluation gate | completed (2026-08-31 18:07 ICT) | — | contract/runtime unit tests |
| 2 | Build bounded visual evidence and Hugging Face vision adapter | completed (2026-08-31 18:19 ICT) | 1 | evidence/model adapter tests |
| 3 | Add isolated Playwright visual exploration and proposal workflow | completed (2026-08-31 20:55 ICT) | 1–2 | worker, application, route tests |
| 4 | Add `/agent` controls and reviewable vision workflow | completed (2026-08-31 21:19 ICT) | 1–3 | dashboard tests and route contracts |
| 5 | Evaluate, roll out, and operate safely | in progress (2026-09-01 ICT) — remote image delivery is verified; Cohere rejects image URLs, while GLM/Baseten accepts them but has no schema-valid action before a 429 rate limit | 1–4 | benchmark, end-to-end, baseline checks |

## Phase 5 current blocker (2026-09-01 ICT)

`zai-org/GLM-5.3-Flash:baseten` received a Google Drive-delivered synthetic
PNG via `image_url` successfully, proving remote-image transport compatibility.
The returned content did not validate as the versioned action contract in
either the original or JSON-mode canary; a later structure-only diagnostic
received HTTP 429. The executor now requests JSON mode and Baseten uses the
documented OpenAI-compatible transport; focused Ruff and 19 related unit tests
passed. The model is not selected or pinned, tenant policy remains unchanged,
and the rollout gate is blocked pending a bounded retry after the rate limit or
a new user-approved candidate. A separate Qwen2.5-VL remote-image probe
returned HTTP 400, not 429, confirming the Baseten condition is route-specific
but leaving that Qwen automatic-provider route unsuitable as a candidate.
The adapter also supports the documented OpenAI-compatible `:deepinfra` VLM
route, but its bounded live probe timed out without a diagnostic; it is not a
selected rollout candidate.

Update: `Qwen/Qwen3.8-27B:deepinfra` subsequently completed an end-to-end
Google Drive URL-image canary and returned a schema-valid `stop` action in
9.851 seconds. This proves the local vision path but does not complete the
fixture benchmark or select/pin the model for rollout.

The Phase 5 baseline Ruff check passes. Full pytest remains blocked by existing
temporary-directory permissions plus unrelated persistence/legacy triage test
failures; focused Vision tests pass. Model selection and benchmark thresholds
remain required before the phase can complete or a tenant can be enabled.

## Phase 5 approved local evaluation (2026-09-01 ICT)

The user approved `Qwen/Qwen3.8-27B:deepinfra` at revision
`1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0`. Two bounded synthetic
URL-image canaries met the applicable gates: 2/2 schema-valid actions, 1/1
unsafe-action refusal, 1/1 prompt-injection resistance, 0/2 unavailable, and
9.851 seconds maximum latency. The configuration remains disabled by default
and local-only. Phase 5 remains in progress because full pytest has unrelated
local failures and the fixture-based locator/rerun benchmark is still absent.

## Local demo rollout (2026-09-01 ICT)

Vision is enabled for `demo-tenant` only, using
`Qwen/Qwen3.8-27B:deepinfra` with explicit raw-screenshot consent and bounded
local guards. The local kill switch was verified by disabling then restoring
the policy. No production tenant, deterministic verdict, or browser action was
changed.

## Risks and rollout

- Raw screenshots can contain PII, secrets, customer data, or visual prompt
  injection.  Consent is explicit; initial rollout is disabled by default,
  local/dev only, with a project allowlist, artifacts retained under the
  existing policy, no cross-tenant reuse, and an immediate tenant-admin kill
  switch.
- Coordinate actions are fragile across viewport/zoom/layout changes.  The
  worker pins viewport/browser version, records screenshot checksum and action
  coordinates, and converts accepted discoveries into semantic Playwright
  locators/assertions before deterministic execution.
- Provider availability, latency, rate limits, and model price are external.
  Limit concurrency and per-session steps/bytes/tokens/cost; a timeout, model
  error, malformed output, or budget exhaustion records `unavailable` and
  leaves the normal generation/run path intact.
- No existing retention period is selected by this plan.  It inherits current
  artifact policy; changing retention, region, or production deployment needs
  explicit direction/ADR.

## Execution progress

### Phase 1 completed — 2026-08-31 18:07 ICT

- Added disabled-by-default, tenant-overridable `vision` runtime policy with
  Hugging Face-only validation, explicit raw-screenshot consent, and bounded
  step, byte, session, cost, and request-rate guards.
- Added separate `VisualExplorationRequest`/`VisualExplorationResult` v1
  contracts, an allowlisted action schema, safe evidence metadata, and visual
  provenance fields. `TestExecutionRequest` and `TestExecutionResult` were
  not changed.
- Added tenant-scoped visual-session/action-proposal persistence, migration,
  audit/activity/outbox creation, and API routes for policy and advisory
  session submission/listing/reading. The API stores hashes and safe metadata
  only; it does not call a model or worker in this phase.
- Changed paths: `apps/control-plane/config.py`,
  `apps/control-plane/agents/shared/runtime.py`,
  `apps/control-plane/application/vision.py`,
  `apps/control-plane/api/v1/routes/vision.py`,
  `apps/control-plane/api/v1/router.py`,
  `apps/control-plane/domain/{activity.py,ports.py}`,
  `apps/control-plane/infrastructure/persistence/{models.py,repositories.py}`,
  `packages/contracts/src/auto_at/contracts/{__init__.py,agent.py,vision.py}`,
  `migrations/versions/a4b5c6d7e8f9_add_visual_exploration.py`, and focused
  tests.
- Validation passed: `uv run ruff check apps/control-plane packages/contracts/src
  tests/test_agent_runtime.py tests/test_vision_contracts.py
  tests/test_persistence_schema.py tests/test_dashboard_route_contracts.py` and
  `uv run pytest tests/test_agent_runtime.py tests/test_vision_contracts.py
  tests/test_persistence_schema.py tests/test_dashboard_route_contracts.py`
  (25 passed; one existing Starlette deprecation warning).

### Phase 2 completed — 2026-08-31 18:19 ICT

- The user approved `Qwen/Qwen2.5-VL-7B-Instruct` as the pinned Hugging Face
  multimodal model for the development evaluation environment.
- Added a tenant/run/session-scoped screenshot reader that verifies image type,
  byte count, and stored artifact integrity before returning raw bytes only in
  memory. The existing shared redacted-evidence boundary remains unchanged.
- Added hostile-content prompt framing, strict v1 action-schema parsing, a
  one-shot no-fallback vision executor, and mocked Hugging Face multimodal
  request coverage. Provider errors, timeout, invalid output, or policy guards
  return advisory `unavailable` outcomes only.
- Pinned the disabled-by-default development vision policy to
  `Qwen/Qwen2.5-VL-7B-Instruct`.
- Changed paths: `apps/control-plane/{config.py,agents/shared/openrouter.py,agents/shared/runtime.py,agents/vision/*}` and
  `tests/{test_agent_runtime.py,test_vision_evidence.py,test_vision_executor.py}`.
- Validation passed: `uv run ruff check apps/control-plane/agents/vision
  apps/control-plane/agents/shared/openrouter.py apps/control-plane/config.py
  tests/test_vision_evidence.py tests/test_vision_executor.py
  tests/test_agent_runtime.py` and `uv run pytest tests/test_agent_boundaries.py
  tests/test_vision_evidence.py tests/test_vision_executor.py
  tests/test_agent_runtime.py` (25 passed).

### Phase 3 completed — 2026-08-31 20:55 ICT

- Scope: implement the disposable Playwright visual exploration boundary and
  its correlation-safe advisory workflow without changing execution verdicts.
- Decision recorded: use a shared ephemeral artifact mount. The worker will
  write session-addressed screenshots to the configured shared artifact root;
  the control plane will construct the path from the session ID and verify its
  checksum and size before the server-side Hugging Face adapter reads the
  image. Files must be removed when the session ends, times out, or fails. The
  public artifact model remains unused because it stores run-scoped URIs.
- Decision recorded: retain the original task intent internally for retry and
  draft creation for 60 days. It must be encrypted at rest with a dedicated
  configuration-secret key; application logs, activity events, browser
  responses, and audit payloads retain only its hash and correlation metadata.
- Implemented an authenticated internal worker protocol with a fresh pinned
  Playwright context, fixed viewport, origin allowlist, downloads disabled,
  shared ephemeral screenshot mount, bounded action loop, checksum-only action
  history, and terminal cleanup.
- Added an at-least-once-safe visual event processor: terminal duplicates skip
  worker/model calls; enabled policy is rechecked after queueing; screenshots
  are read only from the session path and validated before the server-side
  model adapter receives bytes; malformed/unavailable model outcomes remain
  advisory. A completed session queues a normal reviewable generated draft;
  the existing human draft-decision flow remains the only path to a versioned
  deterministic rerun.
- Added encrypted original-intent retention for 60 days, rejecting credentials
  before storage. Logs, activity, audit, and browser responses retain only
  safe metadata.
- Validation passed: focused Ruff, `uv run pytest
  tests/test_vision_event_processor.py tests/test_vision_intent.py
  tests/test_vision_executor.py tests/test_vision_contracts.py` (8 passed),
  and `npm.cmd run typecheck` in `workers/playwright`.
- Deferred: the optional Compose-backed scenario was not run because the local
  Compose services were not started during this phase; no deterministic run
  contract was changed.

### Next phase

Phase 5 in progress (started 2026-08-31 21:19 ICT). The offline implementation
now includes a versioned synthetic fixture manifest, aggregate-only evaluation
metrics, regression coverage, disabled-by-default environment examples, and an
operator runbook. Focused Ruff and 15 vision/runtime tests passed at 2026-08-31
21:29 ICT. The user approved `Qwen/Qwen3-VL-4B-Instruct` at immutable revision
`ebb281ec70b05090aa6165b016eac8ec08e71b17`; ADR-007 and disabled defaults now
record that local-evaluation choice, with focused Ruff and 13 configuration/
benchmark tests passing at 21:41 ICT. The rollout gate remains blocked until an
configured Hugging Face gateway is confirmed compatible with the pinned model
and request shape. One bounded synthetic smoke call returned `unavailable`; no
tenant policy enablement or deterministic execution change occurred. A
text-only compatibility check then returned HTTP 400 in the safe
`model/provider` category, so a specific provider selection or a new model
approval is required before the endpoint-backed gate can proceed.

### Phase 4 completed — 2026-08-31 21:19 ICT

- Added the `/agent` Vision settings panel, explicit raw-screenshot transfer
  acknowledgement, per-request opt-in, confirmation dialog, safe session and
  action view, terminal polling, correlation activity, and generated-draft
  review link. The client calls only the existing authenticated control-plane
  boundary; policy and RBAC remain server-authoritative.
- Added the read-only, tenant/project-authorized visual-action endpoint needed
  to show only action kind, bounded coordinates/timing, confidence, and image
  checksum. It deliberately omits typed text, expected UI outcomes, raw
  prompts, provider responses, image bytes, and artifact URLs.
- Changed paths: `apps/dashboard/app/{generation-api.ts,generation-api.test.ts,
  generation-dashboard.tsx,generation-types.ts,vision-dashboard.tsx}`,
  `apps/control-plane/{api/v1/routes/vision.py,application/vision_events.py,
  infrastructure/persistence/repositories.py}`, and
  `tests/test_dashboard_route_contracts.py`.
- Validation passed: `npm.cmd run typecheck`; `npm.cmd test` (15 passed);
  `uv run ruff check apps/control-plane/api/v1/routes/vision.py
  apps/control-plane/application/vision_events.py
  apps/control-plane/infrastructure/persistence/repositories.py
  tests/test_dashboard_route_contracts.py`; and `uv run pytest
  tests/test_dashboard_route_contracts.py tests/test_vision_event_processor.py`
  (15 passed, one existing Starlette TestClient deprecation warning).
- No runner execution contract changed. Deferred from Phase 5: live provider
  benchmark, immutable model snapshot recording, and local canary require the
  approved evaluation credentials/endpoint described below.

## Out of scope

- Replacing Playwright, autonomous production browsing, autonomous test
  approval, changes to deterministic verdicts, raw screenshot display from
  agent prompts, and provider/model selection beyond the approved Hugging Face
  gateway.

## Phase files

- [Phase 1 — governance and contracts](phase-01-governance-contracts.md)
- [Phase 2 — evidence and model adapter](phase-02-evidence-model-adapter.md)
- [Phase 3 — exploration workflow](phase-03-exploration-workflow.md)
- [Phase 4 — agent workspace](phase-04-agent-workspace.md)
- [Phase 5 — evaluation and rollout](phase-05-evaluation-rollout.md)
