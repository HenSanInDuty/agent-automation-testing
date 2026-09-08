# Phase 4 - fixtures, validation, and rollout

## Objective

Prove that trajectory replay remains truthful, safe, and useful across representative branches and safely introduce it without breaking existing evidence access.

## Scope and prerequisites

Requires Phases 1-3. This phase supplies deterministic fixtures and validation; it does not enable a new tenant, model, provider, cloud service, or change artifact retention.

## Source paths to add/change

- `tests/test_vision_event_processor.py`, `tests/test_vision_replay.py`, `tests/test_vision_routes.py`, and focused new `tests/test_vision_trajectory.py`
- `workers/playwright/src/vision.ts` test/spec files
- `apps/dashboard/app/components/vision-replay-model.test.ts` and new trajectory component tests
- `apps/dashboard/app/generation-api.test.ts`
- A small checked-in, synthetic dashboard fixture under `apps/dashboard/app/components/fixtures/` (or existing test-fixture convention)
- `docs/visual-replay-research-2026-09.md` and/or `docs/changelog.md` for final terminology/behavior documentation
- `README.md` only if the user-facing Vision workflow is documented there

## Detailed behavior and rollout steps

1. Build a synthetic trajectory fixture with a root state, two sibling candidates, one observed child with coordinate action, one no-change scroll branch, a stop edge, a failed/null-child edge, and a missing/deleted frame. Use fictional hashes/IDs and no raw screenshots, URLs, prompts, or typed values.
2. Exercise a fixture-driven dashboard state so reviewers can judge default path, branch switch, marker labeling, failure-first status, and legacy fallback without a live model/provider call.
3. Add an event-processor integration-style test with a fake worker/model to verify the complete state -> proposal/edge -> child or terminal sequence and idempotent retry behavior.
4. Run the smallest Compose-backed scenario available: authorized session submission, worker capture, RustFS frame persistence, safe trajectory GET/SSE, and dashboard retrieval. If local services are unavailable, document the exact blocker and leave the feature disabled; do not substitute production resources.
5. Verify privacy/RBAC regression cases: project reader succeeds, cross-tenant/service callers receive not-found, raw URLs/text/provider payload do not serialize, deleted frames stay unavailable while graph metadata truthfully reports missing evidence, and no-store headers remain present.
6. Update copy/runbook/research conclusion to explain that frames are BFS exploration evidence and the visual path is a selected trajectory, not continuous browser recording. Add an operator check for SSE-to-polling fallback and evidence deletion.
7. Release in additive order: migration; processor/worker writes; read endpoint; dashboard feature; then enable display for existing authorized tenants. Keep the legacy gallery fallback until telemetry/fixtures confirm no old active sessions require it. Roll back UI/API readers independently of the immutable data migration if needed.

## Tests and validation

- `uv run ruff check .` and focused `uv run pytest` for all Vision contracts, persistence, processor, replay, progress, and route tests; run full `uv run pytest` if the known unrelated baseline failures have been resolved.
- `npm.cmd test` and `npm.cmd run typecheck` in both `apps/dashboard` and `workers/playwright` where scripts exist.
- `uv run alembic heads` plus migration upgrade validation.
- Compose/API-to-worker scenario and a manual keyboard/accessibility smoke test at desktop and narrow viewport.

## Acceptance criteria

The fixture suite demonstrates every research-mandated case: siblings, action without coordinates, branch navigation, missing image, terminal limit, and failed candidate call. The UI remains readable in live and completed states, and safeguards/verdict boundaries remain proven by regression tests.

## Risks and non-goals

Compose and provider availability are external to this feature; a failed live provider call must appear as a safe failed edge, not block deterministic fixture validation. Do not promote replay evidence to a test result, automate a draft decision, or revise global retention/provider policy.

## Execution record

- Status: completed 2026-09-07 22:07 +07:00.
- Added: synthetic redacted dashboard fixture and model coverage for sibling branches, observed coordinate action, no-coordinate scroll, terminal stop, safe failed edge, and missing frame; the research document now carries the exploration-evidence terminology, rollback order, polling fallback, and deletion operator checks.
- Validation passed: full Ruff; 42 focused Python tests with a workspace-local pytest temporary directory; 22 dashboard tests and dashboard typecheck; 2 worker Vision tests and worker typecheck; Alembic head and an actual local Compose migration upgrade; `git diff --check`.
- Deferred: no live authenticated submission/worker-provider scenario was issued because it needs a target URL and task intent selected by the user. The existing healthy local Compose services and deterministic fixtures cover the schema and behavior boundaries without initiating that external interaction.
