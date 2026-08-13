# Terminal run reporting agent

## Goal

Add one advisory agent that creates a tenant-scoped, immutable run report after every
deterministic execution result (`passed`, `failed`, `errored`, or `skipped`). The dashboard
must show a concise explanation of what ran and what happened. For failures, it must identify
the failed test location and assertion/runner reason when that information is available in
permitted evidence. The report must never alter the deterministic verdict, dispatch a retry, or
change a generated test.

## Acceptance criteria

- Every terminal `TestExecutionResult` produces exactly one durable `run-report` outbox event and
  at most one immutable report record per run/version.
- A report records the deterministic status verbatim, a plain-language outcome, executed scope,
  verified observations, skipped/unverified scope, and evidence references. A failed/errored
  report additionally includes the safe failure location/reason when available; otherwise it says
  that the precise location was unavailable.
- The agent receives only the existing redacted evidence bundle plus bounded, redacted text
  extracts from allowlisted textual artifacts. It receives no secrets, raw binary artifacts, or
  unbounded logs.
- Provider failure, invalid report output, or guard exhaustion records an auditable unavailable
  report status/activity without changing the run result or retrying the run.
- Run detail exposes the report and its provenance; viewers can read it but cannot approve,
  reject, or apply it.
- Existing failure triage remains unchanged and still creates reviewable proposals only for failed
  and errored results.

## Request and decisions

User request: add one agent that reports after a run completes, including how a failed run failed
and where it failed.

Confirmed decisions:

- Reuse the existing configured provider/runtime (`agent.runtime.v1`), fallback, step guard,
  evidence flags, redaction policy, tenant scoping, and correlation IDs. No provider, model,
  cloud, or authentication decision is made by this plan.
- Treat the report as informational, not as an `AgentProposal`: it has no approval flow and no
  authority over a verdict.
- Run it for result-bearing terminal statuses only. A cancelled run without a
  `TestExecutionResult` remains out of scope for v1.
- Keep current artifact retention unchanged. Store only report JSON plus hashes/provenance; do not
  duplicate raw logs or binaries.

Assumptions:

- `playwright-output` and worker JSON result artifacts are eligible for bounded redacted-text
  extraction when `include_redacted_text` is enabled; screenshots, video, and trace stay as
  references unless a future approved evidence policy enables them.
- The current OpenRouter provider/model and configured token/cost guards are acceptable for one
  extra agent invocation per result-bearing terminal run. Runtime enforcement must make skipped
  or unavailable reporting visible rather than silently exceed a guard.

Unresolved questions: none blocking planning. The execution phase must surface the additional
per-run model cost and add an operational metric before enabling in a production environment.

## Scout findings

- `apps/control-plane/application/runs.py`: `RecordDeterministicResult` persists an immutable
  `TestExecutionResult`; `RequestFailureTriage` emits triage only for `failed`/`errored`.
- `apps/control-plane/application/triage_events.py` and `agents/triage/executor.py`: existing
  outbox consumer resolves the tenant runtime, applies guard/fallback, creates activity events,
  and cannot modify a verdict. It is the implementation pattern for this feature.
- `apps/control-plane/agents/shared/evidence.py`: current bundle redacts metadata and carries
  artifact references but does not extract textual artifact content, so it cannot reliably name a
  Playwright assertion location today.
- `packages/contracts/src/auto_at/contracts/agent.py`: typed evidence and proposal contracts
  exist, but there is no report contract/kind.
- `apps/control-plane/infrastructure/persistence/models.py` and `migrations/versions/`: reports
  require a dedicated tenant/run-scoped persistence model and Alembic migration; proposals are
  deliberately reviewable and are unsuitable for read-only reports.
- `apps/control-plane/infrastructure/workflows/temporal_worker.py`: the local publisher already
  injects triage and generation handlers, providing the durable report-consumer insertion point.
- `apps/control-plane/api/v1/routes/runs.py` and `apps/dashboard/app/runs/[id]/page.tsx`: run
  detail currently shows only deterministic summary, timeline, and artifacts; no report API/UI
  exists.

## Constraints

- Preserve the target-neutral v1 `TestExecutionRequest`/`TestExecutionResult` contract; reports
  are control-plane records and must not modify either envelope.
- Follow ADR-002: agent code has no browser, shell, repository, dispatch, or approval authority;
  source remains untrusted and verdict authority remains the runner.
- Follow ADR-003: use only redacted evidence, existing configurable provider/fallback/guards, and
  persist provider/model/prompt/redaction/input-hash provenance.
- Tenant isolation and RBAC must match run/evidence visibility. Secrets remain environment-only.
- Use deterministic IDs/idempotency keys, audit events, correlation-aware activity entries, and
  bounded text extraction for durable/retry-safe operation.

## Phases

| Phase | Objective | Status | Dependencies | Validation |
| --- | --- | --- | --- | --- |
| [01](phase-01-report-contract-and-evidence.md) | Define report contract, bounded evidence extraction, persistence, and event | completed — 2026-08-13T22:56:31+07:00 | None | 13 focused Python tests passed; Alembic upgraded to `c5d6e7f8a9b0`; Ruff passed |
| [02](phase-02-report-agent-and-workflow.md) | Run the advisory reporter durably after every result-bearing terminal run | completed — 2026-08-13T23:13:48+07:00 | Phase 01 | 21 focused Python tests passed; Ruff and diff check passed |
| [03](phase-03-report-api-and-dashboard.md) | Expose an understandable report on run detail and test end-to-end behavior | completed — 2026-08-13T23:27:59+07:00 | Phases 01–02 | 14 focused Python tests, dashboard typecheck/lint/tests, 3 Compose workflow tests, and diff check passed |

## Progress record

### Phase 01 completed — 2026-08-13T22:56:31+07:00

- Implemented strict `RunReport` contracts and report states, plus the additive report-requested
  event. The deterministic execution envelopes remain unchanged.
- Added bounded, verified text extraction for `playwright-output` and `worker-result` text/JSON
  artifacts. It redacts before hashing or prompt input and excludes binaries and unknown types.
- Added immutable, tenant/run/version-scoped `run_reports` persistence and migration
  `c5d6e7f8a9b0_add_run_reports.py`; duplicate adds return the existing record.
- Changed paths: `packages/contracts/src/auto_at/contracts/{agent,events}.py`,
  `apps/control-plane/{agents/shared/evidence.py,domain/entities.py,domain/ports.py,infrastructure/runners.py,infrastructure/persistence/{models,repositories}.py}`,
  `migrations/versions/c5d6e7f8a9b0_add_run_reports.py`, and focused report tests.
- Validation passed: `UV_CACHE_DIR=/tmp/auto-at-uv-cache uv run alembic upgrade head` and
  `UV_CACHE_DIR=/tmp/auto-at-uv-cache uv run pytest tests/test_agent_boundaries.py tests/test_persistence_schema.py tests/test_run_report_contract.py tests/test_run_report_repository.py tests/test_verified_artifacts.py` (13 passed); scoped Ruff passed.
- No deviations. Phase 02 is unblocked. Existing historical runs intentionally have no report.

### Phase 02 completed — 2026-08-13T23:13:48+07:00

- Added the durable `agent.run_report.requested.v1` outbox path after verified deterministic
  results, with one `run-report:<run-id>:v1` key for all passed, failed, errored, and skipped
  results. Cancellation without a result remains excluded.
- Implemented the bounded reporting agent, guarded provider/fallback invocation, strict output
  validation, immutable completed/unavailable persistence, correlation-aware activity, and local
  Temporal-worker wiring. Existing failure triage remains failure-only and unchanged.
- Changed paths: `apps/control-plane/agents/reporting/`,
  `apps/control-plane/application/{reporting.py,reporting_events.py,runs.py}`,
  `apps/control-plane/infrastructure/workflows/{temporal.py,temporal_worker.py}`, plus reporting
  executor/event/outbox/use-case tests and additive activity/configuration support.
- Validation passed: scoped Ruff; `UV_CACHE_DIR=/tmp/auto-at-uv-cache uv run pytest
  tests/test_run_use_cases.py tests/test_outbox_publishing.py tests/test_reporting_executor.py
  tests/test_reporting_event_processor.py` (21 passed); `git diff --check` passed. One existing
  Pytest collection warning about the `TestRun` dataclass remains.
- No deviations. Phase 03 is unblocked; operational metric export remains a production rollout
  follow-up, while structured reporting logs include status, correlation ID, and latency.

### Phase 03 completed — 2026-08-13T23:27:59+07:00

- Added the tenant/RBAC-scoped, read-only `GET /api/v1/runs/{run_id}/report` endpoint. It first
  authorizes normal run visibility, returns 404 for missing/cross-tenant reports, and exposes only
  report payload, safe unavailable reason, and whitelisted provenance—never raw prompts, provider
  responses, credentials, or binary bytes.
- Added a dashboard report section for completed, unavailable, pending, and historical-absence
  states. It makes the advisory/no-verdict-authority boundary explicit and turns matching report
  references into existing authorized artifact-download links.
- Changed paths: `apps/control-plane/{application/reporting.py,api/v1/routes/runs.py}`,
  `apps/dashboard/app/{run-api.ts,run-api.test.ts,runs/[id]/page.tsx}`, and
  `tests/{test_reporting_routes.py,test_dashboard_route_contracts.py}`.
- Validation passed: `UV_CACHE_DIR=/tmp/auto-at-uv-cache uv run pytest tests/test_run_routes.py
  tests/test_dashboard_route_contracts.py tests/test_reporting_routes.py` (14 passed); scoped Ruff;
  `corepack pnpm --dir apps/dashboard typecheck`, `lint`, and `test` (13 passed);
  `UV_CACHE_DIR=/tmp/auto-at-uv-cache uv run pytest tests/test_playwright_worker_compose.py`
  (3 passed); and `git diff --check`.
- No deviations. Existing FastAPI TestClient and Node module-type warnings remain pre-existing,
  non-failing test-environment warnings. The plan is complete; production metric export remains the
  Phase 02 rollout follow-up.

## Risks and rollout

- Extra model invocations increase per-run cost and latency after the verdict is known. Start with
  existing local guard limits and emit metrics for request, completion, unavailable, token/evidence
  budget rejection, and latency before production enablement.
- Logs may contain credentials or PII. Extraction must be an allowlist by artifact kind/content
  type, redact before hashing/prompting/persisting, cap bytes before and after redaction, and store
  only safe excerpts/references.
- A report can be incomplete due to absent artifacts, blocked external origins, or provider outage.
  It must say so explicitly and never upgrade/downgrade the runner result.
- Existing successful runs have no report. Do not backfill automatically; expose “Report unavailable
  for this historical run” and consider an operator-triggered backfill only in a separately approved
  plan.

## Out of scope

- Changing test source, re-running tests, auto-healing, proposal approval, notifications, external
  production deployment, changing data retention, and visual/binary evidence analysis.

## Overall completion

Status: completed — 2026-08-13T23:27:59+07:00. All three planned phases are complete and validated.
No contract version change, production deployment, or unapproved agent authority was introduced.
