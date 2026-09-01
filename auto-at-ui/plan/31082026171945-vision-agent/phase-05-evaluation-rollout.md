# Phase 5 — Evaluation, rollout, and operational readiness

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
