# Phase 4 — `/agent` controls and review experience

## Objective

Expose clear, authorized vision controls and session/proposal visibility in the
existing Agent workspace without moving security decisions into the dashboard.

## Execution status

**Status:** completed — 2026-08-31 21:19 ICT

Implementing dashboard controls against the Phase 1–3 control-plane endpoints.
Client state remains informational; authorization and policy enforcement stay
server-side.

## Completion record

The workspace now obtains policy and exploration state through authenticated
control-plane APIs, requires an explicit raw-image acknowledgement before a
tenant-admin policy save or exploratory submission, and confirms a raw-image
exploration before dispatch. It shows only safe action metadata (action kind,
bounded coordinates/timing, confidence, and checksum), correlation activity,
safe failure detail, and a link to the ordinary human draft review flow.

Validation passed: `npm.cmd run typecheck`, `npm.cmd test` (15 passed), focused
Ruff, and focused Python route/workflow tests (15 passed). The known Starlette
TestClient deprecation warning remains unrelated. The dashboard does not render
raw screenshots, prompt text, provider output, typed action content, expected
page content, or signed artifact URLs.

## Scope and prerequisites

- Complete the policy and session APIs from Phases 1–3.
- Reuse the current authenticated API client, CSRF handling, state components,
  activity timeline, and confirmation dialog conventions.

## Exact paths and changes

- Replace the thin wrapper in `apps/dashboard/app/agent/page.tsx` only as
  necessary to compose the enhanced workspace.  Extend
  `apps/dashboard/app/generation-dashboard.tsx`, or split a focused
  `vision-dashboard.tsx` if it keeps generation concerns readable.
- Extend `apps/dashboard/app/generation-api.ts` and `generation-types.ts` with
  typed policy/session/proposal calls.  All calls use the existing `apiRequest`
  path and credentials/CSRF behavior; client state is never authoritative.
- Add a tenant-admin-only Vision settings panel showing provider/model name,
  current enablement, guard summaries, and a required confirmation that raw
  screenshots may be sent to Hugging Face.  Disable save until explicit
  acknowledgement; render server authorization errors rather than inferring
  role permissions client-side.
- Add a per-request `Use Vision Agent` toggle.  It is disabled with explanatory
  text when server policy is off.  When toggled on, show the target, raw-image
  disclosure, action limits, and that exploration is not a test verdict.
- Add a session status/activity view: queued/running/completed/unavailable,
  safe actions/checksums/confidence/stop conditions, correlation ID, and link
  to the existing review flow.  Never render raw model prompts, provider
  responses, images from prompts, signed artifact URLs, or raw screen contents.
- Use the existing `ConfirmDialog` before starting a raw-image exploration and
  before draft approval.  Preserve accessible labels, keyboard behavior,
  loading/error/empty states, and responsive layout.

## Tests and validation

- Add component/model tests mirroring `generation-dashboard.test.ts` and
  `app-shell.test.ts`: policy-off control, disclosure/confirmation, request
  body, API error, polling terminal state, no unsafe content rendering, and
  link to proposal review.
- Extend `tests/test_dashboard_route_contracts.py` for the new typed control
  plane endpoints and add FastAPI HTTP tests proving UI-relevant RBAC semantics.
- Run `npm.cmd run typecheck`, dashboard tests, and focused Python route tests.

## Acceptance criteria

- A user can plainly choose vision per request only when an admin-enabled
  policy permits it; the UI cannot fake enablement.
- The workspace communicates the raw image transfer, advisory status, and human
  approval boundary before any request is submitted.

## Risks and non-goals

- This phase does not display the raw screenshots that were sent to the model;
  authorized run-artifact viewing remains its separate existing flow.
