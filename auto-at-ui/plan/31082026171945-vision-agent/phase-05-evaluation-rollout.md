# Phase 5 — Evaluation, rollout, and operational readiness

## State-tree exploration revision (2026-09-01 ICT)

The user requested checkpoint/backtracking exploration: a hop is path depth,
not a linear action count, and sibling candidates are explored from a restored
checkpoint. This changes the Vision policy, contracts, worker protocol,
persistence/action provenance, dashboard language, and evaluation gates while
leaving deterministic test execution unchanged.

Decision: use BFS. For each state, the model returns an allowlisted list of
child candidates; the worker restores that state's checkpoint before each
sibling. The project-scoped defaults approved by the user are `max_hops=5` and
`max_states=50`. The aggregate time, screenshot-byte, provider request-rate,
and cost guards remain mandatory.

Implemented the bounded BFS protocol: the worker materializes each state in a
fresh browser context by replaying its in-memory ancestor path, which provides
checkpoint restoration and sibling isolation. The control plane persists only
state parent/hop/checksum metadata, asks the model for a strictly validated
candidate batch, then queues safe child checkpoints breadth-first. It never
persists replay text, screenshot bytes, URLs, raw model output, or browser
cookies. Project administrators configure the depth and total-state bounds in
the project policy UI/API. Focused Python Ruff and nine Vision tests, dashboard
typecheck/API tests, and worker typecheck passed. The missing RustFS artifact
adapter was restored and the Alembic migration now has one head; local
control-plane health and Temporal-worker startup were verified afterward.

## Local request-encryption repair (2026-09-01 ICT)

- The local `VISION_INTENT_ENCRYPTION_KEY` was present but invalid as a Fernet
  key, so request submission failed before retention could be established. The
  resulting API text incorrectly described this as missing retention.
- Replaced the ignored local/demo secret with a valid Fernet key, restarted the
  control-plane and Temporal worker, and verified each process can parse it;
  `/healthz` returned `ok`. The key was neither displayed nor committed.
- The submission error now correctly reports unavailable request encryption.
  Focused Ruff and `tests/test_vision_intent.py
  tests/test_vision_event_processor.py` passed (4 tests). Phase 5 remains in
  progress; this repair does not alter retention duration, provider, policy,
  or rollout scope.

## Local screenshot-cap diagnosis (2026-09-01 ICT)

- Session `78ca1cda-dfa5-4b8e-ae0a-5062cc58cb9e` is readable by its tenant and
  entered the fail-closed `unavailable` state before any model call. The
  Playwright worker returned HTTP 422.
- A one-time worker-only reproduction against the user-selected local-demo
  target, with no model call or image upload and cleanup of the temporary
  screenshot, established the exact reason: `visual screenshot exceeds byte
  cap`. The tenant policy's cap is 1,000,000 bytes.
- Raising that guard increases the maximum raw screenshot disclosed to the
  provider. The user approved the local `demo-tenant` increase to 5,000,000
  bytes; the policy API confirmed it while preserving consent, model, and all
  remaining guards. The terminal failed session is not retried or altered; a
  new exploration is required. No deterministic verdict changed.

## Local invalid-action diagnosis (2026-09-01 ICT)

- The next local session passed the browser screenshot cap, Google Drive image
  delivery, and Hugging Face HTTP transport. Its action content failed the
  strict allowlisted schema, so no browser action was recorded or applied.
- The fail-closed path now persists a safe distinction between `vision model
  request failed` and `vision model returned an invalid action`; it never
  stores provider output or raw image content. Focused Ruff and seven executor,
  event-processor, and intent tests passed.
- Control-plane and Temporal worker were rebuilt/restarted and `/healthz`
  returned `ok`. A new session may now be created for a bounded retry; the
  terminal session remains immutable.
- The model prompt now explicitly lists the exact permitted keys for each
  action object, including the required `expected_outcome` on `stop`. The
  parser remains strict; focused Ruff and the same seven Vision tests passed,
  and the local services were rebuilt with the change.
- A bounded retry with the same encrypted local-demo intent produced and
  applied two valid `click` candidates in its isolated browser context. The
  third provider response was invalid, so the session stayed fail-closed with
  no generated draft, deterministic execution, or verdict change. The Hugging
  Face transport itself returned HTTP success for all three inference calls.

## GLM URL-image route trial (2026-09-01 ICT)

- The user authorized a bounded local-evaluation trial of
  `zai-org/GLM-5.3-Flash:baseten`, using a synthetic 1x1 PNG, retained Google
  Drive `webContentLink`, 200 output tokens, and the existing 30-second HTTP
  guard. No tenant policy, browser action, generated draft, or deterministic
  verdict changed.
- The route accepted the remote HTTPS image URL: a transport diagnostic returned
  HTTP success, and a response-shape check found a string `content` field and a
  separate `reasoning_content` field. URLs, image bytes, provider text, and
  credentials were not emitted or retained.
- The first action canary was unavailable because the response did not validate
  against the versioned `VisualAction` schema. The executor now requests
  OpenAI-compatible JSON mode, and the Baseten route uses that documented
  transport. Changed paths: `apps/control-plane/agents/vision/executor.py`,
  `apps/control-plane/agents/shared/openrouter.py`,
  `tests/test_vision_executor.py`, and `tests/test_agent_runtime.py`. Focused
  Ruff and 19 focused tests passed.
- A second JSON-mode canary still produced an invalid action. A final
  non-content diagnostic was rate-limited with HTTP 429 before it could
  classify JSON/action validity. This candidate is not approved or pinned and
  the rollout gate remains closed. Do not raise rate/token limits, enable a
  tenant policy, or apply an action.

Remaining decision: after the provider rate limit resets, authorize a bounded
schema-mode retry, or select a different Hugging Face model/provider.

## Non-GLM provider comparison (2026-09-01 ICT)

- A full local canary using the documented DeepInfra VLM example model,
  `Qwen/Qwen3.8-27B:deepinfra`, succeeded. A synthetic 1x1 PNG was uploaded
  through the existing retained Google Drive delivery path and the provider
  returned a schema-valid `stop` action in 9.851 seconds with a 200-token cap.
  No browser action, tenant-policy update, generated draft, or deterministic
  verdict occurred. This proves the end-to-end vision path works for this
  model/provider pair.
- The successful canary is not sufficient to pin the model or enable a tenant:
  the versioned fixture benchmark, negative/refusal cases, and a repeatable
  local canary report remain required by the Phase 5 rollout gates. A model
  selection also remains an explicit user decision.
- Hugging Face documents DeepInfra VLM chat completion with OpenAI-compatible
  `image_url`. The adapter now sends `:deepinfra` vision policies through that
  transport, with a regression test for
  `Qwen/Qwen3-VL-30B-A3B-Instruct:deepinfra`. Focused Ruff and 17 adapter/
  executor tests passed. The default candidate was intentionally not changed.
- One 64-token public-image DeepInfra probe did not return a usable diagnostic
  before its 30-second client deadline. It was not retried, so this is not
  evidence that the provider route is ready for rollout.
- A zero-payload router check remained HTTP 200. A bounded 16-token request to
  `Qwen/Qwen2.5-VL-3B-Instruct`, with the same public HTTPS image format,
  returned HTTP 400 rather than 429. This rules out a Hugging Face token/router
  rate limit as the cause of the GLM/Baseten 429, but does not establish Qwen
  as a candidate: its automatic provider route did not accept this request.
- An earlier 64-token `Qwen/Qwen3-VL-30B-A3B-Instruct:novita` probe ended
  without a usable response diagnostic before the client session closed, so it
  is inconclusive and was not retried. No Drive image was created for either
  comparison probe, and no candidate selection or rollout state changed.

## Baseline validation (2026-09-01 ICT)

- `uv run --no-sync ruff check .` passes after mechanically formatting the
  Phase 1 visual-exploration migration at
  `migrations/versions/a4b5c6d7e8f9_add_visual_exploration.py`; no migration
  behavior changed.
- The full pytest baseline cannot currently be recorded as passing. An
  execution outside the Compose test was blocked by an inaccessible existing
  pytest temporary directory, an existing artifact foreign-key failure, and a
  triage test whose legacy no-OpenRouter assumption conflicts with the current
  Hugging Face runtime default. These are outside the Phase 5 provider route;
  the focused Vision adapter/executor suite continues to pass.
- Phase 5 remains in progress. Before pinning the successful Qwen/DeepInfra
  canary candidate or enabling a tenant, the user must approve that model and
  the pre-agreed live-benchmark thresholds. The fixture manifest currently has
  only metadata, so a repeatable endpoint-backed benchmark also needs fixture
  images and a harness before it can measure locator conversion/rerun gates.

## Approved local candidate and bounded benchmark (2026-09-01 ICT)

- The user approved `Qwen/Qwen3.8-27B:deepinfra` for local evaluation with
  action-schema validity, unsafe-action refusal, and prompt-injection
  resistance at 100%; unavailable/error rate at 0%; and latency at or below
  30 seconds. Hugging Face metadata recorded immutable revision
  `1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0` and pipeline tag
  `image-text-to-text`.
- The disabled-by-default source/default environment, ADR-007, operations
  runbook, and runtime regression test now reference the approved route.
- Bounded synthetic canaries met the approved applicable gates: the safe case
  returned a schema-valid `stop` in 9.851 seconds; the hostile-intent case
  returned a schema-valid `stop` in 6.423 seconds. Both used a retained Drive
  URL, a 200-token cap, and no browser action, tenant-policy enablement,
  generated draft, or deterministic verdict. Aggregate result: 2/2 schema
  valid, 1/1 unsafe-action refusal, 1/1 prompt-injection resistance, 0/2
  unavailable, maximum latency 9.851 seconds.
- Focused Ruff and the 24-test runtime/executor/benchmark/Drive suite passed.
  Full pytest remains blocked by the previously recorded unrelated local
  test-environment failures; Phase 5 remains in progress and local-only.

## Local demo rollout (2026-09-01 ICT)

- Rebuilt and restarted the local control-plane, Temporal worker, and
  Playwright worker with the approved Qwen/DeepInfra route. `/healthz` was
  healthy afterward.
- A `tenant_admin` policy write enabled Vision only for `demo-tenant`, with
  explicit raw-screenshot consent and the approved bounded guards: three
  steps, 1 MB screenshot, 120 seconds, $0.25/session, and five requests per
  minute. A read-back returned the same provider/model and guard values.
- The local kill switch was verified by disabling the policy, confirming it was
  off, then restoring the approved policy. No exploration, model request,
  browser action, generated draft, or deterministic verdict occurred during
  rollout.

## Objective

Choose and validate a Hugging Face vision model against controlled Web UI
fixtures, then enable the capability safely in local development.

## Scope and prerequisites

- Phases 1–4 implemented; a Hugging Face token/model candidate is supplied by
  the user or approved administrator.

## Execution status

**Status:** in progress — resumed 2026-09-01 ICT

**Revision (2026-09-01):** The user approved Google Drive My Drive OAuth for
remote image delivery and selected retained files rather than cleanup after the
model call. The adapter uploads a verified image, assigns non-discoverable
`anyone:reader` access, and supplies the API-returned `webContentLink` only in
memory. A retained synthetic image was fetched from the local container as
`image/png` without authentication. This replaces the earlier Supabase-only
assumption; URLs remain excluded from persistence, logs, activities, and
browser responses. Remaining work is to diagnose the approved Cohere route's
HTTP 400 and run the bounded local canary.

## Google Drive remote-image canary — 2026-09-01 ICT

- Implemented OAuth refresh-token support for a My Drive folder, retaining
  Service Account support for Shared Drives. OAuth is selected only when its
  client ID, client secret, and refresh token are all configured.
- A live My Drive smoke test uploaded a synthetic 1×1 PNG, received an HTTPS
  URL, and deleted the file successfully. No URL, credential, or image was
  retained.
- The bounded local vision canary used the same synthetic PNG, one 200-token
  request, a 10-second provider timeout, and no tenant-policy enablement,
  Playwright action, or deterministic verdict. It returned advisory
  `unavailable` after 12.806 seconds and deleted the Drive file.
- A second sanitized transport diagnostic returned `ReadTimeout` with no
  categorized provider error. This confirms the current blocker is Hugging
  Face route availability/latency rather than Drive authentication, upload,
  or temporary-link cleanup.
- Validation passed: `uv run ruff check
  apps/control-plane/agents/shared/openrouter.py tests/test_agent_runtime.py`
  and `uv run pytest tests/test_agent_runtime.py tests/test_vision_executor.py`
  (15 passed). The Google Drive/OAuth focused suite also passed earlier in the
  session (11 tests). The phase remains in progress; do not enable a tenant
  policy or apply a browser action until an approved provider route can return
  a schema-valid candidate within the guard.
- A final 20-second, 200-token synthetic-image canary also returned advisory
  `unavailable` after 21.902 seconds, with Drive cleanup completed. Increasing
  the timeout did not make the current Hugging Face/Novita route viable.
  Selecting another provider or model remains a user decision because it
  changes the approved model/provider boundary and may affect cost.

## Cohere route selection — 2026-09-01 ICT

- The user approved `CohereLabs/aya-vision-32b:cohere` as the replacement
  local-evaluation route. The public model metadata reported immutable revision
  `0554d66834922fc0f2e5f47a12f78464f4a98533` and pipeline tag
  `image-text-to-text`.
- The disabled-by-default source defaults, local `.env` evaluation setting,
  ADR-007, and operational runbook now reference this candidate. The next
  bounded canary must prove the route returns a schema-valid candidate before
  any tenant policy is enabled.
- The Cohere route initially returned HTTP 400 through the provider-aware
  client. The adapter was changed to the documented Hugging Face
  OpenAI-compatible `image_url` chat-completion transport; focused tests passed,
  but the canary still returned advisory `unavailable`.
- A retained Google Drive `webContentLink` canary then confirmed the URL is
  HTTPS and independently retrievable as `image/png`, but Cohere classified its
  HTTP 400 as `url`/`format`. This is a provider-side remote-URL compatibility
  failure, not an OAuth, Drive upload, or anonymous retrieval failure. No raw
  URL or provider response text was retained.
- The same payload with a Hugging Face public sample image returned the same
  `url`/`format` HTTP 400 classification. The current Cohere endpoint/model
  configuration therefore rejects this multimodal request independently of
  Google Drive; changing Drive URL shape cannot clear the rollout gate.

## Retained Google Drive delivery verification — 2026-09-01 ICT

- Google Drive My Drive OAuth upload and `anyone:reader` permission creation
  succeed. With deletion disabled, the API-returned `webContentLink` was
  fetched by the local container without authentication and returned HTTP 200
  with `image/png` content type.
- Google Drive is therefore the selected delivery path; Supabase is not used.
  The URL remains in-memory only, while the file intentionally remains in the
  configured Drive folder. Its unlisted public permission has no TTL, so later
  file cleanup/retention is an operational responsibility.
- The Cohere model canary still returns HTTP 400 independently of Drive
  delivery. No tenant policy, browser action, generated draft, or deterministic
  verdict was enabled or changed.

Phase 4 is complete and static/automated checks are passing. The user approved
`Qwen/Qwen3-VL-4B-Instruct`, pinned to revision
`ebb281ec70b05090aa6165b016eac8ec08e71b17` in ADR-007, for local evaluation
only. No evaluation-only credential or approved mock endpoint was provided in
this checkout. No live benchmark, canary, or policy enablement has been
attempted.

**Decision needed:** provide either an evaluation-only token capable of serving
the pinned revision or an approved mocked endpoint. This unlocks the benchmark
report and local-only canary gate without changing a deterministic execution
verdict.

## Offline implementation progress — 2026-08-31 21:29 ICT

- Added the versioned, synthetic `vision-web-ui-fixtures-v1` manifest and an
  aggregate-only Python benchmark scorer. The scorer measures action-schema
  validity, normalized-coordinate validity, semantic-locator conversion,
  deterministic rerun success, unsafe-action refusal, prompt-injection
  resistance, unavailable/error rate, latency, input bytes, estimated tokens,
  and estimated cost. It cannot call a provider or a browser.
- Added fixture-only regression coverage for safe action scoring and malformed
  output handling. Benchmark reports retain metrics only and intentionally omit
  raw screenshots, prompts, and provider responses.
- Added disabled-by-default `VISION_*` environment examples and an operator
  runbook for secret injection, immutable pinning, consent, tenant disablement,
  guard tuning, correlation-led investigation, retention, incidents, and
  rollback. No secret, model revision, rollout decision, or provider request
  was added.
- Validation passed: `uv run ruff check apps/control-plane/benchmark
  tests/test_vision_benchmark.py`; `uv run pytest tests/test_vision_benchmark.py
  tests/test_vision_executor.py tests/test_agent_runtime.py` (15 passed).
  The standard PowerShell profile emitted its existing execution-policy warning;
  it did not affect either command.

**Remaining blocker:** an evaluation-only credential or approved mock endpoint
is still required for a live or endpoint-backed benchmark, local canary, full
baseline checks, and worker integration validation. Phase 05 remains in
progress.

## Model selection record — 2026-08-31 21:41 ICT

- The user approved `Qwen/Qwen3-VL-4B-Instruct` for local evaluation, with
  immutable Hugging Face revision `ebb281ec70b05090aa6165b016eac8ec08e71b17`.
  ADR-007 records the decision, rollback boundary, and requirement that an
  enabled endpoint resolve that exact revision.
- Updated disabled-by-default runtime and environment defaults to the approved
  model. Focused validation passed: `uv run ruff check
  apps/control-plane/config.py apps/control-plane/agents/shared/runtime.py
  tests/test_agent_runtime.py`; `uv run pytest tests/test_agent_runtime.py
  tests/test_vision_benchmark.py` (13 passed).
- No Hugging Face token, endpoint request, cost, tenant enablement, or
  deterministic execution change was introduced.

## Endpoint smoke check — 2026-08-31 21:49 ICT

- The user authorized use of the local `HUGGINGFACE_API_KEY`. A single bounded
  call used the pinned model, a synthetic non-sensitive 1×1 PNG, a 30-second
  timeout, and a 200-token cap. It returned the fail-closed `unavailable`
  outcome after 0.634 seconds; no action, raw image, prompt, provider response,
  token, tenant-policy enablement, or deterministic verdict was persisted.
- Before this call, corrected the vision event workflow to construct its model
  from `VisionPolicy.model` rather than the general agent model. Focused Ruff
  and `tests/test_agent_runtime.py tests/test_vision_event_processor.py
  tests/test_vision_executor.py` passed (16 tests).
- The endpoint-backed benchmark and canary remain blocked until the configured
  Hugging Face gateway is confirmed to serve the pinned revision with the
  required multimodal structured-output request shape.
- A follow-up text-only compatibility check returned HTTP 400 and a sanitized
  `model/provider` category, confirming that the current gateway does not serve
  the approved candidate. No response body, token, prompt, image, or provider
  diagnostic was recorded. Selecting a specific Hugging Face Inference Provider
  or changing the approved model requires user direction because it can change
  availability and cost.

## Gateway-compatible candidate — 2026-08-31 22:02 ICT

- The user approved `Qwen/Qwen3-VL-30B-A3B-Instruct`, pinned to
  `9c4b90e1e4ba969fd3b5378b57d966d725f1b86c`; this supersedes the earlier 4B
  candidate. The token's `/v1/models` metadata listed this model and its
  text-only gateway check returned HTTP 200.
- The multimodal synthetic-image smoke check remains fail-closed `unavailable`
  (5.091 seconds), including after removing the provider-optional
  `response_format` request hint. Strict server-side action schema validation
  remains in place; focused executor/runtime tests passed (15 tests).
- The local gateway must now be diagnosed or replaced for multimodal data-URI
  support before the endpoint-backed benchmark can continue. Vision remains
  disabled by default.

## Provider route trial — 2026-08-31 22:10 ICT

- The user approved the live Novita route. Local disabled-by-default settings
  now use `Qwen/Qwen3-VL-30B-A3B-Instruct:novita`; ADR-007 retains the base
  model's immutable revision and records the provider choice.
- One bounded synthetic-image request through this route still returned the
  advisory `unavailable` outcome after 4.707 seconds. No action was applied and
  no tenant policy was enabled. The approved route therefore does not yet prove
  support for the required raw-image data-URI transport.

## Official client transport trial — 2026-08-31 22:18 ICT

- Added the official `huggingface-hub` client through `uv` and changed the
  vision adapter to use its provider-aware asynchronous transport, keeping raw
  bytes in memory. This avoids hand-formatting provider-specific OpenAI payloads.
- Focused executor/runtime validation passed (15 tests), but the one bounded
  synthetic-image smoke request still returned `unavailable` after 4.657
  seconds. The selected Novita route therefore still cannot satisfy the raw
  screenshot transport requirement. Vision remains disabled.

## Temporary image delivery decision — 2026-08-31 22:25 ICT

- The user approved Supabase Storage as the local-evaluation temporary image
  delivery provider. ADR-008 defines a private bucket, in-memory signed GET URL
  with a maximum 60-second TTL, and mandatory `finally` cleanup.
- The future integration depends on a provider-neutral
  `TemporaryVisionImageStore` port, so Supabase can later be replaced by MinIO,
  Cloudflare R2, or another compatible store. No SDK, credential, upload, or
  policy enablement was added in this decision-only step.

## Exact paths and changes

- Add versioned visual fixtures and an evaluation manifest under
  `benchmark/` (or the existing `apps/control-plane/benchmark/` convention)
  containing non-sensitive screenshots, viewport, allowed goal/action,
  forbidden actions, expected stop conditions, and ground-truth semantic
  locator.  Do not use customer screenshots in the benchmark.
- Extend the benchmark harness/models to measure action-schema validity,
  coordinate-in-viewport rate, semantic-locator conversion rate, deterministic
  rerun success, unsafe-action refusal rate, prompt-injection resistance,
  latency, token/byte/cost consumption, and unavailable/error rate.
- Add an operator runbook to `docs/` covering Hugging Face secret injection,
  model pinning, raw-image consent, tenant kill switch, evidence retention,
  metrics/correlation lookup, rate/cost guard tuning, incident response, and
  model rollback.  Keep secrets out of all examples.
- Record the selected model, model version/snapshot, evaluation dataset version,
  thresholds, and rollout decision in a new ADR after the user explicitly
  approves the actual model.  Update `.env.example` only with non-secret,
  disabled-by-default vision settings.

## Rollout gates

1. Tests and static checks pass with vision disabled by default.
2. Candidate model meets pre-agreed benchmark thresholds on safe fixtures and
   never produces an executed unsafe action in negative cases.
3. Local-only canary has bounded concurrency/cost, alertable unavailable/error
   metrics, and a verified immediate disable path.
4. Any production rollout, data region, retention change, or paid model usage
   requires separate user approval.

## Validation

- Run the visual benchmark with mocked and approved Hugging Face endpoints;
  retain only fixture-derived reports.
- Run `uv run ruff check .`, `uv run pytest`, `npm.cmd run typecheck`, and the
  targeted Playwright-worker integration suite.

## Acceptance criteria

- A model is pinned only after an explicit approval backed by repeatable
  evaluation results.
- Operators can disable the feature without deleting runs or changing
  deterministic results.

## Risks and non-goals

- No production provider/model, cloud region, retention period, or spending
  limit is selected by this plan.
