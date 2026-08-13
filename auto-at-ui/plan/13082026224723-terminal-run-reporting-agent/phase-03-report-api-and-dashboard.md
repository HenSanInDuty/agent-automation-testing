# Phase 03 — Report API and run-detail presentation

## Objective

Expose the immutable advisory report with deterministic context and evidence links on the existing
run-detail experience, making pass and failure outcomes understandable without granting UI authority.

## Prerequisites

- Phases 01–02 complete, including report persistence and durable processor.

## Source paths

- Add tenant/RBAC-scoped report response route in
  `apps/control-plane/api/v1/routes/runs.py` (or a dedicated read-only `reports.py` router if it
  keeps route ownership clearer); register it in `apps/control-plane/api/v1/router.py` if needed.
- Add application read use case in `apps/control-plane/application/reporting.py` and repository
  dependency usage at the route boundary.
- Extend `apps/dashboard/app/run-api.ts` types/functions and `run-api.test.ts`.
- Update `apps/dashboard/app/runs/[id]/page.tsx` with a report section: deterministic status,
  headline, what ran, observations, failure location/reason, unverified scope, limitations,
  provenance, and evidence links. Render unavailable/historical absence explicitly.
- Add dashboard presentation model/component tests if formatting logic becomes non-trivial; update
  `tests/test_dashboard_route_contracts.py` and add focused route tests.

## Behavior and data flow

1. Serve `GET /api/v1/runs/{run_id}/report` to principals already authorized to read that run.
   Return 404 for missing run/report without cross-tenant disclosure; use a stable response model
   with report state and deterministic status.
2. Do not expose raw prompt, model response, credentials, binary artifact bytes, or internal
   provider diagnostics. Evidence links reuse existing authorized run-scoped artifact download
   behavior.
3. Run detail loads report alongside run and artifacts. While queued/running, show “Report will be
   prepared after a deterministic result.” After a historical terminal run without a report, show
   “No report is available for this historical run.”
4. On `completed`, label the report advisory and show it cannot change the result. On `unavailable`,
   show safe reason and retain runner result as the primary verdict.
5. Failure display prioritizes failure location, message, and linked textual evidence; pass display
   prioritizes executed scope, observations, and unverified/skip limitations so a pass is not
   mistaken for complete coverage.

## Validation

```bash
uv run pytest tests/test_run_routes.py tests/test_dashboard_route_contracts.py \
  tests/test_reporting_routes.py
uv run ruff check apps/control-plane tests
corepack pnpm --dir apps/dashboard typecheck
corepack pnpm --dir apps/dashboard lint
corepack pnpm --dir apps/dashboard test
uv run pytest tests/test_playwright_worker_compose.py
```

## Acceptance criteria

- Authorized viewers see a report for both passed and failed new runs, including an explicit
  coverage/limitation section.
- A failed run with an available Playwright location displays the file/line/assertion and evidence
  link; a failed run without it states that it was unavailable.
- Viewers cannot approve, edit, rerun, or alter a report; cross-tenant requests are denied.
- Existing triage proposal approval UI and deterministic run verdicts remain unchanged.

## Risks and non-goals

- No push notification/email/Slack delivery in v1.
- No automatic historical report generation, report regeneration, or source/test modification.

## Completion record

- Status: completed 2026-08-13T23:27:59+07:00.
- Delivered a tenant/RBAC-scoped report read endpoint with a strict safe response model, dashboard
  report presentation for completed/unavailable/pending/historical states, and authorized evidence
  download links. The view exposes no write, approval, rerun, or verdict-changing controls.
- Validation passed: focused run/dashboard/reporting route tests (14 passed), scoped Ruff,
  dashboard typecheck/lint/tests (13 passed), the local Playwright Compose suite (3 passed), and
  `git diff --check`.
- Deviation: none. Existing FastAPI TestClient and Node module-type warnings are non-failing and
  pre-existing test-environment warnings.
