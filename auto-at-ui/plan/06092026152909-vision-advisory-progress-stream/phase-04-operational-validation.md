# Phase 04 — Operational validation

## Objective

## Completion record

**Status:** completed (2026-09-06 16:05 ICT)

Documented safe session progress and Last-Event-ID stream usage. No provider call,
tenant enablement, retention change, or production action was performed. Focused
tests passed (21), ruff passed, the complete Python suite completed successfully
(214 collected), and dashboard test/typecheck/lint/build passed.

Prove that the progress stream is safe, observable, backward-compatible, and ready
for the existing disabled-by-default Vision rollout path.

## Scope and prerequisites

Phases 01–03 must be implemented and the migration applied in a local stack. This
phase selects no production provider, authentication system, cloud service, or
retention policy.

## Exact paths

Change if wording/API examples need updating:

- `docs/vision-agent-operations.md`
- `docs/api-examples.md`
- `README.md` (only if the Vision user journey materially needs the new live-status
  explanation)

Verify:

- `tests/test_activity.py`
- `tests/test_vision_event_processor.py`
- `tests/test_vision_progress.py`
- `tests/test_vision_routes.py`
- `apps/dashboard/app/vision-dashboard.test.ts`
- `apps/dashboard/app/components/vision-progress-timeline-model.test.ts`

## Implementation and validation steps

1. Update operational documentation to state that live progress contains redacted,
   bounded activity summaries only, is session/project scoped, and falls back to
   polling. Repeat that it is not model reasoning, raw visual evidence, or a verdict.
2. Add API examples for the authenticated session history/stream endpoint only if
   existing documentation covers Vision API usage. Include `Last-Event-ID` resume
   semantics and omit credentials from examples.
3. Apply the migration locally before exercising Vision. Run fixture-only Vision
   tests before any provider call, as prescribed by `docs/vision-agent-operations.md`.
4. Exercise a consenting local synthetic session: verify queued → running → safe
   milestones → action candidates → completed/unavailable; then verify browser SSE
   and deliberately blocked stream behavior fall back to polling. Verify a different
   tenant/project cannot access the session progress.
5. Inspect application logs, SSE payloads, database events, and audit records using
   sentinel secret/text inputs. Confirm that screenshots, temporary links, task
   intent, typed action text, provider output, exception detail, and secrets are
   absent. Record only aggregate/non-sensitive diagnostics.
6. Confirm existing generation handoff and human approval behavior remains unchanged
   and deterministic run result APIs still pass their fixture checks.

## Full validation commands

```powershell
uv run pytest tests/test_activity.py tests/test_vision_event_processor.py tests/test_vision_progress.py tests/test_vision_routes.py tests/test_vision_contracts.py
uv run ruff check .
uv run pytest
Set-Location apps/dashboard
pnpm test
pnpm typecheck
pnpm lint
pnpm build
```

## Acceptance criteria

The feature passes focused and baseline validation, exposes no forbidden data in
stream/history/error paths, preserves authorization isolation, and requires no new
provider/cost/retention decision to deploy behind the existing Vision policy.

## Risks and non-goals

Do not enable a production tenant or perform paid provider calls as part of this
phase. Production SLOs, data-region decisions, and retention changes remain separate
approval items.
